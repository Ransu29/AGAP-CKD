"""PRD v3 risk level: features, logistic model, cut-offs, guideline floor and Thai benchmark.

The model predicts the probability of an *abnormal kidney screen* (one measured eGFR < 60 or urine
ACR >= 30) from questionnaire answers only. Its output becomes a Low / Medium / High risk level,
which is never a diagnosis. Labs, hidden traits, kidney status and heat are never inputs
(config/params.yaml -> models.forbidden_features; ADR 0001).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from agap.models.leakage import check_allowed_features
from agap.simulate.risk_check import DONT_KNOW, calibrate_intercept, risk_check_cohort

LEVELS = ("Low", "Medium", "High")
AGE_FEATURES = {"40-49": "age_40_49", "50-59": "age_50_59", "60-69": "age_60_69", "70+": "age_70_plus"}
UNKNOWN_ITEMS = ("heart_disease_stroke", "kidney_stones", "family_history", "heavy_outdoor_work")
FEATURES = [*AGE_FEATURES.values(), "female", "diabetes_model", "hypertension_model",
            *[f"{item}_{answer}" for item in UNKNOWN_ITEMS for answer in ("yes", "unknown")],
            "bmi_overweight", "bmi_obese", "bmi_unknown"]
THAI_AGE_POINTS = {"18-39": 1, "40-49": 2, "50-59": 2, "60-69": 4, "70+": 8}
# Never risk-level inputs, on top of models.forbidden_features: heat (ADR 0001; the allocation pipeline's
# climate model still uses hot_dry_score) and kidney status, which only routes people to care.
RISK_LEVEL_EXCLUDED = ("hot_dry_score", "community_heat", "kidney_status")


def forbidden_features(cfg):
    return [*cfg["models"]["forbidden_features"], *RISK_LEVEL_EXCLUDED]


def rng_for(cfg, component):
    return np.random.default_rng(cfg["seed"] * 1000 + cfg["triage"]["risk_level"]["seed_components"][component])


def encode_features(cohort, cfg):
    """Questionnaire answers -> model inputs.

    Diabetes and high blood pressure: "I don't know" enters as Yes (PRD v3; self-report misses
    undiagnosed disease, Molenaar 2007). A "High" BP reading also counts as high blood pressure.
    Other items keep "I don't know" as its own category rather than an imputed value.
    """
    traits = cfg["simulator"]["risk_check"]["traits"]
    X = pd.DataFrame(index=cohort.index)
    for group, column in AGE_FEATURES.items():
        X[column] = cohort.age_group.eq(group)
    X["female"] = cohort.sex.eq("Female")
    X["diabetes_model"] = cohort.diabetes.isin(["Yes", DONT_KNOW])
    X["hypertension_model"] = cohort.high_blood_pressure.isin(["Yes", DONT_KNOW]) | cohort.bp_reading.eq("High")
    for item in UNKNOWN_ITEMS:
        X[f"{item}_yes"] = cohort[item].eq("Yes")
        X[f"{item}_unknown"] = cohort[item].eq(DONT_KNOW)
    bmi = cohort.bmi_reported
    X["bmi_overweight"] = bmi.ge(traits["bmi_overweight_cut"]) & bmi.lt(traits["bmi_obese_cut"])
    X["bmi_obese"] = bmi.ge(traits["bmi_obese_cut"])
    X["bmi_unknown"] = bmi.isna()
    X = X[FEATURES].astype(int)
    check_allowed_features(X.columns, FEATURES, forbidden_features(cfg))
    return X


def fit_model(X, y, cfg):
    model = LogisticRegression(C=cfg["triage"]["risk_level"]["l2_C"], max_iter=2000)
    return model.fit(X.to_numpy(float), np.asarray(y, int))


def coefficient_table(model, X, cfg):
    """Coefficients, odds ratios and 95% Wald intervals from the inverse penalized Hessian.

    scikit-learn's L2 penalty (strength 1/C) applies to the coefficients but not the intercept, so
    the Hessian adds 1/C to every diagonal element except the intercept's.
    """
    design = np.column_stack([np.ones(len(X)), X.to_numpy(float)])
    beta = np.concatenate([model.intercept_, model.coef_[0]])
    p = 1 / (1 + np.exp(-design @ beta))
    hessian = design.T @ (design * (p * (1 - p))[:, None])
    hessian[np.arange(1, len(beta)), np.arange(1, len(beta))] += 1 / cfg["triage"]["risk_level"]["l2_C"]
    se = np.sqrt(np.diag(np.linalg.inv(hessian)))
    table = pd.DataFrame(dict(term=["intercept", *X.columns], coefficient=beta, se=se))
    table["odds_ratio"] = np.exp(table.coefficient)
    table["or_low_95"] = np.exp(table.coefficient - 1.96 * table.se)
    table["or_high_95"] = np.exp(table.coefficient + 1.96 * table.se)
    return table


def set_cutoffs(y, p, cfg):
    """Validation cut-offs (PRD v3).

    Medium-or-High: the highest threshold whose Medium-or-High group still catches at least
    ``medium_min_sensitivity`` of abnormal screens. High: the lowest threshold above it whose High
    group has an abnormal rate of at least ``high_min_prevalence_multiple`` times the prevalence.
    Raises ValueError when no stable High threshold exists (the PRD fallback trigger).
    """
    rules = cfg["triage"]["risk_level"]
    y, p = np.asarray(y, bool), np.asarray(p, float)
    prevalence = y.mean()
    thresholds = np.unique(p)[::-1]
    sensitivity = np.array([y[p >= t].sum() / y.sum() for t in thresholds])
    t_medium = float(thresholds[np.flatnonzero(sensitivity >= rules["medium_min_sensitivity"])[0]])
    target = rules["high_min_prevalence_multiple"] * prevalence
    candidates = [t for t in thresholds[thresholds > t_medium]
                  if y[p >= t].sum() >= 30 and y[p >= t].mean() >= target]
    if not candidates:
        raise ValueError("No High cut-off reaches the required abnormal rate with at least 30 abnormal screens")
    t_high = float(min(candidates))
    if not t_high > t_medium:
        raise ValueError("High cut-off must exceed the Medium cut-off")
    return dict(t_medium=t_medium, t_high=t_high, prevalence=float(prevalence),
                medium_or_high_sensitivity=float(y[p >= t_medium].sum() / y.sum()),
                high_abnormal_rate=float(y[p >= t_high].mean()), high_target_rate=float(target))


def model_levels(p, cutoffs):
    p = np.asarray(p, float)
    return np.where(p >= cutoffs["t_high"], 2, np.where(p >= cutoffs["t_medium"], 1, 0))


def guideline_floor(cohort):
    """ADR 0002: diabetes or high BP (explicit Yes, or a High BP reading) -> at least Medium;
    both, or either with age 60 or older -> High. "I don't know" never triggers the floor."""
    dm = cohort.diabetes.eq("Yes").to_numpy()
    htn = (cohort.high_blood_pressure.eq("Yes") | cohort.bp_reading.eq("High")).to_numpy()
    older = cohort.age_group.isin(["60-69", "70+"]).to_numpy()
    return np.where((dm & htn) | ((dm | htn) & older), 2, np.where(dm | htn, 1, 0))


def floored(levels, floor):
    return np.maximum(np.asarray(levels), np.asarray(floor))


def floored_score(p, floor, cutoffs):
    """A continuous score consistent with the floored levels, for discrimination metrics."""
    minimum = np.where(np.asarray(floor) == 2, cutoffs["t_high"], np.where(np.asarray(floor) == 1, cutoffs["t_medium"], 0.0))
    return np.maximum(np.asarray(p, float), minimum)


def thai_points(cohort):
    """Thai simplified CKD score (Thakkinstian 2011), the 4-16 point scheme in which reference
    categories score 1: age < 40 = 1, 40-59 = 2, 60-69 = 4, >= 70 = 8; diabetes 3 vs 1;
    hypertension 2 vs 1; kidney stones 3 vs 1. Diabetes and hypertension use the same answer
    mapping as the AGAP model, so the comparison isolates the scoring method."""
    dm = cohort.diabetes.isin(["Yes", DONT_KNOW])
    htn = cohort.high_blood_pressure.isin(["Yes", DONT_KNOW]) | cohort.bp_reading.eq("High")
    return (cohort.age_group.map(THAI_AGE_POINTS) + np.where(dm, 3, 1) + np.where(htn, 2, 1)
            + np.where(cohort.kidney_stones.eq("Yes"), 3, 1)).to_numpy()


def thai_points_table2(cohort):
    """The paper's Table 2 points, with reference categories scored 0 (age < 40 = 0, 40-59 = 2,
    60-69 = 4, >= 70 = 8; diabetes 3; hypertension 2; kidney stones 3). Unlike a constant shift, the
    1-point references change the gap for each risk factor, so the two schemes can rank people
    differently; this one is reported as a sensitivity check of the benchmark's AUROC."""
    dm = cohort.diabetes.isin(["Yes", DONT_KNOW])
    htn = cohort.high_blood_pressure.isin(["Yes", DONT_KNOW]) | cohort.bp_reading.eq("High")
    age = cohort.age_group.map({"18-39": 0, "40-49": 2, "50-59": 2, "60-69": 4, "70+": 8})
    return (age + np.where(dm, 3, 0) + np.where(htn, 2, 0) + np.where(cohort.kidney_stones.eq("Yes"), 3, 0)).to_numpy()


