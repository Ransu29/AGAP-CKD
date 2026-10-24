"""PRD v3 single-person risk check: shared scoring (ADR 0003), next steps, reasons, tips and facilities."""
import copy
from datetime import date

import numpy as np
import pandas as pd
import pytest

from agap.analyst import simulate_checks
from agap.config import ROOT, load_config
from agap.risk_check_service import (Answers, FrozenModel, blood_sugar_prompt, evaluate, load_context, next_step,
                                     reasons, score_frame, tips)
from agap.simulate.risk_check import DONT_KNOW, risk_check_cohort
from agap.triage import LEVELS, encode_features, fit_model

LAGUNA = ROOT / "data/processed/public/laguna"
TODAY = date(2026, 10, 24)
CUTOFFS = dict(t_medium=0.07, t_high=0.12)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def frozen(cfg):
    train = risk_check_cohort(cfg, 3000, np.random.default_rng(3))
    return FrozenModel(fit_model(encode_features(train, cfg), train.y_true, cfg), dict(CUTOFFS))


@pytest.fixture(scope="module")
def context(cfg):
    return load_context(LAGUNA, cfg)


def person(**overrides):
    base = dict(age_group="18-39", sex="Female", municipality="City of Calamba", diabetes="No", high_blood_pressure="No",
                heart_disease_stroke="No", kidney_stones="No", family_history="No", heavy_outdoor_work="No",
                kidney_status="Never tested", bp_reading="Normal", height_cm=160, weight_kg=50)
    return Answers(**{**base, **overrides})


def row(answers):
    return answers.to_frame().iloc[0]


def test_app_and_analyst_score_identically(cfg, frozen):
    """ADR 0003: an analyst-view check and the same answers sent through the app get the same level."""
    local = copy.deepcopy(cfg)
    local["simulator"]["analyst_checks"]["total_checks"] = 200
    adults = pd.read_csv(LAGUNA / "municipal_adults.csv")
    checks = simulate_checks(local, adults, frozen.model, frozen.cutoffs)
    for record in checks.head(60).to_dict("records"):
        answers = Answers(age_group=record["age_group"], sex=record["sex"], municipality=record["municipality"],
                          diabetes=record["diabetes"], high_blood_pressure=record["high_blood_pressure"],
                          heart_disease_stroke=record["heart_disease_stroke"], kidney_stones=record["kidney_stones"],
                          family_history=record["family_history"], heavy_outdoor_work=record["heavy_outdoor_work"],
                          kidney_status=record["kidney_status"], medicine=record["medicine"] or None,
                          bp_reading=record["bp_reading"] or None)
        frame = answers.to_frame()
        frame["bmi_reported"] = record["bmi_reported"]
        level, _, _ = score_frame(frame, frozen.model, frozen.cutoffs, cfg)
        assert LEVELS[int(level[0])] == record["risk_level"]


def test_dont_know_raises_the_model_but_never_triggers_the_floor(cfg, frozen):
    _, model_no, floor_no = score_frame(person().to_frame(), frozen.model, frozen.cutoffs, cfg)
    frame = person(diabetes=DONT_KNOW, high_blood_pressure=DONT_KNOW, bp_reading=DONT_KNOW).to_frame()
    p_no = frozen.model.predict_proba(encode_features(person().to_frame(), cfg).to_numpy(float))[0, 1]
    p_dk = frozen.model.predict_proba(encode_features(frame, cfg).to_numpy(float))[0, 1]
    _, _, floor_dk = score_frame(frame, frozen.model, frozen.cutoffs, cfg)
    assert p_dk > p_no
    assert floor_dk[0] == 0 == floor_no[0]


def test_branching_blanks_items_that_were_not_shown():
    frame = person(high_blood_pressure="Yes", bp_reading="High", medicine="Stopped").to_frame()
    assert frame.bp_reading[0] == "" and frame.medicine[0] == "Stopped"
    assert person(medicine="Stopped").to_frame().medicine[0] == ""
    assert np.isnan(person(height_cm=None).to_frame().bmi_reported[0])


