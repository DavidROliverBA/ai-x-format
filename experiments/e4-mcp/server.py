#!/usr/bin/env python3
"""E4: a tools-only MCP server over an AI-X federation manifest.

Plan: MyVault docs/plans/2026-09-26-federation-experiments-plan.md, E4 section.
Shape copied from Google's minimal `fileskb` sample (list / search / read over
a directory) and from the AI-X validator's own `--federation` loader, so
resolution rules match `tools/ai-x-validate.py` exactly (SPEC §9, §6).

Tools (all namespace/id-addressed, never wiki-link-addressed — SPEC §9.2):
    list_bundles()                          -> [{namespace, concepts, ref}]
    list_concepts(namespace=None)           -> [{namespace, id, ref, type, title, description}]
    search(query, namespace=None, limit=5)  -> [{namespace, id, ref, type, title, score, snippet}]
    get(namespace, id)                      -> {namespace, id, ref, frontmatter, body, bundle_ref}

Every response that names a concept carries `namespace` and `id` separately
AND as `ref: "namespace/id"` (E4 plan, measure 2). `get()` additionally
carries `bundle_ref`: the federation manifest's declared `ref` for that
bundle (a git commit for `source: git` bundles, `null` for `source: path`
bundles that carry no ref) — this is the provenance field E1 found matters
more than resolution itself.

Each concept is also exposed as a resource `ai-x://<namespace>/<id>`
(text/markdown, the concept file's raw content verbatim) for the VS Code
side-test (E4 measure 3). Resources are secondary; tools are primary.

Run directly (stdio, the default transport):
    uv run --with mcp --with pyyaml server.py [--federation <federation.ai-x.yaml>]

Inspect interactively:
    uv run --with mcp --with pyyaml mcp dev server.py -- --federation <path>

Self-contained beyond the two `--with` packages: PyYAML is preferred but
optional — `tools/ai-x-validate.py` (imported directly, not reimplemented)
falls back to a stdlib-only YAML subset parser when PyYAML is absent, the
same fallback E2 proved byte-identical against the fixtures.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import math
import re
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError

# --- Paths ---------------------------------------------------------------

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[2]  # experiments/e4-mcp/server.py -> ai-x-format/
VALIDATOR_PATH = REPO_ROOT / "tools" / "ai-x-validate.py"
DEFAULT_FEDERATION = REPO_ROOT / "experiments" / "fixtures" / "federation.ai-x.yaml"


def _load_validator_module() -> ModuleType:
    """Import tools/ai-x-validate.py by path (hyphenated filename, not a
    valid module name) so this server reuses its exact frontmatter/YAML
    parsing and federation-manifest loading rather than reimplementing
    either — the task's own instruction, and the reason E1/E2's numbers
    and this server's numbers can be compared directly."""
    spec = importlib.util.spec_from_file_location("ai_x_validate", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load validator module from {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_validator_module()


# --- CLI (parsed at import time so it works whether this file is run
# directly, spawned as a stdio subprocess by a client, or launched under
# `mcp dev` / `mcp run`) ----------------------------------------------------

def _parse_federation_path() -> Path:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--federation", type=Path, default=None)
    args, _unknown = parser.parse_known_args()
    path = args.federation or DEFAULT_FEDERATION
    return path.resolve()


FEDERATION_PATH = _parse_federation_path()


# --- Federation loading ----------------------------------------------------

def load_federation_bundles(fed_path: Path) -> dict[str, dict]:
    """Load every bundle a federation.ai-x.yaml lists, resolving `source:
    path` relative to the manifest and `source: git` as `subdir` relative
    to the manifest's own git repo root — identical resolution to
    `ai-x-validate.py --federation` (SPEC §9). Returns
    {namespace: {root, ref, source, concepts: {id: {fm, body, path}}}}."""
    if not fed_path.is_file():
        raise RuntimeError(f"federation manifest not found: {fed_path}")

    federation, findings, bundle_reports = validator.load_federation(fed_path)
    errors = [f for f in findings if f.level == "error"]
    if errors:
        detail = "; ".join(f"{f.path}: {f.msg}" for f in errors)
        raise RuntimeError(f"federation manifest {fed_path} failed to load: {detail}")

    bundles: dict[str, dict] = {}
    for report in bundle_reports:
        ns = report["namespace"]
        root = Path(report["root"])
        concepts: dict[str, dict] = {}
        for p in sorted(root.rglob("*.md")):
            if p.name in validator.RESERVED_MD:
                continue
            fm, _err, body = validator.parse_concept(p)
            if not isinstance(fm, dict):
                continue
            cid = fm.get("id")
            if not cid:
                continue
            concepts[str(cid)] = {"fm": fm, "body": body, "path": p}
        bundles[ns] = {
            "root": root,
            "ref": report.get("ref"),
            "source": report.get("source"),
            "concepts": concepts,
        }
    return bundles


def json_safe(value):
    """Frontmatter loaded via PyYAML resolves ISO dates/datetimes to Python
    `date`/`datetime` objects, which are not JSON-serialisable and would
    break an MCP tool result. Convert them to their ISO string form —
    values are preserved verbatim, only the Python type changes for
    transport. A no-op when the stdlib fallback parser is in play, since it
    keeps every scalar as a string already (SPEC-parsing note in
    ai-x-validate.py)."""
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value


FEDERATION: dict[str, dict] = load_federation_bundles(FEDERATION_PATH)


# --- BM25 (stdlib-only; e3-index/bm25.py does not exist in this branch at
# the time this server was written, so this is a small independent
# implementation, not a copy) -----------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """Classic Robertson/Sparck-Jones BM25 (k1=1.5, b=0.75) over a fixed
    list of docs, each {"namespace", "id", "tokens", ...}. No field
    weighting: title, description and body are concatenated into one bag of
    words per concept (SPEC gives no guidance here; a judgement call — see
    e4-results.md)."""

    K1 = 1.5
    B = 0.75

    def __init__(self, docs: list[dict]):
        self.docs = docs
        self.n = len(docs)
        self.avgdl = (sum(len(d["tokens"]) for d in docs) / self.n) if self.n else 0.0
        self.df: Counter[str] = Counter()
        for d in docs:
            self.df.update(set(d["tokens"]))

    def _idf(self, term: str) -> float:
        n_t = self.df.get(term, 0)
        return math.log((self.n - n_t + 0.5) / (n_t + 0.5) + 1)

    def _score(self, doc: dict, query_tokens: list[str]) -> float:
        if not doc["tokens"]:
            return 0.0
        tf = Counter(doc["tokens"])
        dl = len(doc["tokens"])
        score = 0.0
        for t in query_tokens:
            f = tf.get(t, 0)
            if f == 0:
                continue
            idf = self._idf(t)
            denom = f + self.K1 * (1 - self.B + self.B * dl / (self.avgdl or 1.0))
            score += idf * (f * (self.K1 + 1)) / denom
        return score

    def search(self, query: str, limit: int = 5) -> list[tuple[float, dict]]:
        q = tokenize(query)
        scored = [(self._score(d, q), d) for d in self.docs]
        scored = [pair for pair in scored if pair[0] > 0]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[:limit]


def _doc_text(fm: dict, body: str) -> str:
    title = str(fm.get("title") or "")
    description = str(fm.get("description") or "")
    return f"{title}\n{description}\n{body}"


def _build_index(bundles: dict[str, dict], namespace: str | None) -> BM25Index:
    docs = []
    namespaces = [namespace] if namespace is not None else sorted(bundles)
    for ns in namespaces:
        for cid, rec in bundles[ns]["concepts"].items():
            docs.append({
                "namespace": ns,
                "id": cid,
                "tokens": tokenize(_doc_text(rec["fm"], rec["body"])),
            })
    return BM25Index(docs)


GLOBAL_INDEX = _build_index(FEDERATION, namespace=None)


def make_snippet(fm: dict, body: str, length: int = 200) -> str:
    """Prefer the concept's own `description`; fall back to the first
    non-heading body line. Judgement call on length: 200 chars is enough to
    disambiguate a colliding id (SPEC §9.1) without dumping the whole
    concept into a search result."""
    text = str(fm.get("description") or "").strip()
    if not text:
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                text = line
                break
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > length:
        head = text[:length].rsplit(" ", 1)[0]
        text = f"{head}…"
    return text


# --- MCP server --------------------------------------------------------

mcp = MCPServer(
    "ai-x-federation",
    instructions=(
        "Serves an AI-X federation of knowledge bundles. Use list_bundles to see what's "
        "held, search or list_concepts to find a concept, and get(namespace, id) to read "
        "one in full. Always cite results as namespace/id — two bundles in this "
        "federation deliberately share bare ids, and only the namespace disambiguates them."
    ),
)


def _known_namespaces() -> str:
    return ", ".join(sorted(FEDERATION)) or "(none)"


@mcp.tool()
def list_bundles() -> list[dict]:
    """List every bundle held by this server: its namespace, how many
    concepts it has, and the federation manifest's declared `ref` for it
    (a git commit for a `source: git` bundle, null for `source: path`)."""
    return [
        {
            "namespace": ns,
            "concepts": len(FEDERATION[ns]["concepts"]),
            "ref": FEDERATION[ns].get("ref"),
        }
        for ns in sorted(FEDERATION)
    ]


@mcp.tool()
def list_concepts(namespace: str | None = None) -> list[dict]:
    """List concepts across the whole federation, or within one namespace
    if given. Each entry carries namespace and id separately and combined
    as ref ("namespace/id")."""
    if namespace is not None and namespace not in FEDERATION:
        raise ToolError(f"Unknown namespace '{namespace}'. Known namespaces: {_known_namespaces()}.")
    namespaces = [namespace] if namespace is not None else sorted(FEDERATION)
    out = []
    for ns in namespaces:
        for cid in sorted(FEDERATION[ns]["concepts"]):
            fm = FEDERATION[ns]["concepts"][cid]["fm"]
            out.append({
                "namespace": ns,
                "id": cid,
                "ref": f"{ns}/{cid}",
                "type": fm.get("type"),
                "title": fm.get("title"),
                "description": fm.get("description"),
            })
    return out


@mcp.tool()
def search(query: str, namespace: str | None = None, limit: int = 5) -> list[dict]:
    """BM25 search over concept title + description + body, across the
    federation by default or within one namespace. Returns up to `limit`
    hits, each carrying namespace and id separately and combined as ref."""
    if namespace is not None and namespace not in FEDERATION:
        raise ToolError(f"Unknown namespace '{namespace}'. Known namespaces: {_known_namespaces()}.")
    index = GLOBAL_INDEX if namespace is None else _build_index(FEDERATION, namespace)
    hits = index.search(query, limit=limit)
    out = []
    for score, doc in hits:
        ns, cid = doc["namespace"], doc["id"]
        rec = FEDERATION[ns]["concepts"][cid]
        fm = rec["fm"]
        out.append({
            "namespace": ns,
            "id": cid,
            "ref": f"{ns}/{cid}",
            "type": fm.get("type"),
            "title": fm.get("title"),
            "score": round(score, 4),
            "snippet": make_snippet(fm, rec["body"]),
        })
    return out


@mcp.tool()
def get(namespace: str, id: str) -> dict[str, object]:
    """Fetch one concept by namespace + id: its frontmatter verbatim
    (including links, verified, sources, status, stale_after, provenance),
    its body, and bundle_ref (the federation manifest's ref for its
    bundle)."""
    bundle = FEDERATION.get(namespace)
    if bundle is None:
        raise ToolError(f"Unknown namespace '{namespace}'. Known namespaces: {_known_namespaces()}.")
    record = bundle["concepts"].get(id)
    if record is None:
        known = ", ".join(sorted(bundle["concepts"])) or "(none)"
        raise ToolError(f"Unknown id '{id}' in namespace '{namespace}'. Known ids: {known}.")
    return {
        "namespace": namespace,
        "id": id,
        "ref": f"{namespace}/{id}",
        "frontmatter": json_safe(record["fm"]),
        "body": record["body"],
        "bundle_ref": bundle.get("ref"),
    }


@mcp.resource("ai-x://{namespace}/{id}", mime_type="text/markdown")
def concept_resource(namespace: str, id: str) -> str:
    """The concept file's raw markdown (frontmatter + body), verbatim, for
    clients that only read resources (the VS Code side-test, E4 measure 3)."""
    bundle = FEDERATION.get(namespace)
    if bundle is None:
        raise ResourceNotFoundError(f"Unknown namespace '{namespace}'. Known namespaces: {_known_namespaces()}.")
    record = bundle["concepts"].get(id)
    if record is None:
        known = ", ".join(sorted(bundle["concepts"])) or "(none)"
        raise ResourceNotFoundError(f"Unknown id '{id}' in namespace '{namespace}'. Known ids: {known}.")
    return record["path"].read_text(encoding="utf-8")


if __name__ == "__main__":
    print(
        f"ai-x-federation MCP server: {len(FEDERATION)} bundle(s) held from {FEDERATION_PATH} "
        f"({sum(len(b['concepts']) for b in FEDERATION.values())} concepts total)",
        file=sys.stderr,
    )
    mcp.run()
