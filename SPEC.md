# AIX — AI eXchange Format

**Version:** 0.2
**Status:** Draft
**Date:** 2026-08-20
**Supersedes:** v0.1 (2026-07-18)

AIX is an open, vendor-neutral format for representing curated knowledge so that
humans and AI agents can produce and consume it without a translation layer. It
is a **strict superset of the Open Knowledge Format (OKF) v0.2**: every
conformant AIX bundle is also a conformant OKF bundle, so AIX content degrades
gracefully to OKF-only consumers while AIX-aware consumers get a richer model —
**stable identity, typed relationships, provenance, media identity, and
federation**.

> The keywords MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are used as defined in
> RFC 2119.

---

## 1. Why AIX exists

OKF proved that a directory of markdown files with YAML frontmatter is enough to
make knowledge portable. OKF v0.2 (2026-07-25) added trust and lifecycle
signals — `sources`, `generated`, `verified`, `status`, `stale_after` — which
closed one of the three gaps AIX v0.1 identified. Two gaps remain open, and
scale has exposed two more:

1. **Stable identity.** OKF makes the file path the identity of a concept. Move
   or rename a file and every reference breaks. Real vaults move notes
   constantly (archival, state folders, reclassification).
2. **Typed relationships.** "A supersedes B", "A depends on B" and "A contradicts
   B" are not the same edge. Collapsing them to an untyped link discards the
   signal an agent most needs.
3. **Media identity.** Knowledge is no longer only prose. Diagrams, recordings,
   and screenshots enter OKF only as opaque URIs; nothing gives a binary asset
   a stable, deduplicable identity or a hook for multimodal retrieval.
4. **Federation.** The moment a second team publishes a bundle, ids collide,
   vocabularies drift, and trust signals stop being comparable. A format that
   only works inside one bundle stops at the edge of one team.

AIX adds exactly these capabilities and nothing else load-bearing. It stays
"just markdown + YAML + files": readable without tooling, diffable in version
control, parseable without a bespoke SDK, portable across tools and time.

---

## 2. Relationship to OKF (the compatibility contract)

AIX v0.2 is defined as a superset of **OKF v0.2**. The contract is:

- **Every AIX concept file MUST be a valid OKF concept file** — parseable YAML
  frontmatter with a non-empty `type` field.
- **AIX adopts OKF v0.2's trust and lifecycle fields as-is** (`sources`,
  `generated`, `verified`, `status`, `stale_after`). AIX does not redefine
  them; it builds on them (§7).
- **All AIX-specific data lives in frontmatter keys or an inline link
  convention that OKF consumers preserve or ignore.** OKF's conformance rules
  require consumers to preserve unknown keys and tolerate unknown content, so
  AIX extensions never break an OKF reader.
- **AIX producers MUST also emit plain markdown body links** for every typed
  relationship (see §6.4). This guarantees an OKF-only consumer still sees the
  graph edge, even though it cannot see the edge's *type*.

The result: **publish once, consumed by both.** An OKF agent sees a valid OKF
bundle. An AIX agent sees the same bundle plus identity, edge types, richer
provenance, media identity, and federation.

Bundles authored against OKF v0.1 conventions (a `timestamp` field; a body
`# Citations` list) remain valid AIX input. Consumers MUST tolerate both
generations; producers SHOULD migrate to the v0.2 forms (`generated.at`,
`sources`).

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
aliases: [Payments API, PaymentSvc]

# OKF v0.2 trust & lifecycle (shared vocabulary — §7)
generated:
  by: agent:vault-exporter
  at: 2026-08-20T09:12:00Z
verified:
  - by: human:jane-doe
    at: 2026-08-20
status: active
stale_after: 2027-02-20
sources:
  - uri: https://internal.example.com/runbooks/payments
    title: Payments runbook

# AIX additions
provenance:
  confidence: high
  source: primary

links:
  - rel: depends-on
    to: orders-table
    note: Reads order totals to compute capture amounts.
  - rel: superseded-by
    to: payment-service-v2

