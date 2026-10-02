#!/usr/bin/env python3
"""AI-XF v0.3 reference validator.

Validates an AI-XF bundle against the conformance ladder defined in ../SPEC.md:

  Level 0  OKF-compatible  — every non-reserved .md has parseable frontmatter
                             with a non-empty `type`.
  Level 1  AI-XF Core        — Level 0 + unique `id` per concept + manifest.ai-xf.yaml
                             declaring `ai-xf` and `name`.
  Level 2  AI-XF Full        — Level 1 + every `links` entry is a valid link object
                             (rel + resolvable `to`), same-bundle links mirrored
                             by a body link, + trust signals on every concept
                             (a `provenance` map or an OKF v0.2 trust field),
                             + every `media` entry carries a `uri`,
                             + any link `state` / `resolved` is well-formed.
  Level 3  AI-XF Federated   — Level 2 + manifest declares a valid `namespace`
                             and `vocabularies`; qualified references are
                             well-formed `namespace/id`.

Usage:
    python3 ai-xf-validate.py <bundle-dir> [--level N] [--json] [--stats]
                            [--federation <federation.ai-xf.yaml>]

`--stats` reports curation health (SPEC §6.5, §7.2, §10.2): trust tiers,
staleness, open and resolved contradictions, per-claim citation coverage, the
spread of asserted confidence, the Update:Creation ratio from log.md, and
freshness (E8): concept files no index.md lists, and live edges into retired
concepts. With `--federation` it adds edges into other bundles' retired
concepts and the federation vocabulary declared but unused (by rel pair). It
never affects pass/fail — it measures whether a bundle is compounding, which
is a question of policy, not conformance.

`--federation <path>` (experimental, SPEC §9) loads a `federation.ai-xf.yaml`
manifest describing sibling bundles (`bundles[]`, each `source: path` or
`source: git`), builds a namespace -> id index across all of them, and
resolves the bundle-under-test's `to:` references against it:
  - `namespace/id` and the explicit `ai-xf://namespace/id` form resolve against
    the federation index; unresolved is a tolerated warning, and a reference
    qualified with the bundle's own namespace is an error (SPEC §9.2).
  - An unqualified `to:` that fails to resolve in the bundle itself but does
    resolve in one or more other federated bundles resolves deterministically
    (own bundle first, then other namespaces alphabetically) with a warning
    naming every candidate and the one chosen — never silently.
`source: git` entries are, for now, resolved as a local path: `subdir`
relative to the manifest's own git repository root. Git fetching itself is
out of scope; `ref` is recorded for provenance reporting only. With
`--federation`, `--stats` gains a `federation` block and the text/JSON output
report which bundles were held and their resolved roots.

Self-contained: uses PyYAML if present, otherwise a minimal built-in parser
covering the subset of YAML that AI-XF frontmatter uses. Derives nothing from a
hardcoded path.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

RESERVED_MD = {"index.md", "log.md"}
LEGACY_SCHEMES = ("ai-x://", "aix://")        # earlier spellings of ai-xf://
MANIFEST_NAME = "manifest.ai-xf.yaml"
LEGACY_MANIFEST_NAMES = ("manifest.ai-x.yaml", "manifest.aix.yaml")   # earlier spellings: read, warn, never write

CORE_RELS = {
    "relates-to", "part-of", "has-part", "depends-on", "depended-on-by",
    "references", "referenced-by", "derived-from", "source-of",
    "supersedes", "superseded-by", "contradicts", "authored-by",
    "author-of", "describes", "described-by",
    # added in v0.3
    "supports", "supported-by", "merged-into", "merged-from",
    "split-from", "split-into",
    # added in v0.4
    "imported", "exported-to",
}

# Inverse column of SPEC §6.2, including the registered extension rels. A rel
# pair counts as used when either direction is written (§6.3 synthesises the
# other), so `--stats` reports unused vocabulary by pair, never by inverse name.
REL_INVERSES = {
    "relates-to": "relates-to", "part-of": "has-part", "depends-on": "depended-on-by",
    "references": "referenced-by", "derived-from": "source-of", "supersedes": "superseded-by",
    "contradicts": "contradicts", "supports": "supported-by", "merged-into": "merged-from",
    "split-from": "split-into", "imported": "exported-to", "authored-by": "author-of",
    "describes": "described-by", "depicts": "depicted-in", "remediates": "remediated-by",
    "discusses": "discussed-in",
}
REL_INVERSES.update({inv: fwd for fwd, inv in list(REL_INVERSES.items())})

SUCCESSOR_RELS = {"superseded-by", "merged-into"}
OKF_STATUS = {"draft", "stable", "deprecated"}
LINK_STATES = {"open", "resolved"}
OUTCOMES = {"superseded", "reconciled", "both-stand"}
# AI-XF v0.2 actor spellings that deviate from OKF's convention (SPEC §7.3).
BAD_ACTOR_PREFIXES = ("agent:", "pipeline:")
LOG_WORDS = ("Initialization", "Creation", "Update", "Merge", "Split",
             "Deprecation", "Contradiction", "Resolution", "Gap")

# Registered extension rels (SPEC §6.2) — allowed without a warning.
EXT_RELS = {
    "depicts", "depicted-in", "remediates", "remediated-by",
    "discusses", "discussed-in",
}

# OKF v0.2 trust/lifecycle fields — any one satisfies the Level 2 trust rule.
OKF_TRUST_FIELDS = ("sources", "generated", "verified", "status", "stale_after")

# Deprecated v0.1 keys (SPEC §7.3) — read, don't write.
DEPRECATED_PROV_KEYS = ("verified", "freshness", "reviewed")

QUALIFIED_RE = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*$")
HASH_RE = re.compile(r"^[a-z0-9]+:[0-9a-fA-F…]+$")

# --- YAML loading (PyYAML if available, else a minimal fallback) -------------

try:
    import yaml  # type: ignore

    def load_yaml(text: str):
        return yaml.safe_load(text)
except Exception:  # pragma: no cover - fallback path
    def load_yaml(text: str):
        return _mini_yaml(text)


def _coerce(v: str):
    s = v.strip()
    if s == "" or s == "~" or s.lower() == "null":
        return None
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_coerce(x) for x in inner.split(",")] if inner else []
    if s.startswith("{") and s.endswith("}"):
        out = {}
        for part in s[1:-1].split(","):
            if ":" in part:
                k, _, v = part.partition(":")
                out[k.strip()] = _coerce(v)
        return out
    if " #" in s:  # trailing comment on an unquoted scalar
        return _coerce(s.split(" #", 1)[0])
    return s


def _mini_yaml(text: str):
    """Minimal parser: top-level scalars/lists/maps, one level of nesting,
    and lists-of-maps (as used by AI-XF `links`). Not a general YAML parser."""
    root: dict = {}
    lines = [ln.rstrip("\n") for ln in text.split("\n")]
    i = 0
    n = len(lines)

    def indent(ln: str) -> int:
        return len(ln) - len(ln.lstrip(" "))

    while i < n:
        ln = lines[i]
        if not ln.strip() or ln.lstrip().startswith("#"):
            i += 1
            continue
        if indent(ln) != 0:
            i += 1
            continue
        key, _, rest = ln.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest:
            root[key] = _coerce(rest)
            i += 1
            continue
        # block value: gather deeper-indented lines — or, as PyYAML dumps
        # them, list items at column 0 directly under the key (`links:\n- rel:`)
        block = []
        j = i + 1
        while j < n and (not lines[j].strip() or indent(lines[j]) > 0
                         or (lines[j].startswith("- ") and (block or j == i + 1))):
            block.append(lines[j])
            j += 1
        root[key] = _parse_block(block)
        i = j
    return root


def _parse_block(block: list[str]):
    items = [ln for ln in block if ln.strip() and not ln.lstrip().startswith("#")]
    if not items:
        return None
    base = min(len(ln) - len(ln.lstrip(" ")) for ln in items)
    is_list = all(ln.lstrip().startswith("- ") or ln.strip() == "-" for ln in items
                  if (len(ln) - len(ln.lstrip(" "))) == base)
    if is_list:
        result = []
        cur = None
        key_indent = None   # indent of an item's own keys
        nested = None       # open nested map, e.g. links[].resolved
        for ln in items:
            ind = len(ln) - len(ln.lstrip(" "))
            body = ln.lstrip()
            if ind == base and body.startswith("-"):
                if cur is not None:
                    result.append(cur)
                nested = None
                key_indent = ind + 2
                body = body[1:].strip()
                if not body:
                    cur = {}
                elif ":" in body:
                    k, _, v = body.partition(":")
                    cur = {k.strip(): _coerce(v)}
                else:
                    cur = _coerce(body)
            elif isinstance(cur, dict) and ":" in body:
                k, _, v = body.partition(":")
                if key_indent is None:
                    key_indent = ind
                if ind > key_indent and isinstance(nested, dict):
                    nested[k.strip()] = _coerce(v)
                    continue
                val = _coerce(v)
                if val is None and not v.strip():
                    val = nested = {}
                else:
                    nested = None
                cur[k.strip()] = val
        if cur is not None:
            result.append(cur)
        return result
    # map
    result = {}
    for ln in items:
        if (len(ln) - len(ln.lstrip(" "))) != base:
            continue
        k, _, v = ln.strip().partition(":")
        result[k.strip()] = _coerce(v.strip())
    return result


# --- Bundle parsing ----------------------------------------------------------

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


class Finding:
    def __init__(self, level: str, path: str, msg: str):
        self.level = level  # "error" | "warning"
        self.path = path
        self.msg = msg

    def as_dict(self):
        return {"severity": self.level, "file": self.path, "message": self.msg}


def parse_concept(path: Path):
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if not m:
        return None, "", text
    fm_raw = m.group(1)
    body = text[m.end():]
    try:
        fm = load_yaml(fm_raw)
    except Exception as e:  # noqa: BLE001
        return "PARSE_ERROR", str(e), body
    if not isinstance(fm, dict):
        return "PARSE_ERROR", "frontmatter is not a mapping", body
    return fm, "", body


def body_link_targets(body: str, concept_dir: Path, bundle: Path, path_to_id: dict | None = None):
    """Return the set of normalised targets (id-or-relpath) linked in the body."""
    targets = set()
    for raw in MD_LINK_RE.findall(body):
        tgt = link_destination(raw)
        if not tgt or tgt.startswith(("http://", "https://", "mailto:")):
            continue
        targets.add(tgt)
        # also record the resolved id (filename stem) for id-based matching
        stem = Path(tgt).stem
        targets.add(stem)
        # and the id of the concept file the link actually lands on, so a file
        # moved or renamed with its id unchanged still mirrors (SPEC §5.2)
        if path_to_id:
            for cand in (concept_dir / tgt, bundle / tgt):
                hit = path_to_id.get(cand.resolve())
                if hit:
                    targets.add(hit)
        # ai-xf://<namespace>/<id> (federation-qualified, SPEC §9.2) also
        # mirrors a bare `namespace/id` link target with the same meaning.
        if tgt.startswith("ai-xf://"):
            targets.add(tgt[len("ai-xf://"):])
    return targets


def link_destination(raw: str) -> str:
    """The path part of a markdown link destination: `<a b.md>` unwrapped, a
    trailing `"title"` dropped, the `#fragment` removed, `%20` decoded."""
    from urllib.parse import unquote
    raw = raw.strip()
    if raw.startswith("<") and ">" in raw:
        raw = raw[1:raw.index(">")]
    else:
        raw = raw.split()[0] if raw.split() else ""
    return unquote(raw.split("#")[0])


def as_list(v):
    """OKF lets a single map stand for a one-element list (e.g. `verified`)."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def actors_of(fm: dict):
    """Yield (where, actor) for every identity-bearing field in a concept."""
    gen = fm.get("generated")
    if isinstance(gen, dict) and gen.get("by"):
        yield "generated.by", gen["by"]
    for i, v in enumerate(as_list(fm.get("verified"))):
        if isinstance(v, dict) and v.get("by"):
            yield f"verified[{i}].by", v["by"]
    for i, ln in enumerate(as_list(fm.get("links"))):
        if not isinstance(ln, dict):
            continue
        if ln.get("by"):
            yield f"links[{i}].by", ln["by"]
        for j, v in enumerate(as_list(ln.get("verified"))):
            if isinstance(v, dict) and v.get("by"):
                yield f"links[{i}].verified[{j}].by", v["by"]
        res = ln.get("resolved")
        if isinstance(res, dict) and res.get("by"):
            yield f"links[{i}].resolved.by", res["by"]


