"""Live evidence is model-consistent; timeline eligibility never becomes attendance."""
import json

import h3
import numpy as np
import pandas as pd
import pytest

from agap.community_map import (community_figure, community_hex_deck, hex_summary,
                                selected_community, selected_hex_community)
from agap.decision_support import (BUCKETS, bottleneck_counts, evaluation_mask,
                                   evidence_scorecard, marginal_swap, resident_chips, resident_timeline, weather_context_dates)


@pytest.fixture
def records():
    return pd.DataFrame(dict(resident_id=list("ABCDE"), y_true=[True]*4+[False],
        invited=[True, True, False, False, True], completed=[True, False, False, False, True],
        access_feasible=[True, True, True, False, True], score=[.8, .3, .2, .1, .4],
        age=[35, 70, 40, 50, 60], reported=[True, False, True, False, False]))


def test_weather_context_uses_actual_coverage_and_defaults_around_gaps():
    local = pd.DataFrame(dict(cutoff=pd.date_range("2024-01-01", periods=4),
                              complete_7d=[True, False, True, True], complete_30d=[False, False, True, False]))
    before = local.copy(deep=True)
    assert weather_context_dates(local, "2024-01-02", 7) == dict(saved_available=False, default=pd.Timestamp("2024-01-01"))
    assert weather_context_dates(local, "2024-01-03", 30) == dict(saved_available=True, default=pd.Timestamp("2024-01-03"))
    # A fallback may be after screening, but is explicitly historical context.
    assert weather_context_dates(local, "2023-12-31", 30)["default"] == pd.Timestamp("2024-01-03")
    assert weather_context_dates(local, "2024-02-01", 7)["default"] == pd.Timestamp("2024-01-04")
    assert weather_context_dates(local, "2024-01-04", 7)["saved_available"]
    assert not weather_context_dates(local, "2024-01-04", 30)["saved_available"]
    assert weather_context_dates(local.iloc[:2], "2024-01-03", 30) == dict(saved_available=False, default=None)
    assert weather_context_dates(local.iloc[:0], "2024-01-03", 7)["default"] is None
    pd.testing.assert_frame_equal(local, before)


def test_bottlenecks_partition_hidden_positives_and_handle_zero_cases(records):
    counts = bottleneck_counts({"Live": records})
    assert counts.Count.tolist() == [1, 1, 1, 1]
    assert counts.Share.sum() == 1
    assert records.loc[evaluation_mask(records, "All invited"), "resident_id"].tolist() == ["A", "B", "E"]
    assert records.loc[evaluation_mask(records, BUCKETS[2]), "resident_id"].tolist() == ["C"]
    empty = bottleneck_counts({"Zero": records.assign(y_true=False)})
    assert empty.Count.sum() == 0 and np.isfinite(empty.Share).all()


def test_marginal_swap_describes_actual_set_members_not_assumed_demographics(records):
    risk = records.assign(invited=records.resident_id.isin(["A", "C"]))
    mixed = records.assign(invited=records.resident_id.isin(["B", "C"]))
    swap = marginal_swap(risk, mixed)
    assert swap.Residents.tolist() == [1, 1]
    assert swap.Mean_age.tolist() == [35, 70]  # outreach may add an older resident
    assert swap.Mean_score.tolist() == [.8, .3]
    assert swap.Reported_share.tolist() == [1., 0.]
    unchanged = marginal_swap(risk, risk)
    assert unchanged.Residents.eq(0).all() and unchanged.Mean_score.isna().all()


