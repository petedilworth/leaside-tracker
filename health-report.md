# Health report

Produced by code **64b12a2 · dated 2026-10-06 · 4 days old**.

> This code is 4 days old (64b12a2). If Claude has sent fixes since, run `git pull` before reading anything into these results.

- rows stored: **23198** (nothing is ever deleted)
- rows the page can show: **21816**
- routine rows, logged but not shown: **1232**
- hidden rows, kept in the log: **50**
- changes recorded: **1099**
- duplicate links: **0**
- duplicate headlines: **207**

## Per source

| source | rows | no date | html left | no link | oldest | newest |
| --- | --- | --- | --- | --- | --- | --- |
| `city_building_permits` | 8788 | 0 | 6 | 8788 | 1987-12-25 | 2026-10-08 |
| `tps_reported_crime` | 8454 | 0 | 0 | 8454 | 2013-05-17 | 2026-09-30 |
| `city_dinesafe` | 2855 | 0 | 0 | 2855 | 2023-11-13 | 2026-10-09 |
| `tps_traffic_collisions` | 2204 | 0 | 0 | 2204 | 2025-06-26 | 2026-09-30 |
| `city_public_notices` | 273 | 0 | 5 | 0 | 2018-01-08 | 2026-09-11 |
| `news_police_coverage` | 131 | 0 | 0 | 0 | 2016-07-21 | 2026-10-06 |
| `news_leaside_coverage` | 125 | 0 | 0 | 0 | 2017-11-07 | 2026-10-07 |
| `city_ksi_collisions` | 104 | 0 | 0 | 104 | 2006-02-19 | 2024-04-08 |
| `tps_hub_dcat` | 100 | 0 | 1 | 0 | 2024-03-21 | 2026-10-08 |
| `tps_calls_for_service` | 78 | 0 | 0 | 78 | 2026-10-02 | 2026-10-10 |
| `media_south_bayview_bulldog` | 13 | 0 | 0 | 0 | 2026-06-17 | 2026-10-07 |
| `ra_leaside` | 11 | 0 | 0 | 0 | 2026-03-22 | 2026-10-07 |
| `biz_bayview_leaside_bia` | 10 | 0 | 0 | 0 | 2023-03-01 | 2026-09-02 |
| `community_leaside_gardens` | 10 | 0 | 0 | 0 | 2024-11-21 | 2026-03-18 |
| `planning_fontra` | 10 | 0 | 0 | 0 | 2025-12-02 | 2026-09-26 |
| `ra_south_rosedale` | 10 | 0 | 0 | 0 | 2022-12-05 | 2025-11-20 |
| `ra_davisville` | 9 | 0 | 0 | 0 | 2025-09-12 | 2026-04-25 |
| `ra_moore_park` | 9 | 0 | 0 | 0 | 2026-04-01 | 2026-09-28 |
| `biz_leaside_business_park` | 4 | 0 | 0 | 0 | 2026-07-02 | 2026-10-05 |

## Duplicates

| source | what | copies |
| --- | --- | --- |
| `tps_traffic_collisions` | headline Collision | 20 |
| `tps_traffic_collisions` | headline Collision | 20 |
| `tps_traffic_collisions` | headline Collision | 15 |
| `tps_traffic_collisions` | headline Collision | 12 |
| `tps_traffic_collisions` | headline Collision | 12 |
| `tps_traffic_collisions` | headline Collision | 12 |
| `tps_traffic_collisions` | headline Collision | 11 |
| `tps_traffic_collisions` | headline Collision | 11 |
| `tps_traffic_collisions` | headline Collision | 10 |
| `tps_traffic_collisions` | headline Collision | 10 |
| `tps_traffic_collisions` | headline Collision | 10 |
| `tps_traffic_collisions` | headline Collision | 10 |
| `tps_traffic_collisions` | headline Collision | 10 |
| `tps_traffic_collisions` | headline Collision | 10 |
| `tps_traffic_collisions` | headline Collision | 9 |
| `tps_traffic_collisions` | headline Collision | 9 |
| `tps_traffic_collisions` | headline Collision | 9 |
| `tps_traffic_collisions` | headline Collision | 9 |
| `tps_traffic_collisions` | headline Collision | 9 |
| `tps_traffic_collisions` | headline Collision | 9 |

Duplicate links are always a fault. Repeated headlines are not always:
crime and collision records reuse short labels like `Assault`, so several
genuine incidents on one day share a headline. Judge those by the link column.

## What the raw records look like

Listed for sources where most rows lack a date or a link, and for every
source still marked guess. These are the actual keys and
sample values, so the parser can be matched to them.

### `city_building_permits`

