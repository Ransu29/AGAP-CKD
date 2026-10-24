"""Operational rounds freeze allocation inputs and derive work only from events."""
from copy import deepcopy
from datetime import datetime, timedelta
import json

import numpy as np
import pandas as pd
import pytest

from agap.config import load_config
from agap.experiment import policy_order
from agap.workflow import (MANILA, build_round_snapshot, normalize_event, normalize_snapshot,
                           project_worklist, replacement_candidate)


@pytest.fixture
def inputs():
    cfg = load_config()
    cfg["allocation"]["budget_tests"] = 2
    frame = pd.DataFrame(dict(
        resident_id=["SYN-A0", "SYN-A1", "SYN-A2", "SYN-A3", "SYN-B0", "SYN-B1", "SYN-A4"],
        municipality=["A", "A", "A", "A", "B", "B", "A"],
        latitude=[14., 14.01, 14.02, 14.5, 14.1, 14.11, 14.015], longitude=121.,
        age=50, female=0, reported=False, dm_report=np.nan, htn_report=np.nan,
        family_report=np.nan, outdoor_report=np.nan, cutoff=pd.Timestamp("2026-01-01"),
        clinical_score=[.9, .8, .7, .99, .95, .5, .6], tie_uniform=np.arange(7) / 10,
        y_true=True, creatinine=4.0, uacr=200., completion_uniform=.01, outdoor_true=True,
        research_interest="interested", research_state="interested", persistent_abnormal=True,
    ))
    facilities = pd.DataFrame(dict(facility_id=["F1", "F2"], latitude=[14., 14.1], longitude=121.,
                                   municipality=["A", "B"], capacity=[2, 2]))
    records = frame[["resident_id", "municipality"]].copy()
    records["invited"] = records.resident_id.isin(["SYN-A0", "SYN-B0"])
    records["reason"] = np.where(records.invited, "risk_ranked", "not invited")
    records["facility_id"] = ["F1", None, None, None, "F2", None, None]
    records["completed"] = True  # never used to populate operational work
    records["y_true"] = True
    settings = dict(budget=2, strategy="Prioritize higher scores", outreach=.2)
    return frame, facilities, records, cfg, settings


@pytest.fixture
def snapshot(inputs):
    frame, facilities, records, cfg, settings = inputs
    return build_round_snapshot(frame, facilities, records, cfg, "original-run", "clinical", settings,
                                manifest=dict(run_id="original-run", source_hash="original-source",
                                              config_hash="original-config", input_checksums={"source.tif": "abc"}))


def append(snapshot, slots, events, kind, payload, rid="SYN-A0"):
    normalized = normalize_event(snapshot, slots, events, rid, kind, payload)
    event = dict(sequence=len(events) + 1, event_id=f"e{len(events) + 1}", resident_id=rid,
                 event_type=kind, payload=normalized, recorded_at="2026-10-21T10:00:00+00:00")
    events.append(event)
    for slot in slots:
        if slot.get("current_resident_id") == rid:
            if kind == "contact" and normalized["outcome"] in {"Declined", "Withdrawn", "Unreachable"}:
                slot.update(status="released", current_resident_id=None, version=slot["version"] + 1)
            elif kind in {"specimen", "result"}:
                slot["status"] = "started"
    return normalized


def test_snapshot_filters_hidden_truth_and_freezes_original_identity(inputs, snapshot):
    before = deepcopy(inputs)
    forbidden = {"y_true", "creatinine", "uacr", "completion_uniform", "outdoor_true", "research_interest",
                 "research_state", "persistent_abnormal", "completed"}
    assert not any(forbidden & set(resident) for resident in snapshot["residents"])
    assert snapshot["provenance"]["source_hash"] == "original-source"
    assert snapshot["provenance"]["config_hash"] == "original-config"
    assert snapshot["provenance"]["input_checksums"] == {"source.tif": "abc"}
    assert json.loads(json.dumps(snapshot, allow_nan=False)) == snapshot
    work = project_worklist(snapshot, snapshot["slots"], [])
    assert set(work.queue) == {"Needs contact"}
    assert not work.panel_complete.any() and work.creatinine.isna().all()
    assert work.resident_id.tolist() == ["SYN-A0", "SYN-B0"]
    pd.testing.assert_frame_equal(inputs[0], before[0])
    inputs[0].loc[:, "clinical_score"] = .1
    inputs[0].loc[:, "y_true"] = False
    inputs[4]["budget"] = 7
    assert snapshot["settings"]["budget"] == 2 and snapshot["residents"][0]["score"] == .9


