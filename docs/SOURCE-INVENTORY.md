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

## What the first health report showed, 12 September 2026

The first full look at the real database found three field-name guesses that had
been wrong since day one, without ever raising an error.

| Finding | What it meant | Fix |
| --- | --- | --- |
| Every one of 136 city notices had no date and no link | The title guess matched; the date and link guesses did not. Notices sorted by when they were first seen and could not be clicked. | Field names are now matched by fragment, not guessed. Ingest prints which key each field resolved to and warns when one is missing. |
| Serious collisions went from 137 rows to 1 | The date, latitude and collision-number columns were all guessed wrong. With the new stable key built from missing fields, every row produced the same key and they all collapsed. | Columns discovered from the datastore's own field list. Ingest prints the resolved columns and lists the real ones when a role cannot be filled. |
| 1,042 police collision rows dated January to June 2014 | The retired annual table left its rows behind. They inflated every neighbourhood count. | Retired dataset and directory sources are swept on every run. Retired feeds keep their history. |
| Two feeds have posted nothing in over a year | Lawrence Park's newest item is from November 2023; Leaside Baseball's from February 2024. Fetched every run, never on the page. | Reported under "Feeds with nothing new in over a year". Not dropped yet; that is the owner's call. |
| "Rows not seen in the latest run" listed every source | It compared against the newest timestamp rather than the run start, so a source fetched three minutes earlier looked stale. | Compares against the run start recorded in the runs table. |

For any source where most rows lack a date or a link, the health report now prints
the raw record's keys and sample values, so the next correction comes from evidence.

## Areas cut, September 2026

Deer Park, Lytton Park and Bedford Park are out. All three border the seven areas
rather than sitting in them, and none was ever going to be read.

| Area | What happened |
| --- | --- |
| Lytton Park | Added from the directory scan on the strength of having the most active feed found, 16 entries. Activity is not relevance. It sits west of Lawrence Park and two neighbourhoods from Leaside. Removed with its source. |
| Deer Park | Added because it borders Moore Park. Bordering the thing you care about is not the same as being it. Removed with its source. |
| Bedford Park | Never added. Rejected during the directory scan as too far north, and that judgement stands. |

Their stored rows are removed automatically on the next run, because a source that
is no longer configured has its items swept. The ability to keep an area but switch
it off by default remains in the code for the next one that turns out to be noise.

The lesson for future additions: the test is whether a source's boundary touches one
of the seven areas, not whether its feed is busy. I added two on the wrong test.

## The police catalogue, resolved

The 71 dataset names Toronto Police actually publish arrived on 12 September 2026,
and they explain a failure that had repeated on every run since the start.

**There is no "Major Crime Indicators" layer.** It does not exist under that name,
nor as MCI. Toronto Police publish each offence as its own dataset. The source was
looking for something the publisher had never offered.

Now collected as one source, `tps_reported_crime`, gathering six layers:

| Layer | Why |
| --- | --- |
| Break and Enter Open Data | The crime residents ask about most |
| Auto Theft Open Data | Ontario-wide concern, and a driveway crime |
| Theft From Motor Vehicle Open Data | Far more common than auto theft |
| Robbery Open Data | Person-on-person, on the street |
| Assault Open Data | Highest volume of the six |
| Bicycle Thefts Open Data | High volume in this part of the city |

Deliberately left out, though all are available:

| Layer | Why not |
| --- | --- |
| Homicides, Shooting and Firearm Discharges | Rare enough that Leaside Life or the Bulldog will tell you first, and with context |
| Hate Crimes | Reported counts are contested and easy to misread from a map pin |
| Mental Health Act Apprehensions, Persons in Crisis Calls | These are people in distress, not neighbourhood news. Mapping them onto a residential page is not something this project should do. |
| Intimate Partner and Family Violence | Same reasoning, with an added safety concern about locating victims |

Also found, and worth knowing about:

- **Killed and Seriously Injured**, plus Pedestrian, Cyclist, Automobile, Motorcylist,
  Passenger and Fatals KSI. A fallback if the City's collision dataset fails again.
- **Neighbourhood Crime Rates Open Data** and **Community Safety Indicators**. Rates
  per neighbourhood rather than incidents. The right source for "is break-and-enter
  up this year", which is a different question from "what happened this week".
- **Traffic Collisions Open Data (ASR-T-TBL-001)**, confirmed as the annual
  statistical table already retired from this project.

## First clean run, 12 September 2026

