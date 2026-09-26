# E2 — Identity resolution under collision

Validator-side test cases for **E2** of the federation experiments plan
(`~/Documents/MyVault/docs/plans/2026-09-26-federation-experiments-plan.md`,
§1 and §2 "E2"). Question: when two bundles share an `id`, what does a
consumer do with a qualified, an unqualified, and an explicit-scheme
reference? This directory tests the `aix-validate.py --federation` resolver
added for E1/E2 against three small, self-contained fixture bundles.

These fixtures are independent of `experiments/fixtures/` (built separately
for E1/E3+) — nothing here depends on that directory existing.

## Layout

```
e2-resolution/
├── README.md                       # this file
├── federation.aix.yaml             # lists bundle-a, bundle-b, bundle-c (all source: path)
├── bundle-a/                       # namespace `a` — ids: shared, only-a
├── bundle-b/                       # namespace `b` — ids: shared, only-b
├── bundle-c/                       # namespace `c` — the consumer under test
│   └── concepts/linker.md          # one concept, six `links` entries — see below
├── baseline-examples-level2.json   # examples/ --level 2 --json, captured BEFORE
│                                   # --federation was added to aix-validate.py
├── test_resolution.py              # stdlib unittest, subprocess + --json
└── run.sh                          # runs the validator by hand, then the test suite
```

## The collision

`bundle-a` and `bundle-b` both declare a concept with `id: shared` — a
genuine cross-bundle id collision, the scenario §9.2's Foam rule exists for.
`bundle-a` additionally has `only-a` (unique), `bundle-b` has `only-b`
(unique, unreferenced — present only so bundle-b isn't a single-purpose
stub).

## The six cases (`bundle-c/concepts/linker.md`)

| # | `to:` | Form | Expected result |
|---|-------|------|------------------|
| 1 | `only-a` | unqualified | Doesn't resolve in bundle-c itself; resolves in exactly one other bundle (`a`) → **warning**, Foam rule, names `a`, chosen `a`. |
| 2 | `shared` | unqualified | Resolves in **both** `a` and `b` → **warning**, names both, chosen `a` (alphabetically first). |
| 3 | `a/only-a` | qualified | Resolves against the federation index → **no finding**. |
| 4 | `aix://b/shared` | explicit `aix://` | Resolves against the federation index → **no finding**. Also exercises the `body_link_targets` change: the body links to this exact URL, proving the scheme is recognised (and would register `b/shared` too, had the body used the bare form instead). |
| 5 | `c/something` | qualified, own namespace | **Error** — "MUST NOT qualify same-bundle references" (SPEC §9.2) — fires even though `bundle-c/concepts/something.md` exists and would otherwise resolve. This is the one case that makes the bundle fail Level 2. |
| 6 | `b/missing` | qualified | No such id anywhere in the federation → **warning**, tolerated (§11.1). |

Total: 4 findings (2 warnings from the Foam rule, 1 error from
self-qualification, 1 warning from an unresolved qualified reference), 0
findings from cases 3 and 4 — the "zero silent misresolutions" check is that
absence, asserted explicitly in `test_resolution.py`.

## Running

```bash
./run.sh
```

Runs the validator directly against `bundle-c --federation federation.aix.yaml`
under both the stdlib fallback YAML parser and real PyYAML (`uv run --with
pyyaml`), diffs `examples/` (no `--federation`) between parsers and against
the pre-change baseline, then runs the unittest suite.

Or directly:

```bash
python3 test_resolution.py -v
```

`test_resolution.py` skips the PyYAML-specific tests if `uv` isn't on `PATH`
(the stdlib-parser tests and the fixture-content tests still run).

## What the tests assert

- **`RegressionUnchanged`** — `examples/ --level 2 --json` (no `--federation`)
  is unchanged from `baseline-examples-level2.json`, a copy captured with
  `python3 tools/aix-validate.py examples --level 2 --json` *before* the
  `--federation` flag existed. Checked under both parsers, and the two
  parsers are also checked against each other directly.
- **`FederationResolution`** — the six-case table above, exactly: 4 findings,
  each with the right severity and message substrings, and explicit
  assertions that `links[2]` (case 3) and `links[3]` (case 4) produce no
  finding at all. Also checks the JSON `federation` provenance block (E1:
  namespace, resolved root, `ref`), the `--stats` `federation` block
  (bundles held, concepts per namespace, colliding ids, qualified
  resolved/unresolved counts, Foam-rule resolution count), and the text-mode
  provenance report lines.
- Both test classes run their JSON-producing case under stdlib and PyYAML
  and assert the two are identical.

## Spec ambiguities resolved while implementing

1. **Body-link mirroring for federation-qualified references.** SPEC §6.4
   says mirroring is a MUST only for same-bundle targets and SHOULD/MAY for
   federation-qualified ones. This implementation extends that "not
   mandatory" treatment to the Foam-rule case too: an unqualified reference
   that resolves in *another* bundle is, definitionally, not "inside the
   same bundle" once resolved that way, so it is exempt from the MUST-mirror
   check even though its `to:` text looks identical to a same-bundle
   reference. Only a `to:` that resolves via this bundle's own `ids` or a
   same-bundle relative path is held to the MUST-mirror rule.
2. **`source: git` in `federation.aix.yaml`.** Per the task brief, treated as
   a local path for this experiment: `subdir` is resolved relative to the
   git repository that contains the *federation manifest itself* (walking
   up from the manifest's directory for a `.git`), not the `repo:` URL the
   full E1 format proposes. `ref` is recorded verbatim in the provenance
   report but never used to check out or fetch anything — cloning is
   explicitly out of scope. This fixture doesn't exercise `source: git`
   (all three bundles are `source: path`); it was smoke-tested by hand
   against this same repository during development.
3. **Resolution order.** Own bundle's `ids` and same-bundle relative paths
   are tried first (unchanged from the non-federated code path); only on
   failure does the Foam rule search other bundles' namespaces in plain
   alphabetical order. A reference that resolves in the own bundle never
   triggers the Foam rule or a warning, even when other bundles also carry
   that id (case 2 shows the opposite: bundle-c has neither `only-a` nor
   `shared`, so both fall through to the Foam search).
4. **`aix://` and Level 3's qualified-reference well-formedness check.** The
   pre-existing Level 3 check ("`to:` containing `/` must be a well-formed
   `namespace/id`") did not know about the new explicit `aix://namespace/id`
   form and would have flagged it as malformed. Both checks now share one
   `qualified_parts()` helper so `aix://` is recognised consistently
   everywhere a qualified reference is parsed.
5. **Federation-level vocab checks** (types/rels lists at the federation
   level) are implemented in `aix-validate.py` per the task brief but not
   exercised by this fixture — `federation.aix.yaml` here has no
   `vocabularies` key. That check belongs more naturally with an E3-style
   fixture that already has shared vocab files; adding one here would have
   pulled unrelated findings into this test's exact-count assertions.
