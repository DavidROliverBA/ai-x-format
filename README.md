# AI-XF — AI eXchange Format

> A portable, vendor-neutral format for curated knowledge that both humans and
> AI agents produce and consume. It adds what a *reasoning* agent needs on top
> of a folder of markdown: **stable identity, typed relationships, provenance,
> media identity, federation, and change semantics**.

AI-XF is a **strict superset of Google Cloud's [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/open-knowledge-format) v0.2**.
Every AI-XF bundle is also a valid OKF bundle: OKF-only agents read it today,
AI-XF-aware agents read the same files and see more.

| | |
|---|---|
| **Spec** | [`SPEC.md`](./SPEC.md) — v0.4.4, draft |
| **Experiments** | [`experiments/`](./experiments/) — runnable evidence: federation (E1–E7), freshness and interoperability (E8–E9), maturity journeys into a database, from a wiki and into another system (E10–E12); numbers in [`RESULTS.md`](./experiments/RESULTS.md) |
| **Curation policy** (non-normative) | [`CURATOR.md`](./CURATOR.md) — seven rules and four numbers to paste into an agent's instructions |
| **Worked example** | [`examples/`](./examples/) — passes the validator at Level 3 |
| **Validator** | [`tools/ai-xf-validate.py`](./tools/ai-xf-validate.py) — conformance ladder, `--stats` (curation health and freshness), `--federation`; no dependencies |

---

## The idea in one paragraph

Keep knowledge as markdown files with YAML frontmatter, exactly as OKF says.
Give each concept a permanent `id` so files can move. Give each link a `rel` so
an agent knows whether *B replaces A* or *B depends on A*. Carry OKF's trust
fields unchanged so a human-reviewed concept means the same thing in every
bundle. Give binary assets a content hash so a diagram keeps its identity when
it moves. Let bundles from different teams cite each other by `namespace/id`.
Record what happens when new knowledge meets old: an open contradiction, a
merge, a claim gaining support. And when a concept leaves, keep it as a
tombstone that says so, rather than deleting it. Everything stays "just files".

---

## What AI-XF adds to OKF

