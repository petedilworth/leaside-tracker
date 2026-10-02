#!/usr/bin/env bash
# Carry the SQLite database between GitHub runs on a separate `state` branch.
#
#   scripts/state.sh restore   copy the last saved database into data/
#   scripts/state.sh save      push data/ and the generated page to the state branch
#
# GitHub gives every run a clean machine, so without this each run would look
# like the first. The database lives on its own branch, never beside the code,
# because a database committed to the working branch makes `git pull` conflict
# on any PC that also runs the project - the fault that once hid five sessions
# of fixes. Both workflows (daily publish, weekly email) use this same script
# and share one concurrency group, so they never write the branch at once.
set -euo pipefail

case "${1:-}" in
  restore)
    mkdir -p data
    if git ls-remote --exit-code --heads origin state >/dev/null 2>&1; then
      git fetch --depth 1 origin state
      if git cat-file -e origin/state:leaside.db 2>/dev/null; then
        git show origin/state:leaside.db > data/leaside.db
        echo "Restored $(stat -c%s data/leaside.db) bytes from the state branch."
      else
        echo "The state branch has no database yet. Starting fresh."
      fi
    else
      echo "No state branch yet. This is the first run."
    fi
    ;;
  save)
    : "${GITHUB_TOKEN:?GITHUB_TOKEN is needed to push the state branch}"
    : "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is needed to push the state branch}"
    tmp="$(mktemp -d)"
    cp data/leaside.db "$tmp/leaside.db"
    cp config/health-report.md "$tmp/health-report.md" 2>/dev/null || true
    cp site/index.html "$tmp/index.html" 2>/dev/null || true
    cd "$tmp"
    git init -q -b state
    # Identity belongs to THIS repository. Setting it in the checkout did nothing
    # here, and two scheduled runs died with "empty ident name".
    git config user.name "leaside-tracker"
    git config user.email "noreply@github.com"
    git remote add origin "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
    git add -A
    git commit -q -m "State after $(date -u +%Y-%m-%dT%H:%MZ)"
    git push -q --force origin state
    echo "Saved to the state branch."
    ;;
  *)
    echo "usage: scripts/state.sh restore|save" >&2
    exit 2
    ;;
esac
