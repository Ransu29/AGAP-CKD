"""Exercise saved coordination actions through real Streamlit forms."""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from agap.config import load_config
from agap.workflow import build_round_snapshot
from agap import workflow_store as store
import agap.workflow_ui


@pytest.fixture
def coordination(tmp_path):
    cfg = load_config()
    cfg["allocation"]["budget_tests"] = 2
    scored = pd.DataFrame(dict(
        resident_id=["R1", "R2", "R3", "R4"], municipality=["Demo town"] * 4,
        latitude=[14.0, 14.001, 14.002, 14.003], longitude=[121.0] * 4,
        age=[50, 50, 50, 50], female=[True, False, True, False],
        reported=[True, False, True, True], dm_report=[0.0] * 4,
        htn_report=[0.0] * 4, family_report=[0.0] * 4, outdoor_report=[0.0] * 4,
        tie_uniform=[.1, .2, .3, .4], clinical_score=[.9, .8, .7, .6],
        clinical_rank=[1, 2, 3, 4], cutoff=["2026-10-01"] * 4,
        y_true=[True] * 4, completion_uniform=[0.0] * 4,
        creatinine=[99.0] * 4, uacr=[999.0] * 4,
    ))
    facilities = pd.DataFrame(dict(facility_id=["F1"], latitude=[14.0], longitude=[121.0], capacity=[2]))
    decisions = pd.DataFrame(dict(resident_id=scored.resident_id, municipality=scored.municipality,
        invited=[True, True, False, False], reason=["risk_ranked", "risk_ranked", "not invited", "not invited"],
        facility_id=["F1", "F1", None, None], score=scored.clinical_score))
    settings = dict(budget=2, strategy="Prioritize higher scores", outreach=0.0)
    snapshot = build_round_snapshot(scored, facilities, decisions, cfg, "saved-demo-run", "clinical", settings)
    path = tmp_path / "data/reports/screening_workflow.sqlite3"
    record = store.create_round(path, snapshot, request_id="create-fixture")
    return tmp_path, path, record, scored, facilities, decisions, cfg, settings


def open_worklist(coordination, selected="R1", bridge=False):
    root, _, _, *_ = coordination
    followed = "st.session_state.get('flow_resident')" if bridge else repr(selected)
    source = f"""
from pathlib import Path
import streamlit as st
from agap.workflow_ui import render_worklist, workflow_path
from agap import workflow_store as store
root = Path({str(root)!r})
record = store.active_round(workflow_path(root), run_id='saved-demo-run')
if record is not None:
    selected = render_worklist(root, record, selected_resident={followed})
    st.session_state['returned_selection'] = selected
    if {bridge!r}:
        st.session_state['flow_resident'] = selected
else:
    st.info('No active round')
"""
    app = AppTest.from_string(source).run(timeout=15)
    assert not app.exception
    return app


def click(app, label):
    next(button for button in app.button if button.label == label).click().run(timeout=15)
    assert not app.exception


def choice(app, label, value):
    next(widget for widget in app.selectbox if widget.label == label).set_value(value)


def text(app, label, value):
    next(widget for widget in app.text_input if widget.label == label).set_value(value)


def test_saved_contact_specimen_partial_result_and_review_journey(coordination):
    _, path, record, *_ = coordination
    app = open_worklist(coordination)
    assert app.session_state["returned_selection"] == "R1"
    # Hidden simulator values do not prepopulate results or completions.
    frame = store.worklist(path, record["round_id"])
    assert frame.panel_complete.eq(False).all()
    assert frame.creatinine.isna().all()
    choice(app, "Contact outcome", "Accepted")
    click(app, "Save contact outcome")
    assert store.worklist(path, record["round_id"]).iloc[0]["queue"] == "Awaiting screening"
    click(app, "Record specimen collection")
    text(app, "Creatinine (mg/dL; blank = unavailable)", "0.9")
    click(app, "Save panel results")
    person = store.worklist(path, record["round_id"]).iloc[0]
    assert not person.panel_complete
    assert pd.isna(person.screening_flag)
    assert person.queue == "Awaiting screening"
    text(app, "uACR (mg/g; blank = unavailable)", "50")
    click(app, "Save panel results")
    person = store.worklist(path, record["round_id"]).iloc[0]
    assert person.panel_complete and person.review_open
    assert person.queue == "Needs review / follow-up"
    click(app, "Save review disposition")
    person = store.worklist(path, record["round_id"]).iloc[0]
    assert person.queue == "Needs review / follow-up" and person.next_action == "Explain reviewed results to resident"
    click(app, "Record results explained")
    assert store.worklist(path, record["round_id"]).iloc[0]["queue"] == "Tasks complete"
    assert any("Results explained to the resident. Now tasks complete." in item.value for item in app.success)
    # A new browser session reconstructs the same queue from persisted events.
    reopened = open_worklist(coordination)
    assert any("Tasks complete: 1" in item.value for item in reopened.caption)
    assert len([e for e in store.get_events(path, record["round_id"]) if e["event_type"] == "result"]) == 2


