#!/usr/bin/env bash
# E4: serving via MCP tools. Runs the smoke test, deterministic mode
# (always), then llm mode (self-skips without ANTHROPIC_API_KEY, exit 0).
#
# Usage: ./run.sh [--federation <path>] [--questions <path>]
# Note: no `set -u` — this repo's default /bin/bash is 3.2 (macOS), where
# `"${arr[@]}"` on a genuinely empty array is treated as an unbound
# variable under `set -u` (same issue e1-transport hit and documented).
set -eo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

FEDERATION=""
QUESTIONS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --federation) FEDERATION="$2"; shift 2 ;;
    --questions) QUESTIONS="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

FED_ARGS=()
[[ -n "$FEDERATION" ]] && FED_ARGS+=(--federation "$FEDERATION")
Q_ARGS=()
[[ -n "$QUESTIONS" ]] && Q_ARGS+=(--questions "$QUESTIONS")

echo "== E4: smoke test =="
uv run --with mcp --with pyyaml smoke_test.py "${FED_ARGS[@]}"

echo
echo "== E4: deterministic mode =="
uv run --with mcp --with pyyaml client_harness.py --mode deterministic "${FED_ARGS[@]}" "${Q_ARGS[@]}"

echo
echo "== E4: llm mode (skips cleanly if ANTHROPIC_API_KEY is unset) =="
uv run --with mcp --with pyyaml --with anthropic client_harness.py --mode llm "${FED_ARGS[@]}" "${Q_ARGS[@]}"

echo
echo "== E4: done. See e4-results.md, results-deterministic.json, results-llm.json (if it ran). =="
