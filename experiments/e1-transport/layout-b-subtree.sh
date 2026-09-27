#!/usr/bin/env bash
# experiments/e1-transport/layout-b-subtree.sh
#
# Builds $E1_WORK/consumer-b: the three bundles merged in with
# `git subtree add --prefix bundles/<ns> <remote> main --squash`, with NO
# federation manifest checked in. Then attempts naive discovery: scan for
# manifest.ai-xf.yaml files under the merged tree, read each one's own
# `namespace:` field (which subtree-add preserves verbatim, since it copies
# the whole bundle including its manifest), and write what a consumer with no
# federation-aware tooling beyond "grep for manifests" could reconstruct to
# $E1_WORK/consumer-b/discovered.yaml.
#
# Per-bundle commit provenance is deliberately NOT recovered here (`ref:
# null` for every entry) — recovering it requires reading git-subtree's
# trailer metadata (git log --grep), which is exactly the extra step layout C
# takes and layout B does not. That is the point of the B/C comparison (M3).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E1_WORK="${E1_WORK:-/tmp/ai-xf-e1}"
CONSUMER="$E1_WORK/consumer-b"

# shellcheck source=./lib-subtree.sh
source "$SCRIPT_DIR/lib-subtree.sh"

if [ ! -f "$E1_WORK/remotes.json" ]; then
  echo "error: $E1_WORK/remotes.json missing — run setup.sh first" >&2
  exit 1
fi

e1_build_subtree_consumer "$CONSUMER" "Layout B"

echo "-- discovering bundle roots by scanning for manifest.ai-xf.yaml (no manifest checked in)"
python3 - "$CONSUMER" <<'PY'
import re
import sys
from pathlib import Path

consumer = Path(sys.argv[1])
bundles = []
for manifest in sorted(consumer.rglob("manifest.ai-xf.yaml")):
    ns = None
    for line in manifest.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^namespace:\s*(\S+)\s*$", line)
        if m:
            ns = m.group(1)
            break
    if ns is None:
        continue
    rel_dir = manifest.parent.relative_to(consumer)
    bundles.append({"namespace": ns, "path": f"./{rel_dir}"})

lines = [
    "# Reconstructed by naive filesystem discovery",
    "# (experiments/e1-transport/layout-b-subtree.sh) — no manifest was checked",
    "# in for this layout, and no git history was consulted. `ref` is null",
    "# because per-bundle commit provenance does not survive a squash merge",
    "# without deliberately recording it (that is what layout C adds).",
    "federation: e1-consumer-b-discovered",
    "bundles:",
]
for b in bundles:
    lines.append(f"  - namespace: {b['namespace']}")
    lines.append("    source: path")
    lines.append(f"    path: {b['path']}")
    lines.append("    ref: null")

(consumer / "discovered.yaml").write_text("\n".join(lines) + "\n")
PY

echo "-- discovered.yaml:"
cat "$CONSUMER/discovered.yaml"
