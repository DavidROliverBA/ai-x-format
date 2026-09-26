#!/usr/bin/env python3
"""E3 runner: cross-bundle index (qmd collections vs plain BM25 over the union).

Builds three configurations and scores each against the 20 fixture questions:

  (a) qmd, one collection per bundle — collection names equal the namespace
      exactly (example-payments, data-eng, household), all three collections
      living in one qmd index so a query with no `-c` filter searches across
      all of them (this is how qmd's "collection" primitive works: it tags
      documents, it does not partition the index).
  (b) qmd, one collection named `all` over a directory that holds a *copy*
      of all three bundles (qmd does not follow symlinks and a collection
      root is a single path, so the union has to be materialised on disk;
      see NOTE-COPY below). Namespace is recovered from the first path
      segment under the collection root, which is the bundle name because
      that's how the copy was laid out.
  (c) bm25.py — plain BM25 over the union, namespace/id read directly from
      the original fixture files' own frontmatter/manifest.

Usage:
    python3 run.py             # build everything fresh, run, write outputs
    python3 run.py --skip-build  # reuse existing qmd/bm25 indexes, just query+score

Writes results.json (raw per-question hits + scores) and e3-results.md
(summary tables) next to this script.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
DATA_ENG_DIR = REPO_ROOT / "experiments" / "fixtures" / "data-eng"
HOUSEHOLD_DIR = REPO_ROOT / "experiments" / "fixtures" / "household"
QUESTIONS_PATH = REPO_ROOT / "experiments" / "fixtures" / "questions.yaml"

QMD_HOME = HERE / "qmd_home"
A_DIR = QMD_HOME / "a"
B_DIR = QMD_HOME / "b"
SHARED_MODELS = QMD_HOME / "_shared_models"
ALL_BUNDLES_DIR = HERE / "all-bundles"
BM25_INDEX_PATH = HERE / "bm25_index.json"

QMD_BIN = shutil.which("qmd") or str(Path.home() / ".bun" / "bin" / "qmd")

sys.path.insert(0, str(HERE))
from bm25 import BM25Index, read_frontmatter_id, default_bundle_dirs  # noqa: E402


# --------------------------------------------------------------------------
# questions.yaml parsing (hand-rolled: the file's shape is fixed and simple
# — one field per line, no nesting inside a question — so a full YAML
# parser is not worth the dependency; PyYAML is not installed and this repo
# keeps bm25.py stdlib-only by design, so run.py follows the same rule).
# --------------------------------------------------------------------------

def parse_questions(path: Path) -> list[dict]:
    questions: list[dict] = []
    current: dict | None = None
    for raw in path.read_text().splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^-\s*id:\s*(\S+)\s*$", stripped)
        if m:
            if current is not None:
                questions.append(current)
            current = {"id": m.group(1)}
            continue
        if current is None:
            continue
        m = re.match(r'^question:\s*"(.*)"\s*$', stripped)
        if m:
            current["question"] = m.group(1)
            continue
        m = re.match(r'^answer:\s*"(.*)"\s*$', stripped)
        if m:
            current["answer"] = m.group(1)
            continue
        m = re.match(r"^expected:\s*\[(.*)\]\s*$", stripped)
        if m:
            current["expected"] = [x.strip() for x in m.group(1).split(",") if x.strip()]
            continue
        m = re.match(r"^kind:\s*(\S+)\s*$", stripped)
        if m:
            current["kind"] = m.group(1)
            continue
        m = re.match(r"^collision:\s*(true|false)\s*$", stripped)
        if m:
            current["collision"] = m.group(1) == "true"
            continue
    if current is not None:
        questions.append(current)
    return questions


# --------------------------------------------------------------------------
# qmd plumbing
# --------------------------------------------------------------------------

def qmd_env(home: Path) -> dict:
    env = os.environ.copy()
    env["XDG_CACHE_HOME"] = str(home / "cache")
    env["XDG_CONFIG_HOME"] = str(home / "config")
    env["QMD_TRUST_LOCAL_CONFIG"] = "1"
    return env


def run(cmd: list[str], env: dict | None = None, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)


def ensure_models(home: Path) -> None:
    """Download qmd's embedding/rerank/expansion models once, then reuse
    the same ~2.1GB of GGUF weights for both qmd configs (a) and (b) by
    copying rather than downloading twice — they're the same fixed models
    regardless of which corpus is indexed, so this only saves wall-clock
    on a second build, it doesn't change what's being measured."""
    models_dir = home / "cache" / "qmd" / "models"
    if models_dir.exists() and any(models_dir.glob("*.gguf")):
        return
    if SHARED_MODELS.exists() and any(SHARED_MODELS.glob("*.gguf")):
        models_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(SHARED_MODELS, models_dir, dirs_exist_ok=True)
        return
    env = qmd_env(home)
    print(f"  pulling qmd models into {home.name} (first run only, ~2.1GB)...", file=sys.stderr)
    t0 = time.perf_counter()
    r = run([QMD_BIN, "pull", "--progress"], env=env, timeout=1200)
    if r.returncode != 0:
        print(r.stdout, r.stderr, file=sys.stderr)
        raise RuntimeError("qmd pull failed")
    print(f"  model pull took {time.perf_counter() - t0:.1f}s", file=sys.stderr)
    SHARED_MODELS.parent.mkdir(parents=True, exist_ok=True)
    if not SHARED_MODELS.exists():
        shutil.copytree(models_dir, SHARED_MODELS)


def dir_size_bytes(path: Path, exclude_dirnames: tuple[str, ...] = ()) -> int:
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in exclude_dirnames]
        for f in files:
            fp = Path(root) / f
            if fp.exists():
                total += fp.stat().st_size
    return total


def build_config_a() -> dict:
    """Three qmd collections, named exactly by namespace, in one qmd index."""
    if A_DIR.exists():
        shutil.rmtree(A_DIR)
    (A_DIR / "cache").mkdir(parents=True)
    (A_DIR / "config").mkdir(parents=True)
    ensure_models(A_DIR)
    env = qmd_env(A_DIR)

    t0 = time.perf_counter()
    for path, name in [
        (EXAMPLES_DIR, "example-payments"),
        (DATA_ENG_DIR, "data-eng"),
        (HOUSEHOLD_DIR, "household"),
    ]:
        r = run([QMD_BIN, "collection", "add", str(path), "--name", name], env=env)
        if r.returncode != 0:
            raise RuntimeError(f"collection add {name} failed: {r.stderr}")
    r = run([QMD_BIN, "embed"], env=env, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"embed failed: {r.stderr}")
    build_seconds = time.perf_counter() - t0

    index_bytes = dir_size_bytes(A_DIR / "cache" / "qmd", exclude_dirnames=("models",))
    return {"build_seconds": build_seconds, "index_bytes": index_bytes}


def build_config_b() -> dict:
    """One qmd collection `all`, over a materialised copy of all three
    bundles (qmd collections are a single path + glob; symlinks are not
    followed, so the union has to exist on disk — see module docstring)."""
    if B_DIR.exists():
        shutil.rmtree(B_DIR)
    (B_DIR / "cache").mkdir(parents=True)
    (B_DIR / "config").mkdir(parents=True)
    ensure_models(B_DIR)

    if ALL_BUNDLES_DIR.exists():
        shutil.rmtree(ALL_BUNDLES_DIR)
    ALL_BUNDLES_DIR.mkdir(parents=True)
    shutil.copytree(EXAMPLES_DIR, ALL_BUNDLES_DIR / "example-payments")
    shutil.copytree(DATA_ENG_DIR, ALL_BUNDLES_DIR / "data-eng")
    shutil.copytree(HOUSEHOLD_DIR, ALL_BUNDLES_DIR / "household")

    env = qmd_env(B_DIR)
    t0 = time.perf_counter()
    r = run([QMD_BIN, "collection", "add", str(ALL_BUNDLES_DIR), "--name", "all"], env=env)
    if r.returncode != 0:
        raise RuntimeError(f"collection add all failed: {r.stderr}")
    r = run([QMD_BIN, "embed"], env=env, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"embed failed: {r.stderr}")
    build_seconds = time.perf_counter() - t0

    index_bytes = dir_size_bytes(B_DIR / "cache" / "qmd", exclude_dirnames=("models",))
    return {"build_seconds": build_seconds, "index_bytes": index_bytes}


def build_config_c() -> dict:
    idx = BM25Index()
    elapsed = idx.build([str(p) for p in default_bundle_dirs(REPO_ROOT)])
    idx.save(str(BM25_INDEX_PATH))
    return {"build_seconds": elapsed, "index_bytes": BM25_INDEX_PATH.stat().st_size}, idx


# --------------------------------------------------------------------------
# query + mapping to namespace/id
# --------------------------------------------------------------------------

ROOT_MAP_A = {
    "example-payments": EXAMPLES_DIR,
    "data-eng": DATA_ENG_DIR,
    "household": HOUSEHOLD_DIR,
}


def qmd_query(home: Path, question: str, n: int = 5) -> list[str]:
    """Returns ordered list of "namespace/id" strings (may contain
    duplicates if two chunks of the same file both land in the top n —
    see README note on ties/dedup)."""
    env = qmd_env(home)
    r = run([QMD_BIN, "query", question, "-n", str(n), "--format", "json"], env=env, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"qmd query failed: {r.stderr}")
    hits = json.loads(r.stdout)
    out = []
    for hit in hits:
        file_field = hit["file"]
        assert file_field.startswith("qmd://")
        rest = file_field[len("qmd://"):]
        collection, _, sub = rest.partition("/")
        if home == A_DIR:
            namespace = collection
            real_path = ROOT_MAP_A[namespace] / sub
        else:  # B_DIR: collection is "all", namespace is the first segment of sub
            namespace, _, sub2 = sub.partition("/")
            real_path = ALL_BUNDLES_DIR / namespace / sub2
        doc_id = read_frontmatter_id(real_path)
        out.append(f"{namespace}/{doc_id}")
    return out


def bm25_query(idx: BM25Index, question: str, n: int = 5) -> list[str]:
    return [f"{h['namespace']}/{h['id']}" for h in idx.search(question, top_n=n)]


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

def precision_at_5(hits: list[str], expected: list[str]) -> float:
    denom = min(5, len(expected))
    if denom == 0:
        return 0.0
    matched = len(set(hits[:5]) & set(expected))
    return matched / denom


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true", help="reuse existing indexes")
    args = ap.parse_args()

    questions = parse_questions(QUESTIONS_PATH)
    assert len(questions) == 20, f"expected 20 questions, got {len(questions)}"

    print("Building config (a): qmd, one collection per bundle...", file=sys.stderr)
    if args.skip_build and (A_DIR / "cache").exists():
        stats_a = {"build_seconds": None, "index_bytes": dir_size_bytes(A_DIR / "cache" / "qmd", exclude_dirnames=("models",))}
    else:
        stats_a = build_config_a()

    print("Building config (b): qmd, one collection `all`...", file=sys.stderr)
    if args.skip_build and (B_DIR / "cache").exists():
        stats_b = {"build_seconds": None, "index_bytes": dir_size_bytes(B_DIR / "cache" / "qmd", exclude_dirnames=("models",))}
    else:
        stats_b = build_config_b()

    print("Building config (c): plain BM25 over the union...", file=sys.stderr)
    stats_c, bm25_idx = build_config_c()

    print("Running 20 questions x 3 configs...", file=sys.stderr)
    per_question = []
    for q in questions:
        expected = q["expected"]
        hits_a = qmd_query(A_DIR, q["question"])
        hits_b = qmd_query(B_DIR, q["question"])
        hits_c = bm25_query(bm25_idx, q["question"])

        entry = {
            "id": q["id"],
            "kind": q["kind"],
            "collision": q["collision"],
            "expected": expected,
            "hits": {"a": hits_a, "b": hits_b, "c": hits_c},
            "p_at_5": {
                "a": precision_at_5(hits_a, expected),
                "b": precision_at_5(hits_b, expected),
                "c": precision_at_5(hits_c, expected),
            },
            "top_hit_correct": {
                "a": bool(hits_a) and hits_a[0] in expected,
                "b": bool(hits_b) and hits_b[0] in expected,
                "c": bool(hits_c) and hits_c[0] in expected,
            },
        }
        per_question.append(entry)
        print(f"  {q['id']} ({q['kind']}{'*' if q['collision'] else ''}): "
              f"a={entry['p_at_5']['a']:.2f} b={entry['p_at_5']['b']:.2f} c={entry['p_at_5']['c']:.2f}",
              file=sys.stderr)

    # ---- aggregate ----
    configs = ["a", "b", "c"]
    overall = {c: mean([e["p_at_5"][c] for e in per_question]) for c in configs}
    by_kind = {
        kind: {c: mean([e["p_at_5"][c] for e in per_question if e["kind"] == kind]) for c in configs}
        for kind in ("cross", "single")
    }
    collision_qs = [e for e in per_question if e["collision"]]
    collision_top_hit = {c: sum(1 for e in collision_qs if e["top_hit_correct"][c]) for c in configs}

    summary = {
        "date": time.strftime("%Y-%m-%d"),
        "qmd_version": get_qmd_version(),
        "python_version": sys.version.split()[0],
        "build": {"a": stats_a, "b": stats_b, "c": stats_c},
        "overall_p_at_5": overall,
        "by_kind_p_at_5": by_kind,
        "collision_top_hit_correct": collision_top_hit,
        "collision_n": len(collision_qs),
        "questions": per_question,
    }

    (HERE / "results.json").write_text(json.dumps(summary, indent=2))
    write_markdown(summary)
    print("Wrote results.json and e3-results.md", file=sys.stderr)


def get_qmd_version() -> str:
    r = run([QMD_BIN, "--version"])
    return r.stdout.strip() or r.stderr.strip()


def write_markdown(summary: dict) -> None:
    a, b, c = summary["build"]["a"], summary["build"]["b"], summary["build"]["c"]

    def fmt_time(x):
        return f"{x:.1f}s" if isinstance(x, (int, float)) else "n/a (skip-build)"

    def fmt_size(n):
        return f"{n / 1024:.1f} KB" if n < 1024 * 1024 else f"{n / (1024 * 1024):.1f} MB"

    md = []
    md.append("# E3 results: cross-bundle index\n")
    md.append(f"**Date:** {summary['date']}  ")
    md.append(f"**qmd version:** {summary['qmd_version']}  ")
    md.append(f"**Python:** {summary['python_version']}\n")

    md.append("## Configurations\n")
    md.append("- (a) qmd, one collection per bundle (`example-payments`, `data-eng`, `household`), "
               "queried with no `-c` filter so all three collections are searched together.")
    md.append("- (b) qmd, one collection `all` over a materialised copy of the three bundles "
               "(qmd collections are a single path; symlinks aren't followed, so the union is a real copy "
               "under `all-bundles/`, with the original bundle name as the top-level directory in each case).")
    md.append("- (c) `bm25.py` — stdlib-only BM25 (k1=1.5, b=0.75) over the union, namespace/id read from "
               "each bundle's own manifest/frontmatter.\n")

    md.append("Mode: **hybrid** (BM25 + vector + LLM rerank via `qmd query`) for (a) and (b) — the model "
               "download and embedding both completed without falling back to BM25-only. "
               "(c) is BM25-only by construction.\n")

    md.append("P@5 formula: `|top5 ∩ expected| / min(5, |expected|)`, per question, then averaged.\n")

    md.append("## Retrieval quality\n")
    md.append("| Metric | (a) qmd per-bundle collections | (b) qmd single collection | (c) plain BM25 |")
    md.append("|---|---|---|---|")
    md.append(f"| Mean P@5, overall (20 q) | {summary['overall_p_at_5']['a']:.3f} | "
               f"{summary['overall_p_at_5']['b']:.3f} | {summary['overall_p_at_5']['c']:.3f} |")
    md.append(f"| Mean P@5, `kind: cross` (12 q) | {summary['by_kind_p_at_5']['cross']['a']:.3f} | "
               f"{summary['by_kind_p_at_5']['cross']['b']:.3f} | {summary['by_kind_p_at_5']['cross']['c']:.3f} |")
    md.append(f"| Mean P@5, `kind: single` (8 q) | {summary['by_kind_p_at_5']['single']['a']:.3f} | "
               f"{summary['by_kind_p_at_5']['single']['b']:.3f} | {summary['by_kind_p_at_5']['single']['c']:.3f} |")
    n = summary["collision_n"]
    md.append(f"| Collision top-hit correct (x/{n}) | {summary['collision_top_hit_correct']['a']}/{n} | "
               f"{summary['collision_top_hit_correct']['b']}/{n} | {summary['collision_top_hit_correct']['c']}/{n} |")
    md.append("")

    md.append("## Index build cost\n")
    md.append("On-disk size excludes qmd's shared model weights (~2.1GB embedding/rerank/query-expansion "
               "GGUF files) — those are a fixed one-time tool-setup cost, identical regardless of corpus "
               "or configuration, and would otherwise swamp any real difference between (a) and (b). "
               "Build time likewise excludes the model download (also a one-time, shared cost); it covers "
               "collection add (lexical indexing) + `qmd embed` (vector indexing) for (a)/(b), and the "
               "in-process `build()` call for (c).\n")
    md.append("| Metric | (a) | (b) | (c) |")
    md.append("|---|---|---|---|")
    md.append(f"| Build time | {fmt_time(a['build_seconds'])} | {fmt_time(b['build_seconds'])} | {fmt_time(c['build_seconds'])} |")
    md.append(f"| On-disk index size | {fmt_size(a['index_bytes'])} | {fmt_size(b['index_bytes'])} | {fmt_size(c['index_bytes'])} |")
    md.append("")

    md.append("## Per-question results\n")
    md.append("`*` marks the 4 collision questions. P@5 shown per config; ✓/✗ in the last column is "
               "top-hit-correct, shown only for collision questions (blank otherwise).\n")
    md.append("| Q | Kind | P@5 (a) | P@5 (b) | P@5 (c) | Top-hit ok (a/b/c) |")
    md.append("|---|---|---|---|---|---|")
    for e in summary["questions"]:
        mark = "*" if e["collision"] else ""
        tophit = ""
        if e["collision"]:
            tophit = "/".join("✓" if e["top_hit_correct"][c] else "✗" for c in ("a", "b", "c"))
        md.append(f"| {e['id']}{mark} | {e['kind']} | {e['p_at_5']['a']:.2f} | "
                   f"{e['p_at_5']['b']:.2f} | {e['p_at_5']['c']:.2f} | {tophit} |")
    md.append("")

    (HERE / "e3-results.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
