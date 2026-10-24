#!/usr/bin/env python3
"""Real Chromium smoke test: local rendering, map picks and desktop layout.

Run after ``make all CONFIG=config/climate.yaml``. With no --url this
starts a temporary Streamlit server; --url connects to an existing instance.
Requires requirements-browser.txt and ``python -m playwright install chromium``.
All browser internet requests are blocked AND counted, including failed attempts.
Desktop and responsive journeys run sequentially in fresh Chromium processes.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
DESTINATIONS = ["Worklist", "Plan", "Resident report", "Resident weather", "Evaluate", "Data"]


@contextmanager
def isolated_workflow_database(enabled=True):
    if not enabled:
        yield
        return
    previous = os.environ.get("AGAP_WORKFLOW_DB")
    with tempfile.TemporaryDirectory(prefix="agap-planner-browser-") as folder:
        os.environ["AGAP_WORKFLOW_DB"] = str(Path(folder) / "workflow.sqlite3")
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("AGAP_WORKFLOW_DB", None)
            else:
                os.environ["AGAP_WORKFLOW_DB"] = previous


@contextmanager
def local_server(url, config, output):
    if url:
        if urlparse(url).hostname not in LOOPBACK:
            raise ValueError("This verification script only connects to loopback servers.")
        yield url
        return
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    command = [sys.executable, "-m", "streamlit", "run", "app/main.py", "--server.headless=true",
               "--server.address=127.0.0.1", f"--server.port={port}", "--browser.gatherUsageStats=false",
               "--", "--config", config]
    with (output / "server.log").open("w") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Streamlit exited; inspect server.log.")
                try:
                    with urlopen(url + "/_stcore/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.2)
            else:
                raise TimeoutError("The local Streamlit server did not become healthy.")
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def selectbox(page, label):
    return page.get_by_test_id("stSelectbox").filter(has=page.get_by_text(label, exact=True))


def choose(page, label, option):
    if label == "Municipality":
        page.get_by_role("tab", name="Residents", exact=True).click()
    control = page.get_by_role("combobox", name=label, exact=True)
    control.click()
    control.press("ArrowDown")
    page.get_by_role("option", name=option, exact=True).click()


def sign_in(page, role="Health worker (RHU)"):
    """Pass the simulated sign-in screen; the role only selects a demo view."""
    expect(page.get_by_role("heading", name="Community screening workspace", exact=True)).to_be_visible(timeout=45000)
    expect(page.locator(".agap-disclaimer")).to_be_visible(timeout=45000)
    page.get_by_role("button", name=f"Sign in as {role}", exact=True).click()
    expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_attached(timeout=45000)
    healthy(page)


def navigate_destination(page, destination):
    """Use the visible destination control at the actual browser width."""
    if destination not in DESTINATIONS:
        raise ValueError(f"Unknown workspace destination: {destination}")
    compact = page.get_by_role("combobox", name="Page", exact=True)
    if compact.count() and compact.is_visible():
        choose(page, "Page", destination)
    else:
        page.get_by_role("tab", name=destination, exact=True).click()
    healthy(page)


def pick_resident(page, row_index=0, force=False):
    card = page.locator(".st-key-resident_decision")
    existing = re.search(r"SYN-[A-Za-z0-9-]+", card.inner_text())
    if not existing or force:
        page.get_by_role("tab", name="Residents", exact=True).click()
        table = page.locator(".st-key-community_workspace").get_by_test_id("stDataFrame")
        table.scroll_into_view_if_needed()
        canvas = table.locator("canvas").first.bounding_box()
        # Native dataframe row-selection checkbox, first row below its header.
        page.mouse.click(canvas["x"] + 18, canvas["y"] + 53 + row_index * 35)
        if force and existing:
            expect(card).not_to_contain_text(existing.group(0), timeout=30000)
        expect(card).to_contain_text(re.compile(r"SYN-[A-Za-z0-9-]+"), timeout=30000)
    page.get_by_role("tab", name="Decision", exact=True).click()
    return re.search(r"SYN-[A-Za-z0-9-]+", card.inner_text()).group(0)


def healthy(page):
    expect(page.get_by_role("button", name="Stop", exact=True)).not_to_be_visible(timeout=45000)
    expect(page.locator('[data-stale="true"]:visible')).to_have_count(0, timeout=45000)
    # Streamlit delays its busy indicator. A fast SQLite commit or callback can
    # happen before it appears, so an instant "not visible" check is not idle.
    # Require a quiet interval long enough to include that indicator's debounce.
    page.evaluate("window.__agapIdleSince = null")
    page.wait_for_function("""() => {
        const visible = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
        const busy = [...document.querySelectorAll('button')].some(el => el.textContent.trim() === 'Stop' && visible(el));
        const stale = [...document.querySelectorAll('[data-stale="true"]')].some(visible);
        if (busy || stale) { window.__agapIdleSince = null; return false; }
        const now = performance.now();
        if (window.__agapIdleSince === null) window.__agapIdleSince = now;
        return now - window.__agapIdleSince >= 700;
    }""", timeout=45000)
    expect(page.get_by_test_id("stException")).to_have_count(0)


def at_top(page):
    page.evaluate("""() => {
        window.scrollTo(0, 0);
        document.querySelectorAll('[data-testid="stMain"], [data-testid="stAppViewContainer"]').forEach(el => el.scrollTop = 0);
    }""")
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


def map_sized(page):
    page.wait_for_function("""() => {
        const host = document.querySelector('.st-key-community_map, .st-key-community_street_map');
        const plot = host?.querySelector('.js-plotly-plot, canvas');
        if (!plot || Math.abs(plot.getBoundingClientRect().width - host.getBoundingClientRect().width) >= 5) return false;
        return plot.tagName !== 'CANVAS' || Math.abs(plot.width - plot.getBoundingClientRect().width * devicePixelRatio) < 3;
    }""")
    # A canvas can acquire its CSS size before deck.gl updates the picking
    # viewport. Let ResizeObserver and the following GPU frame finish first.
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


def street_target(chart):
    """Project a public operational centroid; the selection is still a mouse click.

    Read only ID/municipality/location columns, never hidden medical outcomes.
    The flat map uses the standard north-up Web Mercator projection.
    """
    import pandas as pd
    from agap.community_map import community_points, community_street_deck
    directory = Path(json.loads((ROOT / "outputs/latest_run.json").read_text())["path"])
    locations = pd.read_parquet(directory / "deployment_hidden.parquet",
        columns=["resident_id", "municipality", "latitude", "longitude"])
    queue = locations.assign(score=0., invitation_status="Not planned")
    cells = pd.read_parquet(directory / "cells.parquet")
    point = community_points(queue, locations, cells).iloc[0]
    deck = community_street_deck(queue, locations, locations.iloc[:0], "unused", cells=cells)
    view = deck.initial_view_state
    scale = 512 * 2 ** view.zoom
    def project(lon, lat):
        return ((lon+180)/360*scale, (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*scale)
    centre, target = project(view.longitude, view.latitude), project(point.longitude, point.latitude)
    box = chart.locator("canvas").first.bounding_box()
    return dict(x=box["x"]+box["width"]/2+target[0]-centre[0],
                y=box["y"]+box["height"]/2+target[1]-centre[1], community=point.municipality)


def verify_models(page, output, report, resident):
    control = page.get_by_role("combobox", name="Planning model", exact=True)
    if not control.is_enabled():
        report["model_comparison"] = "not available in this context-only profile"
        return
    import csv
    import joblib
    import pandas as pd
    directory = Path(json.loads((ROOT / "outputs/latest_run.json").read_text())["path"])
    card = page.locator(".st-key-resident_decision")
    scores = {}
    for variant, label in (("clinical", "Questionnaire only"), ("climate", "Questionnaire + climate")):
        model = joblib.load(directory / f"model_{variant}.joblib")
        # Only model-visible fields; no hidden health outcomes are read here.
        features = list(model.feature_names_in_)
        frame = pd.read_parquet(directory / "deployment_hidden.parquet", columns=["resident_id", *features])
        expected = model.predict_proba(frame.loc[frame.resident_id.eq(resident), features])[0, 1]
        choose(page, "Planning model", label)
        expect(card).to_contain_text(resident, timeout=30000)
        metric = card.get_by_test_id("stMetric").filter(has=page.get_by_text("This resident's score", exact=True))
        expect(metric.get_by_test_id("stMetricValue")).to_have_text(f"{expected:.1%}", timeout=30000)
        healthy(page)
        scores[variant] = f"{expected:.1%}"
        page.get_by_role("tab", name="Plan settings", exact=True).click()
        with page.expect_download() as download:
            page.get_by_role("button", name="Download whole-plan invitation preview", exact=True).click()
        path = download.value.path()
        rows = list(csv.DictReader(Path(path).read_text().splitlines()))
        if not rows or any(row["model"] != variant or row["budget_panels"] != "500" for row in rows):
            raise AssertionError("The invitation export does not match the chosen model and unchanged budget.")
        if {"y_true", "positive_detected", "completed"} & set(rows[0]):
            raise AssertionError("Hidden health outcomes leaked into the operational export.")
        page.get_by_role("tab", name="Decision", exact=True).click()
        expect(card).to_be_visible(timeout=30000)
        healthy(page)
    navigate_destination(page, "Evaluate")
    page.get_by_role("tab", name="Climate vs questionnaire", exact=True).click()
    heading = page.get_by_role("heading", name="Climate impact on invitations", exact=True)
    expect(heading).to_be_visible(timeout=30000)
    heading.scroll_into_view_if_needed()
    page.screenshot(path=str(output / "model-comparison-1440x900.png"))
    calibration = page.locator(".st-key-model_calibration")
    expect(calibration.locator(".js-plotly-plot")).to_be_visible(timeout=30000)
    healthy(page)
    calibration.screenshot(path=str(output / "model-calibration.png"))
    report["model_comparison"] = dict(status="passed", resident=resident, scores=scores,
                                       exports="both models; same 500-panel budget; no hidden outcomes")
    at_top(page)


def verify_weather_workspace(page, output, report, resident):
    workspace = page.locator(".st-key-weather_workspace")
    card = workspace.locator(".st-key-weather_resident")
    expect(card).to_contain_text(resident)
    chart = workspace.locator(".st-key-screening_weather_timeline .js-plotly-plot")
    expect(chart).to_be_visible(timeout=30000)
    chart.scroll_into_view_if_needed()
    details = chart.evaluate("""gd => {
        const point = gd.calcdata[0][14];
        return {
            traces:gd.data.map((t,i) => ({name:t.name, xaxis:t.xaxis, yaxis:t.yaxis, points:gd.calcdata[i].length})),
            hover:gd.layout.hovermode, panels:gd.layout.hoversubplots,
            target:{x:gd.getBoundingClientRect().x + gd._fullLayout.xaxis._offset + gd._fullLayout.xaxis.c2p(point.x),
                    y:gd.getBoundingClientRect().y + gd._fullLayout.yaxis._offset + gd._fullLayout.yaxis.c2p(point.y)}
        };
    }""")
    if {t["xaxis"] for t in details["traces"]} != {"x"} or any(t["points"] != 30 for t in details["traces"]):
        raise AssertionError("Weather panels must share the same 30 complete local days and x axis.")
    page.mouse.move(details["target"]["x"], details["target"]["y"])
    expect(chart.locator(".hoverlayer")).to_contain_text("Daily rainfall", timeout=15000)
    expect(chart.locator(".hoverlayer")).to_contain_text("Daily maximum")
    page.mouse.move(0, 0)
    for width, height in ((1440, 900), (1280, 800)):
        page.set_viewport_size({"width": width, "height": height})
        at_top(page)
        healthy(page)
        expect(chart).to_be_visible()
        geometry = {"chart": chart.bounding_box(), "decision": card.bounding_box(),
                    "comparison": workspace.locator(".agap-model-shift").bounding_box()}
        if any(box is None or box["y"] >= height for box in geometry.values()):
            raise AssertionError(f"Weather timeline, model consequence and resident decision must be visible together: {geometry}")
        if page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"):
            raise AssertionError("The weather workspace overflows the desktop viewport horizontally.")
        page.screenshot(path=str(output / f"weather-workspace-{width}x{height}.png"))
        # Generous section spacing can put the lower rainfall panel below the
        # initial fold. A normal scroll must expose the complete chart and its
        # adjacent resident handoff together, without compressing either card.
        chart.scroll_into_view_if_needed()
        rain_bottom = chart.evaluate("gd => gd.getBoundingClientRect().y + gd._fullLayout.yaxis2._offset + gd._fullLayout.yaxis2._length")
        action = card.get_by_role("button", name="Show in Plan", exact=True).bounding_box()
        chart_box = chart.bounding_box()
        if chart_box is None or chart_box["y"] < 40 or rain_bottom > height or action is None or action["y"] < 40 or action["y"]+action["height"] > height:
            raise AssertionError(f"The full weather chart and primary handoff must be visible after scrolling: chart={chart_box}, rainfall bottom={rain_bottom}, action={action}")
        geometry["after_scroll"] = dict(chart=chart_box, handoff=action, rainfall_bottom=rain_bottom)
        page.screenshot(path=str(output / f"weather-workspace-details-{width}x{height}.png"))
        report["screenshots"].append(dict(file=f"weather-workspace-{width}x{height}.png", viewport=[width, height], geometry=geometry))
    page.set_viewport_size({"width": 1440, "height": 900})
    at_top(page)
    healthy(page)
    # Use the new weather-page control; it must update the main model and keep
    # the current resident, plan and page instead of creating another scenario.
    workspace.get_by_test_id("stRadio").get_by_text("Questionnaire only", exact=True).click()
    expect(workspace.locator('.agap-model-cell.is-active[data-model="clinical"]')).to_be_visible(timeout=30000)
    expect(card).to_contain_text(resident)
    expect(card.locator(".agap-current-decision")).to_contain_text("Questionnaire only")
    healthy(page)
    workspace.get_by_test_id("stRadio").get_by_text("Questionnaire + climate", exact=True).click()
    expect(workspace.locator('.agap-model-cell.is-active[data-model="climate"]')).to_be_visible(timeout=30000)
    expect(card).to_contain_text(resident)
    healthy(page)
    workspace.get_by_role("button", name="Show in Plan", exact=True).click()
    expect(page.locator(".st-key-resident_decision")).to_be_visible(timeout=30000)
    expect(page.locator(".st-key-resident_decision")).to_contain_text(resident)
    expect(page.get_by_role("combobox", name="Planning model", exact=True)).to_have_value("Questionnaire + climate")
    navigate_destination(page, "Resident weather")
    report["weather_workspace"] = dict(status="passed", resident=resident, timeline=details["traces"],
        hover="temperature and rainfall together", model_switch="synced with planner; resident and plan retained")


def capture(page, output, name, report, resident=False, hex_view=False):
    """Record real viewport geometry, not a CSS/source-based placement guess."""
    for width, height in ((1440, 900), (1280, 800)):
        page.evaluate("() => document.activeElement?.blur()")
        page.set_viewport_size({"width": width, "height": height})
        at_top(page)
        street = not hex_view and page.locator(".st-key-community_street_map").count() > 0
        chart = page.locator(".st-key-community_hex_map" if hex_view else ".st-key-community_street_map" if street else ".st-key-community_map")
        expect(chart).to_be_visible()
        chart.locator("canvas" if hex_view or street else ".js-plotly-plot").first.wait_for()
        # Plotly responds to ResizeObserver; wait for its actual width to settle.
        if not hex_view:
            map_sized(page)
        at_top(page)
        targets = {"map": chart, "tools": page.locator(".st-key-workspace_tools"),
                   "title": page.get_by_role("heading", name="Community screening workspace", exact=True)}
        if resident:
            targets["resident_card"] = page.locator(".st-key-resident_decision")
        geometry = {key: locator.bounding_box() for key, locator in targets.items()}
        for key, box in geometry.items():
            if box is None or box["y"] < 0 or box["y"] >= height:
                raise AssertionError(f"{key} is not visible above the fold at {width}x{height}: {box}")
        box = geometry["map"]
        workspace = page.locator(".st-key-screening_plan_stage").bounding_box()
        if workspace is None or box["height"] < 600 or box["width"] < workspace["width"] * .70 or box["y"] > 360:
            raise AssertionError(f"Map must dominate the desktop workspace, not be a small chart: {box}")
        if not hex_view and not street:
            geography = chart.evaluate("""host => {
                const bounds = [...host.querySelectorAll('.scatterlayer .trace .lines')]
                    .map(el => el.getBoundingClientRect()).filter(box => box.width > 0 && box.height > 0);
                return {x: Math.min(...bounds.map(box => box.x)), y: Math.min(...bounds.map(box => box.y)),
                    width: Math.max(...bounds.map(box => box.right)) - Math.min(...bounds.map(box => box.x)),
                    height: Math.max(...bounds.map(box => box.bottom)) - Math.min(...bounds.map(box => box.y))};
            }""")
            if geography["height"] < 420:
                raise AssertionError(f"The rendered geography must fill the larger canvas: {geography}")
            geometry["geography"] = geography
        report["screenshots"].append(dict(file=f"{name}-{width}x{height}.png", viewport=[width, height], geometry=geometry))
        page.screenshot(path=str(output / f"{name}-{width}x{height}.png"))
        if resident:
            explanation = targets["resident_card"].get_by_text("Why this score?", exact=True)
            explanation.scroll_into_view_if_needed()
            expect(explanation).to_be_in_viewport()
            geometry["explanation_after_scroll"] = explanation.bounding_box()
            page.locator(".st-key-workspace_tools").evaluate("el => el.scrollTop = 0")
            at_top(page)
    page.set_viewport_size({"width": 1440, "height": 900})
    if not hex_view:
        map_sized(page)


def verify_responsive_planner(page, output, report):
    """A phone/tablet starts on tasks and the revealed map still picks correctly."""
    report["responsive_planner"] = []
    report["responsive_attempts"] = []
    chart = page.locator(".st-key-community_street_map")
    tools = page.locator(".st-key-workspace_tools")
    toggle = page.locator(".st-key-workspace_mobile_toggle")
    for width, height in ((768, 1024), (390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        at_top(page)
        expect(toggle).to_be_visible()
        toggle.get_by_text("Tasks", exact=True).click()
        page.get_by_role("tab", name="Residents", exact=True).click()
        healthy(page)
        expect(chart).not_to_be_visible()
        expect(tools).to_be_visible()
        box = tools.bounding_box()
        table = page.locator(".st-key-community_workspace").get_by_test_id("stDataFrame").bounding_box()
        if box is None or box["width"] < width * .90 or box["y"] >= height or table is None:
            raise AssertionError(f"Task-first queue must fit the narrow viewport: {box}, {table}")
        if max(0, table["y"] + 88 - height) > height:
            raise AssertionError(f"The first resident row requires more than one viewport of scrolling: {table}")
        if page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"):
            raise AssertionError("Narrow planning workspace overflows horizontally.")
        page.screenshot(path=str(output / f"planner-tasks-{width}x{height}.png"))
        page.locator(".st-key-community_workspace").get_by_test_id("stDataFrame").scroll_into_view_if_needed()
        visible_table = page.locator(".st-key-community_workspace").get_by_test_id("stDataFrame").bounding_box()
        if visible_table is None or visible_table["y"] + 53 < 40 or visible_table["y"] + 88 > height:
            raise AssertionError(f"The first resident row is not reachable by normal scrolling: {visible_table}")
        page.screenshot(path=str(output / f"planner-queue-{width}x{height}.png"))
        choose(page, "Municipality", "All municipalities")
        toggle.get_by_text("Map", exact=True).click()
        healthy(page)
        expect(chart).to_be_visible()
        expect(tools).not_to_be_visible()
        # The 640px map extends below a phone's first screen. Bring its canvas
        # into view before sending a real pointer event to a community marker.
        chart.scroll_into_view_if_needed()
        # Single-object selection toggles an already selected marker off. Each
        # viewport is a new selection check, so clear the previous viewport's
        # native map selection before clicking that same community again.
        chart.hover(position={"x": 20, "y": 20})
        clear = chart.get_by_role("button", name=re.compile(r"^Clear selection:"), include_hidden=True)
        cleared_native_selection = False
        if clear.count():
            clear.click()
            cleared_native_selection = True
            healthy(page)
            expect(clear).to_have_count(0)
            chart.scroll_into_view_if_needed()
        expect(tools.locator('input[role="combobox"][aria-label="Municipality"]')).to_have_value("All municipalities")
        map_sized(page)
        target = street_target(chart)
        # Save the exact attempted pointer target before touching the canvas so
        # a renderer/GPU crash cannot erase the viewport's diagnostic context.
        attempt = dict(viewport=[width, height], target=target,
                       cleared_native_selection=cleared_native_selection, status="attempting")
        report["responsive_attempts"].append(attempt)
        page.mouse.move(target["x"], target["y"])
        expect(chart.get_by_text(target["community"], exact=False)).to_be_visible(timeout=15000)
        # The revealed deck has resized, but its first GPU picking frame can
        # still be in flight. Follow the same hover-then-click interaction used
        # for the desktop check, and await the selection before switching views.
        page.wait_for_timeout(1500)
        page.mouse.click(target["x"], target["y"])
        # Tasks are deliberately hidden in Map view, including their accessible
        # roles. Its mounted input still receives the real map selection.
        expect(tools.locator('input[role="combobox"][aria-label="Municipality"]')).to_have_value(target["community"], timeout=30000)
        healthy(page)
        toggle.get_by_text("Tasks", exact=True).click()
        expect(page.get_by_role("combobox", name="Municipality", exact=True)).to_have_value(target["community"], timeout=30000)
        report["responsive_planner"].append(dict(viewport=[width, height], task_panel=box, first_row_y=table["y"] + 53,
                                               first_row_after_scroll=visible_table["y"] + 53,
                                               map_pick=target["community"], map_target=target))
        attempt["status"] = "passed"
    page.set_viewport_size({"width":1440, "height":900})
    at_top(page)
    map_sized(page)


def verify_phone_destinations(page, output, report):
    """Every main destination is reachable without a horizontal tab strip."""
    # Community picking deliberately clears the resident selection. Follow a
    # real row before asserting resident-specific report/climate contents.
    resident = pick_resident(page)
    healthy(page)
    page.set_viewport_size({"width": 390, "height": 844})
    at_top(page)
    healthy(page)
    compact = page.get_by_role("combobox", name="Page", exact=True)
    expect(compact).to_be_visible()
    header = page.locator(".st-key-workspace_destinations").get_by_role(
        "tablist", include_hidden=True).first
    expect(header).not_to_be_visible()
    results = []
    for destination in [*(name for name in DESTINATIONS if name != "Plan"), "Plan"]:  # end on the planner
        at_top(page)
        navigate_destination(page, destination)
        expect(compact).to_have_value(destination)
        if destination == "Resident report":
            target = page.get_by_role("heading", name="Review or correct questionnaire answers", exact=True)
        elif destination == "Resident weather":
            target = page.locator(".st-key-weather_workspace")
        elif destination == "Evaluate":
            target = page.locator(".st-key-evaluate_area")
        elif destination == "Data":
            target = page.get_by_role("heading", name="Clinic verification", exact=True)
        elif destination == "Worklist":
            target = page.locator(".st-key-screening_worklist_stage")
        else:
            target = page.locator(".st-key-screening_plan_stage")
        expect(target).to_be_visible(timeout=30000)
        at_top(page)
        if page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"):
            raise AssertionError(f"Phone destination {destination} overflows horizontally.")
        box = compact.bounding_box()
        if box is None or box["x"] < 0 or box["x"] + box["width"] > 392 or not 0 <= box["y"] < 844:
            raise AssertionError(f"The phone Page selector must be reachable without sideways scrolling: {box}")
        filename = "phone-destination-" + re.sub(r"[^a-z]+", "-", destination.lower()).strip("-") + ".png"
        page.screenshot(path=str(output / filename))
        results.append(dict(destination=destination, selector=box, screenshot=filename))
    report["phone_destinations"] = dict(status="passed", viewport=[390, 844], resident_id=resident, destinations=results,
        behavior="visible Page selector; all six destinations; no horizontal tab scrolling")
    page.set_viewport_size({"width": 1440, "height": 900})
    at_top(page)
    healthy(page)


def exercise(page, url, output, report):
    page.goto(url, wait_until="domcontentloaded")
    sign_in(page)
    expect(page.get_by_role("heading", name="Community screening workspace", exact=True)).to_be_visible(timeout=45000)
    chart = page.locator(".st-key-community_street_map")
    expect(chart.locator("canvas").first).to_be_visible(timeout=45000)
    # Tile/glyph requests originate in map workers, so main-page resource timing
    # misses them. Playwright response events cover both workers and the page.
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        files = report["map_asset_responses"]
        if sum("/tiles/" in row["path"] and row["status"] == 200 for row in files) >= 4 and any(
                "/fonts/" in row["path"] and row["status"] == 200 for row in files):
            break
        page.wait_for_timeout(100)
    else:
        raise AssertionError("Local street tiles and label glyphs did not load.")
    expect(chart.locator(".mapboxgl-ctrl-attrib")).to_contain_text("OpenStreetMap", timeout=30000)
    # Glyph decoding/placement and GPU composition follow their network replies.
    page.wait_for_timeout(1500)
    healthy(page)
    capture(page, output, "initial", report)
    print("Initial 2D layout rendered offline.", flush=True)

    point = street_target(chart)
    report["2d_click"] = point
    page.mouse.move(point["x"], point["y"])
    expect(chart.get_by_text(point["community"], exact=False)).to_be_visible(timeout=15000)
    # A click sent the moment the tooltip appears is dropped by the map and never
    # reaches Streamlit; pause as a user would before clicking.
    page.wait_for_timeout(1500)
    page.mouse.click(point["x"], point["y"])
    expect(page.get_by_role("combobox", name="Municipality", exact=True)).to_have_value(point["community"], timeout=30000)
    report["2d_selected_community"] = point["community"]

    chart.locator(".mapboxgl-ctrl-zoom-in").click()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if any("/tiles/10/" in row["path"] and row["status"] == 200 for row in report["map_asset_responses"]):
            break
        page.wait_for_timeout(100)
    else:
        raise AssertionError("The native zoom control did not load more detailed local street tiles.")
    chart.locator(".mapboxgl-ctrl-zoom-out").click()
    report["street_zoom"] = "passed"

    resident = pick_resident(page)
    other = pick_resident(page, row_index=1, force=True)
    if other == resident:
        raise AssertionError("Selecting another native queue row did not change the followed resident.")
    again = pick_resident(page, force=True)
    if again != resident:
        raise AssertionError("Repeated native row selection did not return to the first resident.")
    report["repeated_resident_selection"] = [resident, other, again]
    card = page.locator(".st-key-resident_decision")
    expect(card).to_contain_text(resident, timeout=30000)
    expect(card.get_by_text("Why this score?", exact=True)).to_be_visible()
    healthy(page)
    capture(page, output, "resident", report, resident=True)
    report["resident"] = resident
    page.get_by_role("tab", name="Plan settings", exact=True).click()
    page.get_by_role("button", name="Compare screening plans", exact=True).click()
    expect(page.get_by_text("Current plan:", exact=False)).to_be_visible(timeout=30000)
    healthy(page)
    page.get_by_role("tab", name="Decision", exact=True).click()
    expect(card).to_be_visible(timeout=30000)
    healthy(page)
    capture(page, output, "planned", report, resident=True)
    print("2D community pick, resident decision and plan comparison passed.", flush=True)
    verify_models(page, output, report, resident)

    # Reset the view filter so an actual hex click must visibly change it.
    choose(page, "Municipality", "All municipalities")
    page.get_by_text("3D H3 hex map", exact=True).click()
    deck = page.locator(".st-key-community_hex_map")
    expect(deck.locator("canvas").first).to_be_visible(timeout=30000)
    expect(page.locator(".st-key-community_map")).to_have_count(0)
    healthy(page)
    capture(page, output, "hex-overview", report, hex_view=True)
    deck.scroll_into_view_if_needed()
    box = deck.locator("canvas").first.bounding_box()
    picked = None
    # Deck's canvas has no DOM element per polygon. Probe actual central pixels,
    # then confirm the corresponding native municipality selector changed.
    for fy in (.5, .6, .4, .7, .3, .8, .2):
        for fx in (.5, .6, .4, .7, .3, .8, .2):
            page.mouse.click(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)
            try:
                expect(page.get_by_role("combobox", name="Municipality", exact=True)).not_to_have_value("All municipalities", timeout=600)
                picked = page.get_by_role("combobox", name="Municipality", exact=True).input_value()
                break
            except AssertionError:
                healthy(page)
        if picked:
            break
    if not picked:
        raise AssertionError("No actual 3D H3 column click changed the municipality filter.")
    report["3d_selected_community"] = picked
    healthy(page)
    at_top(page)
    report["hex_canvas_geometry"] = deck.locator("canvas").first.bounding_box()
    page.screenshot(path=str(output / "hex-selected-1440x900.png"))
    capture(page, output, "hex-map", report, hex_view=True)
    # Follow someone in the picked community and verify a view change keeps them.
    resident = pick_resident(page)
    expect(card).to_contain_text(resident, timeout=30000)
    page.get_by_text("2D community map", exact=True).click()
    expect(chart).to_be_visible(timeout=30000)
    expect(page.locator(".st-key-community_hex_map")).to_have_count(0)
    expect(card).to_contain_text(resident)
    report["resident_retained_after_map_toggle"] = resident
    print("3D rendering, actual hex pick and selection retention passed.", flush=True)

    choose(page, "Map background", "Outline map")
    expect(page.locator(".st-key-community_map .js-plotly-plot")).to_be_visible(timeout=30000)
    expect(page.locator(".st-key-community_street_map")).to_have_count(0)
    expect(card).to_contain_text(resident)
    choose(page, "Map background", "Street map")
    expect(chart).to_be_visible(timeout=30000)
    report["outline_fallback"] = "passed"

    for tab in ("Resident report", "Resident weather", "Data", "Evaluate"):
        navigate_destination(page, tab)
        if tab == "Resident weather" and isinstance(report.get("model_comparison"), dict):
            verify_weather_workspace(page, output, report, resident)
        if tab == "Data":
            expect(page.get_by_role("combobox", name="Clinic to verify", exact=True)).to_be_visible(timeout=30000)
            expect(page.get_by_role("textbox", name="Verified latitude", exact=True)).to_have_value("")
            report["clinic_verification"] = "unverified source queue and evidence form rendered"
    page.get_by_role("tab", name="Surveillance", exact=True).click()
    expect(page.locator(".st-key-visibility_gap .js-plotly-plot")).to_be_visible(timeout=30000)
    healthy(page)
    at_top(page)
    page.screenshot(path=str(output / "surveillance-1440x900.png"))
    report["supporting_tabs"] = "passed"


def exercise_responsive(page, url, output, report):
    """Start a clean application session before checking narrow map picking."""
    page.goto(url, wait_until="domcontentloaded")
    sign_in(page)
    expect(page.get_by_role("heading", name="Community screening workspace", exact=True)).to_be_visible(timeout=45000)
    expect(page.locator(".st-key-community_street_map canvas").first).to_be_visible(timeout=45000)
    healthy(page)
    page.get_by_role("tab", name="Plan settings", exact=True).click()
    page.get_by_role("button", name="Compare screening plans", exact=True).click()
    expect(page.get_by_text("Current plan:", exact=False)).to_be_visible(timeout=30000)
    healthy(page)
    verify_responsive_planner(page, output, report)
    verify_phone_destinations(page, output, report)


def _assert_no_browser_errors(report):
    failed_assets = [item for item in report["map_asset_responses"] if item["status"] >= 400]
    if report["external_requests"] or report["page_errors"] or report["console_errors"] or failed_assets:
        raise AssertionError("Browser attempted external requests or encountered JS/map asset errors; inspect report.json.")


def save_report(output, report):
    """Preserve completed phases even if a later browser/session is interrupted."""
    temporary = output / "report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2))
    temporary.replace(output / "report.json")


def run_browser_session(playwright, url, output, report, name, operation):
    """Use a distinct Chromium process and the same offline checks per phase.

    The long desktop sequence creates multiple software-rendered WebGL scenes.
    Closing its process before responsive checks prevents that accumulated GPU
    state from influencing an independent phone/tablet session.
    """
    session = dict(name=name, fresh_chromium_process=True, status="failed")
    report.setdefault("browser_sessions", []).append(session)
    if name == "responsive":
        report["responsive_session"] = session
    save_report(output, report)
    started = time.monotonic()
    browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    session["chromium"] = browser.version
    report.setdefault("chromium", browser.version)
    page = None
    try:
        context = browser.new_context(viewport={"width": 1440, "height": 900}, service_workers="block")

        def route_request(route):
            parsed = urlparse(route.request.url)
            if parsed.scheme in ("data", "blob") or parsed.hostname in LOOPBACK:
                route.continue_()
            else:
                report["external_requests"].append(route.request.url)
                route.abort()

        context.route("**/*", route_request)
        page = context.new_page()
        page.set_default_timeout(15000)
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        page.on("console", lambda message: report["console_errors"].append(message.text[:500]) if message.type == "error" else None)
        page.on("response", lambda response: report["map_asset_responses"].append(
            dict(path=urlparse(response.url).path, status=response.status)) if "/app/static/maps/" in response.url else None)
        operation(page, url, output, report)
        _assert_no_browser_errors(report)
        healthy(page)
        session["status"] = "passed"
    except Exception as error:
        session["error"] = str(error)
        report["failure_session"] = name
        if page is not None:
            try:
                report["layout_debug"] = page.evaluate("""() => [...document.querySelectorAll('*')]
                    .filter(el => el.scrollHeight > el.clientHeight + 100 && el.clientHeight > 50)
                    .map(el => ({tag:el.tagName, testid:el.dataset.testid, className:el.className,
                        scrollTop:el.scrollTop, height:el.clientHeight, scrollHeight:el.scrollHeight})).slice(0,20)""")
                page.screenshot(path=str(output / "failure.png"), full_page=True)
            except Exception as diagnostic_error:
                session["diagnostic_error"] = str(diagnostic_error)
        raise
    finally:
        session["elapsed_seconds"] = round(time.monotonic() - started, 2)
        save_report(output, report)
        if browser.is_connected():
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Existing local Streamlit URL; otherwise starts a temporary server")
    parser.add_argument("--config", default="config/climate.yaml")
    parser.add_argument("--phase", choices=("all", "desktop", "responsive"), default="all",
                        help="Run all checks or one fresh-browser phase for focused debugging")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/browser-verification")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = dict(status="running", phase=args.phase, external_requests=[], page_errors=[], console_errors=[], map_asset_responses=[], screenshots=[])
    save_report(output, report)
    try:
        with isolated_workflow_database(not args.url), local_server(args.url, args.config, output) as url, sync_playwright() as playwright:
            if args.phase in ("all", "desktop"):
                run_browser_session(playwright, url, output, report, "desktop", exercise)
            if args.phase == "all":
                print("Desktop browser closed; starting a fresh Chromium process for responsive planning.", flush=True)
            if args.phase in ("all", "responsive"):
                run_browser_session(playwright, url, output, report, "responsive", exercise_responsive)
            _assert_no_browser_errors(report)
            report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
    finally:
        save_report(output, report)
    print(json.dumps(dict(status=report["status"], external_requests=len(report["external_requests"]),
                         page_errors=len(report["page_errors"]), output=str(output), error=report.get("error"))))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