def thai_levels(points):
    """The paper's four bands collapsed to three (a team choice): 4-5 Low; 6-8 Medium
    (intermediate-low); >= 9 High (intermediate-high and high)."""
    points = np.asarray(points)
    return np.where(points >= 9, 2, np.where(points >= 6, 1, 0))


def level_metrics(y, levels, score):
    y, levels = np.asarray(y, bool), np.asarray(levels)
    row = dict(auroc=roc_auc_score(y, score), sensitivity=float(y[levels >= 1].sum() / y.sum()),
               specificity=float((~y[levels == 0]).sum() / (~y).sum()), referred_share=float((levels >= 1).mean()))
    for code, name in enumerate(LEVELS):
        row[f"share_{name.lower()}"] = float((levels == code).mean())
        row[f"abnormal_rate_{name.lower()}"] = float(y[levels == code].mean()) if (levels == code).any() else np.nan
    return row


def rule_net_benefit(y, refer, threshold_probability):
    """Net benefit of a fixed referral rule (Vickers & Elkin) at one threshold probability."""
    y, refer = np.asarray(y, bool), np.asarray(refer, bool)
    odds = threshold_probability / (1 - threshold_probability)
    return float((refer & y).mean() - (refer & ~y).mean() * odds)


def benchmark(cohort, model, cutoffs, cfg):
    """Side-by-side metrics on one cohort for the Thai score, the model alone, and model + floor."""
    X = encode_features(cohort, cfg)
    p = model.predict_proba(X.to_numpy(float))[:, 1]
    y = cohort.y_true.to_numpy()
    levels = model_levels(p, cutoffs)
    floor = guideline_floor(cohort)
    points = thai_points(cohort)
    arms = {"Thai simplified score": (thai_levels(points), points),
            "AGAP model alone": (levels, p),
            "AGAP model + guideline floor": (floored(levels, floor), floored_score(p, floor, cutoffs))}
    rows = [dict(arm=name, **level_metrics(y, arm_levels, score)) for name, (arm_levels, score) in arms.items()]
    return pd.DataFrame(rows), dict(p=p, levels=levels, floor=floor, points=points, y=y)


