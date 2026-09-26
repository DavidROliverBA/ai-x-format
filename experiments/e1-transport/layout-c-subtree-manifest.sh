#!/usr/bin/env bash
# experiments/e1-transport/layout-c-subtree-manifest.sh
#
# Builds $E1_WORK/consumer-c: same subtree merges as layout B, but this time a
# hand-written federation.ai-x.yaml is ALSO checked in. Its `source: path`
# entries point at ./bundles/<ns>, and — unlike layout B's naive discovery —
# it records real per-bundle provenance: the original commit each bundle was
# squashed from, read from the `git-subtree-split:` trailer that
# `git subtree add --squash` leaves in the squash commit's message. That
# trailer is git plumbing, not an AI-X concept — a human (or a slightly less
# naive discovery script) has to go looking for it deliberately, which is
# exactly the B vs C distinction this experiment measures (M3).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E1_WORK="${E1_WORK:-/tmp/ai-x-e1}"
CONSUMER="$E1_WORK/consumer-c"

# shellcheck source=./lib-subtree.sh
source "$SCRIPT_DIR/lib-subtree.sh"

if [ ! -f "$E1_WORK/remotes.json" ]; then
  echo "error: $E1_WORK/remotes.json missing — run setup.sh first" >&2
  exit 1
fi

e1_build_subtree_consumer "$CONSUMER" "Layout C"

echo "-- writing hand-authored federation.ai-x.yaml with subtree-split provenance"

# No associative arrays here — /bin/bash on macOS is still 3.2 (no `declare
# -A`). A single pass over the fixed bundle list is enough.
{
  echo 'ai-x: "0.4"'
  echo "federation: e1-consumer-c"
  echo "vocabularies:"
  echo "  types: ../vocab/types-v1.json"
  echo "  rels: ../vocab/rels-v1.json"
  echo "bundles:"
  for name in data-eng household payments; do
    manifest="$CONSUMER/bundles/$name/manifest.ai-x.yaml"
    ns="$(grep -m1 '^namespace:' "$manifest" | sed 's/^namespace:[[:space:]]*//')"
    ref="$(e1_subtree_split_ref "$CONSUMER" "$name")"
    echo "  - namespace: $ns"
    echo "    source: path"
    echo "    path: ./bundles/$name"
    echo "    ref: $ref  # from git-subtree-split trailer, provenance only"
  done
} > "$CONSUMER/federation.ai-x.yaml"

FIXED_DATE="2026-09-26T09:15:00+00:00"
FIXED_NAME="AI-X E1 Fixture"
FIXED_EMAIL="e1-fixture@example.invalid"
(
  cd "$CONSUMER"
  git add federation.ai-x.yaml
  GIT_AUTHOR_NAME="$FIXED_NAME" GIT_AUTHOR_EMAIL="$FIXED_EMAIL" \
  GIT_AUTHOR_DATE="$FIXED_DATE" GIT_COMMITTER_NAME="$FIXED_NAME" \
  GIT_COMMITTER_EMAIL="$FIXED_EMAIL" GIT_COMMITTER_DATE="$FIXED_DATE" \
  git commit -q -m "Check in hand-written federation.ai-x.yaml with subtree provenance"
)

echo "-- checked-in $CONSUMER/federation.ai-x.yaml:"
cat "$CONSUMER/federation.ai-x.yaml"
