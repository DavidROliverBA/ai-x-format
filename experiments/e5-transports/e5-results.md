# E5 — trust survival through transports

Part of the federation experiments plan (vault doc
`docs/plans/2026-09-26-federation-experiments-plan.md`, §2 E5 — not part of
this repo, kept in the planning vault). Round-trips `examples/` (namespace
`example-payments`, 7 concepts: 2 `System`, 2 `Claim`, 1 `DataAsset`, 1
`Person`, 1 tombstone `System`) through five transports and diffs
frontmatter key-by-key plus whole-file bytes. Reproduce with
`experiments/e5-transports/run.sh` (writes scratch state to `/tmp/ai-x-e5/`,
never touches `examples/`, `tools/ai-x-validate.py`, or other
`experiments/*` directories).

**Run date:** 2026-09-26. **Tool versions:** git 2.54.0 (Apple Git-157),
Python 3.14.4, uv 0.11.7, `rsync` = macOS's bundled **openrsync** (protocol
29 — a BSD reimplementation, not classic rsync; noted because `-a` behaviour
can differ on edge cases like ACLs and xattrs, though not on anything this
bundle exercises), PyYAML (via `uv run --with pyyaml`, latest resolved at
run time).

## Summary

| Transport | Keys preserved | Keys normalised | Keys lost | Files byte-identical |
|---|---|---|---|---|
| (a) git (init → commit → clone) | 15 | 0 | 0 | yes (10/10) |
| (b) rsync -a | 15 | 0 | 0 | yes (10/10) |
| (c) iCloud Drive (copy in → poll → copy out) | 15 | 0 | 0 | yes (10/10) |
| (d) Knowledge Catalog (kcmd) | — | — | — | **SKIPPED** (no gcloud on this machine) |
| (e) YAML normalisation round trip (PyYAML `safe_load`/`safe_dump`) | 7 | 8 | 0 | no (3/10) |

**Headline finding:** the three real transports — git, rsync, iCloud Drive —
are all byte-identical, 15/15 keys preserved, zero exceptions. Nothing about
*moving* the bundle touches a single byte. The only transport that changes
anything is (e), the one that **parses and rewrites** the frontmatter — and
even there, nothing is *lost*: every one of the 8 affected keys round-trips
to the same value, just in different YAML surface syntax. Zero keys were
lost by any transport tested here. The plan's fixtures never got to exercise
real loss (that requires (d), skipped) — but (e) demonstrates *why* (d) is
expected to lose keys: kcmd's `--json`-equivalent step is exactly this
parse-and-rewrite operation, just with a target schema that only has room
for seven of AI-X's frontmatter keys.

## (a) git: init → commit → clone

```
git init -b main && git add -A && git commit -m "..." && git clone
```

Files compared: **10**. Byte-identical: **10/10**.

| Key | Status | preserved/normalised/lost (files) |
|---|---|---|
| `type` | preserved | 7/0/0 |
| `id` | preserved | 7/0/0 |
| `title` | preserved | 7/0/0 |
| `description` | preserved | 7/0/0 |
| `tags` | preserved | 7/0/0 |
| `generated` | preserved | 7/0/0 |
| `status` | preserved | 7/0/0 |
| `stale_after` | preserved | 5/0/0 |
| `sources` | preserved | 4/0/0 |
| `provenance` | preserved | 6/0/0 |
| `links` | preserved | 7/0/0 |
| `verified` | preserved | 5/0/0 |
| `resource` | preserved | 3/0/0 |
| `aliases` | preserved | 1/0/0 |
| `media` | preserved | 1/0/0 |

No surprise: git stores blobs verbatim (no `.gitattributes` line-ending or
smudge/clean filters in this repo touch `.md`/`.yaml`). Clone reproduces the
commit's tree exactly.

## (b) rsync -a

Files compared: **10**. Byte-identical: **10/10**. Identical per-key table to
(a) — `rsync -a` copies bytes, permissions and mtimes; content is untouched.

## (c) iCloud Drive

Bundle copied into `~/Library/Mobile Documents/com~apple~CloudDocs/ai-x-e5-roundtrip/`,
polled for up to 120s, copied back out to `/tmp/ai-x-e5/icloud/dest/`, diffed,
then the iCloud folder removed.

**Sync confirmation: YES, with a caveat.** The first poll design (single
`brctl status` read for `client:idle`) gave a **false positive** on the very
first run: poll #1 read `client:idle` immediately after the `cp`, before the
CloudDocs daemon had even registered the new files — the very next full
status dump, moments later, showed `client:needs-sync` with a "Client Truth
Unclean Items" block still pending. The script was corrected to require the
idle / no-`.icloud`-placeholder / no-"Unclean Items" state to hold for **3
consecutive polls, 5s apart**, after an initial 3s settle delay. On the
corrected re-run: poll #1 still showed `unclean_blocks=1`; polls #2–#4 were
clean, so sync was confirmed after ~23s, comfortably inside the 120s budget.
This is still a **local daemon-queue signal**, not proof the bytes reached
Apple's servers — `brctl status` reports the client's own queue state, not a
server acknowledgement. Recorded as a judgement call, not overclaimed.

