#!/usr/bin/env bash
# experiments/e1-transport/setup.sh
#
# Builds $E1_WORK (default /tmp/aix-e1), wiping it first, so every run starts
# from the same state. Creates three LOCAL bare git repositories that act as
# "remotes" for the federation transport experiment (E1 — see README.md):
#
#   remotes/data-eng.git   <- experiments/fixtures/data-eng   (bundle at root)
#   remotes/household.git  <- experiments/fixtures/household  (bundle at root)
#   remotes/payments.git   <- examples/                       (bundle at root)
#
# Each remote is built from a single commit with a fixed author/committer
# identity and date, so the resulting commit SHA is reproducible across runs
# on the same git version (content unchanged). The three HEAD SHAs are
# recorded to $E1_WORK/remotes.json for later provenance comparisons (M3).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
E1_WORK="${E1_WORK:-/tmp/aix-e1}"

FIXED_DATE="2026-09-26T09:00:00+00:00"
FIXED_NAME="AIX E1 Fixture"
FIXED_EMAIL="e1-fixture@example.invalid"

echo "== E1 setup: building scratch environment at $E1_WORK =="
rm -rf "$E1_WORK"
mkdir -p "$E1_WORK/remotes" "$E1_WORK/vocab" "$E1_WORK/.work"

cp "$REPO_ROOT/experiments/fixtures/vocab/types-v1.json" "$E1_WORK/vocab/types-v1.json"
cp "$REPO_ROOT/experiments/fixtures/vocab/rels-v1.json" "$E1_WORK/vocab/rels-v1.json"

make_remote() {
  local name="$1" src="$2"
  local work="$E1_WORK/.work/$name"
  echo "-- building remote '$name' from $src"
  rm -rf "$work"
  mkdir -p "$work"
  # Copy bundle content only (no .git, no OS cruft) so the bundle sits at the
  # remote repo's root, per the plan.
  (cd "$src" && tar cf - --exclude='.git' --exclude='.DS_Store' .) | (cd "$work" && tar xf -)

  (
    cd "$work"
    git init -q -b main
    git add -A
    GIT_AUTHOR_NAME="$FIXED_NAME" GIT_AUTHOR_EMAIL="$FIXED_EMAIL" \
    GIT_AUTHOR_DATE="$FIXED_DATE" \
    GIT_COMMITTER_NAME="$FIXED_NAME" GIT_COMMITTER_EMAIL="$FIXED_EMAIL" \
    GIT_COMMITTER_DATE="$FIXED_DATE" \
    git commit -q -m "Initial import of $name bundle (E1 fixture, reproducible)"
  )

  rm -rf "$E1_WORK/remotes/$name.git"
  git clone -q --bare "$work" "$E1_WORK/remotes/$name.git" >/dev/null
  # Bare clones of a local path record the source path as 'origin' — harmless
  # here (nothing ever fetches from it again), but drop it so the bare repo
  # reads as a clean, self-contained remote.
  git -C "$E1_WORK/remotes/$name.git" remote remove origin 2>/dev/null || true
  rm -rf "$work"
}

make_remote "data-eng"  "$REPO_ROOT/experiments/fixtures/data-eng"
make_remote "household" "$REPO_ROOT/experiments/fixtures/household"
make_remote "payments"  "$REPO_ROOT/examples"

rmdir "$E1_WORK/.work" 2>/dev/null || true

python3 - "$E1_WORK" <<'PY'
import json, subprocess, sys
from pathlib import Path

work = Path(sys.argv[1])
remotes = {}
for name in ("data-eng", "household", "payments"):
    p = work / "remotes" / f"{name}.git"
    sha = subprocess.check_output(["git", "-C", str(p), "rev-parse", "HEAD"], text=True).strip()
    remotes[name] = {"path": str(p), "head": sha}

out = work / "remotes.json"
out.write_text(json.dumps(remotes, indent=2) + "\n")
print(f"Wrote {out}:")
print(json.dumps(remotes, indent=2))
PY

echo "== E1 setup complete =="
