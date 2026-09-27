# E6 Results — Integrity: ORAS + Cosign

**2026-09-26.** oras 1.3.4 (Homebrew), cosign v3.1.3 (Homebrew), Docker 29.8.0 (daemon running), registry:2 (Docker Hub, pulled fresh), Python 3.13 (`make-bundle.py`), git commit `f35d5db` at run time (moved during the session as the E3/E4/E5 agents landed their own work — irrelevant to this experiment, recorded here only because it is embedded in the artifact's `org.opencontainers.image.revision` annotation).

Built and run by a Sonnet agent per `docs/plans/2026-09-26-federation-experiments-plan.md` (E6 section). `run.sh` executed four times end-to-end during development (two while debugging `oras` path handling, two clean confirmation runs); all four produced the same pass/fail pattern.

Backend used: **local Docker registry** (`registry:2`, plain HTTP, port 5001 — 5000 was avoided per the plan's own note). Docker's daemon was running throughout, so the `--oci-layout` / `sign-blob` fallback path was **not exercised in anger**, but is implemented in `run.sh` and documented below (§ Fallback path) since a second party re-running this without Docker will hit it.

Cosign signed the **OCI artifact directly** (`cosign sign`, key-based, Referrers-API-attached signature) — it did **not** fall back to `sign-blob`. Keyless/OIDC was not attempted (would need an interactive browser login; explicitly out of scope per the task).

## Measure 1 — Package and push

`examples/` (the `example-payments` bundle) packaged as a single-layer OCI artifact:

- **Layer:** deterministic `tar.gz` of the bundle directory, entries rooted at `example-payments/`, sorted path order, `mtime=0` on every tar entry *and* on the gzip wrapper itself, `uid=gid=0`, `uname=gname=""`. Built with `experiments/e6-oci/make-bundle.py` (pure-Python `tarfile`/`gzip`, no shelling out to system `tar` — sidesteps the BSD-tar-vs-GNU-tar flag mismatch on macOS entirely).
- **Media type / artifact type:** `application/vnd.ai-xf.bundle.v1+tar+gzip` (proposed), used for both the manifest's `artifactType` and the single layer's `mediaType`.
- **Config:** the OCI empty descriptor (`application/vnd.oci.empty.v1+json`) — this experiment did not define an AI-XF-specific structured config blob. See § Judgement calls.
- **Annotations set:**

  | Key | Value (example run) | Namespace |
  |---|---|---|
  | `org.opencontainers.image.title` | `example-payments` | standard OCI |
  | `org.opencontainers.image.created` | `2026-09-21T08:10:00Z` (the bundle's own `generated:` timestamp) | standard OCI |
  | `org.opencontainers.image.revision` | `f35d5db19120a78cca231538c72e9b98f5437995` | standard OCI |
  | `io.aix.bundle.name` | `example-payments` | proposed AI-XF namespace |
  | `io.aix.bundle.namespace` | `example-payments` | proposed AI-XF namespace |
  | `io.aix.bundle.aix-version` | `0.3` | proposed AI-XF namespace |

  Mirrors the two-namespace annotation pattern (`org.opencontainers.image.*` + a project-specific `io.*` namespace) used by the reference implementation skimmed for this experiment, [ThomasVitale/agents-skills-oci-artifacts-spec](https://github.com/ThomasVitale/agents-skills-oci-artifacts-spec) (`io.agentskills.skill.name` there → `io.aix.bundle.name` here).

- **Manifest digest (a representative run):** `sha256:9308e291b9057189c894f1d36d7f93424f08364c556603854c3cdb5b673976df`
- **Layer digest (the tar.gz content itself, stable across every run):** `sha256:f40d7b9a5b577641f28a0faf0f1f8d095bdd192f999e63607dee431c56b00ee2`

**Reproducibility finding (not in the plan, discovered while building this):** `oras push` stamps `org.opencontainers.image.created` with the current wall-clock time by default *unless a value is supplied explicitly*. That default means the **manifest digest is not reproducible** across repeated pushes of byte-identical content — confirmed experimentally: two pushes of the same tarball with no explicit `created` annotation produced two different manifest digests; supplying a fixed value made every push produce the identical manifest digest. `run.sh` pins it to the bundle's own `generated:` field from `manifest.ai-xf.yaml`, so re-publishing unchanged content reproduces the exact same manifest digest — verified across two full clean runs (`sha256:9308e291b9...` both times). Anyone doing this for real needs to know this default exists; it is easy to assume "same content in, same digest out" and be wrong purely because of a timestamp annotation, which has nothing to do with `make-bundle.py`'s own tar/gzip determinism.

## Measure 2 — Verify (untouched) and tamper

| Step | Result | Notes |
|---|---|---|
| Verify untouched, by digest | **PASS** | `cosign verify --key cosign.pub` |
| Tamper: `payment-service.md` `status: deprecated` → `stable`, repackaged, pushed to the **same tag** | new manifest digest `sha256:9c41d9d...` (was `sha256:9308e29...`) | content-addressing did its job — a one-line frontmatter change moved the digest |
| Verify **by the tag** (now pointing at tampered content) | **FAIL** — `Error: no signatures found` | expected: no signature was ever attached to the *new* digest |
| Verify **by the ORIGINAL digest** | **PASS**, byte-identical signature output to the first verify | expected: content-addressed storage means the old blob, its manifest, and its signature are all still sitting in the registry, untouched by the tag move |

**Why both outcomes are correct, not just "one passed one failed":** Cosign signatures are attached to a specific manifest **digest** via the Referrers API, not to a tag. Moving a tag to point at new content does not move, copy, or extend the signature — the new digest simply has no `Referrers` entry of type `signature`. The tag is a mutable pointer; the digest is the thing that was actually signed. This is exactly the property E1 needed and didn't have from git alone (E1's M3: provenance is only recoverable from the manifest digest / commit, not from a mutable ref) — E6 shows the same principle enforced cryptographically rather than just by convention.

## Measure 2 (continued) — Wall-clock and command count

| Flow | Wall-clock (representative run, of 2 clean runs) | Commands |
|---|---|---|
| **Producer** (package + push + sign) | **1.43–1.57s** | `make-bundle.py` (package) → `oras push` → `cosign sign` = 3 commands, after a one-time `cosign generate-key-pair` (0.02s, excluded — a producer generates a key pair once and reuses it across every future push, so it doesn't belong in the per-publish cost) |
| **Consumer** (pull + verify + unpack) | **0.42–0.56s** | `oras pull` → `cosign verify` → `tar -xzf` = 3 commands |

**Commands a first-time consumer needs, counted literally, against a registry and public key they've never used before:**

1. `brew install oras cosign` (one-time, if not already installed)
2. *(out-of-band, not a shell command: obtain the producer's `cosign.pub` — e.g. from a release page or the federation manifest — cosign has no built-in discovery for a bare key)*
3. `oras pull <ref> -o <dir>` — downloads the layer blob; **does not extract it**
4. `cosign verify --key cosign.pub <digest-ref>` — must be the **digest** reference to get the "verify what you think you're signing" guarantee `cosign sign --help` itself warns about; a tag reference degrades the guarantee to "whatever the tag currently points at"
5. `tar -xzf <bundle>.tar.gz` — to actually get the AI-XF bundle directory back

**Four shell commands** (one of them one-time/amortised) plus one manual, non-scriptable step (getting the public key). All local registry/local key-pair local timings; a real GHCR round-trip would add real network latency to steps 3–4, but not add or remove any command.

## Measure 3 — Validate the pulled bundle

```
python3 tools/ai-xf-validate.py <unpacked-original>/example-payments --level 3
```

```
AI-XF validator — bundle: .../unpacked/example-payments
  concepts: 7
  highest level achieved: 3 (AI-XF Federated)
  checked at level: 3
  ✓ no findings

PASS at level 3 (0 error(s), 0 warning(s))
```

The bundle that went through package → push → sign → pull → unpack is byte-identical to `examples/` and validates cleanly at Level 3 — the OCI round-trip is transparent to the AI-XF format, exactly as the reference agent-skills spec's design goal 3 ("transparent packaging") intends.

## Measure 3 (continued) — Can `manifest.ai-xf.yaml` carry the digest?

**No — not the bundle's own `manifest.ai-xf.yaml`, and this is structural, not a limitation to fix later.**

The digest is a hash of the *layer*, and the layer is a tar.gz of the whole bundle directory — including `manifest.ai-xf.yaml` itself. Writing the digest into the file that gets hashed is the same chicken-and-egg problem as a file trying to contain its own checksum: writing the digest changes the file, which changes the hash, which invalidates the digest just written. There is no fixed point short of an infinite regress (this is the same reason git commits don't contain their own SHA inline, and why a code-signing certificate is never embedded inside the binary segment it signs — see also `CLAUDE.md`'s note that a hook script "can't validate its own hash" for the same structural reason).

**The OCI spec itself solves this by keeping the digest outside the artifact, in the registry and in the signature** — which is exactly the pattern this experiment exercised:

- The digest lives in the **registry's manifest store** (content-addressed by construction — the registry computed it, the artifact never had to know it).
- The **signature** references the digest from outside the artifact (Cosign's Referrers API entry points *at* a digest; it isn't a file inside the signed content).
- The **federation manifest** (`federation.ai-xf.yaml`, from E1) is the right place at the AI-XF layer for the same reason: it's a document *about* bundles, not one of the bundles, so it can safely name a digest without that digest describing itself.

**Recommendation for v0.4**, building directly on E1's finding ("a federation manifest is required for provenance, not for resolution"): extend `federation.ai-xf.yaml`'s existing `source: git` / `source: path` bundle-entry pattern with a third option, `source: oci`, carrying a `ref` and a `digest` — the OCI equivalent of `source: git`'s `ref: <commit>`:

```yaml
bundles:
  - namespace: example-payments
    source: oci
    ref: ghcr.io/exampleorg/example-payments:v1
    digest: sha256:9308e291b9057189c894f1d36d7f93424f08364c556603854c3cdb5b673976df
```

This is deliberately **not** the plan's original sketch of a `distribution: {oci: <ref>, digest: ...}` block *inside* `manifest.ai-xf.yaml`. It keeps the digest where E1 already put provenance (the federation manifest, external to every bundle it describes) instead of introducing a second, self-referential place to put it. A tool that publishes a bundle would: package → push → sign → **then** write the resulting digest into whatever `federation.ai-xf.yaml` its consumers use — an ordinary "record what just happened" step, not a paradox.

**v0.4 should mention OCI distribution** as a third `source:` option alongside `git` and `path` in the federation manifest (E1), documented with the annotation and layer conventions from this experiment. It should **not** add a `digest` field to `manifest.ai-xf.yaml` itself.

## Fallback path (not exercised — Docker was running)

`run.sh` detects `docker info` failing and, in that branch: pushes with `oras push --oci-layout <dir>:<tag>` (no registry needed) and signs with `cosign sign-blob --key cosign.key <tarball>` instead of `cosign sign`. This is not equivalent, and the script says so at runtime:

- `cosign sign` attaches a signature to a **specific digest** in a registry, discoverable by anyone who has the reference, via the Referrers API — no side channel needed.
- `cosign sign-blob` produces a **detached `.sig` file** next to the tarball. It signs the *file*, not an OCI manifest/digest at all (`cosign sign --help`/`verify --help` in v3.1.3 have no `--oci-layout` or local-image option, confirmed by inspection). A consumer must receive the `.sig` out of band (email, a release asset, a second file in the same directory) and run `cosign verify-blob` against both files together. There is nothing to attach the signature *to* inside an OCI layout with no registry.

Checked at v3.1.3; worth re-checking if this experiment is re-run against a newer cosign, since `--oci-layout` support for `sign`/`verify` may land later.

## Judgement calls

1. **`oras push` rejects absolute file paths by default** (`Error: absolute file path detected`). Resolved by `cd`-ing into the scratch directory and pushing/pulling with relative filenames, rather than reaching for `--disable-path-validation` — no reason to disable a real safety check when a relative path does the job.
2. **The layer's `org.opencontainers.image.title` annotation is derived from the pushed file's path** and is what `oras pull` uses as the output filename; an absolute title trips oras's own path-traversal guard on pull (`path traversal disallowed`). Same fix as (1): push with a relative name.
3. **Single artifact type used for both `artifactType` and the layer `mediaType`**, per the plan's literal wording ("artifact type `application/vnd.ai-xf.bundle.v1+tar+gzip`"). The reference spec skimmed for this experiment separates a `skill.v1` artifact type from a `skill.content.v1.tar+gzip` layer media type, and defines a structured config blob carrying queryable metadata (name/version/description) without unpacking the layer. This experiment used the OCI empty config descriptor instead — sufficient to answer E6's three measures, but a real v0.4 proposal should probably define an AI-XF config schema (bundle name, namespace, `ai-xf` version, concept count) mirroring `manifest.ai-xf.yaml`'s own top-level fields, the same way the reference spec's config mirrors `SKILL.md` frontmatter. Left as a follow-up, not implemented here.
4. **`cosign verify`/`sign` require `--allow-http-registry`** against the local plain-HTTP registry — expected and fine for an experiment; a real deployment (GHCR, ECR, etc.) is TLS by default and wouldn't need it.
5. **Key-based signing only** (`cosign generate-key-pair`, `COSIGN_PASSWORD=""`), per the task's explicit instruction not to attempt keyless/OIDC (interactive browser login). The private key lives in `/tmp/ai-xf-e6/keys/`, outside the repo, and `run.sh` reuses it across runs rather than regenerating (regeneration would itself be a reason for the tag-verify test to fail, muddying the tamper-test result with an unrelated cause).
6. **`org.opencontainers.image.created` pinned to the bundle's own `generated:` field** — see Measure 1's reproducibility finding. Without this, re-running `run.sh` twice with unchanged bundle content produces two different "original" digests, which would make the write-up's specific digest values meaningless from one run to the next (they're still internally consistent per run — the tamper test still works — but not citable as *the* digest for this bundle).
7. **Local Docker registry, not GHCR**, per the task's explicit instruction (the available `gh` token lacks `write:packages`). Port 5001, not 5000, per the task's own note that 5000 is often taken on macOS (AirPlay Receiver) — confirmed unnecessary to check, just followed the instruction.

## Decision this supports (plan §2, E6 "Decides")

- **v0.4 should mention OCI distribution**, scoped as a third `source:` option in `federation.ai-xf.yaml` (E1) — `git`, `path`, `oci` — not as a change to `manifest.ai-xf.yaml`.
- **`manifest.ai-xf.yaml` should NOT gain a `digest` field.** The digest belongs one level up, in the document that references bundles rather than in a bundle referencing itself.
- Signed OCI distribution catches tampering correctly and cheaply: sub-2-second producer flow, sub-second consumer flow, zero false passes and zero false failures across every run of this experiment.
