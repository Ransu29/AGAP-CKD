"""PRD v3 risk-check development cohort: synthetic adults with questionnaire answers and labs.

Everyone in the cohort has a kidney test, as in the population surveys behind the Thai simplified
score (Thakkinstian 2011), SCORED (Bang 2007) and the Long An study (Tran 2017). The outcome is the
*abnormal kidney screen*: a single measured eGFR < 60 or urine ACR >= 30. It is a screening
outcome, never a diagnosis; chronic kidney disease needs abnormality persisting over 3 months.

Generation order:
1. Age group (Laguna adult shares), exact age within the group, and sex.
2. True traits: diabetes and hypertension (the existing age-dependent generators), heart disease
   or stroke, kidney stones, family history, heavy outdoor work, BMI, medicine use, and a synthetic
   community heat exposure.
3. Underlying kidney state from a logistic model on those traits; the odds ratios are registered
   in config/parameter_register.yaml.
4. Underlying labs consistent with that state (truncated, continuous draws), then one day-0
   measurement with within-person variability. The measured result defines the outcome.
5. Self-reported answers, including "I don't know", from the true traits and diagnosis awareness.
6. Kidney status; people already told something was wrong are routed out of the risk check.

Community heat enters outcome generation only. ADR 0001 keeps it out of the risk level, so the
fitted model omits a true (assumed) effect by design.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import truncnorm

from agap.simulate.kidney import ckd_epi_2021, creatinine_for_egfr, observed_screen_label

DONT_KNOW = "I don't know"
YES_NO = ("Yes", "No", DONT_KNOW)
BP_READINGS = ("Normal", "High", "Not measured", DONT_KNOW)
MEDICINE = ("Regularly", "Sometimes miss", "Stopped", "No medicine given", DONT_KNOW)
KIDNEY_STATUS = ("Never tested", "Tested normal in the past 12 months", "Told something was wrong", DONT_KNOW)
# Columns that describe the hidden truth or the lab outcome. All are forbidden model inputs.
HIDDEN_COLUMNS = ("age", "dm_true", "htn_true", "heart_true", "stones_true", "family_true", "outdoor_true",
                  "bmi", "dm_aware", "htn_aware", "medicine_true", "community_heat", "kidney_damage_true",
                  "creatinine_true", "egfr_true", "uacr_true", "creatinine", "egfr", "uacr", "y_true")


def measurement_factor(rng, cv, size):
    """Mean-one log-normal within-person variability factor with coefficient of variation ``cv``."""
    sigma = np.sqrt(np.log1p(cv ** 2))
    return np.exp(rng.normal(-sigma ** 2 / 2, sigma, size))


def _answer(rng, true, aware, unaware_dk, negative_dk):
    """Self-report: aware cases say Yes; unaware cases say I don't know or No; others mostly No."""
    draw = rng.random(len(true))
    return np.where(true & aware, "Yes",
                    np.where(true, np.where(draw < unaware_dk, DONT_KNOW, "No"),
                             np.where(draw < negative_dk, DONT_KNOW, "No")))


def _simple_answer(rng, true, dont_know):
    draw = rng.random(len(true))
    return np.where(draw < dont_know, DONT_KNOW, np.where(true, "Yes", "No"))


