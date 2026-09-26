#!/usr/bin/env bash
# experiments/e1-transport/layout-a-submodules.sh
#
# Builds $E1_WORK/consumer-a: a git repo whose bundles/{data-eng,household,
# payments} are git submodules of the three local remotes built by setup.sh.
# NO federation.ai-x.yaml is checked in by a human — instead this script
# GENERATES one from .gitmodules + `git submodule status`, to test whether
# .gitmodules alone carries enough information to reconstruct a federation
# manifest (the plan's central question for E1).
#
# JUDGEMENT CALL (documented, see README.md "Notes on deviations"):
# the plan sketch says `subdir: .` for each git-sourced bundle entry. Reading
# tools/ai-x-validate.py's load_federation(), a `source: git` entry resolves
# as `(repo_root_of_the_directory_holding_the_federation_manifest) / subdir`
# — it does NOT clone `repo:`, and it does NOT treat `subdir` as relative to
# the submodule's own repo. Since federation.ai-x.yaml lives at consumer-a's
# OWN root (a real, distinct git repo), `subdir: .` would resolve to
# consumer-a's root itself (which has no manifest.ai-x.yaml) and every bundle
# would fail to load. This script instead emits `subdir: bundles/<name>`,
# which is what the implemented resolver actually requires to find the
# submodule directories. `ref` still carries the exact submodule SHA for
# provenance (M3), and `repo` still carries the real submodule URL (reported,
# not fetched — git fetching is explicitly out of scope for this flag).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E1_WORK="${E1_WORK:-/tmp/ai-x-e1}"
CONSUMER="$E1_WORK/consumer-a"

FIXED_DATE="2026-09-26T09:05:00+00:00"
FIXED_NAME="AI-X E1 Fixture"
FIXED_EMAIL="e1-fixture@example.invalid"

if [ ! -f "$E1_WORK/remotes.json" ]; then
  echo "error: $E1_WORK/remotes.json missing — run setup.sh first" >&2
  exit 1
fi

echo "== Layout A: git submodules, no manifest checked in =="
rm -rf "$CONSUMER"
mkdir -p "$CONSUMER"

(
  cd "$CONSUMER"
  git init -q -b main
  export GIT_AUTHOR_NAME="$FIXED_NAME" GIT_AUTHOR_EMAIL="$FIXED_EMAIL" \
         GIT_AUTHOR_DATE="$FIXED_DATE" GIT_COMMITTER_NAME="$FIXED_NAME" \
         GIT_COMMITTER_EMAIL="$FIXED_EMAIL" GIT_COMMITTER_DATE="$FIXED_DATE"
  git commit -q --allow-empty -m "consumer-a root (E1 fixture)"

  for name in data-eng household payments; do
    git -c protocol.file.allow=always submodule add -q \
      "$E1_WORK/remotes/$name.git" "bundles/$name"
  done

  git commit -q -m "Add data-eng, household, payments as git submodules"
)

echo "-- generating federation.ai-x.yaml from .gitmodules + git submodule status"
python3 - "$CONSUMER" <<'PY'
import re
import subprocess
import sys
from pathlib import Path

consumer = Path(sys.argv[1])

# 1. .gitmodules -> {path: url}
cfg = subprocess.check_output(
    ["git", "config", "-f", str(consumer / ".gitmodules"), "--list"], text=True
)
urls = {}
for line in cfg.splitlines():
    m = re.match(r"submodule\.(.+)\.url=(.*)", line)
    if m:
        urls[m.group(1)] = m.group(2)

# 2. `git submodule status` -> {path: sha}   (strip leading +/- state marker)
status = subprocess.check_output(
    ["git", "-C", str(consumer), "submodule", "status"], text=True
)
shas = {}
for line in status.splitlines():
    line = line.strip()
    if not line:
        continue
    marker = line[0] if line[0] in "+-U" else " "
    body = line[1:] if marker != " " else line
    parts = body.split()
    sha, path = parts[0], parts[1]
    shas[path] = sha

bundles = []
for name in ("data-eng", "household", "payments"):
    path = f"bundles/{name}"
    manifest = consumer / path / "manifest.ai-x.yaml"
    ns = None
    for line in manifest.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^namespace:\s*(\S+)\s*$", line)
        if m:
            ns = m.group(1)
            break
    if ns is None:
        raise SystemExit(f"could not find namespace: in {manifest}")
    bundles.append({
        "namespace": ns,
        "repo": urls[path],
        "ref": shas[path],
        # subdir relative to consumer-a's own repo root — see the header
        # comment in this script for why this differs from the plan's
        # `subdir: .` sketch.
        "subdir": path,
    })

lines = [
    'ai-x: "0.4"',
    "federation: e1-consumer-a",
    "vocabularies:",
    "  types: ../vocab/types-v1.json",
    "  rels: ../vocab/rels-v1.json",
    "bundles:",
]
for b in bundles:
    lines.append(f"  - namespace: {b['namespace']}")
    lines.append("    source: git")
    lines.append(f"    repo: {b['repo']}")
    lines.append(f"    ref: {b['ref']}")
    lines.append(f"    subdir: {b['subdir']}")

(consumer / "federation.ai-x.yaml").write_text("\n".join(lines) + "\n")
PY

echo "-- generated $CONSUMER/federation.ai-x.yaml:"
cat "$CONSUMER/federation.ai-x.yaml"
