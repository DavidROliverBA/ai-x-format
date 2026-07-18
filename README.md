# AIX — AI eXchange Format

> A portable, vendor-neutral format for curated knowledge that both humans and
> AI agents produce and consume — with **stable identity, typed relationships,
> and provenance** built in.

AIX is a **strict superset of Google Cloud's [Open Knowledge Format
(OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
v0.1**. Every AIX bundle is also a valid OKF bundle, so your knowledge is
readable by OKF-only agents today while AIX-aware agents get a richer graph.

- **Spec:** [`SPEC.md`](./SPEC.md)
- **Worked example bundle:** [`examples/`](./examples/)
- **Reference validator:** [`tools/aix-validate.py`](./tools/aix-validate.py)

---

## Why not just use OKF?

OKF is an excellent floor: markdown files + YAML frontmatter + link graph, with
`type` the only required field. But it deliberately stops short of what a
knowledge base needs for *reasoning*:

| Capability | OKF v0.1 | AIX v0.1 |
|---|---|---|
| Markdown + YAML, human-readable, git-diffable | ✅ | ✅ |
| Only `type` required | ✅ | ✅ (Level 0) |
| Identity | **File path** — breaks on move/rename | **Stable `id` slug** — survives moves |
| Relationships | **Untyped** links; meaning only in prose | **Typed** edges (`depends-on`, `supersedes`, `contradicts`, …) with inverses |
| Provenance | — | `confidence` / `freshness` / `source` / `verified` / `reviewed` |
| Bundle manifest | — | `manifest.aix.yaml` |
| OKF interoperability | n/a | **Guaranteed** — every AIX bundle is a valid OKF bundle |

AIX adds exactly those three things (identity, typed relationships, provenance)
and nothing else load-bearing. It stays "just files".

## Origin

AIX generalises the note model that a ~2,900-note working knowledge vault
converged on independently — stable slug foreign keys, typed relationship fields
(`supersedes` / `dependsOn` / `contradicts` / `linked_*`), and quality
indicators (`confidence` / `freshness` / `source` / `verified`). That model
turned out to be a superset of OKF; AIX is that superset written down as a
portable standard.

## The compatibility contract

1. Every AIX concept file is a valid OKF concept file (parseable frontmatter,
   non-empty `type`).
2. AIX-only data lives in frontmatter keys (`id`, `links`, `provenance`) that OKF
   consumers preserve or ignore.
3. Every typed `links` edge is **mirrored by a plain markdown body link**, so an
   OKF-only consumer still sees the (untyped) edge.

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
timestamp: 2026-07-18T09:12:00Z
provenance:
  confidence: high
  freshness: current
  source: primary
  verified: true
  reviewed: 2026-07-18
links:
  - rel: depends-on
    to: orders-table
    note: Reads order totals to compute capture amounts.
---
# Overview
Depends on the [orders table](./orders-table.md).
```

## Conformance ladder

| Level | Name | Adds |
|-------|------|------|
| 0 | OKF-compatible | Valid OKF bundle |
| 1 | AIX Core | Unique `id` per concept + `manifest.aix.yaml` |
| 2 | AIX Full | Typed+mirrored `links` + `provenance` on every concept |

Validate any bundle:

```bash
python3 tools/aix-validate.py examples/          # check the example bundle
python3 tools/aix-validate.py path/to/bundle --level 2
python3 tools/aix-validate.py path/to/bundle --json
```

## Status

AIX v0.1 is a draft, designed for backward-compatible growth. Feedback and
alternative implementations welcome.