media:
  - uri: ./assets/payment-flow.png
    hash: sha256:9f2c8a41d6…
    describes: payment-service
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

`type` is the only field required for **OKF Level 0** conformance (see §11).

### 5.2 Identity (AIX)

| Field | Type   | Rule   | Meaning |
|-------|--------|--------|---------|
| `id`  | string | SHOULD | A **stable identifier** that uniquely names the concept within the bundle. Lowercase; words separated by `-`. Once assigned, `id` MUST NOT change even if the file is renamed or moved. |

- If `id` is absent, consumers MUST fall back to the bundle-relative file path as
  the identity (OKF behaviour).
- `id` values MUST be unique within a bundle.
- `id` is the **preferred link target** (§6). Because identity is decoupled from
  path, files can be reorganised without breaking references — the defining fix
  AIX makes over OKF.
- `id` values MUST NOT contain `/`. The `/` character is reserved for
  federation-qualified references (§9).

### 5.3 Recommended (inherited from OKF)

| Field | Type | Meaning |
|-------|------|---------|
| `title` | string | Human-readable name. Consumers MAY derive from filename if absent. |
| `description` | string | Single-sentence summary for previews/search. |
| `resource` | string (URI) | Canonical URI of the underlying asset. Omitted for abstract concepts. |
| `tags` | list of string | Cross-cutting categorisation. |
| `generated` | map | Producer and time of last generation (OKF v0.2). `generated.at` replaces v0.1's `timestamp`. |
| `verified` | list of maps | Verification events with actor-prefixed `by` (OKF v0.2). |
| `sources` | list of maps | Provenance of the content (OKF v0.2). Replaces the v0.1 body `# Citations` list. |
| `status` | string | Lifecycle state (OKF v0.2), e.g. `active`, `deprecated`, `draft`. |
| `stale_after` | ISO 8601 date | Absolute date after which the content SHOULD be treated as stale (OKF v0.2). |
| `timestamp` | ISO 8601 datetime | **Deprecated** (OKF v0.1). Read as a fallback for `generated.at`; do not emit in new bundles. |

### 5.4 Recommended (AIX additions)

| Field | Type | Meaning |
|-------|------|---------|
| `aliases` | list of string | Alternative names/labels for the concept. Accumulate old paths and titles here on rename so history keeps resolving. |
| `provenance` | map | Trust metadata OKF does not carry (§7). |
| `links` | list of link objects | **Typed** relationships (§6). |
| `media` | list of media objects | Identity for binary assets the concept owns or references (§8). |

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
| `to` | string | MUST | Target concept: an `id` (preferred), a bundle-relative path, or a federation-qualified reference `namespace/id` (§9). |
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
| `describes` | `described-by` | Explains or documents the target (added in v0.2; the primary edge between documentation, media, and subject). |

Symmetric relationships (`relates-to`, `contradicts`) are their own inverse.

**Registered extension rels.** The following custom values are RECOMMENDED
spellings for common multimodal and operational edges, so independent producers
converge without the core vocabulary growing: `depicts` / `depicted-in` (a
visual asset shows the target), `remediates` / `remediated-by` (a runbook fixes
the target), `discusses` / `discussed-in` (a recording or thread covers the
target). Consumers without special handling treat them as `relates-to`, per the
rule above.

### 6.3 Inference of inverse edges

A consumer building a graph SHOULD synthesise the inverse edge for each declared
link, using the inverse column above, so that backlinks are available without
the producer writing every edge twice. Producers SHOULD declare each edge once,
from whichever side is more natural.

### 6.4 Body-link mirroring (OKF compatibility — MUST)

For every entry in `links` whose target is **inside the same bundle**, the
producer MUST also emit at least one **plain markdown link** to the same target
somewhere in the document body. This ensures OKF-only consumers — which read
only body links and know nothing of `links` — still discover the (untyped)
edge. AIX-aware consumers read `links` for the typed edge and MAY ignore the
redundant body link.

