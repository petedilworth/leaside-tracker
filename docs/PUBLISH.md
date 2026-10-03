# Putting the page on the web

Once this is set up, GitHub collects the news every morning and publishes the
page at **https://petedilworth.github.io/leaside-tracker/**. Your PC does not
need to be on. A code change pushed to `main` republishes within minutes.

The page is public: anyone with the address can open it. It is **not
searchable**: every page carries a `noindex` tag, which Google, Bing and
DuckDuckGo honour, so it will not turn up in search results. Someone has to be
given the address.

Setting it up takes about five minutes and you do it once.

---

## Step 1. Make the repository public

GitHub Pages on a free account only works for public repositories. Private
Pages need GitHub Pro, about 4 US dollars a month. Going public means the code,
the documents in this folder and the collected data all become readable by
anyone who finds the repository. There are no passwords or keys in it: the
email key lives in GitHub Secrets, which stay private. The one personal detail
is your email address in `config/sources.yaml`, which identifies the crawler to
the websites it visits. It is already in every commit you have made, so public
changes nothing there.

1. Go to **https://github.com/petedilworth/leaside-tracker/settings**
2. Scroll to the bottom, to the red **Danger Zone** box.
3. Click **Change visibility**, then **Change to public**.
4. GitHub asks you to type the repository name to confirm. Type
   `petedilworth/leaside-tracker` and click the confirm button.

If you would rather pay for Pro and keep the code private, skip this step. The
remaining steps are the same.

---

## Step 2. Switch on GitHub Pages

1. Go to **https://github.com/petedilworth/leaside-tracker/settings/pages**
2. Under **Build and deployment**, find **Source**.
3. Change it from "Deploy from a branch" to **GitHub Actions**.

That is the whole setting. There is no save button; it applies at once.

---

## Step 3. Publish for the first time

1. Go to **https://github.com/petedilworth/leaside-tracker/actions**
2. Click **Publish the site** in the list on the left.
3. Click the grey **Run workflow** button on the right, then the green
   **Run workflow** button underneath it.
4. Wait. The run takes five to ten minutes because it collects everything first.
   Refresh the page: a green tick means it worked.
5. Open **https://petedilworth.github.io/leaside-tracker/**

Bookmark that address. The full collection runs every morning around 6am
Toronto time, and the police-calls strip at the top refreshes every half hour.
The trends page is at **https://petedilworth.github.io/leaside-tracker/trends.html**
and is linked from the top of the main page.

From the next weekly email onward, the email links to the live page too.

---

## If the run fails

Click the failed run, then click the red step to see its message.

- **A yellow "Page not published" notice** and no Deploy step: Step 2 was missed.
  The run still collected and saved. Do Step 2 and run the workflow again.
- **"Resource not accessible by integration"** in *Deploy*: Pages is set to
  "Deploy from a branch". Change it to GitHub Actions (Step 2).
- **A red step called *Collect***: a source was down. The page still publishes
  from everything else and will catch up tomorrow.

---

## Taking it down

Go to the Pages settings page from Step 2 and click **Unpublish site**. The
address stops working within minutes. The workflows keep collecting and simply
skip publishing, with a notice, until Pages is switched back on.

---

## How it stays unsearchable, and the limit of that

The `noindex` tag asks search engines not to list the page, and the large ones
comply. It does not stop a person who has the address from sharing it, and it
does not hide the repository itself: a public repository's front page on
github.com can appear in search results, with its name and README. The page
address is not written anywhere in the repository except this document, so
finding the repository does not hand anyone the page by itself, but it is one
click away through the Actions tab. If that matters, GitHub Pro and a private
repository is the only arrangement that closes it.
