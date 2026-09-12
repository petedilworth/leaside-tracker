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

        # Areas are toggles, not a single choice: turn Leaside off, the rest stay on.
        before = visible()
        leaside = pg.locator('.chip[data-area="leaside"]')
        leaside.click()
        assert visible() < before
        assert leaside.get_attribute("aria-pressed") == "false"

        pg.reload()
        assert pg.locator('.chip[data-area="leaside"]').get_attribute("aria-pressed") == "false", \
            "area choice must be remembered"

        pg.locator("#area-reset").click()
        assert pg.locator('.chip[data-area="leaside"]').get_attribute("aria-pressed") == "true"

        assert unread() == 0, "mark-all must persist"
        assert "ago" in pg.locator("li.item time").first.inner_text()
        assert not errors, errors
        b.close()


def test_every_item_offers_a_way_to_read_more(demo_url):
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_context().new_page()
        pg.goto(demo_url)
        items = pg.locator("li.item")
        for i in range(items.count()):
            row = items.nth(i)
            assert row.locator(".links a").count() >= 1, \
                "every item needs somewhere to click through to"
        # a crime item has coordinates, so it also offers a map
        assert pg.locator('.links a[href*="openstreetmap"]').count() >= 1
        assert pg.locator('.links a:has-text("Read the original")').count() >= 1
        b.close()


def test_long_summaries_clip_with_a_show_more_button(demo_url):
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_context().new_page()
        pg.goto(demo_url)
        assert pg.locator(".sum.clipped").count() == 1, "the long summary should be clipped"
        more = pg.locator("button.more").first
        assert more.count() == 1
        # Hold the element itself: the locator ".sum.clipped" stops matching once expanded.
        sum_el = pg.locator(".sum").first
        clipped_height = sum_el.bounding_box()["height"]

        more.click()
        assert more.inner_text() == "Show less"
        assert pg.locator(".sum.clipped").count() == 0
        assert sum_el.bounding_box()["height"] > clipped_height

        more.click()
        assert more.inner_text() == "Show more"
        assert pg.locator(".sum.clipped").count() == 1
        # short summaries must not sprout a button
        assert pg.locator("button.more").count() < pg.locator(".sum").count()
        b.close()


def test_since_control_reaches_late_arriving_records(demo_url):
    """Collision and crime data is months or years old. It has to be reachable.

    The default window keeps the page readable; the Everything option is how the
    late records are seen at all. The demo carries one 900-day-old collision.
    """
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_context().new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(demo_url)

        def visible():
            return pg.locator("li.item:not([hidden])").count()

        default_view = visible()
        assert int(pg.locator("#view-count").inner_text()) == default_view

        pg.locator('.row[data-group="since"] .chip[data-filter="0"]').click()
        widened = visible()
        assert widened > default_view, "the old collision should appear"
        assert int(pg.locator("#view-count").inner_text()) == widened

        pg.reload()
        assert visible() == widened, "the Since choice must be remembered"

        pg.locator('.row[data-group="since"] .chip[data-filter="120"]').click()
        assert visible() == default_view
        assert not errors, errors
        b.close()
