# What data actually exists

Compiled 6 September 2026. **Nothing here was fetched.** The session that wrote this
had no outbound internet access, so every URL below comes from search results and
publisher documentation, not from a live request. Run `python -m leaside.cli probe`
on your own machine to turn these claims into facts.

Sources are graded on how much work they cost you, not on how interesting they are.

## Tier 1 - real machine-readable feeds, low effort

| Source | Endpoint | What you get |
| --- | --- | --- |
| City Clerk public notices | `https://secure.toronto.ca/nm/notices.json` | Every notice published since 2018, in JSON, in real time. Includes Committee of Adjustment hearings, road closures, public meetings. Documented at `secure.toronto.ca/nm/opendata.do`. |
| Toronto Open Data (CKAN) | `https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/...` | Standard CKAN. `package_search`, `package_show`, `datastore_search`. Gateway to collisions, 311, building permits, neighbourhood boundaries. |
| Toronto Police open data | `https://data.tps.ca/api/feed/dcat-us/1.1.json` | ArcGIS Hub DCAT catalogue. Discover Major Crime Indicators, Shootings, Homicides, Traffic Collisions and KSI layers, then query each FeatureServer with a bounding box. |
| KSI collisions | Toronto Open Data dataset `motor-vehicle-collisions-involving-killed-or-seriously-injured-persons` | 2006 to present, City and TPS jointly. |
| Residents' association and local paper feeds | `/feed/` on each WordPress site | Leaside Residents Association, North Rosedale, South Rosedale, Lawrence Park, Leaside Life. All unconfirmed until probed. |

## Tier 2 - exists, but you write a scraper

| Source | Why it costs more |
| --- | --- |
| TPS news releases (`tps.ca/media-centre/news-releases/`) | TPS says an RSS feed exists and has publicly said it breaks. Scrape the HTML list. Releases name intersections, so geocode to filter. |
| TMMIS council and committee agendas (`app.toronto.ca/tmmis/`) | No API, no RSS. Server-rendered search you can scrape. Leaside sits under **North York Community Council**, which is the meeting to watch. |
| Committee of Adjustment North York schedule | Agendas are PDFs on a schedule page. Cheaper first cut: read CofA hearing notices out of the public notices JSON above. |
| Metrolinx Eglinton Crosstown notices | Per-project email and RSS subscriptions exist but the feed URL is not published. Subscribe by email first. Laird and Leaside stations are on your doorstep. |

## Tier 3 - blocked, and worth knowing why

| Source | Verdict |
| --- | --- |
| **Facebook groups** | Dead. Meta removed the Groups API endpoints and permissions in April 2024 across all API versions. No third-party app can read a group feed. The only working paths are a browser extension inside your own logged-in session or reading it yourself, and automating either breaches Facebook's terms. Treat Facebook as a human input, not a source. |
| **Application Information Centre (AIC)** | JavaScript front end over an undocumented internal endpoint. Development applications, Committee of Adjustment and Toronto Local Appeal Body files all live here. You can capture the XHR the page makes, but it is fragile and legally grey. Ask `developmentreview@toronto.ca` for documented access. |
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
