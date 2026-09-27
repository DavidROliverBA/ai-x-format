#!/usr/bin/env bash
# experiments/e5-transports/run.sh
#
# E5 — trust survival through transports (MyVault plan
# docs/plans/2026-09-26-federation-experiments-plan.md, E5). Round-trips the
# `examples/` bundle (example-payments — 7 concepts) through:
#
#   (a) git        — init, commit, clone
#   (b) rsync      — `rsync -a` to a temp dir
#   (c) iCloud     — copy into ~/Library/.../CloudDocs/ai-xf-e5-roundtrip/,
#                    poll for sync, copy back out, remove the folder
#   (d) kcmd       — SKIPPED (no gcloud on this machine); records the
#                    connector doc's own stated losses instead
#   (e) YAML       — load+safe_dump every concept's frontmatter with PyYAML,
#                    simulating what any parse-and-rewrite tool (kcmd
#                    included) does even when it "carries every key"
#
# For (a)/(b)/(c)/(e), compare.py diffs the transported bundle against the
# untouched source, byte-for-byte and frontmatter key-by-key, classifying
# each key preserved / normalised / lost. Only reads examples/; never
# modifies it or tools/ai-xf-validate.py. All scratch work happens under
# $E5_WORK (default /tmp/ai-xf-e5).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
E5_WORK="${E5_WORK:-/tmp/ai-xf-e5}"
COMPARE="$SCRIPT_DIR/compare.py"
ROUNDTRIP="$SCRIPT_DIR/yaml_roundtrip.py"

echo "############################################"
echo "# E5 — trust survival through transports"
echo "############################################"
echo
echo "Tool versions: $(git --version), $(python3 --version), $(uv --version), $(rsync --version | head -1)"
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo
echo "--- 0. scratch setup: $E5_WORK ---"
rm -rf "$E5_WORK"
mkdir -p "$E5_WORK/results"
SOURCE="$E5_WORK/source"
cp -R "$REPO_ROOT/examples" "$SOURCE"
echo "source bundle snapshotted from $REPO_ROOT/examples ($(find "$SOURCE" -type f | wc -l | tr -d ' ') files)"

run_compare() {
  # run_compare <dest-dir> <transport-label> <json-out-name>
  local dest="$1" label="$2" out="$3"
  uv run -q --with pyyaml python3 "$COMPARE" diff "$SOURCE" "$dest" \
    --transport "$label" --json-out "$E5_WORK/results/$out"
}

echo
echo "############################################"
echo "# (a) git: init, commit, clone"
echo "############################################"
GIT_ORIGIN="$E5_WORK/git/origin"
GIT_CLONE="$E5_WORK/git/clone"
mkdir -p "$GIT_ORIGIN"
cp -R "$SOURCE"/. "$GIT_ORIGIN"/
(
  cd "$GIT_ORIGIN"
  git init -q -b main
  git -c user.name="AI-XF E5 Fixture" -c user.email="e5-fixture@example.invalid" add -A
  git -c user.name="AI-XF E5 Fixture" -c user.email="e5-fixture@example.invalid" \
      -c commit.gpgsign=false commit -q -m "E5 fixture: example-payments bundle"
)
git clone -q "$GIT_ORIGIN" "$GIT_CLONE"
echo "cloned $(git -C "$GIT_CLONE" rev-parse HEAD)"
run_compare "$GIT_CLONE" "git (init/commit/clone)" "git.json"

echo
echo "############################################"
echo "# (b) rsync: rsync -a to a temp dir"
echo "############################################"
RSYNC_DEST="$E5_WORK/rsync/dest"
mkdir -p "$RSYNC_DEST"
rsync -a "$SOURCE"/ "$RSYNC_DEST"/
run_compare "$RSYNC_DEST" "rsync -a" "rsync.json"

echo
echo "############################################"
echo "# (c) iCloud Drive: copy in, poll for sync, copy out"
echo "############################################"
ICLOUD_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/ai-xf-e5-roundtrip"
rm -rf "$ICLOUD_DIR"
mkdir -p "$ICLOUD_DIR"
cp -R "$SOURCE"/. "$ICLOUD_DIR"/
echo "copied bundle into $ICLOUD_DIR"

