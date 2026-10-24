"""Role views: citizen content, aggregate LGU tables and V3-013 provenance labels."""
from datetime import date
import json

import numpy as np
import pandas as pd
import pytest

from agap.citizen import (GUIDANCE, KIDNEY_STATES, NO_INVITATION, STATUS_MESSAGES, age_band, append_profile,
                          invitation_message, latest_profile, normalize_profile)
from agap.community_overview import TOTAL, cohort_summary, round_summary, suppress
from agap.config import load_config
from agap.provenance import geography_banner, geography_label, provenance_caption
from agap.workflow import QUEUES


def test_small_counts_are_suppressed_but_zero_and_large_counts_are_shown():
    assert [suppress(value, 5) for value in (0, 1, 4, 5, 1234)] == ["0", "<5", "<5", "5", "1,234"]


def test_cohort_summary_reports_aggregates_without_resident_rows():
    frame = pd.DataFrame(dict(municipality=["A"] * 12 + ["B"] * 3, reported=[True] * 6 + [False] * 9,
                              nearest_distance_km=[1.] * 14 + [50.], resident_id=[f"SYN-{i}" for i in range(15)],
                              y_true=True))
    table = cohort_summary(frame, 20, 5).set_index("Municipality")
    assert table.loc["A", "Cohort adults"] == "12" and table.loc["A", "Questionnaire coverage"] == "50%"
    assert table.loc["B", "Cohort adults"] == "<5" and table.loc["B", "Questionnaire coverage"] == "suppressed"
    assert table.loc[TOTAL, "Cohort adults"] == "15"
    assert "resident_id" not in table.columns and "y_true" not in table.columns


def test_round_summary_counts_recorded_queues_and_overdue_tasks():
    cases = pd.DataFrame(dict(resident_id=[f"SYN-{i}" for i in range(8)], municipality=["A"] * 7 + ["B"],
                              queue=[QUEUES[0]] * 6 + [QUEUES[2], QUEUES[0]], next_action="Contact resident",
                              owner="", due_on=["2026-10-01"] * 6 + ["", ""]))
    table = round_summary(cases, 5, today=date(2026, 10, 23)).set_index("Municipality")
    assert table.loc["A", "Invited"] == "7" and table.loc["A", QUEUES[0]] == "6"
    assert table.loc["A", QUEUES[2]] == "<5" and table.loc["B", "Invited"] == "<5"
    assert table.loc["A", "Overdue open tasks"] == "6" and table.loc[TOTAL, "Invited"] == "8"


def test_citizen_profile_keeps_unknowns_and_never_accepts_real_identifiers(tmp_path):
    profile, errors = normalize_profile("SYN-DEPLOYMENT-000001", {"reported_kidney_state": "Receiving dialysis"})
    assert not errors and profile["reported_diagnosed_htn"] == "Not answered"
    assert profile["age_band"] == "Unknown / not answered" and profile["municipality_code"] == "Unknown / not answered"
    _, errors = normalize_profile("Juan Dela Cruz", {})
    assert errors
    _, errors = normalize_profile("SYN-X", {"reported_diagnosed_dm": "Maybe"})
    assert errors
    path = tmp_path / "profiles.jsonl"
    append_profile(path, profile)
    record = latest_profile(path, "SYN-DEPLOYMENT-000001")
    assert record["namespace"] == "synthetic" and record["verified"] is False


def test_citizen_content_has_no_scores_and_never_reassures_uninvited_residents():
    assert set(GUIDANCE) == set(KIDNEY_STATES)
    text = " ".join(line for lines in GUIDANCE.values() for line in lines) + " ".join(STATUS_MESSAGES.values())
    for banned in ("score", "rank", "risk of", "you have CKD", "diagnosed with CKD"):
        assert banned not in text
    assert "does not mean your kidneys are healthy" in invitation_message(None)
    assert invitation_message({"queue": QUEUES[2]}) == STATUS_MESSAGES[QUEUES[2]]
    assert invitation_message({"queue": "unknown"}) == NO_INVITATION


@pytest.mark.parametrize(("age", "band"), [(18, "18–29"), (29, "18–29"), (45, "40–49"), (69, "60–69"),
                                           (70, "70+"), (95, "70+"), (np.nan, "Unknown / not answered")])
def test_age_band(age, band):
    assert age_band(age) == band


def test_provenance_caption_requires_every_part():
    caption = provenance_caption("saved run", "synthetic adults", "2025", "residents", "synthetic simulation")
    assert caption.startswith("Source: saved run") and caption.endswith("Evidence: synthetic simulation")
    with pytest.raises(ValueError, match="Period"):
        provenance_caption("saved run", "synthetic adults", "", "residents", "synthetic simulation")
    with pytest.raises(ValueError, match="evidence type"):
        provenance_caption("saved run", "synthetic adults", "2025", "residents", "validated")


def test_fixture_geography_is_never_labelled_as_the_real_population():
    cfg = load_config()
    cfg["prototype"]["geography_mode"] = "fixture"
    assert "not the Laguna population" in geography_label(cfg) and "Fictional geography" in geography_banner(cfg)
    cfg["prototype"]["geography_mode"] = "public"
    assert geography_banner(cfg) is None and "modeled 2020 Laguna population" in geography_label(cfg)


def test_citizen_clinic_list_keeps_own_municipality_and_nearest_others():
    from agap.role_views import nearby_clinics
    clinics = pd.DataFrame(dict(name=["A", "B", "C", "D", "E"], municipality_name=["Bay", "Bay", "Calamba", "Calamba", "Nagcarlan"],
                                latitude=[14.18, 14.40, 14.20, 14.21, 14.13], longitude=[121.28, 121.40, 121.16, 121.17, 121.41]))
    table = nearby_clinics(clinics, 14.18, 121.28, "Bay", count=2)
    assert set(table.name) == {"A", "B", "C", "D"} and table.distance_km.is_monotonic_increasing
    assert table.iloc[0]["name"] == "A" and table.iloc[0]["distance_km"] == pytest.approx(0, abs=1e-6)


def test_known_ckd_residents_follow_each_residents_latest_profile(tmp_path):
    from agap.citizen import known_ckd_residents
    path = tmp_path / "profiles.jsonl"
    for rid, state in (("SYN-1", "Receiving dialysis"), ("SYN-2", "Diagnosed CKD, not receiving dialysis"),
                       ("SYN-3", "No known CKD diagnosis"), ("SYN-2", "Unsure")):
        append_profile(path, normalize_profile(rid, {"reported_kidney_state": state})[0])
    assert known_ckd_residents(path) == {"SYN-1"}
    assert known_ckd_residents(tmp_path / "missing.jsonl") == set()