Files compared: **10**. Byte-identical: **10/10**. Identical per-key table to
(a)/(b) — once sync genuinely settles, the round-tripped files are
byte-for-byte the same as what was copied in.

## (d) Knowledge Catalog via kcmd — SKIPPED

**Reason:** no `gcloud` CLI on this machine, and kcmd's setup/push/pull flow
requires it for auth and EntryGroup provisioning. Per the plan, this is
optional and the connector doc's own stated losses are quoted instead
(fetched live via `curl` from
`https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/connectors/gcp-knowledge-catalog.md`,
raw content, 136 lines, `## Limitations` section, verbatim):

> - **Seven frontmatter keys are carried**, plus the markdown body. `title`,
>   `description` and `tags` become native entry fields, `resource` becomes
>   `catalogEntry.resource.name`, and `type`, `generated` and `sources` go on
>   the `okf` aspect. To carry more, add fields to `okf-aspect.json` and
>   `okf.ts`, keeping existing `index` values stable.
> - **Only `.md` files are carried.** Anything else in the bundle — images,
>   HTML, CSV — is ignored in both directions: never pushed, and left alone
>   on pull.
> - **Cross-links resolve to nothing.** Relative paths (§6.1) are stored
>   verbatim. Don't rewrite them in your source — the relative form is what
>   renders on GitHub.
> - **Tags become entry labels set to `"true"`**, and only labels with that
>   exact value are read back as tags. Dataplex caps label keys at 128
>   characters.
> - **Renames orphan catalog state, deletes leave entries behind**, and
>   there is no merge story. Treat git as authoritative: push on merge,
>   don't pull into a tracked bundle.
> - **No entry-level access control.** Anyone with a basic role on the
>   project can read and bulk-export the EntryGroup...
> - **Scale is untested** beyond the 14-file demo.

And from the "first pull" section (§6, verified in the same fetch):

> The first pull rewrites every frontmatter block into `kcmd`'s YAML style —
> sequences indented, timestamps unquoted, mapping keys reordered, lines
> rewrapped at a different width. No values change. Commit that
> normalization once and later pulls are byte-identical...

**Against our 7-concept bundle, this means:** `verified`, `status`+trust
tier logic beyond `generated`/`sources`, `provenance`, `stale_after`, and
every `links`/`media` entry — i.e. everything AI-X/OKF adds beyond the
original seven OKF v0.1 keys the connector was built for — would be **lost**
on push, not normalised. `sync-capture-limits-throughput.md`'s
`contradicts`/`state: open` link, `payment-service.md`'s `media` hash, and
`payment-service-v2.md`'s federation-qualified `depends-on:
data-eng/orders-events` (already stated to "resolve to nothing" once
through the connector) would all disappear. This is the connector's own
documentation, not our inference — we did not run kcmd, so we cannot
confirm it empirically. The (e) result below is the closest empirical stand-in.

## (e) YAML normalisation round trip (PyYAML `safe_load` + `safe_dump(sort_keys=False)`)

Simulates what any parse-and-rewrite tool — kcmd included, per its own "first
pull rewrites every frontmatter block" documentation quoted above — does to
a bundle even when it claims to carry every key. Files compared: **10**.
Byte-identical: **3/10** (the 3 non-frontmatter files — `index.md`, `log.md`,
`manifest.ai-x.yaml` — pass through unchanged; all 7 concept files change).

| Key | Status | preserved/normalised/lost (files) | What changed |
|---|---|---|---|
| `type` | preserved | 7/0/0 | — |
| `id` | preserved | 7/0/0 | — |
| `title` | preserved | 7/0/0 | — |
| `description` | normalised | 5/2/0 | long descriptions (>~80 chars) rewrapped at PyYAML's default width |
| `tags` | normalised | 0/7/0 | flow `[a, b]` → block list; every instance |
| `generated` | normalised | 0/7/0 | timestamp `2026-05-28T14:30:00Z` → `2026-05-28 14:30:00+00:00` (PyYAML's implicit YAML-1.1 timestamp resolver parses the `Z`-suffixed string into a `datetime`, then re-emits it in its own style — same instant, different text) |
| `status` | preserved | 7/0/0 | — |
| `stale_after` | preserved | 5/0/0 | date-only values (`2027-05-28`) round-trip byte-identical — only timestamps with a time component are affected |
| `sources` | normalised | 0/4/0 | list-of-maps indentation flattened (`  - id:` → `- id:`) |
| `provenance` | preserved | 6/0/0 | — |
| `links` | normalised | 0/7/0 | list indentation flattened; long `note:` text rewrapped |
| `verified` | normalised | 0/5/0 | list indentation flattened |
| `resource` | preserved | 3/0/0 | — |
| `aliases` | normalised | 0/1/0 | flow list → block list |
| `media` | normalised | 0/1/0 | list indentation flattened |

**Zero keys lost.** Every value survives `normalize()`-equal (dates/times
canonicalised to UTC ISO 8601, lists/dicts compared recursively) — this is
formatting churn, not data loss. One thing PyYAML round-tripping *does*
discard that isn't a frontmatter key at all: **inline YAML comments**
(`# OKF v0.2 trust & lifecycle`, `# AI-X additions` section headers present in
2 of the 7 concept files — `payment-service.md` and `payment-service-v2.md`)
vanish, because YAML's data model has no place for them. `compare.py`
detects and flags this separately (`comments_lost`) —
it's a real loss, just not of a *key*, so it sits outside the plan's table
but is worth recording: any tool that treats frontmatter as data-only will
silently drop human-authored section comments.

