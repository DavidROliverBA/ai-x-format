#!/usr/bin/env bash
# experiments/e12-longview/run.sh
#
# E12 — From an LLM knowledge base to the Longview database ("across")
#
# Federate-imports two AI-XF bundles that Longview did not write (examples/ and a copy of the
# author's psychology-kb) into a THROWAWAY Postgres, changes the bundle and re-imports, seeds one
# event/item/claim by SQL (standing in for the LLM pipeline, which is never run), exports with
# Longview's own exporter, and validates the export with Longview's vendored validator and with
# this repository's current one. Writes results.json next to this script.
#
# Safety: Longview is used from a scratch copy without .env (Bun would otherwise load it), under
# `env -i` and `bun --no-env-file`; no mail, model or production endpoint is configured. The
# database is a new container on port 55412, removed at the end. The developer database
# (longview-db-1, port 5433) and the Longview repository are never touched.
#
# Needs: docker, bun, python3, rsync, ~/Documents/GitHub/longview (with node_modules installed)
# and ~/Documents/GitHub/psychology-kb.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
LONGVIEW="${LONGVIEW:-$HOME/Documents/GitHub/longview}"
PSYCH="${PSYCH:-$HOME/Documents/GitHub/psychology-kb}"
PORT=55412; NAME=aixf-e12-pg
DB="postgres://longview:longview@localhost:$PORT/longview"
W="$(mktemp -d -t e12)"; OUT="$W/out"; mkdir -p "$OUT" "$W/bundles"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "# E12, $(date -u +%Y-%m-%dT%H:%M:%SZ), longview $(git -C "$LONGVIEW" rev-parse --short HEAD), workdir $W"

# 1. Throwaway database and a scratch Longview with no .env
cleanup
docker run -d --rm --name "$NAME" -e POSTGRES_USER=longview -e POSTGRES_PASSWORD=longview \
  -e POSTGRES_DB=longview -p "$PORT:5432" pgvector/pgvector:pg17 >/dev/null
until docker exec "$NAME" pg_isready -U longview -q; do sleep 1; done; sleep 2
rsync -a --exclude .git --exclude node_modules --exclude '.env' --exclude '.env.*' \
  --exclude briefings --exclude business-plan "$LONGVIEW/" "$W/lv/"
ln -s "$LONGVIEW/node_modules" "$W/lv/node_modules"
lv() { (cd "$W/lv" && env -i HOME="$HOME" PATH="$PATH" DATABASE_URL="$DB" bun --no-env-file run "$@"); }
psql() { docker exec -i "$NAME" psql -U longview -v ON_ERROR_STOP=1 -tA "$@"; }
lv src/db-migrate.ts >/dev/null 2>&1
# The scratch copy's federation file gains an entry for the psychology namespace (--local import).
cat >> "$W/lv/topics/ai/federation.ai-xf.yaml" <<'EOF'
  - namespace: psychology
    source: git
    repo: https://github.com/DavidROliverBA/psychology-kb
    ref: "0000000000000000000000000000000000000000"
    weight: 1
    category: practitioner
EOF
cp -R "$REPO/examples" "$W/bundles/examples"
rsync -a --exclude .git "$PSYCH/" "$W/bundles/psychology/"

# 2. Federate import: dry run, then real
for b in examples psychology; do
  lv scripts/import-ai-xf.ts "$W/bundles/$b" --mode federate --dry-run > "$OUT/$b-dry.txt" 2>&1
  lv scripts/import-ai-xf.ts "$W/bundles/$b" --mode federate --json > "$OUT/$b-1.json" 2>"$OUT/$b-1.err"
done

# 3. Change the bundle: edit one concept, retire one as a tombstone, add one; re-import
python3 - "$W/bundles/psychology/concepts" <<'EOF'
import re, sys
from pathlib import Path
p = Path(sys.argv[1])
a = p / "action-bias.md"; a.write_text(a.read_text().replace("## Quick Reference", "## Quick Reference\n\nEdited for E12.", 1))
t = p / "affect-heuristic.md"; s = t.read_text(); end = s.index("\n---", 4)
t.write_text(re.sub(r"^status: \S+", "status: deprecated", s[:end], flags=re.M) + "\n---\n\nRetired for E12.\n")
(p / "e12-new-concept.md").write_text("---\ntype: Concept\nid: e12-new-concept\ntitle: E12 New Concept\n"
    "description: Added for the E12 re-import test.\nstatus: stable\ngenerated:\n  by: human:e12\n"
    "  at: '2026-10-03T08:00:00Z'\n---\n\nAdded for E12.\n")
