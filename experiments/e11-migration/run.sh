#!/usr/bin/env bash
# experiments/e11-migration/run.sh
#
# E11 — Migrating Word-on-SharePoint and Confluence into AI-XF
#
# Builds a synthetic corpus (5 Word documents with SharePoint sidecar metadata,
# 5 Confluence pages in storage format with REST-style sidecar metadata, all
# about a fictional company), converts it naive (MarkItDown) and mapped (this
# experiment's converter), and measures every probe in the ground truth against
# each bundle, then runs tools/ai-xf-validate.py at level 3 with --stats.
# Writes results.json next to this script; everything else goes to a temp dir.
# Needs uv (python-docx >= 1.2, markitdown[docx], pyyaml are fetched on demand).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
W="$(mktemp -d -t e11)"
PY=(uv run -q --with 'python-docx>=1.2' --with 'markitdown[docx]' --with pyyaml python3)
"${PY[@]}" "$HERE/make_corpus.py" "$W/corpus"
"${PY[@]}" "$HERE/convert.py" "$W/corpus" "$W/out"
python3 "$HERE/measure.py" "$W/corpus" "$W/out" "$REPO/tools/ai-xf-validate.py" "$HERE/results.json"
echo "workdir: $W"
