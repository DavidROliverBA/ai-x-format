#!/usr/bin/env python3
"""Tests for ai-x-validate.py's --federation identity resolution (E2).

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
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
VALIDATOR = REPO_ROOT / "tools" / "ai-x-validate.py"
EXAMPLES = REPO_ROOT / "examples"
BUNDLE_C = HERE / "bundle-c"
FEDERATION_YAML = HERE / "federation.ai-x.yaml"
BASELINE_FILE = HERE / "baseline-examples-level2.json"

HAS_UV = shutil.which("uv") is not None


def run_validator(args: list[str], use_pyyaml: bool = False, cwd: Path = REPO_ROOT) -> tuple[int, dict]:
    """Run ai-x-validate.py with --json and return (returncode, parsed_json)."""
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
    qualified reference, a resolving explicit ai-x:// reference, an illegal
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
        # cleanly (qualified `a/only-a` and explicit `ai-x://b/shared`) must
        # produce no finding at all — links[2] and links[3] are absent.
        self.assertEqual(find_findings(findings, "links[2]"), [])
        self.assertEqual(find_findings(findings, "links[3]"), [])
        self.assertEqual(find_findings(findings, "a/only-a` qualified"), [])
        self.assertEqual(find_findings(findings, "ai-x://b/shared"), [])

    def test_resolution_stdlib_parser(self):
        rc, data = run_validator(["bundle-c", "--federation", "federation.ai-x.yaml", "--json"], cwd=HERE)
        self.assertEqual(rc, 1)  # the same-bundle-qualification case is an error
        self.assertFalse(data["passed"])
        self.assertEqual(data["achieved_level"], 1)
        self._check(data["findings"])

    def test_resolution_pyyaml_parser(self):
        if not HAS_UV:
            self.skipTest("uv not available")
        rc, data = run_validator(
            ["bundle-c", "--federation", "federation.ai-x.yaml", "--json"], use_pyyaml=True, cwd=HERE)
        self.assertEqual(rc, 1)
        self.assertFalse(data["passed"])
        self._check(data["findings"])

    def test_stdlib_and_pyyaml_agree_on_bundle_c(self):
        if not HAS_UV:
            self.skipTest("uv not available")
        _, a = run_validator(["bundle-c", "--federation", "federation.ai-x.yaml", "--json"], cwd=HERE)
        _, b = run_validator(
            ["bundle-c", "--federation", "federation.ai-x.yaml", "--json"], use_pyyaml=True, cwd=HERE)
        self.assertEqual(normalize_bundle_field(a), normalize_bundle_field(b))

    def test_federation_provenance_in_json(self):
        _, data = run_validator(["bundle-c", "--federation", "federation.ai-x.yaml", "--json"], cwd=HERE)
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
            ["bundle-c", "--federation", "federation.ai-x.yaml", "--stats", "--json"], cwd=HERE)
        fed_stats = data["stats"]["federation"]
        self.assertEqual(fed_stats["bundles_held"], 3)
        self.assertEqual(fed_stats["concepts_per_namespace"], {"a": 2, "b": 2, "c": 2})
        self.assertEqual(fed_stats["colliding_ids"], {"shared": ["a", "b"]})
        self.assertEqual(fed_stats["qualified_refs"], {"resolved": 2, "unresolved": 1})
        self.assertEqual(fed_stats["unqualified_cross_bundle_resolutions"], 2)

    def test_provenance_report_text_mode(self):
        cmd = [sys.executable, str(VALIDATOR), "bundle-c", "--federation", "federation.ai-x.yaml"]
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
            ["bundle-c", "--federation", "federation.ai-x.yaml", "--stats", "--json"], cwd=HERE)
        collisions = data["stats"]["federation"]["colliding_ids"]
        self.assertNotIn("linker", collisions)
        self.assertNotIn("something", collisions)


if __name__ == "__main__":
    unittest.main()
