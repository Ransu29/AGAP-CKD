"""Staff-task browsing must preserve case identity and approved decisions."""
from datetime import date

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from agap.workflow_overview import (
    display_alias, filtered_overview, next_case_id, overview_rows, queue_counts,
)
from agap import workflow_store as store
from test_workflow_ui import coordination, open_worklist, choice, click


TODAY = date(2026, 10, 21)


@pytest.fixture
def cases():
    return pd.DataFrame([
        dict(resident_id="R1", municipality="North town", queue="Needs contact", next_action="Call again",
             owner="Ari", due_on="2026-10-22", score=.99),
        dict(resident_id="R2", municipality="South town", queue="Awaiting screening", next_action="Collect panel",
             owner="", due_on="2026-10-20", score=.01),
        dict(resident_id="R3", municipality="North town", queue="Needs review / follow-up", next_action="Review panel",
             owner="Bea", due_on="2026-10-21", score=.50),
        dict(resident_id="R4", municipality="South town", queue="Tasks complete", next_action="", owner="",
             due_on="2026-10-01", score=.80),
        dict(resident_id="R5", municipality="East town", queue="Declined / withdrawn", next_action="", owner="",
             due_on="2026-10-01", score=.70),
        dict(resident_id="R6", municipality="East town", queue="Needs contact", next_action="First contact",
             owner=None, due_on=None, score=1.0),
    ])


def test_task_sort_uses_staff_dates_and_excludes_simulator_fields(cases):
    original = cases.copy(deep=True)
    rows = overview_rows(cases, today=TODAY)
    assert list(rows.resident_id) == ["R2", "R3", "R1", "R6", "R4", "R5"]
    assert not {"score", "y_true", "completion_uniform", "random_rank"}.intersection(rows.columns)
    assert list(rows.loc[rows.overdue, "resident_id"]) == ["R2"]
    assert list(rows.loc[rows.due_today, "resident_id"]) == ["R3"]
    pd.testing.assert_frame_equal(cases, original)
    shuffled = cases.sample(frac=1, random_state=3).assign(score=lambda frame: 1 - frame.score)
    assert list(overview_rows(shuffled, today=TODAY).resident_id) == list(rows.resident_id)


@pytest.mark.parametrize("task_filter, expected", [
    ("All tasks", ["R2", "R3", "R1", "R6", "R4", "R5"]),
    ("Overdue", ["R2"]), ("Due today", ["R3"]), ("Unassigned", ["R2", "R6"]),
])
def test_date_and_owner_filters_only_treat_open_cases_as_tasks(cases, task_filter, expected):
    assert list(filtered_overview(cases, task_filter=task_filter, today=TODAY).resident_id) == expected


def test_query_and_queue_filters_combine_without_regex_or_hidden_fields(cases):
    assert list(filtered_overview(cases, queue="Needs contact", query="north ARI", today=TODAY).resident_id) == ["R1"]
    assert list(filtered_overview(cases, query="Case R3", today=TODAY).resident_id) == ["R3"]
    assert filtered_overview(cases, query="[.*", today=TODAY).empty
    assert filtered_overview(cases.iloc[:0], query="anything", today=TODAY).empty
    assert filtered_overview(cases, queue="Tasks complete", task_filter="Overdue", query="anything", today=TODAY).empty
    assert queue_counts(cases) == {
        "Needs contact": 2, "Awaiting screening": 1, "Needs review / follow-up": 1,
        "Tasks complete": 1, "Declined / withdrawn": 1,
    }


def test_aliases_are_stable_unique_and_full_ids_stay_searchable():
    ids = ["SYN-DEPLOYMENT-000347", "SYN-DEPLOYMENT-100347", "R1", "long-another-prefix-000347"]
    aliases = [display_alias(value, ids) for value in ids]
    assert aliases[:2] == ["Resident 000347", "Resident 100347"]
    assert len(set(aliases)) == len(ids)
    assert aliases == [display_alias(value, list(reversed(ids))) for value in ids]
    frame = pd.DataFrame(dict(resident_id=ids, queue=["Needs contact"] * len(ids)))
    assert list(filtered_overview(frame, query=ids[0], today=TODAY).resident_id) == [ids[0]]