@pytest.mark.parametrize(("reason", "policy", "route", "basis"), [
    ("risk", "risk_ranked", "priority", "priority"),
    ("risk_ranked", "risk_ranked", "priority", "priority"),
    ("exploration", "risk_ranked", "outreach", "random"),
    ("random", "random", "outreach", "random"),
    ("population_proportional", "population_proportional", "municipality", "random"),
    ("quota shortfall reassigned", "population_proportional", "municipality", "random"),
    ("coverage requirement", "risk_ranked", "municipality", "priority"),
    ("coverage requirement", "random", "municipality", "random"),
    ("coverage requirement", "population_proportional", "municipality", "random"),
])
def test_every_allocator_reason_keeps_exact_route_and_order(inputs, reason, policy, route, basis):
    frame, facilities, records, cfg, settings = inputs
    records.loc[records.invited, "reason"] = reason
    settings.update(policy=policy, strategy="Priority + random outreach", outreach=.2)
    snapshot = build_round_snapshot(frame, facilities, records, cfg, "run", "clinical", settings)
    assert all(slot["selection_reason"] == reason and slot["selection_route"] == route
               and slot["ordering_basis"] == basis for slot in snapshot["slots"])
    expected = policy_order(frame, frame.clinical_score, "random" if basis == "random" else "risk_ranked", 0,
                            cfg["seed"] + 100)
    assert snapshot["orders"][basis] == frame.iloc[expected].resident_id.tolist()


def test_snapshot_rejects_mismatched_or_over_capacity_allocation(inputs, snapshot):
    frame, facilities, records, cfg, settings = inputs
    with pytest.raises(ValueError, match="whole cohort"):
        build_round_snapshot(frame, facilities, records.iloc[:2], cfg, "run", "clinical", settings)
    facilities.loc[facilities.facility_id.eq("F1"), "capacity"] = 0
    with pytest.raises(ValueError, match="capacity"):
        build_round_snapshot(frame, facilities, records, cfg, "run", "clinical", settings)
    bad = deepcopy(snapshot)
    bad["slots"][0]["status"] = "started"
    with pytest.raises(ValueError, match="reserved"):
        normalize_snapshot(bad)
    with pytest.raises(ValueError, match="different run"):
        build_round_snapshot(frame, inputs[1], records, cfg, "run", "clinical", settings,
                             manifest={"run_id": "other"})


@pytest.mark.parametrize("change", [
    lambda value: value["provenance"].update(run_id="different-run"),
    lambda value: value["settings"].update(budget=2.5),
    lambda value: value["settings"]["outcome"].update(egfr_threshold=float("inf")),
    lambda value: value["settings"]["outcome"].update(uacr_threshold=0),
    lambda value: value["facilities"][0].update(capacity=-1),
    lambda value: value["residents"][0]["candidate_distances_km"].update(F1=-1),
    lambda value: value["residents"][1]["candidate_distances_km"].update(F1=None),
    lambda value: value["slots"][0].update(ordering_basis="random"),
])
def test_malformed_snapshots_cannot_enter_persistence(snapshot, change):
    change(snapshot)
    with pytest.raises(ValueError):
        normalize_snapshot(snapshot)


