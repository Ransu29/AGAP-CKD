"""Exercise coordination through the real app, reports and immutable run files."""
import json
import shutil

import pandas as pd
import pytest

from agap import workflow_store as store
from test_judge_demo import saved_demo, open_demo, click


@pytest.fixture
def workflow_demo(saved_demo, tmp_path):
    source_root, source_directory, cfg = saved_demo
    root = tmp_path / "workspace"
    directory = root / "run"
    shutil.copytree(source_directory, directory)
    (root / "outputs").mkdir()
    (root / "outputs/latest_run.json").write_text(json.dumps(dict(path=str(directory))))
    return root, directory, cfg


def approve(app, root):
    click(app, "Compare screening plans")
    app.checkbox(key="workflow_create_confirm_run").check().run(timeout=30)
    click(app, "Create demo screening round")
    assert app.session_state["workspace_tab"] == "Worklist"
    path = root / "data/reports/screening_workflow.sqlite3"
    record = store.active_round(path, run_id="run")
    assert record is not None
    assert app.session_state["workflow_active_round"] == record["round_id"]
    return path, record


def open_case_report(app, round_id, resident_id):
    app.button(key=f"workflow_report_{round_id}_{resident_id}").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["workspace_tab"] == "Resident report"
    assert app.session_state["flow_resident"] == resident_id


def fictional_report(app):
    for key, value in (("DM", "Y"), ("HTN", "N"), ("FAM", "N"), ("OUT", "N"), ("PRIOR", "N")):
        app.selectbox(key=f"report_form_{key}").set_value(value)
    app.text_input(key="report_form_hours").set_value("0")
    click(app, "Preview this report's effect")
    assert "report_result" in app.session_state


def test_approved_round_report_amendment_saves_on_first_apply_and_survives_reset(workflow_demo, monkeypatch):
    root, directory, _ = workflow_demo
    original = {name: (directory / name).read_bytes() for name in (
        "deployment_hidden.parquet", "allocations_hidden.parquet", "metrics.csv")}
    app = open_demo(workflow_demo, monkeypatch)
    path, record = approve(app, root)
    round_id = record["round_id"]
    frozen = record["snapshot"]
    resident_id = app.session_state["flow_resident"]
    open_case_report(app, round_id, resident_id)
    fictional_report(app)
    # Preview has an audit event but remains unapplied until the explicit action.
    assert len([e for e in store.get_events(path, round_id) if e["event_type"] == "report_attempt"]) == 1
    assert not [e for e in store.get_events(path, round_id) if e["event_type"] == "report_applied"]
    click(app, "Apply report & return to workspace")
    assert app.session_state["workspace_tab"] == "Worklist"
    assert any("Questionnaire amendment saved" in item.value for item in app.success)
    assert not any("changed since the worklist was displayed" in item.value for item in app.warning)
    events = [e for e in store.get_events(path, round_id) if e["event_type"] == "report_applied"]
    assert len(events) == 1
    assert events[0]["resident_id"] == resident_id
    assert app.session_state["applied_reports"][resident_id]["DM"] == "Y"
    assert store.load_round(path, round_id)["snapshot"] == frozen
    assert all((directory / name).read_bytes() == content for name, content in original.items())

    reopened = open_demo(workflow_demo, monkeypatch)
    assert not reopened.exception
    assert reopened.session_state["workspace_tab"] == "Worklist"
    assert reopened.session_state["applied_reports"][resident_id] == events[0]["payload"]
    click(reopened, "Reset draft workspace")
    assert store.active_round(path, run_id="run")["round_id"] == round_id
    assert not reopened.session_state["comparison_started"]
    assert reopened.session_state["applied_reports"][resident_id] == events[0]["payload"]
    assert store.load_round(path, round_id)["snapshot"] == frozen


def test_switching_worklist_resident_clears_previous_questionnaire_form(workflow_demo, monkeypatch):
    root, directory, _ = workflow_demo
    app = open_demo(workflow_demo, monkeypatch)
    path, record = approve(app, root)
    round_id = record["round_id"]
    first_id = app.session_state["flow_resident"]
    open_case_report(app, round_id, first_id)
    fictional_report(app)
    click(app, "Back to Worklist")
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    current = set(store.worklist(path, round_id).resident_id)
    other = frame.loc[frame.resident_id.isin(current) & frame.dm_report.eq(0) & frame.resident_id.ne(first_id)].iloc[0]
    app.selectbox(key=f"workflow_resident_{round_id}").set_value(other.resident_id).run(timeout=30)
    assert not app.exception
    assert app.session_state["flow_resident"] == other.resident_id
    assert not app.session_state.get("report_result")
    open_case_report(app, round_id, other.resident_id)
    assert app.selectbox(key="report_form_DM").value == "N"


def test_another_run_keeps_previous_round_as_readonly_history(workflow_demo, monkeypatch):
    root, directory, _ = workflow_demo
    app = open_demo(workflow_demo, monkeypatch)
    path, record = approve(app, root)
    other_directory = root / "other-run"
    shutil.copytree(directory, other_directory)
    (root / "outputs/latest_run.json").write_text(json.dumps(dict(path=str(other_directory))))
    app.run(timeout=30)
    assert not app.exception
    assert app.session_state["demo_run"] == "other-run"
    assert app.session_state["workflow_active_round"] is None
    assert app.session_state["workspace_tab"] == "Plan"
    assert store.active_round(path, run_id="other-run") is None
    assert store.active_round(path, run_id="run")["round_id"] == record["round_id"]
    saved = next(widget for widget in app.selectbox if widget.label == "Saved round")
    assert any("past run run" in label for label in saved.options)
    assert store.load_round(path, record["round_id"])["status"] == "active"
