"""Automated tests for AGAP-CKD Competition REST API."""
import pytest
from agap.triage import FEATURES
from api.main import (
    init_state,
    get_meta,
    evaluate_citizen,
    evaluate_risk_check,
    batch_sync_checks,
    get_analyst_overview,
    get_analyst_climate,
    FIELD_SYNC_LOG_PATH,
    RiskCheckRequest,
    BatchSyncRequest,
)


@pytest.fixture(scope="session", autouse=True)
def setup_api_state():
    init_state()


def test_api_meta_contains_safety_disclaimer():
    meta = get_meta()
    assert meta["status"] == "ready"
    assert "not diagnoses" in meta["disclaimer"].lower()
    assert meta["features"] == FEATURES


@pytest.fixture()
def frozen_risk_check(monkeypatch, tmp_path_factory):
    """A small fitted risk-level model with fixed cut-offs, so these tests do not need `make triage`."""
    import numpy as np

    import api.main as api
    from agap.config import load_config
    from agap.risk_check_service import FrozenModel, load_context
    from agap.simulate.risk_check import risk_check_cohort
    from agap.triage import encode_features, fit_model

    cfg = load_config()
    train = risk_check_cohort(cfg, 3000, np.random.default_rng(5))
    frozen = FrozenModel(fit_model(encode_features(train, cfg), train.y_true, cfg),
                         dict(t_medium=0.07, t_high=0.12, config_fingerprint="test", git_commit="test"))
    monkeypatch.setitem(api.STATE, "risk_check", (frozen, load_context(api.LAGUNA_DIR, cfg)))
    # Scored app checks are logged for the analyst map; keep test checks out of the real log.
    monkeypatch.setattr(api, "RISK_CHECK_LOG_PATH", tmp_path_factory.mktemp("logs") / "risk_check_log.jsonl")
    return frozen


def answers(**overrides):
    base = dict(safety="No", age_group="18-39", sex="Female", municipality="City of Calamba", diabetes="No",
                high_blood_pressure="No", bp_reading="Normal", heart_disease_stroke="No", kidney_stones="No",
                family_history="No", height_cm=160, weight_kg=50, heavy_outdoor_work="No", kidney_status="Never tested")
    return RiskCheckRequest(**{**base, **overrides})


def test_risk_check_low_risk_baseline(frozen_risk_check):
    res = evaluate_risk_check(answers())
    assert res["route"] == "result" and res["level"] == "Low"
    assert res["next_step"]["code"] == "recheck" and res["next_step"]["next_kidney_test"] is None
    assert "probability" not in str(res)
    assert len(res["where"]["facilities"]) > 0
    assert all(f["verification"] == "Not yet verified, call ahead" for f in res["where"]["facilities"])


def test_risk_check_guideline_floor_applied(frozen_risk_check):
    # ADR 0002: diabetes Yes raises the level to at least Medium; with high BP too, High.
    res = evaluate_risk_check(answers(diabetes="Yes", medicine="Regularly"))
    assert res["level"] in ("Medium", "High") and "diabetes" in res["reasons"]
    assert evaluate_risk_check(answers(diabetes="Yes", high_blood_pressure="Yes", medicine="Regularly"))["level"] == "High"


def test_risk_check_safety_and_diagnosed_routes_get_no_level(frozen_risk_check):
    doctor = evaluate_risk_check(answers(safety="Yes"))
    assert doctor["route"] == "see_doctor" and "level" not in doctor
    diagnosed = evaluate_risk_check(answers(kidney_status="Told something was wrong"))
    assert diagnosed["route"] == "already_diagnosed" and "level" not in diagnosed


def test_risk_check_needs_the_frozen_model(monkeypatch, tmp_path):
    import api.main as api
    from fastapi import HTTPException

    monkeypatch.setitem(api.STATE, "risk_check", None)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    with pytest.raises(HTTPException) as missing:
        evaluate_risk_check(answers())
    assert missing.value.status_code == 503


def test_risk_check_facilities_for_one_town_or_all(frozen_risk_check):
    import api.main as api

    everything = api.get_risk_check_facilities()
    calamba = api.get_risk_check_facilities("City of Calamba")
    assert len(everything["facilities"]) > len(calamba["facilities"]) > 0
    assert {f["verification"] for f in everything["facilities"]} == {"Not yet verified, call ahead"}


def test_unknown_municipality_is_rejected(frozen_risk_check):
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        evaluate_risk_check(answers(municipality="Atlantis"))


