# AI-XF — AI eXchange Format

**Version:** 0.4
**Status:** Draft
**Date:** 2026-09-26
**Supersedes:** v0.3 (2026-09-21)

AI-XF is an open, vendor-neutral format for representing curated knowledge so that
humans and AI agents can produce and consume it without a translation layer. It
is a **strict superset of the Open Knowledge Format (OKF) v0.2**: every
conformant AI-XF bundle is also a conformant OKF bundle, so AI-XF content degrades
gracefully to OKF-only consumers while AI-XF-aware consumers get a richer model —
**stable identity, typed relationships, provenance, media identity,
federation, and change semantics**.

> The keywords MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are used as defined in
> RFC 2119.

---

## 1. Why AI-XF exists

OKF proved that a directory of markdown files with YAML frontmatter is enough to
make knowledge portable. OKF v0.2 (2026-07-25) added trust and lifecycle
signals — `sources`, `generated`, `verified`, `status`, `stale_after` — which
closed one of the three gaps AI-XF v0.1 identified. Two gaps remain open, scale
has exposed two more, and use has exposed a fifth:

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
5. **Change.** Every field above describes a concept *at rest*. None records
   what happened when new knowledge met old: that two concepts disagree and
   nobody has ruled yet, that two concepts were merged, that a claim gained or
   lost support. A knowledge base compounds only when new material changes
   existing concepts, and a format that cannot express that change cannot show
   whether it is happening.

AI-XF adds exactly these capabilities and nothing else load-bearing. It stays
"just markdown + YAML + files": readable without tooling, diffable in version
control, parseable without a bespoke SDK, portable across tools and time.

---

## 2. Relationship to OKF (the compatibility contract)

AI-XF v0.3 is defined as a superset of **OKF v0.2**. The contract is:

- **Every AI-XF concept file MUST be a valid OKF concept file** — parseable YAML
  frontmatter with a non-empty `type` field.
- **AI-XF adopts OKF v0.2's trust and lifecycle fields as-is** (`sources`,
  `generated`, `verified`, `status`, `stale_after`), including their value
  vocabularies, the actor convention, and per-claim footnote attribution. AI-XF
  does not redefine them; it builds on them (§7).
- **All AI-XF-specific data lives in frontmatter keys or an inline link
  convention that OKF consumers preserve or ignore.** OKF's conformance rules
  require consumers to preserve unknown keys and tolerate unknown content, so
  AI-XF extensions never break an OKF reader.
- **AI-XF producers MUST also emit plain markdown body links** for every typed
  relationship (see §6.4). This guarantees an OKF-only consumer still sees the
  graph edge, even though it cannot see the edge's *type*.

The result: **publish once, consumed by both.** An OKF agent sees a valid OKF
bundle. An AI-XF agent sees the same bundle plus identity, edge types, richer
provenance, media identity, federation, and change semantics.

Bundles authored against OKF v0.1 conventions (a `timestamp` field; a body
`# Citations` list) remain valid AI-XF input. Consumers MUST tolerate both
generations; producers SHOULD migrate to the v0.2 forms (`generated.at`,
`sources`).

---

## 3. Bundle structure

An AI-XF **bundle** is a directory tree of markdown **concept** files plus
optional reserved files.

```
my-bundle/
├── manifest.ai-xf.yaml        # optional bundle manifest (AI-XF)
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
  bundle root only, `manifest.ai-xf.yaml` (AI-XF). Reserved files are never
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
  by: vault-exporter/1.0
  at: 2026-08-20T09:12:00Z
verified:
  - by: human:jane-doe
    at: 2026-08-20T00:00:00Z
status: deprecated
stale_after: 2027-02-20T00:00:00Z
sources:
  - id: payments-runbook
    resource: https://internal.example.com/runbooks/payments
    title: Payments runbook

# AI-XF additions
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
Capture is synchronous.[^payments-runbook]

[^payments-runbook]: Payments runbook
```

Note that the two links in the body mirror the two typed `links` entries — that
is the OKF-compatibility rule from §2. The footnote label is a `sources[].id`:
OKF v0.2's per-claim attribution, which AI-XF inherits unchanged (§7.4).

---

## 5. Fields

### 5.1 Required

| Field  | Type   | Rule | Meaning |
|--------|--------|------|---------|
| `type` | string | MUST | Kind of concept (e.g. `Concept`, `System`, `Metric`, `Runbook`). Not centrally registered; consumers MUST handle unknown values gracefully. |

`type` is the only field required for **OKF Level 0** conformance (see §11).

### 5.2 Identity (AI-XF)

| Field | Type   | Rule   | Meaning |
|-------|--------|--------|---------|
| `id`  | string | SHOULD | A **stable identifier** that uniquely names the concept within the bundle. Lowercase; words separated by `-`. Once assigned, `id` MUST NOT change even if the file is renamed or moved. |

- If `id` is absent, consumers MUST fall back to the bundle-relative file path as
  the identity (OKF behaviour).
- `id` values MUST be unique within a bundle.
- `id` is the **preferred link target** (§6). Because identity is decoupled from
  path, files can be reorganised without breaking references — the defining fix
  AI-XF makes over OKF.
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
| `sources` | list of maps | Provenance of the content (OKF v0.2): each entry has a REQUIRED `resource` and an optional `id` used as a footnote label for per-claim attribution (§7.4). Replaces the v0.1 body `# Citations` list. |
| `status` | string | Lifecycle state (OKF v0.2): `draft`, `stable` or `deprecated`. Absent ⇒ `stable`. |
| `stale_after` | ISO 8601 datetime (§5.6) | Absolute instant from which the content SHOULD be treated as stale (OKF v0.2). |
| `timestamp` | ISO 8601 datetime | **Deprecated** (OKF v0.1). Read as a fallback for `generated.at`; do not emit in new bundles. |