EOF
lv scripts/import-ai-xf.ts "$W/bundles/psychology" --mode federate --json > "$OUT/psychology-2.json" 2>/dev/null
# ... then delete the added concept outright (no tombstone) and re-import
rm "$W/bundles/psychology/concepts/e12-new-concept.md"
lv scripts/import-ai-xf.ts "$W/bundles/psychology" --mode federate --json > "$OUT/psychology-3.json" 2>/dev/null
psql -c "select json_build_object(
  'raw_rows_action_bias', (select count(*) from raw_items where url = 'ai-xf://psychology/action-bias'),
  'retired_raw_status', (select payload->'aixf'->'trust'->>'status' from raw_items where url = 'ai-xf://psychology/affect-heuristic' order by id desc limit 1),
  'retired_stored_status', (select frontmatter->>'status' from aixf_concepts where namespace = 'psychology' and id = 'affect-heuristic'),
  'deleted_still_stored', (select count(*) from aixf_concepts where namespace = 'psychology' and id = 'e12-new-concept'),
  'deleted_still_raw', (select count(*) from raw_items where url = 'ai-xf://psychology/e12-new-concept'),
  'stale_after_kept_verbatim', (select frontmatter->>'stale_after' from aixf_concepts where namespace = 'psychology' and id = 'action-bias'),
  'conceptType_kept', (select frontmatter->>'conceptType' from aixf_concepts where namespace = 'psychology' and id = 'action-bias'))" > "$OUT/lifecycle.json"

# 4. Stand in for the LLM pipeline: one event, item and claim by SQL, citing a federated item
psql > /dev/null <<'SQL'
with r as (select id, url, payload from raw_items where url = 'ai-xf://psychology/action-bias' order by id limit 1),
e as (insert into events (title, event_type, first_seen, significance, summary)
      values ('E12 seeded event about action bias', 'opinion', '2026-10-01T09:30:00Z', 3,
              'A seeded summary written for E12, standing in for pipeline extraction.') returning id),
i as (insert into items (raw_id, title, canonical_url, published_at, text, event_id)
      select r.id, r.payload->>'title', r.url, '2026-09-30T14:00:00Z', r.payload->>'text', e.id from r, e returning id, event_id)
insert into claims (event_id, entity_id, text, polarity, confidence, cited_item_id, created_at)
select i.event_id, (select id from entities where slug = 'jane-doe'),
       'Jane Doe favours acting over waiting (seeded for E12).', 'asserts', 0.6, i.id, '2026-10-01T10:00:00Z' from i;
SQL

# 5. Export with Longview, validate with both validators
lv scripts/export-ai-xf.ts --out "$W/export" > "$OUT/export.txt" 2>&1
lv scripts/validate-ai-xf.ts "$W/export" > "$OUT/validate-longview.txt" 2>&1 && echo "longview validate: pass" || echo "longview validate: FAIL"
python3 "$REPO/tools/ai-xf-validate.py" "$W/export" --level 3 --json > "$OUT/validate-v043.json" || true
python3 "$LONGVIEW/scripts/vendor/ai-xf-validate.py" "$W/export" --level 3 --json > "$OUT/validate-vendored.json" || true
cp "$W/export/stories"/*/*/event-*.md "$OUT/event.md"

# 6. Summarise
python3 - "$OUT" "$HERE/results.json" <<'EOF'
import json, sys, re, pathlib
out, dest = pathlib.Path(sys.argv[1]), sys.argv[2]
j = lambda n: json.loads((out / n).read_text())
def summary(r):
    return {"concepts": r["concepts"], "projected": r["projected"], "entities": {k: r["entities"][k] for k in r["entities"] if k != "skipped"},
            "links": {k: r["links"][k] for k in r["links"] if k in ("total", "byRel", "byReason", "unprojectedByRel", "unprojectedByReason")} or r["links"],
            "trust": r.get("trust"), "keysNotModelled": r.get("keys", {}).get("notModelled", r.get("keys"))}
v043, vend = j("validate-v043.json"), j("validate-vendored.json")
kinds = {}
for f in v043["findings"]:
    k = re.sub(r"`[^`]*`", "X", f["message"]); kinds[k] = kinds.get(k, 0) + 1
res = {
    "import_examples": summary(j("examples-1.json")),
    "import_psychology": summary(j("psychology-1.json")),
    "reimport_after_edit_retire_add": summary(j("psychology-2.json")),
    "reimport_after_delete": summary(j("psychology-3.json")),
    "lifecycle": j("lifecycle.json"),
    "export": [l for l in (out / "export.txt").read_text().splitlines() if l.startswith(("read:", "concepts:"))],
    "export_event_cites": re.findall(r"resource: (\S+)", (out / "event.md").read_text()),
    "validate_vendored_4ff386f": {"passed": vend["passed"], "findings": len(vend["findings"])},
    "validate_v0_4_3": {"passed": v043["passed"], "findings": len(v043["findings"]), "kinds": kinds},
}
pathlib.Path(dest).write_text(json.dumps(res, indent=2) + "\n")
print(json.dumps({k: res[k] for k in ("lifecycle", "export", "validate_vendored_4ff386f", "validate_v0_4_3")}, indent=2))
EOF
