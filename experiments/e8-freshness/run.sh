#!/usr/bin/env bash
# experiments/e8-freshness/run.sh
#
# E8 — Freshness and drift (added after v0.4.2)
#
# Replays add / edit / rename / delete against MyVault's ai-xf-export.py on
# copies of the vault's Psychology/Concepts notes, under four producer modes
# (inplace, fresh, tombstone, stable), and measures the federation vocabulary
# declared vs used. Writes results.json next to this script. Needs `uv` (the
# exporter requires PyYAML) and read access to ~/Documents/MyVault and
# ~/Documents/GitHub/ai-concepts-kb; writes only to a scratch directory.
set -euo pipefail
cd "$(dirname "$0")"
python3 run.py "$(mktemp -d -t e8)"