### 5.4 Recommended (AI-XF additions)

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

### 5.6 Timestamps (v0.4.3)

Every timestamp-valued key is an **ISO 8601 datetime with an explicit UTC
offset**, for example `2026-06-30T14:00:00Z`. This is OKF's rule since its
PR #6 (2026-08-21) for `generated.at`, `verified[].at`, `stale_after`,
`sources[].last_modified` and `usage_window.from`/`to`; AI-XF applies it to its
own timestamps too (`links[].at`, `links[].resolved.at`, `links[].verified[].at`).
A bare date names a different instant in every timezone, so the same concept
could be stale in one office and fresh in another.

- Producers MUST write the datetime form.
- Consumers MUST still read a bare date, or a datetime with no offset, as
  that date or time in UTC (a date as `T00:00:00Z`). Validators SHOULD warn.
  This is the usual rule for older spellings: read, don't write (§7.3).
- `log.md` date headings are not field values and stay `YYYY-MM-DD` (§10.2).
- When converting old dates, keep events in order. A verification read as
  `T00:00:00Z` lands *before* content generated later that day, and a consumer
  comparing `verified[].at` with `generated.at` will then read the content as
  changed since it was checked (OKF §5.2 makes `generated.at` the last
  meaningful change). E9 found exactly this in this repository's own examples.

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
| `by` | string | MAY | The actor that asserted this edge, in OKF's actor convention (§7.1). Lets a consumer tell an edge a person drew from one an agent inferred. *(v0.3)* |
| `at` | ISO 8601 datetime (§5.6) | MAY | When the edge was asserted. *(v0.3)* |
| `state` | `open` \| `resolved` | MAY | Lifecycle of a `contradicts` edge (§6.5). Meaningless on other rels; consumers MUST ignore it there. *(v0.3)* |
| `resolved` | map | MAY | How a contradiction was settled: `by`, `at`, and optional `outcome` (§6.5). *(v0.3)* |
| `verified` | list of maps | MAY | Verification events for **this edge**, same shape and actor convention as the concept-level field (§7.1). An edge's trust tier is derived from it exactly as a concept's is; an edge with no `verified` is unverified even when its concept is human-reviewed. *(v0.4)* |

A link asserts a **directed** edge from the containing concept to `to`.

### 6.2 Relationship vocabulary

AI-XF defines a **core vocabulary** of `rel` values with defined inverses.
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
| `contradicts` | `contradicts` | Known conflict (symmetric). Carries a lifecycle (§6.5). |
| `supports` | `supported-by` | The containing concept is evidence for the target (added in v0.3). The counterpart to `contradicts`: together they let a consumer see how a claim stands. |
| `merged-into` | `merged-from` | The containing concept was absorbed by the target and is now a tombstone (added in v0.3; §6.6). |
| `split-from` | `split-into` | The containing concept was carved out of the target (added in v0.3; §6.6). |
| `imported` | `exported-to` | The containing concept is a copy of, or was derived from, the target in another bundle (added in v0.4; §9.6). The copy does **not** inherit the target's trust tier. |
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
edge. AI-XF-aware consumers read `links` for the typed edge and MAY ignore the
redundant body link.

Federation-qualified links (§9) SHOULD be mirrored where a resolvable URI for
the target exists, and MAY be omitted from the body where none does.

A markdown body link whose target has **no** corresponding `links` entry is
treated as an untyped `relates-to` edge (OKF behaviour preserved).

### 6.5 Contradiction lifecycle (new in v0.3)

A contradiction is the most valuable signal a curated knowledge base produces,
and the easiest to destroy: an agent asked to integrate new material will, by
default, rewrite the old text until everything agrees again. v0.2 said the
resolution "SHOULD be in prose", which left a bundle unable to answer the basic
question *which disagreements are still open?* v0.3 gives the edge a state.

```yaml
links:
  - rel: contradicts
    to: orders-db-is-not-the-bottleneck
    state: open
    by: curator/1.0
    at: 2026-09-21T00:00:00Z
    note: Load test on 2026-09-18 shows headroom on the orders database.
```

- A `contradicts` edge with no `state` MUST be read as `open`.
- Producers recording a contradiction SHOULD keep **both** concepts intact and
  MUST NOT silently reconcile their text as a substitute for the edge.
- To settle it, set `state: resolved` and add a `resolved` map:

```yaml
    state: resolved
    resolved:
      by: human:jane-doe
      at: 2026-09-25T00:00:00Z
      outcome: superseded      # superseded | reconciled | both-stand
```

| `outcome` | Meaning |
|-----------|---------|
| `superseded` | One side won. The winner SHOULD carry a `supersedes` edge to the loser, and the loser `status: deprecated`. |
| `reconciled` | Both concepts were edited so they no longer conflict. |
| `both-stand` | The conflict is real and accepted (different contexts, open science). The explanation belongs in `note` or the body. |

- `resolved.by` follows the same logic as trust tiers (§7.1): a consumer MAY
  treat a contradiction resolved only by a non-`human:` actor as still open.
  The tier is *derived* by the consumer, not mandated on the producer.
