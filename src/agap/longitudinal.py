"""SIM-09 longitudinal scenario: follow-up measurements and a hypothetical acute-event indicator.

Deployment residents get creatinine and uACR at 90 and 180 days, generated from their
day-0 values with assumed measurement variability, slow eGFR decline and an optional
hypothetical acute event that raises creatinine at that visit. Persistence means abnormal
at day 0 and at the persistence day (default 180). Every column here is hidden evaluation
data and is forbidden as a screening-model input (SIM-10). Nothing here is a diagnosis:
persistent is not CKD and a hypothetical acute event is not AKI. See
docs/sim09_longitudinal_design.md.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.special import expit, logit

from agap.climate.integration import climate_mode, validated_exposure
from agap.experiment import atomic_text, fixture_hot_dry, rng_for, save_frame
from agap.simulate.kidney import ckd_epi_2021, creatinine_for_egfr, measurement_factor, observed_screen_label

LONGITUDINAL_COMPONENT = 40  # rng component; partitions use 1-30, surveillance 1000+
DEFAULTS = dict(followup_days=[90, 180], persistence_day=180, creatinine_cv=.05, uacr_cv=.30,
                egfr_decline_per_year=1.0, acute_event_rate=.02, acute_creatinine_factor=1.5)
LABEL = ("Simulated follow-up under assumed parameters. 'Still abnormal at 180 days' is a persistent "
         "abnormal screening pattern, not a CKD diagnosis; hypothetical acute events are not AKI.")


def settings_for(cfg):
    settings = {**DEFAULTS, **cfg.get("longitudinal", {})}
    if settings["persistence_day"] not in settings["followup_days"]:
        raise ValueError("persistence_day must be one of followup_days")
    return settings


def followup_columns(days=DEFAULTS["followup_days"]):
    """Hidden follow-up columns; all are forbidden screening-model inputs (SIM-10)."""
    columns = []
    for day in days:
        columns += [f"creatinine_{day}d", f"uacr_{day}d", f"egfr_{day}d", f"abnormal_{day}d",
                    f"hypothetical_acute_event_{day}d", f"hot_dry_score_{day}d", f"visit_uniform_{day}d"]
    return columns + ["persistent_abnormal", "transient_abnormal"]


def acute_probability(frame, hot_dry, prototype, settings):
    """Hypothetical acute-event probability; settings rate applies at age 40, no DM/HTN, score 0."""
    linear = (logit(settings["acute_event_rate"])
              + prototype["age_log_odds_per_year"] * (frame.age.to_numpy(float) - 40)
              + prototype["dm_log_odds"] * frame.dm_true.to_numpy(float)
              + prototype["htn_log_odds"] * frame.htn_true.to_numpy(float)
              + np.log(prototype["heat_or"]) * np.asarray(hot_dry, float))
    return expit(linear)


_variability = measurement_factor


def simulate_followup(frame, hot_dry_at, prototype, settings, rng):
    """Follow-up measurements for each resident in frame.

    hot_dry_at maps each follow-up day to the hot-dry score of that visit's 30-day window
    (NaN where no complete window exists; those residents are excluded, not imputed).
    Draws are made for every resident in a fixed order, so exclusion never shifts them.
    """
    output = frame[["resident_id", "cutoff", "era5_cell", "age", "female", "creatinine", "uacr", "egfr", "y_true"]].copy()
    age, female, count = frame.age.to_numpy(float), frame.female.to_numpy(bool), len(frame)
    included = np.ones(count, bool)
    for day in settings["followup_days"]:
        hot = np.asarray(hot_dry_at[day], float)
        included &= np.isfinite(hot)
        event = rng.random(count) < acute_probability(frame, np.nan_to_num(hot), prototype, settings)
        # Each visit re-measures the underlying kidney state; the day-0 value is itself one noisy measurement.
        base_egfr = (frame.egfr_true if "egfr_true" in frame else frame.egfr).to_numpy(float)
        chronic = np.maximum(base_egfr - settings["egfr_decline_per_year"] * day / 365.25, 1.0)
        creatinine = (creatinine_for_egfr(chronic, age, female) * _variability(rng, settings["creatinine_cv"], count)
                      * np.where(event, settings["acute_creatinine_factor"], 1.0))
        uacr = (frame.uacr_true if "uacr_true" in frame else frame.uacr).to_numpy(float) * _variability(rng, settings["uacr_cv"], count)
        egfr = ckd_epi_2021(creatinine, age, female)
        output[f"hot_dry_score_{day}d"] = hot
        output[f"hypothetical_acute_event_{day}d"] = event
        output[f"creatinine_{day}d"], output[f"uacr_{day}d"], output[f"egfr_{day}d"] = creatinine, uacr, egfr
        output[f"abnormal_{day}d"] = observed_screen_label(egfr, uacr) == 1
    for day in settings["followup_days"]:
        output[f"visit_uniform_{day}d"] = rng.random(count)
    persistent_day = output[f"abnormal_{settings['persistence_day']}d"].to_numpy()
    output["followup_included"] = included
    output["persistent_abnormal"] = included & output.y_true.to_numpy(bool) & persistent_day
    output["transient_abnormal"] = included & output.y_true.to_numpy(bool) & ~persistent_day
    return output


def followup_metrics(followup, allocations, completion_probability, settings):
    """Per policy: hidden persistence of detected positives and the observed confirmatory pathway.

    Only residents whose initial test was completed and abnormal are invited back; each visit
    is attended with the resident's completion probability and a shared per-visit uniform.
    """
    days, persistence_day = settings["followup_days"], settings["persistence_day"]
    people = followup.assign(completion_probability=np.asarray(completion_probability, float))
    included = people.followup_included
    rows = []
    for policy, records in allocations.groupby("policy", sort=True):
        merged = records[["resident_id", "completed"]].merge(people, on="resident_id", how="inner", validate="one_to_one")
        merged = merged[merged.followup_included]
        detected = merged.completed & merged.y_true
        row = dict(policy=policy, included_residents=int(included.sum()),
                   excluded_for_climate_coverage=int((~included).sum()),
                   population_initial_positives=int(merged.y_true.sum()),
                   population_persistent_positives=int(merged.persistent_abnormal.sum()),
                   initial_positives_detected=int(detected.sum()),
                   hidden_persistent_detected=int((detected & merged.persistent_abnormal).sum()),
                   hidden_transient_detected=int((detected & merged.transient_abnormal).sum()),
                   followup_invited=int(detected.sum()))
        attended = {}
        for day in days:
            attended[day] = detected & (merged[f"visit_uniform_{day}d"] < merged.completion_probability)
            row[f"day{day}_completed"] = int(attended[day].sum())
            row[f"hypothetical_acute_events_{day}d"] = int(merged[f"hypothetical_acute_event_{day}d"].sum())
        seen = attended[persistence_day]
        abnormal = merged[f"abnormal_{persistence_day}d"]
        row["observed_persistent"] = int((seen & abnormal).sum())
        row["observed_transient"] = int((seen & ~abnormal).sum())
        row["observed_unknown"] = int((detected & ~seen).sum())
        row["hidden_persistent_share_of_detected"] = (row["hidden_persistent_detected"] / row["initial_positives_detected"]
                                                      if row["initial_positives_detected"] else np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


def persistence_by_plan(plans, followup, day=180):
    """For each (label, allocation records) plan: detected positives still abnormal at the persistence day.

    Uses every found resident's simulated follow-up (hidden evaluation data), excluding residents whose
    follow-up falls outside the climate data. Persistent is not a CKD diagnosis.
    """
    columns = ["resident_id", "followup_included", "persistent_abnormal", "transient_abnormal"]
    rows = []
    for label, records in plans:
        found = records.loc[records.positive_detected, ["resident_id"]].merge(followup[columns], on="resident_id")
        found = found[found.followup_included]
        rows.append({"Plan": label, "Abnormal initial results found": len(found),
                     f"Still abnormal at {day} days": int(found.persistent_abnormal.sum()),
                     f"Normal again at {day} days": int(found.transient_abnormal.sum())})
    return pd.DataFrame(rows)


def visit_hot_dry(cfg, directory, frame, day):
    dates = (pd.to_datetime(frame.cutoff) + pd.Timedelta(days=day)).dt.normalize()
    if climate_mode(cfg) != "era5_land":
        return fixture_hot_dry(dates, frame.era5_cell)
    exposure = validated_exposure(directory / "climate_exposure.parquet")
    complete = exposure.loc[exposure.complete.eq(True), ["era5_cell", "cutoff", "hot_dry_score"]]
    keys = pd.DataFrame({"era5_cell": frame.era5_cell.to_numpy(), "cutoff": dates.to_numpy()})
    return keys.merge(complete, on=["era5_cell", "cutoff"], how="left", validate="many_to_one").hot_dry_score.to_numpy()


def longitudinal(cfg, directory, repetition=0):
    settings = settings_for(cfg)
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    allocations = pd.read_parquet(directory / "allocations_hidden.parquet")
    hot_dry_at = {day: visit_hot_dry(cfg, directory, frame, day) for day in settings["followup_days"]}
    followup = simulate_followup(frame, hot_dry_at, cfg["prototype"], settings,
                                 rng_for(cfg["seed"], repetition, LONGITUDINAL_COMPONENT))
    metrics = followup_metrics(followup, allocations, frame.completion_probability, settings)
    save_frame(followup, directory / "longitudinal_hidden.parquet")
    metrics.to_csv(directory / "longitudinal_metrics.csv", index=False)
    atomic_text(directory / "longitudinal.json", json.dumps(dict(
        label=LABEL, settings=settings, parameter_status="assumed; not yet sourced (SIM-04)",
        acute_heat_effect="log(heat_or) per hot-dry score unit, shared with the outcome model's heat scenario",
        climate=climate_mode(cfg), heat_or=cfg["prototype"]["heat_or"], mechanism=cfg["prototype"]["mechanism"],
        included_residents=int(followup.followup_included.sum()),
        excluded_for_climate_coverage=int((~followup.followup_included).sum()),
        hidden_columns="All follow-up columns are evaluation-only and forbidden as model inputs (SIM-10).",
        repetition=repetition), indent=2))
    return followup, metrics
