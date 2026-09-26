# Results

Filled in per experiment as it runs. Each entry: date, versions, the numbers
against the plan's pass criteria, and the decision the gate produced.

## Phase 0: fixtures

**2026-09-26.** Built by a Sonnet agent from the plan §1; corrected by hand for two plan errors.

- `data-eng` (5 concepts) and `household` (5 concepts) both PASS `aix-validate --level 3` with zero errors and zero warnings. `examples/` (`example-payments`) unchanged, still PASS.
- Deliberate collisions in place: `orders-table` (example-payments vs data-eng) and `customers` (data-eng vs household).
- `vocab/types-v1.json` (7 types) and `vocab/rels-v1.json` (28 rels: the §6.2 core vocabulary plus the registered extension rels).
- `questions.yaml`: 20 questions, 12 cross-bundle, 8 single-bundle, 4 targeting a colliding id.
- `--stats` on data-eng: 1 open contradiction, update:creation 0.6; on household: 1 of 5 past `stale_after` (deliberate), update:creation 0.2.

**Plan errors found by building the fixtures (both fixed):**
1. The plan's manifest named the example bundle `payments`; its existing manifest says `example-payments`, and §9.1 forbids renaming a namespace. Fixtures now use `example-payments`.
2. The plan's manifest used `./fixtures/<bundle>` paths while placing the file inside `fixtures/`. Paths are now `./<bundle>`.

**Observation for E1/E2:** without `--federation`, the v0.3 validator emits *no* finding at all for a well-formed `namespace/id` reference that does not resolve locally, not even the tolerated warning. Silence, not tolerance. This is the baseline E1's M1 is measured against.

**Judgement call recorded:** data-eng's claim contradicts a `Policy`, not another `Claim` (spec allows it; kept to diversify contradiction shapes).

**Gate 0: passed.** Question set still to be reviewed by the author before Phase 1 results are read.

## E1: transport and the root manifest

**2026-09-26.** git 2.54.0 (Apple), Python 3.14. Three consumer layouts built from local bare remotes of the three fixture bundles; `data-eng` (and `payments` for M2) validated with `--federation` in each. Built by a Sonnet agent; re-run by the author (`e1-transport/run.sh`, exit 0).

| Measure (plan target) | (a) submodules, manifest generated from `.gitmodules` | (b) subtree, no manifest, naive root discovery | (c) subtree + hand-written manifest |
|---|---|---|---|
| M1 qualified refs resolved (100 % where a manifest exists; expected < 100 % for b) | 2/2 | **2/2** | 2/2 |
| M2 rename survives (id unchanged) (yes, all) | yes | yes | yes |
| M3 exact commit per bundle nameable (yes for a, c; no for b) | yes, submodule SHAs | **no** (`ref: null`) | yes, from the `git-subtree-split` trailer |
| M4 rebuild from clean clone byte-identical (yes) | yes | yes | yes |

**The plan's hypothesis was wrong on M1.** Resolution never needed a manifest: `git subtree add --squash` copies each bundle's own `manifest.aix.yaml`, so a scan for that file recovers every namespace, and the validator resolves all references. What layout (b) loses is **provenance** (M3): the pre-squash commit is only recoverable from a git trailer that nothing AIX-shaped knows to read.

**Gate 1 decision this supports:**
- A federation manifest is **required for provenance, not for resolution**. v0.4 should say: a consumer MAY discover bundle roots by scanning for `manifest.aix.yaml`; it MUST hold a `federation.aix.yaml` (or equivalent, `.gitmodules` qualifies) to claim reproducible provenance, and the `ref` per bundle is the field that matters.
- `.gitmodules` + `git submodule status` was enough to *generate* a complete manifest, so the spec can describe `federation.aix.yaml` as derivable from submodules rather than competing with them.
- `subdir` for `source: git` entries must be the bundle root relative to the repo holding the manifest (`bundles/<ns>`, not `.`): the plan's sketch was wrong there too.

**Judgement calls recorded:** `protocol.file.allow=always` needed for local-path subtrees on this git; bash 3.2 compatibility (no associative arrays).

## E2: identity resolution under collision

**2026-09-26.** Validator gained `--federation <manifest>`, the explicit `aix://namespace/id` form, and the Foam rule (own bundle first, then other namespaces alphabetically, always with a warning naming every candidate). Built by a Sonnet agent; re-run and checked by the author. `python3 3.13`, both the stdlib fallback parser and PyYAML.

Synthetic collision suite (`e2-resolution/`, bundles a, b, c; `test_resolution.py`, 10 tests):

| Measure (plan target) | Result |
|---|---|
| 1. Silent wrong resolutions (0) | **0** |
| 2. Warnings for every ambiguous unqualified reference (100 %) | **2 of 2** (`only-a` single candidate; `shared` two candidates, resolved to `a`, both named) |
| 3. Explicit `aix://b/shared` resolves without warning (100 %) | **yes**; qualified `a/only-a` likewise |
| 4. Regression on `examples/` without the flag (0 new findings) | **byte-identical** JSON and text, all levels, both parsers |
| Extra | same-bundle qualified ref `c/something` → error (§9.2); unresolved `b/missing` → tolerated warning |

Real fixtures under `fixtures/federation.aix.yaml`: all three bundles PASS Level 3 with zero findings; federation stats report the two deliberate collisions (`orders-table`: data-eng/example-payments; `customers`: data-eng/household) and 2 qualified refs resolved, 0 unresolved. The fixtures contain no *unqualified* cross-bundle references, by design, so the Foam rule is exercised only by the synthetic suite.