def timestamps_of(fm: dict):
    """Yield (where, value) for every timestamp-valued key in a concept: the
    OKF ones (§7.1) and the AI-XF edge ones (§6.1). SPEC §5.6."""
    yield "stale_after", fm.get("stale_after")
    gen = fm.get("generated")
    if isinstance(gen, dict):
        yield "generated.at", gen.get("at")
    for i, v in enumerate(as_list(fm.get("verified"))):
        if isinstance(v, dict):
            yield f"verified[{i}].at", v.get("at")
    windows = [("usage_window", fm.get("usage_window"))]
    for i, src in enumerate(as_list(fm.get("sources"))):
        if isinstance(src, dict):
            yield f"sources[{i}].last_modified", src.get("last_modified")
            windows.append((f"sources[{i}].usage_window", src.get("usage_window")))
    for where, w in windows:
        if isinstance(w, dict):
            yield f"{where}.from", w.get("from")
            yield f"{where}.to", w.get("to")
    for i, ln in enumerate(as_list(fm.get("links"))):
        if not isinstance(ln, dict):
            continue
        yield f"links[{i}].at", ln.get("at")
        res = ln.get("resolved")
        if isinstance(res, dict):
            yield f"links[{i}].resolved.at", res.get("at")
        for j, v in enumerate(as_list(ln.get("verified"))):
            if isinstance(v, dict):
                yield f"links[{i}].verified[{j}].at", v.get("at")


OFFSET_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|z|[+-]\d{2}(:?\d{2})?)$")


def has_offset(v) -> bool:
    """An ISO 8601 datetime with an explicit UTC offset (OKF v0.2, PR #6).
    PyYAML hands back datetime objects, the fallback parser strings: both
    must give the same answer."""
    if isinstance(v, datetime):
        return v.tzinfo is not None
    if isinstance(v, date):
        return False
    return bool(OFFSET_DT_RE.match(str(v).strip()))


