# Leaside Tracker

A private dashboard for what is happening in Leaside, Toronto, and the neighbouring
areas: North Rosedale, South Rosedale, Moore Park, Davisville and Lawrence Park.

It pulls residents' association news, City of Toronto public notices, police open data
and local media into one SQLite file and renders a static page. No server, no accounts.

## Start here

**On Windows, read [docs/SETUP-WINDOWS.md](docs/SETUP-WINDOWS.md) and follow it.**
It assumes no technical knowledge. Short version: install Python, then
double-click `run-windows.bat`.

On a Mac, double-click `run-mac.command`.

Under the hood, all either script does is:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python -m leaside.cli probe     # find out which sources are real
.venv/bin/python -m leaside.cli ingest    # pull the ones that work
.venv/bin/python -m leaside.cli build     # write site/index.html

.venv/bin/python -m leaside.cli discover  # scan directory pages for new feeds
.venv/bin/python -m leaside.cli doctor    # write config/health-report.md
.venv/bin/python -m leaside.cli digest --dry-run   # preview the weekly email
```

`probe` is not optional. Every endpoint in `config/sources.yaml` is a documented
promise or a conventional guess. None has been confirmed from a live request. The probe
writes `config/probe-report.md`, which is the only file in this repo that records
verified facts.

To see the site render without any network:

```bash
.venv/bin/python -m leaside.cli demo && .venv/bin/python -m leaside.cli build
```

## Layout

| Path | Purpose |
| --- | --- |
| `config/sources.yaml` | Every source, its kind, and an honest status |
| `config/areas.geojson` | Placeholder rectangles for each neighbourhood |
| `leaside/fetchers/` | One module per source kind: RSS, JSON, ArcGIS, CKAN, HTML |
| `docs/SOURCE-INVENTORY.md` | What data exists, what it costs, what is blocked |
| `docs/ROADMAP.md` | Phased plan and five more things worth tracking |
| `docs/MAILING-LISTS.md` | Which newsletters to join, and why a separate address |
| `docs/EMAIL-DIGEST.md` | Setting up the weekly email, once |
| `.github/workflows/weekly-digest.yml` | Runs weekly on GitHub and emails the digest |
| `config/health-report.md` | Written every run: what came in, duplicates, failures |
| `tests/` | Parser tests against fixtures, no network |
| `run-windows.bat` | Double-click launcher for Windows |
| `find-associations.bat` | One-off scan for residents' association feeds |
| `run-mac.command` | Double-click launcher for macOS |

## Rules this project follows

- Identify itself in every request, and pause between requests to the same host.
- Store links and short summaries, never republished article bodies.
- Never present police crime points as exact addresses. Toronto Police offset them to
  the nearest intersection on purpose.
- Record failure. A source that stops working shows up in the source health table
  rather than disappearing quietly.
