# The hourly timer on Cloudflare

## Why it exists

The police calls map shows each call for about four hours, then drops it. The
tracker keeps a call only if it checks the map while the call is still there.

GitHub's own timer is set to check every half hour, but GitHub skips most of
those runs on a busy day. From 3 October to 2 November 2026 it ran about 5 times
a day instead of 48. The typical gap was 4.7 hours and the longest 10.4 hours,
so about one call in four was lost. None of the skipped runs failed: GitHub
never started them. The daily publish, set for 10:17 UTC, also started 4 to 7
hours late.

A press of GitHub's **Run workflow** button has never been skipped. So a small
program on Cloudflare presses that button once an hour. GitHub's own timer stays
on as a backup. A run every hour means no gap longer than about an hour and a
half, well inside the four-hour window.

## What is where

| Piece | Where | What it does |
|---|---|---|
| `cloudflare/poll-timer.js` | this repository | The program, kept here for its history and tests |
| The Worker `leaside-poll-timer` | your Cloudflare account | The running copy, pasted from the file above |
| Secret `GITHUB_TOKEN` | the Worker's settings | A GitHub key that can only start runs on this repository |
| Cron trigger `13 * * * *` | the Worker's settings | Runs it at 13 minutes past every hour |

Cloudflare's free plan includes timers like this
([Cloudflare limits](https://developers.cloudflare.com/workers/platform/limits/)).

## Setting it up, once

### Part 1 - a GitHub key that can only start runs

1. Go to **https://github.com/settings/personal-access-tokens/new**
2. **Token name:** `Cloudflare poll timer`
3. **Expiration:** pick the longest choice offered. When it runs out, the timer
   stops and GitHub's own timer carries on alone.
4. **Repository access:** pick **Only select repositories**, then choose
   **leaside-tracker**.
5. **Permissions:** open **Repository permissions**, find **Actions** and set it
   to **Read and write**. Leave everything else alone.
6. Click **Generate token** at the bottom.
7. Copy the key it shows (it starts with `github_pat_`). GitHub shows it once.
   Keep the tab open until Part 2 step 9. Do not paste it anywhere else.

### Part 2 - the Worker on Cloudflare

1. Go to **https://dash.cloudflare.com/sign-up** and make a free account.
   Confirm the email Cloudflare sends.
2. In the menu on the left, click **Workers & Pages** (it may sit under
   **Compute**).
3. Click **Create**, then **Start with Hello World!**. If Cloudflare asks you to
   pick a `workers.dev` subdomain first, any name is fine.
4. **Name:** `leaside-poll-timer`. Click **Deploy**.
5. Click **Edit code**.
6. In a new tab, open
   **https://raw.githubusercontent.com/petedilworth/leaside-tracker/main/cloudflare/poll-timer.js**,
   select all (Ctrl+A) and copy (Ctrl+C).
7. Back in the editor, select everything (Ctrl+A), paste (Ctrl+V), then click
   **Deploy**.
8. Go back to the Worker's page and open **Settings**.
9. Under **Variables and Secrets**, click **Add**. Set **Type** to **Secret**,
   **Variable name** to `GITHUB_TOKEN`, and paste the GitHub key as the value.
   Click **Deploy**.
10. Still in **Settings**, under **Trigger Events**, click **Add**, then
    **Cron Triggers**. Choose to write a custom expression and enter
    `13 * * * *`. Click **Add**.

### Part 3 - check it works

1. Wait until a little after 13 minutes past the next hour.
2. Go to **https://github.com/petedilworth/leaside-tracker/actions/workflows/live-poll.yml**
3. The newest run should say **Manually run by** your name. That is the
   timer. Runs that GitHub's own timer started say **Scheduled**.

If no such run appears, open the Worker in Cloudflare and look at **Logs**, or
the cron trigger's past events. The message there says what went wrong:

- **GitHub answered 401** - the key is wrong or expired. Make a new one (Part 1)
  and replace the secret (Part 2 step 9).
- **GitHub answered 403 or 404** - the key cannot see the repository, or
  **Actions** is not set to **Read and write**.
- **No GITHUB_TOKEN secret** - Part 2 step 9 was skipped or the name is spelt
  differently.

## Changing the program

Edit `cloudflare/poll-timer.js` here, run the tests, then paste the new version
into the Cloudflare editor (Part 2 steps 5 to 7). The two copies are not linked.