def test_score_changes_require_recomparison_before_approval(inputs):
    frame, facilities, records, cfg, settings = inputs
    records["score"] = frame.clinical_score.to_numpy()
    frame.loc[0, "clinical_score"] = .01
    with pytest.raises(ValueError, match="Compare the screening plan again"):
        build_round_snapshot(frame, facilities, records, cfg, "run", "clinical", settings)


def test_partials_are_unknown_normal_and_abnormal_flags_require_review(snapshot):
    slots, events = deepcopy(snapshot["slots"]), []
    today = datetime.now(MANILA).date().isoformat()
    append(snapshot, slots, events, "contact", {"outcome": "Accepted"})
    first = append(snapshot, slots, events, "result", {"creatinine": .7, "specimen_date": today})
    assert first["screening_flag"] is None and not first["panel_complete"]
    case = project_worklist(snapshot, slots, events).set_index("resident_id").loc["SYN-A0"]
    assert case.queue == "Awaiting screening" and case.egfr > 60
    second = append(snapshot, slots, events, "result", {"uacr": 30, "specimen_date": today})
    assert second["creatinine"] == .7 and second["screening_flag"] is True
    assert second["supersedes_event_id"] == "e2"
    case = project_worklist(snapshot, slots, events).set_index("resident_id").loc["SYN-A0"]
    assert case.queue == "Needs review / follow-up" and case.panel_complete
    # A corrected, normal panel must not silently erase the pending review.
    third = append(snapshot, slots, events, "result", {"uacr": 10, "specimen_date": today})
    assert third["screening_flag"] is False and third["supersedes_event_id"] == "e3"
    assert project_worklist(snapshot, slots, events).set_index("resident_id").loc["SYN-A0"].review_pending
    append(snapshot, slots, events, "review", {"disposition": "Complete", "note": "Reviewed corrected demonstration result"})
    assert project_worklist(snapshot, slots, events).set_index("resident_id").loc["SYN-A0"].queue == "Tasks complete"


def test_partial_abnormal_still_has_missing_component_and_explicit_followup(snapshot):
    slots, events = deepcopy(snapshot["slots"]), []
    today = datetime.now(MANILA).date()
    append(snapshot, slots, events, "result", {"uacr": 30, "specimen_date": today})
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert case.screening_flag and not case.panel_complete and case.review_pending
    with pytest.raises(ValueError, match="Next action"):
        normalize_event(snapshot, slots, events, "SYN-A0", "review", {"disposition": "Follow-up requested"})
    append(snapshot, slots, events, "review", {"disposition": "Follow-up requested", "next_action": "Arrange missing test",
                                              "due_on": today + timedelta(days=3)})
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert case.followup_open and not case.review_pending and case.next_action == "Arrange missing test"
    append(snapshot, slots, events, "followup_complete", {})
    # The reviewed abnormal component still has to be explained to the resident.
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert case.queue == "Needs review / follow-up" and case.next_action == "Explain reviewed results to resident"
    append(snapshot, slots, events, "communication", {"method": "Phone call", "explained_by": "Demo nurse"})
    assert project_worklist(snapshot, slots, events).iloc[0].queue == "Awaiting screening"


