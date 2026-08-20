#!/usr/bin/env python3
"""AIX v0.2 reference validator.

Validates an AIX bundle against the conformance ladder defined in ../SPEC.md:

  Level 0  OKF-compatible  — every non-reserved .md has parseable frontmatter
                             with a non-empty `type`.
  Level 1  AIX Core        — Level 0 + unique `id` per concept + manifest.aix.yaml
                             declaring `aix` and `name`.
  Level 2  AIX Full        — Level 1 + every `links` entry is a valid link object
                             (rel + resolvable `to`), same-bundle links mirrored
                             by a body link, + trust signals on every concept
                             (a `provenance` map or an OKF v0.2 trust field),
                             + every `media` entry carries a `uri`.
  Level 3  AIX Federated   — Level 2 + manifest declares a valid `namespace`
                             and `vocabularies`; qualified references are
                             well-formed `namespace/id`.

Usage:
    python3 aix-validate.py <bundle-dir> [--level N] [--json]

Self-contained: uses PyYAML if present, otherwise a minimal built-in parser
covering the subset of YAML that AIX frontmatter uses. Derives nothing from a
hardcoded path.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RESERVED_MD = {"index.md", "log.md"}
MANIFEST_NAME = "manifest.aix.yaml"

CORE_RELS = {
    "relates-to", "part-of", "has-part", "depends-on", "depended-on-by",
    "references", "referenced-by", "derived-from", "source-of",
    "supersedes", "superseded-by", "contradicts", "authored-by",
    "author-of", "describes", "described-by",
}

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
    return s


def _mini_yaml(text: str):
    """Minimal parser: top-level scalars/lists/maps, one level of nesting,
    and lists-of-maps (as used by AIX `links`). Not a general YAML parser."""
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
        # block value: gather deeper-indented lines
        block = []
        j = i + 1
        while j < n and (not lines[j].strip() or indent(lines[j]) > 0):
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
        for ln in items:
            ind = len(ln) - len(ln.lstrip(" "))
            body = ln.lstrip()
            if ind == base and body.startswith("-"):
                if cur is not None:
                    result.append(cur)
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
                cur[k.strip()] = _coerce(v)
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


def body_link_targets(body: str, concept_dir: Path, bundle: Path):
    """Return the set of normalised targets (id-or-relpath) linked in the body."""
    targets = set()
    for raw in MD_LINK_RE.findall(body):
        tgt = raw.split("#")[0].strip()
        if not tgt or tgt.startswith(("http://", "https://", "mailto:")):
            continue
        targets.add(tgt)
        # also record the resolved id (filename stem) for id-based matching
        stem = Path(tgt).stem
        targets.add(stem)
    return targets


def validate(bundle: Path, target_level: int):
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
            findings.append(Finding("error", rel, "no YAML frontmatter (OKF/AIX require it)"))
            continue
        if fm == "PARSE_ERROR":
            findings.append(Finding("error", rel, f"frontmatter parse error: {err}"))
            continue
        typ = fm.get("type")
        if not typ or not str(typ).strip():
            findings.append(Finding("error", rel, "missing or empty required field `type`"))
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

    # Level 1 checks
    if target_level >= 1:
        manifest = bundle / MANIFEST_NAME
        if not manifest.exists():
            findings.append(Finding("error", MANIFEST_NAME, "missing manifest.aix.yaml (required at Level 1)"))
        else:
            try:
                man = load_yaml(manifest.read_text(encoding="utf-8")) or {}
                for k in ("aix", "name"):
                    if not man.get(k):
                        findings.append(Finding("error", MANIFEST_NAME, f"manifest missing `{k}`"))
            except Exception as e:  # noqa: BLE001
                findings.append(Finding("error", MANIFEST_NAME, f"manifest parse error: {e}"))
        for rel, (fm, _body, _p) in parsed.items():
            if not fm.get("id"):
                findings.append(Finding("error", rel, "missing `id` (required at Level 1)"))

    # Level 2 checks
    if target_level >= 2:
        for rel, (fm, body, p) in parsed.items():
            # trust signals: AIX provenance map OR any OKF v0.2 trust field
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
            btargets = body_link_targets(body, p.parent, bundle)
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
                if not to:
                    findings.append(Finding("error", rel, f"{where} missing `to`"))
                    continue
                to = str(to)
                # resolve: id, or a path resolving to a known file
                resolved = to in ids
                if not resolved:
                    cand = (p.parent / to).resolve()
                    resolved = cand.exists()
                # federation-qualified reference (SPEC §9.2): namespace/id,
                # not resolvable as a same-bundle path — tolerated, no mirror rule
                if not resolved and QUALIFIED_RE.match(to) and to not in ids:
                    continue
                if not resolved:
                    findings.append(Finding("warning", rel, f"{where} `to: {to}` does not resolve (tolerated — may be not-yet-written)"))
                # body-link mirroring (same-bundle targets only)
                mirrored = to in btargets or Path(to).stem in btargets
                if not mirrored:
                    findings.append(Finding("error", rel, f"{where} `to: {to}` not mirrored by a body markdown link (OKF-compat rule)"))

    # Level 3 checks
    if target_level >= 3:
        manifest = bundle / MANIFEST_NAME
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
        if not isinstance(vocab, dict) or not vocab.get("types") or not vocab.get("rels"):
            findings.append(Finding("error", MANIFEST_NAME, "missing `vocabularies` with `types` and `rels` (required at Level 3)"))
        for rel, (fm, _body, _p) in parsed.items():
            for idx, link in enumerate(fm.get("links") or []):
                if not isinstance(link, dict):
                    continue
                to = str(link.get("to") or "")
                if "/" in to and not to.endswith(".md") and not to.startswith(".") \
                        and not QUALIFIED_RE.match(to):
                    findings.append(Finding("error", rel, f"links[{idx}] `to: {to}` is not a well-formed qualified reference (`namespace/id`)"))

    errors = [f for f in findings if f.level == "error"]
    return findings, concepts, errors


def run(bundle: Path, level: int):
    highest = -1
    per_level = {}
    for lv in range(0, level + 1):
        findings, concepts, errors = validate(bundle, lv)
        per_level[lv] = (findings, errors)
        if not errors:
            highest = lv
    return per_level, highest, concepts_count(bundle)


def concepts_count(bundle: Path) -> int:
    return len([p for p in bundle.rglob("*.md") if p.name not in RESERVED_MD])


def main():
    ap = argparse.ArgumentParser(description="Validate an AIX v0.2 bundle.")
    ap.add_argument("bundle", type=Path, help="path to the bundle directory")
    ap.add_argument("--level", type=int, default=2, choices=[0, 1, 2, 3],
                    help="highest conformance level to check (default 2)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    bundle = args.bundle
    if not bundle.is_dir():
        print(f"error: {bundle} is not a directory", file=sys.stderr)
        sys.exit(2)

    per_level, highest, n = run(bundle, args.level)
    findings, errors = per_level[args.level]

    if args.json:
        print(json.dumps({
            "bundle": str(bundle),
            "concepts": n,
            "checked_level": args.level,
            "achieved_level": highest,
            "passed": len(errors) == 0,
            "findings": [f.as_dict() for f in findings],
        }, indent=2))
        sys.exit(0 if len(errors) == 0 else 1)

    print(f"AIX validator — bundle: {bundle}")
    print(f"  concepts: {n}")
    label = {0: "OKF-compatible", 1: "AIX Core", 2: "AIX Full", 3: "AIX Federated", -1: "none"}
    print(f"  highest level achieved: {highest} ({label.get(highest, '?')})")
    print(f"  checked at level: {args.level}")
    if not findings:
        print("  ✓ no findings")
    for f in findings:
        mark = "✗" if f.level == "error" else "!"
        print(f"  {mark} [{f.level}] {f.path}: {f.msg}")
    ok = len(errors) == 0
    print(f"\n{'PASS' if ok else 'FAIL'} at level {args.level} "
          f"({len(errors)} error(s), {len(findings) - len(errors)} warning(s))")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
