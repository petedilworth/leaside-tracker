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


def shown_count(pg) -> int:
    """How many items a person can actually see.

    Counting `li.item:not([hidden])` only checks the attribute. A CSS rule once
    kept every filtered item on screen while that count said they were gone, and
    only a screenshot caught it.
    """
    return pg.evaluate(
        "() => Array.from(document.querySelectorAll('li.item'))"
        ".filter(li => li.offsetParent !== null).length"
    )


@pytest.fixture(scope="module")
def demo_url():
    subprocess.run([sys.executable, "-m", "leaside.cli", "demo"], check=True,
                   capture_output=True)
    return "file://" + str(pathlib.Path("site/demo.html").resolve())


@pytest.fixture(scope="module")
def reader_url(demo_url):
    """The full reader. The front page (demo.html) is the briefing."""
    return demo_url.replace("demo.html", "demo-news.html")


def test_read_state_and_filters_work_like_a_person_expects(reader_url):
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_context().new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(reader_url)

        def unread():
            return int(pg.locator("#unread-count").inner_text())

        def visible():
            return shown_count(pg)

        assert unread() == 5 and visible() == 5
        # The list is drawn from data in the browser, so the item outside the
        # default window is not in the DOM at all until Since is widened.
        assert pg.locator("li.item").count() == 5

        pg.locator("li.item .done").first.click()
        assert unread() == 4 and visible() == 4, "ticked item should leave the unread view"

        pg.reload()
        assert unread() == 4, "read state must survive a reload"

        pg.locator("#mark-all").click()
        assert unread() == 0 and visible() == 0
        assert pg.locator("#mark-all").is_hidden()
        assert pg.evaluate("() => Array.from(document.querySelectorAll('h2.day'))"
                           ".filter(h => h.offsetParent !== null).length") == 0, \
            "empty day headings hide"

        pg.locator('.row[data-group="read"] .chip[data-filter="all"]').click()
        assert visible() == 5
        assert pg.evaluate("() => Array.from(document.querySelectorAll('h2.day'))"
                           ".filter(h => h.offsetParent !== null).length") == 5

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
        # Everything is read, so the unread view draws nothing at all; the rows
        # exist only once Everything is chosen.
        pg.locator('.row[data-group="read"] .chip[data-filter="all"]').click()
        assert "ago" in pg.locator("li.item time").first.inner_text()
        assert not errors, errors
        b.close()


def test_every_item_offers_a_way_to_read_more(reader_url):
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_context().new_page()
        pg.goto(reader_url)
        items = pg.locator("li.item")
        for i in range(items.count()):
            row = items.nth(i)
            assert row.locator(".links a").count() >= 1, \
                "every item needs somewhere to click through to"
        # a crime item has coordinates, so it also offers a map
        assert pg.locator('.links a[href*="openstreetmap"]').count() >= 1
        assert pg.locator('.links a:has-text("Read the original")').count() >= 1
        b.close()


def test_long_summaries_clip_with_a_show_more_button(reader_url):
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_context().new_page()
        pg.goto(reader_url)
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


def test_since_control_reaches_late_arriving_records(reader_url):
    """Collision and crime data is months or years old. It has to be reachable.

    The default window keeps the page readable; the Everything option is how the
    late records are seen at all. The demo carries one 900-day-old collision.
    """
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_context().new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(reader_url)

        def visible():
            return shown_count(pg)

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


def test_since_choice_survives_touching_an_area(reader_url):
    """Toggling an area used to save the view without the Since setting, so
    choosing Everything and then hiding a neighbourhood forgot Everything."""
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_context().new_page()
        pg.goto(reader_url)
        pg.locator('.row[data-group="since"] .chip[data-filter="0"]').click()
        widened = shown_count(pg)
        pg.locator('.chip[data-area="leaside"]').click()
        pg.locator('.chip[data-area="leaside"]').click()
        pg.reload()
        assert shown_count(pg) == widened, "Since must survive an area toggle"
        assert pg.locator('.row[data-group="since"] .chip[data-filter="0"]') \
            .get_attribute("aria-pressed") == "true"
        b.close()


def test_trends_page_hover_layer_works_with_pointer_and_keyboard(demo_url):
    """The crosshair finds the month, the tooltip lists both years, and arrow keys
    do the same for keyboard users. Values are also in the table twin."""
    trends_url = demo_url.replace("demo.html", "demo-trends.html")
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_context().new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(trends_url)

        svg = pg.locator("svg[data-facet]").first
        assert svg.count() == 1, "the demo has a crime record, so one facet must render"
        svg.scroll_into_view_if_needed()   # the shared header pushed the chart below the fold
        box = svg.bounding_box()
        tip = pg.locator("#tip")
        assert tip.is_hidden()

        # pointer: hover the middle of the plot, tooltip appears with both series rows
        pg.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
        assert tip.is_visible()
        assert tip.locator(".row").count() == 2, "one tooltip, every series"
        month = tip.locator("div").first.inner_text()
        assert month in ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        # A 1px vertical <line> has a zero-width box, so Playwright's visibility
        # heuristic calls it hidden even while painted. Check the attribute instead.
        assert svg.locator(".xh").first.get_attribute("hidden") is None, "crosshair shows"

        pg.mouse.move(0, 0)
        assert tip.is_hidden(), "leaving the plot hides it"

        # keyboard: focus and step with arrows
        svg.focus()
        pg.keyboard.press("ArrowRight")
        assert tip.is_visible()
        first = tip.locator("div").first.inner_text()
        pg.keyboard.press("ArrowRight")
        assert tip.locator("div").first.inner_text() != first, "arrow moved the month"

        # the table twin carries the same values without hovering
        pg.locator("details.tbl summary").first.click()
        first_table = pg.locator("details.tbl").first.locator("table tr")
        assert first_table.count() == 13, "header + 12 months, in this facet's table only"

        # the news page links here and this page links back
        assert pg.locator('a[href="index.html"]').count() >= 1   # the brand and the nav both go home
        assert not errors, errors
        b.close()


