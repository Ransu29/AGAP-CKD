"""SIM-09 longitudinal scenario: follow-up measurements, acute events, persistence and SIM-10."""
import numpy as np
import pandas as pd
import pytest

from agap.config import load_config
from agap.experiment import CLINICAL, allocate, build_data, simulate, train
from agap.longitudinal import (
    DEFAULTS, acute_probability, followup_columns, followup_metrics, longitudinal, persistence_by_plan, simulate_followup,
)
from agap.models.leakage import LeakageError, check_allowed_features, check_no_leakage
from agap.simulate.kidney import ckd_epi_2021, creatinine_for_egfr


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    cfg = load_config()
    cfg["prototype"].update(n_train=2000, n_validation=800, n_deployment=1200)
    directory = tmp_path_factory.mktemp("run")
    for stage in (build_data, simulate, train, allocate):
        stage(cfg, directory)
    followup, metrics = longitudinal(cfg, directory)
    return cfg, pd.read_parquet(directory / "deployment_hidden.parquet"), followup, metrics


def residents(count=200, seed=0):
    rng = np.random.default_rng(seed)
    female = np.arange(count) % 2 == 0
    age = rng.integers(25, 80, count)
    egfr = rng.uniform(35, 110, count)
    creatinine = creatinine_for_egfr(egfr, age, female)
    uacr = rng.lognormal(np.log(20), .8, count)
    egfr = ckd_epi_2021(creatinine, age, female)
    return pd.DataFrame(dict(resident_id=[f"SYN-T-{i:04d}" for i in range(count)], cutoff=pd.Timestamp("2025-03-01"),
                             era5_cell="14.2,121.2", age=age, female=female, creatinine=creatinine, uacr=uacr, egfr=egfr,
                             y_true=(egfr < 60) | (uacr >= 30), dm_true=False, htn_true=False))


def no_change(**overrides):
    return {**DEFAULTS, "creatinine_cv": 0.0, "uacr_cv": 0.0, "egfr_decline_per_year": 0.0, "acute_event_rate": 1e-12, **overrides}


def test_day0_is_unchanged_and_followup_egfr_uses_ckd_epi(run):
    _, deployment, followup, _ = run
    for column in ("creatinine", "uacr", "egfr", "y_true"):
        assert followup[column].equals(deployment[column])
    for day in DEFAULTS["followup_days"]:
        assert np.allclose(followup[f"egfr_{day}d"], ckd_epi_2021(followup[f"creatinine_{day}d"], followup.age, followup.female))


def test_without_variability_decline_or_events_followup_equals_day0():
    frame = residents()
    prototype = load_config()["prototype"] | {"heat_or": 1.0}
    hot = {day: np.zeros(len(frame)) for day in DEFAULTS["followup_days"]}
    followup = simulate_followup(frame, hot, prototype, no_change(), np.random.default_rng(0))
    for day in DEFAULTS["followup_days"]:
        assert np.allclose(followup[f"creatinine_{day}d"], frame.creatinine)
        assert np.allclose(followup[f"uacr_{day}d"], frame.uacr)
    assert followup.persistent_abnormal.sum() == frame.y_true.sum() and not followup.transient_abnormal.any()


def test_acute_event_raises_creatinine_at_that_visit_only():
    frame = residents()
    prototype = load_config()["prototype"] | {"heat_or": 3.0}
    hot = {90: np.full(len(frame), 40.0), 180: np.full(len(frame), -40.0)}
    followup = simulate_followup(frame, hot, prototype, no_change(acute_event_rate=.5), np.random.default_rng(0))
    assert followup.hypothetical_acute_event_90d.all() and not followup.hypothetical_acute_event_180d.any()
    assert np.allclose(followup.creatinine_90d, frame.creatinine * DEFAULTS["acute_creatinine_factor"])
    assert np.allclose(followup.creatinine_180d, frame.creatinine)