Federation-qualified links (§9) SHOULD be mirrored where a resolvable URI for
the target exists, and MAY be omitted from the body where none does.

A markdown body link whose target has **no** corresponding `links` entry is
treated as an untyped `relates-to` edge (OKF behaviour preserved).

---

## 7. Provenance and trust

v0.1 defined a self-contained `provenance` map. OKF v0.2 then standardised
overlapping trust fields. AIX v0.2 resolves the overlap in one direction:
**where OKF now defines a field, OKF's definition wins.** The AIX `provenance`
map shrinks to carry only what OKF still lacks.

### 7.1 The shared base (OKF v0.2, adopted as-is)

| Field | Meaning |
|-------|---------|
| `sources` | Where the content came from, as a list of `{uri, title, …}` maps. |
| `generated` | Which actor produced the content and when (`by`, `at`). Actor names use OKF's prefix convention: `human:`, `agent:`, `pipeline:`. |
| `verified` | A list of verification events (`by`, `at`). The actor prefix yields OKF's three trust tiers: unverified (empty/absent), machine-confirmed (`agent:`/`pipeline:`), human-reviewed (`human:`). |
| `status` | Lifecycle state. |
| `stale_after` | Absolute staleness date. Staleness is a plain date comparison, not a calculation. |

### 7.2 The AIX `provenance` map (what OKF lacks)

| Key | Values | Meaning |
|-----|--------|---------|
| `confidence` | `high` \| `medium` \| `low` | How authoritative the content is, independent of who verified it. |
| `source` | `primary` \| `secondary` \| `synthesis` \| `external` | The epistemic class of the content: first-hand, documented, compiled, or imported. Distinct from `sources`, which records *which* documents; this records *what kind* of knowledge. |

Producers MAY add custom provenance keys; consumers MUST preserve them.

### 7.3 Deprecated v0.1 keys (read, don't write)

| v0.1 key | v0.2 replacement | Consumer rule |
|----------|------------------|---------------|
| `provenance.verified` (boolean) | `verified` actor list | Read `true` as one machine-tier verification of unknown actor; read `false` as unverified. |
| `provenance.freshness` (band) | `stale_after` (date) | Read `stale` as past-stale; `current`/`recent` as not-yet-stale. |
| `provenance.reviewed` (date) | `verified[].at` | Read as the date of the most recent verification event. |
| `timestamp` | `generated.at` | Read as `generated.at` with unknown actor. |

Consumers MUST tolerate both generations. Validators SHOULD warn on the
deprecated forms without failing the bundle.

---

## 8. Media identity (new in v0.2)

Binary assets — diagrams, recordings, screenshots, notebooks — carry knowledge
that markdown cannot. OKF admits them only as URIs, which gives them no
identity: move the file, change hosts, or duplicate it and every reference is a
new opaque string. The `media` array fixes that.

Each entry in a concept's `media` list is a map:

| Key | Type | Rule | Meaning |
|-----|------|------|---------|
| `uri` | string | MUST | Where the asset currently lives (bundle-relative path or absolute URI). |
| `hash` | string | SHOULD | Content hash in `<algo>:<hex>` form (e.g. `sha256:…`). The hash — not the URI — is the asset's identity: stable across moves, hosts and renames, and deduplicable across bundles. |
| `title` | string | MAY | Human-readable label. |
| `describes` | string | MAY | The `id` (or `namespace/id`) of the concept the asset is about, when it is not the containing concept. |
| `embedding` | string (URI) | MAY | Pointer to a stored embedding of the asset's content — the hook a multimodal retrieval layer hangs off. AIX does not prescribe the embedding model or store. |

Rules:

- A media entry does **not** make the asset a concept. Knowledge *about* the
  asset lives in the containing concept's body, as prose.
- Two media entries with the same `hash` refer to the same asset, regardless of
  `uri`. Consumers deduplicating across a federation SHOULD key on `hash`.
- Consumers MUST tolerate absent `hash` (degrades to URI identity — OKF
  behaviour) and absent `embedding`.

---

