#!/usr/bin/env bash
# experiments/e10-database/run.sh
#
# E10 — An AI-XF bundle as a department database (exploratory).
#
# Starts its OWN throwaway Postgres 17 on port 55410 (never the Longview
# database on 5433), loads examples/, psychology-kb and ai-concepts-kb, and
# measures round trip, concurrent writers, CQRS read models and a blue/green
# read-model swap. Writes results.json next to this script, then removes the
# container. Needs docker, bun (Bun.sql, Bun.YAML) and python3.
set -euo pipefail
cd "$(dirname "$0")"
NAME=aixf-e10-pg
PORT=55410
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=e10 -p "$PORT:5432" postgres:17-alpine >/dev/null
trap 'docker stop "$NAME" >/dev/null 2>&1 || true' EXIT
WORK="$(mktemp -d -t e10)"
bun e10.ts "$WORK" "postgres://postgres:e10@localhost:$PORT/postgres"
