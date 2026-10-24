"""Operational projections must never expose simulator truth or allocate a filtered cohort."""
import numpy as np
import pandas as pd
import pytest

from agap.demo import (filter_queue, filters_for_resident, invitation_export, planner_queue,
                       queue_status, selected_queue_resident, with_reports)


@pytest.fixture
def scored():
    return pd.DataFrame(dict(
        resident_id=["SYN-A", "SYN-B", "SYN-C"], municipality=["A", "B", "A"], age=[40, 60, 55],
        female=[0, 1, 0], reported=[False, True, True], cutoff=pd.Timestamp("2026-01-01"),
        nearest_distance_km=[5., 25., 10.], dm_report=[np.nan, 1., 0.],
        htn_report=[np.nan, 1., np.nan], family_report=[np.nan, 0., 0.], outdoor_report=[np.nan, 0., 1.],
        clinical_score=[.3, .9, .6], clinical_rank=[3, 1, 2],
        y_true=[True, False, True], outdoor_true=[1, 0, 1], completion_uniform=[.1, .2, .3],
    ), index=[10, 20, 30])


@pytest.fixture
def decisions():
    return pd.DataFrame(dict(resident_id=["SYN-C", "SYN-A", "SYN-B"], invited=[True, False, False],
                             reason=["risk", "not invited", "outside access limit"],
                             facility_id=["SIM-001", None, None], distance_km=[11., np.nan, np.nan],
                             y_true=[True, True, False], positive_detected=[True, False, False]))


def test_queue_joins_by_identity_and_distinguishes_unplanned(scored, decisions):
    before = scored.copy(deep=True)
    unplanned = planner_queue(scored, "clinical", 20)
    assert unplanned.invitation_status.eq("Not planned").all()
    queue = planner_queue(scored, "clinical", 20, decisions)
    assert queue.resident_id.tolist() == ["SYN-B", "SYN-C", "SYN-A"]
    assert queue.invitation_status.tolist() == ["Not invited", "Invited", "Not invited"]
    c = queue.set_index("resident_id").loc["SYN-C"]
    assert c.facility_id == "SIM-001" and c.assigned_distance_km == 11.
    assert c.nearest_distance_km == 10.  # nearest and assigned distances are distinct
    assert c.missing_answers == 1
    assert not {"y_true", "outdoor_true", "completion_uniform", "positive_detected"} & set(queue)
    pd.testing.assert_frame_equal(scored, before)
    with pytest.raises(ValueError, match="whole cohort"):
        planner_queue(scored, "clinical", 20, decisions.iloc[:2])


def test_filters_are_views_and_export_always_uses_full_plan(scored, decisions):
    queue = planner_queue(scored, "clinical", 20, decisions)
    before = queue.copy(deep=True)
    assert filter_queue(queue, questionnaire="No questionnaire").resident_id.tolist() == ["SYN-A"]
    assert filter_queue(queue, access="Outside assumed access limit").resident_id.tolist() == ["SYN-B"]
    assert filter_queue(queue, invitation="Invited").resident_id.tolist() == ["SYN-C"]
    assert filter_queue(queue, municipality="B", search="syn-b").resident_id.tolist() == ["SYN-B"]
    assert filter_queue(queue, search=".*").empty  # literal search, not a regex
    assert filter_queue(queue, questionnaire="Missing model answers").resident_id.tolist() == ["SYN-C", "SYN-A"]
    settings = dict(budget=2, strategy="Prioritize higher scores", outreach=.3)
    export = invitation_export(queue, "run-123", "clinical", settings)
    assert export.resident_id.tolist() == ["SYN-C"]
    assert export.iloc[0].outreach_share == 0
    assert export.iloc[0].run_id == "run-123" and export.iloc[0].budget_panels == 2
    assert not {"y_true", "outdoor_true", "positive_detected", "completed", "clinical_rank"} & set(export)
    pd.testing.assert_frame_equal(queue, before)


def test_selected_row_maps_to_its_input_identity_after_filter_and_sort(scored):
    queue = filter_queue(planner_queue(scored, "clinical", 20), municipality="A")
    assert selected_queue_resident(tuple(queue.resident_id), [0]) == "SYN-C"
    assert selected_queue_resident(tuple(queue.iloc[::-1].resident_id), [0]) == "SYN-A"
    assert selected_queue_resident(tuple(queue.resident_id), []) is None
    assert selected_queue_resident(tuple(queue.resident_id), [99]) is None