| key | sample |
| --- | --- |
| `_id` | 194315 |
| `PERMIT_NUM` | 23 199052 BLD |
| `REVISION_NUM` | 01 |
| `PERMIT_TYPE` | Small Residential Projects |
| `STRUCTURE_TYPE` | 2 Unit - Detached |
| `WORK` | Multiple Projects |
| `STREET_NUM` | 270 |
| `STREET_NAME` | HILLSDALE |
| `STREET_TYPE` | AVE |
| `STREET_DIRECTION` | E |
| `POSTAL` | M4S |
| `GEO_ID` | 7324164 |
| `WARD_GRID` | S1228 |
| `APPLICATION_DATE` | 2024-01-15 |
| `ISSUED_DATE` | 2024-01-26 |
| `COMPLETED_DATE` | None |
| `STATUS` | Revision Issued |
| `DESCRIPTION` | Revision #01 - Minor changes in structure, windows at second |
| `CURRENT_USE` | Sfd |
| `PROPOSED_USE` | Sfd |
| `DWELLING_UNITS_CREATED` | 0 |
| `DWELLING_UNITS_LOST` | 0 |
| `EST_CONST_COST` | 0 |
| `ASSEMBLY` | 0 |
| `INSTITUTIONAL` | 0 |
| `RESIDENTIAL` | 22.58 |
| `BUSINESS_AND_PERSONAL_SERVICES` | 0 |
| `MERCANTILE` | 0 |
| `INDUSTRIAL` | 0 |
| `INTERIOR_ALTERATIONS` | 0 |
| `DEMOLITION` | 0 |
| `BUILDER_NAME` | None |

### `city_dinesafe`

| key | sample |
| --- | --- |
| `_id` | 115710 |
| `unique_id` | 5f2c458de5c9e457492f5a71b5a911b6 |
| `estId` | 001Vo000013QhKOIA0 |
| `oldEstId` | 10702353 |
| `estName` | BOMOU |
| `address` | 1636 Bayview Ave None M4G 3B7 |
| `inspectionStatus` | Conditional Pass |
| `phone` | 6473446455 |
| `inspectionDate` | 2024-04-19 |
| `observation` | One or more significant infractions were observed under the  |
| `typeDesc` | FOOD PREMISE NOT MAINTAINED WITH FOOD HANDLING ROOM IN SANIT |
| `deficiencyDesc` | 5C. Proper maintenance / washing of rooms (including washroo |
| `severity` | M - Minor |
| `OutcomeDate` | None |
| `OutcomeDesc` | None |
| `amountFined` | None |
| `latitude` | 43.706713 |
| `longitude` | -79.37592785 |

### `tps_calls_for_service`

| key | sample |
| --- | --- |
| `OBJECTID` | 26 |
| `OCCURRENCE_TIME` | 1790984800000 |
| `DIVISION` | D32 |
| `LATITUDE` | 43.72609117778053 |
| `LONGITUDE` | -79.39758914167055 |
| `CALL_TYPE_CODE` | BREEN |
| `CALL_TYPE` | BREAK & ENTER |
| `CROSS_STREETS` | CARDINAL PL - PRESTON PL |
| `OCCURRENCE_TIME_AGOL` | 1790984800000 |


## Feeds with nothing new in over a year

Still fetched every run, never on the page. Candidates to drop.

| source | newest item |
| --- | --- |
| `city_ksi_collisions` | 2024-04-08 |

## Rows not seen in the most recent run (started 2026-10-10T15:53)

| source | rows | last seen |
| --- | --- | --- |
| `tps_traffic_collisions` | 391 | 2026-10-07T17:29 |
| `tps_reported_crime` | 266 | 2026-10-07T17:29 |
| `city_building_permits` | 167 | 2026-10-09T17:04 |
| `tps_calls_for_service` | 74 | 2026-10-10T09:44 |
| `city_dinesafe` | 50 | 2026-10-05T19:35 |
| `news_police_coverage` | 31 | 2026-10-09T17:03 |
| `news_leaside_coverage` | 25 | 2026-10-09T17:03 |
| `media_south_bayview_bulldog` | 1 | 2026-10-06T22:54 |
| `ra_leaside` | 1 | 2026-10-07T17:26 |

## By neighbourhood

| area | items |
| --- | --- |
| Leaside | 5960 |
| Davisville | 5114 |
| North Rosedale | 4133 |
| Lawrence Park | 3427 |
| Moore Park | 2160 |
| South Rosedale | 2075 |
| Bennington Heights | 131 |
| Unmatched | 98 |

## Hidden from the page, kept in the log

| why | rows |
| --- | --- |
| superseded by a corrected record | 50 |

## Size of the log

The database is **46.6 MB**, about **7.1 MB** compressed, which is how it is stored on GitHub. GitHub refuses a single file over 100 MB.

## Last result per source

19 succeeded, 1 failed.

| source | error |
| --- | --- |
| `media_leaside_life` | HTTPError: 403 Client Error: Forbidden for url: https://leasidelife.com/feed/ |