@pytest.mark.parametrize("included,draw,abnormal,expected", [
    (False, .1, True, "Excluded"), (True, .8, True, "Missed 180d"),
    (True, .1, True, "Persistent abnormal"), (True, .1, False, "Normal again"),
])
def test_timeline_separates_climate_coverage_attendance_and_outcome(included, draw, abnormal, expected):
    person = pd.Series(dict(reported=False, completion_probability=.4))
    current = pd.Series(dict(invited=True, completed=True, positive_detected=True, reason="risk", facility_id="SIM-1"))
    visit = pd.Series(dict(followup_included=included, visit_uniform_180d=draw, abnormal_180d=abnormal))
    timeline = resident_timeline(person, current, visit, history=[dict(valid=False)], applied=True)
    assert timeline[0][1] == "Validated · what-if applied"
    assert expected in timeline[-1][1]
    assert "eval truth" in timeline[2][1]
    absent = resident_timeline(person, current)
    assert absent[-1][1] == "Unavailable in this saved run"
    not_found = current.copy()
    not_found["positive_detected"] = False
    no_positive = resident_timeline(person, not_found)
    assert "Not applicable" in no_positive[-1][1]


def test_report_validation_is_not_clinical_review():
    person = pd.Series(dict(reported=False))
    timeline = resident_timeline(person, None, history=[dict(valid=False)])
    assert "Validation failed" in timeline[0][1]
    assert all(status == "Not planned" for _, status in timeline[1:])
    assert "preview only" in resident_timeline(person, None, history=[dict(valid=True)])[0][1]


def test_cartesian_map_and_marker_selection_use_local_geometry_only():
    cell = h3.latlng_to_cell(14.2, 121.2, 8)
    locations = pd.DataFrame(dict(resident_id=["SYN-A"], municipality=["A"], latitude=[14.2], longitude=[121.2]))
    queue = locations.assign(score=.3, invitation_status="Invited")
    facilities = locations.assign(facility_id="SIM-1")
    cells = locations.assign(h3=cell, adult_count=100)
    figure = community_figure(queue, locations, facilities, cells=cells, planned=True, selected_area="A", selected_resident="SYN-A")
    assert all(trace.type == "scatter" for trace in figure.data)
    assert not figure.layout.geo.to_plotly_json() and not figure.layout.map.to_plotly_json()
    community = next(trace for trace in figure.data if trace.name == "Communities")
    assert list(community.customdata) == ["A"]
    layers = [trace.name for trace in figure.data]
    assert layers.index("Communities") > layers.index("Hypothetical service points")
    assert next(trace for trace in figure.data if trace.name == "Hypothetical service points").hoverinfo == "skip"
    assert selected_community([dict(customdata="A")], {"A"}) == "A"
    assert selected_community([dict(customdata=["A"])], {"A"}) == "A"
    assert selected_community([dict(customdata="SIM-1"), dict(customdata=None)], {"A"}) is None


def test_resident_chips_use_factual_reports_access_and_recorded_decisions_only():
    person = pd.Series(dict(age=60, reported=False, dm_report=np.nan, htn_report=1.,
                            family_report=0., outdoor_report=np.nan, y_true=True, outdoor_true=True))
    decision = pd.Series(dict(missing_answers=2, nearest_distance_km=25., access_eligible=True,
        invitation_status="Invited", selection_reason="Random outreach", facility_id="SIM-3", assigned_distance_km=27.))
    chips = resident_chips(person, decision, 30)
    text = " · ".join(value for _, value in chips)
    assert "No questionnaire submitted" in text and "outreach candidate" not in text.lower()
    assert "Within 30 km limit (25.0 km)" in text
    assert "Hypertension: Yes" in text and "Family history: No" in text
    assert "Diabetes: Yes" not in text and "Outdoor work: Yes" not in text
    assert "Random outreach" in text and "SIM-3 (27.0 km)" in text
    assert resident_chips(person.drop(["y_true", "outdoor_true"]), decision, 30) == chips
    decision["nearest_distance_km"] = np.nan
    decision["access_eligible"] = False
    decision["display_status"] = "Plan unavailable"
    text = " · ".join(value for _, value in resident_chips(person, decision, 30))
    assert "distance unavailable" in text and "Outside 30" not in text
    assert "Plan unavailable" in text and "Invited ·" not in text