@pytest.mark.parametrize(("kind", "later_payload"), [
    ("contact", {"outcome": "Accepted"}),
    ("contact", {"outcome": "Accepted", "next_action": "", "due_on": ""}),
    ("contact", {"outcome": "No answer", "next_action": "Retry contact", "due_on": "2026-11-01"}),
    ("contact", {"outcome": "Retry requested", "next_action": "Retry contact", "due_on": "2026-11-02"}),
    ("specimen", {}),
])
def test_later_contact_or_specimen_preserves_unfinished_followup(snapshot, kind, later_payload):
    slots, events = deepcopy(snapshot["slots"]), []
    today = datetime.now(MANILA).date()
    due = (today + timedelta(days=3)).isoformat()
    append(snapshot, slots, events, "result", {"uacr": 100, "specimen_date": today})
    append(snapshot, slots, events, "review", {"disposition": "Follow-up requested",
        "next_action": "Arrange missing creatinine result", "due_on": due})
    later_payload = {**later_payload, **({"specimen_date": today} if kind == "specimen" else {})}
    append(snapshot, slots, events, kind, later_payload)
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert case.followup_open and case.queue == "Needs review / follow-up"
    assert case.next_action == "Arrange missing creatinine result" and case.due_on == due
    # Staff can intentionally edit the open task or complete it; unrelated
    # contact/specimen activity must not act as an implicit task amendment.
    append(snapshot, slots, events, "assignment", {"owner": "Demo coordinator", "next_action": "Confirm lab appointment",
                                                   "due_on": today + timedelta(days=4)})
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert case.next_action == "Confirm lab appointment"
    assert case.due_on == (today + timedelta(days=4)).isoformat()
    append(snapshot, slots, events, "followup_complete", {})
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert not case.followup_open and case.communication_needed
    append(snapshot, slots, events, "communication", {"method": "In person", "explained_by": "Demo nurse"})
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert case.queue == "Awaiting screening" and case.due_on == ""


def test_normal_panel_completion_closes_generic_queue_instruction(snapshot):
    slots, events = deepcopy(snapshot["slots"]), []
    today = datetime.now(MANILA).date()
    append(snapshot, slots, events, "specimen", {"specimen_date": today})
    append(snapshot, slots, events, "assignment", {"owner": "Demo staff", "next_action": "Finish missing panel",
                                                   "due_on": today + timedelta(days=2)})
    append(snapshot, slots, events, "result", {"creatinine": .8, "uacr": 10, "specimen_date": today})
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert case.queue == "Tasks complete" and case.next_action == "Recorded tasks complete" and case.due_on == ""
    append(snapshot, slots, events, "assignment", {"owner": "Updated demo owner"})
    assert project_worklist(snapshot, slots, events).iloc[0].owner == "Updated demo owner"
    with pytest.raises(ValueError, match="owner changes only"):
        normalize_event(snapshot, slots, events, "SYN-A0", "assignment",
                        {"owner": "Demo staff", "next_action": "Call resident with results", "due_on": today})
    with pytest.raises(ValueError, match="owner changes only"):
        normalize_event(snapshot, slots, events, "SYN-A0", "assignment", {"owner": "Demo staff", "due_on": today})
    with pytest.raises(ValueError, match="New contact activity"):
        normalize_event(snapshot, slots, events, "SYN-A0", "contact",
                        {"outcome": "Retry requested", "next_action": "Retry contact", "due_on": today})


def test_legacy_completed_instructions_are_not_projected_as_unfinished_work(snapshot):
    slots, events = deepcopy(snapshot["slots"]), []
    today = datetime.now(MANILA).date()
    append(snapshot, slots, events, "result", {"creatinine": .8, "uacr": 10, "specimen_date": today})
    # Previously saved events remain append-only; the projection must still
    # give truthful completion counts and avoid displaying an active deadline.
    events.append(dict(sequence=2, event_id="legacy-assignment", event_type="assignment", resident_id="SYN-A0",
                       payload={"owner": "Demo staff", "next_action": "Old generic instruction", "due_on": today.isoformat()}))
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert case.queue == "Tasks complete" and case.next_action == "Recorded tasks complete" and case.due_on == ""
    # A result amendment can explicitly reopen the existing clinical workflow.
    append(snapshot, slots, events, "result", {"uacr": 100, "specimen_date": today})
    assert project_worklist(snapshot, slots, events).iloc[0].queue == "Needs review / follow-up"
    append(snapshot, slots, events, "contact", {"outcome": "Accepted"})


