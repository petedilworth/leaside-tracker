#!/bin/bash
# Leaside Tracker - double-click this file on a Mac.
# THIS FILE MUST NEVER CHANGE: bash reads a script while it runs, so an update
# that rewrote it mid-run would execute garbage. It only collects the update,
# then hands over to scripts/run-mac-main.sh, which the update may replace.
cd "$(dirname "$0")" || exit 1
echo ""
echo "=============================================="
echo "  Leaside Tracker"
echo "=============================================="
echo ""
if command -v git >/dev/null 2>&1; then
  echo "Step 0 of 4: collecting updates..."
  if ! git pull --ff-only; then
    echo "A file looks edited to git. Trying to clear it automatically..."
    if git checkout -- . && git pull --ff-only; then
      echo "Cleared. Updated successfully."
    else
      echo "Still stuck. Send this whole window to Claude."
      git status --short
    fi
  fi
  echo ""
fi
exec bash "scripts/run-mac-main.sh"