def test_hex_view_joins_by_identity_and_aggregates_only_represented_cohort_members():
    first, second = h3.latlng_to_cell(14.2, 121.2, 8), h3.latlng_to_cell(14.3, 121.3, 8)
    locations = pd.DataFrame(dict(resident_id=["B", "C", "A"], h3=[first, second, first],
                                 latitude=[14.2, 14.3, 14.2], longitude=[121.2, 121.3, 121.2]))
    queue = pd.DataFrame(dict(resident_id=["A", "B", "C"], municipality=["One", "One", "Two"],
                             score=[.8, .2, .4], invitation_status=["Invited", "Not invited", "Invited"]))
    rows = {row["h3"]: row for row in hex_summary(queue, locations, planned=True)}
    assert len(rows) == 2 and rows[first]["adults"] == 2
    assert rows[first]["mean_score"] == .5 and rows[first]["invitation_coverage"] == .5
    assert rows[second]["mean_score"] == .4 and rows[second]["invitation_coverage"] == 1
    assert rows[first]["elevation"] == 180 and rows[first]["polygon"][0] == rows[first]["polygon"][-1]
    assert not {"y_true", "completed", "positive_detected"} & set(rows[first])
    deck = community_hex_deck(queue, locations, locations.iloc[:1], planned=True, selected_resident="C")
    serialized = json.loads(deck.to_json())
    assert serialized.get("mapProvider") is None and serialized["mapStyle"] == "__MAP_STYLE__"
    layers = {layer["id"]: layer for layer in serialized["layers"]}
    assert layers["communities_hex"]["extruded"] and layers["communities_hex"]["pickable"]
    assert not layers["facilities"]["pickable"] and not layers["selected_resident"]["pickable"]
    assert layers["selected_resident"]["data"][0]["latitude"] == 14.3
    assert selected_hex_community({"selection": {"objects": {"communities_hex": [{"municipality": "One"}]}}}, {"One"}) == "One"
    for selection in ({}, {"selection": {"objects": {"facilities": [{"municipality": "One"}]}}},
                      {"selection": {"objects": {"communities_hex": [{"municipality": "Other"}]}}}):
        assert selected_hex_community(selection, {"One"}) is None
    with pytest.raises(ValueError, match="one-to-one"):
        hex_summary(queue, pd.concat([locations, locations.iloc[[0]]]))


def test_scorecard_missing_artifacts_are_not_passes(tmp_path):
    assert all(card[1] == "Unavailable" for card in evidence_scorecard(tmp_path))
    (tmp_path / "population_check.json").write_text(json.dumps(dict(relative_difference=.1, tolerance=1e-6)))
    (tmp_path / "integrity.json").write_text(json.dumps(dict(passed=1, checks=["x"], skipped_missing_files=["missing.parquet"])))
    (tmp_path / "weight_diagnostics.json").write_text(json.dumps([dict(model="ipw_climate", effective_sample_size=14,
        min_population_observation_probability=0, population_claim="supported subset only", weight_source="oracle MNAR")]))
    (tmp_path / "spatial_sensitivity.json").write_text(json.dumps(dict(ranking_changed=True)))
    cards = evidence_scorecard(tmp_path)
    assert cards[0][1] == "Failed" and cards[1][1] == "Incomplete"
    assert "oracle MNAR" in cards[2][2] and "supported subset" in cards[2][2]
    assert cards[3][1] == "Ranking changed"


def test_reach_by_questionnaire_uses_only_operational_invitations():
    from agap.decision_support import positives_by_questionnaire, reach_by_questionnaire
    queue = pd.DataFrame(dict(reported=[True, True, False, False, False],
                              invitation_status=["Invited", "Not invited", "Invited", "Not invited", "Not planned"]))
    reach = reach_by_questionnaire(queue).set_index("Questionnaire")
    assert reach.loc["Questionnaire submitted", "Invited"] == 1 and reach.loc["No questionnaire", "Residents"] == 3
    assert reach.loc["No questionnaire", "Invitation coverage"] == pytest.approx(1 / 3)
    records = queue.assign(y_true=[1, 0, 1, 1, 0], positive_detected=[1, 0, 1, 0, 0])
    found = positives_by_questionnaire(records).set_index("Questionnaire")
    assert found.loc["No questionnaire", "Found (eval)"] == 1 and found.loc["No questionnaire", "Hidden initial positives (eval)"] == 2