def test_normal_panel_does_not_close_explicit_open_followup(snapshot):
    slots, events = deepcopy(snapshot["slots"]), []
    today = datetime.now(MANILA).date()
    due = (today + timedelta(days=3)).isoformat()
    append(snapshot, slots, events, "result", {"uacr": 100, "specimen_date": today})
    append(snapshot, slots, events, "review", {"disposition": "Follow-up requested",
        "next_action": "Review remaining result", "due_on": due})
    append(snapshot, slots, events, "result", {"creatinine": .8, "uacr": 10, "specimen_date": today})
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert case.queue == "Needs review / follow-up" and case.followup_open
    assert case.next_action == "Review remaining result" and case.due_on == due
    append(snapshot, slots, events, "followup_complete", {})
    assert project_worklist(snapshot, slots, events).iloc[0].queue == "Tasks complete"


def test_completed_contact_restriction_preserves_idempotent_prior_requests(snapshot, tmp_path):
    from agap import workflow_store as store

    database = tmp_path / "coordination.sqlite3"
    record = store.create_round(database, snapshot)
    round_id = record["round_id"]
    accepted = store.record_event(database, round_id, "SYN-A0", "contact", {"outcome": "Accepted"},
                                  request_id="original-contact", expected_version=0)
    store.record_event(database, round_id, "SYN-A0", "result",
                       {"creatinine": .8, "uacr": 10, "specimen_date": datetime.now(MANILA).date().isoformat()})
    saved_version = store.load_round(database, round_id)["version"]
    assert store.record_event(database, round_id, "SYN-A0", "contact", {"outcome": "Accepted"},
                               request_id="original-contact", expected_version=0) == accepted
    assert store.load_round(database, round_id)["version"] == saved_version
    with pytest.raises(ValueError, match="New contact activity"):
        store.record_event(database, round_id, "SYN-A0", "contact", {"outcome": "Accepted"}, request_id="new-contact")
    assert store.load_round(database, round_id)["version"] == saved_version


@pytest.mark.parametrize("payload", [
    {"creatinine": 0}, {"creatinine": -1}, {"creatinine": float("nan")},
    {"creatinine": float("inf")}, {"creatinine": True}, {"uacr": -1},
    {"uacr": float("nan")}, {"creatinine": .8, "creatinine_unit": "umol/L"},
    {"uacr": 10, "uacr_unit": "mg/mmol"}, {},
])
def test_result_validation_rejects_invalid_values_and_unsupported_units(snapshot, payload):
    with pytest.raises(ValueError):
        normalize_event(snapshot, snapshot["slots"], [], "SYN-A0", "result",
                        {"specimen_date": datetime.now(MANILA).date().isoformat(), **payload})


def test_result_dates_missing_inputs_and_revision_validation(snapshot):
    slots, events = deepcopy(snapshot["slots"]), []
    today = datetime.now(MANILA).date()
    with pytest.raises(ValueError, match="future"):
        normalize_event(snapshot, slots, events, "SYN-A0", "result", {"uacr": 0, "specimen_date": today + timedelta(days=1)})
    append(snapshot, slots, events, "result", {"uacr": 0, "specimen_date": today})
    with pytest.raises(ValueError, match="same specimen date"):
        normalize_event(snapshot, slots, events, "SYN-A0", "result", {"uacr": 30, "specimen_date": today - timedelta(days=1)})
    with pytest.raises(ValueError, match="latest saved result"):
        normalize_event(snapshot, slots, events, "SYN-A0", "result",
                        {"uacr": 30, "specimen_date": today, "supersedes_event_id": "stale"})
    missing = deepcopy(snapshot)
    missing["residents"][0]["female"] = None
    normalized = normalize_event(missing, missing["slots"], [], "SYN-A0", "result", {"creatinine": .8, "uacr": 10, "specimen_date": today})
    assert normalized["egfr"] is None and normalized["screening_flag"] is None
    missing_events = []
    append(missing, missing["slots"], missing_events, "result", {"creatinine": .8, "uacr": 10, "specimen_date": today})
    assert project_worklist(missing, missing["slots"], missing_events).iloc[0].queue == "Needs review / follow-up"


