"""Drive the rendered page in a real browser. Skipped when no Chromium is available.

The page's reading features live in JavaScript, which the other tests cannot reach.
This one clicks through them like a person would and checks read state survives
a reload. It runs against the demo page so it needs no network.
"""
import pathlib
import shutil
import subprocess
import sys

import pytest

CANDIDATES = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    shutil.which("chromium"), shutil.which("chromium-browser"),
    shutil.which("google-chrome"), shutil.which("chrome"),
]
CHROME = next((c for c in CANDIDATES if c and pathlib.Path(c).exists()), None)
playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.skipif(CHROME is None, reason="no Chromium found")


@pytest.fixture(scope="module")
def demo_url():
    subprocess.run([sys.executable, "-m", "leaside.cli", "demo"], check=True,
                   capture_output=True)
    return "file://" + str(pathlib.Path("site/demo.html").resolve())


def test_read_state_and_filters_work_like_a_person_expects(demo_url):
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_context().new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(demo_url)

        def unread():
            return int(pg.locator("#unread-count").inner_text())

        def visible():
            return pg.locator("li.item:not([hidden])").count()

        assert unread() == 5 and visible() == 5

        pg.locator("li.item .done").first.click()
        assert unread() == 4 and visible() == 4, "ticked item should leave the unread view"

        pg.reload()
        assert unread() == 4, "read state must survive a reload"

        pg.locator("#mark-all").click()
        assert unread() == 0 and visible() == 0
        assert pg.locator("#mark-all").is_hidden()
        assert pg.locator("h2.day:not([hidden])").count() == 0, "empty day headings hide"

        pg.locator('.row[data-group="read"] .chip[data-filter="all"]').click()
        assert visible() == 5 and pg.locator("h2.day:not([hidden])").count() == 5

        pg.locator('.row[data-group="area"] .chip[data-filter="leaside"]').click()
        assert visible() == 4

        pg.reload()
        assert unread() == 0, "mark-all must persist"
        assert "ago" in pg.locator("li.item time").first.inner_text()
        assert not errors, errors
        b.close()
