"""The Cloudflare timer presses GitHub's "Run workflow" button for the live poll.

The Worker runs in Cloudflare, not here, so these tests load the same file in
Node with GitHub replaced by a stand-in that records what it was sent.
"""
import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / "cloudflare" / "poll-timer.js"

HARNESS = r"""
const src = process.argv[1];
const mod = await import("data:text/javascript;base64," + src);
const worker = mod.default;
const out = {};
async function run(status, env) {
  const sent = [];
  globalThis.fetch = async (url, init) => {
    sent.push({ url, method: init.method, headers: init.headers, body: init.body });
    return new Response(status === 204 ? null : "nope", { status });
  };
  try { await worker.scheduled({}, env, {}); return { ok: true, sent }; }
  catch (e) { return { ok: false, error: String(e), sent }; }
}
out.good = await run(204, { GITHUB_TOKEN: "github_pat_test" });
out.expired = await run(401, { GITHUB_TOKEN: "github_pat_test" });
out.nokey = await run(204, {});
const page = await worker.fetch(new Request("https://example.org/"));
out.page = { status: page.status, text: await page.text() };
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def result():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not installed here")
    src = base64.b64encode(WORKER.read_bytes()).decode()
    done = subprocess.run([node, "--input-type=module", "-e", HARNESS, src],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])   # last line; the Worker logs too


def test_presses_the_button_for_the_live_poll_on_main(result):
    good = result["good"]
    assert good["ok"], good
    [call] = good["sent"]
    workflow = call["url"].rsplit("/workflows/", 1)[1].split("/")[0]
    assert call["url"] == ("https://api.github.com/repos/petedilworth/leaside-tracker"
                           f"/actions/workflows/{workflow}/dispatches")
    assert call["method"] == "POST"
    assert json.loads(call["body"]) == {"ref": "main"}
    assert call["headers"]["Authorization"] == "Bearer github_pat_test"
    assert call["headers"]["User-Agent"]          # GitHub refuses requests without one
    # The workflow it names exists and has the button.
    flow = yaml.safe_load((ROOT / ".github" / "workflows" / workflow).read_text())
    assert "workflow_dispatch" in flow[True]      # YAML reads the key "on" as True


def test_a_refused_key_shows_as_a_failed_run(result):
    assert not result["expired"]["ok"]
    assert "401" in result["expired"]["error"]


def test_a_missing_key_fails_before_calling_github(result):
    assert not result["nokey"]["ok"]
    assert "GITHUB_TOKEN" in result["nokey"]["error"]
    assert result["nokey"]["sent"] == []


def test_visiting_the_web_address_starts_nothing(result):
    assert result["page"]["status"] == 200
    assert "does nothing" in result["page"]["text"]
