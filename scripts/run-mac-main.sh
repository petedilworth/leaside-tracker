#!/bin/bash
# Everything after the update step. Safe to change.
cd "$(dirname "$0")/.." || exit 1

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