def test_recovery_preserves_municipality_facility_limit_and_never_reuses_residents(snapshot):
    slots, events = deepcopy(snapshot["slots"]), []
    with pytest.raises(ValueError, match="explicitly released"):
        replacement_candidate(snapshot, slots, events, slots[0]["slot_id"])
    append(snapshot, slots, events, "contact", {"outcome": "No answer"})
    assert slots[0]["status"] == "reserved"
    append(snapshot, slots, events, "contact", {"outcome": "Declined"})
    proposal = replacement_candidate(snapshot, slots, events, slots[0]["slot_id"])
    # Higher scoring A3 is outside the service-point radius; B0 is a different municipality.
    assert proposal["resident_id"] == "SYN-A1"
    assert proposal["facility_id"] == "F1" and proposal["municipality"] == "A"
    assert proposal["distance_km"] <= 20 and proposal["selection_basis"] == "priority"
    slot = slots[0]
    slot.update(current_resident_id=proposal["resident_id"], status="reserved", version=slot["version"] + 1)
    events.append(dict(sequence=3, event_type="replacement", resident_id="SYN-A1", slot_id=slot["slot_id"], payload=proposal))
    work = project_worklist(snapshot, slots, events).set_index("resident_id")
    assert work.loc["SYN-A0", "queue"] == "Declined / withdrawn"
    assert not work.loc["SYN-A0", "is_current"] and work.loc["SYN-A0", "slot_state"] == "reserved"
    assert not work.loc["SYN-A0", "slot_available_for_replacement"]
    assert work.loc["SYN-A1", "queue"] == "Needs contact"
    append(snapshot, slots, events, "contact", {"outcome": "Declined"}, rid="SYN-A1")
    assert replacement_candidate(snapshot, slots, events, slot["slot_id"])["resident_id"] == "SYN-A2"
    assert project_worklist(snapshot, slots, events).resident_id.nunique() == 3
    history = project_worklist(snapshot, slots, events).set_index("resident_id")
    assert not history.loc["SYN-A0", "slot_available_for_replacement"]
    assert history.loc["SYN-A1", "slot_available_for_replacement"]


@pytest.mark.parametrize(("reason", "policy", "basis"), [
    ("risk", "risk_ranked", "priority"), ("risk_ranked", "risk_ranked", "priority"),
    ("exploration", "risk_ranked", "random"), ("random", "random", "random"),
    ("population_proportional", "population_proportional", "random"),
    ("quota shortfall reassigned", "population_proportional", "random"),
    ("coverage requirement", "risk_ranked", "priority"),
    ("coverage requirement", "random", "random"),
])
def test_recovery_uses_the_frozen_original_route_for_every_reason(inputs, reason, policy, basis):
    frame, facilities, records, cfg, settings = inputs
    records.loc[records.invited, "reason"] = reason
    settings.update(policy=policy, strategy="Priority + random outreach", outreach=.2)
    snapshot = build_round_snapshot(frame, facilities, records, cfg, "run", "clinical", settings)
    slots, events = deepcopy(snapshot["slots"]), []
    append(snapshot, slots, events, "contact", {"outcome": "Declined"})
    expected = next(rid for rid in snapshot["orders"][basis]
                    if rid in {"SYN-A1", "SYN-A2", "SYN-A4"})
    proposal = replacement_candidate(snapshot, slots, events, slots[0]["slot_id"])
    assert proposal["resident_id"] == expected
    assert proposal["ordering_basis"] == basis and proposal["selection_reason"] == reason


def test_recording_sequence_not_backdated_occurrence_controls_current_state(snapshot):
    slots, events = deepcopy(snapshot["slots"]), []
    append(snapshot, slots, events, "contact", {"outcome": "No answer", "due_on": "2026-10-20", "next_action": "Retry contact"})
    append(snapshot, slots, events, "contact", {"outcome": "Accepted"})
    events[0]["occurred_at"] = "2026-10-21T08:00:00Z"
    events[1]["occurred_at"] = "2026-10-20T08:00:00Z"
    case = project_worklist(snapshot, slots, events[::-1]).iloc[0]
    assert case.contact_outcome == "Accepted" and case.queue == "Awaiting screening"
    assert case.next_action == "Record screening visit" and case.due_on == ""


