# AIX — AI eXchange Format

**Version:** 0.1
**Status:** Draft
**Date:** 2026-07-18

AIX is an open, vendor-neutral format for representing curated knowledge so that
humans and AI agents can produce and consume it without a translation layer. It
is a **strict superset of the Open Knowledge Format (OKF) v0.1**: every
conformant AIX bundle is also a conformant OKF bundle, so AIX content degrades
gracefully to OKF-only consumers while AIX-aware consumers get a richer model —
**stable identity, typed relationships, and provenance**.

> The keywords MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are used as defined in
> RFC 2119.

---

## 1. Why AIX exists

OKF proved that a directory of markdown files with YAML frontmatter is enough to
make knowledge portable. But OKF is deliberately minimal: it requires only a
`type` field and it treats every link as an **untyped** edge — the meaning of a
relationship lives only in prose. That is a floor, not a ceiling.

Knowledge bases used for real reasoning need three things OKF leaves out:

1. **Stable identity.** OKF makes the file path the identity of a concept. Move
   or rename a file and every reference breaks. Real vaults move notes
   constantly (archival, state folders, reclassification).
2. **Typed relationships.** "A supersedes B", "A depends on B" and "A contradicts
   B" are not the same edge. Collapsing them to an untyped link discards the
   signal an agent most needs.
3. **Provenance.** An agent grounding itself in a knowledge base must know how far
   to trust each concept: who authored it, how fresh it is, whether it was
   verified.

AIX adds exactly these three capabilities and nothing else load-bearing. It
stays "just markdown + YAML + files": readable without tooling, diffable in
version control, parseable without a bespoke SDK, portable across tools and
time.

---

## 2. Relationship to OKF (the compatibility contract)

AIX is defined as a superset of OKF v0.1. The contract is:

- **Every AIX concept file MUST be a valid OKF concept file** — parseable YAML
  frontmatter with a non-empty `type` field.
- **All AIX-specific data lives in frontmatter keys or an inline link
  convention that OKF consumers preserve or ignore.** OKF's conformance rules
  require consumers to preserve unknown keys and tolerate unknown content, so
  AIX extensions never break an OKF reader.
- **AIX producers MUST also emit plain markdown body links** for every typed
  relationship (see §6.4). This guarantees an OKF-only consumer still sees the
  graph edge, even though it cannot see the edge's *type*.

The result: **publish once, consumed by both.** An OKF agent sees a valid OKF
bundle. An AIX agent sees the same bundle plus identity, edge types, and
provenance.

---

## 3. Bundle structure

An AIX **bundle** is a directory tree of markdown **concept** files plus
optional reserved files.

```
my-bundle/
├── manifest.aix.yaml        # optional bundle manifest (AIX)
├── index.md                 # optional navigation (OKF reserved)
├── log.md                   # optional changelog (OKF reserved)
├── concepts/
│   ├── index.md
│   ├── payment-service.md
│   └── orders-table.md
└── people/
    └── jane-doe.md
```

- Any `.md` file that is **not** a reserved filename is a **concept**.
- Reserved filenames are `index.md`, `log.md` (inherited from OKF) and, at the
  bundle root only, `manifest.aix.yaml` (AIX). Reserved files are never
  concepts.
- Directory structure is **producer-determined**. Paths carry no mandated
  meaning; grouping is for human navigation only. (Identity comes from `id`, not
  path — see §5.)

---

## 4. Concept documents

A concept is a single markdown file: YAML frontmatter, then a markdown body.

```markdown
---
type: Concept
id: payment-service
title: Payment Service
description: Handles authorisation and capture for all customer payments.
resource: https://internal.example.com/services/payment
tags: [platform, payments]
timestamp: 2026-07-18T09:12:00Z
aliases: [Payments API, PaymentSvc]

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
  - rel: superseded-by
    to: payment-service-v2
---

# Overview

The payment service depends on the [orders table](../concepts/orders-table.md)
and is being replaced by [payment service v2](./payment-service-v2.md).
```

Note that the two links in the body mirror the two typed `links` entries — that
is the OKF-compatibility rule from §2.

---

## 5. Fields