@pytest.mark.parametrize("level, answers, code, check_months, test_months", [
    ("Low", person(), "recheck", 36, None),                                   # 18-39, no risk factors, BP normal
    ("Low", person(bp_reading="Not measured"), "recheck", 12, None),          # 3 years needs a normal reading
    ("Low", person(age_group="40-49"), "recheck", 12, None),                  # aged 40+
    ("Low", person(family_history="Yes"), "recheck", 12, None),               # any risk factor
    ("Medium", person(kidney_stones="Yes"), "bp_sugar_first", None, None),    # no diabetes or high BP
    ("Medium", person(diabetes=DONT_KNOW), "bp_sugar_first", None, None),     # I don't know is not "with diabetes"
    ("Medium", person(diabetes="Yes"), "kidney_test", None, 12),
    ("High", person(high_blood_pressure="Yes"), "kidney_test", None, 12),
    ("High", person(age_group="70+", kidney_stones="Yes"), "kidney_test", None, 12),
])
def test_next_step_follows_the_prd_interval_table(cfg, level, answers, code, check_months, test_months):
    step = next_step(level, row(answers), cfg, TODAY)
    assert step["code"] == code
    expected = lambda months: None if months is None else f"{2026 + (9 + months) // 12}-{(9 + months) % 12 + 1:02d}"
    assert step["next_check"] == expected(check_months)
    assert step["next_kidney_test"] == expected(test_months)
    assert step["soon"] == (level == "High")


def test_people_without_risk_factors_never_get_a_kidney_test(cfg, frozen, context):
    for age in ("18-39", "40-49"):
        result = evaluate(person(age_group=age), "No", frozen, context, cfg, TODAY)
        if result["level"] == "Medium":
            assert result["next_step"]["code"] == "bp_sugar_first"
        assert result["next_step"]["code"] != "kidney_test"


def test_blood_sugar_prompt(cfg):
    assert blood_sugar_prompt(row(person(age_group="40-49")), cfg)
    assert blood_sugar_prompt(row(person(weight_kg=70)), cfg)                # BMI 27.3
    assert not blood_sugar_prompt(row(person()), cfg)
    assert not blood_sugar_prompt(row(person(age_group="60-69", diabetes="Yes")), cfg)


def test_reasons_and_tips_follow_priority(cfg):
    answers = row(person(diabetes="Yes", medicine="Stopped", age_group="60-69", weight_kg=80, heavy_outdoor_work="Yes"))
    assert reasons(answers, cfg) == ["diabetes", "age_group", "obese"]
    assert tips(answers, cfg, heat_card=True) == ["keep_medicine", "diabetes_care", "weight_activity", "avoid_painkillers"]
    assert "water_shade" in tips(row(person(heavy_outdoor_work="Yes")), cfg, heat_card=False)
    assert reasons(row(person()), cfg) == ["age_group"]


def test_results_carry_no_probability_and_routes_skip_the_level(cfg, frozen, context):
    result = evaluate(person(), "No", frozen, context, cfg, TODAY)
    assert "probability" not in str(result).lower()
    assert evaluate(person(), "Yes", frozen, context, cfg, TODAY)["route"] == "see_doctor"
    assert evaluate(person(), DONT_KNOW, frozen, context, cfg, TODAY)["route"] == "result"
    diagnosed = evaluate(person(kidney_status="Told something was wrong"), "No", frozen, context, cfg, TODAY)
    assert diagnosed["route"] == "already_diagnosed" and "level" not in diagnosed


def test_heat_never_changes_the_level(cfg, frozen, context):
    indoor = evaluate(person(), "No", frozen, context, cfg, TODAY)
    hot = copy.copy(context)
    hot.recent_hot_days = {"City of Calamba": 12.0}
    assert evaluate(person(), "No", frozen, hot, cfg, TODAY)["level"] == indoor["level"]
    assert evaluate(person(), "No", frozen, hot, cfg, TODAY)["heat_advisory"]["show"]


def test_facilities_fall_back_to_the_nearest_town(context):
    victoria = context.facilities_for("Victoria")
    assert victoria["shown_from"] is not None and victoria["facilities"]
    calamba = context.facilities_for("City of Calamba", limit=3)
    assert calamba["shown_from"] is None and len(calamba["facilities"]) == 3
    assert {f["kidney_tests"] for f in calamba["facilities"]} == {"Unknown"}
