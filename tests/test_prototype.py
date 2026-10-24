import copy
from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd
import pytest

from agap.config import load_config
from agap.demo import compare_plans, load_demo, report_preview, with_report
from agap.data.geography import make_geography
from agap.experiment import MODELS, allocation_metrics, allocate_policy, build_data, simulate, train
from agap.models.leakage import LeakageError, check_allowed_features
from agap.reports import append_report, normalize_report, parse_sms, reports_at
from agap.simulate.kidney import observed_screen_label


@pytest.mark.parametrize("egfr,uacr,expected", [(90,10,0), (55,10,1), (60,29.9,0), (90,30,1),
                                               (np.nan,10,np.nan), (np.nan,30,1), (55,np.nan,1),
                                               (90,np.nan,np.nan), (np.nan,np.nan,np.nan)])
def test_observed_labels(egfr, uacr, expected):
    actual = observed_screen_label(egfr, uacr)
    assert np.isnan(actual) if np.isnan(expected) else actual == expected


def test_transport_equivalence_and_bad_inputs():
    form, errors = normalize_report("SYN-DEMO", 45, dict(DM="Y", HTN="N", FAM="U", OUT="Y"))
    sms, sms_errors = parse_sms("AGAP SYN-DEMO 45 DM:Y HTN:N FAM:U OUT:Y")
    assert not errors and not sms_errors and form == sms
    assert parse_sms("AGAP SYN-DEMO 45 DM:Y DM:N HTN:N FAM:U OUT:Y")[1]
    assert normalize_report("SYN-DEMO", "18.5", dict(DM="N", HTN="N", FAM="U", OUT="Y"))[1]
    assert normalize_report("Real Name", 45, dict(DM="N", HTN="N", FAM="U", OUT="Y"))[1]


def test_revisions_preserve_historical_cutoff(tmp_path):
    path = tmp_path / "reports.jsonl"
    first, _ = normalize_report("SYN-DEMO", 45, dict(DM="Y", HTN="N", FAM="U", OUT="Y"))
    initial, created = append_report(path, first, [], "form")
    assert created
    assert not append_report(path, first, [], "sms")[1]
    second = dict(first, DM="N")
    correction, created = append_report(path, second, [], "form")
    assert created and correction["supersedes"] == initial["report_id"]
    assert reports_at(path, initial["available_at"])[0]["payload"]["DM"] == "Y"
    assert reports_at(path, correction["available_at"])[0]["payload"]["DM"] == "N"


@pytest.fixture(scope="module")
def trial(tmp_path_factory):
    cfg = load_config()
    cfg["prototype"].update(n_train=2000, n_validation=800, n_deployment=1200)
    cfg["allocation"].update(budget_tests=100, slots_per_facility=25)
    directory = tmp_path_factory.mktemp("trial")
    cells, demographics, facilities = build_data(cfg, directory)
    frames = simulate(cfg, directory)
    return cfg, directory, frames, facilities


def test_observation_and_holdout_contracts(trial):
    cfg, directory, frames, facilities = trial
    train_frame, validation, deployment = (frames[name] for name in ("train", "validation", "deployment"))
    assert set(train_frame.era5_cell).isdisjoint(deployment.era5_cell)
    assert set(train_frame.resident_id).isdisjoint(deployment.resident_id)
    assert train_frame.cutoff.max() < validation.cutoff.min() < deployment.cutoff.min()
    assert not (train_frame.round0_completed & ~train_frame.round0_invited).any()
    assert (train_frame.observation_probability > 0).all()
    assert train_frame.loc[~train_frame.reported, "dm_report"].isna().all()
    assert deployment.observed_label.isna().all()
    assert train_frame.loc[~train_frame.reported, "round0_completed"].any()


def test_models_score_every_resident_without_hidden_features(trial):
    cfg, directory, frames, facilities = trial
    train(cfg, directory)
    predictions = pd.read_parquet(directory / "predictions.parquet")
    assert np.isfinite(predictions.score).all()
    assert len(predictions) == len(frames["deployment"]) * len(MODELS) * 2
    assert not any(column in predictions for column in ("y_true", "uacr", "creatinine"))
    with pytest.raises(LeakageError):
        check_allowed_features(["age", "research_interest"], ["age"])


