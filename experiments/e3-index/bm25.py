#!/usr/bin/env python3
"""Configuration (c) for E3: plain BM25 over the union of the three fixture
bundles, written from scratch with the Python standard library only (no
third-party dependencies — this is the point of comparison against qmd).

Tokenises the *whole file* (YAML frontmatter + markdown body) into lowercase
alphanumeric tokens. Each document is tagged with:

  - `namespace` — read from its bundle's manifest.ai-xf.yaml `namespace:` field
    (not the `name:` field, though the two happen to match in these fixtures).
  - `id`        — the file's own frontmatter `id:` field. Files with no
    frontmatter (index.md, log.md) have no `id`; they fall back to the
    file's stem ("index", "log") purely so every document has *some* key —
    these never appear in `expected` lists in questions.yaml, so they can
    only ever be non-matching noise in a result set, which is the correct
    behaviour to measure (a plain-BM25 union has no way to know these files
    aren't citable concepts).

Standard Okapi BM25, k1=1.5, b=0.75, IDF with the +1 smoothing term
(`ln((N - n + 0.5) / (n + 0.5) + 1)`) so common terms never score negative.

CLI:
    python3 bm25.py --build                      # build + persist the index
    python3 bm25.py --query "some question" -n 5 # query the persisted index

Also usable as a library — see BM25Index.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from pathlib import Path

TOKEN_RE = re.compile(r"[a-z0-9]+")
K1 = 1.5
B = 0.75


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _frontmatter_block(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end]


def read_manifest_namespace(bundle_dir: Path) -> str:
    manifest = bundle_dir / "manifest.ai-xf.yaml"
    text = manifest.read_text()
    m = re.search(r'^namespace:\s*"?([^"\n]+?)"?\s*$', text, re.MULTILINE)
    if not m:
        raise ValueError(f"no namespace: field found in {manifest}")
    return m.group(1).strip()


def read_frontmatter_id(path: Path) -> str:
    text = path.read_text()
    fm = _frontmatter_block(text)
    if fm is not None:
        m = re.search(r'^id:\s*"?([^"\n]+?)"?\s*$', fm, re.MULTILINE)
        if m:
            return m.group(1).strip()
    # No frontmatter / no id: field (index.md, log.md). Fall back to the
    # file stem so every document is addressable; these never match any
    # question's `expected` list by construction.
    return path.stem


class BM25Index:
    def __init__(self) -> None:
        self.docs: list[dict] = []  # {path, namespace, id, len, tf}
        self.df: dict[str, int] = {}
        self.N = 0
        self.avgdl = 0.0
        self.build_seconds: float | None = None

    def _add_bundle(self, bundle_dir: Path) -> None:
        namespace = read_manifest_namespace(bundle_dir)
        for md in sorted(bundle_dir.rglob("*.md")):
            text = md.read_text()
            tokens = tokenize(text)
            self.docs.append(
                {
                    "path": str(md),
                    "namespace": namespace,
                    "id": read_frontmatter_id(md),
                    "len": len(tokens),
                    "tf": _term_freqs(tokens),
                }
            )

    def build(self, bundle_dirs: list[str]) -> float:
        t0 = time.perf_counter()
        for d in bundle_dirs:
            self._add_bundle(Path(d))
        self.N = len(self.docs)
        total_len = 0
        df: dict[str, int] = {}
        for doc in self.docs:
            total_len += doc["len"]
            for t in doc["tf"]:
                df[t] = df.get(t, 0) + 1
        self.df = df
        self.avgdl = (total_len / self.N) if self.N else 0.0
        self.build_seconds = time.perf_counter() - t0
        return self.build_seconds

    def _idf(self, term: str) -> float:
        n = self.df.get(term, 0)
        return math.log((self.N - n + 0.5) / (n + 0.5) + 1)

    def _score(self, doc: dict, query_tokens: list[str]) -> float:
        s = 0.0
        dl = doc["len"]
        for t in query_tokens:
            f = doc["tf"].get(t, 0)
            if f == 0:
                continue
            idf = self._idf(t)
            denom = f + K1 * (1 - B + B * (dl / self.avgdl if self.avgdl else 0))
            s += idf * (f * (K1 + 1)) / denom
        return s

    def search(self, query: str, top_n: int = 5) -> list[dict]:
        q_tokens = tokenize(query)
        scored = []
        for doc in self.docs:
            s = self._score(doc, q_tokens)
            if s > 0:
                scored.append((s, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"namespace": d["namespace"], "id": d["id"], "score": s, "path": d["path"]}
            for s, d in scored[:top_n]
        ]

    def to_serializable(self) -> dict:
        return {
            "N": self.N,
            "avgdl": self.avgdl,
            "df": self.df,
            "docs": self.docs,
        }

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_serializable(), f)

    @classmethod
    def load(cls, path: str) -> "BM25Index":
        with open(path) as f:
            data = json.load(f)
        idx = cls()
        idx.N = data["N"]
        idx.avgdl = data["avgdl"]
        idx.df = data["df"]
        idx.docs = data["docs"]
        return idx


def _term_freqs(tokens: list[str]) -> dict[str, int]:
    tf: dict[str, int] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    return tf


def default_bundle_dirs(repo_root: Path) -> list[Path]:
    return [
        repo_root / "examples",
        repo_root / "experiments" / "fixtures" / "data-eng",
        repo_root / "experiments" / "fixtures" / "household",
    ]


def main() -> None:
    here = Path(__file__).resolve().parent
    repo_root_default = here.parents[1]  # .../ai-xf-format

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="build and persist the index")
    ap.add_argument(
        "--index-path",
        default=str(here / "bm25_index.json"),
        help="where the persisted index lives",
    )
    ap.add_argument("--repo-root", default=str(repo_root_default))
    ap.add_argument("--query", default=None, help="run a single query against the persisted index")
    ap.add_argument("-n", type=int, default=5)
    args = ap.parse_args()

    repo_root = Path(args.repo_root)

    if args.build:
        idx = BM25Index()
        elapsed = idx.build([str(p) for p in default_bundle_dirs(repo_root)])
        idx.save(args.index_path)
        size = os.path.getsize(args.index_path)
        print(json.dumps({"build_seconds": elapsed, "docs": idx.N, "index_bytes": size}))
        return

    if args.query is not None:
        idx = BM25Index.load(args.index_path)
        print(json.dumps(idx.search(args.query, top_n=args.n), indent=2))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
