#!/usr/bin/env python3
"""E8: freshness and drift. Does an AI-XF bundle reconcile, or accumulate?

Replays the add / edit / rename / delete lifecycle from Isci, "How to Keep
Knowledge Graphs Fresh" (Medium, Aug 2026) against a real producer
(MyVault's `ai-xf-export.py`) and a real corpus (copies of the vault's
Psychology/Concepts notes), then asks what a consumer holding only the bundle
can detect. Nothing in the vault or in the published kb repos is touched:
every phase runs on copies under a scratch directory.

  Instance layer (ABox): per phase, ground-truth ghosts (concept files whose
  source note is gone) against what bundle-only detectors catch.
  Schema layer (TBox): federation vocabulary declared vs used, before and
  after the last instance of a type is removed.

Usage: python3 run.py [scratch-dir] [--exporter PATH] [--out results.json]
       (needs `uv` for the exporter's PyYAML; --exporter runs another version,
        e.g. the pre-fix one from vault git history)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
VALIDATOR = REPO / "tools" / "ai-xf-validate.py"
VAULT = Path.home() / "Documents" / "MyVault"
EXPORTER = Path(sys.argv[sys.argv.index("--exporter") + 1]) if "--exporter" in sys.argv \
    else VAULT / ".claude" / "scripts" / "ai-xf-export.py"
OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "results.json"
SOURCE_NOTES = VAULT / "Psychology" / "Concepts"
AI_CONCEPTS_KB = Path.home() / "Documents" / "GitHub" / "ai-concepts-kb"
FIXTURES = REPO / "experiments" / "fixtures"

FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
ID_RE = re.compile(r"^id:\s*(\S+)", re.MULTILINE)
TYPE_RE = re.compile(r"^type:\s*(\S+)", re.MULTILINE)
REL_RE = re.compile(r"^\s*-?\s*rel:\s*(\S+)", re.MULTILINE)
TO_RE = re.compile(r"^\s*to:\s*(\S+)", re.MULTILINE)
INDEX_LINK_RE = re.compile(r"\]\(\./concepts/([^)]+)\.md\)")
NOT_RESOLVE_RE = re.compile(r"`to: ([^`]+)` (?:qualified reference )?does not resolve")


def slugify(name: str) -> str:
    """The exporter's id rule: de-prefixed filename, kebab-cased."""
    name = re.sub(r"^[A-Za-z]+ - ", "", name)
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def frontmatter(p: Path) -> str:
    m = FM_RE.match(p.read_text(encoding="utf-8"))
    return m.group(1) if m else ""


def concept_files(bundle: Path) -> list[Path]:
    return [p for p in bundle.rglob("*.md") if p.name not in ("index.md", "log.md")]


def bundle_ids(bundle: Path) -> set[str]:
    out = set()
    for p in concept_files(bundle):
        m = ID_RE.search(frontmatter(p))
        out.add(m.group(1).strip("'\"") if m else p.stem)
    return out


def export(src: Path, out: Path, fed: Path, mode: str) -> None:
    if mode == "fresh" and out.exists():
        shutil.rmtree(out)
    r = subprocess.run(["uv", "run", "-q", "--with", "pyyaml", "python3", str(EXPORTER),
                        str(src), "--out", str(out), "--name", "psychology",
                        "--federation", str(fed)], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"exporter failed:\n{r.stdout}\n{r.stderr}")


def validate(bundle: Path, fed: Path) -> dict:
    r = subprocess.run([sys.executable, str(VALIDATOR), str(bundle), "--level", "3",
                        "--federation", str(fed), "--json"], capture_output=True, text=True)
    return json.loads(r.stdout)


def unresolved(report: dict) -> set[str]:
    return {m.group(1) for f in report["findings"]
            if (m := NOT_RESOLVE_RE.search(f["message"]))}


def measure(src: Path, psych: Path, aic: Path, fed: Path) -> dict:
    truth = {(m.group(1) if (m := re.search(r"^slug:\s*(\S+)", frontmatter(p), re.MULTILINE))
              else slugify(p.stem)) for p in src.glob("*.md")}
    on_disk = bundle_ids(psych)
    retired = deprecated_ids(psych)
    ghosts = on_disk - truth - retired
    missing = truth - on_disk
    index_ids = set(INDEX_LINK_RE.findall((psych / "index.md").read_text(encoding="utf-8")))
    manifest_count = int(re.search(r"concepts:\s*(\d+)",
                                   (psych / "manifest.ai-xf.yaml").read_text()).group(1))
    rp, ra = validate(psych, fed), validate(aic, fed)
    # Detectors that need only the bundle itself (no access to the source corpus)
    d_index = on_disk - index_ids - retired                      # D1: file not listed in index.md
    d_count = len(on_disk) != manifest_count            # D2: manifest count disagrees
    return {
        "source_notes": len(truth),
        "concept_files": len(on_disk),
        "manifest_count": manifest_count,
        "index_entries": len(index_ids),
        "ghosts_truth": sorted(ghosts),
        "not_exported": sorted(missing),
        "tombstones": sorted(retired),
        "edges_into_tombstones": links_into(psych, retired) + links_into(aic, retired, "psychology/"),
        "edges_into_ghosts": links_into(psych, ghosts) + links_into(aic, ghosts, "psychology/"),
        "D1_files_not_in_index": sorted(d_index),
        "D2_count_mismatch": d_count,
        "psychology_passed": rp["passed"],
        "psychology_unresolved": sorted(unresolved(rp)),
        "ai_concepts_unresolved_psychology": sorted(t for t in unresolved(ra) if t.startswith("psychology/")),
        "ai_concepts_unresolved_total": len(unresolved(ra)),
    }