def test_decline_recovery_preserves_history_and_excludes_old_invitation(coordination):
    _, path, record, *_ = coordination
    app = open_worklist(coordination, selected="R2")
    choice(app, "Contact outcome", "Declined")
    click(app, "Save contact outcome")
    assert any(button.label == "Assign replacement" for button in app.button)
    click(app, "Assign replacement")
    slots = store.get_slots(path, record["round_id"])
    replacement = next(slot for slot in slots if slot["original_resident_id"] == "R2")
    assert replacement["current_resident_id"] == "R3"
    frame = store.worklist(path, record["round_id"])
    assert frame.set_index("resident_id").loc["R2", "queue"] == "Declined / withdrawn"
    assert frame.set_index("resident_id").loc["R3", "queue"] == "Needs contact"
    assert not any(button.label == "Assign replacement" for button in app.button)
    assert not any("Could not prepare" in error.value for error in app.error)
    assert any("reassigned: 1" in caption.value for caption in app.caption)


def test_invalid_results_do_not_acknowledge_or_write_an_event(coordination):
    _, path, record, *_ = coordination
    app = open_worklist(coordination)
    click(app, "Record specimen collection")
    before = len(store.get_events(path, record["round_id"]))
    text(app, "Creatinine (mg/dL; blank = unavailable)", "nan")
    click(app, "Save panel results")
    assert any("finite" in error.value for error in app.error)
    assert len(store.get_events(path, record["round_id"])) == before
    assert not any("Panel results saved" in success.value for success in app.success)


def test_archive_preserves_cases_and_round_history(coordination):
    _, path, record, *_ = coordination
    app = open_worklist(coordination)
    next(widget for widget in app.checkbox if widget.label == "Archive this demo round and keep its history").check().run(timeout=15)
    click(app, "Archive demo round")
    assert store.active_round(path, run_id="saved-demo-run") is None
    assert store.load_round(path, record["round_id"])["status"] == "archived"
    assert len(store.worklist(path, record["round_id"])) == 2


