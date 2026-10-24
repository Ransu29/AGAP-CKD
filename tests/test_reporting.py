"""Engine 1 report schema v2: new fields, missing vs unknown, dates, bounds, report timing."""
import copy
import hashlib
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from agap.config import load_config
from agap.demo import with_report
from agap.experiment import build_data, simulate
from agap.reports import append_report, normalize_report, parse_sms, record_resident_id, resident_history, reports_at

TODAY = date(2026, 10, 18)
CORE = dict(DM="Y", HTN="N", FAM="U", OUT="Y")


def errors_for(**answers):
    return normalize_report("SYN-DEMO", 45, answers, submitted=TODAY)[1]


def test_form_and_sms_give_the_same_payload_with_new_fields():
    form, form_errors = normalize_report("SYN-DEMO", 45, dict(CORE, PRIOR="N", HRS="30", DATE="2026-10-15"), submitted=TODAY)
    sms, sms_errors = parse_sms("AGAP SYN-DEMO 45 DM:Y HTN:N FAM:U OUT:Y PRIOR:N HRS:30 DATE:2026-10-15", submitted=TODAY)
    assert not form_errors and not sms_errors and form == sms
    assert form["PRIOR"] == "N" and form["HRS"] == 30 and form["DATE"] == "2026-10-15"


def test_omitted_unknown_and_no_stay_distinct():
    payload, errors = parse_sms("AGAP SYN-DEMO 45 DM:U HTN:N", submitted=TODAY)
    assert not errors
    assert payload["DM"] == "U" and payload["HTN"] == "N"
    assert payload["FAM"] is None and payload["OUT"] is None and payload["PRIOR"] is None and payload["HRS"] is None
    assert payload["DATE"] == TODAY.isoformat()  # event date defaults to the submission date


@pytest.mark.parametrize("event_date,message", [("2026-10-19", "after the submission"), ("2026-09-17", "within 30 days"),
                                                ("2026-02-30", "real date"), ("18/10/2026", "real date")])
def test_event_dates_are_validated(event_date, message):
    assert any(message in error for error in errors_for(**CORE, DATE=event_date))


def test_boundary_dates_are_accepted():
    assert not errors_for(**CORE, DATE="2026-10-18") and not errors_for(**CORE, DATE="2026-09-18")


@pytest.mark.parametrize("hours", ["-1", "169", "12.5", "many"])
def test_outdoor_hours_outside_bounds_are_rejected(hours):
    assert any(error.startswith("HRS") for error in errors_for(**CORE, HRS=hours))


def test_outdoor_hours_bounds_unknown_and_consistency():
    assert not errors_for(**CORE, HRS="0") and not errors_for(**CORE, HRS="168") and not errors_for(**CORE, HRS="U")
    assert any("must be 0 when OUT is N" in error for error in errors_for(DM="Y", OUT="N", HRS="5"))
    assert not errors_for(DM="Y", OUT="N", HRS="0")


def test_stored_report_keeps_event_and_availability_dates(tmp_path):
    payload, _ = normalize_report("SYN-DEMO", 45, dict(CORE, DATE="2026-10-15"), submitted=TODAY)
    record, created = append_report(tmp_path / "reports.jsonl", payload, [], "sms")
    assert created and record["event_at"] == "2026-10-15" and record["schema_version"] == 2
    assert record["available_at"][:10] != "2026-10-15"


def test_rejected_sms_keeps_resident_context_and_valid_revision_chain(tmp_path):
    path = tmp_path / "reports.jsonl"
    payload, _ = normalize_report("SYN-DEMO", 45, CORE, submitted=TODAY)
    first, _ = append_report(path, payload, [], "Simple form")
    text = "AGAP SYN-DEMO 45 DM:Y DM:N"
    malformed, errors = parse_sms(text, submitted=TODAY)
    assert malformed is None and errors
    rejected, created = append_report(path, malformed, errors, "SMS-style text", resident_id="SYN-DEMO", raw_text=text)
    assert created and rejected["resident_id"] == "SYN-DEMO" and rejected["raw_text"] == text
    assert not rejected["valid"] and rejected["supersedes"] is None
    assert rejected["previous_attempt_id"] == first["report_id"]
    assert resident_history(path, "SYN-DEMO")[-1] == rejected
    correction, _ = append_report(path, dict(payload, DM="N"), [], "Simple form")
    assert correction["supersedes"] == first["report_id"]
    assert correction["previous_attempt_id"] == rejected["report_id"]
    assert reports_at(path, rejected["available_at"]) == [first]
    assert reports_at(path, correction["available_at"]) == [correction]


