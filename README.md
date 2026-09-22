# AIX — AI eXchange Format

> A portable, vendor-neutral format for curated knowledge that both humans and
> AI agents produce and consume. It adds what a *reasoning* agent needs on top
> of a folder of markdown: **stable identity, typed relationships, provenance,
> media identity, federation, and change semantics**.

AIX is a **strict superset of Google Cloud's [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) v0.2**.
Every AIX bundle is also a valid OKF bundle: OKF-only agents read it today,
AIX-aware agents read the same files and see more.

| | |
|---|---|
| **Spec** | [`SPEC.md`](./SPEC.md) — v0.3, draft |
| **Curation policy** (non-normative) | [`CURATOR.md`](./CURATOR.md) — six rules and four numbers to paste into an agent's instructions |
| **Worked example** | [`examples/`](./examples/) — passes the validator at Level 3 |
| **Validator** | [`tools/aix-validate.py`](./tools/aix-validate.py) — conformance ladder plus `--stats` |

---

## The idea in one paragraph

Keep knowledge as markdown files with YAML frontmatter, exactly as OKF says.
Give each concept a permanent `id` so files can move. Give each link a `rel` so
an agent knows whether *B replaces A* or *B depends on A*. Carry OKF's trust
fields unchanged so a human-reviewed concept means the same thing in every
bundle. Give binary assets a content hash so a diagram keeps its identity when
it moves. Let bundles from different teams cite each other by `namespace/id`.
And, new in v0.3, record what happens when new knowledge meets old: an open
contradiction, a merge, a claim gaining support. Everything stays "just files".

---

## What AIX adds to OKF

| Capability | OKF v0.2 | AIX v0.3 |
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
| Curation activity | prose `log.md` | controlled leading-word vocabulary, so a bundle can report its own Update : Creation ratio |
| Binary assets | opaque URIs | **content-hash identity** and embedding pointers (`media`) |
| Multiple teams | one bundle at a time | **federation**: namespaces, qualified cross-bundle links, shared vocabularies |
| Bundle manifest | — | `manifest.aix.yaml` |
| OKF interoperability | n/a | **guaranteed**: every AIX bundle is a valid OKF bundle |

AIX adds exactly those capabilities and nothing else load-bearing.

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

The format still cannot make a curator behave. That is policy, and it ships
separately as [`CURATOR.md`](./CURATOR.md): search by meaning before writing,
keep evidence apart from synthesis, store claims rather than topics, treat a
contradiction as a ticket for a person, gate changes by reversibility, and log
one entry per move. Nothing in it is required for conformance.

---

## The compatibility contract

1. Every AIX concept file is a valid OKF concept file: parseable frontmatter,
   non-empty `type`.
2. OKF v0.2's trust and lifecycle fields are adopted unchanged, with OKF's value
   vocabularies (`status: draft | stable | deprecated`), its actor convention
   (`<producer>/<version>`, `human:<id>`, `process:<id>`) and its per-claim
   footnote attribution.
3. AIX-only data lives in frontmatter keys (`id`, `links`, `provenance`,
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

A Level 2 (AIX Full) claim with an open contradiction and a per-claim citation:

```markdown
---
type: Claim
id: orders-db-is-not-the-bottleneck
title: The orders database is not the payment bottleneck
generated:
  by: curator/1.0
  at: 2026-09-21T08:00:00Z
status: draft
stale_after: 2026-12-21
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
    at: 2026-09-21
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
| 1 | AIX Core | Unique `id` per concept + `manifest.aix.yaml` |
| 2 | AIX Full | Typed and mirrored `links`, trust signals on every concept, well-formed `media`, well-formed contradiction `state` / `resolved` |
| 3 | AIX Federated | `namespace` + qualified cross-bundle links + shared vocabularies |

Validate any bundle:

```bash
python3 tools/aix-validate.py examples/                 # the example bundle
python3 tools/aix-validate.py path/to/bundle --level 3
python3 tools/aix-validate.py path/to/bundle --json
python3 tools/aix-validate.py path/to/bundle --stats    # curation health
```

`--stats` never affects pass/fail. It reports trust tiers, staleness, open and
resolved contradictions, per-claim citation coverage, the spread of asserted
confidence (and flags a lopsided one), and the Update : Creation ratio from
`log.md`. The validator warns on the three spellings AIX v0.2 got wrong
(`status: active`, `sources[].uri`, `agent:` / `pipeline:` actors) and still
reads them.

---

## Origin

AIX generalises the note model that a ~2,900-note working knowledge vault
converged on independently: stable identifier foreign keys, typed relationship
fields (`supersedes` / `dependsOn` / `contradicts`) and quality indicators
(`confidence` / `freshness` / `source` / `verified`). That model turned out to
be a superset of OKF; AIX is that superset written down.

- **v0.1** (2026-07-18): identity, typed links, provenance.
- **v0.2** (2026-08-20): rebased on OKF v0.2, media identity, federation.
- **v0.3** (2026-09-21): change semantics. Prompted by auditing the same vault
  and finding the fields present but unused: 138 notes with a `contradicts`
  field, six filled in.

## Status

AIX v0.3 is a draft designed for backward-compatible growth. Every v0.2 bundle
is a valid v0.3 bundle; v0.1 bundles remain valid input, with their deprecated
fields (`timestamp`, `provenance.verified` / `.freshness` / `.reviewed`) read
but no longer written. See the changelog in [`SPEC.md`](./SPEC.md) §13.

It has one producer and one consumer today, which makes it a published
hypothesis rather than a standard. Feedback, alternative implementations and
conformance cases are welcome; see [`CONTRIBUTING.md`](./CONTRIBUTING.md).
MIT licensed.
