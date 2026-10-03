# E12 results: from an LLM knowledge base into Longview

**2026-10-03.** Longview (`12b250b`) is a Bun, TypeScript and Postgres system that turns public
sources into entities, stories, claims and briefs. It now exports its knowledge base as an AI-XF
bundle and imports bundles back, in two modes: **restore** (its own bundle, ids preserved) and
**federate** (anyone else's bundle, read as an untrusted source). This experiment takes the
"across" journey: an AI-XF bundle written elsewhere, into Longview's database, and back out.
Exploratory: no plan with pass criteria preceded it. Re-run with `run.sh`; numbers in
`results.json`.

Everything ran against a throwaway Postgres container, from a scratch copy of Longview with no
`.env`. The LLM pipeline (clustering, extraction, entity linking, adjudication) was never run; one
event, item and claim were inserted by SQL to stand in for it.

## 1. What a federate import does today

Two bundles Longview did not write: `examples/` (7 concepts, namespace `example-payments`) and the
author's `psychology-kb` (102 concepts, the v0.4.3 export).

| | examples | psychology |
|---|---|---|
| Stored verbatim in `aixf_concepts` (frontmatter as JSON, body, content hash) | 7 | 102 |
| Projected as `raw_items` for the pipeline | 5 (2 tombstones stored only) | 102 |
| Entities created | 1 (`Person` Jane Doe) | 0 (`type: Concept` is not an entity kind) |
| Links projected into Longview `edges` | 0 of 14 | 0 of 417 |
| Trust tiers read | 5 human, 2 unverified | 43 human, 59 unverified |
| Keys kept but not modelled | `stale_after`, `verified`, `sources`, `provenance`, `media`, `tags`, `resource` | `stale_after`, `verified`, `provenance`, `tags`, `conceptType` |
| Manifest | "not a Longview manifest" (`producer: hand-authored`, not an actor); kept raw | "not a Longview manifest" (no `vocabularies`); kept raw |

- **Identity survives.** Each projected item carries `guid: ai-xf://namespace/id`, the trust tier,
  status, provenance and an `imported` record (§9.6). Trust never raises the source weight.
- **Nothing is lost at rest.** Every key, including `stale_after` (as written, a datetime) and the
  custom `conceptType`, is kept whole in `aixf_concepts` (§7.3a).
- **Links are almost entirely dropped from the working model.** Only entity-to-entity links whose
  rel maps into Longview's closed edge vocabulary are projected. All 431 links here were left in
  `aixf_concepts`: `supersedes`, `contradicts`, `supports`, `depends-on` and `relates-to` alike.
  Contradiction state (open or resolved) and successor links do not reach Longview's tables.
- **Tombstones are honoured on first import.** Both `examples/` tombstones were stored and not
  projected, so retired concepts never enter the pipeline.

## 2. Re-importing a changed bundle

Edit one concept, retire one as a tombstone, add one; then delete the added one outright.

| Change | `aixf_concepts` | `raw_items` |
|---|---|---|
| Unchanged (100) | untouched (content hash) | untouched |
| Edited | updated | **a second row** for the same `ai-xf://` URL; once the pipeline has made an item, it is "not refreshed" |
| Retired (tombstone) | updated to `deprecated` | **old row stays, payload still `stable`** |
| Added | inserted | inserted |
| Deleted (no tombstone) | **kept, still `stable`**; counted as "stored but gone from bundle" | **kept** |

The importer is idempotent and never duplicates an unchanged concept. But it is an accumulator in
E8's sense on the projection side: an edit, a retirement and a deletion are each recorded or
counted, and none of them reaches what the pipeline has already ingested.

## 3. Back out again: export and validation

Longview exported the scratch database: 66 sources, plus the seeded entity, event and claim
(69 concepts). The 109 federated concepts **do not re-export** as themselves; only what the
pipeline makes of them does.

- **Provenance survives as a citation.** The event and claim cite the federated concept as
  `sources[].resource: ai-xf://psychology/action-bias`, author "psychology (AI-XF bundle)".
- **Entity identity does not.** Jane Doe comes back as `entity-jane-doe` in `longview-ai`, with no
  `imported` link to `example-payments/jane-doe`, and (correctly, §9.6) without her human review.
- **Validators disagree.** Longview's vendored validator (`4ff386f`) passes it with 0 findings.
  The current validator (v0.4.3) passes with **5 warnings on 3 concepts**: every entity, event and
  claim has a date-only `stale_after`, and every cited item a date-only `sources[].last_modified`
  (Longview's `isoDate()`). `bun run validate:ai-xf` fails on any warning, so re-vendoring v0.4.3
  turns Longview's export gate red; on its 13,424-concept fixture that is at least one warning per
  entity, event and claim.

Longview's own list of AI-XF spec gaps (`docs/AI-XF.md`), against v0.4.3:

| Gap | Status |
|---|---|
| Body-link mirroring matched by file name, not id | **Fixed in v0.4.3** (moved files keep conformance) |
| Custom rels warned on even when the bundle declares them in its own `vocab/rels.json` | **Still open**: both validators warn on a declared `competes-with`; only a *federation* vocabulary is consulted |
| Links have no `sources` (evidence) | Open |
| No confidence on a machine-resolved contradiction | Open |
| Numeric confidence (three bands only) | Open |

## The journey, as it stands

```bash
# 1. Export the knowledge base as AI-XF (vault exporter shown; any producer works)
python3 .claude/scripts/ai-xf-export.py "Psychology/Concepts/*.md" --out ~/Documents/GitHub/psychology-kb --name psychology
# 2. Publish it at a commit, and pin that commit in Longview's topics/<pack>/federation.ai-xf.yaml
#    (namespace, repo, full 40-character sha, weight 1-5, a public category)
# 3. Import: dry run, then real
bun run import:ai-xf DavidROliverBA/psychology-kb@<sha> --mode federate --dry-run
bun run import:ai-xf DavidROliverBA/psychology-kb@<sha> --mode federate
# 4. The daily pipeline turns projected items into stories, claims and entities (LLM cost)
# 5. Longview's own export now cites the concepts as ai-xf://namespace/id sources
```

- **Preserved:** every concept verbatim, identity (`namespace/id`, `ref`), trust tier as metadata,
  tombstones on first import, typed people and systems as entities.
- **Lost from the working model** (kept only in `aixf_concepts`): typed links, contradiction state,
  successors, `stale_after`, verification events, custom keys, and plain `Concept`s as entities.
- **Needs the LLM pipeline:** everything that makes a concept useful inside Longview (events,
  claims, entity links, adjudication).
- **Does not propagate:** later edits, retirements and deletions in the bundle.

## Gaps, and where each fix lives

| # | Gap | Fix lives in |
|---|---|---|
| 1 | Retired or deleted concepts stay live in `raw_items`/`items` | Longview importer: on `deprecated` or "gone from bundle", mark the stored concept and retire or flag the projected item |
| 2 | An edit adds a second raw row and never refreshes the item | Longview importer and normaliser: refresh by `ai-xf://` URL, or record the supersession |
| 3 | Typed links, contradictions and successors never reach Longview's tables | Longview: project `supersedes`/`contradicts` between concepts, not only entity edges |
| 4 | Date-only `stale_after` and `last_modified` in Longview's export | Longview exporter: `isoDate` → `isoDateTime` (`T00:00:00Z`), then re-vendor the v0.4.3 validator |
| 5 | Federated entities lose their source identity on export | Longview exporter: an `imported` link (§9.6) from `entity-<slug>` to `namespace/id` |
| 6 | Declared custom rels still warned on | AI-XF validator: read the bundle manifest's own `vocabularies.rels` (§9.3) |
| 7 | `examples/manifest.ai-xf.yaml` says `ai-xf: "0.3"` and `producer: hand-authored` | AI-XF `examples/`: bump to 0.4 and use an actor (`human:jane-doe`); §10.3 should say producer is an actor |
| 8 | The vault exporter's manifest has no `vocabularies` | `ai-xf-export`: carry the federation's vocabulary pointers, or Longview should accept their absence below Level 3 |
| 9 | A plain `Concept` never becomes a Longview entity | Longview topic pack or AI-XF type mapping: decide whether `Concept` maps to a kind |
