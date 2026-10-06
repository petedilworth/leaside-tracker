# The complete log

Since 6 October 2026, nothing this project collects is ever deleted. Every record
from every source is kept, and every change to a record is kept too.

## How to look at it

**On the web page.** Scroll to the bottom. The box called *The complete log* has
two download links. Both open in Excel.

- **Download everything**: one row per thing ever collected, shown on the page or
  not, with when it was first and last seen, where, and a link.
- **Download every change**: one row per event. *First seen*, *Changed* (with what
  changed and the old wording), *Hidden* (with why), *Seen again*.

**On your PC.** After running `run-windows.bat`, the same two files are in
`Documents\leaside-tracker\site\log\`. Note that your PC keeps its own copy of the
log, separate from GitHub's. GitHub's is the complete one, because it runs every
day whether your PC is on or not.

## What is kept but not shown on the page

| What | Why it is off the page | Where it is |
| --- | --- | --- |
| Clean restaurant inspections | A pass is the normal outcome and would bury the rest | Status *Routine, not shown* |
| Rows from a source that was removed | The source is gone | Status *Hidden: source no longer configured* |
| Rows stored under a faulty key | A parser fix replaced them with correct rows | Status *Hidden: superseded by a corrected record* |
| Items older than a source's email window | Too old to be news | On the page under *Since*, never emailed |

The page itself shows the newest 3,000 items. The download has all of them.

## What changed on 6 October

Before this, three things threw data away:

1. **Crime and collision records outside the newest 4,000 per offence were
   deleted every run.** The police service only hands out the newest 4,000, so
   each run deleted whatever had slipped past that line. They are now kept, so the
   history grows instead of sliding.
2. **City notices older than 120 days were discarded before being stored.** They
   are now stored, and kept out of the email instead.
3. **Clean restaurant inspections were discarded.** They are now stored as routine.

Records deleted before 6 October cannot be recovered. The log starts from what
the database held that day: 19,100 records.

## How it is protected

- **Compressed on GitHub.** The database was 32 MB. GitHub refuses any file over
  100 MB, so it is stored compressed: 4.5 MB. The health report states the size
  every run and warns well before the limit.
- **Never overwritten by a smaller copy.** Since nothing is deleted, a save with
  fewer records than the run started with is refused, and so is any save after a
  failed restore. Either would mean a fault, and pushing it would wipe the log.
- **A dated backup every Monday.** Under the repository's *Releases*, in
  *Log backups*. One compressed file per week, about 5 MB each. If anything ever
  goes wrong, tell Claude which date to go back to.

## What it does not fix

The log keeps everything the project *sees*. It cannot keep what it never sees.
Police calls show on the police map for about four hours. GitHub runs the
half-hourly check about five times a day, not 48, so calls that come and go
between checks are never collected. See the October entry in
`docs/SOURCE-INVENTORY.md` for the numbers.