def test_round_snapshot_is_created_only_after_explicit_approval(coordination, monkeypatch):
    root, _, _, scored, facilities, decisions, cfg, settings = coordination
    inputs_path = root / "approval_inputs.pkl"
    pd.to_pickle(dict(scored=scored, facilities=facilities, decisions=decisions, cfg=cfg, settings=settings), inputs_path)
    output_root = root / "approval-workspace"
    calls = []
    original = agap.workflow_ui.build_round_snapshot

    def snapshot(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(agap.workflow_ui, "build_round_snapshot", snapshot)
    source = f"""
from pathlib import Path
import pandas as pd
from agap.workflow_ui import render_round_approval
inputs = pd.read_pickle({str(inputs_path)!r})
render_round_approval(Path({str(output_root)!r}), 'saved-demo-run', inputs['scored'], inputs['facilities'],
    {{'proposed': inputs['decisions']}}, inputs['cfg'], 'clinical', inputs['settings'])
"""
    app = AppTest.from_string(source).run(timeout=15)
    assert not app.exception
    assert not calls
    assert not (output_root / "data/reports/screening_workflow.sqlite3").exists()
    assert next(button for button in app.button if button.label == "Create demo screening round").disabled
    app.checkbox(key="workflow_create_confirm_saved-demo-run").check().run(timeout=15)
    click(app, "Create demo screening round")
    assert len(calls) == 1
    assert app.session_state["workflow_open_worklist"]
    saved = store.active_round(output_root / "data/reports/screening_workflow.sqlite3", run_id="saved-demo-run")
    assert len(saved["snapshot"]["slots"]) == 2
    app.run(timeout=15)
    assert not app.exception
    assert len(calls) == 1


def test_changed_round_reloads_old_form_without_recording_stale_submission(coordination):
    _, path, record, *_ = coordination
    app = open_worklist(coordination)
    store.record_event(path, record["round_id"], "R1", "contact", dict(outcome="Accepted"),
                       request_id="other-browser", expected_version=0)
    before = len(store.get_events(path, record["round_id"]))
    click(app, "Save contact outcome")
    assert any("changed since" in warning.value for warning in app.warning)
    assert len(store.get_events(path, record["round_id"])) == before
    assert store.worklist(path, record["round_id"]).iloc[0].contact_outcome == "Accepted"
    choice(app, "Contact outcome", "No answer")
    click(app, "Save contact outcome")
    assert store.worklist(path, record["round_id"]).iloc[0].contact_outcome == "No answer"


def test_followup_completion_keeps_incomplete_panel_visible(coordination):
    _, path, record, *_ = coordination
    app = open_worklist(coordination)
    click(app, "Record specimen collection")
    text(app, "uACR (mg/g; blank = unavailable)", "50")
    click(app, "Save panel results")
    choice(app, "Review disposition", "Follow-up requested")
    text(app, "Follow-up action (required when requested)", "Demo review conversation")
    click(app, "Save review disposition")
    assert not any(button.label == "Save review disposition" for button in app.button)
    click(app, "Complete follow-up task")
    person = store.worklist(path, record["round_id"]).iloc[0]
    assert not person.followup_open and person.communication_needed
    click(app, "Record results explained")
    person = store.worklist(path, record["round_id"]).iloc[0]
    assert not person.panel_complete and person.results_communicated
    assert person.queue == "Awaiting screening"


def test_referral_is_tracked_from_sent_to_outcome_in_the_worklist(coordination):
    _, path, record, *_ = coordination
    app = open_worklist(coordination)
    click(app, "Record specimen collection")
    text(app, "Creatinine (mg/dL; blank = unavailable)", "2.5")
    text(app, "uACR (mg/g; blank = unavailable)", "120")
    click(app, "Save panel results")
    click(app, "Save review disposition")
    click(app, "Record results explained")
    text(app, "Referred to (clinic, hospital or specialist)", "Demo provincial hospital")
    click(app, "Save referral status")
    person = store.worklist(path, record["round_id"]).iloc[0]
    assert person.referral_open and person.next_action == "Confirm referral attendance"
    assert any(item.value.startswith("Referral sent saved.") for item in app.success)
    choice(app, "Referral status", "Attended")
    click(app, "Save referral status")
    person = store.worklist(path, record["round_id"]).iloc[0]
    assert person.referral_status == "Attended" and person.queue == "Tasks complete"


def test_workflow_database_override_is_a_trusted_process_setting(tmp_path, monkeypatch):
    override = tmp_path / "isolated-demo.sqlite3"
    monkeypatch.setenv("AGAP_WORKFLOW_DB", str(override))
    assert agap.workflow_ui.workflow_path(tmp_path / "workspace") == override
    monkeypatch.delenv("AGAP_WORKFLOW_DB")
    assert agap.workflow_ui.workflow_path(tmp_path) == tmp_path / "data/reports/screening_workflow.sqlite3"


def test_first_case_change_after_fresh_worklist_selection_is_retained(coordination):
    app = open_worklist(coordination, bridge=True)
    _, _, record, *_ = coordination
    assert app.session_state["flow_resident"] == "R1"
    app.selectbox(key=f"workflow_resident_{record['round_id']}").set_value("R2").run(timeout=15)
    assert not app.exception
    assert app.session_state["returned_selection"] == "R2"
    assert app.session_state["flow_resident"] == "R2"
    app.run(timeout=15)
    assert app.session_state["returned_selection"] == "R2"


def test_complete_case_allows_owner_only_and_keeps_result_amendment_available(coordination):
    _, path, record, *_ = coordination
    store.record_event(path, record["round_id"], "R1", "result", dict(
        creatinine=.5, uacr=2.0, specimen_date="2026-10-01"), request_id="normal-panel")
    assert store.worklist(path, record["round_id"]).iloc[0].queue == "Tasks complete"
    app = open_worklist(coordination)
    assert not any(button.label == "Save contact outcome" for button in app.button)
    assert any(button.label == "Save panel results" for button in app.button)
    assert next(widget for widget in app.text_input if widget.label == "Next action").disabled
    due = next(widget for widget in app.date_input if widget.label == "Action due date")
    assert due.disabled and due.value is None
    text(app, "Responsible demo staff member", "Demo coordinator B")
    click(app, "Save owner")
    assignment = [event for event in store.get_events(path, record["round_id"]) if event["event_type"] == "assignment"][-1]
    assert assignment["payload"] == dict(owner="Demo coordinator B")
    person = store.worklist(path, record["round_id"]).iloc[0]
    assert person.queue == "Tasks complete" and not person.due_on
    assert person.owner == "Demo coordinator B"
    choice(app, "Review disposition", "Follow-up requested")
    text(app, "Follow-up action (required when requested)", "Demo follow-up conversation")
    click(app, "Save review disposition")
    person = store.worklist(path, record["round_id"]).iloc[0]
    assert person.queue == "Needs review / follow-up" and person.followup_open
    click(app, "Complete follow-up task")
    person = store.worklist(path, record["round_id"]).iloc[0]
    assert person.queue == "Tasks complete" and not person.followup_open
    assert person.owner == "Demo coordinator B"


def test_receipts_and_progress_follow_saved_actions_without_inventing_missing_steps(coordination):
    from agap.workflow_presentation import case_progress

    _, path, record, *_ = coordination
    app = open_worklist(coordination)
    choice(app, "Contact outcome", "Accepted")
    click(app, "Save contact outcome")
    assert any("Contact accepted saved. Now awaiting screening." in item.value for item in app.success)
    assert app.session_state["returned_selection"] == "R1"
    # Direct result entry is permitted by the store, but never invents contact
    # for R2 or treats a missing test as complete/clinically cleared.
    store.record_event(path, record["round_id"], "R2", "result",
                       dict(creatinine=.5, specimen_date="2026-10-01"), request_id="partial-no-contact")
    person = store.worklist(path, record["round_id"]).set_index("resident_id").loc["R2"].to_dict()
    stages = {stage["stage"]: stage["detail"] for stage in case_progress(person)}
    assert stages["Contact"] == "Not recorded"
    assert stages["Panel"] == "1 of 2 recorded · incomplete"
    assert stages["Review / follow-up"] == "No review task open"
    store.record_event(path, record["round_id"], "R2", "result",
                       dict(creatinine=.5, uacr=100, specimen_date="2026-10-01"), request_id="flag-no-contact")
    person = store.worklist(path, record["round_id"]).set_index("resident_id").loc["R2"].to_dict()
    stages = {stage["stage"]: stage["detail"] for stage in case_progress(person)}
    assert stages["Contact"] == "Not recorded"
    assert stages["Panel"] == "2 of 2 recorded"
    assert stages["Review / follow-up"] == "Review open"


def test_recovery_facts_expose_saved_constraints_and_capacity_effect(coordination):
    from agap.workflow_presentation import recovery_facts

    _, path, record, *_ = coordination
    store.record_event(path, record["round_id"], "R2", "contact", dict(outcome="Declined"), request_id="decline-for-facts")
    frame = store.worklist(path, record["round_id"])
    person = frame.loc[frame.resident_id.eq("R2")].iloc[0].to_dict()
    proposal = store.propose_replacement(path, record["round_id"], person["slot_id"])
    facts = recovery_facts(record["snapshot"], person, proposal, store.get_slots(path, record["round_id"]), frame)
    assert facts["eligible"]
    assert facts["round_occupied"] == facts["facility_occupied"] == 1
    assert facts["budget"] == facts["facility_capacity"] == 2
    assert facts["ordering_basis"] == "priority" and facts["order_position"] == 3
    before = store.get_events(path, record["round_id"])
    assert len(before) == 2  # Read-only presentation creates no activity.
    # A mismatched proposal must never display all checks passing.
    invalid = dict(proposal, municipality="Another town")
    rejected = recovery_facts(record["snapshot"], person, invalid, store.get_slots(path, record["round_id"]), frame)
    assert not rejected["eligible"]


def test_replacement_receipt_retains_decline_case_and_reports_filled_capacity(coordination):
    _, path, record, *_ = coordination
    app = open_worklist(coordination, selected="R2")
    choice(app, "Contact outcome", "Declined")
    click(app, "Save contact outcome")
    assert any("Now declined / withdrawn" in item.value for item in app.success)
    click(app, "Assign replacement")
    assert any("Round slots occupied: 2/2" in item.value for item in app.success)
    assert app.session_state["returned_selection"] == "R2"
    assert store.worklist(path, record["round_id"]).set_index("resident_id").loc["R2", "queue"] == "Declined / withdrawn"
    click(app, "Open replacement case")
    assert app.session_state["returned_selection"] == "R3"