def simulate_population(cfg, n, rng, intercept=None):
    """``n`` synthetic Laguna adults with traits, answers and one measured kidney screen."""
    sim = cfg["simulator"]
    rc = sim["risk_check"]
    traits, report, odds = rc["traits"], rc["reporting"], rc["odds_ratios"]
    groups = np.array(rc["age_groups"])
    shares = np.asarray(rc["age_group_shares"], float)
    group_index = rng.choice(len(groups), n, p=shares / shares.sum())
    bounds = np.asarray(rc["age_group_bounds"])
    age = rng.integers(bounds[group_index, 0], bounds[group_index, 1] + 1)
    female = rng.random(n) < rc["female_share"]
    centre = sim["age_center"]
    base = sim["traits"]
    dm = rng.random(n) < expit(base["dm_intercept"] + base["dm_log_odds_per_year"] * (age - centre))
    htn = rng.random(n) < expit(base["htn_intercept"] + base["htn_log_odds_per_year"] * (age - centre)
                                + base["htn_dm_log_odds"] * dm)
    heart = rng.random(n) < expit(traits["heart_disease_intercept"] + traits["heart_disease_log_odds_per_year"] * (age - centre))
    stones = rng.random(n) < traits["kidney_stone_prevalence"]
    family = rng.random(n) < base["family_history_prevalence"]
    outdoor = rng.random(n) < base["outdoor_work_prevalence"]
    bmi = rng.normal(traits["bmi_mean"], traits["bmi_sd"], n).clip(14, 60)
    overweight = (bmi >= traits["bmi_overweight_cut"]) & (bmi < traits["bmi_obese_cut"])
    obese = bmi >= traits["bmi_obese_cut"]
    dm_aware = dm & (rng.random(n) < report["dm_awareness"])
    htn_aware = htn & (rng.random(n) < report["htn_awareness"])
    medicine_shares = np.asarray(report["medicine_shares"], float)
    medicine = np.where(dm_aware | htn_aware,
                        np.array(MEDICINE[:4])[rng.choice(4, n, p=medicine_shares / medicine_shares.sum())],
                        "No medicine given")
    heat = rng.normal(0, 1, n)
    log_or = {name: np.log(value) for name, value in odds.items()}
    linear = ((rc["outcome_intercept"] if intercept is None else intercept)
              + log_or["age_40_49"] * (groups[group_index] == "40-49") + log_or["age_50_59"] * (groups[group_index] == "50-59")
              + log_or["age_60_69"] * (groups[group_index] == "60-69") + log_or["age_70_plus"] * (groups[group_index] == "70+")
              + log_or["female"] * female + log_or["diabetes"] * dm + log_or["hypertension"] * htn
              + log_or["kidney_stones"] * stones + log_or["heart_disease_stroke"] * heart
              + log_or["family_history"] * family + log_or["overweight"] * overweight + log_or["obese"] * obese
              + log_or["stopped_medicine"] * (medicine == "Stopped") + log_or["heavy_outdoor_work"] * outdoor
              + log_or["community_heat_per_sd"] * heat)
    damage = rng.random(n) < expit(linear)
    # Underlying labs consistent with the kidney state (truncated, not capped, draws).
    lab, rc_lab = sim["laboratory"], rc["laboratory"]
    subtype = rng.random(n)
    renal = damage & (subtype < lab["renal_subtype_share"])
    albumin = damage & (subtype >= lab["albumin_subtype_start"])
    low, high = rc_lab["normal_egfr_range"]
    mean, sd = rc_lab["normal_egfr_mean"], rc_lab["normal_egfr_sd"]
    normal_gfr = truncnorm.rvs((low - mean) / sd, (high - mean) / sd, loc=mean, scale=sd, size=n, random_state=rng)
    target_gfr = np.where(renal, rng.uniform(*lab["abnormal_egfr_range"], n), normal_gfr)
    creatinine_true = creatinine_for_egfr(target_gfr, age, female)
    egfr_true = ckd_epi_2021(creatinine_true, age, female)
    log_sd, threshold = lab["uacr_log_sd"], cfg["outcome"]["uacr_threshold"]
    abnormal_log, normal_log = np.log(lab["abnormal_uacr_median"]), np.log(lab["normal_uacr_median"])
    abnormal_uacr = np.exp(truncnorm.rvs((np.log(threshold) - abnormal_log) / log_sd, np.inf, loc=abnormal_log,
                                         scale=log_sd, size=n, random_state=rng))
    normal_uacr = np.exp(truncnorm.rvs(-np.inf, (np.log(lab["normal_uacr_max"]) - normal_log) / log_sd, loc=normal_log,
                                       scale=log_sd, size=n, random_state=rng))
    uacr_true = np.where(albumin, abnormal_uacr, normal_uacr)
    if not np.array_equal(observed_screen_label(egfr_true, uacr_true) == 1, damage):
        raise ValueError("Underlying labs are inconsistent with the kidney state")
    # One day-0 measurement with within-person variability (creatinine CV 5%, uACR CV 30%).
    variability = cfg["longitudinal"]
    creatinine = creatinine_true * measurement_factor(rng, variability["creatinine_cv"], n)
    egfr = ckd_epi_2021(creatinine, age, female)
    uacr = uacr_true * measurement_factor(rng, variability["uacr_cv"], n)
    y_true = observed_screen_label(egfr, uacr, cfg["outcome"]["egfr_threshold"], threshold) == 1
    # Self-reported answers.
    dm_answer = _answer(rng, dm, dm_aware, report["unaware_dont_know"], report["negative_dont_know"])
    htn_answer = _answer(rng, htn, htn_aware, report["unaware_dont_know"], report["negative_dont_know"])
    measured = rng.random(n) < report["bp_measured_past_year"]
    bp_reading = np.where(htn_answer == "Yes", "", np.where(measured, np.where(htn, "High", "Normal"), "Not measured"))
    medicine_answer = np.where((dm_answer == "Yes") | (htn_answer == "Yes"), medicine, "")
    other_dk = report["other_item_dont_know"]
    bmi_answer = np.where(rng.random(n) < report["bmi_dont_know"], np.nan, bmi)
    status_draw = rng.random(n)
    kidney_status = np.where(damage & (status_draw < report["told_abnormal_given_damage"]), "Told something was wrong",
                             np.where(~y_true & (status_draw < report["tested_normal_past_year"]),
                                      "Tested normal in the past 12 months", "Never tested"))
    return pd.DataFrame(dict(
        age_group=groups[group_index], sex=np.where(female, "Female", "Male"),
        diabetes=dm_answer, high_blood_pressure=htn_answer, bp_reading=bp_reading, medicine=medicine_answer,
        heart_disease_stroke=_simple_answer(rng, heart, other_dk), kidney_stones=_simple_answer(rng, stones, other_dk),
        family_history=_simple_answer(rng, family, other_dk), heavy_outdoor_work=_simple_answer(rng, outdoor, other_dk),
        bmi_reported=bmi_answer, kidney_status=kidney_status,
        age=age, dm_true=dm, htn_true=htn, heart_true=heart, stones_true=stones, family_true=family, outdoor_true=outdoor,
        bmi=bmi, dm_aware=dm_aware, htn_aware=htn_aware, medicine_true=medicine, community_heat=heat,
        kidney_damage_true=damage, creatinine_true=creatinine_true, egfr_true=egfr_true, uacr_true=uacr_true,
        creatinine=creatinine, egfr=egfr, uacr=uacr, y_true=y_true))


def risk_check_cohort(cfg, n, rng, intercept=None):
    """``n`` people eligible for the risk check: those already told something was wrong are routed to care."""
    parts, eligible = [], 0
    while eligible < n:
        batch = simulate_population(cfg, max(n, 1000), rng, intercept)
        batch = batch[batch.kidney_status != "Told something was wrong"]
        parts.append(batch)
        eligible += len(batch)
    return pd.concat(parts, ignore_index=True).iloc[:n].reset_index(drop=True)


def calibrate_intercept(cfg, target, n, seed, tolerance=1e-4, iterations=40):
    """Monte Carlo bisection: the outcome intercept whose measured abnormal-screen share (population
    level, before routing) equals ``target``. A fixed seed makes the share monotone in the intercept."""
    low, high = -8.0, 1.0
    for _ in range(iterations):
        middle = (low + high) / 2
        share = simulate_population(cfg, n, np.random.default_rng(seed), middle).y_true.mean()
        if abs(share - target) < tolerance:
            break
        low, high = (middle, high) if share < target else (low, middle)
    return middle, float(share)