def test_cross_channel_duplicate_and_legacy_identity_are_backward_compatible(tmp_path):
    path = tmp_path / "reports.jsonl"
    payload, _ = normalize_report("SYN-DEMO", 45, CORE, submitted=TODAY)
    legacy = dict(report_id="REPORT-000001", payload=payload, errors=[], valid=True,
                  available_at="2026-10-18T00:00:00+00:00", channel="Simple form",
                  fingerprint=hashlib.sha256(json.dumps(dict(payload=payload, errors=[]), sort_keys=True).encode()).hexdigest())
    path.write_text(json.dumps(legacy) + "\n")
    before = path.read_bytes()
    record, created = append_report(path, payload, [], "SMS-style text", resident_id="SYN-DEMO", raw_text="different formatting")
    assert not created and record == legacy and path.read_bytes() == before
    assert record_resident_id(legacy) == "SYN-DEMO"
    assert resident_history(path, "SYN-DEMO") == [legacy]
    assert reports_at(path, "2026-10-18T00:00:00+00:00") == [legacy]


def test_malformed_attempts_for_different_residents_are_not_duplicates(tmp_path):
    path = tmp_path / "reports.jsonl"
    errors = ["Unknown or duplicate field: DM"]
    a, _ = append_report(path, None, errors, "sms", resident_id="SYN-A")
    b, created = append_report(path, None, errors, "sms", resident_id="SYN-B")
    duplicate, repeated = append_report(path, None, errors, "form", resident_id="SYN-B")
    assert created and not repeated and duplicate == b
    assert a["fingerprint"] != b["fingerprint"]


@pytest.fixture(scope="module")
def cohorts(tmp_path_factory):
    cfg = load_config()
    directory = tmp_path_factory.mktemp("run")
    build_data(cfg, directory)
    return cfg, directory, simulate(cfg, directory)


def test_simulated_report_details(cohorts):
    _, _, frames = cohorts
    frame = frames["train"]
    reporters, others = frame[frame.reported], frame[~frame.reported]
    assert ((reporters.report_event_date <= reporters.report_available_date) & (reporters.report_available_date <= reporters.cutoff)).all()
    assert not frame.report_late.any()
    assert others[["prior_screen_report", "outdoor_hours_7d_report"]].isna().all().all()
    assert others.report_available_date.isna().all()
    assert frame[frame.outdoor_true].outdoor_hours_7d_true.between(20, 56).all()
    assert frame[~frame.outdoor_true].outdoor_hours_7d_true.between(0, 4).all()


def test_reports_arriving_after_the_cutoff_are_masked(cohorts):
    cfg, directory, frames = cohorts
    late = copy.deepcopy(cfg)
    late["reporting"]["availability_days_before_cutoff"] = [-10, -1]
    frame = simulate(late, directory)["train"]
    reporters = frame[frame.reported]
    assert reporters.report_late.all() and (reporters.report_available_date > reporters.cutoff).all()
    columns = ["dm_report", "htn_report", "family_report", "outdoor_report", "prior_screen_report", "outdoor_hours_7d_report"]
    assert reporters[columns].isna().all().all()
    # The main cohort stream is untouched: hidden traits and outcomes match the default run.
    pd.testing.assert_series_equal(frame.y_true, frames["train"].y_true)


def test_new_hidden_traits_are_forbidden_and_what_if_handles_missing_answers(cohorts):
    cfg, _, frames = cohorts
    assert {"prior_screen_true", "outdoor_hours_7d_true"} <= set(cfg["models"]["forbidden_features"])
    deployment = frames["deployment"]
    person = deployment[~deployment.reported].iloc[0]
    payload, errors = normalize_report(person.resident_id, int(person.age), dict(DM="U", HRS="12"))
    assert not errors
    updated = with_report(deployment, payload).set_index("resident_id").loc[person.resident_id]
    assert updated.reported and np.isnan(updated.dm_report) and np.isnan(updated.htn_report)
    assert updated.outdoor_hours_7d_report == 12
