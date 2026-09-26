#!/usr/bin/env bash
# experiments/e6-oci/run.sh
#
# E6 — Integrity: ORAS + Cosign
# (docs/plans/2026-09-26-federation-experiments-plan.md, E6 section)
#
# Packages examples/ (the `example-payments` bundle) as an OCI artifact,
# pushes it with ORAS, signs it with Cosign (local key pair), verifies,
# tampers with a frontmatter value and re-pushes to the same tag, then
# re-verifies to show:
#   - verification FAILS against the tampered tag (no signature covers
#     the new digest)
#   - verification still PASSES against the original digest reference
#     (content-addressed — the old content, and its signature, are
#     untouched)
#
# Also measures wall-clock for the producer flow (package+push+sign) and
# the consumer flow (pull+verify+unpack), counts the distinct commands a
# first-time consumer needs, and re-validates the pulled original bundle
# with tools/aix-validate.py --level 3.
#
# Environment:
#   - oras and cosign are installed via Homebrew if missing.
#   - Prefers a local Docker registry (plain HTTP, port 5001) if the
#     Docker daemon is running; falls back to oras's --oci-layout mode
#     (no registry) otherwise, with cosign sign-blob in place of
#     cosign sign (see NOTE in that branch for why they are not
#     equivalent).
#
# Work directory: $E6_WORK (default /tmp/aix-e6). Cosign keys persist in
# $E6_WORK/keys/ across runs (not written into the repo). Everything else
# under $E6_WORK is ephemeral scratch space, removed at the end of a
# successful run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUNDLE_SRC="$REPO_ROOT/examples"
VALIDATOR="$REPO_ROOT/tools/aix-validate.py"
MAKE_BUNDLE="$SCRIPT_DIR/make-bundle.py"

E6_WORK="${E6_WORK:-/tmp/aix-e6}"
KEYS="$E6_WORK/keys"
SCRATCH="$E6_WORK/scratch"
REGISTRY_NAME="aix-e6-registry"
REGISTRY_PORT="5001"
REPO_PATH="aix/example-payments"
TAG="e6-experiment"
ARTIFACT_TYPE="application/vnd.aix.bundle.v1+tar+gzip"
ROOT_NAME="example-payments"

mkdir -p "$KEYS" "$SCRATCH"
rm -rf "${SCRATCH:?}"/*

now_s() { python3 -c 'import time; print(f"{time.time():.3f}")'; }

CLEANUP_DONE=0
cleanup() {
  if [ "$CLEANUP_DONE" -eq 1 ]; then return; fi
  CLEANUP_DONE=1
  echo
  echo "--- cleanup ---"
  if [ "${USE_DOCKER:-0}" -eq 1 ]; then
    docker rm -f "$REGISTRY_NAME" >/dev/null 2>&1 && echo "removed container $REGISTRY_NAME" || echo "(no container to remove)"
  fi
  rm -rf "$SCRATCH"
  echo "scratch removed ($SCRATCH); keys kept ($KEYS)"
}
trap cleanup EXIT

echo "############################################"
echo "# E6 — Integrity: ORAS + Cosign"
echo "############################################"
echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo
echo "--- 0. Tool check ---"
for cmd in oras cosign; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "$cmd not found — installing via Homebrew"
    brew install "$cmd"
  fi
done
ORAS_VERSION="$(oras version | head -1)"
COSIGN_VERSION="$(cosign version 2>&1 | grep GitVersion | tr -s ' ')"
echo "oras: $ORAS_VERSION"
echo "cosign: $COSIGN_VERSION"

echo
echo "--- 0b. Registry backend check ---"
USE_DOCKER=0
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  USE_DOCKER=1
  echo "Docker daemon is running — using a local plain-HTTP registry on port $REGISTRY_PORT."
else
  echo "Docker daemon NOT available — falling back to oras --oci-layout mode (no registry)."
  echo "Cosign cannot sign an OCI-layout reference in this version (checked: cosign sign --help"
  echo "has no --oci-layout/local-image flag); falling back to cosign sign-blob on a tarball of"
  echo "the bundle. This signs the FILE, not the OCI manifest/digest, and produces a detached"
  echo ".sig the consumer must carry alongside the tarball out of band — it is not discoverable"
  echo "via the registry's Referrers API the way cosign sign attachments are."
fi

REF_BASE=""
if [ "$USE_DOCKER" -eq 1 ]; then
  echo
  echo "--- 1. Start local registry ---"
  docker rm -f "$REGISTRY_NAME" >/dev/null 2>&1 || true
  docker run -d --name "$REGISTRY_NAME" -p "${REGISTRY_PORT}:5000" registry:2 >/dev/null
  for i in $(seq 1 15); do
    if curl -sf "http://localhost:${REGISTRY_PORT}/v2/_catalog" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  curl -sf "http://localhost:${REGISTRY_PORT}/v2/_catalog" >/dev/null 2>&1 || { echo "registry did not come up"; exit 1; }
  echo "registry up on localhost:${REGISTRY_PORT}"
  REF_BASE="localhost:${REGISTRY_PORT}/${REPO_PATH}"
fi

echo
echo "--- 2. Read bundle metadata ---"
AIX_NAME="$(grep -m1 '^name:' "$BUNDLE_SRC/manifest.aix.yaml" | sed 's/^name: *//')"
AIX_NAMESPACE="$(grep -m1 '^namespace:' "$BUNDLE_SRC/manifest.aix.yaml" | sed 's/^namespace: *//')"
AIX_VERSION="$(grep -m1 '^aix:' "$BUNDLE_SRC/manifest.aix.yaml" | sed 's/^aix: *//; s/"//g')"
AIX_GENERATED="$(grep -m1 '^generated:' "$BUNDLE_SRC/manifest.aix.yaml" | sed 's/^generated: *//')"
GIT_COMMIT="$(cd "$REPO_ROOT" && git rev-parse --short HEAD)"
GIT_COMMIT_FULL="$(cd "$REPO_ROOT" && git rev-parse HEAD)"
echo "name=$AIX_NAME namespace=$AIX_NAMESPACE aix=$AIX_VERSION commit=$GIT_COMMIT"

