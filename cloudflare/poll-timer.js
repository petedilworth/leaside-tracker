// Leaside Tracker - the hourly timer for the police calls check.
//
// GitHub's own timer skipped most of our scheduled runs: from 3 October to
// 2 November 2026 it ran the half-hourly poll about 5 times a day, not 48,
// with gaps up to 10 hours. A police call stays on the map about 4 hours, so
// every gap longer than that lost calls for good. GitHub has never skipped a
// press of the "Run workflow" button, so this Cloudflare Worker presses it
// once an hour. GitHub's own timer stays on as a backup.
//
// This file lives in the repository so it has a history. The copy that runs is
// the one pasted into the Cloudflare dashboard; see docs/CLOUDFLARE-TIMER.md.
// It needs one secret, GITHUB_TOKEN: a GitHub key limited to this one
// repository that can only start and read workflow runs.

const REPO = "petedilworth/leaside-tracker";
const WORKFLOW = "live-poll.yml";
const BRANCH = "main";

export default {
  // Cloudflare calls this on the schedule set under Settings, Trigger events.
  async scheduled(controller, env, ctx) {
    if (!env.GITHUB_TOKEN) {
      throw new Error("No GITHUB_TOKEN secret. Add it under Settings, Variables and Secrets.");
    }
    const res = await fetch(
      `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
          "Accept": "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "Content-Type": "application/json",
          // GitHub refuses requests without a name; this one says who we are.
          "User-Agent": "leaside-tracker-timer (github.com/petedilworth/leaside-tracker)",
        },
        body: JSON.stringify({ ref: BRANCH }),
      },
    );
    if (res.status !== 204) {
      // A failure here shows as an error in the Worker's cron history and logs.
      // 401 means the key expired or was pasted wrong; 403 or 404 means the key
      // cannot see this repository or lacks the Actions permission.
      const text = await res.text();
      throw new Error(`GitHub answered ${res.status}: ${text.slice(0, 300)}`);
    }
    console.log(`Started ${WORKFLOW} on ${BRANCH}.`);
  },

  // Visiting the Worker's web address does nothing, so nobody can start runs by
  // finding it.
  async fetch() {
    return new Response(
      "This Worker starts the Leaside Tracker's police calls check once an hour.\n" +
        "Visiting this page does nothing.\n",
      { headers: { "content-type": "text/plain; charset=utf-8" } },
    );
  },
};
