# The weekly email

Every Monday around 7am Toronto time, GitHub collects the news and emails you
everything new since the last email. Your computer does not need to be on. If a
week is missed, the next email covers both weeks rather than losing one.

Setting it up takes about ten minutes and you do it once.

If the page is published on the web (see `docs/PUBLISH.md`), the email links
to it at the top. Nothing to configure: the workflow checks whether GitHub
Pages is on and adds the link only when it is.

---

## Step 1. Get a Resend account and key

Resend sends the email. Its free tier covers 3,000 emails a month, which is about
250 years of weekly digests.

1. Go to **https://resend.com** and sign up. Use your normal email address.
2. Once you are in, find **API Keys** in the left sidebar.
3. Click **Create API Key**. Name it `leaside-tracker`. Permission: **Sending access**.
4. Copy the key. It starts with `re_`. **You cannot see it again**, so paste it
   somewhere safe for the next few minutes.

There is nothing else to configure at Resend. No domain, no DNS, no verification.
The email will arrive from `onboarding@resend.dev`, which is the sender their free
tier allows, and it can only be sent to the address you signed up with. That is
exactly what we want, since this email is only for you.

---

## Step 2. Give GitHub the key

1. Go to **https://github.com/petedilworth/leaside-tracker/settings/secrets/actions**
2. Click **New repository secret**.
3. Name: `RESEND_API_KEY`. Secret: paste the key from step 1. Click **Add secret**.
4. Click **New repository secret** again.
5. Name: `DIGEST_TO`. Secret: the email address you want the digest sent to, which
   must be the address you signed up to Resend with. Click **Add secret**.

GitHub hides both values from then on, including from Claude. Nobody can read them
back out, which is why step 1 said to keep the key safe until now.

---

## Step 3. Test it before waiting a week

1. Go to **https://github.com/petedilworth/leaside-tracker/actions**
2. Click **Weekly digest** in the left sidebar.
3. Click **Run workflow** on the right. Leave the tick box unticked. Click the
   green **Run workflow** button.
4. Wait. The first run takes about five minutes, because it collects everything
   from scratch.
5. Check your inbox.

If no email arrives, click into the run and open the **Send the digest** step. It
says what went wrong. Send that to Claude.

---

## What the first email looks like

Larger than normal. GitHub starts with an empty database, so everything currently
published counts as new, up to a cap of 60 items with a note saying how many more
there were. Every email after that covers only the week.

## What it contains

Items grouped by kind, with the ones that might need a response first: city
notices, planning, residents' associations, local news, business, community, then
crime and collisions at the bottom as record-keeping. Each item has its headline,
neighbourhood, source, date, a summary, and a link.

## Changing the day or time

The schedule lives in `.github/workflows/weekly-digest.yml` on the line beginning
`- cron:`. It is written in UTC. `0 11 * * 1` is Monday at 11:00 UTC, which is 7am
in Toronto during daylight saving and 6am in winter. Ask Claude rather than editing
it, unless you enjoy cron syntax.

## Turning it off

Go to the Actions tab, click **Weekly digest**, then the **...** menu on the right
and choose **Disable workflow**. Nothing else changes and no data is lost.

## What this does not replace

Your local copy still works and is still worth keeping: the page has filters, read
state, the Since control and the map links, and the email does not. The email is
there so you hear about things without having to remember to look.