def to_instant(v):
    """A timestamp as an aware UTC datetime. A bare date, or a datetime with
    no offset, is read as UTC (the date at 00:00), the legacy reading."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    sv = str(v).strip()
    try:
        dt = datetime.fromisoformat(sv[:-1] + "+00:00" if sv[-1:] in "Zz" else sv)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        d = to_date(sv)
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) if d else None


def to_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if v is None:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(v))
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def trust_tier(fm: dict) -> str:
    events = [v for v in as_list(fm.get("verified")) if isinstance(v, dict) and v.get("by")]
    if not events:
        return "unverified"
    if any(str(v["by"]).startswith("human:") for v in events):
        return "human-reviewed"
    return "machine-confirmed"


FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]]+)\](?!:)")
LOG_ENTRY_RE = re.compile(r"^\s*[-*]\s+\*\*([A-Za-z]+)\*\*", re.MULTILINE)


def collect_stats(bundle: Path, now) -> dict:
    """Curation-health numbers. Informational: never affects conformance.
    `now` is the instant `stale_after` is compared with (a date means 00:00 UTC)."""
    now = to_instant(now)
    concepts = {}
    paths = {}
    for p in sorted(bundle.rglob("*.md")):
        if p.name in RESERVED_MD:
            continue
        fm, _err, body = parse_concept(p)
        if not isinstance(fm, dict):
            continue
        cid = str(fm.get("id") or p.relative_to(bundle))
        concepts[cid] = (fm, body)
        paths[cid] = p.resolve()

    n = len(concepts)
    status = Counter(str(fm.get("status") or "stable") for fm, _ in concepts.values())
    tiers = Counter(trust_tier(fm) for fm, _ in concepts.values())
    conf = Counter()
    past_stale = no_stale = with_sources = cited = 0
    withheld_total = verified_edges = 0
    orphan_footnotes = 0
    rels = Counter()
    contradictions: dict = {}
    retired = []

    for cid, (fm, body) in concepts.items():
        prov = fm.get("provenance")
        if isinstance(prov, dict) and prov.get("confidence"):
            conf[str(prov["confidence"])] += 1
        sa = to_instant(fm.get("stale_after"))
        if sa is None:
            no_stale += 1
        elif now >= sa and str(fm.get("status")) != "deprecated":
            past_stale += 1
        src_ids = {str(s["id"]) for s in as_list(fm.get("sources"))
                   if isinstance(s, dict) and s.get("id")}
        withheld_total += sum(int(s["withheld"]) for s in as_list(fm.get("sources"))
                              if isinstance(s, dict) and isinstance(s.get("withheld"), int))
        verified_edges += sum(1 for ln in as_list(fm.get("links"))
                              if isinstance(ln, dict) and as_list(ln.get("verified")))
        refs = set(FOOTNOTE_REF_RE.findall(body))
        if as_list(fm.get("sources")):
            with_sources += 1
            if refs & src_ids:
                cited += 1
        orphan_footnotes += len(refs - src_ids) if src_ids else 0
        links = [ln for ln in as_list(fm.get("links")) if isinstance(ln, dict)]
        for ln in links:
            relv = str(ln.get("rel") or "")
            rels[relv] += 1
            if relv == "contradicts" and ln.get("to"):
                key = frozenset((cid, str(ln["to"])))
                state = str(ln.get("state") or "open")
                if state not in LINK_STATES:
                    state = "open"
                res = ln.get("resolved") if isinstance(ln.get("resolved"), dict) else {}
                human = str(res.get("by") or "").startswith("human:")
                if state == "resolved" and not human:
                    state = "resolved-machine-only"
                prev = contradictions.get(key)
                # declared on both sides with different states => open (SPEC §6.5)
                contradictions[key] = state if prev in (None, state) else "open"
        if str(fm.get("status")) == "deprecated" and \
                not any(str(ln.get("rel")) in SUCCESSOR_RELS for ln in links):
            retired.append(cid)

    # Freshness (E8). A concept file no index.md lists was not written by the
    # producer that regenerated the index: a ghost of an earlier export, or never
    # indexed. Only meaningful when the bundle has an index at all.
    indexes = sorted(bundle.rglob("index.md"))
    unindexed = None
    if indexes:
        listed = set()
        for ip in indexes:
            for raw in MD_LINK_RE.findall(ip.read_text(encoding="utf-8")):
                tgt = link_destination(raw)
                if tgt and not tgt.startswith(("http://", "https://", "mailto:")):
                    listed.add((ip.parent / tgt).resolve())
        unindexed = sorted(str(paths[c].relative_to(bundle.resolve())) for c in concepts
                           if paths[c] not in listed)
    # Live edges into retired concepts: a successor means a redirect (§6.6);
    # none means the edge points at something the bundle says is gone.
    is_retired = {cid: not any(str(ln.get("rel")) in SUCCESSOR_RELS
                               for ln in as_list(fm.get("links")) if isinstance(ln, dict))
                  for cid, (fm, _) in concepts.items() if str(fm.get("status")) == "deprecated"}
    into_retired = into_redirect = 0
    by_path = {path: cid for cid, path in paths.items()}
    def local_id(to: str) -> str:
        """`to` is an id or a bundle-relative path (SPEC §6.1)."""
        if to in concepts:
            return to
        for cand in (bundle / to, bundle / f"{to}.md"):
            hit = by_path.get(cand.resolve())
            if hit:
                return hit
        return to
    for cid, (fm, _) in concepts.items():
        if str(fm.get("status")) == "deprecated":
            continue
        for ln in as_list(fm.get("links")):
            to = local_id(str(ln.get("to") or "")) if isinstance(ln, dict) else ""
            if to in is_retired and str(ln.get("rel")) not in SUCCESSOR_RELS | {"supersedes", "merged-from"}:
                if is_retired[to]:
                    into_retired += 1
                else:
                    into_redirect += 1

    # Supersession without retirement: something replaces this concept (a
    # `supersedes`/`merged-into` edge points at it, or it names its own
    # successor) but it is not `status: deprecated` (§6.2, §6.6).
    replaced = set()
    for cid, (fm, _) in concepts.items():
        for ln in as_list(fm.get("links")):
            if not isinstance(ln, dict):
                continue
            to = local_id(str(ln.get("to") or ""))
            if str(ln.get("rel")) in ("supersedes", "merged-from") and to in concepts:
                replaced.add(to)
            if str(ln.get("rel")) in SUCCESSOR_RELS:
                replaced.add(cid)
    superseded_live = sorted(c for c in replaced if str(concepts[c][0].get("status")) != "deprecated")
    # Event-based staleness from OKF fields alone: a source that changed after
    # the concept was last verified (`sources[].last_modified` > `verified[].at`).
    # Likewise the content itself: `generated.at` marks its last meaningful
    # change (OKF §5.2), so a later `generated.at` means it changed after the
    # latest check. OKF keeps the tier; a consumer may not (KnowledgeX, E9).
    source_changed, content_changed = [], []
    for cid, (fm, _) in concepts.items():
        checked = [t for v in as_list(fm.get("verified")) if isinstance(v, dict)
                   for t in [to_instant(v.get("at"))] if t]
        gen = fm.get("generated")
        gen_at = to_instant(gen.get("at")) if isinstance(gen, dict) else None
        if checked and gen_at and gen_at > max(checked):
            content_changed.append(cid)
        changed = [t for s_ in as_list(fm.get("sources")) if isinstance(s_, dict)
                   for t in [to_instant(s_.get("last_modified"))] if t]
        if checked and changed and max(changed) > max(checked):
            source_changed.append(cid)

    cstate = Counter(contradictions.values())
    log_words = Counter()
    for lp in bundle.rglob("log.md"):
        log_words.update(LOG_ENTRY_RE.findall(lp.read_text(encoding="utf-8")))
    known = {w: log_words.get(w, 0) for w in LOG_WORDS if log_words.get(w)}
    created, updated = log_words.get("Creation", 0), log_words.get("Update", 0)

    top_conf = max(conf.values()) if conf else 0
    total_conf = sum(conf.values())
    flags = []
    if total_conf >= 10 and top_conf / total_conf >= 0.7:
        label = max(conf, key=conf.get)
        flags.append(f"{top_conf} of {total_conf} confidence labels say `{label}` — "
                     "a label nearly everyone gets carries no information (SPEC §7.2)")
    if n >= 10 and not contradictions:
        flags.append("no `contradicts` edge in the bundle — either nothing here has ever "
                     "disagreed, or the curator is reconciling silently (SPEC §6.5)")
    if created >= 10 and updated == 0:
        flags.append("log.md records creations but no updates — accumulating, not compounding")
    if unindexed:
        flags.append(f"{len(unindexed)} concept file(s) listed in no index.md — left behind by an earlier "
                     "export, or never indexed; retire them as tombstones (SPEC §6.6) or index them")
    if superseded_live:
        flags.append(f"{len(superseded_live)} concept(s) replaced by another but not `status: deprecated`: "
                     f"{', '.join(superseded_live[:5])}" + (" …" if len(superseded_live) > 5 else "")
                     + " (SPEC §6.6)")
    if content_changed:
        flags.append(f"{len(content_changed)} concept(s) changed after they were last verified "
                     "(`generated.at` > `verified[].at`) — re-verify them, or some consumers will treat them as unverified")
    if source_changed:
        flags.append(f"{len(source_changed)} concept(s) whose sources changed after they were last verified "
                     "(`sources[].last_modified` > `verified[].at`) — re-check them")
    if into_retired:
        flags.append(f"{into_retired} edge(s) from live concepts point at retired concepts with no "
                     "successor — re-point or drop them (SPEC §6.6)")

    return {
        "as_of": now.date().isoformat(),
        "concepts": n,
        "status": dict(status),
        "trust_tiers": dict(tiers),
        "staleness": {"past_stale_after": past_stale, "no_stale_after": no_stale},
        "contradictions": {"open": cstate.get("open", 0),
                           "resolved": cstate.get("resolved", 0),
                           "resolved_machine_only": cstate.get("resolved-machine-only", 0)},
        "edges": {k: rels[k] for k in ("supports", "supersedes", "superseded-by",
                                       "merged-into", "split-from") if rels.get(k)},
        "deprecated_without_successor": retired,
        "per_claim_citation": {"concepts_with_sources": with_sources,
                               "citing_per_claim": cited,
                               "footnotes_matching_no_source": orphan_footnotes},
        "confidence": dict(conf),
        "freshness": {"unindexed": unindexed,
                      "edges_into_retired": into_retired,
                      "edges_into_redirects": into_redirect,
                      "superseded_not_deprecated": superseded_live,
                      "sources_changed_since_verified": source_changed,
                      "changed_since_verified": content_changed},
        "withheld_sources": withheld_total,
        "verified_edges": verified_edges,
        "log": {"entries": known,
                "update_to_creation": (round(updated / created, 2) if created else None)},
        "flags": flags,
    }


def print_stats(s: dict):
    print(f"\nCuration health (as of {s['as_of']}) — informational, never affects pass/fail")
    n = s["concepts"] or 1
    fmt = lambda d: ", ".join(f"{k} {v}" for k, v in d.items()) or "none"
    print(f"  status:            {fmt(s['status'])}")
    print(f"  trust tiers:       {fmt(s['trust_tiers'])}")
    st = s["staleness"]
    print(f"  staleness:         {st['past_stale_after']} of {s['concepts']} past `stale_after` "
          f"({100 * st['past_stale_after'] // n}%), {st['no_stale_after']} with none set")
    c = s["contradictions"]
    extra = f", {c['resolved_machine_only']} resolved by machine only" if c["resolved_machine_only"] else ""
    print(f"  contradictions:    {c['open']} open, {c['resolved']} resolved{extra}")
    print(f"  change edges:      {fmt(s['edges'])}")
    if s["deprecated_without_successor"]:
        print(f"  retired (no successor): {', '.join(s['deprecated_without_successor'])}")
    pc = s["per_claim_citation"]
    print(f"  per-claim cites:   {pc['citing_per_claim']} of {pc['concepts_with_sources']} sourced concepts"
          + (f"; {pc['footnotes_matching_no_source']} footnote(s) match no source id"
             if pc["footnotes_matching_no_source"] else ""))
    fr = s["freshness"]
    unidx = "no index.md" if fr["unindexed"] is None else f"{len(fr['unindexed'])} concept file(s) in no index.md"
    print(f"  freshness:         {unidx}; {fr['edges_into_retired']} live edge(s) into retired concepts, "
          f"{fr['edges_into_redirects']} into redirects")
    if fr["superseded_not_deprecated"] or fr["sources_changed_since_verified"] or fr["changed_since_verified"]:
        print(f"    replaced, live:  {len(fr['superseded_not_deprecated'])}; changed since verified: "
              f"{len(fr['changed_since_verified'])}; sources changed since verified: "
              f"{len(fr['sources_changed_since_verified'])}")
    if fr["unindexed"]:
        print(f"    unindexed:       {', '.join(fr['unindexed'][:10])}"
              + (f" … (+{len(fr['unindexed']) - 10})" if len(fr["unindexed"]) > 10 else ""))
    print(f"  confidence:        {fmt(s['confidence'])}")
    if s.get("withheld_sources") or s.get("verified_edges"):
        print(f"  redaction/edges:   {s.get('withheld_sources', 0)} source(s) withheld, {s.get('verified_edges', 0)} edge(s) with verified events")
    lg = s["log"]
    ratio = lg["update_to_creation"]
    print(f"  log.md:            {fmt(lg['entries'])}")
    print(f"  update:creation:   {ratio if ratio is not None else 'n/a'}")
    for f in s["flags"]:
        print(f"  ! {f}")
    fed = s.get("federation")
    if fed:
        print("  federation:")
        print(f"    bundles held:      {fed['bundles_held']} ({', '.join(fed['namespaces']) or 'none'})")
        print(f"    concepts/ns:       {fmt(fed['concepts_per_namespace'])}")
        if fed["colliding_ids"]:
            coll = ", ".join(f"{cid} [{'/'.join(nss)}]" for cid, nss in fed["colliding_ids"].items())
            print(f"    colliding ids:     {coll}")
        else:
            print("    colliding ids:     none")
        qr = fed["qualified_refs"]
        print(f"    qualified refs:    {qr['resolved']} resolved, {qr['unresolved']} unresolved")
        print(f"    unqualified cross-bundle resolutions (Foam rule): {fed['unqualified_cross_bundle_resolutions']}")
        print(f"    edges into other bundles' retired concepts: {fed['cross_bundle_edges_into_retired']}")
        vu = fed["vocabulary"]
        if vu["types_declared"] is not None:
            print(f"    types unused:      {len(vu['types_unused'])} of {vu['types_declared']}"
                  + (f" ({', '.join(vu['types_unused'])})" if vu["types_unused"] else ""))
        if vu["rel_pairs_declared"] is not None:
            print(f"    rel pairs unused:  {len(vu['rel_pairs_unused'])} of {vu['rel_pairs_declared']}"
                  + (f" ({', '.join(vu['rel_pairs_unused'])})" if vu["rel_pairs_unused"] else ""))


# --- Federation loading (SPEC §9, experimental --federation flag) -----------

def qualified_parts(to: str):
    """If `to` is a well-formed qualified reference — `namespace/id` or the
    explicit `ai-xf://namespace/id` form (SPEC §9.2, NEW) — return
    (namespace, id, explicit); otherwise None. Does not check resolution."""
    for old in LEGACY_SCHEMES:
        if isinstance(to, str) and to.startswith(old):
            to = "ai-xf://" + to[len(old):]
            break
    explicit = to.startswith("ai-xf://")
    qual = to[len("ai-xf://"):] if explicit else to
    if QUALIFIED_RE.match(qual):
        ns, _, cid = qual.partition("/")
        return ns, cid, explicit
    return None


def find_repo_root(start: Path) -> Path | None:
    """Walk upward from `start` looking for a `.git` directory."""
    cur = start.resolve()
    for parent in (cur, *cur.parents):
        if (parent / ".git").exists():
            return parent
    return None


def scan_bundle_aliases(bundle_root: Path) -> dict[str, str]:
    """Map alias -> concept `id` for one bundle (SPEC §6.6 fallback). An alias
    that is also an id in the bundle never shadows that id."""
    ids, out = set(), {}
    entries = []
    for p in sorted(bundle_root.rglob("*.md")):
        if p.name in RESERVED_MD:
            continue
        fm, _err, _body = parse_concept(p)
        if isinstance(fm, dict) and fm.get("id"):
            ids.add(str(fm["id"]))
            entries.append((str(fm["id"]), as_list(fm.get("aliases"))))
    for cid, als in entries:
        for al in als:
            if isinstance(al, str) and al not in ids:
                out.setdefault(al, cid)
    return out


def scan_bundle_ids(bundle_root: Path) -> dict[str, Path]:
    """Map concept `id` -> file path for one bundle, for the federation index.
    Concepts without an `id` or with unparseable frontmatter are skipped —
    they are simply not addressable federation-wide (SPEC §5.2 makes `id`
    the preferred link target; a path-only concept can't be a fed target)."""
    ids: dict[str, Path] = {}
    for p in sorted(bundle_root.rglob("*.md")):
        if p.name in RESERVED_MD:
            continue
        fm, _err, _body = parse_concept(p)
        if not isinstance(fm, dict):
            continue
        cid = fm.get("id")
        if cid:
            ids[str(cid)] = p
    return ids


def load_federation(fed_path: Path):
    """Load a federation.ai-xf.yaml manifest (proposed format, MyVault plan
    2026-09-26 §1). Returns (federation, findings, bundle_reports):
      - federation: {"index": {namespace: {id: Path}}, "namespaces": [...],
        "vocab_types": set|None, "vocab_rels": set|None}
      - findings: Finding list, reported under the synthetic path
        "federation.ai-xf.yaml" regardless of the manifest's real location.
      - bundle_reports: [{"namespace", "root", "ref", "source"}, ...] for
        the provenance report (E1)."""
    findings: list[Finding] = []
    fed_label = "federation.ai-xf.yaml"
    try:
        man = load_yaml(fed_path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        findings.append(Finding("error", fed_label, f"federation manifest parse error: {e}"))
        return {"index": {}, "namespaces": [], "vocab_types": None, "vocab_rels": None}, findings, []

    fed_dir = fed_path.parent
    repo_root = find_repo_root(fed_dir)

    index: dict[str, dict[str, Path]] = {}
    aliases: dict[str, dict[str, str]] = {}
    namespaces_seen: list[str] = []
    bundle_reports: list[dict] = []

    for i, entry in enumerate(as_list(man.get("bundles"))):
        if not isinstance(entry, dict):
            findings.append(Finding("error", fed_label, f"bundles[{i}] is not a mapping"))
            continue
        ns = entry.get("namespace")
        where = f"bundles[{i}]" if not ns else f"bundles[{i}] ({ns})"
        if not ns:
            findings.append(Finding("error", fed_label, f"{where} missing `namespace`"))
            continue
        ns = str(ns)
        if ns in namespaces_seen:
            findings.append(Finding("error", fed_label, f"duplicate namespace `{ns}` in federation manifest"))
        namespaces_seen.append(ns)

        source = entry.get("source")
        ref = entry.get("ref")
        root = None
        if source == "git":
            subdir = entry.get("subdir") or ""
            if repo_root is None:
                findings.append(Finding("error", fed_label,
                    f"{where} source: git — could not find the manifest's own git repo to "
                    "resolve `subdir` (git fetching is out of scope for this experiment)"))
            else:
                root = (repo_root / subdir).resolve()
        elif source == "path":
            rel_path = entry.get("path")
            if not rel_path:
                findings.append(Finding("error", fed_label, f"{where} source: path missing `path`"))
            else:
                root = (fed_dir / rel_path).resolve()
        elif source == "oci":
            # SPEC §9.5 / Appendix C: an OCI-distributed bundle. `digest` is the
            # provenance field. Pulling is out of scope; if the producer has
            # unpacked it locally, `path` says where, otherwise the bundle is
            # held only by reference and its ids are unknown to this run.
            if not entry.get("ref"):
                findings.append(Finding("error", fed_label, f"{where} source: oci missing `ref`"))
            digest = str(entry.get("digest") or "")
            if not digest:
                findings.append(Finding("warning", fed_label, f"{where} source: oci has no `digest` — no provenance (§9.5)"))
            elif not HASH_RE.match(digest):
                findings.append(Finding("warning", fed_label, f"{where} `digest: {digest}` is not `<algo>:<hex>` form"))
            ref = digest or ref
            if entry.get("path"):
                root = (fed_dir / str(entry["path"])).resolve()
            else:
                bundle_reports.append({"namespace": ns, "root": "(not held locally — OCI reference only)",
                                       "ref": ref, "source": source})
                continue
        else:
            findings.append(Finding("error", fed_label, f"{where} unknown `source: {source}` (expected `path`, `git` or `oci`)"))

        if root is None:
            continue

        bundle_manifest = root / MANIFEST_NAME
        if not bundle_manifest.exists():
            for old in LEGACY_MANIFEST_NAMES:
                if (root / old).exists():
                    bundle_manifest = root / old
                    findings.append(Finding("warning", fed_label, f"{where} uses earlier spelling {old} — rename to {MANIFEST_NAME}"))
                    break
        if not bundle_manifest.exists():
            findings.append(Finding("error", fed_label, f"{where} root `{root}` has no {MANIFEST_NAME}"))
            continue
        try:
            bman = load_yaml(bundle_manifest.read_text(encoding="utf-8")) or {}
        except Exception as e:  # noqa: BLE001
            findings.append(Finding("error", fed_label, f"{where} manifest parse error: {e}"))
            continue
        bundle_ns = bman.get("namespace")
        if str(bundle_ns) != ns:
            findings.append(Finding("error", fed_label,
                f"{where} bundle manifest declares namespace `{bundle_ns}`, federation entry says `{ns}`"))

        index[ns] = scan_bundle_ids(root)
        aliases[ns] = scan_bundle_aliases(root)
        bundle_reports.append({"namespace": ns, "root": str(root), "ref": ref, "source": source})

    vocab_types = vocab_rels = None
    vocab = man.get("vocabularies")
    if isinstance(vocab, dict):
        for key, target_name in (("types", "types"), ("rels", "rels")):
            v = vocab.get(key)
            if not v:
                continue
            vs = str(v)
            if vs.startswith(("http://", "https://")):
                continue  # remote vocab — existence not checked in this experiment
            vpath = (fed_dir / vs).resolve()
            if not vpath.exists():
                findings.append(Finding("error", fed_label, f"vocabularies.{key} `{vs}` does not exist"))
                continue
            try:
                vdata = json.loads(vpath.read_text(encoding="utf-8"))
                names = {str(item.get("name")) for item in vdata.get("values", [])
                         if isinstance(item, dict) and item.get("name")}
                if target_name == "types":
                    vocab_types = names
                else:
                    vocab_rels = names
            except Exception:  # noqa: BLE001
                pass  # not JSON of the {"version","values":[{"name"}]} shape — informational only

    federation = {"index": index, "aliases": aliases, "namespaces": namespaces_seen,
                  "vocab_types": vocab_types, "vocab_rels": vocab_rels}
    return federation, findings, bundle_reports


def federation_stats(federation: dict, bundle_reports: list[dict], bundle: Path | None = None) -> dict:
    """`--stats --federation` block: SPEC-agnostic curation numbers about the
    federation itself, never affecting pass/fail."""
    # Vocabulary declared vs used across every held bundle (E8). Zero uses is a
    # report, not drift: a federation vocabulary is agreed, not induced (§9.3).
    types_used, rels_used = Counter(), Counter()
    retired: set[str] = set()        # "ns/id" of deprecated concepts with no successor
    for b in bundle_reports:
        root = Path(b["root"])
        for p in sorted(root.rglob("*.md")):
            if p.name in RESERVED_MD:
                continue
            fm, _err, _body = parse_concept(p)
            if not isinstance(fm, dict):
                continue
            if fm.get("type"):
                types_used[str(fm["type"])] += 1
            links = [ln for ln in as_list(fm.get("links")) if isinstance(ln, dict)]
            rels_used.update(str(ln.get("rel")) for ln in links if ln.get("rel"))
            if str(fm.get("status")) == "deprecated" and \
                    not any(str(ln.get("rel")) in SUCCESSOR_RELS for ln in links):
                retired.add(f"{b['namespace']}/{fm.get('id') or p.stem}")
    vt, vr = federation.get("vocab_types"), federation.get("vocab_rels")
    pairs = None
    if vr is not None:
        pairs = sorted({tuple(sorted((r, REL_INVERSES.get(r, r)))) for r in vr})
    def pair_label(pr):
        return pr[0] if pr[0] == pr[1] else f"{pr[0]}/{pr[1]}"
    vocabulary = {
        "types_declared": len(vt) if vt is not None else None,
        "types_unused": sorted(t for t in vt if not types_used[t]) if vt is not None else [],
        "rel_pairs_declared": len(pairs) if pairs is not None else None,
        "rel_pairs_unused": [pair_label(pr) for pr in pairs
                             if not (rels_used[pr[0]] or rels_used[pr[1]])] if pairs is not None else [],
    }
    cross_retired = 0
    if bundle is not None:
        for p in sorted(bundle.rglob("*.md")):
            if p.name in RESERVED_MD:
                continue
            fm, _err, _body = parse_concept(p)
            if not isinstance(fm, dict) or str(fm.get("status")) == "deprecated":
                continue
            for ln in as_list(fm.get("links")):
                to = str(ln.get("to") or "") if isinstance(ln, dict) else ""
                if to.startswith("ai-xf://"):
                    to = to[len("ai-xf://"):]
                if QUALIFIED_RE.match(to) and to in retired:
                    cross_retired += 1
    index = federation["index"]
    concepts_per_ns = {ns: len(ids) for ns, ids in index.items()}
    id_to_ns: dict[str, list[str]] = {}
    for ns, ids in index.items():
        for cid in ids:
            id_to_ns.setdefault(cid, []).append(ns)
    colliding_ids = {cid: sorted(nss) for cid, nss in id_to_ns.items() if len(nss) > 1}
    st = federation.get("_stats") or {"qualified_resolved": 0, "qualified_unresolved": 0, "foam_resolutions": 0}
    return {
        "bundles_held": len(bundle_reports),
        "namespaces": federation["namespaces"],
        "concepts_per_namespace": concepts_per_ns,
        "colliding_ids": colliding_ids,
        "qualified_refs": {"resolved": st["qualified_resolved"], "unresolved": st["qualified_unresolved"]},
        "unqualified_cross_bundle_resolutions": st["foam_resolutions"],
        "cross_bundle_edges_into_retired": cross_retired,
        "vocabulary": vocabulary,
    }


def validate(bundle: Path, target_level: int, federation: dict | None = None):
    findings: list[Finding] = []
    concepts = []
    ids: dict[str, str] = {}

    md_files = [p for p in bundle.rglob("*.md") if p.name not in RESERVED_MD]

    # First pass: parse + collect ids (Level 0 + id collection)
    parsed = {}
    for p in sorted(md_files):
        rel = str(p.relative_to(bundle))
        fm, err, body = parse_concept(p)
        if fm is None:
            findings.append(Finding("error", rel, "no YAML frontmatter (OKF/AI-XF require it)"))
            continue
        if fm == "PARSE_ERROR":
            findings.append(Finding("error", rel, f"frontmatter parse error: {err}"))
            continue
        typ = fm.get("type")
        if not typ or not str(typ).strip():
            findings.append(Finding("error", rel, "missing or empty required field `type`"))
        elif federation is not None and federation.get("vocab_types") is not None \
                and str(typ) not in federation["vocab_types"]:
            findings.append(Finding("warning", rel, f"type `{typ}` is not in the federation vocabulary (tolerated — SPEC §5.1)"))
        parsed[rel] = (fm, body, p)
        concepts.append(rel)
        cid = fm.get("id")
        if cid:
            cid = str(cid)
            if "/" in cid:
                findings.append(Finding("error", rel, f"id `{cid}` must not contain `/` (reserved for qualified references)"))
            if cid in ids:
                findings.append(Finding("error", rel, f"duplicate id `{cid}` (also in {ids[cid]})"))
            else:
                ids[cid] = rel

    # Own namespace, for --federation resolution below (needed regardless of
    # target_level so a same-bundle qualified reference is always caught).
    own_ns = None
    if federation is not None:
        federation["_stats"] = {"qualified_resolved": 0, "qualified_unresolved": 0, "foam_resolutions": 0}
        own_manifest = bundle / MANIFEST_NAME
        if own_manifest.exists():
            try:
                own_man = load_yaml(own_manifest.read_text(encoding="utf-8")) or {}
                own_ns = own_man.get("namespace")
            except Exception:  # noqa: BLE001
                own_ns = None

    # Level 1 checks
    if target_level >= 1:
        manifest = bundle / MANIFEST_NAME
        if not manifest.exists():
            for old in LEGACY_MANIFEST_NAMES:
                if (bundle / old).exists():
                    manifest = bundle / old
                    findings.append(Finding("warning", old, "earlier spelling — rename to manifest.ai-xf.yaml (AI-XF v0.4.2)"))
                    break
        if not manifest.exists():
            findings.append(Finding("error", MANIFEST_NAME, "missing manifest.ai-xf.yaml (required at Level 1)"))
        else:
            try:
                man = load_yaml(manifest.read_text(encoding="utf-8")) or {}
                for old in ("ai-x", "aix"):
                    if man.get(old) and not man.get("ai-xf"):
                        findings.append(Finding("warning", MANIFEST_NAME, f"manifest key `{old}` is an earlier spelling — rename to `ai-xf`"))
                        man["ai-xf"] = man[old]
                for k in ("ai-xf", "name"):
                    if not man.get(k):
                        findings.append(Finding("error", MANIFEST_NAME, f"manifest missing `{k}`"))
            except Exception as e:  # noqa: BLE001
                findings.append(Finding("error", MANIFEST_NAME, f"manifest parse error: {e}"))
        for rel, (fm, _body, _p) in parsed.items():
            if not fm.get("id"):
                findings.append(Finding("error", rel, "missing `id` (required at Level 1)"))

    # Concept file -> id, so links that name a file (body links, path-form `to`)
    # can be compared by identity rather than by filename (SPEC §5.2, §6.1).
    path_to_id = {(bundle / r).resolve(): cid for cid, r in ids.items()}

    # §6.6: a consumer resolving an unknown id SHOULD fall back to `aliases`.
    alias_to_id: dict[str, str] = {}
    for _rel, (afm, _b, _p) in sorted(parsed.items()):
        aid = afm.get("id")
        if not aid:
            continue
        for al in as_list(afm.get("aliases")):
            if isinstance(al, str) and al not in ids:
                alias_to_id.setdefault(al, str(aid))

    def path_id(p: Path, to: str):
        for cand in (p.parent / to, bundle / to):
            hit = path_to_id.get(cand.resolve())
            if hit:
                return hit
        return None

    # Level 2 checks
    if target_level >= 2:
        for rel, (fm, body, p) in parsed.items():
            # trust signals: AI-XF provenance map OR any OKF v0.2 trust field
            has_prov = isinstance(fm.get("provenance"), dict)
            has_okf_trust = any(fm.get(k) is not None for k in OKF_TRUST_FIELDS)
            if not has_prov and not has_okf_trust:
                findings.append(Finding("error", rel, "no trust signals: needs a `provenance` map or an OKF v0.2 trust field (required at Level 2)"))
            # deprecated v0.1 forms (SPEC §7.3) — warn, don't fail
            if fm.get("timestamp") is not None:
                findings.append(Finding("warning", rel, "`timestamp` is deprecated — use `generated.at` (OKF v0.2)"))
            if has_prov:
                for k in DEPRECATED_PROV_KEYS:
                    if fm["provenance"].get(k) is not None:
                        findings.append(Finding("warning", rel, f"`provenance.{k}` is deprecated (SPEC §7.3) — use the OKF v0.2 field"))
            # OKF spellings AI-XF v0.2 got wrong (SPEC §7.3) — warn, don't fail
            st = fm.get("status")
            if st is not None and str(st) not in OKF_STATUS:
                hint = " — use `stable`" if str(st) == "active" else ""
                findings.append(Finding("warning", rel, f"`status: {st}` is not an OKF v0.2 value (draft | stable | deprecated){hint}"))
            for idx, src in enumerate(as_list(fm.get("sources"))):
                if isinstance(src, dict) and "withheld" in src:
                    # SPEC §7.5 redaction marker: a count, never a resource
                    w = src.get("withheld")
                    if not isinstance(w, int) or w < 1 or len(src) != 1:
                        findings.append(Finding("error", rel, f"sources[{idx}] `withheld` must be the sole key with a positive integer count (§7.5)"))
                    continue
                if isinstance(src, dict) and not src.get("resource"):
                    hint = " — rename `uri` to `resource`" if src.get("uri") else ""
                    findings.append(Finding("warning", rel, f"sources[{idx}] has no `resource` (REQUIRED by OKF v0.2){hint}"))
            # timestamps: ISO 8601 datetime with an explicit offset (SPEC §5.6,
            # OKF v0.2 since PR #6). A bare date is still read (as 00:00 UTC).
            for where, ts in timestamps_of(fm):
                if ts is not None and not has_offset(ts):
                    shown = ts.isoformat() if isinstance(ts, (date, datetime)) else ts   # same text under both parsers
                    findings.append(Finding("warning", rel, f"`{where}: {shown}` is not an ISO 8601 datetime with an "
                                            "offset (SPEC §5.6) — write e.g. `2027-02-20T00:00:00Z`; read as 00:00 UTC"))
            for where, actor in actors_of(fm):
                if str(actor).startswith(BAD_ACTOR_PREFIXES):
                    findings.append(Finding("warning", rel, f"{where} `{actor}` is not OKF's actor convention — use `<producer>/<version>`, `human:<id>` or `process:<id>`"))
            # media entries
            media = fm.get("media")
            if media is not None:
                if not isinstance(media, list):
                    findings.append(Finding("error", rel, "`media` must be a list"))
                else:
                    for idx, entry in enumerate(media):
                        where = f"media[{idx}]"
                        if not isinstance(entry, dict) or not entry.get("uri"):
                            findings.append(Finding("error", rel, f"{where} must be a mapping with a `uri`"))
                            continue
                        h = entry.get("hash")
                        if h is None:
                            findings.append(Finding("warning", rel, f"{where} has no `hash` — asset identity degrades to its URI"))
                        elif not HASH_RE.match(str(h)):
                            findings.append(Finding("warning", rel, f"{where} `hash: {h}` is not `<algo>:<hex>` form"))
            links = fm.get("links")
            if links is None:
                continue
            if not isinstance(links, list):
                findings.append(Finding("error", rel, "`links` must be a list"))
                continue
            btargets = body_link_targets(body, p.parent, bundle, path_to_id)
            for idx, link in enumerate(links):
                where = f"links[{idx}]"
                if not isinstance(link, dict):
                    findings.append(Finding("error", rel, f"{where} must be a mapping with `rel` and `to`"))
                    continue
                relv = link.get("rel")
                to = link.get("to")
                if not relv:
                    findings.append(Finding("error", rel, f"{where} missing `rel`"))
                elif relv not in CORE_RELS and relv not in EXT_RELS:
                    findings.append(Finding("warning", rel, f"{where} uses non-core rel `{relv}` (allowed; treated as relates-to)"))
                if relv and federation is not None and federation.get("vocab_rels") is not None \
                        and str(relv) not in federation["vocab_rels"]:
                    findings.append(Finding("warning", rel, f"{where} rel `{relv}` is not in the federation vocabulary (tolerated — SPEC §5.1)"))
                # contradiction lifecycle (SPEC §6.5)
                state = link.get("state")
                res = link.get("resolved")
                if state is not None:
                    if str(state) not in LINK_STATES:
                        findings.append(Finding("error", rel, f"{where} `state: {state}` must be `open` or `resolved`"))
                    elif relv != "contradicts":
                        findings.append(Finding("warning", rel, f"{where} `state` is only meaningful on `contradicts` (ignored on `{relv}`)"))
                    elif str(state) == "resolved" and res is None:
                        findings.append(Finding("warning", rel, f"{where} is `resolved` with no `resolved` map — who ruled, and when?"))
                ev = link.get("verified")
                if ev is not None and not all(isinstance(x, dict) and x.get("by") for x in as_list(ev)):
                    findings.append(Finding("error", rel, f"{where} `verified` must be a list of maps with `by` (§6.1)"))
                if res is not None:
                    if not isinstance(res, dict) or not res.get("by"):
                        findings.append(Finding("error", rel, f"{where} `resolved` must be a mapping with `by`"))
                    elif res.get("outcome") is not None and str(res["outcome"]) not in OUTCOMES:
                        findings.append(Finding("warning", rel, f"{where} `resolved.outcome: {res['outcome']}` is not superseded | reconciled | both-stand"))
                if not to:
                    findings.append(Finding("error", rel, f"{where} missing `to`"))
                    continue
                to = str(to)
                if federation is None:
                    # resolve: id, or a path resolving to a known file
                    resolved = to in ids
                    if not resolved:     # a path: concept-relative, or bundle-relative (§6.1)
                        resolved = (p.parent / to).exists() or (bundle / to).exists()
                    # federation-qualified reference (SPEC §9.2): namespace/id,
                    # not resolvable as a same-bundle path — tolerated, no mirror rule
                    if not resolved and QUALIFIED_RE.match(to) and to not in ids:
                        continue
                    via = None if resolved else alias_to_id.get(to)
                    if via:
                        findings.append(Finding("warning", rel, f"{where} `to: {to}` resolves only as an alias of `{via}` (§6.6) — link to `{via}`"))
                    elif not resolved:
                        findings.append(Finding("warning", rel, f"{where} `to: {to}` does not resolve (tolerated: not in this bundle, by id, path or alias)"))
                    # body-link mirroring (same-bundle targets only)
                    mirrored = to in btargets or Path(to).stem in btargets or path_id(p, to) in btargets \
                        or (via is not None and via in btargets)
                    if not mirrored:
                        findings.append(Finding("error", rel, f"{where} `to: {to}` not mirrored by a body markdown link (OKF-compat rule)"))
                    continue

                # --federation: qualified (`namespace/id` or the explicit
                # `ai-xf://namespace/id`, SPEC §9.2 + NEW) references resolve
                # against the federation-wide index. An unqualified reference
                # is tried against this bundle first (below); if it fails
                # there it falls back to the Foam rule — other bundles in
                # alphabetical order of namespace — always with a warning
                # naming every candidate and the one chosen.
                qp = qualified_parts(to)
                if qp is not None:
                    ns_part, id_part, _explicit = qp
                    if own_ns and ns_part == own_ns:
                        findings.append(Finding("error", rel, f"{where} `to: {to}` MUST NOT qualify same-bundle references (SPEC §9.2)"))
                    elif id_part in federation["index"].get(ns_part, {}):
                        federation["_stats"]["qualified_resolved"] += 1
                        # resolved cross-bundle — mirroring is SHOULD not MUST (§6.4), not checked
                    elif id_part in federation.get("aliases", {}).get(ns_part, {}):
                        federation["_stats"]["qualified_resolved"] += 1
                        via = federation["aliases"][ns_part][id_part]
                        findings.append(Finding("warning", rel, f"{where} `to: {to}` resolves only as an alias of `{ns_part}/{via}` (§6.6) — link to `{ns_part}/{via}`"))
                    else:
                        federation["_stats"]["qualified_unresolved"] += 1
                        findings.append(Finding("warning", rel, f"{where} `to: {to}` qualified reference does not resolve in the federation"))
                    continue

                resolved = to in ids
                if not resolved:         # a path: concept-relative, or bundle-relative (§6.1)
                    resolved = (p.parent / to).exists() or (bundle / to).exists()
                via = None if resolved else alias_to_id.get(to)
                if via:
                    findings.append(Finding("warning", rel, f"{where} `to: {to}` resolves only as an alias of `{via}` (§6.6) — link to `{via}`"))
                    if not (to in btargets or via in btargets):
                        findings.append(Finding("error", rel, f"{where} `to: {to}` not mirrored by a body markdown link (OKF-compat rule)"))
                    continue
                if resolved:
                    # genuinely same-bundle — the MUST-mirror rule applies (§6.4)
                    mirrored = to in btargets or Path(to).stem in btargets or path_id(p, to) in btargets
                    if not mirrored:
                        findings.append(Finding("error", rel, f"{where} `to: {to}` not mirrored by a body markdown link (OKF-compat rule)"))
                    continue

                other_ns = sorted(ns for ns in federation["index"] if ns != own_ns)
                candidates = [ns for ns in other_ns if to in federation["index"][ns]]
                if candidates:
                    federation["_stats"]["foam_resolutions"] += 1
                    chosen = candidates[0]
                    findings.append(Finding("warning", rel,
                        f"{where} `to: {to}` is unqualified; resolves in federation bundle(s) "
                        f"[{', '.join(candidates)}] — resolved to `{chosen}/{to}` (own bundle first, "
                        "then alphabetically); the producer should qualify the reference"))
                    continue

                findings.append(Finding("warning", rel, f"{where} `to: {to}` does not resolve (tolerated: not in any held bundle, by id, path or alias)"))
                mirrored = to in btargets or Path(to).stem in btargets or path_id(p, to) in btargets
                if not mirrored:
                    findings.append(Finding("error", rel, f"{where} `to: {to}` not mirrored by a body markdown link (OKF-compat rule)"))

    # Level 3 checks
    if target_level >= 3:
        manifest = bundle / MANIFEST_NAME
        if not manifest.exists():
            for old in LEGACY_MANIFEST_NAMES:
                if (bundle / old).exists():
                    manifest = bundle / old
                    break
        man = {}
        if manifest.exists():
            try:
                man = load_yaml(manifest.read_text(encoding="utf-8")) or {}
            except Exception:  # noqa: BLE001
                man = {}
        ns = man.get("namespace")
        if not ns:
            findings.append(Finding("error", MANIFEST_NAME, "missing `namespace` (required at Level 3)"))
        elif not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(ns)):
            findings.append(Finding("error", MANIFEST_NAME, f"`namespace: {ns}` must be lowercase kebab-case"))
        vocab = man.get("vocabularies")
        fed_vocab = isinstance(federation, dict) and federation.get("vocab_types") is not None and federation.get("vocab_rels") is not None
        if (not isinstance(vocab, dict) or not vocab.get("types") or not vocab.get("rels")) and not fed_vocab:
            findings.append(Finding("error", MANIFEST_NAME, "missing `vocabularies` with `types` and `rels` (required at Level 3; a federation-level declaration also satisfies this, §9.5)"))
        for rel, (fm, _body, _p) in parsed.items():
            for idx, link in enumerate(fm.get("links") or []):
                if not isinstance(link, dict):
                    continue
                to = str(link.get("to") or "")
                if "/" in to and not to.endswith(".md") and not to.startswith(".") \
                        and qualified_parts(to) is None:
                    findings.append(Finding("error", rel, f"links[{idx}] `to: {to}` is not a well-formed qualified reference (`namespace/id`)"))

    errors = [f for f in findings if f.level == "error"]
    return findings, concepts, errors


def run(bundle: Path, level: int, federation: dict | None = None, fed_findings: list[Finding] | None = None):
    highest = -1
    per_level = {}
    fed_findings = fed_findings or []
    for lv in range(0, level + 1):
        findings, concepts, _errors = validate(bundle, lv, federation)
        findings = fed_findings + findings
        errors = [f for f in findings if f.level == "error"]
        per_level[lv] = (findings, errors)
        if not errors:
            highest = lv
    return per_level, highest, concepts_count(bundle)


def concepts_count(bundle: Path) -> int:
    return len([p for p in bundle.rglob("*.md") if p.name not in RESERVED_MD])


def main():
    ap = argparse.ArgumentParser(description="Validate an AI-XF v0.3 bundle.")
    ap.add_argument("bundle", type=Path, help="path to the bundle directory")
    ap.add_argument("--level", type=int, default=2, choices=[0, 1, 2, 3],
                    help="highest conformance level to check (default 2)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--stats", action="store_true",
                    help="also report curation health (never affects pass/fail)")
    ap.add_argument("--today", type=str, default=None,
                    help="YYYY-MM-DD to evaluate `stale_after` against (default: today, UTC)")
    ap.add_argument("--federation", type=Path, default=None,
                    help="path to a federation.ai-xf.yaml manifest; resolves namespace/id and "
                         "ai-xf://namespace/id references against its federation-wide index")
    args = ap.parse_args()

    bundle = args.bundle
    if not bundle.is_dir():
        print(f"error: {bundle} is not a directory", file=sys.stderr)
        sys.exit(2)

    federation = None
    fed_findings: list[Finding] = []
    bundle_reports: list[dict] = []
    if args.federation is not None:
        if not args.federation.is_file():
            print(f"error: {args.federation} is not a file", file=sys.stderr)
            sys.exit(2)
        federation, fed_findings, bundle_reports = load_federation(args.federation)

    per_level, highest, n = run(bundle, args.level, federation, fed_findings)
    findings, errors = per_level[args.level]
    stats = None
    if args.stats:
        now = to_instant(args.today) if args.today else datetime.now(timezone.utc)
        stats = collect_stats(bundle, now)
        if federation is not None:
            stats["federation"] = federation_stats(federation, bundle_reports, bundle)

    if args.json:
        out = {
            **({"stats": stats} if stats is not None else {}),
            "bundle": str(bundle),
            "concepts": n,
            "checked_level": args.level,
            "achieved_level": highest,
            "passed": len(errors) == 0,
            "findings": [f.as_dict() for f in findings],
        }
        if federation is not None:
            out["federation"] = {"bundles": bundle_reports, "namespaces": federation["namespaces"]}
        print(json.dumps(out, indent=2))
        sys.exit(0 if len(errors) == 0 else 1)

    print(f"AI-XF validator — bundle: {bundle}")
    print(f"  concepts: {n}")
    label = {0: "OKF-compatible", 1: "AI-XF Core", 2: "AI-XF Full", 3: "AI-XF Federated", -1: "none"}
    print(f"  highest level achieved: {highest} ({label.get(highest, '?')})")
    print(f"  checked at level: {args.level}")
    if federation is not None:
        print(f"  federation: {len(federation['namespaces'])} bundle(s) held ({', '.join(federation['namespaces']) or 'none'})")
        for b in bundle_reports:
            ref_part = f" @ {b['ref']}" if b.get("ref") else ""
            git_note = {"git": " (git fetch out of scope — resolved as a local path)",
                        "oci": " (OCI pull out of scope)"}.get(b.get("source"), "")
            print(f"    - {b['namespace']}: {b['root']}{ref_part}{git_note}")
    if not findings:
        print("  ✓ no findings")
    for f in findings:
        mark = "✗" if f.level == "error" else "!"
        print(f"  {mark} [{f.level}] {f.path}: {f.msg}")
    if stats is not None:
        print_stats(stats)
    ok = len(errors) == 0
    print(f"\n{'PASS' if ok else 'FAIL'} at level {args.level} "
          f"({len(errors)} error(s), {len(findings) - len(errors)} warning(s))")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
