# CURATOR.md — a reference curation policy

**Status:** non-normative. Nothing here is required for AI-XF conformance.

AI-XF is a format. It can record that two concepts disagree, that one replaced
another, that a claim points at its evidence. It cannot make a curator do any of
that. The behaviour lives in the instructions you give the agent that maintains
the bundle — what Andrej Karpathy's
[LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
pattern calls the *schema* layer, and deliberately leaves to the reader.

This file is one such schema: seven rules and four numbers. Paste it into your
agent's instruction file (`CLAUDE.md`, `AGENTS.md` or equivalent) and edit it to
fit. It assumes an AI-XF v0.3 bundle, and each rule names the field that makes it
checkable.

The problem it exists to prevent: a knowledge base that grows without
compounding. Every ingest creates a note; nothing ever revises one. In the vault
AI-XF was extracted from, 138 notes carried a `contradicts` field and six had ever
been filled in. The field existed. The discipline did not.

---

## The seven rules

### 1. Search before you write, and search by meaning

Before creating a concept, look for an existing one — twice. First by `id`,
`title` and `aliases`. Then by meaning: the duplicate that hurts is the one that
uses different words, and keyword search will never find it.

If the bundle is part of a federation, search the other held bundles too, and
when you link across a boundary, qualify the reference (`namespace/id` or
`ai-xf://namespace/id`). An unqualified reference that only resolves in another
bundle will be resolved for you, with a warning; do not leave it that way.

Only then choose **one** move and record it in `log.md`:

| Move | When | Log word |
|------|------|----------|
| Update | An existing concept covers this; the new material changes or extends it. | `Update` |
| Import | The concept lives in another bundle and you need a local copy. Link it with `imported`; the copy does not inherit the source's trust. | `Creation` (with an `imported` link) |
| Create | Nothing covers it. | `Creation` |
| Merge | Two existing concepts turn out to be one. Keep a tombstone (SPEC §6.6). | `Merge` |
| Split | One concept turns out to be two. | `Split` |
| Deprecate | The concept is no longer true or no longer needed. | `Deprecation` |

Prefer Update to Create. When you do create, add the names you searched for and
did not find to `aliases`, so the next search lands.

### 2. Never rewrite the evidence

Raw sources are immutable. Read them; never edit them.

Every rewrite of a concept is a paraphrase, and paraphrase compounds error as
readily as insight. So every factual sentence you write or keep MUST carry a
footnote whose label is a `sources[].id` (SPEC §7.4). A sentence you cannot
trace to a source is either removed or marked as the curator's own inference.
When revising, work from the sources, not only from the previous draft.

### 3. Store claims, not topics

Title a concept as a statement that could turn out to be wrong, and give it
`type: Claim` (SPEC §7.5). "Voice latency" can only get longer. "Sub-200 ms
voice replies need on-device processing" can be supported, contradicted or
superseded.

Keep topic concepts as maps: short pages that link to the claims.
Connect evidence to claims with `supports`.

### 4. A contradiction is a ticket, not an edit

When new material disagrees with an existing concept, you MUST NOT rewrite
either side until they agree. That instinct destroys the most valuable signal
the bundle will ever produce.

Instead:

1. Keep both concepts intact.
2. Add a `contradicts` link with `state: open`, your actor in `by`, the date in
   `at`, and one line in `note` saying what disagrees and why (SPEC §6.5).
3. Add a `Contradiction` entry to `log.md`.
4. Stop. A person rules.

When the person rules, record it: `state: resolved` and a `resolved` map with
their `human:` actor and an `outcome`. If one side won, it gains a `supersedes`
link and the loser becomes `status: deprecated`.

### 5. Gate by reversibility, not by size

| May proceed unattended | Waits for a person |
|------------------------|--------------------|
| Creating a concept | Merge, split, deletion, deprecation |
| Adding a source, a link, an alias | Resolving a contradiction |
| Opening a contradiction | Adding a `human:` entry to `verified` |
| Appending to `log.md` | Raising `provenance.confidence` |

Small is not the same as safe: adding one source can raise trust in a false
claim. The test is whether the change can be undone without loss. Propose gated
changes on a branch; the reviewer's approval is the verification event, and is
what writes the `verified` entry.

### 6. One ingest, one commit

Each source processed gets its own commit and its own `log.md` entries: the
source, the move chosen per concept, and why. Never mix curation with file
reorganisation in one commit. If this rule is skipped, none of the numbers below
can be computed.

Also log what you could **not** answer. When a question finds nothing in the
bundle, add a `Gap` entry. That list is next week's reading list.

### 7. Retire, don't delete; rename, don't re-mint

When a concept stops being true or leaves the bundle, set `status: deprecated`,
point it at its successor if it has one (`superseded-by`, `merged-into`), and
log a `Deprecation`. Do not delete the file. A deleted concept looks exactly
like one nobody wrote, and every link into it now says nothing; a retired one
tells the reader what happened (SPEC §6.6). Retirement is gated like deletion
(rule 5), because it changes what agents are told.

A rename keeps the `id`. Change the title, the filename and the folder as you
like; the `id` is what everyone else links to (SPEC §5.2). If a tool has already
minted a new `id`, retire the old one with `superseded-by` the new one and add
the old `id` to the new concept's `aliases`.

If the bundle is generated from somewhere else (an exporter, a sync job), the
generator must do this for you on every run. Test it: delete one source, re-run,
and check that the number of live concepts falls and a `Deprecation`
appears. A generator that passes additions and edits but not this test is
accumulating, not reconciling.

---

## The four numbers

Run them from the bundle itself:

```bash
python3 tools/ai-xf-validate.py path/to/bundle --stats
```

| Number | Healthy | Warning sign |
|--------|---------|--------------|
| **Update : Creation** ratio in `log.md` | Rises as the bundle matures | Every ingest creates; nothing updates |
| **Contradictions** open vs resolved | Some open, some resolved, queue moving | Zero ever opened, or a queue that only grows |
| Share of concepts past **`stale_after`** | Flat or falling | Climbing month on month |
| Share of questions answered **from the bundle alone** | Rising; `Gap` entries get closed | You keep going back to raw sources |

Two more checks are free. `--stats` also reports **freshness**: concept files no
`index.md` lists (left behind by a generator), live links into retired concepts
(re-point them), concepts something replaced but nobody retired, and sources
that changed after the concept was last verified. Each should be zero.

The other is the spread of `provenance.confidence`. If nearly every
concept says `high`, the label has stopped carrying information (SPEC §7.2).
Reset it, and rank on derived signals — trust tier, staleness, `supports` and
open `contradicts` — instead.

---

## Limits

This policy has one author and, so far, one bundle. Rule 4 assumes a person with
time to rule; in a team that queue needs an owner. The rules cost tokens and
time — two searches and a written decision per source. They are offered as a
starting point to fork, not as settled practice.