def reconcile(bundle: Path, today: str = "2026-10-02") -> list[str]:
    """Prototype producer step (tombstone modes): any concept file the export
    did not list in index.md is retired in place as a SPEC §6.6 tombstone, and
    a `Deprecation` entry is appended to log.md (§10.2). Uses only the bundle."""
    listed = set(INDEX_LINK_RE.findall((bundle / "index.md").read_text(encoding="utf-8")))
    retired = []
    for p in concept_files(bundle):
        fm = frontmatter(p)
        cid = (m.group(1).strip("'\"") if (m := ID_RE.search(fm)) else p.stem)
        if cid in listed or re.search(r"^status:\s*deprecated", fm, re.MULTILINE):
            continue
        title = (m.group(1) if (m := re.search(r"^title:\s*(.+)$", fm, re.MULTILINE)) else cid)
        typ = (m.group(1) if (m := TYPE_RE.search(fm)) else "Concept")
        p.write_text(f"---\ntype: {typ}\nid: {cid}\ntitle: {title}\nstatus: deprecated\n---\n\n"
                     f"Retired {today}: the source note is no longer in the export.\n", encoding="utf-8")
        retired.append(cid)
    if retired:
        log = bundle / "log.md"
        old = log.read_text(encoding="utf-8") if log.exists() else "# Log\n"
        entries = "".join(f"- **Deprecation** `{c}`: source note removed from the export slice.\n" for c in retired)
        if f"## {today}\n\n" in old:
            log.write_text(old.replace(f"## {today}\n\n", f"## {today}\n\n{entries}", 1), encoding="utf-8")
        else:
            head, _, rest = old.partition("\n")
            log.write_text(f"{head}\n\n## {today}\n\n{entries}{rest.lstrip(chr(10))}", encoding="utf-8")
    return retired


def deprecated_ids(bundle: Path) -> set[str]:
    out = set()
    for p in concept_files(bundle):
        fm = frontmatter(p)
        if re.search(r"^status:\s*deprecated", fm, re.MULTILINE):
            out.add(m.group(1).strip("'\"") if (m := ID_RE.search(fm)) else p.stem)
    return out


def links_into(bundle: Path, targets: set[str], prefix: str = "") -> int:
    """Edges in `bundle` whose target is one of `targets` (optionally namespace-qualified)."""
    n = 0
    for p in concept_files(bundle):
        n += sum(1 for t in TO_RE.findall(frontmatter(p)) if t.strip("'\"") in {prefix + x for x in targets})
    return n


# ---- schema layer -------------------------------------------------------------

def vocab_usage(fed: Path) -> dict:
    """Declared federation vocabulary vs what the held bundles actually use."""
    man = fed.read_text(encoding="utf-8")
    roots = []
    for m in re.finditer(r"path:\s*(\S+)", man):
        roots.append((fed.parent / m.group(1)).resolve())
    if "subdir: examples" in man:
        roots.append(REPO / "examples")
    tpath = re.search(r"types:\s*(\S+)", man).group(1)
    rpath = re.search(r"rels:\s*(\S+)", man).group(1)
    declared_t = [v["name"] for v in json.loads((fed.parent / tpath).read_text())["values"]]
    declared_r = [v["name"] for v in json.loads((fed.parent / rpath).read_text())["values"]]
    types, rels = Counter(), Counter()
    for root in roots:
        for p in concept_files(root):
            fm = frontmatter(p)
            if (m := TYPE_RE.search(fm)):
                types[m.group(1)] += 1
            rels.update(REL_RE.findall(fm))
    inverse_only = {"has-part", "depended-on-by", "referenced-by", "source-of", "superseded-by",
                    "supported-by", "merged-from", "split-into", "exported-to", "author-of",
                    "described-by", "depicted-in", "remediated-by", "discussed-in"}
    return {
        "bundles": [str(r.relative_to(r.parents[1])) for r in roots],
        "types_declared": len(declared_t),
        "types_unused": [t for t in declared_t if not types[t]],
        "types_used": dict(types),
        "rels_declared": len(declared_r),
        "rels_unused": [r for r in declared_r if not rels[r]],
        "rels_unused_forward_only": [r for r in declared_r if not rels[r] and r not in inverse_only],
        "rels_used": dict(rels),
    }