def test_started_slots_cannot_be_released_and_no_replacement_is_explicit(snapshot):
    slots, events = deepcopy(snapshot["slots"]), []
    append(snapshot, slots, events, "specimen", {"specimen_date": datetime.now(MANILA).date()})
    with pytest.raises(ValueError, match="cannot be released"):
        normalize_event(snapshot, slots, events, "SYN-A0", "contact", {"outcome": "Declined"})
    slots[1].update(status="released", current_resident_id=None)
    small = deepcopy(snapshot)
    for resident in small["residents"]:
        if resident["resident_id"] == "SYN-B1":
            resident["candidate_distances_km"]["F2"] = 21.
    assert replacement_candidate(small, slots, events, slots[1]["slot_id"]) is None


def test_unassigned_reports_are_recorded_without_assigning_or_changing_snapshot(snapshot):
    slots, events = deepcopy(snapshot["slots"]), []
    before = deepcopy(snapshot)
    today = datetime.now(MANILA).date().isoformat()
    report = dict(resident_id="SYN-A1", age=50, DM="Y", HTN="N", DATE=today)
    payload = normalize_event(snapshot, slots, events, "SYN-A1", "report_applied", report)
    events.append(dict(sequence=1, event_type="report_applied", resident_id="SYN-A1", payload=payload))
    assert len(project_worklist(snapshot, slots, events)) == 2
    with pytest.raises(ValueError, match="not received an invitation"):
        normalize_event(snapshot, slots, events, "SYN-A1", "contact", {"outcome": "Accepted"})
    append(snapshot, slots, events, "contact", {"outcome": "Declined"})
    proposal = replacement_candidate(snapshot, slots, events, slots[0]["slot_id"])
    slots[0].update(current_resident_id="SYN-A1", status="reserved")
    events.append(dict(sequence=3, event_type="replacement", resident_id="SYN-A1", slot_id=slots[0]["slot_id"], payload=proposal))
    assert project_worklist(snapshot, slots, events).set_index("resident_id").loc["SYN-A1"].reported
    assert snapshot == before


def test_applied_reports_are_frozen_safely_and_preview_is_never_applied(inputs):
    frame, facilities, records, cfg, settings = inputs
    report = dict(resident_id="SYN-A0", age=50, DM="N", DATE=datetime.now(MANILA).date().isoformat(), y_true=True)
    snapshot = build_round_snapshot(frame, facilities, records, cfg, "run", "clinical", settings,
                                    applied_reports={"SYN-A0": report})
    assert "y_true" not in snapshot["applied_reports"]["SYN-A0"]
    attempt = normalize_event(snapshot, snapshot["slots"], [], "SYN-B0", "report_attempt",
                              dict(payload={**report, "resident_id": "SYN-B0"}, errors=[], channel="form"))
    work = project_worklist(snapshot, snapshot["slots"], [dict(event_type="report_attempt", resident_id="SYN-B0", payload=attempt)])
    assert not work.set_index("resident_id").loc["SYN-B0"].reported


def test_unreported_outreach_slot_is_refilled_from_residents_without_a_questionnaire(inputs):
    frame, facilities, records, cfg, settings = inputs
    frame.loc[frame.resident_id.isin(["SYN-A1", "SYN-A3"]), "reported"] = True
    records.loc[records.invited, "reason"] = "unreported outreach"
    settings.update(strategy="Priority + outreach to unreported residents", outreach=.2)
    snapshot = build_round_snapshot(frame, facilities, records, cfg, "run", "clinical", settings)
    assert snapshot["settings"]["policy"] == "risk_plus_unreported"
    assert all(slot["selection_route"] == "outreach" and slot["ordering_basis"] == "unreported"
               for slot in snapshot["slots"])
    slots, events = deepcopy(snapshot["slots"]), []
    append(snapshot, slots, events, "contact", {"outcome": "Declined"})
    proposal = replacement_candidate(snapshot, slots, events, slots[0]["slot_id"])
    # SYN-A1 has the next-highest score in area A but reported; SYN-A2 is the next nonreporter.
    assert proposal["resident_id"] == "SYN-A2" and proposal["ordering_basis"] == "unreported"