def test_citizen_path_is_the_shared_risk_check(frozen_risk_check, tmp_path, monkeypatch):
    """ADR 0003: the app's path scores exactly like the shared endpoint; there is no second model."""
    import api.main as api

    monkeypatch.setattr(api, "RISK_CHECK_LOG_PATH", tmp_path / "checks.jsonl")
    for overrides in ({}, dict(diabetes="Yes", medicine="Regularly"), dict(age_group="70+", kidney_stones="Yes")):
        assert evaluate_citizen(answers(**overrides)) == evaluate_risk_check(answers(**overrides))


def test_app_checks_are_recorded_without_identities_and_field_checks_wait_for_sync(frozen_risk_check, tmp_path, monkeypatch):
    import json

    import api.main as api

    log = tmp_path / "checks.jsonl"
    monkeypatch.setattr(api, "RISK_CHECK_LOG_PATH", log)
    evaluate_risk_check(answers())
    evaluate_risk_check(answers(channel="field"))
    evaluate_risk_check(answers(safety="Yes"))
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(entries) == 1 and entries[0]["channel"] == "app"
    assert set(entries[0]) == {"channel", "at", "municipality", "risk_level", "answers"}


def test_recorded_checks_reach_the_analyst_map(tmp_path, monkeypatch):
    import json

    import pandas as pd

    import api.main as api

    simulated = pd.DataFrame([dict(municipality="City of Calamba", age_group="18-39", sex="Female", diabetes="No",
                                   high_blood_pressure="No", bp_reading="Normal", medicine="", heart_disease_stroke="No",
                                   kidney_stones="No", family_history="No", heavy_outdoor_work="No", bmi_reported=21.0,
                                   kidney_status="Never tested", risk_level="Low", channel="app", done_reply=False)] * 60)
    simulated.to_parquet(tmp_path / "checks.parquet")
    (tmp_path / "overview.json").write_text(json.dumps(dict(province="Laguna", built_with={"git_commit": "x"})))
    field_log = tmp_path / "field.jsonl"
    field_log.write_text(json.dumps(dict(channel="field", municipality="City of Calamba", outcome="High",
                                         answers=dict(age_group="60-69", sex="Male", diabetes="Yes", high_blood_pressure="Yes",
                                                      heart_disease_stroke="No", kidney_stones="No", family_history="No",
                                                      heavy_outdoor_work="No", kidney_status="Never tested"))) + "\n")
    monkeypatch.setattr(api, "ANALYST_DIR", tmp_path)
    monkeypatch.setattr(api, "FIELD_SYNC_LOG_PATH", field_log)
    monkeypatch.setattr(api, "RISK_CHECK_LOG_PATH", tmp_path / "none.jsonl")
    overview = api.get_analyst_overview()
    calamba = next(m for m in overview["municipalities"] if m["name"] == "Calamba")
    assert calamba["checks"] == 61
    assert overview["summary"]["recorded_checks"] == {"total": 1, "by_channel": {"field": 1}}
    assert overview["built_with"] == {"git_commit": "x"}


def test_field_worker_batch_sync(tmp_path, monkeypatch):
    import api.main as api

    monkeypatch.setattr(api, "FIELD_SYNC_LOG_PATH", tmp_path / "field_sync_log.jsonl")
    req = BatchSyncRequest(
        checks=[
            {"id": "CHK-001", "barangay": "Makiling", "level": "High"},
            {"id": "CHK-002", "barangay": "Makiling", "level": "Low"},
        ]
    )
    res = batch_sync_checks(req)
    assert res["status"] == "success"
    assert res["synced_count"] == 2
    assert api.FIELD_SYNC_LOG_PATH.exists()


def test_analyst_endpoints_serve_built_data(tmp_path, monkeypatch):
    import json

    import api.main as api
    from fastapi import HTTPException

    monkeypatch.setattr(api, "ANALYST_DIR", tmp_path)
    with pytest.raises(HTTPException) as missing:
        api.get_analyst_overview()
    assert missing.value.status_code == 503

    (tmp_path / "overview.json").write_text(json.dumps(dict(province="Laguna", municipalities=[
        dict(name="Famy", checks=4, hidden=True, medium_high_share=None)])))
    (tmp_path / "climate.json").write_text(json.dumps(dict(period=dict(label="Okt 2025 – Set 2026"), note="Context only",
                                                           municipalities={"Biñan": dict(municipality="City of Biñan", series=[])})))
    overview = api.get_analyst_overview()
    assert "not individual medical diagnoses" in overview["disclaimer"]
    assert overview["municipalities"][0]["medium_high_share"] is None
    assert api.get_analyst_climate("City of Biñan")["name"] == "Biñan"
    with pytest.raises(HTTPException) as unknown:
        api.get_analyst_climate("Atlantis")
    assert unknown.value.status_code == 404
