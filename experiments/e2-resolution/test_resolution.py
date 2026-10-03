#!/usr/bin/env python3
"""Tests for ai-xf-validate.py's --federation identity resolution (E2).

Invokes the validator via subprocess with --json under both YAML parsers:
the stdlib fallback mini-parser (plain `python3`, no PyYAML installed) and
real PyYAML (`uv run --with pyyaml python3 ...`). Every assertion is made
against parsed JSON output, never against stdout text.

Run directly:
    python3 experiments/e2-resolution/test_resolution.py -v
or via run.sh, which runs this file under both parsers explicitly.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
VALIDATOR = REPO_ROOT / "tools" / "ai-xf-validate.py"
EXAMPLES = REPO_ROOT / "examples"
BUNDLE_C = HERE / "bundle-c"
FEDERATION_YAML = HERE / "federation.ai-xf.yaml"
BASELINE_FILE = HERE / "baseline-examples-level2.json"

HAS_UV = shutil.which("uv") is not None


def run_validator(args: list[str], use_pyyaml: bool = False, cwd: Path = REPO_ROOT) -> tuple[int, dict]:
    """Run ai-xf-validate.py with --json and return (returncode, parsed_json)."""
    if use_pyyaml:
        cmd = ["uv", "run", "-q", "--with", "pyyaml", "python3", str(VALIDATOR), *args]
    else:
        cmd = [sys.executable, str(VALIDATOR), *args]
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:  # pragma: no cover - debugging aid
        raise AssertionError(
            f"non-JSON output from {' '.join(cmd)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        ) from e
    return proc.returncode, data


def normalize_bundle_field(data: dict) -> dict:
    """The `bundle` field just echoes the CLI arg — irrelevant to regression
    comparison, and it legitimately varies with invocation cwd/relpath."""
    d = dict(data)
    d.pop("bundle", None)
    return d


def find_findings(findings: list[dict], substring: str) -> list[dict]:
    return [f for f in findings if substring in f["message"]]


class RegressionUnchanged(unittest.TestCase):
    """examples/ WITHOUT --federation must be byte-identical (module the
    echoed `bundle` path) to the pre-change baseline captured before any
    --federation code was added."""

    def setUp(self):
        if not BASELINE_FILE.exists():
            self.skipTest(f"no baseline file at {BASELINE_FILE}")
        self.baseline = normalize_bundle_field(json.loads(BASELINE_FILE.read_text()))

    def test_examples_unchanged_stdlib_parser(self):
        rc, data = run_validator(["examples", "--level", "2", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(normalize_bundle_field(data), self.baseline)

    def test_examples_unchanged_pyyaml_parser(self):
        if not HAS_UV:
            self.skipTest("uv not available")
        rc, data = run_validator(["examples", "--level", "2", "--json"], use_pyyaml=True)
        self.assertEqual(rc, 0)
        self.assertEqual(normalize_bundle_field(data), self.baseline)

    def test_stdlib_and_pyyaml_agree_on_examples(self):
        if not HAS_UV:
            self.skipTest("uv not available")
        _, a = run_validator(["examples", "--level", "2", "--json"])
        _, b = run_validator(["examples", "--level", "2", "--json"], use_pyyaml=True)
        self.assertEqual(normalize_bundle_field(a), normalize_bundle_field(b))


class FederationResolution(unittest.TestCase):
    """bundle-c under --federation exercises every reference form: Foam-rule
    unqualified resolution (single and colliding candidates), a resolving
    qualified reference, a resolving explicit ai-xf:// reference, an illegal
    same-bundle qualification, and an unresolved qualified reference."""

    EXPECTED = {
        "foam_single": ("warning", "only-a", [
            "links[0] `to: only-a`",
            "resolves in federation bundle(s) [a]",
            "resolved to `a/only-a`",
        ]),
        "foam_collision": ("warning", "shared", [
            "links[1] `to: shared`",
            "resolves in federation bundle(s) [a, b]",
            "resolved to `a/shared`",
        ]),
        "same_bundle_qualified": ("error", "c/something", [
            "links[4] `to: c/something`",
            "MUST NOT qualify same-bundle references",
        ]),
        "unresolved_qualified": ("warning", "b/missing", [
            "links[5] `to: b/missing`",
            "qualified reference does not resolve in the federation",
        ]),
    }

    def _check(self, findings: list[dict]):
        # Exactly the four expected findings, one each, with the right severity.
        self.assertEqual(len(findings), 4, findings)
        for _name, (severity, _needle, substrings) in self.EXPECTED.items():
            matches = [f for f in findings
                       if f["severity"] == severity and all(s in f["message"] for s in substrings)]
            self.assertEqual(len(matches), 1,
                              f"expected exactly one {severity} finding matching {substrings}, got {matches}")

        # Zero silent misresolutions: the two references that DO resolve
        # cleanly (qualified `a/only-a` and explicit `ai-xf://b/shared`) must
        # produce no finding at all — links[2] and links[3] are absent.
        self.assertEqual(find_findings(findings, "links[2]"), [])
        self.assertEqual(find_findings(findings, "links[3]"), [])
        self.assertEqual(find_findings(findings, "a/only-a` qualified"), [])
        self.assertEqual(find_findings(findings, "ai-xf://b/shared"), [])

    def test_resolution_stdlib_parser(self):
        rc, data = run_validator(["bundle-c", "--federation", "federation.ai-xf.yaml", "--json"], cwd=HERE)
        self.assertEqual(rc, 1)  # the same-bundle-qualification case is an error
        self.assertFalse(data["passed"])
        self.assertEqual(data["achieved_level"], 1)
        self._check(data["findings"])

    def test_resolution_pyyaml_parser(self):
        if not HAS_UV:
            self.skipTest("uv not available")
        rc, data = run_validator(
            ["bundle-c", "--federation", "federation.ai-xf.yaml", "--json"], use_pyyaml=True, cwd=HERE)
        self.assertEqual(rc, 1)
        self.assertFalse(data["passed"])
        self._check(data["findings"])

    def test_stdlib_and_pyyaml_agree_on_bundle_c(self):
        if not HAS_UV:
            self.skipTest("uv not available")
        _, a = run_validator(["bundle-c", "--federation", "federation.ai-xf.yaml", "--json"], cwd=HERE)
        _, b = run_validator(
            ["bundle-c", "--federation", "federation.ai-xf.yaml", "--json"], use_pyyaml=True, cwd=HERE)
        self.assertEqual(normalize_bundle_field(a), normalize_bundle_field(b))

    def test_federation_provenance_in_json(self):
        _, data = run_validator(["bundle-c", "--federation", "federation.ai-xf.yaml", "--json"], cwd=HERE)
        fed = data["federation"]
        self.assertEqual(sorted(fed["namespaces"]), ["a", "b", "c"])
        namespaces_held = {b["namespace"] for b in fed["bundles"]}
        self.assertEqual(namespaces_held, {"a", "b", "c"})
        for b in fed["bundles"]:
            self.assertTrue(Path(b["root"]).is_dir(), b)
            self.assertEqual(b["source"], "path")
            self.assertIsNone(b["ref"])  # source: path entries carry no git ref

    def test_federation_stats(self):
        _, data = run_validator(
            ["bundle-c", "--federation", "federation.ai-xf.yaml", "--stats", "--json"], cwd=HERE)
        fed_stats = data["stats"]["federation"]
        self.assertEqual(fed_stats["bundles_held"], 3)
        self.assertEqual(fed_stats["concepts_per_namespace"], {"a": 2, "b": 2, "c": 2})
        self.assertEqual(fed_stats["colliding_ids"], {"shared": ["a", "b"]})
        self.assertEqual(fed_stats["qualified_refs"], {"resolved": 2, "unresolved": 1})
        self.assertEqual(fed_stats["unqualified_cross_bundle_resolutions"], 2)

    def test_provenance_report_text_mode(self):
        cmd = [sys.executable, str(VALIDATOR), "bundle-c", "--federation", "federation.ai-xf.yaml"]
        proc = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
        self.assertIn("federation: 3 bundle(s) held (a, b, c)", proc.stdout)
        for ns in ("a", "b", "c"):
            self.assertIn(f"- {ns}: ", proc.stdout)

    def test_own_bundle_resolution_beats_other_bundles(self):
        """SPEC/plan: if an unqualified `to:` resolves in the OWN bundle, no
        finding is emitted even if other bundles also carry that id — the
        Foam rule never fires. `linker` and `something` are bundle-c's own
        ids and neither is used as an unqualified `to:` target elsewhere in
        this fixture, so this is checked structurally: bundle-c's own ids
        never appear in the federation-collision list, and no Foam-rule
        warning names bundle c as a candidate for its own id."""
        _, data = run_validator(
            ["bundle-c", "--federation", "federation.ai-xf.yaml", "--stats", "--json"], cwd=HERE)
        collisions = data["stats"]["federation"]["colliding_ids"]
        self.assertNotIn("linker", collisions)
        self.assertNotIn("something", collisions)


FRESHNESS_FILES = {
    # bundle x: one live concept, one ghost the index does not list, one
    # retired tombstone (no successor), one redirect tombstone (successor).
    "x/manifest.ai-xf.yaml": "ai-xf: \"0.4\"\nname: x\nnamespace: x\n",
    "x/index.md": ("# x\n\n- [Live](./concepts/live.md)\n- [New](./concepts/new.md)\n\n## Retired\n\n"
                   "- [Gone](./concepts/gone.md)\n- [Old](./concepts/old.md)\n"),
    "x/concepts/live.md": ("---\ntype: Concept\nid: live\nstatus: stable\nlinks:\n- rel: relates-to\n  to: gone\n"
                           "- rel: relates-to\n  to: old\n- rel: supersedes\n  to: gone\n---\n\n"
                           "[Gone](./gone.md) [Old](./old.md)\n"),
    "x/concepts/new.md": "---\ntype: Concept\nid: new\nstatus: stable\n---\n\nNew.\n",
    "x/concepts/gone.md": "---\ntype: Concept\nid: gone\nstatus: deprecated\n---\n\nRetired.\n",
    "x/concepts/old.md": ("---\ntype: Concept\nid: old\nstatus: deprecated\nlinks:\n- rel: superseded-by\n"
                          "  to: new\n---\n\n[New](./new.md)\n"),
    "x/concepts/ghost.md": "---\ntype: Concept\nid: ghost\nstatus: stable\n---\n\nLeft behind.\n",
    # bundle y: a live edge into x's retired concept, written as a qualified ref.
    "y/manifest.ai-xf.yaml": "ai-xf: \"0.4\"\nname: y\nnamespace: y\n",
    "y/concepts/far.md": "---\ntype: Concept\nid: far\nstatus: stable\nlinks:\n- rel: references\n  to: x/gone\n---\n\n[Gone](x/gone)\n",
    "types.json": '{"version": 1, "values": [{"name": "Concept"}, {"name": "Policy"}]}',
    "rels.json": ('{"version": 1, "values": [{"name": "relates-to"}, {"name": "part-of"}, {"name": "has-part"},'
                  ' {"name": "references"}, {"name": "referenced-by"}, {"name": "supersedes"}]}'),
    "federation.ai-xf.yaml": ("ai-xf: \"0.4\"\nfederation: fresh\nvocabularies:\n  types: ./types.json\n"
                              "  rels: ./rels.json\nbundles:\n  - namespace: x\n    source: path\n    path: ./x\n"
                              "  - namespace: y\n    source: path\n    path: ./y\n"),
}


class FreshnessStats(unittest.TestCase):
    """`--stats` freshness and vocabulary numbers (E8). Informational only:
    none of them may change pass/fail."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = Path(tempfile.mkdtemp(prefix="ai-xf-fresh-"))
        for rel, text in FRESHNESS_FILES.items():
            (cls.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (cls.tmp / rel).write_text(text, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def stats(self, bundle: str, use_pyyaml: bool = False) -> tuple[int, dict]:
        rc, data = run_validator([bundle, "--federation", "federation.ai-xf.yaml", "--stats", "--json"],
                                 use_pyyaml=use_pyyaml, cwd=self.tmp)
        return rc, data["stats"]

    def test_unindexed_and_edges_into_retired(self):
        rc, st = self.stats("x")
        self.assertEqual(rc, 0)                       # never affects pass/fail
        fr = st["freshness"]
        self.assertEqual(fr["unindexed"], ["concepts/ghost.md"])
        self.assertEqual(fr["edges_into_retired"], 1)    # live -> gone; `supersedes` is not counted
        self.assertEqual(fr["edges_into_redirects"], 1)  # live -> old (superseded-by new)
        self.assertTrue(any("listed in no index.md" in f for f in st["flags"]))

    def test_no_index_means_unknown_not_zero(self):
        _, st = self.stats("y")
        self.assertIsNone(st["freshness"]["unindexed"])

    def test_cross_bundle_edge_into_retired(self):
        _, st = self.stats("y")
        self.assertEqual(st["federation"]["cross_bundle_edges_into_retired"], 1)

    def test_vocabulary_unused_by_pair(self):
        _, st = self.stats("x")
        vu = st["federation"]["vocabulary"]
        self.assertEqual(vu["types_unused"], ["Policy"])
        # 6 names, 4 pairs; references/referenced-by and supersedes are used,
        # so only has-part/part-of is unused. relates-to is used too.
        self.assertEqual(vu["rel_pairs_declared"], 4)
        self.assertEqual(vu["rel_pairs_unused"], ["has-part/part-of"])

    def test_parsers_agree(self):
        if not HAS_UV:
            self.skipTest("uv not available")
        for b in ("x", "y"):
            self.assertEqual(self.stats(b), self.stats(b, use_pyyaml=True))


class LinkForms(unittest.TestCase):
    """Link forms the spec allows but the v0.4.2 validator mishandled (found
    while testing E8): a concept file moved with its id unchanged (§5.2), a
    bundle-relative path in `to` (§6.1), and markdown destinations written
    with angle brackets, a title, or %-encoding. Core findings, not stats."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-xf-links-"))
        shutil.copytree(EXAMPLES, self.tmp / "ex")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def validate(self, use_pyyaml: bool = False) -> tuple[int, dict]:
        return run_validator([str(self.tmp / "ex"), "--level", "3", "--stats", "--json"], use_pyyaml=use_pyyaml)

    def edit(self, rel: str, old: str, new: str) -> None:
        f = self.tmp / "ex" / rel
        text = f.read_text(encoding="utf-8")
        self.assertIn(old, text, rel)
        f.write_text(text.replace(old, new), encoding="utf-8")

    def move_orders_table(self) -> None:
        """What a curator does: move the file, keep the id, fix the body links."""
        ex = self.tmp / "ex"
        (ex / "concepts" / "data").mkdir()
        (ex / "concepts" / "orders-table.md").rename(ex / "concepts" / "data" / "orders.md")
        for f in ex.rglob("*.md"):
            t = f.read_text(encoding="utf-8")
            t2 = t.replace("./concepts/orders-table.md", "./concepts/data/orders.md") \
                  .replace("(./orders-table.md)", "(./data/orders.md)")
            if t2 != t:
                f.write_text(t2, encoding="utf-8")

    def test_moved_file_keeps_id_and_passes(self):
        self.move_orders_table()
        rc, data = self.validate()
        self.assertEqual(rc, 0, data["findings"])
        self.assertEqual(data["findings"], [])
        self.assertEqual(data["stats"]["freshness"]["unindexed"], [])

    def test_bundle_relative_path_in_to(self):
        self.edit("concepts/payment-service.md", "to: orders-table", "to: concepts/orders-table.md")
        rc, data = self.validate()
        self.assertEqual(rc, 0)
        self.assertEqual(find_findings(data["findings"], "does not resolve"), [])

    def test_link_destination_forms(self):
        self.edit("index.md", "(./concepts/orders-table.md)", "(<./concepts/orders-table.md> \"Orders\")")
        self.edit("index.md", "(./people/jane-doe.md)", "(./people/jane%2Ddoe.md)")
        self.edit("concepts/payment-service.md", "(./orders-table.md)", "(<./orders-table.md>)")
        rc, data = self.validate()
        self.assertEqual(rc, 0, data["findings"])
        self.assertEqual(data["stats"]["freshness"]["unindexed"], [])

    def test_path_form_edge_into_retired_is_counted(self):
        # payments-api is a merge tombstone (has a successor): a redirect, by id or by path
        _, before = self.validate()
        # payment-service is itself deprecated, and edges from retired concepts are not counted
        self.edit("concepts/payment-service-v2.md", "to: orders-table", "to: concepts/payments-api.md")
        self.edit("concepts/payment-service-v2.md", "(./orders-table.md)", "(./payments-api.md)")
        _, after = self.validate()
        self.assertEqual(after["stats"]["freshness"]["edges_into_redirects"],
                         before["stats"]["freshness"]["edges_into_redirects"] + 1)

    def test_parsers_agree(self):
        if not HAS_UV:
            self.skipTest("uv not available")
        self.move_orders_table()
        self.assertEqual(normalize_bundle_field(self.validate()[1]),
                         normalize_bundle_field(self.validate(use_pyyaml=True)[1]))


def write_tree(root: Path, files: dict) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


class TimestampsAliasesAndRetirement(unittest.TestCase):
    """v0.4.3: timestamps are datetimes with an offset (OKF PR #6, §5.6); an
    unknown id falls back to `aliases` (§6.6); an unresolved link no longer
    claims to be "not-yet-written"; and two stats from existing fields:
    replaced-but-live concepts and sources changed since verification."""

    FILES = {
        "t/manifest.ai-xf.yaml": "ai-xf: \"0.4\"\nname: t\nnamespace: t\n",
        "t/concepts/dated.md": ("---\ntype: Concept\nid: dated\nstale_after: 2026-01-01\n"
                                "verified:\n- by: human:x\n  at: 2026-01-01T09:00:00\n---\n\nx\n"),
        "t/concepts/timed.md": ("---\ntype: Concept\nid: timed\nstale_after: 2099-01-01T00:00:00+01:00\n"
                                "generated:\n  by: human:x\n  at: 2026-02-01T00:00:00Z\n"
                                "verified:\n- by: human:x\n  at: '2026-01-01T09:00:00Z'\n"
                                "sources:\n- resource: https://example.com/a\n  last_modified: 2026-03-01T00:00:00Z\n---\n\nx\n"),
        "t/concepts/new.md": ("---\ntype: Concept\nid: new\nstatus: stable\naliases: [old-name]\n"
                              "links:\n- rel: supersedes\n  to: old\n---\n\n[Old](./old.md)\n"),
        "t/concepts/old.md": "---\ntype: Concept\nid: old\nstatus: stable\n---\n\nStill live.\n",
        "t/concepts/linker.md": ("---\ntype: Concept\nid: linker\nstatus: stable\nlinks:\n"
                                 "- rel: relates-to\n  to: old-name\n- rel: relates-to\n  to: nowhere\n---\n\n"
                                 "[New](./new.md) [Nowhere](./nowhere.md)\n"),
        "u/manifest.ai-xf.yaml": "ai-xf: \"0.4\"\nname: u\nnamespace: u\n",
        "u/concepts/far.md": ("---\ntype: Concept\nid: far\nstatus: stable\nlinks:\n- rel: references\n"
                              "  to: t/old-name\n---\n\nx\n"),
        "federation.ai-xf.yaml": ("ai-xf: \"0.4\"\nfederation: v043\nbundles:\n  - namespace: t\n    source: path\n"
                                  "    path: ./t\n  - namespace: u\n    source: path\n    path: ./u\n"),
    }

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = Path(tempfile.mkdtemp(prefix="ai-xf-v043-"))
        write_tree(cls.tmp, cls.FILES)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_t(self, *extra, use_pyyaml=False, bundle="t"):
        return run_validator([bundle, "--level", "2", "--stats", "--json", "--today", "2026-06-01", *extra],
                             use_pyyaml=use_pyyaml, cwd=self.tmp)

    def test_date_only_and_offsetless_timestamps_warn(self):
        rc, d = self.run_t()
        self.assertEqual(rc, 0)
        msgs = [f["message"] for f in d["findings"] if f["file"] == "concepts/dated.md"]
        self.assertTrue(any(m.startswith("`stale_after: 2026-01-01`") for m in msgs), msgs)
        self.assertTrue(any(m.startswith("`verified[0].at:") for m in msgs), msgs)
        self.assertEqual([f for f in d["findings"] if f["file"] == "concepts/timed.md"], [])

    def test_staleness_compares_instants(self):
        _, d = self.run_t()
        self.assertEqual(d["stats"]["staleness"]["past_stale_after"], 1)   # dated only

    def test_alias_fallback_and_wording(self):
        _, d = self.run_t()
        msgs = [f["message"] for f in d["findings"] if f["file"] == "concepts/linker.md"]
        self.assertIn("links[0] `to: old-name` resolves only as an alias of `new` (§6.6) — link to `new`", msgs)
        self.assertTrue(any("`to: nowhere` does not resolve (tolerated:" in m for m in msgs), msgs)
        self.assertFalse(any("not-yet-written" in m for m in msgs))
        self.assertFalse(any(f["severity"] == "error" for f in d["findings"]))   # alias target mirrored

    def test_qualified_alias_fallback(self):
        _, d = self.run_t("--federation", "federation.ai-xf.yaml", bundle="u")
        msgs = [f["message"] for f in d["findings"]]
        self.assertIn("links[0] `to: t/old-name` resolves only as an alias of `t/new` (§6.6) — link to `t/new`", msgs)
        self.assertEqual(d["stats"]["federation"]["qualified_refs"], {"resolved": 1, "unresolved": 0})

    def test_replaced_but_live_and_source_changed(self):
        _, d = self.run_t()
        fr = d["stats"]["freshness"]
        self.assertEqual(fr["superseded_not_deprecated"], ["old"])
        self.assertEqual(fr["sources_changed_since_verified"], ["timed"])
        self.assertEqual(fr["changed_since_verified"], ["timed"])   # generated after its check

    def test_parsers_agree(self):
        if not HAS_UV:
            self.skipTest("uv not available")
        for b, extra in (("t", ()), ("u", ("--federation", "federation.ai-xf.yaml"))):
            self.assertEqual(normalize_bundle_field(self.run_t(*extra, bundle=b)[1]),
                             normalize_bundle_field(self.run_t(*extra, bundle=b, use_pyyaml=True)[1]))


class DeclaredRels(unittest.TestCase):
    """A custom rel the bundle declares in its own `vocabularies.rels` (§9.3),
    or the declared `inverse` of one, is not reported as non-core. Found by
    Longview, whose seven declared rels warned on every use (E12)."""

    REL = ("---\ntype: Concept\nid: {id}\nstatus: stable\nlinks:\n"
           "- rel: released-by\n  to: other\n- rel: released\n  to: other\n- rel: sues\n  to: other\n---\n\n"
           "[Other](./other.md)\n")

    def make(self, vocab_ref: str) -> Path:
        import tempfile
        root = Path(tempfile.mkdtemp(prefix="ai-xf-rels-"))
        self.addCleanup(shutil.rmtree, root, True)
        write_tree(root, {
            "manifest.ai-xf.yaml": f"ai-xf: \"0.4\"\nname: r\nnamespace: r\nvocabularies:\n  types: ./vocab/types.json\n  rels: {vocab_ref}\n",
            "vocab/types.json": '{"version": 1, "values": [{"name": "Concept"}]}',
            "vocab/rels.json": '{"version": 1, "values": [{"name": "released-by", "inverse": "released", "definition": "x"}]}',
            "concepts/a.md": self.REL.format(id="a"),
            "concepts/other.md": "---\ntype: Concept\nid: other\nstatus: stable\n---\n\nx\n",
        })
        return root

    def non_core(self, root: Path, use_pyyaml: bool = False) -> list[str]:
        _, d = run_validator([str(root), "--level", "3", "--json"], use_pyyaml=use_pyyaml)
        return sorted(re.search(r"non-core rel `([^`]+)`", f["message"]).group(1)
                      for f in d["findings"] if "non-core rel" in f["message"])

    def test_declared_rel_and_inverse_do_not_warn(self):
        self.assertEqual(self.non_core(self.make("./vocab/rels.json")), ["sues"])

    def test_remote_vocabulary_is_not_fetched(self):
        self.assertEqual(self.non_core(self.make("https://example.com/rels.json")), ["released", "released-by", "sues"])

    def test_parsers_agree(self):
        if not HAS_UV:
            self.skipTest("uv not available")
        root = self.make("./vocab/rels.json")
        self.assertEqual(self.non_core(root), self.non_core(root, use_pyyaml=True))


if __name__ == "__main__":
    unittest.main()
