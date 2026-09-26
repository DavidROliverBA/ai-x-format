# experiments/e1-transport/lib-subtree.sh
#
# Shared helper for layout-b-subtree.sh and layout-c-subtree-manifest.sh:
# both consumers are built the same way (three `git subtree add --squash`
# merges of the same three remotes); they differ only in what, if anything,
# they check in afterwards. Sourced, not executed.

e1_build_subtree_consumer() {
  local consumer="$1" label="$2"
  local fixed_date="2026-09-26T09:10:00+00:00"
  local fixed_name="AI-X E1 Fixture"
  local fixed_email="e1-fixture@example.invalid"

  echo "== $label: git subtree merges, three remotes into one repo =="
  rm -rf "$consumer"
  mkdir -p "$consumer"

  (
    cd "$consumer"
    git init -q -b main
    export GIT_AUTHOR_NAME="$fixed_name" GIT_AUTHOR_EMAIL="$fixed_email" \
           GIT_AUTHOR_DATE="$fixed_date" GIT_COMMITTER_NAME="$fixed_name" \
           GIT_COMMITTER_EMAIL="$fixed_email" GIT_COMMITTER_DATE="$fixed_date"
    git commit -q --allow-empty -m "$(basename "$consumer") root (E1 fixture)"

    for name in data-eng household payments; do
      git subtree add -q --prefix="bundles/$name" \
        "$E1_WORK/remotes/$name.git" main --squash \
        -m "Subtree merge $name (E1 fixture)"
    done
  )
}

# Extract the original source commit SHA for a subtree-merged bundle from the
# squash commit's `git-subtree-split:` trailer (SPEC-agnostic; git plumbing
# only). Returns empty string if not found.
e1_subtree_split_ref() {
  local consumer="$1" name="$2"
  git -C "$consumer" log --all --grep="git-subtree-dir: bundles/$name\$" -1 --pretty=%B \
    | awk -F': ' '/^git-subtree-split:/{print $2}'
}