def prevalence_sensitivity(model, cutoffs, cfg):
    """Re-simulate the validation cohort at other prevalences with the frozen model and cut-offs."""
    rules, rc = cfg["triage"]["risk_level"], cfg["simulator"]["risk_check"]
    rows = []
    for index, target in enumerate(rules["prevalence_scenarios"]):
        seed = cfg["seed"] * 1000 + rules["seed_components"]["sensitivity"]
        intercept, population_share = calibrate_intercept(cfg, target, min(rules["calibration_n"], 100_000), seed)
        cohort = risk_check_cohort(cfg, rules["n_validation"], np.random.default_rng(seed + 10 + index), intercept)
        table, _ = benchmark(cohort, model, cutoffs, cfg)
        for row in table.to_dict("records"):
            rows.append(dict(target_prevalence=target, outcome_intercept=intercept,
                             cohort_prevalence=float(cohort.y_true.mean()), **row))
    return pd.DataFrame(rows)


def train_and_evaluate(cfg):
    """The full PRD v3 retraining run, shared by scripts/train_triage.py and the notebook."""
    rules = cfg["triage"]["risk_level"]
    train = risk_check_cohort(cfg, rules["n_train"], rng_for(cfg, "train"))
    validation = risk_check_cohort(cfg, rules["n_validation"], rng_for(cfg, "validation"))
    test = risk_check_cohort(cfg, rules["n_test"], rng_for(cfg, "test"))
    X_train = encode_features(train, cfg)
    model = fit_model(X_train, train.y_true, cfg)
    X_validation = encode_features(validation, cfg)
    p_validation = model.predict_proba(X_validation.to_numpy(float))[:, 1]
    cutoffs = set_cutoffs(validation.y_true, p_validation, cfg)
    # Cut-offs are tuned on validation, so the benchmark is reported on the held-out test cohort.
    validation_table, _ = benchmark(validation, model, cutoffs, cfg)
    table, scored = benchmark(test, model, cutoffs, cfg)
    return dict(train=train, validation=validation, test=test, X_train=X_train, X_validation=X_validation, model=model,
                coefficients=coefficient_table(model, X_train, cfg), cutoffs=cutoffs, benchmark=table,
                validation_benchmark=validation_table, scored=scored)


