# AIX — AI eXchange Format

> A portable, vendor-neutral format for curated knowledge that both humans and
> AI agents produce and consume — with **stable identity, typed relationships,
> provenance, media identity, federation, and change semantics** built in.

AIX is a **strict superset of Google Cloud's [Open Knowledge Format
(OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
v0.2**. Every AIX bundle is also a valid OKF bundle, so your knowledge is
readable by OKF-only agents today while AIX-aware agents get a richer graph.

- **Spec:** [`SPEC.md`](./SPEC.md)
- **Worked example bundle:** [`examples/`](./examples/)
- **Reference validator:** [`tools/aix-validate.py`](./tools/aix-validate.py)
- **Reference curation policy (non-normative):** [`CURATOR.md`](./CURATOR.md)

---

## Why not just use OKF?

OKF is an excellent floor: markdown files + YAML frontmatter + link graph, with
`type` the only required field. v0.2 added trust and lifecycle signals
(`sources`, `generated`, `verified`, `status`, `stale_after`), which AIX adopts
as-is. But OKF still deliberately stops short of what a knowledge base needs
for *reasoning*:

| Capability | OKF v0.2 | AIX v0.3 |
|---|---|---|
| Markdown + YAML, human-readable, git-diffable | ✅ | ✅ |
| Only `type` required | ✅ | ✅ (Level 0) |
| Trust & lifecycle (`sources`, `generated`, `verified`, `status`, `stale_after`) | ✅ | ✅ (adopted unchanged) |
| Identity | **File path** — breaks on move/rename | **Stable `id`** — survives moves |
| Relationships | **Untyped** links; meaning only in prose | **Typed** edges (`depends-on`, `supersedes`, `contradicts`, `describes`, …) with inverses |
| Trust class | — | Epistemic `source` class; asserted `confidence` as a tie-breaker |
| Per-claim attribution | ✅ footnotes keyed to `sources[].id` | ✅ (inherited; recommended for agent-rewritten content) |
| Disagreement | — | **Contradiction lifecycle**: `open` / `resolved`, who ruled, and the outcome |
| Evidence | — | `supports` edges; `type: Claim` recommended |
| Merge and split | — | Tombstones, `merged-into` / `split-from`, successor redirects |
| Curation activity | Prose `log.md` | Controlled log vocabulary, so a bundle can report its own Update:Creation ratio |
| Binary assets | Opaque URIs | **Content-hash identity** + embedding pointers (`media`) |
| Multiple teams | One bundle at a time | **Federation**: namespaces, qualified cross-bundle links, shared vocabularies |
| Bundle manifest | — | `manifest.aix.yaml` |
| OKF interoperability | n/a | **Guaranteed** — every AIX bundle is a valid OKF bundle |

AIX adds exactly those capabilities and nothing else load-bearing. It stays
"just files".

## Knowledge at rest, knowledge in motion

v0.1 and v0.2 describe a concept *at rest*: what it is called, what it links
to, how far to trust it. v0.3 describes it *changing*: that two concepts
disagree and nobody has ruled yet, that two were merged, that a claim gained
support. A knowledge base compounds only when new material changes existing
concepts, and you cannot see whether that is happening in a format that cannot
express it.

The format still cannot make a curator behave. That is policy, and it ships
separately as [`CURATOR.md`](./CURATOR.md): six rules and four numbers to paste
into your agent's instructions.

## Origin

AIX generalises the note model that a ~2,900-note working knowledge vault
converged on independently — stable identifier foreign keys, typed relationship fields
(`supersedes` / `dependsOn` / `contradicts` / `linked_*`), and quality
indicators (`confidence` / `freshness` / `source` / `verified`). That model
turned out to be a superset of OKF; AIX is that superset written down as a
portable standard. v0.2 tracks OKF v0.2 and extends the model to binary assets
and multi-team federation. v0.3 came from auditing that same vault and finding
the fields present but unused: 138 notes with a `contradicts` field, six filled
in.

## The compatibility contract

1. Every AIX concept file is a valid OKF concept file (parseable frontmatter,
   non-empty `type`).
2. OKF v0.2's trust fields are adopted unchanged — trust tiers mean the same
   thing in an AIX bundle as in any OKF bundle.
3. AIX-only data lives in frontmatter keys (`id`, `links`, `provenance`,
   `media`) that OKF consumers preserve or ignore.
4. Every same-bundle typed `links` edge is **mirrored by a plain markdown body
   link**, so an OKF-only consumer still sees the (untyped) edge.

**Publish once, consumed by both.**

## Quickstart

A minimal Level 0 (OKF-compatible) concept:

```markdown
---
type: Note
---
# Anything
```

A Level 2 (AIX Full) concept:

```markdown
---
type: Concept
id: payment-service
title: Payment Service
description: Handles authorisation and capture for customer payments.
tags: [platform, payments]
generated:
  by: human:jane-doe
  at: 2026-08-20T09:12:00Z
verified:
  - by: human:jane-doe
    at: 2026-08-20
status: stable
stale_after: 2027-02-20
provenance:
  confidence: high
  source: primary
links:
  - rel: depends-on
    to: orders-table
    note: Reads order totals to compute capture amounts.
media:
  - uri: https://internal.example.com/diagrams/payment-flow.png
    hash: sha256:9f2c8a41d6…
---
# Overview
Depends on the [orders table](./orders-table.md).
```

## Conformance ladder

| Level | Name | Adds |
|-------|------|------|
| 0 | OKF-compatible | Valid OKF bundle |
| 1 | AIX Core | Unique `id` per concept + `manifest.aix.yaml` |
| 2 | AIX Full | Typed+mirrored `links` + trust signals on every concept + well-formed `media` |
| 3 | AIX Federated | `namespace` + qualified cross-bundle links + shared vocabularies |

Validate any bundle:

```bash
python3 tools/aix-validate.py examples/          # check the example bundle
python3 tools/aix-validate.py path/to/bundle --level 3
python3 tools/aix-validate.py path/to/bundle --json
python3 tools/aix-validate.py path/to/bundle --stats   # curation health
```

`--stats` never affects pass/fail. It reports trust tiers, staleness, open and
resolved contradictions, per-claim citation coverage, the spread of asserted
confidence, and the Update:Creation ratio from `log.md`.

## Status

AIX v0.3 is a draft, designed for backward-compatible growth. Every v0.2 bundle
is a valid v0.3 bundle. v0.3 also corrects three spellings where AIX v0.2
deviated from the OKF v0.2 it claimed to adopt (`status: active`,
`sources[].uri`, `agent:` / `pipeline:` actors); the validator warns on the old
forms. v0.1 bundles remain valid input; deprecated fields (`timestamp`, `provenance.verified`,
`provenance.freshness`, `provenance.reviewed`) are read but should no longer be
written — see the changelog in [`SPEC.md`](./SPEC.md) §13. Feedback and
alternative implementations welcome.
