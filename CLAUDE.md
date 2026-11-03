# Leaside Tracker

A private neighbourhood tracker for Leaside and its neighbours in Toronto: news,
City notices, permits, inspections and police data, collected daily on GitHub
and published as a static site. The owner is not a programmer: explain every
step they must take in plain words, one action at a time.

## Tracker
This repo reports to my Build Pipeline dashboard through ROADMAP.md.
- At the end of any session that changes the repo, update ROADMAP.md:
  tick finished items and move them to Done with the date;
  add new work you find under Later.
- One line per item, under 90 characters, plain words.
- Never reword or reorder existing items. The dashboard matches items
  by their exact text, and I set priority there.
- Delete items I've dropped; say so in the reply.

## Git
- When the work is done, commit and push to main. Never leave a branch
  or pull request for me to merge – I don't review code.
- If you worked on a side branch, merge it into main and push main
  before you finish.
- Before pushing, run this repo's tests or checks. If they fail, fix
  them. If you can't, don't push to main, and tell me why.
- If main publishes a website, check the change at phone width first.

## How to check things here
- Tests: `.venv/bin/python -m pytest -q` (parser tests and browser tests; the
  browser tests use the Chromium at `/opt/pw-browsers`).
- Phone width: build with `python -m leaside.cli demo` and open `site/demo.html`
  at 390 px, or run the browser tests, which hold every page to that width.
- Nothing collected is ever deleted. A fix that changes what is shown hides rows
  with a reason; see `docs/THE-LOG.md`.
- The crawler never disguises itself. A 403 from a publisher is a no.
