#!/usr/bin/env python3
"""E11 measurement: every probe in corpus/ground-truth.json, looked up in each
of the four bundles, and classified:

  kept       present with its meaning (a heading as a heading, a link that
             resolves to the migrated concept, code in a code block, ...)
  degraded   the text survived but its structure or meaning did not (a page
             link as plain words, a panel as an ordinary paragraph, a tracked
             deletion silently applied, an image reduced to a placeholder)
  withheld   deliberately not exported (a restricted page), and the bundle
             says so where the gap is visible
  leaked     restricted content that reached the bundle
  lost       gone

Then the reference validator at level 3 (and its --stats) on each bundle.

Usage: python3 measure.py <corpus-dir> <out-dir> <validator> <results.json>
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

CORPUS, OUT, VALIDATOR, RESULTS = (Path(a) for a in sys.argv[1:5])
truth = json.loads((CORPUS / "ground-truth.json").read_text())
restricted_titles = {json.loads(f.read_text())["title"] for f in (CORPUS / "confluence").glob("*.json")
                     if f.name != "users.json" and json.loads(f.read_text()).get("restrictions")}


def unescape(t: str) -> str:
    return re.sub(r"\\([\\_*\[\]()#.!|-])", r"\1", t)


def lines_with(text: str, needle: str) -> list[str]:
    return [l for l in text.split("\n") if needle in l]


def classify(p: dict, bundle: str, files: dict, log: str, root: Path) -> str:
    title, kind, pr = p["doc"], p["kind"], unescape(p["probe"])
    mapped = bundle.startswith("mapped")
    restricted = p["source"] == "confluence" and title in restricted_titles   # only Confluence has restrictions
    if title not in files:
        return "withheld" if mapped and restricted else "lost"
    text = unescape((root / files[title]).read_text())
    leak = (not mapped) and restricted
    if kind == "macro-toc":
        return "kept"                                       # regenerable from headings either way
    if kind in ("heading",):
        hit = [l for l in lines_with(text, pr) if l.lstrip().startswith("#")]
        out = "kept" if hit else ("degraded" if pr in text else "lost")
    elif kind == "list-item":
        hit = [l for l in lines_with(text, pr) if re.match(r"\s*(\d+\.|[-*])\s", l)]
        out = "kept" if hit else ("degraded" if pr in text else "lost")
    elif kind == "table":
        out = "kept" if any(l.lstrip().startswith("|") for l in lines_with(text, pr)) else (
            "degraded" if pr in text else "lost")
    elif kind == "link-internal":
        target = p.get("target")
        tfile = files.get(target)
        if tfile:
            rel = Path(tfile).name
            out = "kept" if re.search(rf"\]\([^)]*{re.escape(rel)}\)", text) else (
                "degraded" if (pr in text or (p.get("anchor") or "") in text) else "lost")
        elif p["source"] == "confluence" and target in restricted_titles and mapped:
            out = "withheld" if "withheld from this export" in text else "lost"
        else:
            out = "degraded" if pr in text else "lost"
    elif kind == "link-external":
        out = "kept" if f"]({pr})" in text else ("degraded" if pr in text else "lost")
    elif kind == "image":
        assets = list((root / "assets").glob("*")) if (root / "assets").exists() else []
        out = "kept" if (assets and "media:" in text and "sha256:" in text) else (
            "degraded" if "![" in text else "lost")
    elif kind == "comment":
        out = "kept" if pr in text else "lost"
    elif kind == "tracked-insert":
        out = ("kept" if "Pending tracked changes" in text else "degraded") if pr in text else "lost"
    elif kind == "tracked-delete":
        out = "kept" if pr in text else "degraded"          # dropped silently = shown as accepted
    elif kind in ("macro-info", "macro-warning", "macro-note"):
        hit = [l for l in lines_with(text, pr) if l.lstrip().startswith(">")]
        out = "kept" if hit else ("degraded" if pr in text else "lost")
    elif kind == "macro-code":
        fenced = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
        out = "kept" if any(pr in f for f in fenced) else ("degraded" if pr.replace(" ", "") in text.replace(" ", "")
                                                            else "lost")
    elif kind == "macro-jira":
        out = "kept" if re.search(rf"\[{re.escape(pr)}\]\(https?://", text) else ("degraded" if pr in text else "lost")
    elif kind in ("macro-expand", "text", "macro-details"):
        out = "kept" if pr in text else "lost"
    elif kind == "mention":
        out = "kept" if re.search(rf"\[{re.escape(pr)}\]\(", text) else ("degraded" if pr in text else "lost")
    elif kind == "attachment":
        out = "kept" if (pr in text and "media:" in text) else ("degraded" if pr in text else "lost")
    elif kind == "version":
        cid = Path(files[title]).stem
        out = "kept" if any(pr in l and f"`{cid}`" in l for l in log.split("\n")) else "lost"
    elif kind == "metadata":
        v = pr
        if p["field"] in ("created", "modified", "last-modified"):
            out = "kept" if (v in text or v[:16] in text or (v[:10] in log and Path(files[title]).stem in log)) else "lost"
        elif p["field"] in ("approval", "content-status"):
            out = "kept" if (v in text or ("verified:" in text and v in ("Approved", "verified"))
                             or ("status: draft" in text and v in ("Pending", "Draft", "rough draft"))) else "lost"
        elif p["field"] in ("label", "managed-metadata", "keywords"):
            terms = [t.strip().lower().replace(" ", "-") for t in v.split(";")]
            out = "kept" if all(re.search(rf"^\s*-\s+'?{re.escape(t)}'?$", text, re.M) for t in terms) else "lost"
        elif p["field"] == "ancestor":
            out = "kept" if "rel: part-of" in text else ("degraded" if v in text else "lost")
        elif p["field"] in ("author", "last-modified-by", "created-by"):
            out = "kept" if ("human:" + re.sub(r"[^a-z0-9]+", "-", v.lower())) in text or f"[{v}](" in text \
                or (v in log and Path(files[title]).stem in log) else ("degraded" if v in text else "lost")
        elif p["field"] == "restriction":
            out = "lost"
        else:
            out = "kept" if v in text or v.lower() in text.lower() else "lost"
    else:
        out = "kept" if pr in text else "lost"
    if leak and out in ("kept", "degraded"):
        return "leaked"
    return out


def validate(root: Path) -> dict:
    r = subprocess.run([sys.executable, str(VALIDATOR), str(root), "--level", "3", "--json", "--stats",
                        "--today", "2026-10-03"], capture_output=True, text=True)
    d = json.loads(r.stdout)
    errs = [f for f in d["findings"] if f["severity"] == "error"]
    warns = [f for f in d["findings"] if f["severity"] == "warning"]
    st = d.get("stats", {})
    return {"achieved_level": d["achieved_level"], "errors": len(errs), "warnings": len(warns),
            "error_kinds": dict(Counter(re.sub(r"`[^`]*`", "`…`", f["message"])[:70] for f in errs)),
            "warning_kinds": dict(Counter(re.sub(r"`[^`]*`", "`…`", f["message"])[:70] for f in warns)),
            "trust_tiers": st.get("trust_tiers"), "status": st.get("status"),
            "past_stale_after": (st.get("staleness") or {}).get("past_stale_after"),
            "freshness": st.get("freshness"), "log": (st.get("log") or {}).get("entries")}


def main() -> None:
    results: dict = {"bundles": {}, "by_kind": {}, "losses": defaultdict(list)}
    for bundle in ("naive-word", "mapped-word", "naive-confluence", "mapped-confluence"):
        src = bundle.split("-")[1]
        root = OUT / bundle
        files = json.loads((OUT / f"{bundle}.map.json").read_text())
        log = (root / "log.md").read_text() if (root / "log.md").exists() else ""
        per_kind: dict[str, Counter] = defaultdict(Counter)
        for p in truth:
            if p["source"] != src:
                continue
            kind = p["kind"] if p["kind"] != "metadata" else f"metadata:{p['field']}"
            c = classify(p, bundle, files, log, root)
            per_kind[kind][c] += 1
            if c in ("lost", "degraded", "leaked"):
                results["losses"][bundle].append(f"{c}: {p['doc']} / {kind}: {p['probe'][:60]}")
        total = Counter()
        for k in per_kind.values():
            total.update(k)
        results["by_kind"][bundle] = {k: dict(v) for k, v in sorted(per_kind.items())}
        results["bundles"][bundle] = {"probes": dict(total), "validator": validate(root)}
    results["losses"] = dict(results["losses"])
    stats = OUT / "mapped-confluence.stats.json"
    if stats.exists():
        results["bundles"]["mapped-confluence"]["withholding"] = json.loads(stats.read_text())
    RESULTS.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    for b, r in results["bundles"].items():
        v = r["validator"]
        print(f"{b:18} probes {r['probes']} | level {v['achieved_level']}, {v['errors']} errors, {v['warnings']} warnings")


if __name__ == "__main__":
    main()