def test_replacement_skips_residents_who_reported_a_known_ckd_diagnosis(inputs):
    frame, facilities, records, cfg, settings = inputs
    frame["reported_known_ckd"] = frame.resident_id.eq("SYN-A3")
    snapshot = build_round_snapshot(frame, facilities, records, cfg, "run", "clinical", settings)
    assert next(r for r in snapshot["residents"] if r["resident_id"] == "SYN-A3")["reported_known_ckd"]
    slots, events = deepcopy(snapshot["slots"]), []
    append(snapshot, slots, events, "contact", {"outcome": "Declined"})
    proposal = replacement_candidate(snapshot, slots, events, slots[0]["slot_id"])
    # SYN-A3 has the highest remaining score in area A but reported a known diagnosis.
    assert proposal["resident_id"] != "SYN-A3"


def test_abnormal_results_stay_open_until_explained_and_referral_outcome_recorded(snapshot):
    slots, events = deepcopy(snapshot["slots"]), []
    today = datetime.now(MANILA).date()
    append(snapshot, slots, events, "result", {"creatinine": 2.5, "uacr": 120, "specimen_date": today})
    append(snapshot, slots, events, "review", {"disposition": "Complete"})
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert case.queue == "Needs review / follow-up" and case.next_action == "Explain reviewed results to resident"
    with pytest.raises(ValueError, match="explained"):
        append(snapshot, slots, events, "communication", {"method": "Carrier pigeon", "explained_by": "Demo nurse"})
    append(snapshot, slots, events, "communication", {"method": "Home visit", "explained_by": "Demo BHW"})
    with pytest.raises(ValueError, match="as sent"):
        append(snapshot, slots, events, "referral", {"status": "Attended"})
    with pytest.raises(ValueError, match="referred"):
        append(snapshot, slots, events, "referral", {"status": "Sent"})
    append(snapshot, slots, events, "referral", {"status": "Sent", "destination": "Provincial hospital nephrology clinic"})
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert case.referral_open and case.next_action == "Confirm referral attendance"
    append(snapshot, slots, events, "referral", {"status": "Did not attend"})
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert case.referral_open and case.next_action == "Follow up missed referral"
    assert case.referral_destination == "Provincial hospital nephrology clinic"
    append(snapshot, slots, events, "referral", {"status": "Outcome unknown"})
    case = project_worklist(snapshot, slots, events).iloc[0]
    assert not case.referral_open and case.queue == "Tasks complete" and case.referral_status == "Outcome unknown"


def test_unreachable_needs_repeated_unanswered_attempts_and_then_releases_like_a_decline(snapshot):
    slots, events = deepcopy(snapshot["slots"]), []
    attempts = snapshot["settings"]["unreachable_after_attempts"]
    for _ in range(attempts - 1):
        append(snapshot, slots, events, "contact", {"outcome": "No answer"})
    with pytest.raises(ValueError, match="unanswered"):
        append(snapshot, slots, events, "contact", {"outcome": "Unreachable"})
    append(snapshot, slots, events, "contact", {"outcome": "No answer"})
    append(snapshot, slots, events, "contact", {"outcome": "Unreachable"})
    case = project_worklist(snapshot, slots, events).set_index("resident_id").loc["SYN-A0"]
    assert case.queue == "Declined / withdrawn" and case.no_answer_count == attempts
    proposal = replacement_candidate(snapshot, slots, events, slots[0]["slot_id"])
    assert proposal is not None and proposal["resident_id"] != "SYN-A0"