- Because `contradicts` is symmetric and SHOULD be declared once (§6.3), the
  state lives on the declaring side. If both sides declare the edge and their
  states disagree, consumers MUST treat the contradiction as `open`.

### 6.6 Merge, split, and redirects (new in v0.3)

Stable identity (§5.2) says an `id` never changes. Curation still merges two
concepts that turn out to be one, and splits one that turns out to be two. The
rules below keep every historical reference resolving.

**Merge.** When concept B is absorbed into concept A:

- B's file SHOULD remain as a **tombstone**: `status: deprecated`, a
  `merged-into` link to A, and a body link to A (§6.4). Its body MAY be reduced
  to that one line.
- B's `id` MUST NOT be reused for a different concept.
- A SHOULD add B's title and aliases to its own `aliases`, so search by the old
  name lands on the survivor.
- If B's file is deleted instead, A MUST list B's `id` in `aliases`; consumers
  resolving an unknown `id` SHOULD fall back to an `aliases` match.

**Split.** When concept C is carved out of concept A, C declares
`split-from: A`. A keeps its `id`. Nothing is deprecated.

**Retirement (v0.4.3).** A concept that leaves a bundle SHOULD become a
tombstone rather than disappear: `status: deprecated`, a `superseded-by` or
`merged-into` edge when it has a successor, and a `Deprecation` (or `Merge`)
entry in `log.md`. A producer that regenerates a bundle from another source,
such as an exporter, SHOULD do this itself on every run, retiring any concept
whose source has left the export. Deleting the file instead makes a removed
concept indistinguishable from one that was never written, and a regenerating
producer that never deletes leaves removed concepts live, with links still
resolving to them; both were measured in `experiments/e8-freshness/`. A rename
keeps the `id` (§5.2); where a producer cannot keep it, the old `id` becomes a
tombstone with a `superseded-by` edge to the new one, and the new concept lists
the old `id` in `aliases`.

**Redirects.** When a consumer resolves a reference to a concept whose `status`
is `deprecated` and which declares exactly one `superseded-by` or `merged-into`
edge, it SHOULD surface the successor alongside (or instead of) the deprecated
concept. Consumers following successor chains MUST guard against cycles. A
deprecated concept with no successor edge is simply retired; that is valid.

---

## 7. Provenance and trust

v0.1 defined a self-contained `provenance` map. OKF v0.2 then standardised
overlapping trust fields. AI-XF v0.2 resolves the overlap in one direction:
**where OKF now defines a field, OKF's definition wins.** The AI-XF `provenance`
map shrinks to carry only what OKF still lacks.

### 7.1 The shared base (OKF v0.2, adopted as-is)

| Field | Meaning |
|-------|---------|
| `sources` | Where the content came from, as a list of maps. `resource` is REQUIRED per entry; `id`, `title` and OKF's credibility signals (`author`, `usage_count`, `last_modified`) are optional. One entry MAY instead be a `withheld` marker (§7.6). |
| `generated` | Which actor produced the content and when (`by`, `at`). Actors use OKF's convention: `<producer>/<version>` for agents and tools, `human:<id>` for a person, `process:<id>` for an automated process. |
| `verified` | A list of verification events (`by`, `at`); a single bare map is read as a one-element list. The actor yields OKF's three trust tiers: unverified (absent), machine-confirmed (non-`human:` actors only), human-reviewed (any `human:` actor). |
| `status` | Lifecycle state: `draft`, `stable` (the default when absent) or `deprecated`. |
| `stale_after` | Absolute staleness instant (§5.6). Staleness is a plain comparison, `now >= stale_after`, not a calculation. |

### 7.2 The AI-XF `provenance` map (what OKF lacks)

| Key | Values | Meaning |
|-----|--------|---------|
| `confidence` | `high` \| `medium` \| `low` | How authoritative the content is, independent of who verified it. |
| `source` | `primary` \| `secondary` \| `synthesis` \| `external` | The epistemic class of the content: first-hand, documented, compiled, or imported. Distinct from `sources`, which records *which* documents; this records *what kind* of knowledge. |

Producers MAY add custom provenance keys; consumers MUST preserve them.

`confidence` is an **asserted** signal, and asserted signals drift: in the vault
AI-XF was extracted from, 303 of 413 labelled notes claimed `high` and 10 claimed
`low`, at which point the label no longer discriminates. OKF declines to store a
credibility score for the same reason. Consumers SHOULD therefore rank on
*derived* signals first — trust tier, `stale_after`, `supports` and open
`contradicts` edges — and treat `confidence` as a tie-breaker. Producers SHOULD
review the distribution across a bundle; the reference validator's `--stats`
reports it and flags a lopsided one.

### 7.3 Deprecated v0.1 keys (read, don't write)

| v0.1 key | v0.2 replacement | Consumer rule |
|----------|------------------|---------------|
| `provenance.verified` (boolean) | `verified` actor list | Read `true` as one machine-tier verification of unknown actor; read `false` as unverified. |
| `provenance.freshness` (band) | `stale_after` (date) | Read `stale` as past-stale; `current`/`recent` as not-yet-stale. |
| `provenance.reviewed` (date) | `verified[].at` | Read as the date of the most recent verification event. |
| `timestamp` | `generated.at` | Read as `generated.at` with unknown actor. |
| any timestamp written as a bare date | the same key as a datetime with offset (§5.6) | Read as `T00:00:00Z` on that date. |

Consumers MUST tolerate both generations. Validators SHOULD warn on the
deprecated forms without failing the bundle.