### 5.1 Required

| Field  | Type   | Rule | Meaning |
|--------|--------|------|---------|
| `type` | string | MUST | Kind of concept (e.g. `Concept`, `System`, `Metric`, `Runbook`). Not centrally registered; consumers MUST handle unknown values gracefully. |

`type` is the only field required for **OKF Level 0** conformance (see §8).

### 5.2 Identity (AIX)

| Field | Type   | Rule   | Meaning |
|-------|--------|--------|---------|
| `id`  | string | SHOULD | A **stable slug** that uniquely identifies the concept within the bundle. Lowercase; words separated by `-`. Once assigned, `id` MUST NOT change even if the file is renamed or moved. |

- If `id` is absent, consumers MUST fall back to the bundle-relative file path as
  the identity (OKF behaviour).
- `id` values MUST be unique within a bundle.
- `id` is the **preferred link target** (§6). Because identity is decoupled from
  path, files can be reorganised without breaking references — the defining fix
  AIX makes over OKF.

### 5.3 Recommended (inherited from OKF)

| Field | Type | Meaning |
|-------|------|---------|
| `title` | string | Human-readable name. Consumers MAY derive from filename if absent. |
| `description` | string | Single-sentence summary for previews/search. |
| `resource` | string (URI) | Canonical URI of the underlying asset. Omitted for abstract concepts. |
| `tags` | list of string | Cross-cutting categorisation. |
| `timestamp` | ISO 8601 datetime | Last meaningful modification. |

### 5.4 Recommended (AIX additions)

| Field | Type | Meaning |
|-------|------|---------|
| `aliases` | list of string | Alternative names/labels for the concept. |
| `provenance` | map | Trust and freshness metadata (§7). |
| `links` | list of link objects | **Typed** relationships (§6). |

### 5.5 Custom fields

Producers MAY add any additional frontmatter keys. Consumers MUST preserve
unknown keys when round-tripping and MUST NOT reject a document for their
presence.

---

## 6. Relationships

### 6.1 The `links` array

Typed relationships are declared in a `links` frontmatter array. Each entry is a
map:

| Key | Type | Rule | Meaning |
|-----|------|------|---------|
| `rel` | string | MUST | The relationship type (§6.2). |
| `to` | string | MUST | Target concept: an `id` (preferred) or a bundle-relative path. |
| `note` | string | MAY | One-line human explanation of this specific edge. |

A link asserts a **directed** edge from the containing concept to `to`.

### 6.2 Relationship vocabulary

AIX defines a **core vocabulary** of `rel` values with defined inverses.
Producers SHOULD use a core value where one fits, and MAY introduce custom
`rel` values (any lowercase kebab-case string) where none does. Consumers MUST
treat an unknown `rel` as a generic `relates-to` edge rather than rejecting it.

| `rel` | Inverse | Meaning |
|-------|---------|---------|
| `relates-to` | `relates-to` | Generic association (symmetric). |
| `part-of` | `has-part` | Composition / containment. |
| `depends-on` | `depended-on-by` | Requires the target to function. |
| `references` | `referenced-by` | Cites or points at the target. |
| `derived-from` | `source-of` | Was produced from the target. |
| `supersedes` | `superseded-by` | Replaces the target (target is deprecated). |
| `contradicts` | `contradicts` | Known conflict (symmetric); resolution SHOULD be in prose. |
| `authored-by` | `author-of` | Attribution to a person/agent concept. |

Symmetric relationships (`relates-to`, `contradicts`) are their own inverse.

### 6.3 Inference of inverse edges

A consumer building a graph SHOULD synthesise the inverse edge for each declared
link, using the inverse column above, so that backlinks are available without
the producer writing every edge twice. Producers SHOULD declare each edge once,
from whichever side is more natural.

### 6.4 Body-link mirroring (OKF compatibility — MUST)

For every entry in `links`, the producer MUST also emit at least one **plain
markdown link** to the same target somewhere in the document body. This ensures
OKF-only consumers — which read only body links and know nothing of `links` —
still discover the (untyped) edge. AIX-aware consumers read `links` for the
typed edge and MAY ignore the redundant body link.