| Capability | OKF v0.2 | AI-XF v0.4 |
|---|---|---|
| Markdown + YAML, human-readable, git-diffable | ✅ | ✅ |
| Only `type` required | ✅ | ✅ (Level 0) |
| Trust and lifecycle: `sources`, `generated`, `verified`, `status`, `stale_after` | ✅ | ✅ adopted unchanged, including value vocabularies and the actor convention |
| Per-claim attribution (footnotes keyed to `sources[].id`) | ✅ | ✅ inherited; recommended wherever an agent may rewrite the text |
| Identity | file path; breaks on move or rename | **stable `id`**; survives moves, with `aliases` for old names |
| Relationships | untyped links; meaning only in prose | **typed edges** (`depends-on`, `supersedes`, `contradicts`, `supports`, `describes`, …) with defined inverses |
| Trust class | — | epistemic `source` class; asserted `confidence` as a tie-breaker behind derived signals |
| Disagreement | — | **contradiction lifecycle**: `open` / `resolved`, who ruled, and the outcome |
| Evidence | — | `supports` edges; `type: Claim` recommended for falsifiable statements |
| Merge and split | — | tombstones, `merged-into` / `split-from`, successor redirects |
| Retirement | file deleted; a removed concept looks unwritten | a concept that leaves a bundle **becomes a tombstone**; producers that regenerate a bundle retire on every run |
| Timestamps | datetime with an offset (since OKF PR #6) | the same rule, applied to AI-XF's own edge timestamps; bare dates still read, with a warning |
| Curation activity | prose `log.md` | controlled leading-word vocabulary, so a bundle can report its own Update : Creation ratio |
| Binary assets | opaque URIs | **content-hash identity** and embedding pointers (`media`) |
| Multiple teams | one bundle at a time | **federation**: namespaces, `namespace/id` and `ai-xf://namespace/id` links, shared vocabularies, a consumer manifest with per-bundle provenance (`ref` or OCI `digest`), a resolution rule that never crosses a bundle boundary silently, and `imported` copies that do not inherit trust |
| Bundle manifest | — | `manifest.ai-xf.yaml` |
| OKF interoperability | n/a | **guaranteed**: every AI-XF bundle is a valid OKF bundle |

AI-XF adds exactly those capabilities and nothing else load-bearing.

---

## Knowledge at rest, knowledge in motion

v0.1 and v0.2 describe a concept *at rest*: what it is called, what it links
to, how far to trust it. v0.3 describes it *changing*.

A knowledge base compounds only when new material changes the concepts already
there. In a format that cannot express that change you cannot see whether it is
happening. So v0.3 gives a `contradicts` link a state and a ruling, gives a
merged concept a tombstone that points at its successor, gives evidence a
`supports` edge, and fixes nine leading words for `log.md` so that updates,
creations, contradictions and gaps can be counted without version control.

**v0.4 adds federation with evidence.** Six experiments on three deliberately
colliding fixture bundles (see [`experiments/RESULTS.md`](./experiments/RESULTS.md))
decided what went in: a consumer manifest is needed for *provenance*, not for
resolution (E1); unqualified references across bundles resolve deterministically
and always warn (E2, zero silent misresolutions); trust fields survive any
byte-moving transport and degrade only under parse-and-rewrite ingestion (E5);
a signed OCI artifact catches tampering and its digest belongs in the
federation manifest, never in the bundle's own (E6); and a tools-only MCP
server can carry `namespace/id` end to end (E4).

**v0.4.3 adds freshness, also with evidence.** Deleting a source is the test
most knowledge pipelines fail: a real exporter kept removed concepts live, and
the warning that called their broken links "not yet written" was wrong 11 times
in 12 (E8). So a departing concept becomes a tombstone, and `--stats` reports
what a bundle has stopped reconciling. Tested against a third-party OKF tool,
KnowledgeX, bare-date timestamps cost every human review in `examples/`, 0 of 5
read as reviewed, until they became datetimes with events in order (E9).

**Where a bundle goes next.** Three experiments follow a growing knowledge
base: in from Confluence or SharePoint Word files, where a naive conversion
kept at most a third of what mattered and leaked a restricted page (E11); up
into Postgres for a department, where concurrent writers, not size, force the
move, and the bundle becomes an export (E10); and across into another system's
database (E12). Each one is a list of what the format still needs, in
[`RESULTS.md`](./experiments/RESULTS.md).

The format still cannot make a curator behave. That is policy, and it ships
separately as [`CURATOR.md`](./CURATOR.md): search by meaning before writing,
keep evidence apart from synthesis, store claims rather than topics, treat a
contradiction as a ticket for a person, gate changes by reversibility, log
one entry per move, and retire rather than delete. Nothing in it is required
for conformance.

---

## The compatibility contract

1. Every AI-XF concept file is a valid OKF concept file: parseable frontmatter,
   non-empty `type`.
2. OKF v0.2's trust and lifecycle fields are adopted unchanged, with OKF's value
   vocabularies (`status: draft | stable | deprecated`), its actor convention
   (`<producer>/<version>`, `human:<id>`, `process:<id>`) and its per-claim
   footnote attribution.
3. AI-XF-only data lives in frontmatter keys (`id`, `links`, `provenance`,
   `media`, `aliases`) that OKF consumers preserve or ignore.
4. Every same-bundle typed `links` edge is mirrored by a plain markdown body
   link, so an OKF-only consumer still sees the (untyped) edge.

**Publish once, consumed by both.**

---

## Quickstart

A minimal Level 0 (OKF-compatible) concept:

```markdown
---
type: Note
---
# Anything
```

A Level 2 (AI-XF Full) claim with an open contradiction and a per-claim citation:

```markdown
---
type: Claim
id: orders-db-is-not-the-bottleneck
title: The orders database is not the payment bottleneck
generated:
  by: curator/1.0
  at: 2026-09-21T08:00:00Z
status: draft
stale_after: 2026-12-21T00:00:00Z
sources:
  - id: sept-load-test
    resource: https://internal.example.com/tests/2026-09-18-capture-load
    title: Capture load test, 18 September 2026
provenance:
  source: secondary
links:
  - rel: contradicts
    to: sync-capture-limits-throughput
    state: open
    by: curator/1.0
    at: 2026-09-21T00:00:00Z
    note: New load test disagrees with the Q2 attribution. Both claims kept.
---
# Claim
Under load the orders database ran at 40% utilisation while capture latency
still degraded.[^sept-load-test] This contradicts the claim that
[synchronous capture limits throughput](./sync-capture-limits-throughput.md).

[^sept-load-test]: Capture load test, 18 September 2026
```

Both sides of the contradiction stay intact. A person resolves it by setting
`state: resolved` with a `resolved: {by: human:…, at, outcome}` map. The full
worked bundle in [`examples/`](./examples/) shows this, a merge tombstone, a
`supports` edge, media identity and a federation-qualified link.

---

## Conformance ladder

| Level | Name | Adds |
|-------|------|------|
| 0 | OKF-compatible | Valid OKF bundle |
| 1 | AI-XF Core | Unique `id` per concept + `manifest.ai-xf.yaml` |
| 2 | AI-XF Full | Typed and mirrored `links`, trust signals on every concept, well-formed `media`, well-formed contradiction `state` / `resolved` |
| 3 | AI-XF Federated | `namespace` + qualified cross-bundle links + shared vocabularies |

Validate any bundle:

```bash
python3 tools/ai-xf-validate.py examples/                 # the example bundle
python3 tools/ai-xf-validate.py path/to/bundle --level 3
python3 tools/ai-xf-validate.py path/to/bundle --json
python3 tools/ai-xf-validate.py path/to/bundle --stats    # curation health
python3 tools/ai-xf-validate.py path/to/bundle --level 3 --federation federation.ai-xf.yaml
```

`--stats` never affects pass/fail. It reports trust tiers, staleness, open and
resolved contradictions, per-claim citation coverage, the spread of asserted
confidence (and flags a lopsided one), and the Update : Creation ratio from
`log.md`. Its freshness section lists concept files no `index.md` lists, live
links into retired concepts, concepts replaced but not retired, and concepts
changed (or whose sources changed) since they were last verified. With
`--federation` it also reports vocabulary nobody uses, by relationship pair. The validator warns on the three spellings AI-XF v0.2 got wrong
(`status: active`, `sources[].uri`, `agent:` / `pipeline:` actors) and still
reads them.

---

## Origin

AI-XF generalises the note model that a ~2,900-note working knowledge vault
converged on independently: stable identifier foreign keys, typed relationship
fields (`supersedes` / `dependsOn` / `contradicts`) and quality indicators
(`confidence` / `freshness` / `source` / `verified`). That model turned out to
be a superset of OKF; AI-XF is that superset written down.

- **v0.1** (2026-07-18): identity, typed links, provenance.
- **v0.2** (2026-08-20): rebased on OKF v0.2, media identity, federation.
- **v0.3** (2026-09-21): change semantics. Prompted by auditing the same vault
  and finding the fields present but unused: 138 notes with a `contradicts`
  field, six filled in.
- **v0.4** (draft, 2026-09-26): federation with evidence. Explicit link form,
  resolution rule, consumer manifest, `imported`, OCI distribution; every rule
  tested in `experiments/` before it was written down.
- **v0.4.3** (2026-10-02): freshness. Timestamps are datetimes with an offset,
  as OKF now requires; a concept that leaves a bundle becomes a tombstone; the
  validator reports what a bundle has stopped reconciling (E8, E9).
- **v0.4.4** (2026-10-03): the validator honours custom rels a bundle declares
  in its own vocabulary, found by a second producer (E12).

## Naming

AI-XF is an independent open-source project. It is not affiliated with, endorsed
by, or connected to IBM (whose registered mark AIX names its Unix operating
system), Google (publisher of the Open Knowledge Format that AI-XF extends), or
any holder of a similar mark. The name was chosen after a register search on
27 September 2026; earlier versions were called AIX (to v0.3) and AI-X (v0.4.0
and v0.4.1), and the validator still reads those spellings.

## Status

AI-XF v0.4 is a draft designed for backward-compatible growth. Every v0.3 bundle
is a valid v0.4 bundle, and every v0.2 bundle a valid v0.3 one; v0.1 bundles
remain valid input, with their deprecated fields (`timestamp`,
`provenance.verified` / `.freshness` / `.reviewed`) read but no longer written.
Bare-date timestamps are read the same way, with a warning. See the changelog
in [`SPEC.md`](./SPEC.md) §13.

AI-XF exists to try things ahead of the OKF specification, not to compete with
it. Every feature that OKF adopts is retired from AI-XF in favour of OKF's
definition, as happened with the trust and lifecycle fields when OKF v0.2
shipped. If OKF wins as the standard, AI-XF has done its job. Evidence goes
back to the OKF issue tracker as it is found: on deletion semantics (#11),
typed relationships (#16, #22) and timestamps (#24).

Two of its producers are the author's own (a notes-vault exporter, and
Longview, a news-intelligence service that exports and imports bundles), and
it has been tested against one independent OKF tool, KnowledgeX (E9). That
still makes it a published hypothesis rather than a standard. Feedback, alternative implementations and
conformance cases are welcome; see [`CONTRIBUTING.md`](./CONTRIBUTING.md).
MIT licensed.
