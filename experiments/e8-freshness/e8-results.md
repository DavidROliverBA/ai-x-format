# E8 results: freshness and drift

**2026-10-02.** Prompted by Isci, "How to Keep Knowledge Graphs Fresh: Staleness,
Drift, and the Schema Nobody Cares About" (Medium, 31 Aug 2026), whose claim is
that deletion is the diagnostic test: a pipeline that handles only additions and
edits is accumulating, not reconciling. Producer: MyVault's `ai-xf-export/0.4`.
Corpus: copies of the vault's `Psychology/Concepts` (102 notes), federated with a
copy of `ai-concepts-kb` (63). Validator at v0.4.2, PyYAML. Re-run with `run.sh`.

No plan with pass criteria preceded this one; it is exploratory. Treat the
numbers as a baseline for a planned experiment, not as a gate.

## Lifecycle

Phases, applied cumulatively: P1 export; P2 add a note; P3 drop one `relatedTo`
link; P4 rename `PC Mindset` (Obsidian-style: inbound wikilinks rewritten); P5
delete `Fermi Paradox` (inbound wikilinks left dangling, as Obsidian does).
`pc-mindset` and `fermi-paradox` are both linked from `ai-concepts`.

Producer modes:

- **inplace**: the exporter as used today, writing over the published bundle.
- **fresh**: the output directory is deleted before each export (full rebuild).
- **tombstone**: inplace, then a prototype reconcile step that retires any concept file missing from the regenerated `index.md` as a §6.6 tombstone, with a §10.2 `Deprecation` entry in `log.md`.
- **stable**: as tombstone, but every source note first gets a pinned `slug:`, which the exporter honours as `id` (§5.2).

State after P5:

| Mode | Active ghosts (no source) | Edges still pointing at them | Tombstones | Cross-bundle refs newly unresolved | Validator |
|---|---|---|---|---|---|
| inplace | **2** (`fermi-paradox`, `pc-mindset`) | 5 | 0 | 0 | PASS, nothing new |
| fresh | 0 | 0 | 0 | **2**, worded "may be not-yet-written" | PASS |
| tombstone | 0 | 5, now into `status: deprecated` | 2, **both "retired, no successor"** | 0 | PASS; `--stats` lists both, `log.md: Deprecation 2` |
| stable | 0 | 4 into the one tombstone | 1 (`fermi-paradox`) | 0 | PASS; rename produced nothing at all |

P1–P3 were clean in every mode: add and edit reconcile because the exporter
rewrites each file it exports. Only rename and delete separate the modes.

**Findings:**

1. **The exporter is an accumulator.** In place, a deleted or renamed note's
   concept stays on disk as `status: stable`, every link into it keeps
   resolving, and the validator reports nothing. This is the failure Isci
   calls the most dangerous: the bundle looks fresh and answers confidently.
2. **A full rebuild trades ghosts for silent dangling links.** Other bundles
   lose their targets, and the only signal is a warning that says the target
   "may be not-yet-written", which is the opposite of what happened.
3. **The bundle already contains a perfect ghost detector.** The exporter
   regenerates `index.md` and `manifest.counts` from the current slice but
   never deletes concept files, so *concept file not listed in `index.md`*
   caught 2/2 ghosts with 0 false positives in every phase, using the bundle
   alone. It depends on a regenerated index; a hand-maintained index would
   need a different signal.
4. **Tombstones work with the spec as written.** §6.6's deprecated-file form
   and §10.2's `Deprecation` entry needed no change. Links keep resolving,
   to a concept that says it is retired, and `--stats` already reports it.
5. **Rename is an identity problem, not a freshness problem.** With
   filename-derived ids, a rename is a delete plus an add, and the best a
   reconciler can write is "retired, no successor", which is wrong. Pinning
   the id in the source removed the event entirely. §5.2 already says ids
   never change; the exporter breaks that by deriving them from filenames.

## What "not-yet-written" actually means on real data

Before any phase ran, `psychology` had 12 distinct unresolved targets, all
reported as "tolerated — may be not-yet-written". Each was looked up in the
vault:

| Actually | Count | Examples |
|---|---|---|
| Archived (retired from the slice; still in `Archive/`) | 7 | `loss-aversion`, `overconfidence-effect`, `survivorship-bias` |
| Written, but a different note type outside the slice (`Reference - …`) | 4 | `reinforcement-learning` |
| Genuinely not written | 1 | `status-quo-bias` (a plain string, and an alias of `Default Effect`) |

The warning's wording was wrong for 11 of 12. This corrects E7's reading that
the slices were "too narrow": the two most-linked dangling targets there,
`overconfidence-effect` (34) and `survivorship-bias` (23), are retired
concepts, which a tombstone would have said.

## Schema layer

Federation vocabularies are hand-agreed (§9.3), not induced, so Isci's
type-accumulation problem needs restating before it applies.

Declared vs used across the real federation (`psychology`, `ai-concepts`, `examples/`):

| | Declared | Unused | Of the unused |
|---|---|---|---|
| Types | 7 | 2 (`Policy`, `Runbook`) | both used in the fixture federation |
| Rels | 24 | 13 | 8 are inverse names, which §6.3 says producers should not write; 5 forward rels unused |

Type extinction on the fixture federation: deleting `data-eng`'s only `Policy`
concept left `Policy` declared with zero instances. The validator reported
one tolerated dangling link from the contradicting claim, and nothing about
the type.

**Findings:**