AI-XF v0.2's own examples also drifted from OKF in three spellings. v0.3 corrects
them; consumers MUST still read the old forms, and validators SHOULD warn:

| AI-XF v0.2 spelling | Correct OKF v0.2 form |
|-------------------|-----------------------|
| `status: active` | `status: stable` |
| `sources[].uri` | `sources[].resource` |
| `agent:<id>` / `pipeline:<id>` actors | `<producer>/<version>` / `process:<id>` |

### 7.3a Trust survives transport, not ingestion (v0.4)

Every field in §7.1 and §7.2 is plain text in frontmatter, and experiment E5
found that anything which moves a bundle as bytes (git, rsync, file sync)
preserves all of them byte-for-byte. What degrades trust is *ingestion*: a tool
that parses the file and writes its own representation keeps only the keys it
models. A tool modelling the whole schema merely normalises formatting; a tool
modelling seven keys of fifteen silently drops the rest, and the dropped ones
are exactly the trust fields (`verified`, `provenance`, contradiction state,
`media`).

Therefore an ingesting consumer MUST do one of two things: round-trip unknown
keys opaquely (§5.5 already requires this of a *conformant* consumer), or
document which keys it drops so a producer can judge whether trust survives.
A count of "keys carried" is not that documentation unless the bundle's key
count stands beside it. Frontmatter comments never survive a YAML round trip;
producers MUST NOT put load-bearing information in them.

### 7.4 Per-claim attribution (inherited from OKF)

`sources` attaches evidence to a whole concept. To attach it to one sentence,
OKF v0.2 uses a markdown footnote whose label is a `sources[].id`:

```markdown
Capture is synchronous.[^payments-runbook]

[^payments-runbook]: Payments runbook
```

AI-XF inherits this unchanged and adds one recommendation: concepts whose content
an agent may rewrite SHOULD cite per claim, not only per concept. Each rewrite
is a paraphrase, and paraphrase compounds error as readily as insight; a claim
that still points at its source can be re-checked, and a page of such claims can
be rebuilt from evidence rather than from its own previous draft.

### 7.5 Withheld sources (new in v0.4)

A bundle served across a trust boundary may have to remove `sources` entries
it cannot disclose. A silently shorter list looks complete, which
misrepresents provenance; disclosing everything leaks what was meant to stay
private. So a serving party that removes entries MUST replace them with one
marker entry naming only the count:

```yaml
sources:
  - id: q2-review
    resource: https://internal.example.com/reviews/2026-q2
    title: Q2 capacity review
  - withheld: 2
```

- A `withheld` entry has no `resource` and MUST NOT be resolved or cited.
- Consumers deriving trust SHOULD surface the count; a concept with withheld
  sources is not less verified, but its provenance is declared incomplete.
- This closes only the field; a source named in prose has already been
  disclosed. Proposed in OKF issue #32; AI-XF adopts it, which narrows §12: the
  format now has one word for redaction, and the policy of *what* to withhold
  stays the producer's.

### 7.6 Claims (recommended type, new in v0.3)

