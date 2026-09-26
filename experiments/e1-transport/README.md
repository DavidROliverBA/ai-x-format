# E1 — transport and the root manifest

Part of the federation experiments plan (vault doc
`docs/plans/2026-09-26-federation-experiments-plan.md`, §1 fixtures, §2 E1 —
not part of this repo, kept in the planning vault). Everything here is
self-contained under
`experiments/e1-transport/` and only reads from `experiments/fixtures/` and
`examples/` — it never touches `experiments/e2-resolution/`,
`experiments/fixtures/`, or `tools/aix-validate.py`.

## Question

Can a consumer resolve every cross-bundle reference, and reproduce exactly
what it read, under each of three ways of assembling a federation of bundles
into one working checkout: git submodules, git subtree, and git subtree plus
a hand-written manifest?

## The three layouts

All three start from the same three bundles, each pushed to its own local
bare git repository (built once by `setup.sh`, acting as a "remote"):

| Remote | Built from |
|---|---|
| `data-eng.git` | `experiments/fixtures/data-eng` (namespace `data-eng`) |
| `household.git` | `experiments/fixtures/household` (namespace `household`) |
| `payments.git` | `examples/` (namespace `example-payments`) |

- **(a) `layout-a-submodules.sh`** — `consumer-a`: the three bundles as git
  submodules at `bundles/{data-eng,household,payments}`. No human-authored
  federation manifest. Instead the script **generates**
  `consumer-a/federation.aix.yaml` from `.gitmodules` + `git submodule
  status`, to test whether `.gitmodules` alone carries enough information to
  reconstruct one.
- **(b) `layout-b-subtree.sh`** — `consumer-b`: the three bundles merged in
  with `git subtree add --prefix bundles/<ns> <remote> main --squash`, with
  **no** manifest checked in. The script then does **naive discovery**: scan
  for `manifest.aix.yaml` files under the tree, read each one's own
  `namespace:` field, and write what that naive scan could reconstruct to
  `consumer-b/discovered.yaml` (`ref: null` throughout — see M3 below).
- **(c) `layout-c-subtree-manifest.sh`** — `consumer-c`: identical subtree
  merges to (b), but this time a **hand-written** `federation.aix.yaml` is
  also checked in. Its `source: path` entries point at `./bundles/<ns>`, and
  its `ref` field records real per-bundle provenance recovered from the
  squash commit's `git-subtree-split:` trailer (git plumbing, not an AIX
  concept — see M3).

## How to run

```bash
cd /Users/davidoliver/github/aix-format
./experiments/e1-transport/run.sh
```

Everything is built under a scratch directory, `$E1_WORK` (default
`/tmp/aix-e1`), which is wiped at the start of every `setup.sh` run — so
`run.sh` is idempotent and safe to re-run. Override the location with
`E1_WORK=/some/other/path ./experiments/e1-transport/run.sh`.

Individual stages can also be run on their own once `setup.sh` has run once:

```bash
./experiments/e1-transport/setup.sh
./experiments/e1-transport/layout-a-submodules.sh
./experiments/e1-transport/layout-b-subtree.sh
./experiments/e1-transport/layout-c-subtree-manifest.sh
```

`run.sh` validates `bundles/data-eng` (and, for M2, `bundles/payments`) in
each consumer with:

```bash
python3 tools/aix-validate.py <consumer>/bundles/data-eng \
  --level 3 --federation <consumer's federation manifest> --json --stats
```

and writes the raw JSON under `$E1_WORK/results/`, plus the final table to
`$E1_WORK/e1-results.md` (also printed to stdout).

If `aix-validate.py` does not yet support `--federation` when this is run,
`run.sh` still builds and validates (at plain `--level 3`, no
`--federation`) all three layouts, and marks the M1 column "validator flag
pending" in the results table rather than failing.

## What is measured

Copied verbatim from the plan (E1):

1. **Qualified references resolved / total** (target 100% where a manifest
   or `.gitmodules` exists; expect < 100% for (b)).
2. **Rename a concept file in `data-eng` (id unchanged): references still
   resolve?** (target: yes, all layouts).
3. **Provenance: from the consumer alone, name the exact commit of each
   bundle** (target: yes for (a) and (c); expect "whole-tree SHA only" for
   (b)).
4. **Rebuild from scratch on a clean clone, byte-identical** (target: yes).

`bundles/data-eng` is used as the bundle-under-test for M1, M3 and M4
because it carries the most cross-bundle links in the fixture set (two
qualified references into `example-payments`). M2 validates
`bundles/payments` instead, because the qualified reference under rename
test — `payment-service-v2` → `data-eng/orders-events` — is declared on the
payments side (`examples/concepts/payment-service-v2.md`), not on
`data-eng`'s.

## Decides

Whether `federation.aix.yaml` is needed at all (if `.gitmodules` alone
passes every measure, the spec should just say "or `.gitmodules`"), and what
fields it must carry.

## Notes on deviations from the plan's literal sketch

- **`subdir` for `source: git` entries.** The plan's manifest sketch and this
  task's brief both mention `subdir: .` for a git-submodule-derived entry.
  Reading the implemented `load_federation()` in `tools/aix-validate.py`: a
  `source: git` entry resolves as `find_repo_root(federation_manifest's own
  directory) / subdir` — it does not clone `repo:`, and `subdir` is relative
  to the repo that *holds the federation manifest*, not to the submodule's
  own repo. Since `consumer-a/federation.aix.yaml` sits at `consumer-a`'s own
  root (a distinct git repo from each submodule), `subdir: .` resolves to
  `consumer-a` itself — which has no `manifest.aix.yaml` — and every bundle
  fails to load. `layout-a-submodules.sh` instead generates `subdir:
  bundles/<name>`, which is what the implemented resolver actually needs.
  `ref` still carries the exact submodule SHA, and `repo` still carries the
  real submodule URL (reported for provenance only — git fetching is
  explicitly out of scope for this flag).
- **M1 for layout (b) turned out to be 100%, not "< 100%" as the plan
  expects.** The naive discovery script only has to scan for
  `manifest.aix.yaml` files and read each one's own `namespace:` field —
  `git subtree add --squash` copies that file byte-for-byte along with the
  rest of the bundle, so the namespace survives the squash merge with zero
  extra effort. What does *not* survive is **provenance** (M3), which needs
  git history, not just the working tree. See `e1-results.md` for the actual
  numbers each run produces.

## Files

| File | Purpose |
|---|---|
| `setup.sh` | Builds the three local bare "remote" repos and `remotes.json` |
| `layout-a-submodules.sh` | Builds `consumer-a` (submodules) + generates its federation manifest |
| `layout-b-subtree.sh` | Builds `consumer-b` (subtree, no manifest) + `discovered.yaml` |
| `layout-c-subtree-manifest.sh` | Builds `consumer-c` (subtree) + hand-written `federation.aix.yaml` |
| `lib-subtree.sh` | Shared subtree-build helper sourced by (b) and (c) |
| `run.sh` | Orchestrates setup + all three layouts, runs the validator, computes M1–M4 |
| `compute-results.py` | Reads the validator JSON + git state, writes `e1-results.md` |