def type_extinction(scratch: Path) -> dict:
    """Remove the federation's only Policy concept; who notices?"""
    fx = scratch / "fixtures"
    shutil.copytree(FIXTURES, fx)
    shutil.copytree(REPO / "examples", fx / "examples")
    fed = fx / "federation.ai-xf.yaml"
    fed.write_text(re.sub(r"  - namespace: example-payments\n(    .*\n)+",
                          "  - namespace: example-payments\n    source: path\n    path: ./examples\n",
                          fed.read_text()))
    before = vocab_usage(fed)
    policies = [p for b in ("data-eng", "household", "examples") for p in concept_files(fx / b)
                if (m := TYPE_RE.search(frontmatter(p))) and m.group(1) == "Policy"]
    for p in policies:
        p.unlink()
    after = vocab_usage(fed)
    rep = validate(fx / "data-eng", fed)
    return {
        "removed": [str(p.relative_to(fx)) for p in policies],
        "types_unused_before": before["types_unused"],
        "types_unused_after": after["types_unused"],
        "data_eng_passed": rep["passed"],
        "data_eng_findings": [f["message"] for f in rep["findings"]],
    }


# ---- lifecycle ----------------------------------------------------------------

ADDED = """---
type: Concept
status: active
title: "E8 Added Concept"
created: 2026-10-02
summary: "A synthetic note added by E8 to exercise the add phase."
relatedTo:
  - "[[Concept - Omission Bias]]"
---

A synthetic concept. Related: [[Concept - Omission Bias]].
"""


def lifecycle(scratch: Path, mode: str) -> list[dict]:
    work = scratch / mode
    src = work / "vault" / "Psychology" / "Concepts"
    shutil.copytree(SOURCE_NOTES, src)
    if mode == "stable":
        # Pin identity in the source: the exporter honours `slug:` (SPEC §5.2).
        for p in src.glob("*.md"):
            t = p.read_text(encoding="utf-8")
            p.write_text(t.replace("---\n", f"---\nslug: {slugify(p.stem)}\n", 1), encoding="utf-8")
    psych, aic = work / "psychology-kb", work / "ai-concepts-kb"
    shutil.copytree(AI_CONCEPTS_KB, aic, ignore=shutil.ignore_patterns(".git"))
    shutil.copytree(REPO / "experiments" / "real-federation" / "vocab", work / "vocab")
    fed = work / "federation.ai-xf.yaml"
    fed.write_text("ai-xf: \"0.4\"\nfederation: e8\nvocabularies:\n"
                   "  types: ./vocab/types-v1.json\n  rels:  ./vocab/rels-v1.json\nbundles:\n"
                   "  - namespace: psychology\n    source: path\n    path: ./psychology-kb\n"
                   "  - namespace: ai-concepts\n    source: path\n    path: ./ai-concepts-kb\n")

    def edit(name: str, old: str, new: str) -> None:
        p = src / name
        p.write_text(p.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    def p1(): pass
    def p2(): (src / "Concept - E8 Added Concept.md").write_text(
        ADDED.replace("---\n", "---\nslug: e8-added-concept\n", 1) if mode == "stable" else ADDED, encoding="utf-8")
    def p3(): edit("Concept - Omission Bias.md", '  - "[[Concept - Outcome Bias]]"\n', "")
    def p4():
        # Obsidian-style rename: file moves and every inbound wikilink is rewritten.
        (src / "Concept - PC Mindset.md").rename(src / "Concept - Proof-of-Concept Mindset.md")
        for p in src.glob("*.md"):
            t = p.read_text(encoding="utf-8")
            if "[[Concept - PC Mindset" in t:
                p.write_text(t.replace("[[Concept - PC Mindset", "[[Concept - Proof-of-Concept Mindset"), encoding="utf-8")
    def p5(): (src / "Concept - Fermi Paradox.md").unlink()   # inbound wikilinks left dangling, as Obsidian does

    phases = [("P1 baseline", p1), ("P2 add", p2), ("P3 edit (drop a link)", p3),
              ("P4 rename", p4), ("P5 delete", p5)]
    out = []
    for name, act in phases:
        act()
        export(src, psych, fed, mode)
        if mode in ("tombstone", "stable"):
            reconcile(psych)
        out.append({"phase": name, "mode": mode, **measure(src, psych, aic, fed)})
    return out


def main() -> None:
    pos = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] not in ("--exporter", "--out")]
    scratch = Path(pos[0]) if pos else Path(tempfile.mkdtemp(prefix="e8-"))
    if scratch.exists() and any(scratch.iterdir()):
        sys.exit(f"{scratch} is not empty")
    scratch.mkdir(parents=True, exist_ok=True)
    results = {
        "lifecycle": [r for m in ("inplace", "fresh", "tombstone", "stable") for r in lifecycle(scratch, m)],
        "vocab_real": vocab_usage(REPO / "experiments" / "real-federation" / "federation.ai-xf.yaml"),
        "type_extinction": type_extinction(scratch),
    }
    (HERE / OUT).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"scratch: {scratch}\nwrote {HERE / OUT}")


if __name__ == "__main__":
    main()