# oras auto-stamps org.opencontainers.image.created with the current wall-clock
# time on every push unless a value is supplied explicitly, which makes the
# MANIFEST digest non-reproducible across pushes even when the layer (the
# bundle content) is byte-identical (confirmed experimentally: two pushes of
# the same tarball, no explicit `created`, gave two different manifest
# digests; supplying a fixed value made them identical). We pin it to the
# bundle's own `generated:` timestamp from manifest.aix.yaml, which is
# itself deterministic per-content, so a re-push of unchanged content
# reproduces the exact same manifest digest.
ANNOTATIONS=(
  --annotation "org.opencontainers.image.title=$AIX_NAME"
  --annotation "org.opencontainers.image.created=$AIX_GENERATED"
  --annotation "org.opencontainers.image.revision=$GIT_COMMIT_FULL"
  --annotation "io.aix.bundle.name=$AIX_NAME"
  --annotation "io.aix.bundle.namespace=$AIX_NAMESPACE"
  --annotation "io.aix.bundle.aix-version=$AIX_VERSION"
)

echo
echo "--- 3. Cosign key pair (generated once, reused across pushes) ---"
KEYGEN_T0="$(now_s)"
if [ ! -f "$KEYS/cosign.key" ]; then
  ( cd "$KEYS" && COSIGN_PASSWORD="" cosign generate-key-pair )
else
  echo "reusing existing key pair in $KEYS (delete it to regenerate)"
fi
KEYGEN_T1="$(now_s)"
KEYGEN_SECS="$(python3 -c "print(f'{$KEYGEN_T1 - $KEYGEN_T0:.2f}')")"

echo
echo "############################################"
echo "# Producer flow: package + push + sign"
echo "############################################"
PRODUCER_T0="$(now_s)"

echo "--- 4a. Package (deterministic tar.gz) ---"
BUNDLE_TGZ="$SCRATCH/${ROOT_NAME}.tar.gz"
python3 "$MAKE_BUNDLE" "$BUNDLE_SRC" "$BUNDLE_TGZ" --root-name "$ROOT_NAME"
BUNDLE_SHA256="$(shasum -a 256 "$BUNDLE_TGZ" | awk '{print $1}')"
echo "tar.gz sha256: $BUNDLE_SHA256"

echo "--- 4b. Push (oras) ---"
# oras embeds the pushed file's path as the layer's org.opencontainers.image.title
# annotation, which `oras pull` later uses as the output filename. Push with a
# relative filename (cd into $SCRATCH first) so pulls stay inside the output dir
# instead of tripping oras's path-traversal guard on an absolute title.
if [ "$USE_DOCKER" -eq 1 ]; then
  PUSH_OUT="$(cd "$SCRATCH" && oras push --plain-http "${REF_BASE}:${TAG}" \
    --artifact-type "$ARTIFACT_TYPE" \
    "${ANNOTATIONS[@]}" \
    "${ROOT_NAME}.tar.gz:${ARTIFACT_TYPE}" 2>&1)"
  echo "$PUSH_OUT"
  ORIGINAL_DIGEST="$(echo "$PUSH_OUT" | grep '^Digest:' | awk '{print $2}')"
  ORIGINAL_REF="${REF_BASE}@${ORIGINAL_DIGEST}"
  TAG_REF="${REF_BASE}:${TAG}"
