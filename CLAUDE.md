# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

AI-XF is a **specification** rather than an application: a markdown + YAML-frontmatter format for curated knowledge bundles, defined as a strict superset of Google's Open Knowledge Format (OKF) v0.2. The deliverables are documents, a reference validator and evidence:

- `SPEC.md`: the normative spec (v0.4 draft). The changelog is in §13.
- `CURATOR.md`: non-normative curation policy.
- `examples/`: the worked bundle. It must pass at Level 3, and it doubles as the `payments` namespace in the experiments.
- `tools/ai-xf-validate.py`: the reference validator and the only real code.
- `experiments/`: runnable evidence (E1–E7) behind the v0.4 federation rules, summarised in `experiments/RESULTS.md`.

## Commands

```bash
python3 tools/ai-xf-validate.py examples/ --level 3 --stats      # the gate for any spec or validator change
python3 tools/ai-xf-validate.py <bundle> --json                  # machine-readable findings
python3 tools/ai-xf-validate.py experiments/fixtures/data-eng --level 3 \
  --federation experiments/fixtures/federation.ai-xf.yaml        # cross-bundle resolution

# Validator test suite (unittest): run under both YAML parsers
cd experiments/e2-resolution && python3 -m unittest test_resolution -v
cd experiments/e2-resolution && uv run -q --with pyyaml python3 -m unittest test_resolution -v
cd experiments/e2-resolution && python3 -m unittest test_resolution.FederationResolution   # one test class

experiments/e2-resolution/run.sh     # full E2 run, including the stdlib-vs-PyYAML diff and the examples/ baseline check
```

Each experiment directory has its own `run.sh`. Some need external tools: `uv`, qmd (E3), an MCP client (E4), ORAS + Cosign (E6), MyVault's exporter (E8) and bun for `bunx knowledgex` (E9). Scratch output goes to `/tmp` or gitignored paths.

## How the validator works

`tools/ai-xf-validate.py` is a single self-contained file with no required dependencies. It uses PyYAML when available and otherwise falls back to a built-in mini YAML parser (`_mini_yaml` / `_parse_block`) that covers only the YAML subset AI-XF frontmatter uses. **Both parsers must produce identical results.** E2's `run.sh` diffs their JSON output, and also diffs `examples/` against `experiments/e2-resolution/baseline-examples-level2.json`. A change that alters the validator's output for `examples/` must update that baseline deliberately. v0.4.1 fixed a fallback-parser bug in which column-0 lists were dropped, so test new YAML shapes under both parsers.

The structure follows the conformance ladder (Level 0 OKF-compatible → 1 Core → 2 Full → 3 Federated). `validate()` accumulates `Finding`s (error or warning) at or below the target level. `collect_stats()` provides `--stats`, which reports curation health and **never affects pass/fail**. `load_federation()` builds a namespace → id index across the bundles listed in a `federation.ai-xf.yaml`. `source: git` entries resolve as local paths relative to the repo root, and the validator never fetches anything. The vocabularies (`CORE_RELS`, `REL_INVERSES`, `LINK_STATES`, `OUTCOMES`, `LOG_WORDS`, `OKF_TRUST_FIELDS`, …) are module-level constants and must stay in step with `SPEC.md` §6, §7 and §10.

Federation resolution rule (SPEC §9.2): the bundle's own namespace is tried first, then other namespaces alphabetically. A cross-bundle resolution always produces a warning and is never silent. A reference qualified with the bundle's own namespace is an error.

## Rules for changing the spec

- **OKF compatibility is the hard constraint.** Every AI-XF bundle must remain a valid OKF bundle. AI-XF-only data lives in frontmatter keys that OKF consumers ignore (`id`, `links`, `provenance`, `media`, `aliases`). Every same-bundle typed link must be mirrored by a plain markdown body link. When OKF adopts a feature, AI-XF retires its own version in favour of OKF's definition.
- **Format and policy stay separate.** `SPEC.md` says what a bundle can express. Behavioural guidance belongs in `CURATOR.md` and never becomes a MUST.
- **Changes must be backward compatible.** Deprecated fields and old spellings (`aix`/`ai-x` schemes and manifest names, `status: active`, `sources[].uri`, `agent:`/`pipeline:` actors, the v0.1 `provenance` keys) are still read with a warning and are never written. Keep that distinction when renaming anything.
- A normative change needs a §13 changelog entry, and `examples/` must still pass at Level 3. v0.4 rules were each tested in `experiments/` before they were written into the spec; keep evidence-first changes to that pattern and record the numbers in `RESULTS.md` and the experiment's results file.
- The experiment plan referenced in `experiments/README.md` lives in the author's MyVault (`docs/plans/2026-09-26-federation-experiments-plan.md`), not in this repo.
- The project is called AI-XF. Earlier names were AIX (up to v0.3) and AI-X (v0.4.0–0.4.1). Use AI-XF in new text. The naming notice in `README.md` exists for trademark reasons, so keep it.
- UK English throughout (`generalises`, `artefacts`).
