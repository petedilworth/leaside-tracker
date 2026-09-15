# Roadmap

The organising principle: **build what has a feed, and buy the rest with a human step.**
Ranked by value divided by effort, not by how much you want it.

## Phase 0 - done in this repo

Source registry, SQLite store, area matching, a probe that tells you which of your
guesses are real, a static renderer, offline fixture tests.

## Phase 1 - one week. The digest that earns its keep.

1. Run the probe. Fix or delete every source that fails.
2. Turn on the residents' association feeds, Leaside Life, and the City Clerk
   public notices JSON.
3. Filter notices to your streets. Render a single reverse-chronological page.
4. Schedule it: `cron` daily, `git commit` the SQLite file, open the HTML from disk.

Stop here for two weeks and see whether you read it. If you do not, nothing in
Phase 2 saves the project.

## Phase 2 - two weeks. Email becomes a feed.

The councillor's newsletter, most residents' association mail, the South Bayview BIA
and Metrolinx construction notices are all email-only. Create a dedicated address,
subscribe it to everything, and read it over IMAP. One connector unlocks about half
of what you asked for. This is the highest-leverage thing in the whole plan.

## Phase 3 - two weeks. Crime and collisions.

Toronto Police ArcGIS layers plus the City's KSI dataset, both filtered by bounding
box. Set expectations now: this data refreshes roughly monthly and points are
offset to intersections. It answers "is break-and-enter up this year", not
"what happened last night". For last night, the TPS news release scraper is closer.

## Phase 4 - ongoing. Planning and development.

Committee of Adjustment via the public notices feed first. TMMIS North York Community
Council agenda scraping second. Application Information Centre last, only after you
have asked the City for documented access.

## Phase 4b - done. The weekly email.

GitHub runs the collection every Monday and emails everything new, through Resend.
The project was pull-only until this: nothing arrived unless someone remembered to
double-click. Setup is in docs/EMAIL-DIGEST.md and takes ten minutes, once.

The database is kept on a separate `state` branch between runs, deliberately not
alongside the code. A database committed to the working branch makes `git pull`
conflict on any machine that also runs the project, which is the exact fault that
hid five sessions of fixes from the owner's PC.

## Phase 5 - only if you go public.

Attribution, a robots-respecting fetcher, no republished article bodies, and a
privacy pass on anything that names a person or an address.

---

## Five more things worth tracking

1. **Email as a source.** Not a feed, a technique. A dedicated mailbox plus IMAP turns
   every unsubscribable newsletter into structured data. Do this before anything clever.

2. **Liquor and business licence applications.** The Alcohol and Gaming Commission of
   Ontario posts public notices of licence applications, and the City posts business
   licence and patio applications. This is your earliest warning of what is opening and
   closing on Bayview, weeks before anyone posts about it.

3. **Tree and ravine permits.** Leaside's mature canopy and the ravine protection bylaw
   generate a steady stream of permit applications and objections. It is a live local
   fight, it is published, and nobody aggregates it.

4. **School accommodation and enrolment.** Toronto District School Board and the
   Catholic board publish enrolment, boundary reviews and accommodation reviews.
   Leaside High School capacity is a recurring neighbourhood issue and it moves
   property decisions more than most crime data does.

5. **A street-name watchlist that cuts across every source.** The real product is not
   another list of feeds. It is one query that runs your street names against council
   agenda text, planning notices, appeal decisions and news, and tells you when your
   block gets mentioned anywhere. Build this once you have three sources, not five.

Honourable mentions: Toronto Hydro outage map, 311 request density as a proxy for
neighbourhood complaints, and Toronto Water basement-flooding project notices.