def test_explicit_next_skips_closed_cases_and_keeps_removed_cases_previous_position(cases):
    rows = filtered_overview(cases, today=TODAY)
    assert next_case_id(rows, "R2") == "R3"
    assert next_case_id(rows, "R6") == "R2"
    assert next_case_id(rows.loc[rows.resident_id.eq("R2")], "R2") is None
    remaining = rows.loc[~rows.resident_id.eq("R3")]
    assert next_case_id(remaining, "R3", previous_ids=["R2", "R3", "R1", "R6"]) == "R1"
    assert next_case_id(rows.loc[~rows.open_task], "R4") is None


def test_browsing_filters_and_saved_queue_transition_preserve_case_and_storage(coordination):
    _, path, record, *_ = coordination
    round_id = record["round_id"]
    app = open_worklist(coordination, bridge=True)
    original = store.load_round(path, round_id)
    initial_events = store.get_events(path, round_id)
    initial_slots = store.get_slots(path, round_id)
    choice(app, "Work queue", "Needs contact")
    app.run(timeout=15)
    assert not app.exception
    choice(app, "Contact outcome", "Accepted")
    click(app, "Save contact outcome")
    assert app.session_state["returned_selection"] == "R1"
    assert app.selectbox(key=f"workflow_queue_{round_id}").value == "Needs contact"
    assert any("outside your current filters" in item.value for item in app.info)
    assert app.session_state["flow_resident"] == "R1"
    assert store.worklist(path, round_id).set_index("resident_id").loc["R1", "queue"] == "Awaiting screening"
    after_save = store.get_events(path, round_id)
    assert len(after_save) == len(initial_events) + 1
    assert store.load_round(path, round_id)["snapshot"] == original["snapshot"]
    assert store.get_slots(path, round_id) == initial_slots

    app.text_input(key=f"workflow_search_{round_id}").set_value("R2").run(timeout=15)
    assert app.session_state["returned_selection"] == "R1"
    assert store.get_events(path, round_id) == after_save
    click(app, "Open next case")
    assert app.session_state["returned_selection"] == "R2"
    assert app.selectbox(key=f"workflow_queue_{round_id}").value == "Needs contact"
    assert app.text_input(key=f"workflow_search_{round_id}").value == "R2"
    assert store.get_events(path, round_id) == after_save
    assert store.get_slots(path, round_id) == initial_slots


def selector_app(tmp_path, frame):
    path = tmp_path / "cases.pkl"
    frame.to_pickle(path)
    source = f"""
import pandas as pd
import streamlit as st
from agap.workflow_ui import _case_selector
frame = pd.read_pickle({str(path)!r})
selected = _case_selector(frame, 'overview-round', st.session_state.get('followed'))
st.session_state['followed'] = selected
"""
    app = AppTest.from_string(source).run(timeout=15)
    assert not app.exception
    return app


def test_case_browse_page_survives_save_rerun_and_only_search_resets_position(tmp_path):
    frame = pd.DataFrame(dict(resident_id=[f"R{index:02}" for index in range(25)],
        queue=["Needs contact"] * 25, municipality=["Demo town"] * 25))
    app = selector_app(tmp_path, frame)
    assert len(app.dataframe[0].value) == 10
    click(app, "Next cases")
    assert app.session_state["workflow_case_page_overview-round"] == 1
    first_row = app.dataframe[0].value.iloc[0].Case
    app.run(timeout=15)
    assert not app.exception
    assert app.session_state["workflow_case_page_overview-round"] == 1
    assert app.dataframe[0].value.iloc[0].Case == first_row
    assert app.session_state["followed"] == "R00"
    app.text_input(key="workflow_search_overview-round").set_value("R24").run(timeout=15)
    assert app.session_state["workflow_case_page_overview-round"] == 0
    assert app.session_state["followed"] == "R00"
    assert len(app.dataframe[0].value) == 1


def test_empty_search_keeps_selected_case_and_disables_next(tmp_path, cases):
    app = selector_app(tmp_path, cases)
    selected = app.session_state["followed"]
    app.text_input(key="workflow_search_overview-round").set_value("no such case").run(timeout=15)
    assert not app.exception
    assert app.session_state["followed"] == selected
    assert next(button for button in app.button if button.label == "Open next case").disabled
    assert any("outside your current filters" in item.value for item in app.info)