# A single "client:idle" read is racy: the CloudDocs daemon can report idle
# for an instant right after the cp, before it has even noticed the new
# files (observed directly on the first E5 run — `client:idle` on poll #1,
# then `client:needs-sync` with a "Client Truth Unclean Items" block moments
# later). Require the idle/no-placeholder/no-unclean-items state to hold for
# 3 consecutive polls, 5s apart (a 10s stability window), before calling it
# confirmed — still only a local daemon-queue signal, not proof of
# server-side upload completion.
SYNC_CONFIRMED=0
STABLE_COUNT=0
DEADLINE=$(( $(date +%s) + 120 ))
CHECKS=0
sleep 3  # let the daemon notice the change before the first read
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  CHECKS=$((CHECKS + 1))
  PLACEHOLDERS=$(find "$ICLOUD_DIR" -name "*.icloud" 2>/dev/null | wc -l | tr -d ' ')
  RAW_STATUS=$(brctl status com.apple.CloudDocs 2>/dev/null || true)
  STATUS_LINE=$(echo "$RAW_STATUS" | grep -o 'client:[a-z-]*' | head -1 || true)
  HAS_UNCLEAN=$(echo "$RAW_STATUS" | grep -c "Truth Unclean Items" || true)
  echo "  poll #$CHECKS: placeholders=$PLACEHOLDERS brctl=$STATUS_LINE unclean_blocks=$HAS_UNCLEAN"
  if [ "$PLACEHOLDERS" = "0" ] && [ "$STATUS_LINE" = "client:idle" ] && [ "$HAS_UNCLEAN" = "0" ]; then
    STABLE_COUNT=$((STABLE_COUNT + 1))
    if [ "$STABLE_COUNT" -ge 3 ]; then
      SYNC_CONFIRMED=1
      break
    fi
  else
    STABLE_COUNT=0
  fi
  sleep 5
done
echo
echo "brctl status com.apple.CloudDocs (final):"
brctl status com.apple.CloudDocs 2>&1 | sed 's/^/  /'
echo
if [ "$SYNC_CONFIRMED" -eq 1 ]; then
  echo "Heuristic sync signal reached (no .icloud placeholders, brctl client:idle) after $CHECKS poll(s)."
  echo "NOTE: this is a local daemon-queue signal, not proof of server-side upload completion — see e5-results.md for the judgement call."
  ICLOUD_LABEL="iCloud Drive (heuristic-confirmed, see caveat)"
else
  echo "No confirmed sync signal within 120s."
  ICLOUD_LABEL="iCloud Drive (local-only, sync unconfirmed)"
fi

ICLOUD_BACKOUT="$E5_WORK/icloud/dest"
mkdir -p "$ICLOUD_BACKOUT"
cp -R "$ICLOUD_DIR"/. "$ICLOUD_BACKOUT"/
run_compare "$ICLOUD_BACKOUT" "$ICLOUD_LABEL" "icloud.json"
echo "SYNC_CONFIRMED=$SYNC_CONFIRMED" > "$E5_WORK/results/icloud-sync-status.txt"

echo "cleaning up $ICLOUD_DIR"
rm -rf "$ICLOUD_DIR"

echo
echo "############################################"
echo "# (d) Knowledge Catalog via kcmd: SKIPPED"
echo "############################################"
echo "Reason: no gcloud CLI on this machine (required by kcmd for auth/EntryGroup setup)."
CONNECTOR_URL="https://raw.githubusercontent.com/GoogleCloudPlatform/open-knowledge-format/main/connectors/gcp-knowledge-catalog.md"
CONNECTOR_DOC="$E5_WORK/results/gcp-kc-connector.md"
if curl -sf --max-time 15 "$CONNECTOR_URL" -o "$CONNECTOR_DOC"; then
  echo "Fetched connector doc ($(wc -l < "$CONNECTOR_DOC" | tr -d ' ') lines) from $CONNECTOR_URL"
  echo
  echo "Limitations section (verbatim, as fetched):"
  sed -n '/^## Limitations/,/^## /p' "$CONNECTOR_DOC" | sed '$d' | sed 's/^/  /'
else
  echo "curl fetch FAILED — could not confirm wording live; see e5-results.md for the last-known quote."
fi

echo
echo "############################################"
echo "# (e) YAML normalisation round trip (PyYAML load + safe_dump)"
echo "############################################"
YAML_DEST="$E5_WORK/yaml-roundtrip/dest"
mkdir -p "$YAML_DEST"
uv run -q --with pyyaml python3 "$ROUNDTRIP" "$SOURCE" "$YAML_DEST"
run_compare "$YAML_DEST" "YAML round trip (safe_load + safe_dump)" "yaml-roundtrip.json"

echo
echo "############################################"
echo "# Summary"
echo "############################################"
uv run -q --with pyyaml python3 "$COMPARE" summary \
  "$E5_WORK/results/git.json" \
  "$E5_WORK/results/rsync.json" \
  "$E5_WORK/results/icloud.json" \
  "$E5_WORK/results/yaml-roundtrip.json" \
  | tee "$E5_WORK/results/summary.md"

echo
echo "(d) kcmd: SKIPPED — no gcloud on this machine. See e5-results.md for the connector doc's stated losses."
echo
echo "Full results (per-transport markdown + JSON) under: $E5_WORK/results/"