else
  LAYOUT_DIR="$SCRATCH/layout"
  mkdir -p "$LAYOUT_DIR"
  PUSH_OUT="$(cd "$SCRATCH" && oras push --oci-layout "layout:${TAG}" \
    --artifact-type "$ARTIFACT_TYPE" \
    "${ANNOTATIONS[@]}" \
    "${ROOT_NAME}.tar.gz:${ARTIFACT_TYPE}" 2>&1)"
  echo "$PUSH_OUT"
  ORIGINAL_DIGEST="$(echo "$PUSH_OUT" | grep '^Digest:' | awk '{print $2}')"
  ORIGINAL_REF="${LAYOUT_DIR}@${ORIGINAL_DIGEST}"
  TAG_REF="${LAYOUT_DIR}:${TAG}"
fi
echo "manifest digest: $ORIGINAL_DIGEST"

echo "--- 4c. Sign (cosign) ---"
if [ "$USE_DOCKER" -eq 1 ]; then
  ( cd "$KEYS" && COSIGN_PASSWORD="" cosign sign --key cosign.key --allow-http-registry --yes "$ORIGINAL_REF" 2>&1 )
  SIGN_MODE="cosign sign (OCI artifact, Referrers-API attached signature)"
else
  ( cd "$KEYS" && COSIGN_PASSWORD="" cosign sign-blob --key cosign.key --yes \
      --output-signature "$SCRATCH/${ROOT_NAME}.tar.gz.sig" \
      --output-certificate "$SCRATCH/${ROOT_NAME}.tar.gz.cert" \
      "$BUNDLE_TGZ" 2>&1 ) || \
  ( cd "$KEYS" && COSIGN_PASSWORD="" cosign sign-blob --key cosign.key --yes \
      --output-signature "$SCRATCH/${ROOT_NAME}.tar.gz.sig" \
      "$BUNDLE_TGZ" 2>&1 )
  SIGN_MODE="cosign sign-blob (detached signature file, NOT attached to the OCI artifact)"
fi
echo "sign mode: $SIGN_MODE"

PRODUCER_T1="$(now_s)"
PRODUCER_SECS="$(python3 -c "print(f'{$PRODUCER_T1 - $PRODUCER_T0:.2f}')")"
echo
echo "Producer flow wall-clock (package+push+sign): ${PRODUCER_SECS}s"

echo
echo "############################################"
echo "# Verify: untouched bundle must PASS"
echo "############################################"
set +e
if [ "$USE_DOCKER" -eq 1 ]; then
  VERIFY_UNTOUCHED_OUT="$(cd "$KEYS" && cosign verify --key cosign.pub --allow-http-registry "$ORIGINAL_REF" 2>&1)"
  VERIFY_UNTOUCHED_RC=$?
else
  VERIFY_UNTOUCHED_OUT="$(cd "$KEYS" && cosign verify-blob --key cosign.pub --signature "$SCRATCH/${ROOT_NAME}.tar.gz.sig" "$BUNDLE_TGZ" 2>&1)"
  VERIFY_UNTOUCHED_RC=$?
fi
set -e
echo "$VERIFY_UNTOUCHED_OUT"
if [ "$VERIFY_UNTOUCHED_RC" -eq 0 ]; then
  echo "RESULT: PASS (as expected)"
else
  echo "RESULT: FAIL (unexpected!)"
fi

echo
echo "############################################"
echo "# Consumer flow: pull + verify + unpack (original)"
echo "############################################"
CONSUMER_T0="$(now_s)"
CONSUMER_PULL_DIR="$SCRATCH/consumer-original"
mkdir -p "$CONSUMER_PULL_DIR"

echo "--- 5a. Pull ---"
if [ "$USE_DOCKER" -eq 1 ]; then
  oras pull --plain-http "$ORIGINAL_REF" -o "$CONSUMER_PULL_DIR"
else
  oras pull --oci-layout "$ORIGINAL_REF" -o "$CONSUMER_PULL_DIR"
fi
PULLED_TGZ="$(find "$CONSUMER_PULL_DIR" -name '*.tar.gz' | head -1)"
echo "pulled: $PULLED_TGZ"

