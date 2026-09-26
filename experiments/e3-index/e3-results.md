# E3 results: cross-bundle index

**Date:** 2026-09-26  
**qmd version:** qmd 2.8.3 (facd35e)  
**Python:** 3.14.4

## Configurations

- (a) qmd, one collection per bundle (`example-payments`, `data-eng`, `household`), queried with no `-c` filter so all three collections are searched together.
- (b) qmd, one collection `all` over a materialised copy of the three bundles (qmd collections are a single path; symlinks aren't followed, so the union is a real copy under `all-bundles/`, with the original bundle name as the top-level directory in each case).
- (c) `bm25.py` — stdlib-only BM25 (k1=1.5, b=0.75) over the union, namespace/id read from each bundle's own manifest/frontmatter.

Mode: **hybrid** (BM25 + vector + LLM rerank via `qmd query`) for (a) and (b) — the model download and embedding both completed without falling back to BM25-only. (c) is BM25-only by construction.

P@5 formula: `|top5 ∩ expected| / min(5, |expected|)`, per question, then averaged.

## Retrieval quality

| Metric | (a) qmd per-bundle collections | (b) qmd single collection | (c) plain BM25 |
|---|---|---|---|
| Mean P@5, overall (20 q) | 0.754 | 0.738 | 0.717 |
| Mean P@5, `kind: cross` (12 q) | 0.715 | 0.688 | 0.667 |
| Mean P@5, `kind: single` (8 q) | 0.812 | 0.812 | 0.792 |
| Collision top-hit correct (x/4) | 2/4 | 3/4 | 4/4 |

## Index build cost

On-disk size excludes qmd's shared model weights (~2.1GB embedding/rerank/query-expansion GGUF files) — those are a fixed one-time tool-setup cost, identical regardless of corpus or configuration, and would otherwise swamp any real difference between (a) and (b). Build time likewise excludes the model download (also a one-time, shared cost); it covers collection add (lexical indexing) + `qmd embed` (vector indexing) for (a)/(b), and the in-process `build()` call for (c).

| Metric | (a) | (b) | (c) |
|---|---|---|---|
| Build time | 2.4s | 2.1s | 0.0s |
| On-disk index size | 9.9 MB | 10.0 MB | 40.1 KB |

## Per-question results

`*` marks the 4 collision questions. P@5 shown per config; ✓/✗ in the last column is top-hit-correct, shown only for collision questions (blank otherwise).

| Q | Kind | P@5 (a) | P@5 (b) | P@5 (c) | Top-hit ok (a/b/c) |
|---|---|---|---|---|---|
| q01* | cross | 1.00 | 0.50 | 0.50 | ✗/✗/✓ |
| q02* | cross | 0.50 | 1.00 | 0.50 | ✓/✓/✓ |
| q03* | cross | 1.00 | 1.00 | 1.00 | ✗/✓/✓ |
| q04* | cross | 1.00 | 1.00 | 1.00 | ✓/✓/✓ |
| q05 | cross | 1.00 | 1.00 | 1.00 |  |
| q06 | cross | 0.50 | 0.50 | 1.00 |  |
| q07 | cross | 0.33 | 0.33 | 0.33 |  |
| q08 | cross | 1.00 | 1.00 | 1.00 |  |
| q09 | cross | 0.50 | 0.50 | 0.50 |  |
| q10 | cross | 1.00 | 0.67 | 0.67 |  |
| q11 | cross | 0.25 | 0.25 | 0.00 |  |
| q12 | cross | 0.50 | 0.50 | 0.50 |  |
| q13 | single | 0.50 | 0.50 | 0.50 |  |
| q14 | single | 1.00 | 1.00 | 0.50 |  |
| q15 | single | 1.00 | 1.00 | 1.00 |  |
| q16 | single | 0.67 | 0.67 | 1.00 |  |
| q17 | single | 0.33 | 0.33 | 0.33 |  |
| q18 | single | 1.00 | 1.00 | 1.00 |  |
| q19 | single | 1.00 | 1.00 | 1.00 |  |
| q20 | single | 1.00 | 1.00 | 1.00 |  |

## Notes and judgement calls

- **qmd's hybrid mode is not deterministic run-to-run.** `qmd query` runs an LLM query-expansion step (generates `lex:`/`vec:`/`hyde:` sub-queries) and an LLM reranker before returning results; re-running this exact script end to end has produced different P@5 numbers between runs (e.g. config (a)'s collision top-hit score moved between runs while (c)'s plain-BM25 score for the same questions did not). Config (c) is fully deterministic by construction. Treat single-run qmd numbers as one sample, not an exact figure — the qualitative pattern (which configuration wins on which measure) is what's worth reading, not the third decimal place.
- **Query phrasing was not tuned.** Every configuration was queried with the literal `question` text from questions.yaml, unmodified, once, per the task's instruction not to tune queries to improve numbers.
- **qmd hit → namespace/id mapping.** For (a), the collection name returned in the `qmd://` file path *is* the namespace (collections were named exactly by namespace). For (b), the namespace is the first path segment under the `all` collection root, because that's how `all-bundles/` was laid out. In both cases the actual on-disk file was then read to pull its frontmatter `id:` field, rather than trusting the file's basename to equal the id (they happen to match in every fixture file, but the mapping doesn't assume that).
- **No dedup/tie-breaking beyond qmd's own ranking.** The raw top-5 hits from each tool are used as returned; if two of the five hits happened to be chunks of the same file (same namespace/id twice), that would silently reduce the number of *distinct* documents actually represented in the top 5, and P@5 would count the id only once (via set intersection) — this did not appear to occur in this run (qmd generally returned 5 distinct files) but the runner does not special-case it.
- **`index.md`/`log.md` have no frontmatter `id:`.** They fall back to their file stem (`index`, `log`) for identification purposes. They can never satisfy an `expected` entry (no question's answer is one of these bundle-overview files), so when one appears in a top-5 it is pure noise against P@5 — which happened for all three configurations at least once, most often for the single-collection/BM25-union configs where a bundle-level overview file legitimately shares a lot of vocabulary with its own concepts.
- **Symlinks: config (b)'s union is a real copy, not a symlink tree.** qmd's collection walker does not follow symlinks (confirmed empirically — a collection over a symlink farm indexed 0 files), so `all-bundles/` under this directory is an actual copy of the three fixture bundles, made once at build time. This is read-only scratch content for indexing, not a fixture edit.
- **Model weights and on-disk size.** qmd's ~2.1GB of GGUF model weights (embedding, reranker, query-expansion) are downloaded once into `qmd_home/_shared_models/` and copied into each config's own cache rather than re-downloaded — identical models regardless of corpus, so this only saves wall-clock on repeat builds. Both the build-time and on-disk-size figures above explicitly exclude these shared weights, since including them would make (a) and (b) look identical in size (correct) while making the size column meaningless as a measure of index growth (the actual point of the measurement).
