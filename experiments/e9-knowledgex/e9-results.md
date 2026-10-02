# E9 results: interoperability with KnowledgeX

**2026-10-02.** KnowledgeX ([rahulnyk/KnowledgeX](https://github.com/rahulnyk/KnowledgeX),
npm `knowledgex@0.4.0`) is a personal knowledge library whose notebooks are OKF
bundles, maintained by an MCP server and a `kx` CLI. It is the first
third-party OKF producer and consumer AI-XF has been tested against. Exploratory:
no plan with pass criteria preceded it. Re-run with `run.sh` (needs bun); the
output of the run recorded here is `results.txt`.

## A. A KnowledgeX notebook, read by AI-XF

Four notes made with `kx new` (two Decisions, a Concept, a Lesson), one
`supersedes`, one `contradicts`, one `verify`. No LLM involved.

| Check | Result |
|---|---|
| `kx check` | 0 errors (4 warnings: unfilled template hints) |
| AI-XF Level 0 (OKF-compatible) | **PASS**, both parsers |
| AI-XF Level 1+ | FAIL as expected: no `id`, no `manifest.ai-xf.yaml` |
| AI-XF `--stats` | **misreads both relationships**: "0 open contradictions", and the superseded Redis decision listed as "retired (no successor)" |

KnowledgeX records relationships as **top-level frontmatter keys holding file
names**: `supersedes: [use-redis-as-the-job-queue.md]`, `contradicts: [...]`,
plus `aliases` (same key and meaning as AI-XF's) and a `created` date. AI-XF
records them as `links: [{rel, to: id}]`. Both are extensions OKF ignores, so
both bundles are valid OKF, and neither tool sees the other's relationships.

## B. AI-XF `examples/`, read by KnowledgeX

| Input | What KnowledgeX sees |
|---|---|
| `examples/` as published (concepts in `concepts/`, `claims/`, `people/`) | `kx check` passes; **search finds 0 notes**. Notebooks are flat folders, and KnowledgeX does not descend into subdirectories |
| Flattened, at `f4031dc` (bare-date timestamps) | 1 machine-confirmed, **6 unverified**: AI-XF's 5 human-reviewed concepts read as **0** |
| Flattened, v0.4.3 (datetimes, events in order) | **5 human-reviewed, 2 unverified**, identical to AI-XF's own reading |
| `kx review`, v0.4.3 | Both tombstones listed as "deprecated without a successor": KnowledgeX does not read `links[]` `superseded-by` / `merged-into` |

`kx search` hides deprecated notes unless `--all` is given, which is the
serve-the-successor behaviour the research recommended for agent-facing tools.
Nothing in the AI-XF copy was modified by any `kx` command (checked by hash).

**Why trust was lost, isolated.** KnowledgeX treats a note whose `generated.at`
is later than its latest `verified[].at` as edited since it was checked, which
is the natural reading of OKF §5.2 (`generated.at` is "the content's last
meaningful change"). Every human verification in `examples/` was a bare date on
the same day as a timed `generated.at`, so it read as midnight, before the
content it verified. Two controls on the `f4031dc` copy restore all 5:
writing the same verification dates as `T23:59:59Z`, or deleting `generated`.
So KnowledgeX parses bare dates; the failure is that a bare date cannot say
which of two same-day events came first.

The first mechanical conversion for v0.4.3 (every bare date to `T00:00:00Z`)
reproduced the same failure in 8 fixture files, and was corrected to put each
verification after its generation. SPEC §5.6 now says to keep events in order
when converting, and `--stats` reports `changed_since_verified`.

## Findings

1. **OKF compatibility held where the spec promised it.** A third-party OKF
   bundle is AI-XF Level 0, and an AI-XF bundle is a clean OKF bundle to a
   third-party checker. The format layer interoperates.
2. **Trust did not travel, because of timestamps.** Bare dates in AI-XF's own
   examples cost all five human reviews in a real OKF consumer. This is the
   strongest evidence yet for v0.4.3's datetime rule (OKF PR #6), and a
   reason it needs the ordering caveat.
3. **Relationships do not interoperate.** Two OKF extensions express
   supersession and contradiction in incompatible frontmatter. Each tool's
   checks then report the other's retirements as successor-less. OKF issues
   #16 and #22 are where this would be settled; until then, a consumer could
   read the other dialect.
4. **Folder layout matters to real consumers.** OKF allows nested bundles;
   KnowledgeX reads flat ones. AI-XF's examples use subfolders, so they are
   invisible to it as published.
5. **Convergent design.** KnowledgeX independently arrived at rules AI-XF
   already has: trust does not travel with copies (§7.3a, E5), `aliases`
   for old titles, `Creation`/`Contradiction` log words, per-type expiry.
   It hides retired notes at search time, and detects renames by content
   fingerprint, which `ai-xf-export` now also does.

## Raised upstream (2026-10-02)

- Nested bundles invisible to KnowledgeX: [rahulnyk/KnowledgeX#22](https://github.com/rahulnyk/KnowledgeX/issues/22).
- Relationship dialects: [OKF #16](https://github.com/GoogleCloudPlatform/open-knowledge-format/issues/16#issuecomment-5962279243).
- Bare dates and event ordering: [OKF #24](https://github.com/GoogleCloudPlatform/open-knowledge-format/issues/24#issuecomment-5962278990).
- E8's tombstone evidence: [OKF #11](https://github.com/GoogleCloudPlatform/open-knowledge-format/issues/11#issuecomment-5962276648).

## Not adopted

- **Reading the KnowledgeX relationship dialect** in the validator. It would be
  a third spelling of the same edges; wait for OKF #16/#22 to choose a carrier,
  then adopt that one (AI-XF retires its own form when OKF adopts a feature).
- **Flat or nested layout:** OKF allows both; nothing to change here.
