#!/usr/bin/env python3
"""E4 smoke test: start server.py via the MCP client SDK, call each tool
once (including an unknown id), read one resource (plus an unknown one),
and assert the payload shapes the plan requires (namespace/id/ref on every
concept-shaped response; frontmatter verbatim including links, verified,
sources, status, stale_after, provenance on `get`).

Run:
    uv run --with mcp --with pyyaml smoke_test.py [--federation <path>]

Exits 0 and prints "SMOKE TEST: PASS" on success; raises AssertionError
(exit 1) on the first failed check.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

HERE = Path(__file__).resolve().parent
SERVER_PATH = HERE / "server.py"


async def main(federation: Path | None) -> None:
    args = [str(SERVER_PATH)]
    if federation is not None:
        args += ["--federation", str(federation)]
    params = StdioServerParameters(command=sys.executable, args=args)

    checks = 0

    async with Client(params) as client:
        # --- list_bundles ---------------------------------------------
        tools = await client.list_tools()
        names = {t.name for t in tools.tools}
        assert names == {"list_bundles", "list_concepts", "search", "get"}, \
            f"unexpected tool set: {names}"
        checks += 1

        r = await client.call_tool("list_bundles", {})
        assert not r.is_error, r.content
        bundles = r.structured_content["result"]
        assert len(bundles) == 3, f"expected 3 bundles, got {len(bundles)}"
        by_ns = {b["namespace"]: b for b in bundles}
        assert {"example-payments", "data-eng", "household"} <= by_ns.keys()
        for b in bundles:
            assert {"namespace", "concepts", "ref"} <= b.keys()
            assert isinstance(b["concepts"], int) and b["concepts"] > 0
        # source: git bundle carries a ref; source: path bundles do not
        assert by_ns["example-payments"]["ref"] is not None
        assert by_ns["data-eng"]["ref"] is None
        assert by_ns["household"]["ref"] is None
        checks += 1
        print(f"list_bundles: {len(bundles)} bundle(s) -> {sorted(by_ns)}")

        # --- list_concepts (all, then scoped) ---------------------------
        r = await client.call_tool("list_concepts", {})
        assert not r.is_error, r.content
        all_concepts = r.structured_content["result"]
        expected_total = sum(b["concepts"] for b in bundles)
        assert len(all_concepts) == expected_total, \
            f"list_concepts total {len(all_concepts)} != sum of bundle counts {expected_total}"
        for c in all_concepts:
            assert {"namespace", "id", "ref", "type", "title", "description"} <= c.keys()
            assert c["ref"] == f"{c['namespace']}/{c['id']}"
        checks += 1

        r = await client.call_tool("list_concepts", {"namespace": "data-eng"})
        assert not r.is_error, r.content
        de_concepts = r.structured_content["result"]
        assert len(de_concepts) == by_ns["data-eng"]["concepts"]
        assert all(c["namespace"] == "data-eng" for c in de_concepts)
        checks += 1
        print(f"list_concepts: {len(all_concepts)} total, {len(de_concepts)} in data-eng")

        # unknown namespace -> clear tool error, not a crash
        r = await client.call_tool("list_concepts", {"namespace": "does-not-exist"})
        assert r.is_error, "list_concepts with an unknown namespace should be a tool error"
        assert "Unknown namespace" in r.content[0].text
        checks += 1

        # --- search ------------------------------------------------------
        r = await client.call_tool("search", {"query": "customers foreign key orders table", "limit": 5})
        assert not r.is_error, r.content
        hits = r.structured_content["result"]
        assert 1 <= len(hits) <= 5
        for h in hits:
            assert {"namespace", "id", "ref", "type", "title", "score", "snippet"} <= h.keys()
            assert h["ref"] == f"{h['namespace']}/{h['id']}"
            assert isinstance(h["score"], (int, float)) and h["score"] > 0
        # scores should be sorted descending
        scores = [h["score"] for h in hits]
        assert scores == sorted(scores, reverse=True), "search results are not score-sorted"
        checks += 1
        print(f"search: {len(hits)} hit(s), top={hits[0]['ref']} score={hits[0]['score']}")

        # namespace-scoped search restricts results to that namespace
        r = await client.call_tool("search", {"query": "customers", "namespace": "household", "limit": 5})
        assert not r.is_error, r.content
        h_hits = r.structured_content["result"]
        assert h_hits, "expected at least one household hit for 'customers'"
        assert all(h["namespace"] == "household" for h in h_hits)
        checks += 1

        # unknown namespace on search -> clear tool error
        r = await client.call_tool("search", {"query": "x", "namespace": "does-not-exist"})
        assert r.is_error
        assert "Unknown namespace" in r.content[0].text
        checks += 1

        # --- get: a known concept with the full trust-signal surface -----
        r = await client.call_tool("get", {"namespace": "data-eng", "id": "orders-table"})
        assert not r.is_error, r.content
        got = r.structured_content
        assert got["namespace"] == "data-eng"
        assert got["id"] == "orders-table"
        assert got["ref"] == "data-eng/orders-table"
        assert "bundle_ref" in got  # None for a source:path bundle, present for source:git
        fm = got["frontmatter"]
        for key in ("type", "id", "title", "description", "generated", "verified",
                    "status", "stale_after", "provenance", "links"):
            assert key in fm, f"frontmatter missing `{key}` (verbatim carry-through broken)"
        assert isinstance(fm["links"], list) and fm["links"], "links must be carried verbatim"
        assert any(link.get("to") == "example-payments/orders-table" for link in fm["links"]), \
            "the federation-qualified link into the colliding id must survive"
        assert "body" in got and isinstance(got["body"], str) and got["body"]
        checks += 1
        print(f"get(data-eng/orders-table): frontmatter keys = {sorted(fm.keys())}")

        # a bundle-ref-bearing concept (source: git)
        r = await client.call_tool("get", {"namespace": "example-payments", "id": "orders-table"})
        assert not r.is_error, r.content
        got2 = r.structured_content
        assert got2["bundle_ref"] == by_ns["example-payments"]["ref"], \
            "get()'s bundle_ref must match list_bundles()'s ref for the same bundle"
        checks += 1

        # --- get: unknown namespace / unknown id -> clear errors, not exceptions
        r = await client.call_tool("get", {"namespace": "does-not-exist", "id": "x"})
        assert r.is_error
        assert "Unknown namespace" in r.content[0].text
        checks += 1

        r = await client.call_tool("get", {"namespace": "data-eng", "id": "does-not-exist"})
        assert r.is_error
        assert "Unknown id" in r.content[0].text
        checks += 1
        print("get(): unknown namespace and unknown id both return clear tool errors (is_error=True), no crash")

        # --- resources -----------------------------------------------------
        listed_templates = await client.list_resource_templates()
        uri_templates = [t.uri_template for t in listed_templates.resource_templates]
        assert "ai-x://{namespace}/{id}" in uri_templates, uri_templates
        checks += 1

        res = await client.read_resource("ai-x://data-eng/orders-table")
        assert len(res.contents) == 1
        content = res.contents[0]
        assert content.mime_type == "text/markdown", content.mime_type
        assert content.text.startswith("---\n"), "resource should be the raw concept file, frontmatter first"
        assert "id: orders-table" in content.text
        checks += 1
        print(f"resource ai-x://data-eng/orders-table: {len(content.text)} chars, mime={content.mime_type}")

        # unknown resource -> a clean protocol error, not a crash
        try:
            await client.read_resource("ai-x://data-eng/does-not-exist")
            raise AssertionError("reading an unknown resource id should have raised")
        except Exception as e:  # MCPError from the client, per the SDK's Handling Errors page
            assert "Unknown id" in str(e), str(e)
        checks += 1

    print(f"\nSMOKE TEST: PASS ({checks} checks)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--federation", type=Path, default=None)
    ns = ap.parse_args()
    asyncio.run(main(ns.federation))
