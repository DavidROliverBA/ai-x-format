#!/usr/bin/env bash
# E2 — Identity resolution under collision (MyVault plan 2026-09-26 §1, §2 "E2").
#
# Runs ai-x-validate.py --federation against the bundle-c fixture under both
# supported YAML parsers, then runs the full unittest suite (which itself
# exercises both parsers and the examples/-unchanged regression check).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
VALIDATOR="$REPO_ROOT/tools/ai-x-validate.py"

echo "== bundle-c --federation, stdlib fallback parser (no PyYAML) =="
cd "$HERE"
python3 "$VALIDATOR" bundle-c --federation federation.ai-x.yaml --stats || true

echo
echo "== bundle-c --federation, real PyYAML (uv run --with pyyaml) =="
uv run -q --with pyyaml python3 "$VALIDATOR" bundle-c --federation federation.ai-x.yaml --stats || true

echo
echo "== examples/ WITHOUT --federation, both parsers (regression check) =="
cd "$REPO_ROOT"
python3 "$VALIDATOR" examples --level 2 --json > /tmp/ai-x-e2-examples-stdlib.json
uv run -q --with pyyaml python3 "$VALIDATOR" examples --level 2 --json > /tmp/ai-x-e2-examples-pyyaml.json
diff /tmp/ai-x-e2-examples-stdlib.json /tmp/ai-x-e2-examples-pyyaml.json \
  && echo "OK: stdlib and PyYAML agree on examples/"
diff <(python3 -c "import json,sys; d=json.load(open('/tmp/ai-x-e2-examples-stdlib.json')); d.pop('bundle'); print(json.dumps(d, indent=2))") \
     <(python3 -c "import json,sys; d=json.load(open('$HERE/baseline-examples-level2.json')); d.pop('bundle'); print(json.dumps(d, indent=2))") \
  && echo "OK: examples/ output unchanged from the pre-change baseline"

echo
echo "== unittest suite (both parsers, exercised internally) =="
cd "$HERE"
python3 test_resolution.py -v