A markdown body link whose target has **no** corresponding `links` entry is
treated as an untyped `relates-to` edge (OKF behaviour preserved).

---

## 7. Provenance

The optional `provenance` map carries trust and freshness signals. All keys are
optional; consumers MUST tolerate any subset.

| Key | Values | Meaning |
|-----|--------|---------|
| `confidence` | `high` \| `medium` \| `low` | How authoritative the content is. |
| `freshness` | `current` \| `recent` \| `stale` | Review recency band. |
| `source` | `primary` \| `secondary` \| `synthesis` \| `external` | Origin of the knowledge. |
| `verified` | boolean | Whether the content was checked against its source. |
| `reviewed` | ISO 8601 date | When it was last reviewed. |

Producers MAY add custom provenance keys; consumers MUST preserve them.

---

## 8. Reserved files

### 8.1 `index.md` (OKF)

- MUST NOT contain frontmatter.
- Groups concepts under section headings with relative links and short
  descriptions, enabling progressive disclosure of a large bundle.

### 8.2 `log.md` (OKF)

- Flat list of date-grouped entries, newest first.
- Date headings use `YYYY-MM-DD`. Entries are prose, optionally prefixed
  (`**Creation**`, `**Update**`, …).

### 8.3 `manifest.aix.yaml` (AIX, optional)

A single YAML file at the **bundle root** describing the bundle as a whole. It
is not a concept and does not affect OKF conformance (OKF ignores non-`.md`
files). Recommended keys:

```yaml
aix: "0.1"                     # spec version this bundle targets
name: my-bundle                # bundle identifier
description: One-line summary of the bundle.
producer: aix-export/1.0       # tool or person that generated it
generated: 2026-07-18T09:12:00Z
conformance: 2                 # highest level the producer claims (§9)
counts:                        # optional, informational
  concepts: 42
```

---

## 9. Conformance levels

AIX defines a ladder so producers can adopt incrementally. A bundle's level is
the highest it fully satisfies.

| Level | Name | Requirements |
|-------|------|--------------|
| **0** | OKF-compatible | Valid OKF v0.1 bundle: every non-reserved `.md` has parseable frontmatter with a non-empty `type`; reserved files follow their structures. |
| **1** | AIX Core | Level 0, **plus** every concept has a unique `id`, **plus** a root `manifest.aix.yaml` declaring `aix` and `name`. |
| **2** | AIX Full | Level 1, **plus** every `links` entry uses a valid link object (`rel` + resolvable `to`) and is mirrored by a body link (§6.4), **plus** every concept carries a `provenance` map. |

### 9.1 Consumer obligations (all levels)

A conformant consumer:

- MUST NOT reject a bundle for: missing optional fields, unknown `type` values,
  unknown frontmatter keys, unknown `rel` values, broken links, or a missing
  `index.md`/`manifest.aix.yaml`.
- MUST treat a broken link as tolerable — it MAY denote not-yet-written
  knowledge.
- SHOULD resolve link targets by `id` first, then by bundle-relative path.
- SHOULD synthesise inverse edges (§6.3).
- MUST preserve unknown keys when round-tripping a document.

This permissive model is what keeps AIX useful while bundles evolve and agents
generate content.

---

## 10. Portability note

AIX defines a *format*, not a policy. Content sensitivity, redaction, and
outbound-sharing rules are the **producer's** responsibility and out of scope
for this spec. Producers exporting into AIX for external exchange SHOULD apply
their own sanitisation before publishing a bundle.

---

## 11. Versioning

This is AIX v0.1 — a starting point designed for backward-compatible growth.
Bundles declare the version they target via `manifest.aix.yaml`'s `aix` key.
Future minor versions MUST remain readable by v0.1 consumers under the
permissive rules of §9.1.

---

## Appendix A — minimal conformant concept (Level 0)

```markdown
---
type: Note
---

# Anything

Body is free-form.
```

## Appendix B — full concept (Level 2)

See the worked bundle in [`examples/`](./examples/) — every file there is Level 2
and passes the reference validator in [`tools/aix-validate.py`](./tools/aix-validate.py).
