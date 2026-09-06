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

if [ ! -d ".venv" ]; then
  echo "First run. Setting up (this takes a minute)..."
  python3 -m venv .venv || { echo "Setup failed."; read -r -p "Press Return."; exit 1; }
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt || { echo "Install failed."; read -r -p "Press Return."; exit 1; }
  echo "Setup done."
  echo ""
fi

echo "Step 1 of 3: checking which news sources are working..."
.venv/bin/python -m leaside.cli probe

echo ""
echo "Step 2 of 3: collecting the news..."
.venv/bin/python -m leaside.cli ingest

echo ""
echo "Step 3 of 3: building your page..."
.venv/bin/python -m leaside.cli build

echo ""
echo "Done. Opening your page now."
open site/index.html
echo ""
read -r -p "Press Return to close this window."
