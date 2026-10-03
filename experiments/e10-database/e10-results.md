# E10 results: an AI-XF bundle as a department database

**2026-10-03.** Exploratory: no plan with pass criteria preceded it. Treat the
numbers as a baseline for a planned experiment, not as a gate.

The question: when one bundle has to serve a department, with many people and
agents reading and writing at once, what does the database look like, which
patterns hold (CQRS, blue/green), and what would AI-XF need to make the move
easy? Inputs: `examples/` (7 concepts), `psychology-kb` (102) and
`ai-concepts-kb` (63), copied read-only. Database: a throwaway Postgres 17
(`postgres:17-alpine`, port 55410), started and removed by `run.sh`. Client:
Bun 1.3.13 (`Bun.sql`, `Bun.YAML`). One laptop, one run recorded in
`results.json`; timings will vary.

## 1. Storage model

Two tables:

- `concepts`: namespace, id, path, `revision`, content hash, the raw file
  verbatim, frontmatter as `jsonb`, body, status, `updated_at`, `updated_by`.
  Primary key (namespace, id).
- `events`: append-only, one row per change, typed with the `log.md`
  vocabulary (§10.2): `Creation`, `Update`, `Deprecation`, `Merge`,
  `Contradiction`, `Resolution`, plus actor and payload.

All 172 concepts loaded in 127 ms. The three `log.md` files replayed as 177
historical events with no mapping at all: every leading word was already an
event type. Each concept also got a `Creation` event, attributed to its
`generated.by` actor.

## 2. Round trip: database back to a bundle

| Export from | Files | Identical | Changed | Validator (level 3, federated) |
|---|---|---|---|---|
| The raw text, verbatim | 181 | **181** | 0 | Same as the input: all pass; 1 / 107 / 97 warnings |
| The parsed `jsonb`, re-serialised | 181 | 9 (the non-concept files) | **172**, every concept | Same as the input |

Every re-serialised concept changed, and no value changed: the frontmatter
parses back equal once keys are sorted. Postgres `jsonb` does not keep key
order (it stores shorter keys first), so `type` and `id` move. The serialiser
also turned flow lists (`[a, b]`, in 7 concepts) into block lists, quoted
some scalars, and dropped YAML comments (2 concepts). The validator did not
notice any of it. This is E5's finding again, now inside a database: trust
survives storage only where the text is kept verbatim.

## 3. Concurrency

50 writers, 200 read-modify-write edits each (append a sentence, add a tag,
or add a link) on the 102 psychology concepts, chosen with a Zipf skew
(s = 1.1): the hottest concept takes 23% of edits, the top five 50%. Each
writer pauses 0–4 ms between reading and writing, standing in for an agent
or a person deciding what to change. Pool of 25 connections. An edit is
**lost** if it was acknowledged but its marker is missing from the final row.

| Policy | Acknowledged | Lost | Retries | Gave up | Throughput | p50 | p95 |
|---|---|---|---|---|---|---|---|
| Last write wins | 10,000 | **4,627 (46.3%)** | 0 | 0 | 3,606/s | 7.6 ms | 46 ms |
| Optimistic, `WHERE revision = expected` | 9,933 | 0 | 60,680 | **67** | 333/s | 11 ms | 773 ms |
| Pessimistic, `SELECT … FOR UPDATE` | 10,000 | 0 | 0 | 0 | 1,170/s | 24 ms | 133 ms |

- **Last write wins loses nearly half the work, silently.** Every lost edit
  was acknowledged to its writer.
- **Optimistic concurrency loses nothing but starves the hot spot.** Retries
  ran six to one, and 67 edits gave up after 100 attempts, all on the most
  contended concepts. At 20 writers it was comfortable (839/s, p95 110 ms,
  none given up).
- **Pessimistic locking was the best fit for hot concepts**: three times the
  optimistic throughput and no failures, at the price of a higher median.
  The practical answer is optimistic by default with a short lock (or a
  queue) for the few concepts everyone edits.

**The file model, for contrast.** Two git branches editing the same concept:

| Concurrent edits to one file | git merge |
|---|---|
| Both add a tag to the same flow list (`tags: [a, b]`) | **Conflict** |
| Both append a link to the end of `links:` | **Conflict** |
| One edits `description`, the other `tags` | Clean |
| One edits frontmatter, the other appends to the body | Clean |

Git never loses an edit; it stops and asks a person, which is right for a few
curators and unworkable for fifty agents.