def test_zero_heat_effect_makes_acute_risk_independent_of_climate():
    frame = residents()
    prototype = load_config()["prototype"] | {"heat_or": 1.0}
    hot = acute_probability(frame, np.full(len(frame), 3.0), prototype, DEFAULTS)
    cool = acute_probability(frame, np.full(len(frame), -3.0), prototype, DEFAULTS)
    assert np.array_equal(hot, cool)
    reference = acute_probability(frame.assign(age=40), np.zeros(len(frame)), prototype, DEFAULTS)
    assert np.allclose(reference, DEFAULTS["acute_event_rate"])


def test_missing_climate_window_excludes_resident_without_shifting_draws():
    frame = residents()
    prototype = load_config()["prototype"]
    hot = {day: np.zeros(len(frame)) for day in DEFAULTS["followup_days"]}
    gap = {day: values.copy() for day, values in hot.items()}
    gap[180][0] = np.nan
    full = simulate_followup(frame, hot, prototype, DEFAULTS, np.random.default_rng(5))
    partial = simulate_followup(frame, gap, prototype, DEFAULTS, np.random.default_rng(5))
    assert not partial.followup_included.iloc[0] and partial.followup_included.iloc[1:].all()
    assert not partial.persistent_abnormal.iloc[0] and not partial.transient_abnormal.iloc[0]
    assert np.array_equal(full.creatinine_180d.iloc[1:], partial.creatinine_180d.iloc[1:])


def test_followup_counts_reconcile_by_policy(run):
    _, _, followup, metrics = run
    assert (metrics.hidden_persistent_detected + metrics.hidden_transient_detected == metrics.initial_positives_detected).all()
    assert (metrics.followup_invited == metrics.initial_positives_detected).all()
    assert (metrics.observed_persistent + metrics.observed_transient + metrics.observed_unknown == metrics.followup_invited).all()
    assert (metrics.day180_completed == metrics.observed_persistent + metrics.observed_transient).all()
    assert (metrics.population_persistent_positives == followup.persistent_abnormal.sum()).all()
    expected = followup.y_true & followup.abnormal_180d & followup.followup_included
    assert followup.persistent_abnormal.equals(expected)


def test_only_completed_abnormal_initial_tests_are_followed_up():
    frame = residents(6)
    frame["y_true"] = [True, True, False, False, True, True]
    followup = simulate_followup(frame, {day: np.zeros(6) for day in DEFAULTS["followup_days"]},
                                 load_config()["prototype"], DEFAULTS, np.random.default_rng(0))
    allocations = pd.DataFrame(dict(policy="p", resident_id=frame.resident_id, completed=[True, False, True, False, True, True]))
    metrics = followup_metrics(followup, allocations, np.ones(6), DEFAULTS).iloc[0]
    assert metrics.followup_invited == 3 and metrics.day180_completed == 3 and metrics.observed_unknown == 0
    never = followup_metrics(followup, allocations, np.zeros(6), DEFAULTS).iloc[0]
    assert never.day90_completed == never.day180_completed == 0 and never.observed_unknown == 3


def test_followup_columns_are_forbidden_model_inputs(run):
    cfg = run[0]
    forbidden = cfg["models"]["forbidden_features"]
    assert set(followup_columns()) <= set(forbidden)
    with pytest.raises(LeakageError):
        check_allowed_features(CLINICAL + ["egfr_180d"], CLINICAL + ["egfr_180d"], forbidden)
    with pytest.raises(LeakageError):
        check_no_leakage(["Persistent_Abnormal"], forbidden)


def test_persistence_by_plan_counts_found_positives_only():
    followup = pd.DataFrame(dict(resident_id=list("abcde"), followup_included=[True, True, True, False, True],
                                 persistent_abnormal=[True, False, False, True, False],
                                 transient_abnormal=[False, True, False, False, False]))
    plan = lambda found: pd.DataFrame(dict(resident_id=list("abcde"), positive_detected=found))
    table = persistence_by_plan((("Random", plan([True, False, False, True, False])),
                                 ("Ranked", plan([True, True, False, False, False]))), followup).set_index("Plan")
    assert table.loc["Random"].tolist() == [1, 1, 0]  # d is outside the follow-up climate window
    assert table.loc["Ranked"].tolist() == [2, 1, 1]
    assert list(table.columns) == ["Abnormal initial results found", "Still abnormal at 180 days", "Normal again at 180 days"]