def test_pages_fit_a_phone_and_show_their_sources(tmp_path, monkeypatch):
    """A long run-together permit description pushed the whole page sideways on
    a phone. And both pages must end with where their data came from."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from leaside import db, render
    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, {"source_id": "city_building_permits", "category": "permit",
                          "title": "Multiple Projects: 147 Rosedale Heights Dr",
                          "summary": "Revision01:" + "REVISE-PERMIT-" * 30, "url": None,
                          "external_id": "p1", "area": "leaside", "published_at": "2026-10-01"})
    db.upsert_item(conn, {"source_id": "tps_reported_crime", "category": "crime",
                          "title": "Assault at X", "url": None, "external_id": "c1",
                          "area": "leaside", "published_at": "2026-05-01",
                          "raw": {"CSI_CATEGORY": "Assault"}})
    conn.commit()
    monkeypatch.setattr(render, "OUT", tmp_path)
    render.run(db_path=tmp_path / "t.db", out_name="index.html")
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        for page in ("index.html", "trends.html"):
            pg = b.new_page(viewport={"width": 390, "height": 800})
            pg.goto((tmp_path / page).as_uri())
            assert pg.evaluate("document.documentElement.scrollWidth") <= 390, page
            sources = pg.locator("#sources")
            assert sources.is_visible(), page
            assert "where this data comes from" in sources.inner_text().lower()
        b.close()


def test_the_police_map_draws_filters_and_explains_a_place(tmp_path, monkeypatch):
    """Runs with no network: the map library ships with the site. Only the
    background tiles fail to load here, which the page tolerates."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from leaside import db, render
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    conn = db.connect(tmp_path / "t.db")
    rows = [("tps_calls_for_service", "police_call", "Theft near BAYVIEW AVE - MILLWOOD RD", 2),
            ("tps_reported_crime", "crime", "Assault", 30),
            ("tps_reported_crime", "crime", "Assault", 900),
            ("tps_traffic_collisions", "collision", "Collision", 40)]
    for i, (sid, cat, title, age) in enumerate(rows):
        db.upsert_item(conn, {"source_id": sid, "category": cat, "title": title, "url": None,
                              "external_id": str(i), "area": "leaside", "lat": 43.708, "lon": -79.364,
                              "published_at": (now - timedelta(days=age)).isoformat(),
                              "raw": {"OFFENCE": title} if cat == "crime" else None})
    conn.commit()
    monkeypatch.setattr(render, "OUT", tmp_path)
    render.run(db_path=tmp_path / "t.db", out_name="index.html")
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1000, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto((tmp_path / "map.html").as_uri())
        pg.wait_for_selector(".leaflet-container")
        assert pg.locator("#nomap").is_hidden()
        assert pg.locator("#summary").inner_text() == "3 records at 1 place, since " + \
            (now - timedelta(days=365)).strftime("%Y-%m-%d") + "."
        row = pg.locator("#places tbody tr").first.inner_text()
        assert "Bayview Ave & Millwood Rd" in row
        assert pg.locator("#since-out").inner_text().endswith("(1 year)")
        pg.locator("#since").fill("11")                           # the last step: everything
        assert pg.locator("#since-out").inner_text().startswith("Everything collected")
        assert pg.locator("#summary").inner_text().startswith("4 records")
        pg.locator("#since").focus()
        pg.keyboard.press("ArrowLeft")                             # the slider works by keyboard
        assert pg.locator("#since-out").inner_text().endswith("(10 years)")
        # Crime types: two assaults recorded; switching assaults off removes both.
        assert [c.inner_text().split()[0] for c in pg.locator("#types .chip").all() if c.is_visible()] \
            == ["Assault", "Select"]
        pg.locator("#types .chip", has_text="Assault").click()
        assert pg.locator("#summary").inner_text().startswith("2 records")
        pg.locator("#layers .chip", has_text="Reported crime").click()
        assert pg.locator("#types").is_hidden()                     # no crime, no crime types
        assert pg.locator("#summary").inner_text().startswith("2 records")
        pg.locator("#places tbody tr button").first.click()
        popup = pg.locator(".leaflet-popup-content")
        popup.wait_for()
        assert "1 collision" in popup.inner_text() and "1 police call" in popup.inner_text()
        assert "Source:" in popup.inner_text()
        assert errors == []
        phone = b.new_page(viewport={"width": 390, "height": 800})
        phone.goto((tmp_path / "map.html").as_uri())
        assert phone.evaluate("document.documentElement.scrollWidth") <= 390
        b.close()