def save_artifacts(result, cfg, sensitivity, directory, git_commit=None):
    """Write the frozen run's artifacts; features and labels go to separate files for the leakage scan."""
    import json

    import joblib

    from agap.experiment import fingerprint

    directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(dict(model=result["model"], features=FEATURES), directory / "model_clinical.joblib")
    cutoffs = dict(result["cutoffs"], config_fingerprint=fingerprint(cfg), git_commit=git_commit, seed=cfg["seed"],
                   n_train=len(result["train"]), n_validation=len(result["validation"]), n_test=len(result["test"]),
                   rules=cfg["triage"]["risk_level"],
                   floor="Diabetes or high BP (explicit Yes or High reading) -> at least Medium; both, or either with "
                         "age 60+ -> High. I don't know does not trigger the floor (ADR 0002).")
    (directory / "triage_cutoffs.json").write_text(json.dumps(cutoffs, indent=2))
    result["coefficients"].to_csv(directory / "triage_coefficients.csv", index=False)
    result["benchmark"].to_csv(directory / "triage_benchmark.csv", index=False)
    result["validation_benchmark"].to_csv(directory / "triage_benchmark_validation.csv", index=False)
    sensitivity.to_csv(directory / "triage_prevalence_sensitivity.csv", index=False)
    result["X_validation"].to_csv(directory / "validation_features.csv", index=False)
    result["validation"][["y_true"]].astype(int).to_csv(directory / "validation_labels.csv", index=False)
    scored = result["scored"]
    pd.DataFrame(dict(y_true=scored["y"].astype(int), y_prob=scored["p"])).to_csv(directory / "triage_dca_model.csv", index=False)
    # The Thai score gives points, not probabilities: map them with a logistic fit on the same (test) cohort.
    points = scored["points"].reshape(-1, 1)
    thai_p = LogisticRegression().fit(points, scored["y"]).predict_proba(points)[:, 1]
    pd.DataFrame(dict(y_true=scored["y"].astype(int), y_prob=thai_p)).to_csv(directory / "triage_dca_thai.csv", index=False)
    return cutoffs