## 9. Federation (new in v0.2)

One bundle is one team's knowledge. The value compounds when bundles from many
producers are consumed together — searched by one index, loaded into one graph —
**without** merging them into one repository. Federation is deliberately small:
a namespace, a reference syntax, and a place to declare shared vocabularies.
Agree on little; interoperate on everything.

### 9.1 Namespace

A bundle participating in a federation MUST declare a `namespace` in its
manifest (§10.3): a lowercase kebab-case string, unique within the federation,
stable for the life of the bundle. The namespace is an identifier, not a path;
renaming it breaks every inbound reference, exactly like renaming an `id`.

### 9.2 Qualified references

A `to` value containing a `/` is a **federation-qualified reference**:
`<namespace>/<id>`, pointing at a concept in another bundle.

```yaml
links:
  - rel: depends-on
    to: data-eng/orders-table
    note: Owned by the data engineering bundle.
```

- Within a bundle, unqualified `id` references remain the norm. Producers MUST
  NOT qualify same-bundle references.
- Consumers that only hold one bundle MUST treat unresolvable qualified
  references as tolerable broken links (§11.1), not errors.
- This is also why wiki-style `[[links]]` do not survive federation: they
  resolve by filename, and filenames collide the moment two teams both write a
  note called `customers`. Authoring tools MAY offer wikilinks in the editor
  but MUST compile them to ids or paths before publishing.

### 9.3 Shared vocabularies

Cross-bundle interoperability needs exactly two agreements: what the `type`
values mean, and what the `rel` values mean. A federation SHOULD version these
as machine-readable documents in a small repository of their own, and each
bundle SHOULD point at the versions it targets from its manifest:

```yaml
vocabularies:
  types: https://example.com/federation/types-v3.json
  rels: https://example.com/federation/rels-v2.json
```

AIX does not prescribe the document format beyond: a flat list of permitted
values with one-line definitions. A dozen types and a dozen rels is very nearly
the entire cross-team agreement.

### 9.4 Trust across bundles

Because AIX adopts OKF v0.2's `generated`/`verified` semantics unchanged (§7.1),
trust tiers mean the same thing in every bundle of a federation. A consumer
reading five teams' bundles can prefer a human-verified concept over an
unverified one while knowing nothing about the five teams. Producers MUST NOT
redefine the actor-prefix convention within a federation.

---

## 10. Reserved files

### 10.1 `index.md` (OKF)

- MUST NOT contain frontmatter.
- Groups concepts under section headings with relative links and short
  descriptions, enabling progressive disclosure of a large bundle.

### 10.2 `log.md` (OKF)

- Flat list of date-grouped entries, newest first.
- Date headings use `YYYY-MM-DD`. Entries are prose, optionally prefixed
  (`**Creation**`, `**Update**`, …).

### 10.3 `manifest.aix.yaml` (AIX, optional)

A single YAML file at the **bundle root** describing the bundle as a whole. It
is not a concept and does not affect OKF conformance (OKF ignores non-`.md`
files). Recommended keys:

```yaml
aix: "0.2"                     # spec version this bundle targets
name: my-bundle                # bundle identifier
namespace: my-bundle           # federation namespace (§9) — required at Level 3
description: One-line summary of the bundle.
producer: aix-export/1.0       # tool or person that generated it
generated: 2026-08-20T09:12:00Z
conformance: 2                 # highest level the producer claims (§11)
vocabularies:                  # shared vocabulary pointers (§9.3)
  types: https://example.com/federation/types-v3.json
  rels: https://example.com/federation/rels-v2.json
counts:                        # optional, informational
  concepts: 42
```

`name` and `namespace` are usually identical; they are separate keys because
`name` is descriptive and MAY change, while `namespace` is referential and MUST
NOT.

---

## 11. Conformance levels

AIX defines a ladder so producers can adopt incrementally. A bundle's level is
the highest it fully satisfies.

