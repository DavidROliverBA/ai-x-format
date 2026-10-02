#!/usr/bin/env bash
# experiments/e9-knowledgex/run.sh
#
# E9 — Interoperability with KnowledgeX, a third-party OKF producer
# (github.com/rahulnyk/KnowledgeX, npm `knowledgex`, pinned below).
#
#   A. KnowledgeX -> AI-XF: build a notebook with the `kx` CLI (no LLM), then
#      validate it with tools/ai-xf-validate.py at levels 0-3, with --stats.
#   B. AI-XF -> KnowledgeX: run `kx check`, `kx search --all` and `kx review`
#      on examples/ as it is, flattened, and flattened at the pre-v0.4.3
#      commit (date-only timestamps), and compare trust tiers.
#
# Needs bun (bunx fetches the package) and git. Writes only to a temp dir;
# `--bundle` is used throughout so `kx init` never writes a config file.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
VALIDATE="python3 $REPO/tools/ai-xf-validate.py"
KX_VERSION="0.4.0"
BEFORE_REF="f4031dc"          # last commit before v0.4.3's datetime timestamps
W="$(mktemp -d -t e9)"
kx() { bunx "knowledgex@$KX_VERSION" "$@"; }
tiers() { kx search --all --bundle "$1" | grep -o '· [a-z-]*-\(reviewed\|confirmed\) \|· unverified ' | sort | uniq -c; }

echo "# E9 run, $(date -u +%Y-%m-%dT%H:%M:%SZ), knowledgex@$KX_VERSION, workdir $W"

echo; echo "## A. KnowledgeX notebook validated as AI-XF"
NB="$W/nb"; mkdir -p "$NB"
kx new Decision "Use PostgreSQL as the job queue" --description "Jobs go through a Postgres table with SKIP LOCKED, not a broker." --by human:tester --source design=https://example.com/adr-12 --bundle "$NB" >/dev/null
kx new Decision "Use Redis as the job queue" --description "Jobs go through Redis lists." --by human:tester --bundle "$NB" >/dev/null
kx new Concept "SKIP LOCKED" --description "Postgres row locking that lets workers skip claimed rows." --by claude-code/test --tags postgres --bundle "$NB" >/dev/null
kx new Lesson "Brokers add an operational dependency" --description "Every broker is one more thing to page someone about." --by human:tester --bundle "$NB" >/dev/null
kx relate use-postgresql-as-the-job-queue.md supersedes use-redis-as-the-job-queue.md --by human:tester --bundle "$NB" >/dev/null
kx verify skip-locked.md --by human:tester --bundle "$NB" >/dev/null
kx relate brokers-add-an-operational-dependency.md contradicts use-postgresql-as-the-job-queue.md --by claude-code/test --bundle "$NB" >/dev/null
echo "kx check: $(kx check --bundle "$NB" | tail -1 | sed "s#$W/##")"
for lv in 0 1 2 3; do
  echo "AI-XF level $lv: $($VALIDATE "$NB" --level $lv | tail -1)"
done
$VALIDATE "$NB" --level 0 --stats | grep -E "contradictions:|retired \(no successor\)|change edges:" | sed 's/^ */AI-XF stats: /'
echo "KnowledgeX relationship keys written:"; grep -h -A1 -E "^(supersedes|contradicts):" "$NB"/*.md | sed 's/^/  /'

echo; echo "## B. AI-XF examples/ read by KnowledgeX"
cp -R "$REPO/examples" "$W/nested"
echo "nested, as published: $(kx check --bundle "$W/nested" | tail -1 | sed "s#$W/##"); search finds $(kx search --all --bundle "$W/nested" | grep -c '·' || true) notes"
mkdir -p "$W/flat-now" "$W/flat-before" "$W/before"
cp "$REPO"/examples/*/*.md "$REPO/examples/log.md" "$W/flat-now/"
git -C "$REPO" archive "$BEFORE_REF" examples | tar -x -C "$W/before"
cp "$W"/before/examples/*/*.md "$W/flat-before/"
echo "flattened, $BEFORE_REF (date-only timestamps), KnowledgeX trust tiers:"; tiers "$W/flat-before" | sed 's/^/  /'
echo "flattened, v0.4.3 (datetimes, events in order), KnowledgeX trust tiers:"; tiers "$W/flat-now" | sed 's/^/  /'
echo "AI-XF's own reading of the same concepts: $($VALIDATE "$REPO/examples" --stats | grep 'trust tiers' | sed 's/^ *trust tiers: *//')"
echo "kx review (v0.4.3):"; kx review --bundle "$W/flat-now" | grep -E "^## |^- " | sed 's/^/  /'
