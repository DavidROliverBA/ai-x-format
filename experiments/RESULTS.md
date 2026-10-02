# Results

Filled in per experiment as it runs. Each entry: date, versions, the numbers
against the plan's pass criteria, and the decision the gate produced.

## Phase 0: fixtures

**2026-09-26.** Built by a Sonnet agent from the plan §1; corrected by hand for two plan errors.

- `data-eng` (5 concepts) and `household` (5 concepts) both PASS `ai-xf-validate --level 3` with zero errors and zero warnings. `examples/` (`example-payments`) unchanged, still PASS.
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

**The plan's hypothesis was wrong on M1.** Resolution never needed a manifest: `git subtree add --squash` copies each bundle's own `manifest.ai-xf.yaml`, so a scan for that file recovers every namespace, and the validator resolves all references. What layout (b) loses is **provenance** (M3): the pre-squash commit is only recoverable from a git trailer that nothing AI-XF-shaped knows to read.

**Gate 1 decision this supports:**
- A federation manifest is **required for provenance, not for resolution**. v0.4 should say: a consumer MAY discover bundle roots by scanning for `manifest.ai-xf.yaml`; it MUST hold a `federation.ai-xf.yaml` (or equivalent, `.gitmodules` qualifies) to claim reproducible provenance, and the `ref` per bundle is the field that matters.
- `.gitmodules` + `git submodule status` was enough to *generate* a complete manifest, so the spec can describe `federation.ai-xf.yaml` as derivable from submodules rather than competing with them.
- `subdir` for `source: git` entries must be the bundle root relative to the repo holding the manifest (`bundles/<ns>`, not `.`): the plan's sketch was wrong there too.

**Judgement calls recorded:** `protocol.file.allow=always` needed for local-path subtrees on this git; bash 3.2 compatibility (no associative arrays).

## E2: identity resolution under collision

**2026-09-26.** Validator gained `--federation <manifest>`, the explicit `ai-xf://namespace/id` form, and the Foam rule (own bundle first, then other namespaces alphabetically, always with a warning naming every candidate). Built by a Sonnet agent; re-run and checked by the author. `python3 3.13`, both the stdlib fallback parser and PyYAML.

Synthetic collision suite (`e2-resolution/`, bundles a, b, c; `test_resolution.py`, 10 tests):

| Measure (plan target) | Result |
|---|---|
| 1. Silent wrong resolutions (0) | **0** |
| 2. Warnings for every ambiguous unqualified reference (100 %) | **2 of 2** (`only-a` single candidate; `shared` two candidates, resolved to `a`, both named) |
| 3. Explicit `ai-xf://b/shared` resolves without warning (100 %) | **yes**; qualified `a/only-a` likewise |
| 4. Regression on `examples/` without the flag (0 new findings) | **byte-identical** JSON and text, all levels, both parsers |
| Extra | same-bundle qualified ref `c/something` → error (§9.2); unresolved `b/missing` → tolerated warning |

Real fixtures under `fixtures/federation.ai-xf.yaml`: all three bundles PASS Level 3 with zero findings; federation stats report the two deliberate collisions (`orders-table`: data-eng/example-payments; `customers`: data-eng/household) and 2 qualified refs resolved, 0 unresolved. The fixtures contain no *unqualified* cross-bundle references, by design, so the Foam rule is exercised only by the synthetic suite.

**Decisions the gate can now take:**
- Resolution order for §9.2: own bundle wins unconditionally and silently; otherwise other namespaces alphabetically with a mandatory warning. Confirmed workable.
- `ai-xf://namespace/id` as the explicit authoring form: implemented, mirrors a `to:` for §6.4, and the Level 3 well-formedness check accepts it. Ready for v0.4 text.
- Body-link mirroring: a Foam-resolved reference is treated as cross-bundle (SHOULD mirror, not MUST). Recorded as a judgement call; v0.4 should say so.
- `source: git` in the federation manifest is *provenance only* in this experiment (no fetching); E1 measures whether that is enough.

## E3: cross-bundle index