| Level | Name | Requirements |
|-------|------|--------------|
| **0** | OKF-compatible | Valid OKF bundle: every non-reserved `.md` has parseable frontmatter with a non-empty `type`; reserved files follow their structures. |
| **1** | AIX Core | Level 0, **plus** every concept has a unique `id`, **plus** a root `manifest.aix.yaml` declaring `aix` and `name`. |
| **2** | AIX Full | Level 1, **plus** every `links` entry uses a valid link object (`rel` + resolvable `to`) and same-bundle links are mirrored by a body link (§6.4), **plus** every concept carries trust signals — a `provenance` map (§7.2) or at least one OKF v0.2 trust field (§7.1), **plus** every `media` entry (if any) carries a `uri`. |
| **3** | AIX Federated | Level 2, **plus** the manifest declares a valid `namespace`, **plus** every cross-bundle reference is federation-qualified (§9.2), **plus** the manifest declares `vocabularies` (§9.3). |

### 11.1 Consumer obligations (all levels)

A conformant consumer:

- MUST NOT reject a bundle for: missing optional fields, unknown `type` values,
  unknown frontmatter keys, unknown `rel` values, broken links, unresolvable
  qualified references, or a missing `index.md`/`manifest.aix.yaml`.
- MUST treat a broken link as tolerable — it MAY denote not-yet-written
  knowledge or a bundle the consumer does not hold.
- SHOULD resolve link targets by `id` first, then by bundle-relative path;
  qualified references resolve by namespace first (§9.2).
- SHOULD synthesise inverse edges (§6.3).
- MUST preserve unknown keys when round-tripping a document.
- MUST tolerate v0.1-generation fields per the mapping in §7.3.

This permissive model is what keeps AIX useful while bundles evolve and agents
generate content.

---

## 12. Portability note

AIX defines a *format*, not a policy. Content sensitivity, redaction, and
outbound-sharing rules are the **producer's** responsibility and out of scope
for this spec. Producers exporting into AIX for external exchange SHOULD apply
their own sanitisation before publishing a bundle — and SHOULD remember that
`media` assets and `sources` URIs leak context just as body prose does.

---

## 13. Versioning

Bundles declare the version they target via `manifest.aix.yaml`'s `aix` key.
Minor versions remain readable by earlier consumers under the permissive rules
of §11.1.

### Changelog — v0.2 (2026-08-20)

**Rebased:**

- Compatibility contract now targets **OKF v0.2** (was v0.1). OKF's trust and
  lifecycle fields (`sources`, `generated`, `verified`, `status`,
  `stale_after`) are adopted as the shared base (§7.1).

**Deprecated** (read, don't write — §7.3):

- `provenance.verified`, `provenance.freshness`, `provenance.reviewed`,
  `timestamp` — each superseded by an OKF v0.2 field.

**Added:**

- `media` array: content-hash identity and embedding pointers for binary
  assets (§8).
- Federation: manifest `namespace`, qualified `namespace/id` references,
  shared vocabulary declarations, cross-bundle trust semantics (§9).
- `describes` / `described-by` added to the core relationship vocabulary;
  `depicts`, `remediates`, `discusses` registered as recommended extension
  rels (§6.2).
- Conformance **Level 3 — AIX Federated** (§11).
- `id` values MUST NOT contain `/` (reserved for qualified references).

**Unchanged:**

- The superset contract, stable identity, typed relationships with body-link
  mirroring, the permissive consumer model, and the "just files" constraint.

### v0.1 (2026-07-18)

Initial draft: stable `id`, typed `links` with inverse inference and body-link
mirroring, self-contained `provenance` map, `manifest.aix.yaml`, conformance
Levels 0–2.

---

## Appendix A — minimal conformant concept (Level 0)

```markdown
---
type: Note
---

# Anything

Body is free-form.
```

## Appendix B — full concept (Level 2+)

See the worked bundle in [`examples/`](./examples/) — the bundle passes the
reference validator in [`tools/aix-validate.py`](./tools/aix-validate.py) at
Level 3 and demonstrates OKF v0.2 trust fields, media identity, and a
federation-qualified link.