Sixteen sources, no failures, no duplicates, 228 rows instead of 1,502. The report
was then good enough to expose three real defects.

**City notices carry no link field at all.** Not under any name. The date guess was
fixed last session, but there was never a URL to find. The public detail page is
built from the notice id, confirmed against pages the City has published:
`https://secure.toronto.ca/nm/api/individual/notice/{noticeId}.do`. Notices also
carry an `addressList` with coordinates, so they are now placed by location rather
than by spotting a street name in the text, and each one gets a map link.

**A robbery in North St.James Town was filed as South Rosedale.** Four kilometres
away. The hand-drawn South Rosedale rectangle is wide enough to contain it. Every
Toronto Police record states its own City neighbourhood, so that now decides: a
record whose neighbourhood is not one of ours is dropped regardless of where the
rectangle thinks it falls. Records with no such field still use the rectangle.

This does not repair the overlapping rectangles, it routes around them for the one
source where the publisher knows better. Each area now also lists the official
neighbourhood names covering it:

| Our area | City neighbourhood |
| --- | --- |
| Leaside, Bennington Heights | Leaside-Bennington |
| North Rosedale, South Rosedale, Moore Park | Rosedale-Moore Park |
| Davisville | Mount Pleasant East |
| Lawrence Park | Lawrence Park South, Lawrence Park North |

Note the middle row. The City treats three of the seven areas as one neighbourhood,
which is why coordinates still decide and the official name is only a fallback.

**Crime data arrives about twelve weeks late.** On 12 September the newest record
was 20 June, 84 days old. A 90-day cap left a six-day window and returned two
incidents for the entire area. The cap is now a year.

## Dead feeds dropped, 12 September 2026

Two feeds had posted nothing in over a year, so neither could ever appear on a page
showing the last 120 days, yet both cost a request on every run.

| Source | Last post | Decision |
| --- | --- | --- |
| Lawrence Park Ratepayers' Association | November 2023 | Dropped. The **area is kept**: city notices and police records in Lawrence Park are still matched, by coordinates and by the official names Lawrence Park South and Lawrence Park North. Only the association's own newsletter is gone. |
| Leaside Baseball Association | February 2024 | Dropped. Added on the reasoning that "things going on" is wider than news. It was, and it was also silent. |

Fourteen sources now run. Of those, six are neighbourhood feeds, two are local
papers, two are business, one is community, one is planning advocacy, and three are
municipal or police data.

## Collisions and crime, 12 September 2026

Three questions from the owner, answered in the code.

**Do collisions have a location?** Yes, coordinates on every record, so each one
gets a map link. But the pin is the nearest road intersection, not the address:
Toronto Police move these deliberately for privacy. The page says so next to the
link and in its footer rather than only in this file.

Records now read as a place rather than a code. "Traffic Collision at BAYVIEW AVE
& MILLWOOD RD" with severity and neighbourhood underneath, instead of "Incident"
over a division code. An explicit intersection field wins over two street names,
and road class is never mistaken for a street.

**Is there a link to the original?** For collisions and crime, no article exists
anywhere. These are spreadsheet rows, not stories. Each links to the publisher's
data portal plus the map. Every other source links to its own article.

**Why were collisions missing?** My age caps at ingest. A 90-day cap discarded all
960 records in the area; a one-year cap discarded the same 960. They are now stored
in full and the page's Since control decides what is shown.

### A bug only a screenshot found

Filtered-out items stayed on screen while the counters correctly said they were
hidden. `li.item` sets `display:grid`, and an author rule beats the browser's own
`[hidden]` rule. Every browser test had been counting the attribute rather than
what a person sees, so all of them passed.

Fixed with an explicit `[hidden] { display:none !important; }`, and the tests now
count elements with a rendered box. Removing the CSS line again fails two tests, so
the guard is real.

## Why five sessions of fixes never arrived

`config/health-report.md` was committed to the repository. The program rewrites it
on every run, so git saw a local edit every time and refused to pull. Three
identical health reports in a row, and an apparently endless loop of "you need to
pull", all traced to one generated file that should never have been tracked.

Now ignored, along with every other generated output: the probe report, the
associations report, and the dataset catalogues. A test reads `git ls-files` and
fails if any of them is ever tracked again. Re-adding one and running the test
confirms it bites.

The launcher also tries to clear a blocked update by itself before giving up, and
its recovery instructions no longer print `%~dp0`, which only expands inside a
running script and would have failed if typed by hand.
