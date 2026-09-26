#!/usr/bin/env bash
# E3: cross-bundle index — reproduce the whole experiment.
#
#   1. Check qmd is installed (install it via bun if not).
#   2. Build all three configurations (qmd x2 + bm25.py) and run the
#      20-question set against each (run.py does this).
#   3. Print the resulting summary table.
#
# Re-run any time with: ./run.sh
# Model weights (~2.1GB, one-time) are cached under qmd_home/_shared_models/
# and reused across runs and across configs (a)/(b) — see run.py's
# ensure_models() for why that's a fair thing to do here.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "== qmd install check =="
if ! command -v qmd >/dev/null 2>&1; then
  echo "qmd not found on PATH — installing with 'bun install -g @tobilu/qmd' (per the qmd README)..."
  bun install -g @tobilu/qmd
fi
echo "qmd: $(qmd --version)"
echo "python3: $(python3 --version)"
echo

echo "== building indexes and running the 20-question set =="
python3 run.py

echo
echo "== e3-results.md =="
cat e3-results.md
