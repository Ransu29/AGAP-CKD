"""PRD v3 risk level: simulator, answer mapping, floor, cut-offs, Thai score and leakage guard."""
import copy

import numpy as np
import pandas as pd
import pytest

from agap.config import load_config
from agap.models.leakage import LeakageError, check_allowed_features
from agap.simulate.kidney import observed_screen_label
from agap.simulate.risk_check import DONT_KNOW, calibrate_intercept, risk_check_cohort, simulate_population
from agap.triage import (FEATURES, encode_features, forbidden_features, guideline_floor, model_levels, set_cutoffs,
                         thai_levels, thai_points, thai_points_table2)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def population(cfg):
    return simulate_population(cfg, 20_000, np.random.default_rng(7))


def people(**columns):
    base = dict(age_group="18-39", sex="Male", diabetes="No", high_blood_pressure="No", bp_reading="Not measured",
                medicine="", heart_disease_stroke="No", kidney_stones="No", family_history="No",
                heavy_outdoor_work="No", bmi_reported=21.0, kidney_status="Never tested")
    length = max(len(v) for v in columns.values() if isinstance(v, list))
    return pd.DataFrame({k: columns.get(k, [v] * length) for k, v in base.items()})


def test_labs_follow_the_kidney_state_and_the_outcome_is_the_measured_screen(population):
    assert np.array_equal(observed_screen_label(population.egfr_true, population.uacr_true) == 1,
                          population.kidney_damage_true.to_numpy())
    assert np.array_equal(observed_screen_label(population.egfr, population.uacr) == 1, population.y_true.to_numpy())
    assert (population.y_true != population.kidney_damage_true).any()  # one measurement can misclassify


def test_calibrated_prevalence_matches_the_registered_target(cfg):
    share = simulate_population(cfg, 100_000, np.random.default_rng(11)).y_true.mean()
    assert share == pytest.approx(cfg["simulator"]["risk_check"]["target_prevalence"], abs=0.01)
    intercept, solved = calibrate_intercept(cfg, 0.08, 20_000, 5)
    assert solved == pytest.approx(0.08, abs=0.005) and intercept < cfg["simulator"]["risk_check"]["outcome_intercept"]


def test_people_already_told_something_was_wrong_never_enter_the_risk_check(cfg):
    cohort = risk_check_cohort(cfg, 3000, np.random.default_rng(3))
    assert len(cohort) == 3000 and not cohort.kidney_status.eq("Told something was wrong").any()


def test_simulation_is_deterministic_for_a_seed(cfg):
    first = simulate_population(cfg, 500, np.random.default_rng(1))
    second = simulate_population(cfg, 500, np.random.default_rng(1))
    pd.testing.assert_frame_equal(first, second)


def test_dont_know_enters_the_model_as_yes_for_diabetes_and_blood_pressure(cfg):
    frame = people(diabetes=["Yes", DONT_KNOW, "No", "No"], high_blood_pressure=["No", "No", DONT_KNOW, "No"],
                   bp_reading=["", "", "", "High"])
    X = encode_features(frame, cfg)
    assert X.diabetes_model.tolist() == [1, 1, 0, 0]
    assert X.hypertension_model.tolist() == [0, 0, 1, 1]
    assert list(X.columns) == FEATURES


def test_other_dont_know_answers_are_their_own_category_not_yes(cfg):
    frame = people(kidney_stones=["Yes", DONT_KNOW, "No"], bmi_reported=[30.0, np.nan, 24.0])
    X = encode_features(frame, cfg)
    assert X.kidney_stones_yes.tolist() == [1, 0, 0] and X.kidney_stones_unknown.tolist() == [0, 1, 0]
    assert X.bmi_obese.tolist() == [1, 0, 0] and X.bmi_unknown.tolist() == [0, 1, 0] and X.bmi_overweight.tolist() == [0, 0, 1]


def test_guideline_floor_rules_and_dont_know_never_trigger_it():
    frame = people(age_group=["18-39", "18-39", "18-39", "60-69", "18-39", "70+"],
                   diabetes=["Yes", "Yes", "No", "No", DONT_KNOW, DONT_KNOW],
                   high_blood_pressure=["No", "Yes", "No", "No", DONT_KNOW, "No"],
                   bp_reading=["", "", "High", "High", "", "Not measured"])
    assert guideline_floor(frame).tolist() == [1, 2, 1, 2, 0, 0]


def test_thai_points_follow_the_paper_and_cover_four_to_sixteen():
    frame = people(age_group=["18-39", "40-49", "60-69", "70+"], diabetes=["No", "Yes", "No", "Yes"],
                   high_blood_pressure=["No", "No", "Yes", "Yes"], kidney_stones=["No", "No", "No", "Yes"])
    points = thai_points(frame)
    assert points.tolist() == [4, 2 + 3 + 1 + 1, 4 + 1 + 2 + 1, 16]
    assert thai_levels(np.array([4, 5, 6, 8, 9, 16])).tolist() == [0, 0, 1, 1, 2, 2]


def test_cutoffs_meet_their_rules_and_high_exceeds_medium(cfg):
    rng = np.random.default_rng(0)
    p = rng.random(4000)
    y = rng.random(4000) < p ** 3
    cut = set_cutoffs(y, p, cfg)
    levels = model_levels(p, cut)
    assert y[levels >= 1].sum() / y.sum() >= 0.85 and cut["t_high"] > cut["t_medium"]
    assert y[levels == 2].mean() >= 2 * y.mean()
    with pytest.raises(ValueError, match="High cut-off"):
        set_cutoffs(np.r_[np.ones(20, bool), np.zeros(20, bool)], np.r_[np.full(20, .5), np.full(20, .5)], cfg)


def test_heat_labs_and_kidney_status_are_rejected_as_model_inputs(cfg):
    forbidden = forbidden_features(cfg)
    assert "hot_dry_score" not in cfg["models"]["forbidden_features"]  # still an allocation-model input
    for column in ("hot_dry_score", "community_heat", "egfr", "uacr", "y_true", "kidney_damage_true", "kidney_status"):
        with pytest.raises(LeakageError):
            check_allowed_features(FEATURES + [column], FEATURES + [column], forbidden)
    check_allowed_features(FEATURES, FEATURES, forbidden)


def test_reference_one_points_are_not_a_constant_shift_of_table_two():
    frame = people(age_group=["70+", "40-49"], diabetes=["No", "Yes"], high_blood_pressure=["No", "Yes"],
                   kidney_stones=["No", "Yes"])
    assert thai_points_table2(frame).tolist() == [8, 10]   # Table 2: the second person scores higher
    assert thai_points(frame).tolist() == [11, 10]         # 4-16 scheme: the order flips