**2026-09-26.** qmd 2.8.3 in full hybrid mode (BM25 + embeddinggemma-300M vectors + Qwen3 reranker + qmd's own query-expansion model; ~2.1 GB of weights), versus a 200-line stdlib BM25 (`bm25.py`). Twenty questions, literal question text as the query, no tuning. Built by a Sonnet agent; re-run by the author. **qmd's hybrid mode is not deterministic** (LLM expansion and reranking vary run to run), so two runs are shown; BM25 is stable.

| Measure | (a) qmd, one collection per bundle | (b) qmd, one collection | (c) plain BM25 over the union, `namespace` as a field |
|---|---|---|---|
| Mean P@5, all 20 (agent run / author run) | 0.700 / 0.754 | 0.808 / 0.738 | 0.717 / 0.717 |
| Mean P@5, cross-bundle (12) | 0.653 / 0.715 | 0.764 / 0.688 | 0.667 / 0.667 |
| Mean P@5, single-bundle (8) | 0.771 / 0.812 | 0.875 / 0.812 | 0.792 / 0.792 |
| Collision top-hit correct (4) | 3/4 / **2/4** | 3/4 / 3/4 | **4/4 / 4/4** |
| Build time (excl. model download) | 2.9 s / 2.4 s | 2.5 s / 2.1 s | 0.0 s |
| Index on disk (excl. 2.1 GB shared weights) | 9.9 MB | 10 MB | 40 KB |

**The plan's hypothesis was wrong, twice.** It expected per-bundle collections (a) to match BM25 on the collision questions and the single collection (b) to fail some. In fact the only configuration that put the right `namespace/id` on top for all four collision questions, in both runs, was the plain BM25 that carries `namespace` as a document field. The hybrid ranker's gains on ordinary questions (a few points of P@5, inside its own run-to-run variance) did not extend to telling two same-named concepts apart.

**Why:** qmd collections *tag* documents in one shared index rather than partitioning it, so a collection is a label on a hit, not a constraint on ranking; and neither qmd configuration gives the ranker the namespace as a signal. BM25 (c) had `namespace` in the document, so the question's own vocabulary ("the payments team's view", "the household") selected the right one.

**Findings not in the plan:** qmd does not follow symlinks for a collection root, so (b) needed a materialised copy of the three bundles; namespace for (b) had to be recovered from the first path segment. Both are consumer-side plumbing the spec cannot fix.

**Gate 2 decision this supports:** AI-XF v0.4 does not specify an index. It recommends, non-normatively, that any index over a federation carry `namespace` and `id` as fields on every document and return `namespace/id` on every hit; "collection = namespace" is a convenient way to get that in tools that support collections, but it is the field, not the collection, that resolves collisions. A hybrid/LLM-reranked index is not a substitute for that field.

## E4: serving via MCP tools

**2026-09-26.** `mcp` SDK 2.2.0 (v2 API), Python 3.11 under uv. Tools-only stdio server over `fixtures/federation.ai-xf.yaml` (`list_bundles`, `list_concepts`, `search`, `get`), reusing the validator's own frontmatter and federation-loading code so resolution matches E1/E2 exactly; each concept also exposed as an `ai-xf://namespace/id` resource for the VS Code side-test. Built by a Sonnet agent; smoke test (15 checks) and deterministic pass re-run by the author.

**Payload contract held end to end:** every concept-shaped response carries `namespace`, `id` and `ref: "namespace/id"`; `get` returns frontmatter verbatim including `links` (the federation-qualified `example-payments/orders-table` link survives) and `bundle_ref`; unknown namespace or id returns a tool error, never a crash.

**Deterministic mode** (search → top hit → get; a retrieval and identity floor, *not* an answer-quality measure):

| | Correct |
|---|---|
| Overall | 18 / 20 |
| Cross-bundle (12) | 10 / 12 |
| Collision questions (4) | **4 / 4** |
| Single-bundle (8) | 8 / 8 |

The two misses (q09, q11) need a second hop that one search-then-get cannot make; a tool-using agent can.

**LLM mode (the plan's measures 1 and 2): not run, by decision (2026-09-26).** The author chose not to run it for v0.4; the harness stays in the repo for whoever does. The harness is written (tool-use loop, max 8 calls per question, `CITES:` parsing, second-call grader, model `claude-sonnet-4-5`) and runs with `./run.sh` once a key is set. The Claude Code and VS Code manual side-tests are specified in `e4-mcp/MANUAL.md`.

**Findings not in the plan:**
- `mcp` v2 silently drops structured output for a bare `-> dict` annotation; `-> dict[str, object]` is needed. Recorded for anyone building on this SDK version.
- A `ref: 1408535` in the federation manifest parses as an integer under PyYAML. Fixture now quotes it; v0.4 §9.5 should say `ref` is a string.

**Gate 3 decision this supports (payload contract only; answer quality unmeasured):** the serving payload contract is `namespace` + `id` + `ref` on every item, verbatim frontmatter on `get`, and the bundle's provenance `ref` alongside. Resources are exposable for free but nothing in this experiment depended on them.

## E5: trust survival through transports

**2026-09-26.** git 2.54, macOS openrsync, iCloud Drive (local daemon), PyYAML. The `examples/` bundle (10 files, 7 concepts, 15 distinct frontmatter keys) round-tripped through each transport and compared key-by-key with a strict rule: "preserved" means byte-identical text for that key. Built by a Sonnet agent; re-run by the author (`e5-transports/run.sh`, exit 0; iCloud scratch folder removed).

| Transport | Preserved | Normalised | Lost | Files byte-identical |
|---|---|---|---|---|
| (a) git init → commit → clone | 15 | 0 | 0 | 10/10 |
| (b) rsync -a | 15 | 0 | 0 | 10/10 |
| (c) iCloud Drive | 15 | 0 | 0 | 10/10 |
| (d) Knowledge Catalog via kcmd | skipped: no gcloud; the connector doc's own words quoted instead ("seven frontmatter keys are carried", "cross-links resolve to nothing", "first pull rewrites every frontmatter block") | | | |
| (e) PyYAML load → `safe_dump` (stand-in for any parse-and-rewrite tool) | 7 | 8 | 0 | 3/10 |

(e) per key: `type`, `id`, `title`, `status`, `stale_after`, `provenance`, `resource` preserved; `description` rewrapped; `tags`/`aliases` flow → block; `generated` timestamps re-emitted in PyYAML's style (same instant, different bytes: `Z` suffix parsed into a `datetime`); `sources`, `verified`, `links`, `media` re-indented and rewrapped. Frontmatter **comments are lost** on any YAML round trip; YAML has no slot for them.

**The rule, now with evidence:** trust survives *transport* (anything that moves bytes: 45 of 45 key checks preserved) and degrades under *ingestion* in proportion to how much of the schema the tool models. A tool that models all of it (PyYAML) only normalises; a tool that models seven of fifteen keys (kcmd, by its own documentation) drops the rest, including `verified`, `provenance`, contradiction state and `media`. "Seven keys carried" reads as coverage until it is held next to a fifteen-key bundle.

**Finding not in the plan:** a single `brctl status` read gave a false "synced" on iCloud immediately after the copy; the run now requires three consecutive clean polls. Recorded as a heuristic, not proof of server-side upload.

**Gate 2 decision this supports:** v0.4 states the rule in §7 and adds one consumer obligation, already implicit in §5.5 and §11.1: an ingesting tool MUST either round-trip unknown keys opaquely or document which keys it drops. The vault's `ai-xf-export` does not need a sidecar for file transports; a sidecar is only for chunking ingestion (Vertex-style), out of scope.

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

**Measure 3, the `digest` question: answered against the plan.** `manifest.ai-xf.yaml` must **not** carry its own digest: the manifest is inside the hashed layer, so writing the digest changes the digest. The OCI ecosystem keeps signatures and referrers outside the artifact for the same reason. The digest belongs in the document that *references* the bundle: add `source: oci` to `federation.ai-xf.yaml` with `ref` (registry reference) and `digest`, parallel to `source: git` + `ref: <commit>`.

**Gate 4 decision this supports:** v0.4 mentions OCI distribution as a non-normative appendix (artifact type, pinned `created`, key or keyless signing left to the producer) and adds `source: oci` to §9.5. No `digest` field on `manifest.ai-xf.yaml`.

## E7: a real federation (added after v0.4)

**2026-09-26.** Two bundles exported from the author's vault with `ai-xf-export/0.4`, each a local git repo: `psychology` (102 concepts, all `Concept`) and `ai-concepts` (63). Federated with `examples/` via `experiments/real-federation/federation.ai-xf.yaml`, federation-level vocabularies. Validated under both YAML parsers; identical results.

| | psychology | ai-concepts |
|---|---|---|
| Links declared | 417 | 172 |
| Targets not in own bundle (alone) | 109 | 100 |
| Of those, present in another held bundle | 1 id (`three-ms-of-ai`, linked twice) | 3 ids (`fermi-paradox`, `pc-mindset`, `productivity-dip-pattern`) |
| Federated: Foam-rule resolutions, each warned and named | **2** | **3** |
| Federated: still unresolved (targets outside every held bundle) | 107 | 97 |
| Id collisions across the two | 0 | 0 |
| Level 3 with federation vocab | PASS | PASS (1 vocab warning: a note with `type: concept`, lower-case) |
| `--stats` flag | 5 open contradictions, 0 resolved; **99 of 102 confidence labels `high`**, flagged | |

**What it showed that the fixtures could not:**
- The five real cross-bundle references are all *unqualified*: the exporter writes bare ids because the vault has no notion of namespace. The Foam rule caught every one, named the bundle, and asked the producer to qualify. Rule 5 of `CURATOR.md` in practice.
- 204 of 209 dangling targets point outside every held bundle (`overconfidence-effect` 34 times, `survivorship-bias` 23): the slices are too narrow, not the format. Federation exposes slice boundaries as a worklist.
- The confidence flag from E-series fired on real data, exactly as the compounding audit predicted.

**Bug found and fixed (v0.4.1):** the validator's fallback YAML parser dropped any `links:` list whose items sit at column 0, which is PyYAML's default dump style, so a bundle written by `ai-xf-export` validated *clean* under plain `python3` and showed 109 warnings under PyYAML. Silent drop in a validator; fixed, and both parsers now agree on every bundle in this repository. Also fixed: Level 3 required per-bundle `vocabularies` even when the federation declared them, contradicting §9.5.

## E8: freshness and drift (added after v0.4.2)

**2026-10-02.** Exploratory, no prior plan. Replays Isci's add / edit / delete stress test (Medium, Aug 2026) against `ai-xf-export/0.4` on copies of the vault's 102 psychology notes, federated with `ai-concepts`, under four producer modes. Detail in `e8-freshness/e8-results.md`.

| After rename + delete | inplace (today) | fresh rebuild | tombstone | stable id + tombstone |
|---|---|---|---|---|
| Active concepts with no source | **2** | 0 | 0 | 0 |
| Cross-bundle refs newly unresolved | 0 | **2**, worded "may be not-yet-written" | 0 | 0 |
| Validator | PASS, silent | PASS | PASS; `--stats` lists 2 retired, `Deprecation 2` | PASS; rename left no trace |

- **The exporter accumulates.** Deleted and renamed notes stay as `stable` concepts that links still resolve to; the validator is silent.
- **Bundle-only ghost detector:** a concept file not listed in the regenerated `index.md` caught 2/2 with 0 false positives.
- **§6.6 tombstones + §10.2 `Deprecation` fix deletion with no spec change.** Rename needs stable ids: with `slug:` pinned, it is a non-event.
- **"May be not-yet-written" was wrong 11 times in 12** on the real bundle (7 archived, 4 out-of-slice references, 1 unwritten). This revises E7: its most-linked dangling targets are retired concepts, not a too-narrow slice.
- **Schema layer:** a naive unused-vocabulary audit is mostly noise (8 of 13 unused rels are inverses unused by design). The real problem is collapse: 165 of 172 real concepts are `Concept`, while the vault's ten-value `conceptType` is dropped on export.
- **Gap:** SPEC §6.6 says consumers SHOULD fall back to `aliases` for an unknown id; the reference validator does not.

**Adopted the same day (no spec change):** the exporter now reconciles on re-export (tombstones, rename → `superseded-by` + alias, read-then-add `log.md`, `--pin-ids`, `conceptType` kept): 0 ghosts and 0 broken cross-bundle refs after rename + delete. Validator `--stats` gained `freshness` (concept files in no `index.md`; live edges into retired concepts and into redirects) and, with `--federation`, edges into other bundles' retired concepts and vocabulary unused by rel pair. On the pre-fix bundle it names both ghosts; on the post-fix one it reports 3 local and 1 cross-bundle edge into the retired concept. 15/15 tests under both parsers; `examples/` baseline unchanged.

**Edge cases (second round):** 12 exporter tests surfaced a rename-back bug (fixed), silent retirement of hand-written concepts (now warned) and a different-slice footgun (now refused without `--allow-mass-retire`). Validator probes surfaced two older core bugs: a concept file moved with its id unchanged **failed Level 3** (mirroring compared filenames with ids, against §5.2), and a bundle-relative `to:` path did not resolve (§6.1). Both fixed; findings unchanged on every existing bundle under both parsers; 20/20 tests. A real re-export into copies of both kb repos: 162 `Update`s (the new `conceptType` only), then a no-op.

**Went into v0.4.3:** the neutral "does not resolve" wording, the §6.6 `aliases` fallback in the validator (local and qualified), and a producer SHOULD in §6.6 that a concept leaving a bundle becomes a tombstone, with `CURATOR.md` rule 7. **Still open:** re-exporting the published kb repos.

## E9: interoperability with KnowledgeX (added after v0.4.2)

**2026-10-02.** Exploratory. `knowledgex@0.4.0`, the first third-party OKF producer tested. Detail in `e9-knowledgex/e9-results.md`.

| Direction | Result |
|---|---|
| KnowledgeX notebook → AI-XF validator | Level 0 PASS (both parsers); Level 1 fails on `id`/manifest, as expected. `--stats` misses both relationships: KnowledgeX writes top-level `supersedes:`/`contradicts:` lists of file names, AI-XF reads `links[]` |
| AI-XF `examples/` → KnowledgeX, nested as published | `kx check` passes, **search finds 0 notes** (flat notebooks only) |
| Flattened, bare-date timestamps (`f4031dc`) | **0 of 5** human-reviewed concepts read as human-reviewed |
| Flattened, v0.4.3 datetimes with events in order | **5 of 5**, matching AI-XF's own reading |

- **The trust loss is about ordering, isolated by two controls:** a bare-date verification reads as midnight, before the same day's timed `generated.at`, so the content looks edited since it was checked (OKF §5.2). The first mechanical conversion to `T00:00:00Z` reproduced it in 8 fixture files; fixed, and SPEC §5.6 now says to keep events in order. `--stats` gained `changed_since_verified`.
- **Relationship dialects do not interoperate** in either direction; each tool reports the other's retirements as having no successor. A matter for OKF #16/#22.
- **Convergent design:** trust does not travel with copies (cf. §7.3a), `aliases`, the log words, retired notes hidden at search time, renames by content fingerprint (now in `ai-xf-export`).
- **Raised upstream:** KnowledgeX#22 (nested bundles); OKF #16 (dialects), #24 (bare dates and ordering), #11 (E8 tombstones). Reading the KnowledgeX dialect is deferred until OKF picks a relationship carrier.

---

## Summary and the v0.4 gate

Six planned experiments plus one on real data, one day of agent time, all reproducible from this directory. What they changed in the spec:

| Experiment | Hypothesis | Outcome | Went into v0.4 as |
|---|---|---|---|
| E1 | A consumer manifest is needed to resolve cross-bundle refs | **Wrong**: bundles carry their own manifests; scanning resolves everything. The manifest is needed for **provenance** | §9.5: manifest MAY be derived, MUST exist to claim provenance; `ref` per bundle |
| E2 | Foam's resolve-and-warn rule prevents silent misresolution | Confirmed: 0 silent, 2/2 warned, explicit form clean, no regression | §9.2 explicit `ai-xf://` form and resolution order; §11.1 obligations |
| E3 | Per-bundle collections beat a single collection on collisions | **Wrong**: only BM25 with `namespace` as a field got 4/4; hybrid ranking did not help | Non-normative index guidance: carry `namespace`/`id` as fields |
| E4 | A tools-only MCP server carries identity end to end | Confirmed for the payload contract (18/20 deterministic floor, 4/4 collisions); agent-answering measure deliberately not run | §9.8 serving guidance, scoped to the payload contract |
| E5 | Trust survives transport, not ingestion | Confirmed with numbers: 45/45 keys through git, rsync, iCloud; 8/15 normalised by parse-and-rewrite; comments lost | §7.3a and a consumer obligation |
| E6 | Signing catches tampering; digest can live in the bundle manifest | First confirmed; second **wrong** (chicken-and-egg): digest belongs in the federation manifest | §9.5 `source: oci` + `digest`; Appendix C; pinned `created` |

Three of six hypotheses were wrong. That is the argument for running them.

**Open:** the E4 LLM measures (deliberately not run for v0.4; harness in place); the Claude Code and VS Code manual side-tests (`e4-mcp/MANUAL.md`); the Knowledge Catalog round trip (needs a GCP project); OKF issue bodies #16/#22/#26/#32 unread.

