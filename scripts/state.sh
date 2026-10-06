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
# of fixes. All three workflows use this script and share one concurrency group,
# so they never write the branch at once.
#
# The database is the complete log: nothing in it is ever deleted. Two rules here
# protect that.
#   1. It is stored compressed. 32 MB raw is 4.5 MB compressed, and GitHub refuses
#      any single file over 100 MB.
#   2. A save that would leave FEWER records than the restore found is refused.
#      Since nothing is deleted, fewer means something went wrong - most likely a
#      restore that failed and a run that started from an empty database - and
#      pushing it would overwrite the whole log.
set -euo pipefail

COUNT_FILE="${RUNNER_TEMP:-/tmp}/leaside-restored-count"

count_items() {
  python3 - "$1" <<'PY'
import sqlite3, sys
try:
    print(sqlite3.connect(sys.argv[1]).execute("SELECT COUNT(*) FROM items").fetchone()[0])
except sqlite3.Error:
    print(0)
PY
}

case "${1:-}" in
  restore)
    mkdir -p data
    set +e
    git ls-remote --exit-code --heads origin state >/dev/null 2>&1
    rc=$?
    set -e
    if [ "$rc" = "2" ]; then
      echo "No state branch yet. This is the first run."
      echo 0 > "$COUNT_FILE"
      exit 0
    elif [ "$rc" != "0" ]; then
      echo "::error title=Could not reach the saved log::git ls-remote failed (exit $rc). Stopping rather than starting from an empty database."
      exit 1
    fi
    git fetch --depth 1 origin state
    if git cat-file -e origin/state:leaside.db.gz 2>/dev/null; then
      git show origin/state:leaside.db.gz | gunzip > data/leaside.db
    elif git cat-file -e origin/state:leaside.db 2>/dev/null; then
      git show origin/state:leaside.db > data/leaside.db      # before compression
    else
      echo "The state branch has no database yet. Starting fresh."
      echo 0 > "$COUNT_FILE"
      exit 0
    fi
    n=$(count_items data/leaside.db)
    echo "$n" > "$COUNT_FILE"
    echo "Restored $(stat -c%s data/leaside.db) bytes, $n records."
    ;;
  save)
    : "${GITHUB_TOKEN:?GITHUB_TOKEN is needed to push the state branch}"
    : "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is needed to push the state branch}"
    # The save step runs even when an earlier step failed, so a failed restore
    # must not be followed by a save: it would push an empty database over the log.
    if [ ! -f "$COUNT_FILE" ] || [ ! -f data/leaside.db ]; then
      echo "::error title=Nothing saved::The restore did not finish in this run, so there is nothing safe to save. The saved log was left untouched."
      exit 1
    fi
    before=$(cat "$COUNT_FILE")
    after=$(count_items data/leaside.db)
    if [ "$after" -lt "$before" ]; then
      echo "::error title=Refused to overwrite the log::The run started with $before records and would save $after. Nothing is ever deleted, so this is a fault. The saved log was left untouched."
      exit 1
    fi
    tmp="$(mktemp -d)"
    gzip -6 -c data/leaside.db > "$tmp/leaside.db.gz"
    size_mb=$(( $(stat -c%s "$tmp/leaside.db.gz") / 1000000 ))
    if [ "$size_mb" -ge 95 ]; then
      echo "::error title=Log too large for GitHub::The compressed log is ${size_mb} MB; GitHub refuses files over 100 MB. Ask Claude to split it by year."
      exit 1
    elif [ "$size_mb" -ge 60 ]; then
      echo "::warning title=Log getting large::The compressed log is ${size_mb} MB of GitHub's 100 MB limit."
    fi
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
    git commit -q -m "State after $(date -u +%Y-%m-%dT%H:%MZ): $after records"
    git push -q --force origin state
    echo "Saved $after records ($before at the start), $(stat -c%s leaside.db.gz) bytes compressed."
    ;;
  *)
    echo "usage: scripts/state.sh restore|save" >&2
    exit 2
    ;;
esac