A concept titled as a topic ("Voice latency") can only grow longer. A concept
titled as a falsifiable statement ("Sub-200 ms voice replies need on-device
processing") can be supported, contradicted or superseded, which is what gives
the edges of §6.2 something to act on. Producers SHOULD use `type: Claim` for
such concepts and keep topic concepts as maps that link to them. `Claim` is a
recommended `type` value, not a registered one; §5.1 still applies.

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
| `embedding` | string (URI) | MAY | Pointer to a stored embedding of the asset's content — the hook a multimodal retrieval layer hangs off. AI-XF does not prescribe the embedding model or store. |

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

**Explicit form (v0.4).** `ai-xf://<namespace>/<id>` is an equivalent spelling of
the qualified reference, for use where a bare `namespace/id` would be read as a
path: markdown body links, authoring tools, URLs in MCP payloads. Consumers MUST
accept both spellings everywhere a `to` value or body link is read, and a body
link in the explicit form satisfies the mirroring rule (§6.4) for the matching
typed link.

```markdown
See the [orders event stream](ai-xf://data-eng/orders-events).
```

**Resolution of unqualified references in a federation (v0.4).** A consumer
holding several bundles resolves an unqualified `to: <id>` as follows:

1. In the containing bundle. If found, resolution is silent and final, even if
   other held bundles also define that `id`.
2. Otherwise, in the other held bundles in alphabetical order of namespace.
   The first match wins, **and the consumer MUST emit a warning** that names
   every namespace in which the `id` was found and the one chosen, and
   recommends qualifying the reference. Resolution across a bundle boundary is
   never silent.
3. Otherwise, a tolerable broken link (§11.1).

A reference resolved by step 2 is a cross-bundle reference for the purposes of
§6.4 (mirroring is SHOULD, not MUST). This is the rule established by the Foam
knowledge tool for multi-root workspaces; it was adopted after experiment E2
showed it produces zero silent misresolutions on deliberately colliding
fixtures.

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

AI-XF does not prescribe the document format beyond: a flat list of permitted
values with one-line definitions. A dozen types and a dozen rels is very nearly
the entire cross-team agreement.

### 9.4 Trust across bundles

Because AI-XF adopts OKF v0.2's `generated`/`verified` semantics unchanged (§7.1),
trust tiers mean the same thing in every bundle of a federation. A consumer
reading five teams' bundles can prefer a human-verified concept over an
unverified one while knowing nothing about the five teams. Producers MUST NOT
redefine the actor-prefix convention within a federation.

### 9.5 The federation manifest (new in v0.4)

A consumer that holds several bundles SHOULD keep a `federation.ai-xf.yaml`
describing what it holds and where each bundle came from:

```yaml
ai-xf: "0.4"
federation: example-federation
vocabularies:                       # federation-wide (§9.3); bundles MAY override
  types: ./vocab/types-v1.json
  rels:  ./vocab/rels-v1.json
bundles:
  - namespace: example-payments
    source: git
    repo: https://github.com/DavidROliverBA/ai-xf-format
    ref: 1408535                     # the exact commit held
    subdir: examples                 # bundle root, relative to the repo root
  - namespace: data-eng
    source: path
    path: ./data-eng                 # relative to this file
  - namespace: vendor-kb
    source: oci
    ref: registry.example.com/kb/vendor-kb:2026-09
    digest: sha256:9308e291b9057189c894f1d36d7f93424f08364c556603854c3cdb5b673976df
```

- `namespace` MUST equal the `namespace` in the bundle's own `manifest.ai-xf.yaml`.
- `source: oci` names a bundle distributed as an OCI artifact (Appendix C).
  `digest` is the artifact's manifest digest and is the provenance field, as
  `ref` is for git. A bundle's own `manifest.ai-xf.yaml` MUST NOT carry its own
  digest: the manifest is inside the hashed content, so writing the digest
  there changes it. The digest lives in the document that references the
  bundle, exactly as OCI keeps signatures outside the artifact they sign.
- `subdir` (git sources) is the bundle root relative to the root of the
  repository that holds it; `path` (path sources) is relative to the federation
  manifest. Both point at the directory containing `manifest.ai-xf.yaml`.
- Two entries MUST NOT share a `namespace`.
- `ref` and `digest` are strings. Quote a short git SHA that happens to be all
  digits (`ref: "1408535"`), or a YAML parser will read it as a number.

**What the manifest is for.** Experiment E1 showed that a consumer can resolve
every cross-bundle reference *without* a federation manifest: each bundle's own
`manifest.ai-xf.yaml` travels with it, so a scan of the tree recovers every
namespace. What a scan cannot recover is **provenance**: which commit of each
bundle is held. So the rule is: consumers MAY discover bundle roots by scanning
for `manifest.ai-xf.yaml`; a consumer that claims reproducible provenance MUST
hold a federation manifest (or an equivalent from which one can be generated,
such as git's `.gitmodules` plus submodule commits) with a `ref` per bundle.

A git repository whose bundles are submodules already carries this information;
a tool MAY generate `federation.ai-xf.yaml` from `.gitmodules` and
`git submodule status`, and E1 did so.

### 9.6 Importing a concept from another bundle (new in v0.4)

Sometimes a bundle needs its own copy of a concept another bundle owns: to work
offline, to freeze a version, or to annotate it locally. The copy MUST declare
where it came from with an `imported` link:

```yaml
links:
  - rel: imported
    to: data-eng/orders-events
    at: 2026-09-26T00:00:00Z
    note: Copied at data-eng ref 7adc76e for offline use.
```

- The copy keeps its own `id`, `generated` and `verified`. It does **not**
  inherit the source's trust tier: `verified` on the copy records who verified
  *the copy*. A consumer that wants the source's trust follows the link.
- The copy SHOULD carry the source's `stale_after` or an earlier instant, never a
  later one.
- This is the answer AI-XF gives to OKF issue #15.

### 9.7 Indexing a federation (non-normative, v0.4)

Whatever index a consumer builds over several bundles SHOULD carry `namespace`
and `id` as fields on every indexed document and SHOULD return `namespace/id`
with every hit. Experiment E3 compared a hybrid, LLM-reranked index using
collections as namespaces against a plain BM25 index carrying `namespace` as a
document field, on twenty questions over three bundles with two deliberate id
collisions. Only the index with the field on the document put the right
concept first for every collision question, in both runs. A collection label
identifies a hit after ranking; it does not help the ranker tell two
same-named concepts apart.

### 9.8 Serving a federation over MCP (non-normative, v0.4)

A server exposing bundles to agents SHOULD use tools (`list`, `search`,
`get`), not resources or roots, since only some clients consume resources and
roots are deprecated in the 2026-07-28 MCP specification. Every item in every
response SHOULD carry `namespace`, `id` and `ref: "namespace/id"`; `get` SHOULD
return frontmatter verbatim, including `links`, and the provenance `ref` of the
bundle it came from. Identity has to travel in the payload: nothing in the
transport namespaces it. Experiment E4's server (`experiments/e4-mcp/`) is a
minimal reference. E4 measured that the contract holds end to end (a
deterministic search-then-get pass put the right `namespace/id` on top for
18 of 20 questions and all four collision questions); it did not measure
whether an agent answers correctly through it. That is future work, not a
claim of this section.

---

## 10. Reserved files

### 10.1 `index.md` (OKF)

- MUST NOT contain frontmatter, with OKF's one exception: a bundle-root
  `index.md` MAY carry an `okf_version` key.
- Groups concepts under section headings with relative links and short
  descriptions, enabling progressive disclosure of a large bundle.

### 10.2 `log.md` (OKF)

- Flat list of date-grouped entries, newest first.
- Date headings use `YYYY-MM-DD`. Entries are prose, optionally prefixed
  (`**Creation**`, `**Update**`, …).

**AI-XF log vocabulary (new in v0.3).** OKF leaves the leading bold word as a
convention. AI-XF fixes a small vocabulary for it, so that a bundle can report its
own curation activity without reference to version control. The log remains a
valid OKF log.

| Leading word | Records |
|--------------|---------|
| `Initialization` | The bundle or directory was created. |
| `Creation` | A new concept. |
| `Update` | New material changed an existing concept. |
| `Merge` | One concept was absorbed into another (§6.6). |
| `Split` | One concept was carved out of another (§6.6). |
| `Deprecation` | A concept was retired or superseded. |
| `Contradiction` | A `contradicts` edge was opened (§6.5). |
| `Resolution` | A contradiction was resolved. |
| `Gap` | A question the bundle could not answer. A reading list, not a change. |

Producers SHOULD write one entry per concept affected, SHOULD reference the
concept by markdown link or backticked `id`, and SHOULD name the source that
prompted the change. The ratio of `Update` to `Creation` entries over a period
is the simplest available measure of whether a bundle is compounding or merely
accumulating. Entries with an unknown leading word are valid and uncounted.

**Merge ownership (v0.4).** When a bundle is produced in parts, or regenerated
by a tool, the reserved files at any directory shared by more than one part
(the bundle root above all) belong to the *merging* producer, not to any part.
`log.md` is **read-then-add, never regenerate**: a merge MUST carry forward
every existing entry and append its own. `manifest.ai-xf.yaml` and a root
`index.md` MUST preserve any existing version keys and hand-written text. A
merge that regenerates the root log silently discards every `Resolution`,
`Merge` and `Deprecation` it recorded, and a conformance check of the file's
*shape* will not notice. This is the rule the OKF community converged on in
issue #26; AI-XF needs it more, because its log vocabulary carries decisions.

### 10.3 `manifest.ai-xf.yaml` (AI-XF, optional)

A single YAML file at the **bundle root** describing the bundle as a whole. It
is not a concept and does not affect OKF conformance (OKF ignores non-`.md`
files). Recommended keys:

```yaml
ai-xf: "0.4"                     # spec version this bundle targets
name: my-bundle                # bundle identifier
namespace: my-bundle           # federation namespace (§9) — required at Level 3
description: One-line summary of the bundle.
producer: ai-xf-export/1.0       # tool or person that generated it
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

AI-XF defines a ladder so producers can adopt incrementally. A bundle's level is
the highest it fully satisfies.

| Level | Name | Requirements |
|-------|------|--------------|
| **0** | OKF-compatible | Valid OKF bundle: every non-reserved `.md` has parseable frontmatter with a non-empty `type`; reserved files follow their structures. |
| **1** | AI-XF Core | Level 0, **plus** every concept has a unique `id`, **plus** a root `manifest.ai-xf.yaml` declaring `ai-xf` and `name`. |
| **2** | AI-XF Full | Level 1, **plus** every `links` entry uses a valid link object (`rel` + resolvable `to`) and same-bundle links are mirrored by a body link (§6.4), **plus** every concept carries trust signals — a `provenance` map (§7.2) or at least one OKF v0.2 trust field (§7.1), **plus** every `media` entry (if any) carries a `uri`, **plus** any link `state` is `open` or `resolved` and any `resolved` map carries `by` (§6.5). |
| **3** | AI-XF Federated | Level 2, **plus** the manifest declares a valid `namespace`, **plus** every cross-bundle reference is federation-qualified (§9.2), **plus** the manifest declares `vocabularies` (§9.3). |

### 11.1 Consumer obligations (all levels)

A conformant consumer:

- MUST NOT reject a bundle for: missing optional fields, unknown `type` values,
  unknown frontmatter keys, unknown `rel` values, broken links, unresolvable
  qualified references, or a missing `index.md`/`manifest.ai-xf.yaml`.
- MUST treat a broken link as tolerable. It may denote knowledge not yet
  written, a concept removed without a tombstone, or a bundle the consumer
  does not hold; a consumer MUST NOT report which of these it is unless the
  bundle says so (a tombstone, §6.6).
- SHOULD resolve link targets by `id` first, then by bundle-relative path,
  then by an `aliases` match (§6.6); qualified references resolve by
  namespace first (§9.2).
- SHOULD synthesise inverse edges (§6.3).
- MUST preserve unknown keys when round-tripping a document.
- MUST tolerate v0.1-generation fields per the mapping in §7.3.
- MUST read a `contradicts` edge without `state` as open, and MUST ignore
  `state` on any other rel (§6.5).
- SHOULD surface the successor of a deprecated concept (§6.6), guarding against
  cycles.
- MUST accept `ai-xf://namespace/id` wherever `namespace/id` is accepted, and MUST
  warn, never stay silent, when it resolves an unqualified reference across a
  bundle boundary (§9.2).
- MUST NOT treat an `imported` copy as carrying its source's trust tier (§9.6).

This permissive model is what keeps AI-XF useful while bundles evolve and agents
generate content.

---

## 12. Scope: a format, not a policy

AI-XF can record that a contradiction is open; it cannot make a curator record
one. The discipline that makes a bundle compound — search before writing, keep
evidence apart from synthesis, queue disagreements for a human, gate destructive
changes — is **policy**, and lives outside this spec. A non-normative reference
policy, written to be pasted into an agent's instructions, ships alongside it as
[`CURATOR.md`](./CURATOR.md). Nothing in it is required for conformance.

Likewise for sharing, with one exception: §7.6 gives the format a single word,
`withheld`, for the fact that something was redacted, because a list that is
silently shorter misleads every consumer. What to withhold remains policy.
AI-XF defines a *format*, not a policy. Content sensitivity, redaction, and
outbound-sharing rules are the **producer's** responsibility and out of scope
for this spec. Producers exporting into AI-XF for external exchange SHOULD apply
their own sanitisation before publishing a bundle — and SHOULD remember that
`media` assets and `sources` URIs leak context just as body prose does.

---

## 13. Versioning

Bundles declare the version they target via `manifest.ai-xf.yaml`'s `ai-xf` key.
Minor versions remain readable by earlier consumers under the permissive rules
of §11.1.

### Changelog — v0.4.4 (2026-10-03)

**Reference validator:** a custom rel declared in the bundle's own
`vocabularies.rels` (§9.3), or the `inverse` it declares, is no longer reported
as non-core. Only a local vocabulary file is read; a URL is never fetched.
Found by Longview's export (E12), whose seven declared rels warned on every
use. **Examples:** `examples/manifest.ai-xf.yaml` now targets `0.4` and names
its producer by actor (`human:jane-doe`), as does the §10.3 sample. No other
change.

### Changelog — v0.4.3 (2026-10-02)

**OKF alignment:** every timestamp is an ISO 8601 datetime with an explicit
offset (§5.6), following OKF PR #6. Bare dates are still read, as 00:00 UTC,
with a validator warning. The examples in this document, `examples/` and the
experiment fixtures now use the datetime form.

**Retirement:** a concept that leaves a bundle SHOULD become a tombstone
(§6.6); a regenerating producer SHOULD retire concepts whose source has gone.
A broken link is no longer described as "not-yet-written knowledge": in E8,
11 of 12 such targets had been archived or lay outside the export (§11.1).
The `aliases` fallback (§6.6) is now in the consumer resolution order.

**Reference validator** (no other normative change): implements the `aliases`
fallback, for local and qualified references; resolves bundle-relative `to`
paths (§6.1); matches body links to the concept they land on, so a file moved
with its `id` unchanged no longer fails the mirroring rule (§5.2, §6.4); and
`--stats` gains freshness numbers (concept files no `index.md` lists, live
edges into retired concepts, concepts replaced but not deprecated, sources
changed after their last verification) and federation vocabulary use by rel
pair. Evidence in `experiments/e8-freshness/`.

### Changelog — v0.4.2 (2026-09-27)

**Renamed again: AI-X is now AI-XF.** The two-letter tail "XF" reads as
"eXchange Format", the name is more distinctive than "AI-X" (which collides
with a great many unrelated products in search), and it keeps the hyphen that
separates it from IBM's AIX. Identifiers follow: `manifest.ai-xf.yaml`,
`ai-xf:`, `ai-xf://`, `federation.ai-xf.yaml`, `tools/ai-xf-validate.py`,
`application/vnd.ai-xf.*`, repository `ai-xf-format`. The validator reads all
three spellings (AIX, AI-X, AI-XF) and warns on the older two. No other change.

### Changelog — v0.4.1 (2026-09-26)

**Fixed:** the reference validator's fallback YAML parser silently dropped a
`links:` list whose items start at column 0 (PyYAML's default dump style), so
bundles written by a PyYAML producer validated clean without PyYAML installed
and warned with it. Both parsers now agree. Level 3 no longer demands
per-bundle `vocabularies` when the federation manifest declares them (§9.5).
Found by federating two real bundles (`experiments/real-federation/`, E7).

### Changelog — v0.4 (2026-09-26)

**Renamed: AIX is now AI-XF.** In prose and in every identifier: the manifest
is `manifest.ai-xf.yaml`, its version key is `ai-x:`, the explicit reference
scheme is `ai-xf://`, the federation manifest is `federation.ai-xf.yaml`, the
validator is `tools/ai-xf-validate.py`, the OCI artifact type is
`application/vnd.ai-xf.bundle.v1`, and the repository is `ai-xf-format`. "AIX"
is a registered trademark of IBM for its operating system; the hyphenated name
avoids the clash and reads as what it is, an AI eXchange format. Consumers MUST
still read the old spellings; the reference validator does, with a warning.
With one producer in the world this is the last moment the break is free.

Theme: federation with evidence. Every addition below was tested in
[`experiments/`](./experiments/) before it was written down; see
`experiments/RESULTS.md` for the numbers.

**Added:**

- `ai-xf://<namespace>/<id>` explicit reference form, accepted everywhere a
  qualified reference is, including body links for §6.4 mirroring (§9.2).
- Resolution rule for unqualified references across held bundles: own bundle
  first, then alphabetical by namespace, always with a warning (§9.2). E2.
- `federation.ai-xf.yaml`: the consumer's manifest of held bundles with a `ref`
  per bundle; required for provenance, not for resolution (§9.5). E1.
- `source: oci` entries with a `digest` in the federation manifest; no digest
  on a bundle's own manifest (§9.5). Appendix C on OCI distribution: one
  gzipped tar layer, `artifactType` distinct from the layer media type, and
  `org.opencontainers.image.created` pinned to the bundle's `generated`
  timestamp so the manifest digest is reproducible (unpinned, oras stamps
  wall-clock time and byte-identical content gets a new digest every push).
  Signing left to the producer (Cosign key or keyless). E6.
- `imported` / `exported-to` relationship: a copy declares its source and does
  not inherit its trust (§9.6). Answers OKF issue #15.
- Validator: `--federation <manifest>`, federation stats (collisions, resolved
  and unresolved qualified references, Foam-rule resolutions), per-bundle
  provenance lines.

- §7.3a: trust survives transport, not ingestion; ingesting consumers round-trip
  unknown keys or document what they drop. E5: 45 of 45 key checks preserved
  through git, rsync and iCloud; a parse-and-rewrite pass normalised 8 of 15
  keys and lost comments.
- §9.5: `ref` and `digest` are strings; a validator understands `source: oci`.

- Non-normative index guidance (§9.7): an index over a federation carries
  `namespace` and `id` as fields on every document and returns `namespace/id`
  on every hit; a collection label is not a substitute. E3: only the index
  with `namespace` as a field put the right concept on top for all four
  collision questions, in both runs; a hybrid LLM-reranked index did not.
- `verified` on link objects: trust tiers for edges, derived exactly as for
  concepts (§6.1). Answers the "sharper half" of OKF issue #16.
- Merge ownership of reserved files; `log.md` is read-then-add, never
  regenerated (§10.2). Answers OKF issue #26.
- `withheld: N` marker in `sources` for redacted entries (§7.5); §12 narrowed
  accordingly. Answers OKF issue #32.
- Non-normative serving guidance (§9.8): a tools-only MCP server returns
  `namespace`, `id`, `ref: "namespace/id"` on every item, frontmatter verbatim
  on `get`, and the bundle's provenance `ref`. E4 (deterministic pass only; the
  agent-answering measure was deliberately not run for v0.4, so §9.8 rests on
  the payload contract, not on answer quality).

**Unchanged:** every v0.3 bundle is a valid v0.4 bundle.

### Changelog — v0.3 (2026-09-21)

Theme: v0.1 and v0.2 describe knowledge at rest. v0.3 describes it changing.

**Corrected** (AI-XF v0.2 deviated from the OKF v0.2 it claimed to adopt — §7.3):

- `status` values are OKF's `draft | stable | deprecated`; `active` was wrong.
- `sources` entries use `resource`, not `uri`.
- Actors use `<producer>/<version>`, `human:<id>`, `process:<id>`; the
  `agent:` / `pipeline:` prefixes were wrong.
- A bundle-root `index.md` MAY carry `okf_version` frontmatter.

**Added:**

- Link objects gain optional `by`, `at`, `state` and `resolved` (§6.1).
- Contradiction lifecycle: `open` / `resolved`, with an `outcome` (§6.5).
- `supports` / `supported-by`, `merged-into` / `merged-from` and `split-from` /
  `split-into` join the core relationship vocabulary (§6.2).
- Merge tombstones, split, and successor redirects (§6.6).
- Per-claim attribution documented as inherited from OKF (§7.4).
- `type: Claim` as a recommended type (§7.5).
- A controlled leading-word vocabulary for `log.md` (§10.2).
- `CURATOR.md`: a non-normative reference curation policy (§12).
- Validator: `--stats` reports curation health; new warnings for the corrected
  spellings above.

**Changed:**

- `provenance.confidence` is reframed as an asserted tie-breaker behind derived
  signals (§7.2). It is not deprecated.
- `contradicts` no longer says resolution "SHOULD be in prose".

**Unchanged:** the superset contract, identity, mirroring, media, federation
and the conformance ladder. Every v0.2 bundle is a valid v0.3 bundle.

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
- Conformance **Level 3 — AI-XF Federated** (§11).
- `id` values MUST NOT contain `/` (reserved for qualified references).

**Unchanged:**

- The superset contract, stable identity, typed relationships with body-link
  mirroring, the permissive consumer model, and the "just files" constraint.

### v0.1 (2026-07-18)

Initial draft: stable `id`, typed `links` with inverse inference and body-link
mirroring, self-contained `provenance` map, `manifest.ai-xf.yaml`, conformance
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
reference validator in [`tools/ai-xf-validate.py`](./tools/ai-xf-validate.py) at
Level 3 and demonstrates OKF v0.2 trust fields, media identity, a
federation-qualified link, per-claim attribution, an open contradiction
between two claims, and a merge tombstone.

## Appendix C — distributing a bundle as an OCI artifact (non-normative, v0.4)

Tested in experiment E6 with `oras` 1.3.4 and `cosign` 3.1.3 against a local
registry. The producer flow (package, push, sign) took under two seconds; the
consumer flow (pull, verify, unpack) under one; a tampered re-push to the same
tag failed verification while the original stayed verifiable by digest.

- **Layer:** one `tar+gzip` of the bundle directory, built deterministically
  (sorted entries, `mtime` 0, uid/gid 0), so the layer digest depends only on
  content.
- **Types:** `artifactType: application/vnd.ai-xf.bundle.v1`; layer
  `mediaType: application/vnd.ai-xf.bundle.layer.v1+tar+gzip`. Keep them
  distinct, as the OCI artifact guidance and the agent-skills OCI draft do.
- **Annotations:** `org.opencontainers.image.title`, the bundle `name`,
  `namespace` and `ai-xf` version, the source commit, and
  `org.opencontainers.image.created` **pinned to the bundle's `generated`
  timestamp**. Left unpinned, `oras push` stamps the wall clock and the
  manifest digest changes on every push of identical content.
- **Signing:** `cosign sign` on the pushed reference (key pair or keyless).
  Consumers verify by digest, not by tag; a tag can be overwritten, a digest
  cannot.
- **Reference from a federation:** `source: oci` with `ref` and `digest` in
  `federation.ai-xf.yaml` (§9.5).

