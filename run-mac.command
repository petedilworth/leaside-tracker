#!/bin/bash
# Leaside Tracker - double-click this file on a Mac.
# It sets itself up the first time, then updates the page every time after.

cd "$(dirname "$0")" || exit 1

echo ""
echo "=============================================="
echo "  Leaside Tracker"
echo "=============================================="
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python is not installed on this Mac."
  echo "Go to https://www.python.org/downloads/ install it, then run this again."
  echo ""
  read -r -p "Press Return to close this window."
  exit 1
fi

# Collect any fixes before running, so results always reflect the latest code.
if command -v git >/dev/null 2>&1; then
  echo "Step 0 of 4: collecting updates..."
  if ! git pull --ff-only; then
    echo ""
    echo "COULD NOT UPDATE. Results below will be out of date."
    echo "To fix: git checkout -- . && git pull"
    git status --short
    echo ""
  fi
  echo ""
fi

if [ ! -d ".venv" ]; then
  echo "First run. Setting up (this takes a minute)..."
  python3 -m venv .venv || { echo "Setup failed."; read -r -p "Press Return."; exit 1; }
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt || { echo "Install failed."; read -r -p "Press Return."; exit 1; }
  echo "Setup done."
  echo ""
else
  .venv/bin/pip install --quiet -r requirements.txt
fi

echo "Step 1 of 4: checking which news sources are working (once a week)..."
.venv/bin/python -m leaside.cli probe

echo ""
echo "Step 2 of 4: collecting the news..."
.venv/bin/python -m leaside.cli ingest

echo ""
echo "Step 3 of 4: building your page..."
.venv/bin/python -m leaside.cli build

echo ""
echo "Step 4 of 4: checking the health of your data..."
.venv/bin/python -m leaside.cli doctor

echo ""
echo "Done. Opening your page now."
echo "To report how the run went, send config/health-report.md"
open site/index.html
echo ""
read -r -p "Press Return to close this window."