## Judgement calls

1. **Comparison granularity is top-level frontmatter keys**, matching the
   plan's own key list (`generated`, `verified`, `sources`, `status`,
   `stale_after`, `provenance`, `links`) plus every other key the bundle
   actually carries (`type`, `id`, `title`, `description`, `resource`,
   `tags`, `aliases`, `media`). Sub-field changes (e.g. `generated.at`'s
   timestamp format) are reported as the *reason* a parent key is
   `normalised`, not as separate rows — this matches how a consumer would
   actually notice the difference (diffing the file), not how a schema
   might slice it.
2. **"Preserved" requires byte-identical text for that key's block**, not
   just semantic equality — this is deliberately stricter than the
   plan's "byte-for-byte" framing would allow if relaxed, so that
   `normalised` only ever means "same value, different bytes," never
   "we didn't look closely enough."
3. **iCloud sync confirmation needed a debounce fix mid-run** (see §(c))
   after the naive single-read check produced a false positive. This is
   itself a finding: any automation that checks `brctl status` once and
   proceeds risks acting on stale/pre-sync state. Recorded rather than
   silently patched away.
4. **rsync on this machine is openrsync** (macOS's BSD-licensed
   reimplementation, protocol 29), not GNU rsync. Noted for reproducibility;
   it made no observable difference for a plain `-a` copy of small text
   files with no ACLs/xattrs.
5. **(d) is evidence-by-documentation, not by execution.** No gcloud on this
   machine means kcmd's stated losses are quoted, not reproduced. (e) is
   offered as the closest empirical analogue (same failure class — a
   parse-and-rewrite step — different tool), not a substitute measurement.

## The rule: trust survives transport, not ingestion

Every transport that treats the bundle as **opaque bytes** — git, rsync,
iCloud Drive — preserved all 15 frontmatter keys byte-for-byte across all 7
concepts, 100% of the time, in this experiment. Every transport that treats
the bundle as **structured data to be re-expressed** behaved differently in
proportion to how much of the structure it understands:

- PyYAML's round trip (e) understands *all* of AI-X's YAML, so it only
  **normalises** — 8 of 15 keys change surface syntax (flow→block lists,
  `Z`-suffixed timestamps → UTC-offset timestamps, list indentation, line
  wrapping) but every value is recoverable and semantically identical. It
  also silently drops non-key content (comments) that isn't part of the
  data model at all.
- kcmd, by its own documentation, understands *seven* of AI-X's keys and
  nothing about AI-X's link/trust extensions, so the same class of operation
  (parse, then re-express) **loses** `verified`, `provenance`, `stale_after`
  beyond its own use, every `links` entry's `state`/contradiction metadata,
  and all `media` — because there is nowhere in its target schema for them
  to go, and it silently drops anything that isn't `.md`.

The dividing line is not "did the file move," it's "did something need to
*understand* the file to move it." Transport failure modes (git corruption,
rsync interruption, iCloud eviction) are availability problems with
well-understood recovery paths. Ingestion failure modes — a tool that only
partially models AI-X's schema — are **silent and structural**: nothing
errors, the push/pull commands report success, and the lost fields are
simply absent from what comes back. This is exactly what the plan's E5
question was checking for, and it argues that **v0.4's guidance to
implementers should be**: any tool consuming an AI-X bundle must either (a)
round-trip the full frontmatter opaquely (treat unknown keys as pass-through,
the way `safe_dump` does), or (b) declare explicitly, in the way this
connector's docs do, exactly which keys it drops — because "seven keys
carried" read on its own sounds like coverage, and only reads as *loss* once
you hold it next to a bundle that has fifteen.