**What the writers did to the format.** After the run, all 102 psychology
concepts had a stale `raw` (the writers changed the parsed fields), and
exporting the parsed fields gave **3,221 validator errors**, every one a typed
link with no body link (§6.4). The writers were naive on purpose; the point
stands. Once the database is the source of truth, the format's invariants
(mirroring, tombstones, log entries) have to be enforced by the write path,
not by the person editing a file, and the raw text must be regenerated from
the fields, which needs a canonical serialisation.

## 4. CQRS: read models projected from the write side

Three read models in their own schema: a link graph with inverse edges
synthesised (§6.3), a weighted full-text search table (title, description,
body; GIN index), and a "current" view that serves a tombstone's successor
(§6.6 redirects).

| | Concepts | Declared links | Inferred inverses | Rebuild from scratch |
|---|---|---|---|---|
| The three bundles | 172 | 603 | 597 | 110 ms |
| Department scale: the two real bundles copied into 50 namespaces | 8,422 | 30,053 | 29,797 | 4.2 s |

Loading the 50 copies took 378 ms. The namespace column served as the
department or team boundary with no other change.

**Incremental projection while writing.** A projector polled `events` every
20 ms and re-projected each touched concept while 20 optimistic writers made
2,000 edits. Event-to-read-model lag: p50 483 ms, p95 671 ms, max 704 ms.
Afterwards, 92 concepts were findable by the text the writers had added. Half
a second is acceptable for a knowledge base and much too slow for a
transaction system; a production projector would batch and run in parallel.

## 5. Blue/green: a mapping change under live reads

The change: refine `type` from the vault's `conceptType` (E8's type-collapse
finding), so `Concept` becomes `Bias`, `Effect`, `Fallacy` and so on. The
green read model was built beside blue in its own schema (5.7 s at 8,422
concepts), exported, and validated before it could serve.

| Gate | psychology | ai-concepts | examples |
|---|---|---|---|
| Green, against the **old** federation vocabulary | Pass; 94 "type not in vocabulary" warnings | Pass; 20 such warnings | Pass |
| Green, against the vocabulary **expanded** with the new types | Pass; 0 type warnings | Pass; 0 | Pass |

So the vocabulary has to change first (expand), then the data, then readers
are switched: blue/green for the read side, expand/contract for the shared
vocabulary and the write-side schema.

**The swap.** Ten readers queried through a stable view while it was
repointed from blue to green in one transaction:

- Swap 4.5 ms, rollback (repoint to blue) 3.5 ms.
- 4,790 reads during the window, **0 errors**; p50 1.5 ms, p99 3.1 ms,
  worst 27.8 ms.
- Distinct types served went from 5 to 14 at the swap.

Blue stays intact until green has been trusted for a while, so rollback is
the same one-line repoint.

## 6. What AI-XF would need to ease the move

**Already in AI-XF, and sufficient:**

- **Stable `id` plus `namespace`** made a natural primary key, and the
  namespace doubled as a team boundary. 50 namespaces needed no change.
- **The `log.md` vocabulary is an event vocabulary.** 177 historical entries
  became typed events without a mapping table.
- **The actor convention** (`human:`, `process:`, `<tool>/<version>`) filled
  `updated_by` and event actors directly.
- **Tombstones and successor edges** (§6.6) became the redirect view in one
  query; inverse synthesis (§6.3) became one insert.
- **The validator as a deploy gate** caught both problems that mattered: the
  writers' unmirrored links (3,221 errors) and the unexpanded vocabulary (114
  warnings).

**Missing from the format, worth adding:**

- **A canonical serialisation.** Key order, list style and quoting are free
  today, so any database that stores parsed fields cannot reproduce the
  file, and every write rewrites the text. A canonical form (key order as
  §4's example, block lists, minimal quoting) would make "regenerate the
  file" deterministic and diffs meaningful.
- **A per-concept revision**, e.g. `revision: 7` or a content hash, so that a
  writer, an MCP tool or a sync job can do a compare-and-set without the
  database. Optimistic concurrency needs exactly this and nothing more.
- **An event form of the log.** Today `log.md` is prose with a leading word.
  A machine-readable line shape (word, concept id, actor, time) would let a
  bundle and an event table convert both ways without parsing prose.

**Belongs in the database, not the format:**

- Locking policy, retries and hot-spot handling.
- Read models, search indexes, projection lag and the swap mechanism.
- Enforcing invariants on write (mirroring, tombstoning, log entries): the
  format states them; the write path must apply them.

## Caveats

One run on one laptop, against a database with nothing else running. The
edit mix and the think time are invented, and the Zipf exponent is a
guess at how unevenly a department edits. The concepts were copies of two
real bundles, so 50 namespaces share identical content. The git contrast is
four hand-made scenarios, not a measurement. The client stores `jsonb` only
when given an object: given a JSON string, Bun's driver stored a JSON
string scalar, which the first run caught.
