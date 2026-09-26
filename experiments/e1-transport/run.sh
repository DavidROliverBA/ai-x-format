#!/usr/bin/env bash
# experiments/e1-transport/run.sh
#
# Runs setup.sh + the three layout scripts, validates each consumer's
# data-eng bundle (the bundle with the most cross-bundle links) with
# `--federation`, and computes the four E1 measures from the plan
# (docs/plans/2026-09-26-federation-experiments-plan.md, E1):
#
#   M1 qualified references resolved / total
#   M2 rename survival (id unchanged, filename changed)
#   M3 provenance: can the consumer name the exact commit of each bundle?
#   M4 rebuild: clean clone byte-identical to the working checkout?
#
# Writes $E1_WORK/e1-results.md and prints it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export E1_WORK="${E1_WORK:-/tmp/aix-e1}"
VALIDATOR="$REPO_ROOT/tools/aix-validate.py"

echo "############################################"
echo "# E1 — transport and the root manifest"
echo "############################################"

echo
echo "--- 0. Does aix-validate.py support --federation yet? ---"
FED_AVAILABLE=1
if ! python3 "$VALIDATOR" --help 2>&1 | grep -q -- "--federation"; then
  FED_AVAILABLE=0
  echo "NOT AVAILABLE — will build all three layouts and note this in the results table."
else
  echo "available."
fi

echo
echo "--- 1. setup.sh (remotes) ---"
"$SCRIPT_DIR/setup.sh"

echo
echo "--- 2. layout-a-submodules.sh ---"
"$SCRIPT_DIR/layout-a-submodules.sh"

echo
echo "--- 3. layout-b-subtree.sh ---"
"$SCRIPT_DIR/layout-b-subtree.sh"

echo
echo "--- 4. layout-c-subtree-manifest.sh ---"
"$SCRIPT_DIR/layout-c-subtree-manifest.sh"

mkdir -p "$E1_WORK/results"

# Consumer -> (bundle-under-test dir, federation manifest path) triples.
# Bash 3.2 on macOS has no associative arrays, so this is three parallel
# lists, joined by index.
CONSUMERS=(consumer-a consumer-b consumer-c)
FED_FILES=(federation.aix.yaml discovered.yaml federation.aix.yaml)

run_validator() {
  # run_validator <bundle-dir> <federation-file> <out-json>
  local bundle="$1" fed="$2" out="$3"
  if [ "$FED_AVAILABLE" -eq 1 ]; then
    python3 "$VALIDATOR" "$bundle" --level 3 --federation "$fed" --json --stats \
      > "$out" 2>&1 || true
  else
    python3 "$VALIDATOR" "$bundle" --level 3 --json --stats > "$out" 2>&1 || true
  fi
}

echo
echo "--- 5. M1: validate data-eng (most cross-bundle links) in each consumer ---"
for i in 0 1 2; do
  name="${CONSUMERS[$i]}"
  fed="$E1_WORK/$name/${FED_FILES[$i]}"
  bundle="$E1_WORK/$name/bundles/data-eng"
  out="$E1_WORK/results/$name-data-eng.json"
  echo "-- $name: $bundle (federation: $fed)"
  run_validator "$bundle" "$fed" "$out"
done

echo
echo "--- 6. M2: rename survival (bundles/data-eng/concepts/orders-events.md, id unchanged) ---"
# The qualified reference under test lives in the PAYMENTS bundle
# (examples/concepts/payment-service-v2.md: `to: data-eng/orders-events`),
# so M2 validates bundles/payments, not bundles/data-eng.
for i in 0 1 2; do
  name="${CONSUMERS[$i]}"
  fed="$E1_WORK/$name/${FED_FILES[$i]}"
  payments_bundle="$E1_WORK/$name/bundles/payments"
  orig="$E1_WORK/$name/bundles/data-eng/concepts/orders-events.md"
  renamed="$E1_WORK/$name/bundles/data-eng/concepts/orders-event-stream.md"

  run_validator "$payments_bundle" "$fed" "$E1_WORK/results/$name-payments-before-rename.json"

  mv "$orig" "$renamed"
  run_validator "$payments_bundle" "$fed" "$E1_WORK/results/$name-payments-after-rename.json"
  # restore immediately, regardless of what we found
  mv "$renamed" "$orig"

  run_validator "$payments_bundle" "$fed" "$E1_WORK/results/$name-payments-restored.json"
  echo "-- $name: renamed, re-validated, restored (see results/$name-payments-*.json)"
done

echo
echo "--- 7. M3: provenance from git submodule status / discovered.yaml / federation ref ---"
git -C "$E1_WORK/consumer-a" submodule status > "$E1_WORK/results/consumer-a-submodule-status.txt"
cat "$E1_WORK/results/consumer-a-submodule-status.txt"

echo
echo "--- 8. M4: fresh clone, diff -r bundles against the working checkout ---"
rm -rf "$E1_WORK/fresh"
mkdir -p "$E1_WORK/fresh"

git -c protocol.file.allow=always clone -q --recurse-submodules \
  "$E1_WORK/consumer-a" "$E1_WORK/fresh/consumer-a" \
  > "$E1_WORK/results/consumer-a-clone.log" 2>&1
diff -r "$E1_WORK/fresh/consumer-a/bundles" "$E1_WORK/consumer-a/bundles" \
  > "$E1_WORK/results/consumer-a-diff.txt" 2>&1 || true

git clone -q "$E1_WORK/consumer-b" "$E1_WORK/fresh/consumer-b" \
  > "$E1_WORK/results/consumer-b-clone.log" 2>&1
diff -r "$E1_WORK/fresh/consumer-b/bundles" "$E1_WORK/consumer-b/bundles" \
  > "$E1_WORK/results/consumer-b-diff.txt" 2>&1 || true

git clone -q "$E1_WORK/consumer-c" "$E1_WORK/fresh/consumer-c" \
  > "$E1_WORK/results/consumer-c-clone.log" 2>&1
diff -r "$E1_WORK/fresh/consumer-c/bundles" "$E1_WORK/consumer-c/bundles" \
  > "$E1_WORK/results/consumer-c-diff.txt" 2>&1 || true

for n in consumer-a consumer-b consumer-c; do
  if [ -s "$E1_WORK/results/$n-diff.txt" ]; then
    echo "-- $n: DIFFERS (see results/$n-diff.txt)"
  else
    echo "-- $n: byte-identical"
  fi
done

echo
echo "--- 9. Compute measures and write results table ---"
python3 "$SCRIPT_DIR/compute-results.py" "$E1_WORK" "$FED_AVAILABLE"

echo
echo "############################################"
echo "# E1 complete — see $E1_WORK/e1-results.md"
echo "############################################"