echo "--- 5b. Verify (by original digest) ---"
if [ "$USE_DOCKER" -eq 1 ]; then
  ( cd "$KEYS" && cosign verify --key cosign.pub --allow-http-registry "$ORIGINAL_REF" >/dev/null 2>&1 ) \
    && echo "verify: PASS" || echo "verify: FAIL"
else
  ( cd "$KEYS" && cosign verify-blob --key cosign.pub --signature "$SCRATCH/${ROOT_NAME}.tar.gz.sig" "$PULLED_TGZ" >/dev/null 2>&1 ) \
    && echo "verify: PASS" || echo "verify: FAIL"
fi

echo "--- 5c. Unpack ---"
UNPACK_DIR="$CONSUMER_PULL_DIR/unpacked"
mkdir -p "$UNPACK_DIR"
tar -xzf "$PULLED_TGZ" -C "$UNPACK_DIR"
UNPACKED_BUNDLE="$UNPACK_DIR/$ROOT_NAME"
echo "unpacked to: $UNPACKED_BUNDLE"

CONSUMER_T1="$(now_s)"
CONSUMER_SECS="$(python3 -c "print(f'{$CONSUMER_T1 - $CONSUMER_T0:.2f}')")"
echo
echo "Consumer flow wall-clock (pull+verify+unpack): ${CONSUMER_SECS}s"

echo
echo "--- 6. Validate the pulled original bundle (Level 3) ---"
set +e
python3 "$VALIDATOR" "$UNPACKED_BUNDLE" --level 3
VALIDATE_RC=$?
set -e
if [ "$VALIDATE_RC" -eq 0 ]; then
  echo "VALIDATE RESULT: PASS — the OCI round-trip preserved a valid AIX v0.3 bundle."
else
  echo "VALIDATE RESULT: FAIL (unexpected!)"
fi

echo
echo "############################################"
echo "# Tamper test"
echo "############################################"
echo "--- 7a. Pull to a temp dir, edit frontmatter, repackage ---"
TAMPER_DIR="$SCRATCH/tamper"
mkdir -p "$TAMPER_DIR/pulled"
if [ "$USE_DOCKER" -eq 1 ]; then
  oras pull --plain-http "$ORIGINAL_REF" -o "$TAMPER_DIR/pulled"
else
  oras pull --oci-layout "$ORIGINAL_REF" -o "$TAMPER_DIR/pulled"
fi
TAMPER_TGZ_IN="$(find "$TAMPER_DIR/pulled" -name '*.tar.gz' | head -1)"
mkdir -p "$TAMPER_DIR/unpacked"
tar -xzf "$TAMPER_TGZ_IN" -C "$TAMPER_DIR/unpacked"

TARGET_FILE="$TAMPER_DIR/unpacked/$ROOT_NAME/concepts/payment-service.md"
echo "before: $(grep '^status:' "$TARGET_FILE")"
sed -i '' 's/^status: deprecated$/status: stable/' "$TARGET_FILE"
echo "after:  $(grep '^status:' "$TARGET_FILE")"

TAMPERED_NAME="${ROOT_NAME}-tampered.tar.gz"
TAMPERED_TGZ="$SCRATCH/${TAMPERED_NAME}"
python3 "$MAKE_BUNDLE" "$TAMPER_DIR/unpacked/$ROOT_NAME" "$TAMPERED_TGZ" --root-name "$ROOT_NAME"
TAMPERED_SHA256="$(shasum -a 256 "$TAMPERED_TGZ" | awk '{print $1}')"
echo "tampered tar.gz sha256: $TAMPERED_SHA256 (original was $BUNDLE_SHA256)"

echo
echo "--- 7b. Push tampered bundle to the SAME tag (overwrite) ---"
if [ "$USE_DOCKER" -eq 1 ]; then
  TAMPER_PUSH_OUT="$(cd "$SCRATCH" && oras push --plain-http "${REF_BASE}:${TAG}" \
    --artifact-type "$ARTIFACT_TYPE" \
    --annotation "org.opencontainers.image.title=$AIX_NAME" \
    --annotation "org.opencontainers.image.revision=${GIT_COMMIT_FULL}-tampered" \
    --annotation "io.aix.bundle.name=$AIX_NAME" \
    --annotation "io.aix.bundle.namespace=$AIX_NAMESPACE" \
    --annotation "io.aix.bundle.aix-version=$AIX_VERSION" \
    "${TAMPERED_NAME}:${ARTIFACT_TYPE}" 2>&1)"
  echo "$TAMPER_PUSH_OUT"
  TAMPERED_DIGEST="$(echo "$TAMPER_PUSH_OUT" | grep '^Digest:' | awk '{print $2}')"
