#!/usr/bin/env bash
# Usage: check-dco.sh BASE HEAD
# Fails if any non-merge commit in BASE..HEAD lacks a Signed-off-by trailer
# whose email matches the commit author's email. Fails closed if either
# revision cannot be resolved.
set -euo pipefail
base="$1"; head="$2"
for rev in "$base" "$head"; do
  if ! git cat-file -e "${rev}^{commit}" 2>/dev/null; then
    echo "::error::Revision $rev is not available; cannot check sign-offs."
    exit 1
  fi
done
commits=$(git rev-list --no-merges "$base..$head")
bad=0
for sha in $commits; do
  name=$(git log -1 --format=%an "$sha")
  email=$(git log -1 --format=%ae "$sha")
  signed=$(git log -1 --format=%B "$sha" | git interpret-trailers --parse \
    | grep -i '^Signed-off-by:' | grep -ciF "<$email>" || true)
  if [ "${signed:-0}" -eq 0 ]; then
    echo "::error::Commit $sha ($name <$email>) has no Signed-off-by line matching its author email."
    bad=1
  fi
done
if [ "$bad" -ne 0 ]; then
  echo
  echo "Fix: 'git commit --amend -s' (last commit) or 'git rebase --signoff origin/main' (several), then force-push."
  echo "See CONTRIBUTING.md and DCO."
  exit 1
fi
echo "All commits in $base..$head are signed off."
