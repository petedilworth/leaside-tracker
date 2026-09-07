# What data actually exists

Compiled 6 September 2026, then **corrected against a real probe run** the same day.
Ten of twenty-two sources responded usefully on the first attempt. What follows now
reflects what actually happened, not what was hoped for.

Six sources work today: four residents' association feeds, Leaside Life, the Toronto
Open Data CKAN API and the Toronto Police ArcGIS catalogue. Two more failed on
timeouts and have been given longer limits. Two had the wrong domain and are fixed.
Two returned HTTP 403, meaning the publisher refuses crawlers, and are not being
worked around.

Sources are graded on how much work they cost you, not on how interesting they are.

## Tier 1 - real machine-readable feeds, low effort

| Source | Endpoint | Status |
| --- | --- | --- |
| City Clerk public notices | `https://secure.toronto.ca/nm/notices.json` | Read timeout at 30 seconds. Not dead - it returns every notice since 2018 in one large file. Now allowed 180 seconds and three attempts. Still the best single municipal source, and it carries Committee of Adjustment hearings. |
| Toronto Open Data (CKAN) | `https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/...` | **Confirmed, valid JSON.** Gateway to collisions, 311, building permits, neighbourhood boundaries. |
| Toronto Police open data | `https://data.tps.ca/api/feed/dcat-us/1.1.json` | **Confirmed, large valid JSON catalogue.** Layer URLs for Major Crime Indicators and Traffic Collisions are discovered from it at ingest time rather than hard-coded. |
| KSI collisions | Toronto Open Data dataset `motor-vehicle-collisions-involving-killed-or-seriously-injured-persons` | Reached through the confirmed CKAN API. Rows are pulled newest first, because the dataset starts in 2006. |
| Leaside Residents Association | `https://leasideresidents.ca/feed/` | **Confirmed, 10 entries.** |
| South Rosedale Residents' Association | `https://southrosedale.org/feed/` | **Confirmed, 10 entries.** |
| Lawrence Park Ratepayers' Association | `https://lpra.ca/feed/` | **Confirmed, 8 entries.** |
| Leaside Life | `https://leasidelife.com/feed/` | **Confirmed, 10 entries.** |
| Moore Park Residents Association | `https://moorepark.org/feed/` | Domain corrected. The earlier guess `mpra.ca` returned 404. |
| South Eglinton Davisville Residents' Association | `https://sedratoronto.ca/feed/` | Domain corrected. The earlier guess `sedra.ca` returned 404. |
| North Rosedale Residents' Association | `https://northrosedale.ca/feed/` | Connect timeout. Slow host, not a wrong address. Retrying at 60 seconds. |

## Tier 2 - exists, but you write a scraper

| Source | Why it costs more |
| --- | --- |
| ~~TPS news releases~~ | **Moved to blocked.** Returned HTTP 403. The site rejects automated requests, and that is the publisher saying no. Use their email subscription instead. |
| TMMIS council and committee agendas (`app.toronto.ca/tmmis/`) | No API, no RSS. Server-rendered search you can scrape. Leaside sits under **North York Community Council**, which is the meeting to watch. |
| Committee of Adjustment North York schedule | Agendas are PDFs on a schedule page. Cheaper first cut: read CofA hearing notices out of the public notices JSON above. |
| Metrolinx Eglinton Crosstown notices | Per-project email and RSS subscriptions exist but the feed URL is not published. Subscribe by email first. Laird and Leaside stations are on your doorstep. |

## Tier 3 - blocked, and worth knowing why

| Source | Verdict |
| --- | --- |
| **Facebook groups** | Dead. Meta removed the Groups API endpoints and permissions in April 2024 across all API versions. No third-party app can read a group feed. The only working paths are a browser extension inside your own logged-in session or reading it yourself, and automating either breaches Facebook's terms. Treat Facebook as a human input, not a source. |
| **Application Information Centre (AIC)** | Confirmed HTTP 403. JavaScript front end over an undocumented internal endpoint. Development applications, Committee of Adjustment and Toronto Local Appeal Body files all live here. You can capture the XHR the page makes, but it is fragile and legally grey. Ask `developmentreview@toronto.ca` for documented access. |
| **Real estate listings and sales** | You were right to skip it. Toronto Regional Real Estate Board data is licensed to members. Assessment data from MPAC and land registry searches are paid. Building permits are the free proxy for "what is changing". |
| **Councillor newsletter** | Email only. No RSS. Ward 15 Don Valley West is represented by **Rachel Chernos Lin**, elected in a November 2024 by-election. Subscribe by emailing `councillor_chernoslin@toronto.ca`. |
| **Toronto Local Appeal Body decisions** | Decisions from 1 February 2023 onward are on CanLII. Earlier ones are by request only. No API. |

## Geography

Area matching uses `config/areas.geojson`. Those polygons are **hand-drawn rectangles**,
good enough to filter a crime point away from downtown, not good enough to draw a map.
Replace them with the City's official neighbourhood boundaries from the Open Data
portal. Leaside is neighbourhood "Leaside-Bennington" in the 158-neighbourhood set.