**Decisions the gate can now take:**
- Resolution order for §9.2: own bundle wins unconditionally and silently; otherwise other namespaces alphabetically with a mandatory warning. Confirmed workable.
- `aix://namespace/id` as the explicit authoring form: implemented, mirrors a `to:` for §6.4, and the Level 3 well-formedness check accepts it. Ready for v0.4 text.
- Body-link mirroring: a Foam-resolved reference is treated as cross-bundle (SHOULD mirror, not MUST). Recorded as a judgement call; v0.4 should say so.
- `source: git` in the federation manifest is *provenance only* in this experiment (no fetching); E1 measures whether that is enough.

## E3: cross-bundle index

_pending_

## E4: serving via MCP tools

**2026-09-26.** `mcp` SDK 2.2.0 (v2 API), Python 3.11 under uv. Tools-only stdio server over `fixtures/federation.aix.yaml` (`list_bundles`, `list_concepts`, `search`, `get`), reusing the validator's own frontmatter and federation-loading code so resolution matches E1/E2 exactly; each concept also exposed as an `aix://namespace/id` resource for the VS Code side-test. Built by a Sonnet agent; smoke test (15 checks) and deterministic pass re-run by the author.

**Payload contract held end to end:** every concept-shaped response carries `namespace`, `id` and `ref: "namespace/id"`; `get` returns frontmatter verbatim including `links` (the federation-qualified `example-payments/orders-table` link survives) and `bundle_ref`; unknown namespace or id returns a tool error, never a crash.

**Deterministic mode** (search → top hit → get; a retrieval and identity floor, *not* an answer-quality measure):

| | Correct |
|---|---|
| Overall | 18 / 20 |
| Cross-bundle (12) | 10 / 12 |
| Collision questions (4) | **4 / 4** |
| Single-bundle (8) | 8 / 8 |

The two misses (q09, q11) need a second hop that one search-then-get cannot make; a tool-using agent can.

**LLM mode (the plan's measures 1 and 2): not run.** No `ANTHROPIC_API_KEY` in the environment and a nested Claude Code session is off-limits here. The harness is written (tool-use loop, max 8 calls per question, `CITES:` parsing, second-call grader, model `claude-sonnet-4-5`) and runs with `./run.sh` once a key is set. The Claude Code and VS Code manual side-tests are specified in `e4-mcp/MANUAL.md`.

**Findings not in the plan:**
- `mcp` v2 silently drops structured output for a bare `-> dict` annotation; `-> dict[str, object]` is needed. Recorded for anyone building on this SDK version.
- A `ref: 1408535` in the federation manifest parses as an integer under PyYAML. Fixture now quotes it; v0.4 §9.5 should say `ref` is a string.

**Gate 3 decision this supports (provisionally, pending the LLM run):** the serving payload contract is `namespace` + `id` + `ref` on every item, verbatim frontmatter on `get`, and the bundle's provenance `ref` alongside. Resources are exposable for free but nothing in this experiment depended on them.

## E5: trust survival through transports

_pending_

## E6: integrity (ORAS + Cosign)

**2026-09-26.** oras 1.3.4, cosign 3.1.3, local `registry:2` over plain HTTP (the GitHub token lacks `write:packages`; keyless OIDC needs a browser login, so key-based signing with a throwaway pair). Built by a Sonnet agent; re-run by the author (`e6-oci/run.sh`, exit 0, container cleaned up).

| Measure (plan target) | Result |
|---|---|
| 1a. Verify untouched artifact (PASS) | **PASS**, by digest |
| 1b. Verify after tampering one frontmatter value and re-pushing to the same tag (FAIL) | **FAIL**: "no signatures found" for the new digest |
| 1c. Verify the original by its original digest after the tamper (PASS) | **PASS**: content-addressed; old manifest and signature untouched |
| Pulled original still validates | PASS Level 3, 0 findings |
| 2. Producer flow (package + push + sign) | 1.4–1.8 s |
| 2. Consumer flow (pull + verify + unpack) | 0.4–0.6 s |
| 2. First-time consumer commands | 4 (`brew install` once, `oras pull`, `cosign verify`, `tar -xzf`) plus one out-of-band step: obtaining the producer's public key |

**Two findings not in the plan:**
- `oras push` stamps `org.opencontainers.image.created` with wall-clock time, so the *manifest* digest of byte-identical content differs on every push until `created` is pinned. `run.sh` pins it to the bundle's `generated` timestamp; the digest is then reproducible across clean runs. v0.4 guidance must say this or every "reproducible digest" claim is false by default.
- The reference OCI-skills spec separates `artifactType` from the layer `mediaType` and defines a structured config blob; E6 used one type for both and the empty config. A v0.4 appendix should adopt the separation.

**Measure 3, the `digest` question: answered against the plan.** `manifest.aix.yaml` must **not** carry its own digest: the manifest is inside the hashed layer, so writing the digest changes the digest. The OCI ecosystem keeps signatures and referrers outside the artifact for the same reason. The digest belongs in the document that *references* the bundle: add `source: oci` to `federation.aix.yaml` with `ref` (registry reference) and `digest`, parallel to `source: git` + `ref: <commit>`.

**Gate 4 decision this supports:** v0.4 mentions OCI distribution as a non-normative appendix (artifact type, pinned `created`, key or keyless signing left to the producer) and adds `source: oci` to §9.5. No `digest` field on `manifest.aix.yaml`.
