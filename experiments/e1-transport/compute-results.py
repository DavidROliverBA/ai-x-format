#!/usr/bin/env python3
"""experiments/e1-transport/compute-results.py

Reads the JSON/log artefacts run.sh produced under $E1_WORK/results/ and
$E1_WORK/remotes.json, computes the four E1 measures (see
docs/plans/2026-09-26-federation-experiments-plan.md, E1), and writes
$E1_WORK/e1-results.md (also printed to stdout).

Not meant to be run standalone — run.sh calls this after building all three
consumers and running the validator against each. Takes two positional args:
  1. E1_WORK directory
  2. "1" if ai-x-validate.py's --federation flag was available this run, "0"
     if not (in which case M1 is reported as "validator flag pending" and
     everything else still runs).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

WORK = Path(sys.argv[1])
FED_AVAILABLE = sys.argv[2] == "1"

CONSUMERS = ["consumer-a", "consumer-b", "consumer-c"]
LABELS = {
    "consumer-a": "(a) git submodules, generated federation.ai-x.yaml",
    "consumer-b": "(b) git subtree, naive discovery (discovered.yaml)",
    "consumer-c": "(c) git subtree + hand-written federation.ai-x.yaml",
}


def load_json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def sh(*args) -> str:
    return subprocess.check_output(list(args), text=True).strip()


# --- M1: qualified references resolved / total, from data-eng validation ---
m1 = {}
for name in CONSUMERS:
    data = load_json(WORK / "results" / f"{name}-data-eng.json")
    if not FED_AVAILABLE:
        m1[name] = "validator flag pending"
        continue
    if data is None:
        m1[name] = "ERROR (see results/*.json)"
        continue
    fed_stats = (data.get("stats") or {}).get("federation")
    if fed_stats is not None:
        qr = fed_stats["qualified_refs"]
        resolved, unresolved = qr["resolved"], qr["unresolved"]
        total = resolved + unresolved
        pct = f"{resolved}/{total}" if total else "0/0"
        m1[name] = f"{pct} ({100*resolved//total if total else 0}%)"
    else:
        # fall back to counting warnings mentioning non-resolution
        n = sum(1 for f in data.get("findings", [])
                if "does not resolve" in f.get("msg", ""))
        m1[name] = f"no federation stats block — {n} unresolved-reference warning(s)"

# --- M2: rename survival, from the payments-bundle before/after/restored runs ---
m2 = {}
for name in CONSUMERS:
    before = load_json(WORK / "results" / f"{name}-payments-before-rename.json")
    after = load_json(WORK / "results" / f"{name}-payments-after-rename.json")
    restored = load_json(WORK / "results" / f"{name}-payments-restored.json")

    def orders_events_broken(doc):
        if doc is None:
            return None
        for f in doc.get("findings", []):
            msg = f.get("msg", "")
            if "orders-events" in msg and "does not resolve" in msg:
                return True
        return False

    b, a, r = (orders_events_broken(x) for x in (before, after, restored))
    if a is None:
        m2[name] = "ERROR (see results/*.json)"
    elif a is False and b is False:
        note = "" if r is False else " (restore mismatch — check manually)"
        m2[name] = f"yes — still resolves after rename{note}"
    elif a is True:
        m2[name] = "no — broke after rename"
    else:
        m2[name] = f"inconclusive (before={b}, after={a}, restored={r})"

# --- M3: provenance — can the consumer name the exact commit of each bundle? ---
remotes = json.loads((WORK / "remotes.json").read_text(encoding="utf-8"))

m3 = {}

# (a) submodule SHAs vs remotes.json
sub_status = (WORK / "results" / "consumer-a-submodule-status.txt").read_text(encoding="utf-8")
sub_shas = {}
for line in sub_status.splitlines():
    line = line.strip()
    if not line:
        continue
    body = line[1:] if line[0] in "+-U" else line
    parts = body.split()
    sha, path = parts[0], parts[1]
    sub_shas[Path(path).name] = sha
a_matches = all(sub_shas.get(n) == remotes[n]["head"] for n in ("data-eng", "household", "payments"))
m3["consumer-a"] = (
    f"yes — submodule SHAs match remotes.json ({', '.join(sub_shas.values())})"
    if a_matches else f"MISMATCH — {sub_shas} vs {remotes}"
)

# (b) discovered.yaml — every ref should be null
discovered_text = (WORK / "consumer-b" / "discovered.yaml").read_text(encoding="utf-8")
b_all_null = discovered_text.count("ref: null") == 3
m3["consumer-b"] = (
    "no — discovered.yaml records `ref: null` for all three bundles "
    "(naive discovery never inspects git-subtree's trailers)"
    if b_all_null else "unexpected: some ref was recovered — check discovered.yaml"
)

# (c) federation.ai-x.yaml ref (git-subtree-split trailer) vs remotes.json
fed_c_text = (WORK / "consumer-c" / "federation.ai-x.yaml").read_text(encoding="utf-8")
c_shas = {}
current_ns = None
for line in fed_c_text.splitlines():
    line = line.strip().lstrip("- ")
    if line.startswith("namespace:"):
        current_ns = line.split(":", 1)[1].strip()
    elif line.startswith("ref:") and current_ns is not None:
        sha = line.split(":", 1)[1].split("#")[0].strip()
        c_shas[current_ns] = sha
ns_to_bundle = {"data-eng": "data-eng", "household": "household", "example-payments": "payments"}
c_matches = all(
    c_shas.get(ns) == remotes[bundle]["head"] for ns, bundle in ns_to_bundle.items()
)
m3["consumer-c"] = (
    f"yes — federation.ai-x.yaml `ref` (from git-subtree-split trailer) matches remotes.json"
    if c_matches else f"MISMATCH — {c_shas} vs {remotes}"
)

# --- M4: rebuild — fresh clone, diff -r bundles, byte-identical? ---
m4 = {}
for name in CONSUMERS:
    diff_file = WORK / "results" / f"{name}-diff.txt"
    diff_text = diff_file.read_text(encoding="utf-8") if diff_file.exists() else "(missing)"
    m4[name] = "byte-identical" if not diff_text.strip() else f"DIFFERS:\n{diff_text.strip()[:2000]}"

# --- Write the table ---
git_version = sh("git", "--version")
py_version = sh("python3", "--version")
today = date.today().isoformat()

lines = []
lines.append("# E1 results — transport and the root manifest")
lines.append("")
lines.append(f"Run on {today}. `{git_version}`, `{py_version}`.")
lines.append("")
lines.append("Bundle under test for M1/M3/M4: `bundles/data-eng` (or `bundles/payments`")
lines.append("for M2 — see note below). Namespaces: `data-eng`, `household`,")
lines.append("`example-payments`.")
lines.append("")
if not FED_AVAILABLE:
    lines.append("> **`ai-x-validate.py --federation` was not available for this run.** "
                 "All three consumer layouts were still built; M1 is marked "
                 "\"validator flag pending\" below. Re-run `run.sh` once the flag lands.")
    lines.append("")

lines.append("| Measure | (a) submodules | (b) subtree, naive discovery | (c) subtree + hand-written manifest |")
lines.append("|---|---|---|---|")
lines.append(f"| **M1** qualified refs resolved | {m1['consumer-a']} | {m1['consumer-b']} | {m1['consumer-c']} |")
lines.append(f"| **M2** rename survival | {m2['consumer-a']} | {m2['consumer-b']} | {m2['consumer-c']} |")
lines.append(f"| **M3** provenance (exact commit nameable) | {m3['consumer-a']} | {m3['consumer-b']} | {m3['consumer-c']} |")
lines.append(f"| **M4** rebuild byte-identical | {m4['consumer-a']} | {m4['consumer-b']} | {m4['consumer-c']} |")
lines.append("")
lines.append("Notes:")
lines.append("")
lines.append("- **M2** validates `bundles/payments`, not `bundles/data-eng` — the qualified")
lines.append("  reference under test (`payment-service-v2` → `data-eng/orders-events`) is")
lines.append("  declared on the payments side, in `examples/concepts/payment-service-v2.md`.")
lines.append("- **M3(b)** is read directly off `discovered.yaml`'s `ref: null` fields — a naive")
lines.append("  scan for `manifest.ai-x.yaml` files never inspects git history, so it cannot")
lines.append("  recover the pre-squash commit that `git subtree add --squash` swallows.")
lines.append("- **M3(c)**'s `ref` comes from the squash commit's `git-subtree-split:` trailer")
lines.append("  (git plumbing, not an AI-X concept) — recoverable, but only by a script or")
lines.append("  human that knows to look for it.")
lines.append("- **M4** diffs `bundles/` only (as specified); consumer-a's diff additionally")
lines.append("  covers each submodule's `.git` gitlink file, which is expected to match since")
lines.append("  both checkouts sit at the same relative depth.")
lines.append("")

out = "\n".join(lines) + "\n"
(WORK / "e1-results.md").write_text(out, encoding="utf-8")
print(out)