else
  TAMPER_PUSH_OUT="$(cd "$SCRATCH" && oras push --oci-layout "layout:${TAG}" \
    --artifact-type "$ARTIFACT_TYPE" \
    --annotation "org.opencontainers.image.title=$AIX_NAME" \
    --annotation "org.opencontainers.image.revision=${GIT_COMMIT_FULL}-tampered" \
    --annotation "io.aix.bundle.name=$AIX_NAME" \
    --annotation "io.aix.bundle.namespace=$AIX_NAMESPACE" \
    --annotation "io.aix.bundle.aix-version=$AIX_VERSION" \
    "${TAMPERED_NAME}:${ARTIFACT_TYPE}" 2>&1)"
  echo "$TAMPER_PUSH_OUT"
  TAMPERED_DIGEST="$(echo "$TAMPER_PUSH_OUT" | grep '^Digest:' | awk '{print $2}')"
fi
echo "tampered manifest digest: $TAMPERED_DIGEST (original was $ORIGINAL_DIGEST)"

echo
echo "--- 7c. Re-verify against the tag (must FAIL) ---"
if [ "$USE_DOCKER" -eq 1 ]; then
  set +e
  TAG_VERIFY_OUT="$(cd "$KEYS" && cosign verify --key cosign.pub --allow-http-registry "$TAG_REF" 2>&1)"
  TAG_VERIFY_RC=$?
  set -e
else
  set +e
  TAG_VERIFY_OUT="$(cd "$KEYS" && cosign verify-blob --key cosign.pub --signature "$SCRATCH/${ROOT_NAME}.tar.gz.sig" "$TAMPERED_TGZ" 2>&1)"
  TAG_VERIFY_RC=$?
  set -e
fi
echo "$TAG_VERIFY_OUT"
if [ "$TAG_VERIFY_RC" -ne 0 ]; then
  echo "RESULT: FAIL (as expected — no signature covers the new/tampered content)"
else
  echo "RESULT: PASS (unexpected — should have failed!)"
fi

echo
echo "--- 7d. Re-verify against the ORIGINAL digest (must still PASS) ---"
if [ "$USE_DOCKER" -eq 1 ]; then
  set +e
  DIGEST_VERIFY_OUT="$(cd "$KEYS" && cosign verify --key cosign.pub --allow-http-registry "$ORIGINAL_REF" 2>&1)"
  DIGEST_VERIFY_RC=$?
  set -e
else
  set +e
  DIGEST_VERIFY_OUT="$(cd "$KEYS" && cosign verify-blob --key cosign.pub --signature "$SCRATCH/${ROOT_NAME}.tar.gz.sig" "$BUNDLE_TGZ" 2>&1)"
  DIGEST_VERIFY_RC=$?
  set -e
fi
echo "$DIGEST_VERIFY_OUT"
if [ "$DIGEST_VERIFY_RC" -eq 0 ]; then
  echo "RESULT: PASS (as expected — content-addressed, the old content and its signature are untouched)"
else
  echo "RESULT: FAIL (unexpected!)"
fi

echo
echo "############################################"
echo "# Summary"
echo "############################################"
cat <<SUMMARY
backend:                  $([ "$USE_DOCKER" -eq 1 ] && echo "local Docker registry (plain-HTTP, port $REGISTRY_PORT)" || echo "oras --oci-layout (no registry)")
sign mode:                $SIGN_MODE
bundle:                   $AIX_NAME ($AIX_NAMESPACE), aix $AIX_VERSION, commit $GIT_COMMIT
original digest:          $ORIGINAL_DIGEST
tampered digest:          $TAMPERED_DIGEST
key generation:           ${KEYGEN_SECS}s (one-time, excluded from producer flow)
producer flow wall-clock: ${PRODUCER_SECS}s (package+push+sign)
consumer flow wall-clock: ${CONSUMER_SECS}s (pull+verify+unpack)
verify untouched:         $([ "$VERIFY_UNTOUCHED_RC" -eq 0 ] && echo PASS || echo FAIL)
verify tampered (tag):    $([ "$TAG_VERIFY_RC" -ne 0 ] && echo "FAIL (expected)" || echo "PASS (unexpected)")
verify original (digest): $([ "$DIGEST_VERIFY_RC" -eq 0 ] && echo "PASS (expected)" || echo "FAIL (unexpected)")
validate pulled bundle:   $([ "$VALIDATE_RC" -eq 0 ] && echo PASS || echo FAIL)
SUMMARY

echo
echo "Full run complete. See experiments/e6-oci/e6-results.md for the write-up."
