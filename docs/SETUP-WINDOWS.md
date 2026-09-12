# Setting this up on your Windows PC

Follow these in order. Do not skip step 1. Total time is about 15 minutes,
and most of that is waiting for downloads.

---

## Step 1. Install Python

Python is the language this project is written in. Your PC almost certainly
does not have it yet.

1. Open your web browser and go to **https://www.python.org/downloads/**
2. Click the big yellow button that says **Download Python**.
3. When the download finishes, open the file. An installer window appears.
4. **This is the important bit.** At the bottom of the first screen there is a
   tick box that says **"Add python.exe to PATH"**. Tick it.
   It is small and easy to miss. Nothing works if you skip it.
5. Click **Install Now**.
6. Wait. When it says "Setup was successful", click **Close**.

### How to check it worked

1. Press the **Windows key**, type `cmd`, press **Enter**. A black window opens.
2. Type this exactly, then press Enter:

   ```
   python --version
   ```

3. You should see something like `Python 3.13.1`. The numbers do not matter.

   If instead you see "Python was not found" or the Microsoft Store opens,
   the tick box in step 4 was missed. Run the installer again, choose
   **Modify**, and make sure "Add python.exe to PATH" is on.

Leave the black window open. You need it for step 2.

---

## Step 2. Get the project onto your PC

You said you have used Git before. In that same black window, type these
three lines, pressing **Enter** after each one.

```
cd %USERPROFILE%\Desktop
```

```
git clone https://github.com/petedilworth/leaside-tracker.git
```

```
cd leaside-tracker && git checkout claude/leaside-news-tracker-8p523i
```

What those do, in plain English:

| Line | What it does |
| --- | --- |
| `cd %USERPROFILE%\Desktop` | Move to your Desktop, so the folder lands somewhere you can find it |
| `git clone ...` | Download the project |
| `git checkout ...` | Switch to the version with the actual code in it. Skipping this leaves you with an almost empty folder. |

You should now have a folder called **leaside-tracker** on your Desktop.

### If `git` is not recognised

Then Git is not installed after all. Instead:

1. Go to **https://github.com/petedilworth/leaside-tracker/tree/claude/leaside-news-tracker-8p523i**
2. Click the green **Code** button, then **Download ZIP**.
3. Find the ZIP in your Downloads folder, right-click it, choose **Extract All**,
   and extract it to your Desktop.

---

## Step 3. Run it

1. Open the **leaside-tracker** folder on your Desktop.
2. Find the file called **run-windows.bat** and double-click it.
3. A black window opens and starts working. The first run takes about a minute
   longer than later ones, because it is installing things.
4. When it finishes, your page opens automatically in your web browser.

### If Windows blocks it

Windows sometimes shows a blue box saying "Windows protected your PC". That is
because the file came from the internet, not because anything is wrong.
Click **More info**, then **Run anyway**.

---

## Step 4. Read what happened

The run now ends by writing **`config\health-report.md`** and opening it in Notepad
behind your browser. That one file is everything Claude needs to know about how the
run went: what came in, from where, whether anything is duplicated, and what failed.

**When Claude asks how the run went, send that file.** You no longer need to
screenshot the page or copy the black window.



Two things are worth looking at after the first run.

**Your page.** It opened in your browser. On the very first run it will look
thin, possibly empty. That is expected and it is not a failure.

**The probe report.** In the leaside-tracker folder, open
`config\probe-report.md` in Notepad. This is the honest scorecard. Every row is
one news source, and the "probe verdict" column tells you the truth about it:

| Verdict | What it means | What to do |
| --- | --- | --- |
| `feed` | Working. Real news feed found. | Nothing. It is already collecting. |
| `json` | Working. Real data feed found. | Nothing. |
| `html` | The website is there but has no feed. | Tell Claude. Someone has to write a scraper for it. |
| `error` | Timed out. Could be a slow site or a wrong address. | Tell Claude the source name. |
| `dead` | HTTP 403 means the site refuses robots. HTTP 404 means the address is wrong. | Tell Claude. A 403 is usually final. |
| `no-url` | Deliberately left out, e.g. Facebook. | Nothing. Explained in the notes. |

**Send me that file.** Copy the contents into a message and I will fix every
broken source and turn on everything that works. Until you do, the page will
stay thin, because right now none of those web addresses has ever been tested.

---

## Finding more residents' associations

There is a one-off job that finds associations this project does not know about yet.
It reads the Federation of North Toronto Residents' Associations member list, follows
every link on it, and tests each website for a news feed.

1. Double-click **find-associations.bat**.
2. Wait. It visits about forty websites, politely, one at a time. Several minutes.
3. It opens `config\associations-report.md` in Notepad when it finishes.
4. Copy that whole file and send it to Claude.

You only need to do this once, or again in a year when the list changes.

---

## Getting my fixes onto your PC

When I change something, you need to pull it down before it takes effect.
Open the black window, then type these two lines:

```
cd %USERPROFILE%\Desktop\leaside-tracker
git pull
```

Then double-click **run-windows.bat** as usual.

If you downloaded the ZIP instead of using Git, download a fresh ZIP and
replace the folder. Keep your `data` folder if you want to keep old items.

---

## Running it again later

Just double-click **run-windows.bat** again. It picks up anything new and
rebuilds the page. Once a day is plenty. Once a week is fine.

Runs are quicker now. The source check in step 1 only repeats once a week; on other
days it says so and moves on.

## Reading the page

The page opens showing only what you have not read. Each item has a green dot. Click
a headline to open it in a new tab, which also marks it read. Click the tick on the
right to mark it read without opening it. **Mark all read** clears everything in view.

Your read history lives in your browser, not in the project. Clearing browser data
or switching browsers starts you fresh. That is a limitation, not a bug, and it is
the price of the site being a plain file with no account behind it.

Switch **Show** to **Everything** to see read items again. Dates and the day
headings are in your own time zone.

Under each item is a link row. **Read the original** opens the article on the site
that published it. Items from a dataset have no article of their own, so they offer
**Where this came from** instead, and **See it on a map** when the record has
coordinates.

Long summaries are trimmed to four lines with a **Show more** button underneath.

The **Where** row is a set of on/off switches, not a single choice. Click a
neighbourhood to hide it, click again to bring it back. Lytton Park starts switched
off because it is the furthest area from Leaside. Your choice is remembered.
**Reset areas** puts it back to the default.

---

## If you want to see what a finished page looks like

You can load five fake sample items and see the layout. This is completely
separate from your real data and cannot mix with it. In the black window, inside
the leaside-tracker folder, type:

```
.venv\Scripts\python.exe -m leaside.cli demo
```

Then open `site\demo.html` in the folder. Every fake item is labelled `[demo]`.
Your real page is `site\index.html` and the demo never touches it.

If you ran an older version of the demo, a few `[demo]` items may have crept into
your real page. The next normal run removes them automatically and says so.

---

## When something goes wrong

The black window will print a wall of text ending in words like `Error` or
`Traceback`. Nothing is broken and nothing is lost. Everything already collected
is saved in the `data` folder.

1. Click inside the black window.
2. Press **Ctrl+A** to select everything, then **Ctrl+C** to copy.
3. Paste it to Claude.

That text names the exact file and line that failed, which is usually enough to
fix it in one go. Do not try to read it yourself.

### A note about Anaconda

If you have Anaconda installed, Python may come from there instead of from
python.org. That is fine and it works. It only matters because Anaconda's Python
handles foreign characters differently on Windows, which caused the first crash
of this project. It is fixed.