def test_allocation_budget_capacity_pairing_and_accounting(trial):
    cfg, directory, frames, facilities = trial
    deployment = frames["deployment"]
    scores = np.linspace(.01, .9, len(deployment))
    result = allocate_policy(cfg, deployment, facilities, scores, "risk_ranked", .2)
    repeat = allocate_policy(cfg, deployment, facilities, scores, "risk_ranked", .2)
    pd.testing.assert_frame_equal(result, repeat)
    assert result.invited.sum() <= cfg["allocation"]["budget_tests"]
    assert not (result.completed & ~result.invited).any()
    assert result.loc[result.invited, "distance_km"].le(cfg["allocation"]["max_distance_km"]).all()
    assigned = result[result.invited].groupby("facility_id").size()
    assert assigned.le(facilities.set_index("facility_id").capacity.reindex(assigned.index)).all()
    metric = allocation_metrics(result, cfg).query("subgroup == 'all'").iloc[0]
    assert metric.eligible_positives == metric.access_excluded_positives + metric.not_invited_feasible_positives + metric.incomplete_positives + metric.positives_detected
    modified = deployment.assign(research_interest="withdrawn")
    pd.testing.assert_frame_equal(result, allocate_policy(cfg, modified, facilities, scores, "risk_ranked", .2))


def test_zero_budget_reports_undefined_yield(trial):
    cfg, directory, frames, facilities = trial
    cfg = copy.deepcopy(cfg)
    cfg["allocation"]["budget_tests"] = 0
    result = allocate_policy(cfg, frames["deployment"], facilities, np.full(len(frames["deployment"]), .2), "random")
    metric = allocation_metrics(result, cfg).query("subgroup == 'all'").iloc[0]
    assert metric.invitations == 0 and np.isnan(metric.positives_per_100_completed)


def test_report_preview_changes_only_available_information(trial):
    cfg, directory, frames, facilities = trial
    original = frames["deployment"]
    person = original.loc[~original.reported].iloc[0]
    payload = dict(resident_id=person.resident_id, age=int(person.age), DM="Y", HTN="N", FAM="U", OUT="U")
    updated = with_report(original, payload)
    selected = updated.resident_id == person.resident_id
    assert updated.loc[selected, "dm_report"].iloc[0] == 1
    assert updated.loc[selected, "htn_report"].iloc[0] == 0
    assert updated.loc[selected, "family_report"].isna().all()
    assert updated.loc[selected, "reported"].all()
    pd.testing.assert_frame_equal(updated[~selected], original[~selected])
    pd.testing.assert_frame_equal(updated[["y_true", "dm_true", "egfr", "uacr", "cutoff"]], original[["y_true", "dm_true", "egfr", "uacr", "cutoff"]])
    assert not original.loc[selected, "reported"].any()


def test_connected_report_and_budget_preview_preserve_saved_results(trial):
    cfg, directory, frames, facilities = trial
    train(cfg, directory)
    frame, facilities, model, scores = load_demo(directory)
    prediction_file = directory / "predictions.parquet"
    saved_bytes = prediction_file.read_bytes()
    predictions = pd.read_parquet(prediction_file).query("model == 'clinical' and target_sensitivity == .9")
    np.testing.assert_allclose(scores, predictions.score)
    person = frame.loc[~frame.reported].iloc[0]
    payload = dict(resident_id=person.resident_id, age=int(person.age), DM="Y", HTN="Y", FAM="U", OUT="U")
    preview = report_preview(frame, facilities, model, scores, cfg, 100, "Priority + random outreach", payload)
    assert len(preview["updated"]["proposed"]) == len(frame)
    assert preview["updated"]["proposed_summary"]["invitations"] <= 100
    assert preview["updated"]["proposed"].set_index("resident_id").loc[person.resident_id, "reported"]
    lower_budget = compare_plans(frame, facilities, scores, cfg, 25, "Prioritize higher scores")
    assert lower_budget["proposed_summary"]["invitations"] <= 25
    assert prediction_file.read_bytes() == saved_bytes
    with pytest.raises(ValueError, match="known age"):
        with_report(frame, dict(payload, age=payload["age"] + 1))
