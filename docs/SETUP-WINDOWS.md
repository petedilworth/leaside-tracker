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
| `error` or `dead` | The address is wrong or the site is gone. | Tell Claude the source name. |
| `no-url` | Deliberately left out, e.g. Facebook. | Nothing. Explained in the notes. |

**Send me that file.** Copy the contents into a message and I will fix every
broken source and turn on everything that works. Until you do, the page will
stay thin, because right now none of those web addresses has ever been tested.

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

---

## If you want to see it working right now

Before any of the real sources are fixed, you can load fake sample items so you
can see what the finished page looks like. In the black window, inside the
leaside-tracker folder, type:

```
.venv\Scripts\python.exe -m leaside.cli demo
```

```
.venv\Scripts\python.exe -m leaside.cli build
```

Then open `site\index.html`. Every fake item is labelled `[demo]` so you will
never confuse it with real news. To clear them out later, delete the file
`data\leaside.db` and run the launcher again.