6. **A naive orphan audit is mostly false positives here.** 8 of 13 "unused"
   rels are inverses that are unused by design, and zero instances of a
   federation type in one federation says nothing about whether it is still
   agreed. Unused vocabulary is a report, never a failure, and inverses must
   be excluded.
7. **The live TBox problem is the opposite of Isci's: collapse, not
   accumulation.** 165 of 172 real concepts are `type: Concept`. The vault
   holds a ten-value `conceptType` (52 bias, 17 effect, 11 fallacy, 10
   illusion, …) that the exporter drops entirely. That is his "fixed
   vocabulary" failure (graphify's single `concept` type) on our own data.

## After the fixes (same day)

The exporter (MyVault, after `4003c1f7`) now reconciles on re-export, and the
validator's `--stats` gained the freshness and vocabulary numbers. `run.sh`
reruns against the current exporter (`results.json`); the pre-fix numbers above
are in `results-before-fix.json` (`run.py --exporter <4003c1f7 copy>`).

Default mode (export over the existing bundle), after P5:

| | Exporter at `4003c1f7` | Exporter now |
|---|---|---|
| Active ghosts | 2 | **0** |
| Tombstones | 0 | 2: `fermi-paradox` retired; `pc-mindset` `superseded-by` `proof-of-concept-mindset`, which lists it in `aliases` |
| Cross-bundle refs newly unresolved | 0 | 0 |
| `log.md` | none | `Initialization`, `Creation`, `Update`, `Deprecation` (read-then-add) |
| Validator `--stats` on psychology | flags **2 concept files in no index.md** (the ghosts, by name) | flags **3 live edges into a retired concept** |
| Validator `--stats` on ai-concepts (federated) | nothing | **1 edge into another bundle's retired concept** |

Direct exporter checks on a copy of the corpus: a repeat export with no change
is a no-op (0 created, 0 updated, 102 unchanged); a body edit logs one
`Update`; a restored note logs `Update … restored`; after `--pin-ids`, a rename
changes nothing. Two bugs found while testing and fixed before the run above:
neighbours of a removed concept logged spurious `Update`s because their link
labels fell back to the raw id, and a rename's alias vanished on the next
export unless rebuilt from existing tombstones.

Federation vocabulary on the real federation, by pair: 2 of 7 types and 4 of 13
rel pairs unused, against 13 of 24 by name. Regression: 15/15 validator tests
pass under both parsers (5 new in `FreshnessStats`); `examples/` byte-identical
to the E2 baseline; stdlib and PyYAML `--stats` JSON identical on `examples/`,
both E8 bundles and `data-eng`.

## Edge cases (second round, same day)

**Exporter**: 12 pytest cases in MyVault `.claude/scripts/tests/test-ai-xf-export.py`
(no-op repeat, delete, rename, rename with a new title, ambiguous title, rename
chain, rename back, hand-written concept, different slice, `--pin-ids`
idempotence, existing log carried forward, archived in place). 8 passed first
time. The 4 failures were:

- **Rename back (A → B → A)** left B retired with no successor: a restored id
  was not counted as an arrival. Fixed; B is now `superseded-by` A.
- **A hand-written concept** in the bundle was retired silently. It is still
  retired (the exporter owns `concepts/`), but now with a warning naming it.
- **Exporting a different slice** into an existing bundle retired every
  concept. Now refused when it would retire more than half the live concepts
  (and more than 5) unless `--allow-mass-retire`; nothing is written.
- **Deleting the last note of a slice** cannot be reconciled: an empty slice is
  refused outright ("no source notes"). Recorded as a limit, not fixed.

Known limit: rename detection matches on title, so a rename that also changes
`title:` is retired without a successor. Every note in both real slices has a
`title:` and no two share one; `--pin-ids` removes the question.

**Validator**: probes found four false results in the new stats (index links
written `<…>`, with a `"title"`, or %-encoded; `to:` as a bundle-relative path)
and two older bugs in the core checks:

- **Moving a concept file with its id unchanged failed Level 3.** Body-link
  mirroring compared link *filenames* with ids, so `examples/` with
  `orders-table.md` moved to `concepts/data/orders.md` (id kept, every body link
  updated) failed with 2 "not mirrored" errors, which is the reorganisation §5.2
  promises is safe. Body links now resolve to the id of the file they land on.
- **A bundle-relative `to:` path did not resolve** (§6.1 allows it): it was
  resolved relative to the linking concept's folder. Both are now tried.

Both fixes only remove false findings: on `examples/` at levels 0–3, both
fixture bundles, both real bundles, all three E2 bundles and the E8 bundle,
findings are identical to the committed validator under both parsers. 20/20
validator tests (5 new in `LinkForms`); E2 baseline unchanged.

**Real re-export** (copies of `psychology-kb` and `ai-concepts-kb`, current
exporter, federation manifest): first run 102 + 60 `Update`, 0 created, 0
retired. The only diff is the new `conceptType` line, so the slices still match
what was published on 2026-09-27. Second run: complete no-op. Both PASS Level 3
with no freshness flags.

## What this suggests

All adopted, in v0.4.3 (SPEC §13):

- Producer reconcile, `--pin-ids`, `conceptType`, and renames matched by
  exact body content as well as title (`ai-xf-export`).
- Validator `--stats` freshness and vocabulary numbers (see above), plus
  replaced-but-live concepts and sources changed since verification.
- Validator wording: "does not resolve (tolerated: …)", without the
  "not-yet-written" guess; the §6.6 `aliases` fallback.
- `CURATOR.md` rule 7: retire, don't delete; rename, don't re-mint.
- SPEC §6.6: a concept that leaves a bundle SHOULD become a tombstone.