One privacy note that matters: Toronto Police deliberately offset every crime point to
the nearest road intersection. Never render or describe those points as exact addresses.

## What the probe changed

| Finding | Action taken |
| --- | --- |
| 4 feeds and 2 JSON APIs work | Promoted to `verified` and switched on |
| 2 residents' associations were at the wrong domain | Corrected to `moorepark.org` and `sedratoronto.ca` |
| 3 sources timed out | Given per-source timeouts up to 180 seconds and three retries with backoff |
| 2 sources returned HTTP 403 | Marked blocked. No user-agent disguising, no workaround. |
| Crime data spans a decade | Capped at 90 days so it cannot bury the neighbourhood news |
| KSI data starts in 2006 | Rows now pulled newest first, capped at 365 days |

## Residents' associations beyond the original six

The Federation of North Toronto Residents' Associations is the directory that matters.
It represents more than thirty associations covering over 175,000 residents, and its
member page is how the Moore Park and Davisville addresses were corrected.

`python -m leaside.cli discover` now reads that page, plus the Leaside Residents
Association resources page, follows every outbound link, and tests each site for a
feed. It writes `config/associations-report.md` with ready-to-paste YAML.

Known to exist and worth checking in that report, roughly in order of closeness
to Leaside:

| Association | Note |
| --- | --- |
| Bennington Heights Residents' Association | Directly adjacent, effectively part of your area. No website found by search. |
| Governor's Bridge Ratepayers' Association | Adjacent, between Leaside and Rosedale. No website found by search. |
| Leaside Towers Tenants Association | `leasidetowerstenants.ca`. Thorncliffe Park, across the Don. Carries the tenant side of local issues, which nothing else here does. |
| Deer Park Ratepayers' Group | Borders Moore Park to the west. |
| Sherwood Park Residents' Association | Between Lawrence Park and Blythwood. |
| Oriole Park Association | `opa32.wildapricot.org`. West of Davisville. |
| Teddington Park Residents' Association | North of Lawrence Park. |
| Lytton Park Residents' Organization | `lyttonparkro.ca`. North of Lawrence Park. |
| Bedford Park Residents' Organization | Further north, marginal for your purposes. |
| South Armour Heights, Annex, Willowdale, York Mills and about twenty more | FONTRA members, but nowhere near Leaside. Ignore them. |

The honest filter: an association matters to this project when its boundary touches
one of your seven areas. FONTRA covers most of north Toronto, so the majority of its
membership is noise for you. Adding all thirty would make the page worse, not better.

## Directory scan results, September 2026

The scan tested 53 websites reached from the FONTRA member pages and the Leaside
Residents Association resources page. Twenty-three had a working feed. Ten were kept.

### Kept

| Source | Why |
| --- | --- |
| The South Bayview Bulldog | Best source found. Its stated coverage is South Bayview including Leaside, Davisville, Bennington Heights and Moore Park, which is almost exactly the project's scope, and it publishes far more often than the monthly paper. |
| Bayview-Leaside Business Improvement Area | Shop openings, closings and street events on Bayview. Has a feed, contrary to what this document previously said. |
| Leaside Business Park Association | Covers the commercial lands east of Laird, where the redevelopment pressure is. |
| Leaside Memorial Community Gardens | Arena and community centre events and closures. |
| Leaside Baseball Association | Community activity rather than news. Filterable. |
| Leaside Heritage Preservation Society | Could not connect. Retrying once with a longer timeout because heritage fights on Leaside streets are directly relevant. |
| Deer Park Residents' Group | Borders Moore Park at Yonge and St Clair. New area added. |
| Lytton Park Residents' Organization | Borders Lawrence Park to the west. Most active feed found, 16 entries. New area added. |
| FONTRA | The umbrella group's own planning submissions. No area forced. |

### Rejected, and why

| Source | Reason |
| --- | --- |
| ABC Residents' Association | Covers Yorkville and North Midtown, Yonge to Avenue Road, Bloor to the rail corridor. Nowhere near Leaside. |
| Bedford Park, Bedford-Wanless, Henry Farm, South Armour Heights, York Mills Valley, FoSTRA | FONTRA members in north Toronto, all well outside the seven areas. |
| Federation of Urban Neighbourhoods | Province-wide advocacy, not neighbourhood news. |
| Don Valley Community Legal Services | A legal clinic. Useful to residents, but not a news source. |
| Eglinton Park Residents' Association | Centred on Eglinton and Avenue Road, roughly two and a half kilometres west of Davisville. Close enough to be tempting, far enough to be noise. |

### Had no feed but still matter

Governor's Bridge Ratepayers, Teddington Park, Oriole Park, Summerhill, Annex,
Greater Yorkville and about fifteen others publish only on the page itself or by
email. Toronto Public Library's Leaside branch and Toronto Police 53 Division are
in the same position. For the ones inside the seven areas, the mailing list route in
docs/MAILING-LISTS.md is the answer, not a scraper.
