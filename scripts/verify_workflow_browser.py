#!/usr/bin/env python3
"""Verify the complete coordination journey in real, offline Chromium.

Run after the final ``make all CONFIG=config/climate.yaml`` build, using
``.venv/bin/python scripts/verify_workflow_browser.py``. Requires
``requirements-browser.txt`` and an installed Playwright Chromium browser.

This script starts its own local Streamlit server with AGAP_WORKFLOW_DB pointing
to a temporary database. All writes happen through the visible browser UI;
read-only domain/store calls verify persistence and select feasible demonstration
cases using frozen operational fields only. No real demo database, resident
report history, model, or experiment output is edited. The temporary database is
deleted on exit; screenshots, CSV downloads, server log and report.json remain
under --output-dir. Browser internet requests are blocked and counted.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import csv
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from agap import workflow_store as store
from agap.workflow import replacement_candidate
from agap.workflow_overview import display_alias, filtered_overview, next_case_id, queue_counts
from agap.workflow_presentation import recovery_facts

if __package__:
    from .verify_offline_browser import DESTINATIONS, LOOPBACK, ROOT, at_top, choose, healthy, local_server, navigate_destination, sign_in
else:
    from verify_offline_browser import DESTINATIONS, LOOPBACK, ROOT, at_top, choose, healthy, local_server, navigate_destination, sign_in


TABS = DESTINATIONS
FORBIDDEN_EXPORT_FIELDS = {"y_true", "completion_uniform", "completed", "positive_detected", "outdoor_true"}
TIMEOUT_SECONDS = 45


@contextmanager
def isolated_database():
    """The child server inherits this trusted override; never touch the real DB."""
    original = os.environ.get("AGAP_WORKFLOW_DB")
    with tempfile.TemporaryDirectory(prefix="agap-workflow-browser-") as temporary:
        path = Path(temporary) / "screening_workflow.sqlite3"
        os.environ["AGAP_WORKFLOW_DB"] = str(path)
        try:
            yield path
        finally:
            if original is None:
                os.environ.pop("AGAP_WORKFLOW_DB", None)
            else:
                os.environ["AGAP_WORKFLOW_DB"] = original


def wait_until(page, description, predicate):
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        if page.get_by_test_id("stException").count():
            raise AssertionError(f"Streamlit failed while waiting for {description}: "
                                 + page.get_by_test_id("stException").inner_text())
        page.wait_for_timeout(100)
    raise AssertionError(f"Timed out waiting for {description}.")


def round_record(path):
    return store.active_round(path)


def wait_event(page, path, round_id, resident_id, event_type, after_sequence=0):
    def find():
        return next((event for event in reversed(store.get_events(path, round_id))
                     if event["sequence"] > after_sequence and event["resident_id"] == resident_id
                     and event["event_type"] == event_type), None)

    event = wait_until(page, f"persisted {event_type} activity", find)
    healthy(page)
    return event


def case(path, round_id, resident_id):
    frame = store.worklist(path, round_id)
    return frame.loc[frame.resident_id.eq(resident_id)].iloc[0].to_dict()


def assignment_signature(path, round_id):
    return [(slot["slot_id"], slot["current_resident_id"], slot["facility_id"], slot["municipality"],
             slot["selection_route"], slot["ordering_basis"], slot["status"])
            for slot in store.get_slots(path, round_id)]


def snapshot_digest(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, allow_nan=False).encode()).hexdigest()


def select_stage(page, mode):
    navigate_destination(page, mode)


def worklist_stage(page):
    return page.locator(".st-key-screening_worklist_stage")


def choose_case(page, resident_id):
    """Find the full ID through staff search, then select its short case alias."""
    stage = worklist_stage(page)
    browser = expand(page, "Browse worklist")
    choose(page, "Work queue", "All cases")
    healthy(page)
    choose(page, "Task filter", "All tasks")
    healthy(page)
    search = browser.get_by_role("textbox", name="Search worklist", exact=True)
    search.fill(resident_id)
    search.press("Enter")
    healthy(page)
    control = stage.get_by_role("combobox", name="Round resident", exact=True)
    control.click()
    control.press("ArrowDown")
    alias = display_alias(resident_id)
    page.get_by_role("option", name=re.compile(rf"^{re.escape(alias)}(?: ·|$)")).click()
    expect(stage.get_by_role("heading", name=re.compile(rf"^{re.escape(alias)} ·"))).to_be_visible(timeout=30000)
    healthy(page)
    details = expand(page, "Case details")
    expect(details).to_contain_text(f"Full resident ID: {resident_id}")
    collapse(page, "Case details")
    collapse(page, "Browse worklist")


def expander_open(details):
    return details.evaluate("""host => {
        const element = host.matches('details') ? host : host.querySelector('details');
        return element ? element.open : host.querySelector('summary')?.getAttribute('aria-expanded') === 'true';
    }""")


def set_expander(page, title, opened):
    # Native details stays open during Streamlit's closing animation. Settle a
    # previous toggle/rerender before reading that state, then verify both the
    # final state and content visibility before returning to the next action.
    healthy(page)
    details = page.get_by_test_id("stExpander").filter(has=page.get_by_text(title, exact=True)).filter(visible=True)
    expect(details).to_have_count(1, timeout=30000)
    if expander_open(details) != opened:
        details.locator("summary").click()
    wait_until(page, f"{title} {'open' if opened else 'closed'}", lambda: expander_open(details) == opened)
    content = details.get_by_test_id("stExpanderDetails").first
    if opened:
        expect(content).to_be_visible(timeout=30000)
    else:
        expect(content).not_to_be_visible(timeout=30000)
    healthy(page)
    assert expander_open(details) == opened, f"{title} changed state before its transition settled."
    return details


def expand(page, title):
    return set_expander(page, title, True)


def collapse(page, title):
    return set_expander(page, title, False)


def expect_saved(page, action, queue):
    """A real committed write must acknowledge both the action and its queue."""
    notice = worklist_stage(page).get_by_test_id("stAlert").filter(has_text=action)
    expect(notice).to_be_visible(timeout=30000)
    expect(notice).to_contain_text(f"Now {queue.lower()}.")


def assert_selected(page, resident_id):
    alias = display_alias(resident_id)
    expect(worklist_stage(page).get_by_role("heading", name=re.compile(rf"^{re.escape(alias)} ·"))).to_be_visible(timeout=30000)


def assert_queue_counts(page, frame):
    grid = worklist_stage(page).locator(".agap-queue-counts")
    expect(grid.locator(".agap-queue-count")).to_have_count(5)
    for queue, count in queue_counts(frame).items():
        item = grid.locator(".agap-queue-count").filter(has=page.get_by_text(queue, exact=True))
        expect(item.locator("strong")).to_have_text(f"{count:,}")


def set_worklist_search(page, text):
    browser = expand(page, "Browse worklist")
    search = browser.get_by_role("textbox", name="Search worklist", exact=True)
    search.fill(text)
    search.press("Enter")
    healthy(page)
    return browser


def overview_journey(page, path, record, report):
    """Counts, real row picking, staff dates/owners and explicit progression."""
    round_id = record["round_id"]
    before = assignment_signature(path, round_id)
    frozen = snapshot_digest(record["snapshot"])
    frame = store.worklist(path, round_id)
    assert_queue_counts(page, frame)
    rows = filtered_overview(frame)
    target = str(rows.iloc[1 if len(rows) > 1 else 0].resident_id)
    browser = set_worklist_search(page, "")
    table = browser.locator(".st-key-worklist_case_overview").get_by_test_id("stDataFrame")
    table.scroll_into_view_if_needed()
    canvas = table.locator("canvas").first.bounding_box()
    assert canvas is not None
    row_index = 1 if len(rows) > 1 else 0
    page.mouse.click(canvas["x"] + 18, canvas["y"] + 53 + row_index * 35)
    healthy(page)
    assert_selected(page, target)
    assert table.bounding_box()["height"] <= 390, "The browser case list must remain bounded."
    collapse(page, "Browse worklist")

    assignment = expand(page, "Owner & next action")
    assignment.get_by_role("textbox", name="Responsible demo staff member", exact=True).fill("Browser QA coordinator")
    assignment.get_by_role("textbox", name="Next action", exact=True).fill("Call for the fictional screening visit")
    assignment.get_by_role("button", name="Save owner & next action", exact=True).click()
    assigned = wait_event(page, path, round_id, target, "assignment")
    assert assigned["payload"]["owner"] == "Browser QA coordinator"
    assert assigned["payload"]["due_on"]
    assert_selected(page, target)
    expect_saved(page, "Owner and task details saved", "Needs contact")

    browser = set_worklist_search(page, "Browser QA coordinator")
    expect(browser).to_contain_text("1 matching cases")
    assert_selected(page, target)
    set_worklist_search(page, "")
    choose(page, "Task filter", "Due today")
    healthy(page)
    expect(browser).to_contain_text("1 matching cases")
    assert_selected(page, target)
    choose(page, "Task filter", "Overdue")
    healthy(page)
    expect(browser).to_contain_text("No cases match these worklist filters")
    assert_selected(page, target)
    expect(worklist_stage(page)).to_contain_text("outside your current filters")
    expect(worklist_stage(page).get_by_role("button", name="Open next case", exact=True)).to_be_disabled()

    choose(page, "Task filter", "Unassigned")
    healthy(page)
    remaining = store.worklist(path, round_id)
    expected = filtered_overview(remaining, task_filter="Unassigned")
    expect(browser).to_contain_text(f"{len(expected):,} matching cases")
    assert_selected(page, target)
    next_id = next_case_id(expected, target)
    assert next_id and next_id != target
    worklist_stage(page).get_by_role("button", name="Open next case", exact=True).click()
    healthy(page)
    assert_selected(page, next_id)
    choose(page, "Task filter", "All tasks")
    healthy(page)
    collapse(page, "Browse worklist")
    assert_queue_counts(page, store.worklist(path, round_id))
    assert assignment_signature(path, round_id) == before
    assert snapshot_digest(store.load_round(path, round_id)["snapshot"]) == frozen
    report["worklist_overview"] = dict(status="passed", native_table_case=target,
        assignment_sequence=assigned["sequence"], due_on=assigned["payload"]["due_on"],
        date_filters=["Due today: 1", "Overdue: 0", f"Unassigned: {len(expected)}"],
        owner_search="one matching case", selected_case="retained across filters and save",
        explicit_next_case=next_id, queue_counts=queue_counts(store.worklist(path, round_id)),
        invariant="staff browsing and task assignment preserve approved snapshot and allocation")
    print("Visible queue counts, bounded native case list, search/date filters and explicit next-case passed.", flush=True)


def clinical_journey(page, path, record, report):
    round_id = record["round_id"]
    residents = {row["resident_id"]: row for row in record["snapshot"]["residents"]}
    resident_id = next(slot["current_resident_id"] for slot in store.get_slots(path, round_id)
                       if residents[slot["current_resident_id"]].get("age") is not None
                       and residents[slot["current_resident_id"]].get("female") is not None)
    choose_case(page, resident_id)
    progress = worklist_stage(page).locator(".agap-case-progress")
    expect(progress.locator("li")).to_have_count(4)
    expand(page, "Record contact")
    choose(page, "Contact outcome", "Accepted")
    page.get_by_role("button", name="Save contact outcome", exact=True).click()
    contact = wait_event(page, path, round_id, resident_id, "contact")
    assert contact["payload"]["outcome"] == "Accepted"
    assert case(path, round_id, resident_id)["queue"] == "Awaiting screening"
    expect_saved(page, "Contact accepted saved", "Awaiting screening")
    expect(progress).to_contain_text("Accepted")

    expand(page, "Screening visit & results")
    page.get_by_role("button", name="Record specimen collection", exact=True).click()
    specimen = wait_event(page, path, round_id, resident_id, "specimen", contact["sequence"])
    assert case(path, round_id, resident_id)["slot_state"] == "started"
    expect_saved(page, "Specimen collection saved", "Awaiting screening")

    expand(page, "Screening visit & results")
    page.get_by_role("textbox", name="Creatinine (mg/dL; blank = unavailable)", exact=True).fill("0.5")
    page.get_by_role("textbox", name="uACR (mg/g; blank = unavailable)", exact=True).fill("")
    page.get_by_role("textbox", name="Result reference (optional)", exact=True).fill("FICTIONAL-QA-PANEL")
    page.get_by_role("button", name="Save panel results", exact=True).click()
    partial = wait_event(page, path, round_id, resident_id, "result", specimen["sequence"])
    partial_case = case(path, round_id, resident_id)
    assert partial_case["queue"] == "Awaiting screening"
    assert not partial_case["panel_complete"] and partial_case["screening_flag"] is None
    expect_saved(page, "Panel results saved · 1 of 2", "Awaiting screening")
    expect(progress).to_contain_text("1 of 2 recorded · incomplete")
    details = expand(page, "Case details")
    expect(details.get_by_text("Incomplete", exact=False)).to_be_visible()

    expand(page, "Screening visit & results")
    page.get_by_role("textbox", name="uACR (mg/g; blank = unavailable)", exact=True).fill("100")
    page.get_by_role("button", name="Save panel results", exact=True).click()
    flagged = wait_event(page, path, round_id, resident_id, "result", partial["sequence"])
    flagged_case = case(path, round_id, resident_id)
    assert flagged_case["panel_complete"] and flagged_case["screening_flag"]
    assert flagged_case["queue"] == "Needs review / follow-up"
    assert flagged["supersedes_event_id"] == partial["event_id"]
    expect_saved(page, "Panel results saved · 2 of 2", "Needs review / follow-up")
    expect(progress).to_contain_text("Review open")
    expect(worklist_stage(page)).to_contain_text("Review screening flag")

    expand(page, "Review & follow-up")
    choose(page, "Review disposition", "Complete")
    page.get_by_role("textbox", name="Review note", exact=True).fill("Fictional panel reviewed for browser verification.")
    page.get_by_role("button", name="Save review disposition", exact=True).click()
    review = wait_event(page, path, round_id, resident_id, "review", flagged["sequence"])
    pending = case(path, round_id, resident_id)
    # A reviewed abnormal result stays open until staff record that it was explained to the resident.
    assert pending["queue"] == "Needs review / follow-up" and pending["communication_needed"]
    expect_saved(page, "Review completed", "Needs review / follow-up")
    expect(progress).to_contain_text("Review complete")

    expand(page, "Results explained & referral")
    page.get_by_role("button", name="Record results explained", exact=True).click()
    explained = wait_event(page, path, round_id, resident_id, "communication", review["sequence"])
    reviewed_case = case(path, round_id, resident_id)
    assert reviewed_case["queue"] == "Tasks complete" and not reviewed_case["review_open"]
    assert reviewed_case["results_communicated"] and not reviewed_case["communication_needed"]
    assert reviewed_case["screening_flag"]  # historical abnormality is preserved after review
    expect_saved(page, "Results explained to the resident", "Tasks complete")
    expect(progress).to_contain_text("Review complete")
    report["clinical_journey"] = dict(status="passed", resident_id=resident_id,
        sequence=[contact["sequence"], specimen["sequence"], partial["sequence"], flagged["sequence"], review["sequence"],
                  explained["sequence"]],
        partial="normal available component remains incomplete", complete="flag opens review",
        review="explicit review, then results explained, closes task; recorded flag preserved", units="creatinine mg/dL; uACR mg/g")
    print("Contact, specimen, partial/complete result, explicit review and results explained passed.", flush=True)
    return resident_id


def report_amendment(page, path, record, resident_id, report):
    """Preview/apply is browser-driven and remains separate from approval."""
    round_id = record["round_id"]
    before = assignment_signature(path, round_id)
    snapshot_before = snapshot_digest(store.load_round(path, round_id)["snapshot"])
    age = next(person["age"] for person in record["snapshot"]["residents"] if person["resident_id"] == resident_id)
    expand(page, "Recording staff & context")
    worklist_stage(page).get_by_role("button", name="Review / correct questionnaire", exact=True).click()
    expect(page.get_by_role("heading", name="Review or correct questionnaire answers", exact=True)).to_be_visible(timeout=30000)
    page.get_by_text("SMS-style text", exact=True).click()
    page.get_by_role("textbox", name="Example message", exact=True).fill(
        f"AGAP {resident_id} {int(age)} DM:Y HTN:N FAM:U OUT:U PRIOR:U HRS:U DATE:{date.today().isoformat()}")
    page.get_by_role("button", name="Validate & preview report", exact=True).click()
    preview = wait_event(page, path, round_id, resident_id, "report_attempt")
    assert not preview["payload"]["errors"]
    assert not any(event["event_type"] == "report_applied" for event in store.get_events(path, round_id))
    assert assignment_signature(path, round_id) == before
    page.get_by_role("button", name="Apply report & return to workspace", exact=True).click()
    applied = wait_event(page, path, round_id, resident_id, "report_applied", preview["sequence"])
    assert applied["payload"]["resident_id"] == resident_id
    assert assignment_signature(path, round_id) == before
    assert snapshot_digest(store.load_round(path, round_id)["snapshot"]) == snapshot_before
    report["report_amendment"] = dict(status="passed", resident_id=resident_id,
        preview_sequence=preview["sequence"], applied_sequence=applied["sequence"],
        invariant="preview and explicit apply preserve approved snapshot and assignments")
    select_stage(page, "Worklist")
    choose_case(page, resident_id)
    print("Report preview/application saved separately from approved assignments.", flush=True)


def donor_with_replacement(path, record, exclude):
    """Choose a feasible donor solely from frozen operational data."""
    slots, events = store.get_slots(path, record["round_id"]), store.get_events(path, record["round_id"])
    for slot in slots:
        if slot["status"] != "reserved" or slot["current_resident_id"] == exclude:
            continue
        hypothetical = copy.deepcopy(slots)
        simulated_release = next(item for item in hypothetical if item["slot_id"] == slot["slot_id"])
        simulated_release.update(status="released", current_resident_id=None)
        proposal = replacement_candidate(record["snapshot"], hypothetical, events, slot["slot_id"])
        if proposal is not None:
            return slot, proposal
    raise AssertionError("This approved run has no unused slot with a feasible same-context replacement.")


def recovery_journey(page, path, record, clinical_resident, report):
    round_id = record["round_id"]
    donor, expected = donor_with_replacement(path, record, clinical_resident)
    before = {row[0]: row for row in assignment_signature(path, round_id)}
    resident_id, slot_id = donor["current_resident_id"], donor["slot_id"]
    choose_case(page, resident_id)
    expand(page, "Record contact")
    choose(page, "Contact outcome", "Declined")
    page.get_by_role("button", name="Save contact outcome", exact=True).click()
    declined = wait_event(page, path, round_id, resident_id, "contact")
    assert declined["payload"]["outcome"] == "Declined"
    proposal = store.propose_replacement(path, round_id, slot_id)
    assert proposal["resident_id"] == expected["resident_id"]
    assert proposal["facility_id"] == donor["facility_id"] and proposal["municipality"] == donor["municipality"]
    assert proposal["selection_route"] == donor["selection_route"]
    assert proposal["ordering_basis"] == donor["ordering_basis"]
    assert proposal["distance_km"] <= record["snapshot"]["settings"]["max_distance_km"]
    recovery = expand(page, "Recover this released slot")
    comparison = recovery.locator(".agap-recovery-comparison")
    expect(comparison).to_be_visible()
    expect(comparison).to_contain_text(display_alias(resident_id))
    expect(comparison).to_contain_text(display_alias(proposal["resident_id"]))
    expect(comparison).to_contain_text(donor["facility_id"])
    expect(comparison).to_contain_text(donor["municipality"])
    facts = recovery_facts(record["snapshot"], case(path, round_id, resident_id), proposal,
                           store.get_slots(path, round_id), store.worklist(path, round_id))
    assert facts["eligible"]
    checks = recovery.locator(".agap-recovery-checks li")
    expect(checks).to_have_count(len(facts["checks"]))
    for index, (label, passed) in enumerate(facts["checks"]):
        assert passed
        expect(checks.nth(index)).to_contain_text(f"Pass {label}")
    expect(recovery).to_contain_text(f"{facts['round_occupied']:,}/{facts['budget']:,} → "
                                     f"{facts['round_occupied'] + 1:,}/{facts['budget']:,}")
    recovery.get_by_role("button", name="Assign replacement", exact=True).click()
    assigned = wait_event(page, path, round_id, proposal["resident_id"], "replacement", declined["sequence"])
    after = {row[0]: row for row in assignment_signature(path, round_id)}
    assert len(after) == len(before)
    assert [key for key in before if before[key] != after[key]] == [slot_id]
    assert after[slot_id][1] == proposal["resident_id"] and after[slot_id][-1] == "reserved"
    assert after[slot_id][2:6] == before[slot_id][2:6]
    assert not case(path, round_id, resident_id)["is_current"]
    assert case(path, round_id, proposal["resident_id"])["queue"] == "Needs contact"
    assert_selected(page, resident_id)
    worklist_stage(page).get_by_role("button", name="Open replacement case", exact=True).click()
    healthy(page)
    assert_selected(page, proposal["resident_id"])
    report["recovery"] = dict(status="passed", slot_id=slot_id, donor=resident_id,
        replacement=proposal["resident_id"], facility_id=donor["facility_id"], municipality=donor["municipality"],
        selection_route=donor["selection_route"], ordering_basis=donor["ordering_basis"],
        distance_km=proposal["distance_km"], sequence=assigned["sequence"],
        visible_checks=[label for label, _ in facts["checks"]],
        occupied_before=facts["round_occupied"], occupied_after=facts["round_occupied"] + 1,
        handoff="saved donor remains visible until explicit Open replacement case",
        invariant="one released slot reused; all other assignments unchanged")
    choose_case(page, proposal["resident_id"])
    print("Explicit decline and same-context frozen-order slot recovery passed.", flush=True)
    return proposal["resident_id"]


def draft_invariance(page, path, record, report):
    before = assignment_signature(path, record["round_id"])
    frozen = snapshot_digest(store.load_round(path, record["round_id"])["snapshot"])
    select_stage(page, "Plan")
    page.locator(".st-key-workspace_tools").get_by_role("tab", name="Plan settings", exact=True).click()
    model = page.get_by_role("combobox", name="Planning model", exact=True)
    switched = model.is_enabled()
    if switched:
        choose(page, "Planning model", "Questionnaire + climate")
        healthy(page)
        page.locator(".st-key-workspace_tools").get_by_role("tab", name="Plan settings", exact=True).click()
    slider = page.get_by_test_id("stSlider").filter(has=page.get_by_text("Screening panels · whole cohort", exact=True)).get_by_role("slider")
    if slider.count():
        slider.focus()
        slider.press("ArrowLeft")
        page.get_by_role("button", name="Compare screening plans", exact=True).click()
        healthy(page)
    assert assignment_signature(path, record["round_id"]) == before
    assert snapshot_digest(store.load_round(path, record["round_id"])["snapshot"]) == frozen
    report["draft_invariance"] = dict(status="passed", model_switch=switched,
        invariant="draft model and budget edits preserve approved snapshot, assignments and consumed slots")
    select_stage(page, "Worklist")


def download_csv(page, output, button, filename):
    with page.expect_download() as pending:
        worklist_stage(page).get_by_role("button", name=button, exact=True).click()
    target = output / filename
    pending.value.save_as(target)
    with target.open(newline="") as source:
        reader = csv.DictReader(source)
        columns, rows = list(reader.fieldnames or []), list(reader)
    assert rows, f"{button} exported no rows."
    assert not FORBIDDEN_EXPORT_FIELDS.intersection(columns)
    assert not any(column.startswith("research_") for column in columns)
    text = target.read_text()
    assert not any(field in text for field in ("completion_uniform", "y_true", "positive_detected", "research_"))
    return columns, rows


def verify_exports(page, path, record, output, report):
    expand(page, "Approved round downloads")
    _, cases = download_csv(page, output, "Download approved round worklist", "approved-worklist.csv")
    _, events = download_csv(page, output, "Download activity history", "activity-history.csv")
    expected_cases = store.worklist(path, record["round_id"])
    assert len(cases) == len(expected_cases)
    assert {row["resident_id"] for row in cases} == set(expected_cases.resident_id)
    assert len(events) == len(store.get_events(path, record["round_id"]))
    for rows in (cases, events):
        assert {row["round_id"] for row in rows} == {record["round_id"]}
        assert {row["run_id"] for row in rows} == {record["run_id"]}
        assert all("Synthetic" in row["data_status"] for row in rows)
    report["exports"] = dict(status="passed", worklist_rows=len(cases), activity_rows=len(events),
        files=["approved-worklist.csv", "activity-history.csv"], labels="round, run and synthetic-data identifiers",
        hidden_outcomes="absent")


def contact_action_reachability(page, stage, height):
    """Readable forms may scroll; the primary action must remain easy to reach."""
    button = stage.get_by_role("button", name="Save contact outcome", exact=True)
    before = button.bounding_box()
    assert before is not None and before["height"] >= 40
    needed = max(0, before["y"] + before["height"] + 16 - height)
    assert needed <= height, f"The primary contact action requires more than one viewport of scrolling: {before}"
    button.scroll_into_view_if_needed()
    after = button.bounding_box()
    assert after is not None and after["y"] >= 40 and after["y"] + after["height"] <= height
    assert button.evaluate("""el => {
        const box = el.getBoundingClientRect();
        const hit = document.elementFromPoint(box.x + box.width/2, box.y + box.height/2);
        return hit === el || el.contains(hit);
    }"""), "The primary contact action is covered by another element."
    return dict(minimum_scroll_to_action=needed, primary_action_after_scroll=after)


def shell_spacing(page):
    brand = page.locator(".agap-brand").bounding_box()
    subtitle = page.locator(".agap-disclaimer").bounding_box()  # the always-visible line under the header
    assert brand is not None and subtitle is not None
    gap = subtitle["y"] - brand["y"] - brand["height"]
    assert gap >= 8, f"The disclaimer crowds or overlaps the header: {gap}px"
    return gap


def responsive_screenshots(page, path, record, output, report):
    stage = worklist_stage(page)
    for width, height in ((1440, 900), (1280, 800), (768, 1024), (390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        at_top(page)
        healthy(page)
        expect(stage.get_by_role("heading", name="Approved round worklist", exact=True)).to_be_visible()
        expect(stage.get_by_role("combobox", name="Round resident", exact=True)).to_be_visible()
        assert_queue_counts(page, store.worklist(path, record["round_id"]))
        overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth + 2")
        if overflow:
            raise AssertionError(f"The worklist overflows horizontally at {width}×{height}.")
        heading = stage.get_by_role("heading", name="Approved round worklist", exact=True).bounding_box()
        queue = stage.get_by_role("combobox", name="Round resident", exact=True).bounding_box()
        action = stage.get_by_role("button", name="Save contact outcome", exact=True).bounding_box()
        geometry = dict(heading=heading, case_selector=queue,
                        counts=stage.locator(".agap-queue-counts").bounding_box(), primary_action=action,
                        header_subtitle_gap=shell_spacing(page),
                        primary_action_above_fold=bool(action and 0 <= action["y"]
                                                       and action["y"] + action["height"] <= height))
        assert heading is not None and 0 <= heading["y"] < height
        filename = f"worklist-{width}x{height}.png"
        page.screenshot(path=str(output / filename))
        geometry.update(contact_action_reachability(page, stage, height))
        report["screenshots"].append(dict(file=filename, viewport=[width, height], geometry=geometry))
        if width <= 768:
            page.screenshot(path=str(output / f"worklist-action-{width}x{height}.png"))
    page.set_viewport_size({"width": 1440, "height": 900})
    at_top(page)


def capture_entry_phone(page, output, report):
    """Expose the initial phone action geometry before running the longer journey."""
    page.set_viewport_size({"width": 390, "height": 844})
    at_top(page)
    healthy(page)
    stage = worklist_stage(page)
    heading = stage.get_by_role("heading", name="Approved round worklist", exact=True).bounding_box()
    queue = stage.get_by_role("combobox", name="Round resident", exact=True).bounding_box()
    action = stage.get_by_role("button", name="Save contact outcome", exact=True).bounding_box()
    report["entry_phone"] = dict(viewport=[390, 844], heading=heading, case_selector=queue,
                                 counts=stage.locator(".agap-queue-counts").bounding_box(), primary_action=action,
                                 header_subtitle_gap=shell_spacing(page),
                                 primary_action_above_fold=bool(action and 0 <= action["y"]
                                                                and action["y"] + action["height"] <= 844))
    page.screenshot(path=str(output / "worklist-entry-390x844.png"))
    report["entry_phone"].update(contact_action_reachability(page, stage, 844))
    page.screenshot(path=str(output / "worklist-entry-action-390x844.png"))
    (output / "entry-phone.json").write_text(json.dumps(report["entry_phone"], indent=2))
    print("Initial phone worklist captured in worklist-entry-390x844.png.", flush=True)
    page.set_viewport_size({"width": 1440, "height": 900})
    at_top(page)
    healthy(page)


def phone_case_navigation(page, path, record, resident_id, output, report):
    """The compact destination selector preserves the saved case and worklist."""
    before = assignment_signature(path, record["round_id"])
    event_count = len(store.get_events(path, record["round_id"]))
    page.set_viewport_size({"width": 390, "height": 844})
    at_top(page)
    healthy(page)
    selector = page.get_by_role("combobox", name="Page", exact=True)
    expect(selector).to_be_visible()
    for destination in [*TABS[1:], TABS[0]]:  # ends on Worklist
        at_top(page)
        navigate_destination(page, destination)
        expect(selector).to_have_value(destination)
        if destination == "Resident report":
            expect(page.get_by_role("heading", name="Review or correct questionnaire answers", exact=True)).to_be_visible()
        elif destination == "Resident weather":
            expect(page.locator(".st-key-weather_workspace")).to_be_visible()
        elif destination == "Evaluate":
            expect(page.locator(".st-key-evaluate_area")).to_be_visible()
        elif destination == "Data":
            expect(page.get_by_role("heading", name="Clinic verification", exact=True)).to_be_visible()
        elif destination == "Plan":
            expect(page.locator(".st-key-screening_plan_stage")).to_be_visible()
        else:
            expect(worklist_stage(page)).to_be_visible()
            assert_selected(page, resident_id)
        if page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"):
            raise AssertionError(f"Phone destination {destination} overflows horizontally.")
    assert assignment_signature(path, record["round_id"]) == before
    assert len(store.get_events(path, record["round_id"])) == event_count
    at_top(page)
    page.screenshot(path=str(output / "worklist-phone-page-selector.png"))
    report["phone_case_navigation"] = dict(status="passed", viewport=[390, 844], destinations=TABS,
        resident_id=resident_id, invariant="same saved case, unchanged events and assignments after destination round trip")
    page.set_viewport_size({"width": 1440, "height": 900})
    at_top(page)
    healthy(page)


def exercise(page, url, path, output, report):
    page.goto(url, wait_until="domcontentloaded")
    sign_in(page)
    expect(page.get_by_role("heading", name="Community screening workspace", exact=True)).to_be_visible(timeout=45000)
    healthy(page)
    assert [name.strip() for name in page.get_by_role("tablist").first.get_by_role("tab").all_text_contents()] == TABS
    report["top_level_tabs"] = TABS
    print("Initial coordinator workspace rendered with six destinations.", flush=True)
    select_stage(page, "Plan")
    page.locator(".st-key-workspace_tools").get_by_role("tab", name="Plan settings", exact=True).click()
    page.get_by_role("button", name="Compare screening plans", exact=True).click()
    page.locator(".st-key-round_approval").get_by_text("I have reviewed these assignments", exact=False).click()
    expect(page.get_by_role("button", name="Create demo screening round", exact=True)).to_be_enabled(timeout=45000)
    healthy(page)
    page.get_by_role("button", name="Create demo screening round", exact=True).click()
    record = wait_until(page, "new approved round in the isolated database", lambda: round_record(path))
    expect(page.get_by_role("heading", name="Approved round worklist", exact=True)).to_be_visible(timeout=45000)
    healthy(page)
    frozen = snapshot_digest(record["snapshot"])
    slots = store.get_slots(path, record["round_id"])
    assert slots and len(slots) <= record["snapshot"]["settings"]["budget"]
    assert len(store.worklist(path, record["round_id"])) == len(slots)
    assert set(store.worklist(path, record["round_id"]).queue) == {"Needs contact"}
    report["approval"] = dict(status="passed", round_id=record["round_id"], run_id=record["run_id"],
        budget=record["snapshot"]["settings"]["budget"], assignments=len(slots),
        initial_counts="all selected residents need contact; no simulated completions copied")
    print(f"Approved isolated demo round with {len(slots)} invitations.", flush=True)
    capture_entry_phone(page, output, report)
    overview_journey(page, path, record, report)
    resident_id = clinical_journey(page, path, record, report)
    report_amendment(page, path, record, resident_id, report)
    replacement_id = recovery_journey(page, path, record, resident_id, report)
    draft_invariance(page, path, record, report)
    assert snapshot_digest(store.load_round(path, record["round_id"])["snapshot"]) == frozen

    persisted = assignment_signature(path, record["round_id"])
    page.reload(wait_until="domcontentloaded")
    sign_in(page)  # a reload starts a new session at the simulated sign-in
    expect(page.get_by_role("heading", name="Approved round worklist", exact=True)).to_be_visible(timeout=45000)
    healthy(page)
    assert assignment_signature(path, record["round_id"]) == persisted
    assert case(path, record["round_id"], resident_id)["queue"] == "Tasks complete"
    choose_case(page, replacement_id)
    assert len([event for event in store.get_events(path, record["round_id"])
                if event["event_type"] == "report_applied"]) == 1
    report["reload_persistence"] = dict(status="passed", round_id=record["round_id"],
        clinical_case="Tasks complete", replacement_case="Needs contact", applied_report="restored")
    verify_exports(page, path, record, output, report)
    responsive_screenshots(page, path, record, output, report)
    phone_case_navigation(page, path, record, replacement_id, output, report)
    report["recorded_events"] = [{key: event[key] for key in ("sequence", "event_type", "resident_id")}
                                 for event in store.get_events(path, record["round_id"])]
    print("Reload, draft invariance, operational exports and four viewport captures passed.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/climate.yaml")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/browser-verification/workflow")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = dict(status="failed", database="isolated temporary database; deleted after verification",
                  external_requests=[], page_errors=[], console_errors=[], map_asset_responses=[], screenshots=[])
    started = time.monotonic()
    try:
        with isolated_database() as path, local_server(None, args.config, output) as url, sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            report["chromium"] = browser.version
            context = browser.new_context(viewport={"width": 1440, "height": 900}, service_workers="block", accept_downloads=True)

            def route_request(route):
                parsed = urlparse(route.request.url)
                if parsed.scheme in {"data", "blob"} or parsed.hostname in LOOPBACK:
                    route.continue_()
                else:
                    report["external_requests"].append(route.request.url)
                    route.abort()

            context.route("**/*", route_request)
            page = context.new_page()
            page.set_default_timeout(15000)
            page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
            page.on("console", lambda message: report["console_errors"].append(message.text[:500])
                    if message.type == "error" else None)
            page.on("response", lambda response: report["map_asset_responses"].append(
                dict(path=urlparse(response.url).path, status=response.status)) if "/app/static/maps/" in response.url else None)
            try:
                exercise(page, url, path, output, report)
                failed_assets = [item for item in report["map_asset_responses"] if item["status"] >= 400]
                if report["external_requests"] or report["page_errors"] or report["console_errors"] or failed_assets:
                    raise AssertionError("External requests or browser/map asset errors occurred; inspect report.json.")
                healthy(page)
                report["status"] = "passed"
            finally:
                if report["status"] != "passed":
                    try:
                        report["visible_error_context"] = page.locator("body").inner_text()[-7000:]
                        page.screenshot(path=str(output / "failure.png"), full_page=True)
                    except Exception as diagnostic_error:
                        report["diagnostic_error"] = str(diagnostic_error)
                browser.close()
    except Exception as error:
        report["error"] = str(error)
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        (output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(dict(status=report["status"], output=str(output), external_requests=len(report["external_requests"]),
                         page_errors=len(report["page_errors"]), error=report.get("error"))))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