@pytest.mark.parametrize("questionnaire", ["No questionnaire", "Missing model answers"])
def test_report_handoff_relaxes_only_filters_hiding_the_updated_resident(scored, decisions, questionnaire):
    queue = planner_queue(scored, "clinical", 20, decisions)
    queue.loc[queue.resident_id.eq("SYN-A"), ["reported", "missing_answers", "invitation_status"]] = [True, 0, "Invited"]
    before = queue.copy(deep=True)
    filters = dict(municipality="A", questionnaire=questionnaire, access="Within assumed access limit",
                   invitation="Not invited", search="syn-a")
    updates = filters_for_resident(queue, "SYN-A", filters)
    assert updates == dict(questionnaire="All questionnaires", invitation="All invitation statuses")
    assert filter_queue(queue, **{**filters, **updates}).resident_id.tolist() == ["SYN-A"]
    assert filters["questionnaire"] == questionnaire
    pd.testing.assert_frame_equal(queue, before)


def test_report_handoff_preserves_matching_filters_and_rejects_missing_resident(scored, decisions):
    queue = planner_queue(scored, "clinical", 20, decisions)
    filters = dict(municipality="A", questionnaire="Missing model answers", invitation="Invited", search="syn-c")
    assert filters_for_resident(queue, "SYN-C", filters) == {}
    with pytest.raises(ValueError, match="absent"):
        filters_for_resident(queue, "SYN-MISSING", filters)


def test_multiple_applied_reports_leave_hidden_columns_and_original_untouched(scored):
    before = scored.copy(deep=True)
    reports = {"SYN-A": dict(resident_id="SYN-A", age=40, DM="Y"),
               "SYN-B": dict(resident_id="SYN-B", age=60, DM="N")}
    working = with_reports(scored, reports)
    assert working.set_index("resident_id").loc[["SYN-A", "SYN-B"], "dm_report"].tolist() == [1., 0.]
    assert working.reported.all()
    pd.testing.assert_frame_equal(working[["y_true", "outdoor_true", "completion_uniform"]], before[["y_true", "outdoor_true", "completion_uniform"]])
    pd.testing.assert_frame_equal(scored, before)
    with pytest.raises(ValueError, match="key must match"):
        with_reports(scored, {"SYN-X": reports["SYN-A"]})


def test_queue_status_uses_exact_access_and_report_states_without_changing_exports(scored, decisions):
    queue = planner_queue(scored, "clinical", 20, decisions)
    variants = pd.concat([queue.iloc[[0]]] * 6, ignore_index=True)
    variants["nearest_distance_km"] = [np.nan, 20.01, 20., 3., 4., np.inf]
    variants["access_eligible"] = variants.nearest_distance_km.le(20)
    variants["reported"] = [False, True, False, True, True, True]
    variants["missing_answers"] = [4, 0, 4, 1, 0, 0]
    assert queue_status(variants).tolist() == [
        "Distance unavailable", "Outside access limit", "No report · reachable",
        "Missing answers · reachable", "Complete model answers · reachable", "Distance unavailable"]
    settings = dict(budget=2, strategy="Prioritize higher scores", outreach=.2)
    original = queue.copy(deep=True)
    export = invitation_export(queue, "test", "clinical", settings)
    queue["display_status"] = queue_status(queue, "ready")
    pd.testing.assert_frame_equal(queue.drop(columns="display_status"), original)
    pd.testing.assert_frame_equal(invitation_export(queue, "test", "clinical", settings), export)
    assert "display_status" not in export


def test_queue_status_preserves_recorded_reasons_and_marks_failed_plans(scored):
    queue = planner_queue(scored, "clinical", 20)
    reasons = ["Higher model score", "Random outreach", "Random invitation", "Municipal share",
               "Municipal coverage requirement", "Reassigned municipal slot",
               "No slot assigned under this plan", "Outside the assumed access limit", None, ""]
    queue = pd.concat([queue.iloc[[0]]] * len(reasons), ignore_index=True)
    queue["selection_reason"] = reasons
    assert queue_status(queue, "ready").tolist() == reasons[:-2] + ["Reason unavailable"] * 2
    assert queue_status(queue, "unavailable").eq("Plan unavailable").all()
    with pytest.raises(ValueError, match="plan state"):
        queue_status(queue, "stale")
