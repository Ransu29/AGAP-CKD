"""Small, reproducible screening/allocation experiment; no real patient claims.

Public geography and optional historical climate inform synthetic residents.
Clinical states, climate-health effects, facilities and behaviour are simulated.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_flow
from scipy.special import expit, logit
from scipy.stats import truncnorm
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer, MissingIndicator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score, roc_curve
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from agap.config import ROOT
from agap.climate.integration import (
    PARTITION_DATES, attach_historical_exposure, climate_inputs, climate_mode,
    snapshot_climate, validated_exposure,
)
from agap.data.geography import make_geography
from agap.models.leakage import check_allowed_features
from agap.simulate.kidney import ckd_epi_2021, creatinine_for_egfr, measurement_factor, observed_screen_label

CLINICAL = ["age", "female", "dm_report", "htn_report", "family_report", "outdoor_report"]
MODELS = {"clinical": CLINICAL, "climate": CLINICAL + ["hot_dry_score"], "ipw_climate": CLINICAL + ["hot_dry_score"]}
UNREPORTED_POLICY = "risk_plus_unreported"


def policy_label(policy, share):
    """Stored policy name; mixed plans carry their outreach share."""
    if share == 0:
        return policy
    prefix = "risk_unreported" if policy == UNREPORTED_POLICY else "risk_explore"
    return f"{prefix}_{int(round(share * 100))}"


def pipeline_policies(cfg):
    """The fixed policy variants compared by saved allocation and spatial sensitivity."""
    shares = [share for share in cfg["allocation"]["exploration_shares"] if share > 0]
    return ([("random", 0), ("population_proportional", 0), ("risk_ranked", 0)]
            + [("risk_ranked", share) for share in shares]
            + [(UNREPORTED_POLICY, cfg["allocation"]["unreported_outreach_share"])])


def atomic_text(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def save_frame(frame, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, path)


def fingerprint(cfg):
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]


def source_hash():
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src/agap").rglob("*.py")):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def input_checksums(cfg):
    from agap.climate.available import weather_inputs
    paths = []
    if cfg["prototype"]["geography_mode"] == "public":
        paths += sorted((ROOT / "data/raw/worldpop/age_sex").glob("*.tif"))
        paths += sorted((ROOT / "data/raw/boundaries").glob("*.geojson"))
        if cfg["allocation"].get("service_points") == "yakap_register":  # public geography only
            paths.append(ROOT / "data/processed/public/laguna/yakap_clinics.csv")
    paths += climate_inputs(cfg, ROOT)
    paths += weather_inputs(cfg, ROOT)
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


STAGES = ("data", "simulate", "train", "allocate", "evaluate", "spatial", "longitudinal", "surveillance", "integrity")


def run_path(cfg):
    checksums = input_checksums(cfg)
    input_hash = hashlib.sha256(json.dumps(checksums, sort_keys=True).encode()).hexdigest()[:8]
    return ROOT / "outputs/runs" / f"{fingerprint(cfg)}-{source_hash()}-{input_hash}"


def rng_for(seed, repetition, component):
    return np.random.default_rng(np.random.SeedSequence([repetition, component, seed]))


def haversine(lat, lon, facility_lat, facility_lon):
    lat, lon, facility_lat, facility_lon = map(np.deg2rad, (lat, lon, facility_lat, facility_lon))
    a = np.sin((facility_lat - lat) / 2) ** 2 + np.cos(lat) * np.cos(facility_lat) * np.sin((facility_lon - lon) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def distance_matrix(frame, facilities):
    return haversine(frame.latitude.to_numpy()[:, None], frame.longitude.to_numpy()[:, None],
                     facilities.latitude.to_numpy()[None, :], facilities.longitude.to_numpy()[None, :])


def fixture_hot_dry(dates, era5_cells):
    """Offline fixture signal. It is not a standard-normal variable or measured climate."""
    day = pd.to_datetime(pd.Series(dates)).dt.dayofyear.to_numpy()
    cell_phase = np.array([int(hashlib.sha256(cell.encode()).hexdigest()[:8], 16) / 2**32 * 2 * np.pi for cell in era5_cells])
    return np.sin(2 * np.pi * day / 365.25) + np.cos(cell_phase)


def build_data(cfg, directory):
    from agap.climate.available import snapshot_weather
    snapshot_weather(cfg, ROOT, directory)
    cells, demographics, facilities, boundary = make_geography(cfg, ROOT)
    atomic_text(directory / "population_check.json", json.dumps(demographics.attrs["population_check"], indent=2))
    cells, demographics = snapshot_climate(cfg, ROOT, directory, cells, demographics)
    for name, frame in (("cells", cells), ("demographics", demographics), ("facilities", facilities)):
        save_frame(frame, directory / f"{name}.parquet")
    atomic_text(directory / "boundary.geojson", json.dumps(boundary))
    return cells, demographics, facilities


def simulate_cohort(cfg, cells, demographics, facilities, repetition, partition, heldout, exposure=None,
                    period=None, count=None, component=None):
    """Simulate one cohort. period/count/component override the partition defaults
    (used by monthly surveillance samples); the defaults reproduce the partitions."""
    p = cfg["prototype"]
    if component is None:
        component = {"train": 10, "validation": 20, "deployment": 30}[partition]
    rng = rng_for(cfg["seed"], repetition, component)
    if count is None:
        count = p[f"n_{partition}"]
    selected_cells = cells[cells.era5_cell.isin(heldout) if partition == "deployment" else ~cells.era5_cell.isin(heldout)]
    demo = demographics[demographics.h3.isin(selected_cells.h3)]
    if demo.empty:
        raise ValueError("No population in requested climate-cell partition")
    chosen = rng.choice(len(demo), count, p=demo.adult_count.to_numpy() / demo.adult_count.sum())
    frame = demo.iloc[chosen].reset_index(drop=True).merge(selected_cells.drop(columns="adult_count"), on="h3", how="left")
    # SIM-01: draws are proportional to adult population, so each resident represents an equal
    # share of the sampled frame. Municipal totals let quotas use represented adults (ALLOC-08).
    frame["representation_weight"] = float(demo.adult_count.sum()) / count
    municipal = demo.merge(selected_cells[["h3", "municipality"]], on="h3").groupby("municipality").adult_count.sum()
    frame["municipality_represented_adults"] = frame.municipality.map(municipal).astype(float)
    frame["resident_id"] = [f"SYN-{partition.upper()}-{i:06d}" for i in range(count)]
    starts = frame.age_start.to_numpy()
    sim = cfg["simulator"]
    frame["age"] = [rng.integers(max(cfg["study_area"]["age_min"], age),
                                 sim["oldest_band_max_age"] + 1 if age == sim["oldest_band_start"] else age + 5)
                    for age in starts]
    frame["partition"] = partition
    # These are different residents in strictly ordered time windows.
    start, end = map(pd.Timestamp, period or PARTITION_DATES[partition])
    frame["cutoff"] = start + pd.to_timedelta(rng.integers(0, (end - start).days + 1, count), unit="D")
    if climate_mode(cfg) == "era5_land":
        if exposure is None:
            raise ValueError("Historical climate requested but no exposure supplied")
        frame = attach_historical_exposure(frame, exposure, rng, partition, period)
    else:
        frame["hot_dry_score"] = fixture_hot_dry(frame.cutoff, frame.era5_cell)
        frame["climate_source"] = "synthetic fixture"
    age = frame.age.to_numpy()
    traits, centre = sim["traits"], sim["age_center"]
    frame["dm_true"] = rng.random(count) < expit(traits["dm_intercept"] + traits["dm_log_odds_per_year"] * (age - centre))
    frame["htn_true"] = rng.random(count) < expit(traits["htn_intercept"] + traits["htn_log_odds_per_year"] * (age - centre)
                                                  + traits["htn_dm_log_odds"] * frame.dm_true)
    frame["family_true"] = rng.random(count) < traits["family_history_prevalence"]
    frame["outdoor_true"] = rng.random(count) < traits["outdoor_work_prevalence"]
    linear = (p["outcome_intercept"] + p["age_log_odds_per_year"] * (age - centre)
              + p["dm_log_odds"] * frame.dm_true + p["htn_log_odds"] * frame.htn_true
              + p["family_log_odds"] * frame.family_true + p["outdoor_log_odds"] * frame.outdoor_true
              + np.log(p["heat_or"]) * frame.hot_dry_score)
    # The declared odds ratios act on the underlying kidney state, not on one noisy test result.
    frame["kidney_damage_true"] = rng.random(count) < expit(linear)
    damage = frame.kidney_damage_true
    subtype = rng.random(count)
    lab = sim["laboratory"]
    renal = damage & (subtype < lab["renal_subtype_share"])
    albumin = damage & (subtype >= lab["albumin_subtype_start"])
    # Truncated (not capped) draws: capping would stack people exactly at a threshold, where one noisy
    # measurement flips half of them. Normal eGFR is bell-shaped, so few people sit just above 60.
    low, high = lab["normal_egfr_range"]
    mean, sd = lab["normal_egfr_mean"], lab["normal_egfr_sd"]
    normal_gfr = truncnorm.rvs((low - mean) / sd, (high - mean) / sd, loc=mean, scale=sd, size=count, random_state=rng)
    target_gfr = np.where(renal, rng.uniform(*lab["abnormal_egfr_range"], count), normal_gfr)
    frame["creatinine_true"] = creatinine_for_egfr(target_gfr, age, frame.female)
    frame["egfr_true"] = ckd_epi_2021(frame.creatinine_true, age, frame.female)
    log_sd = lab["uacr_log_sd"]
    abnormal_log = np.log(lab["abnormal_uacr_median"])
    normal_log = np.log(lab["normal_uacr_median"])
    abnormal_uacr = np.exp(truncnorm.rvs((np.log(cfg["outcome"]["uacr_threshold"]) - abnormal_log) / log_sd, np.inf,
                                         loc=abnormal_log, scale=log_sd, size=count, random_state=rng))
    normal_uacr = np.exp(truncnorm.rvs(-np.inf, (np.log(lab["normal_uacr_max"]) - normal_log) / log_sd,
                                       loc=normal_log, scale=log_sd, size=count, random_state=rng))
    frame["uacr_true"] = np.where(albumin, abnormal_uacr, normal_uacr)
    if not np.array_equal(observed_screen_label(frame.egfr_true, frame.uacr_true), damage.to_numpy()):
        raise ValueError("Laboratory synthesis inconsistent with the underlying kidney state")
    # SIM-11: the day-0 screen is one measurement with within-person variability (same CVs as follow-up
    # visits), so results near a threshold can flag or miss. Y is that measured initial flag.
    noise = rng_for(cfg["seed"], repetition, component + MEASUREMENT_STREAM)
    variability = cfg.get("longitudinal", {})
    frame["creatinine"] = frame.creatinine_true * measurement_factor(noise, variability.get("creatinine_cv", .05), count)
    frame["egfr"] = ckd_epi_2021(frame.creatinine, age, frame.female)
    frame["uacr"] = frame.uacr_true * measurement_factor(noise, variability.get("uacr_cv", .30), count)
    frame["y_true"] = observed_screen_label(frame.egfr, frame.uacr) == 1
    distances = distance_matrix(frame, facilities)
    frame["nearest_distance_km"] = distances.min(axis=1)
    mechanism = p["mechanism"]
    if mechanism not in ("MCAR", "MAR", "MNAR"):
        raise ValueError("mechanism must be MCAR, MAR or MNAR")
    reporting = np.full(count, logit(p["report_rate"]))
    if mechanism != "MCAR":
        observe = sim["observation"]
        reporting += (observe["report_log_odds_per_year"] * (age - observe["report_age_center"])
                      + observe["report_log_odds_per_km"] * frame.nearest_distance_km.to_numpy())
    if mechanism == "MNAR":
        reporting += p["report_mnar_log_odds"] * frame.kidney_damage_true.to_numpy()
    pr = np.clip(expit(reporting), p["min_probability"], 1 - p["min_probability"])
    frame["reported"] = rng.random(count) < pr
    # SIM-12: people with diabetes or hypertension do not all know it; an unaware reporter answers No.
    aware = rng_for(cfg["seed"], repetition, component + AWARENESS_STREAM)
    for field in ("dm", "htn", "family", "outdoor"):
        known = frame[f"{field}_true"].to_numpy(bool)
        if field in ("dm", "htn"):
            known = known & (aware.random(count) < traits[f"{field}_awareness"])
        frame[f"{field}_report"] = np.where(frame.reported, known.astype(float), np.nan)
    if mechanism == "MCAR":
        q0, q1 = np.full(count, sim["observation"]["invitation_mcar"]), np.full(count, sim["observation"]["invitation_mcar"])
    else:
        observe = sim["observation"]
        proximity = np.exp(-frame.nearest_distance_km.to_numpy() / observe["proximity_scale_km"])
        (base0, slope0), (base1, slope1) = observe["invitation_nonreporter"], observe["invitation_reporter"]
        q0, q1 = base0 + slope0 * proximity, base1 + slope1 * proximity
    completion_logit = np.full(count, logit(p["completion_rate"]))
    if mechanism != "MCAR":
        completion_logit += sim["observation"]["completion_log_odds_per_km"] * frame.nearest_distance_km.to_numpy()
    if mechanism == "MNAR":
        completion_logit += p["completion_mnar_log_odds"] * frame.kidney_damage_true.to_numpy()
    completion = np.clip(expit(completion_logit), p["min_probability"], 1 - p["min_probability"])
    frame["report_probability"] = pr
    frame["completion_probability"] = completion
    frame["observation_probability"] = ((1 - pr) * q0 + pr * q1) * completion
    frame["round0_invited"] = rng.random(count) < np.where(frame.reported, q1, q0)
    frame["round0_completed"] = frame.round0_invited & (rng.random(count) < completion)
    frame["observed_label"] = np.where(frame.round0_completed, frame.y_true.astype(float), np.nan)
    # Deployment results are potential outcomes only; no pre-policy deployment labels enter training.
    if partition == "deployment":
        frame["observed_label"] = np.nan
        frame["round0_invited"] = False
        frame["round0_completed"] = False
    frame["completion_uniform"] = rng.random(count)
    frame["tie_uniform"] = rng.random(count)
    return add_report_details(frame, cfg, repetition, component)


REPORT_DETAIL_STREAM = 20_000  # rng component offset; the main cohort stream is never touched
MEASUREMENT_STREAM = 30_000    # day-0 measurement variability (SIM-11)
AWARENESS_STREAM = 40_000      # diagnosis awareness for reported DM/HTN (SIM-12)


def add_report_details(frame, cfg, repetition, component):
    """SIM-02 prior screening and outdoor hours, plus E1-08 report dates, on a separate stream.

    Assumed generators (docs/engine1_reporting_design.md). A report that becomes available
    after the resident's cutoff is not usable at prediction time: its answers are masked.
    """
    settings = cfg.get("reporting", {})
    rng = rng_for(cfg["seed"], repetition, REPORT_DETAIL_STREAM + component)
    count, age = len(frame), frame.age.to_numpy()
    details, centre = cfg["simulator"]["report_details"], cfg["simulator"]["age_center"]
    prior = expit(logit(details["prior_screen_rate"]) + details["prior_screen_log_odds_per_year"] * (age - centre)
                  + details["prior_screen_dm_log_odds"] * frame.dm_true + details["prior_screen_htn_log_odds"] * frame.htn_true)
    frame["prior_screen_true"] = rng.random(count) < prior
    (worker_low, worker_high), (other_low, other_high) = details["outdoor_hours_worker"], details["outdoor_hours_other"]
    frame["outdoor_hours_7d_true"] = np.where(frame.outdoor_true, rng.integers(worker_low, worker_high + 1, count),
                                              rng.integers(other_low, other_high + 1, count))
    reported = frame.reported.to_numpy()
    frame["prior_screen_report"] = np.where(reported, frame.prior_screen_true.astype(float), np.nan)
    frame["outdoor_hours_7d_report"] = np.where(reported, frame.outdoor_hours_7d_true.astype(float), np.nan)
    low, high = settings.get("availability_days_before_cutoff", [0, 14])
    before = rng.integers(low, high + 1, count)
    available = frame.cutoff - pd.to_timedelta(before, unit="D")
    frame["report_available_date"] = available.where(reported)
    lag_low, lag_high = details["event_days_before_available"]
    frame["report_event_date"] = (available - pd.to_timedelta(rng.integers(lag_low, lag_high + 1, count), unit="D")).where(reported)
    frame["report_late"] = reported & (before < 0)
    late = frame.report_late.to_numpy()
    for column in ("dm_report", "htn_report", "family_report", "outdoor_report", "prior_screen_report", "outdoor_hours_7d_report"):
        frame.loc[late, column] = np.nan
    return frame


def simulate(cfg, directory, repetition=0):
    cells = pd.read_parquet(directory / "cells.parquet")
    demographics = pd.read_parquet(directory / "demographics.parquet")
    facilities = pd.read_parquet(directory / "facilities.parquet")
    exposure = validated_exposure(directory / "climate_exposure.parquet") if climate_mode(cfg) == "era5_land" else None
    groups = np.array(sorted(cells.era5_cell.unique()))
    if len(groups) < 5:
        raise ValueError("At least five populated climate groups are required")
    heldout = rng_for(cfg["seed"], repetition, 1).choice(groups, max(1, int(np.ceil(.2 * len(groups)))), replace=False)
    frames = {partition: simulate_cohort(cfg, cells, demographics, facilities, repetition, partition, heldout, exposure)
              for partition in ("train", "validation", "deployment")}
    for name, frame in frames.items():
        save_frame(frame, directory / f"{name}_hidden.parquet")
    atomic_text(directory / "split.json", json.dumps({"heldout_era5_cells": heldout.tolist(),
                                                     "all_populated_era5_cells": len(groups),
                                                     "deployment_count": len(frames["deployment"])}, indent=2))
    return frames


def model_pipeline(features):
    transform = ColumnTransformer([
        ("values", Pipeline([("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                              ("scale", StandardScaler())]), features),
        ("missing", MissingIndicator(features="all"), features),
    ])
    return Pipeline([("features", transform), ("model", LogisticRegression(max_iter=500, C=1.0))])


def weighting_support(population):
    """E3-14: a population-wide weighting claim needs a positive observation probability for every
    resident of the target population; otherwise claims are limited to the supported subpopulation."""
    probability = population.observation_probability.to_numpy(float)
    unsupported = int((~(np.isfinite(probability) & (probability > 0))).sum())
    return dict(target_population_residents=len(probability), zero_probability_residents=unsupported,
                zero_probability_share=unsupported / len(probability) if len(probability) else np.nan,
                min_population_observation_probability=float(np.nanmin(probability)) if np.isfinite(probability).any() else np.nan,
                population_claim="population-wide" if unsupported == 0 else
                f"not population-wide: {unsupported} of {len(probability)} residents have zero observation probability; "
                "estimates apply to the supported subpopulation only")


def train(cfg, directory):
    training = pd.read_parquet(directory / "train_hidden.parquet")
    validation = pd.read_parquet(directory / "validation_hidden.parquet")
    deployment = pd.read_parquet(directory / "deployment_hidden.parquet")
    observed = training[training.observed_label.notna()]
    if observed.observed_label.nunique() < 2:
        raise ValueError("Unsupported training set: fewer than two observed classes")
    prediction_records, metrics, diagnostics = [], [], []
    for name, features in MODELS.items():
        check_allowed_features(features, CLINICAL + ["hot_dry_score"], cfg["models"]["forbidden_features"])
        pipeline = model_pipeline(features)
        kwargs = {}
        weight_note, claim = "unweighted", "unweighted model; no weighting claim"
        if name.startswith("ipw"):
            if not (observed.observation_probability > 0).all():
                raise ValueError("An observed training resident has zero observation probability; weights are undefined")
            support = weighting_support(training)
            claim = support["population_claim"]
            weights = 1 / observed.observation_probability.to_numpy()
            cap = np.quantile(weights, cfg["prototype"]["weight_quantile"])
            weights = np.minimum(weights, cap)
            kwargs["model__sample_weight"] = weights / weights.mean()
            weight_note = "oracle MNAR" if cfg["prototype"]["mechanism"] == "MNAR" else "simulator-known observation probabilities"
            diagnostics.append(dict(model=name, weight_source=weight_note, weight_cap=float(cap),
                                    min_observation_probability=float(observed.observation_probability.min()),
                                    effective_sample_size=float(weights.sum() ** 2 / np.square(weights).sum()),
                                    observed_training_labels=len(observed), **support))
        pipeline.fit(observed[features], observed.observed_label, **kwargs)
        model_file = directory / f"model_{name}.joblib"
        temporary_model = model_file.with_suffix(".joblib.partial")
        joblib.dump(pipeline, temporary_model)
        os.replace(temporary_model, model_file)
        validation_scores = pipeline.predict_proba(validation[features])[:, 1]
        scores = pipeline.predict_proba(deployment[features])[:, 1]
        mask = validation.observed_label.notna()
        labels = validation.loc[mask, "observed_label"].to_numpy()
        for target in (.8, .9):
            threshold = np.nan
            status = "unsupported: insufficient observed validation labels"
            if len(np.unique(labels)) == 2 and labels.sum() >= cfg["prototype"]["min_validation_positives"]:
                _, sensitivity, candidates = roc_curve(labels, validation_scores[mask])
                good = candidates[(sensitivity >= target) & np.isfinite(candidates)]
                if len(good):
                    threshold, status = float(good.max()), "supported"
            result = deployment[["resident_id", "cutoff", "reported"]].copy()
            result["score"], result["model"], result["target_sensitivity"] = scores, name, target
            result["threshold"] = threshold
            result["model_version"] = source_hash()
            result["flag"] = np.where(np.isfinite(threshold), (scores >= threshold).astype(float), np.nan)
            result["status"], result["input_completeness"] = status, deployment[features].notna().mean(axis=1)
            prediction_records.append(result)
            for population, subset in (("all_deployment", np.ones(len(deployment), bool)),
                                       ("reporters", deployment.reported.to_numpy())):
                y, s = deployment.y_true.to_numpy()[subset], scores[subset]
                classes = len(np.unique(y)) == 2
                positives = int(y.sum())
                negatives = len(y) - positives
                flagged = s >= threshold
                metrics.append(dict(model=name, population=population, target_sensitivity=target, threshold=threshold,
                                    status=status, n=len(y), positives=positives, weight_source=weight_note,
                                    population_claim=claim,
                                    auroc=roc_auc_score(y, s) if classes else np.nan,
                                    auprc=average_precision_score(y, s) if classes else np.nan,
                                    brier=brier_score_loss(y, s) if len(y) else np.nan,
                                    sensitivity=float((flagged & y).sum() / positives) if positives and np.isfinite(threshold) else np.nan,
                                    specificity=float((~flagged & ~y).sum() / negatives) if negatives and np.isfinite(threshold) else np.nan))
                metrics[-1]["fnr"] = 1 - metrics[-1]["sensitivity"]
                metrics[-1]["calibration_intercept"] = np.nan
                metrics[-1]["calibration_slope"] = np.nan
                if classes:
                    calibration = LogisticRegression(C=1e6, max_iter=500).fit(logit(np.clip(s, 1e-6, 1 - 1e-6)).reshape(-1, 1), y)
                    metrics[-1]["calibration_intercept"] = float(calibration.intercept_[0])
                    metrics[-1]["calibration_slope"] = float(calibration.coef_[0, 0])
    save_frame(pd.concat(prediction_records, ignore_index=True), directory / "predictions.parquet")
    pd.DataFrame(metrics).to_csv(directory / "model_metrics.csv", index=False)
    atomic_text(directory / "weight_diagnostics.json", json.dumps(diagnostics, indent=2))


def policy_order(frame, scores, policy, share, seed):
    rng = np.random.default_rng(seed)
    if policy == "random":
        return rng.permutation(len(frame))
    if policy == "population_proportional":
        # Interleave random municipality queues by proportion of the represented deployment frame.
        # The allocator below implements explicit largest-remainder invitation quotas.
        return rng.permutation(len(frame))
    ranked = np.lexsort((frame.tie_uniform.to_numpy(), -np.asarray(scores)))
    if share == 0:
        return ranked
    if policy == UNREPORTED_POLICY:
        # Outreach slots go to residents without a questionnaire, highest score first: nonreporters
        # hold most initial positives but rank low when their answers are missing.
        return ranked, ranked[~frame.reported.to_numpy(bool)[ranked]]
    random_order = rng.permutation(len(frame))
    return ranked, random_order


class CoverageInfeasibleError(ValueError):
    """Configured geographic coverage requirements cannot be met (ALLOC-12)."""


def coverage_requirements(cfg, frame):
    """Minimum invitations per municipality from allocation.coverage; zero means no requirement."""
    coverage = cfg["allocation"].get("coverage") or {}
    municipalities = sorted(frame.municipality.unique())
    overrides = coverage.get("minimum_invitations") or {}
    unknown = sorted(set(overrides) - set(municipalities))
    if unknown:
        raise CoverageInfeasibleError(f"Coverage requirements name municipalities not in this cohort: {unknown}. "
                                      f"Available: {municipalities}")
    values = {name: overrides.get(name, coverage.get("minimum_invitations_per_municipality", 0)) for name in municipalities}
    if any(isinstance(value, bool) or int(value) != value or value < 0 for value in values.values()):
        raise CoverageInfeasibleError("Coverage requirements must be whole numbers of zero or more")
    return pd.Series(values, dtype=int)


def _coverage_flow(required, municipality, reachable, capacity):
    """Most required invitations placeable at once: municipality -> resident -> service point."""
    names = list(required.index)
    people = [np.flatnonzero((municipality == name) & reachable.any(axis=1)) for name in names]
    residents = np.concatenate(people)
    first_resident, first_site = 1 + len(names), 1 + len(names) + len(residents)
    sink = first_site + reachable.shape[1]
    edges = [(0, 1 + i, int(required[name])) for i, name in enumerate(names)]
    node = first_resident
    for i, group in enumerate(people):
        for person in group:
            edges.append((1 + i, node, 1))
            edges += [(node, first_site + site, 1) for site in np.flatnonzero(reachable[person])]
            node += 1
    edges += [(first_site + site, sink, int(slots)) for site, slots in enumerate(capacity) if slots > 0]
    rows, cols, caps = map(np.array, zip(*edges))
    graph = csr_matrix((caps.astype(np.int32), (rows, cols)), shape=(sink + 1, sink + 1))
    return int(maximum_flow(graph, 0, sink).flow_value)


def check_coverage_feasibility(floors, frame, facilities, distance, limit, budget):
    """Check requirements before allocation; explain every reason they cannot be met."""
    required = floors[floors > 0]
    if required.empty:
        return dict(required={}, details={})
    reachable = distance <= limit
    municipality = frame.municipality.to_numpy()
    capacity = facilities.capacity.to_numpy().astype(int)
    problems, details = [], {}
    if required.sum() > budget:
        problems.append(f"the requirements total {required.sum()} invitations but the budget is {budget}")
    for name, floor in required.items():
        members = municipality == name
        residents = int((members & reachable.any(axis=1)).sum())
        slots = int(capacity[reachable[members].any(axis=0)].sum())
        details[name] = dict(required=int(floor), reachable_residents=residents, reachable_capacity=slots)
        if floor > residents:
            problems.append(f"{name} needs {floor} invitations but only {residents} of its residents are within {limit} km of a service point")
        if floor > slots:
            problems.append(f"{name} needs {floor} invitations but the service points its residents can reach have {slots} slots")
    if not problems:
        placeable = _coverage_flow(required, municipality, reachable, capacity)
        if placeable < required.sum():
            problems.append(f"each municipality is feasible alone, but shared service-point capacity can place at most "
                            f"{placeable} of the {required.sum()} required invitations at once")
    if problems:
        raise CoverageInfeasibleError("Coverage requirements cannot be met: " + "; ".join(problems)
                                      + ". Lower the requirements or raise the budget, capacity or distance limit; "
                                        "requirements are never relaxed automatically.")
    return dict(required={name: int(floor) for name, floor in required.items()}, details=details)


def allocate_policy(cfg, frame, facilities, scores, policy, share=0.0, seed=2026):
    if len(scores) != len(frame) or not np.isfinite(scores).all():
        raise ValueError("Every candidate must have a finite score")
    budget = int(cfg["allocation"]["budget_tests"])
    if budget < 0 or (facilities.capacity < 0).any():
        raise ValueError("Negative budget or capacity")
    distance = distance_matrix(frame, facilities)
    limit = cfg["allocation"]["max_distance_km"]
    access_feasible = distance.min(axis=1) <= limit
    # A resident who reports a known CKD diagnosis follows their care plan, not a first-screening invitation.
    known_ckd = (frame.reported_known_ckd.fillna(False).astype(bool).to_numpy() if "reported_known_ckd" in frame
                 else np.zeros(len(frame), bool))
    feasible = access_feasible & ~known_ckd
    floors = coverage_requirements(cfg, frame)
    coverage = check_coverage_feasibility(floors, frame, facilities, np.where(known_ckd[:, None], np.inf, distance), limit, budget)
    remaining = facilities.capacity.to_numpy().astype(int).copy()
    assigned = np.full(len(frame), -1, dtype=int)
    reasons = np.full(len(frame), "not invited", dtype=object)
    reasons[~access_feasible] = "outside access limit"
    reasons[known_ckd] = "reported known CKD"
    order = policy_order(frame, scores, policy, share, seed)
    quotas = None
    if policy == "population_proportional":
        if "municipality_represented_adults" in frame:
            # ALLOC-08: represented adult-population totals, not raw synthetic sample counts.
            totals = frame.groupby("municipality").municipality_represented_adults.first()
        else:  # frames built without population inputs (unit-test fixtures) fall back to counts
            totals = frame.groupby("municipality").size()
        weights = totals / totals.sum()
        raw = weights * budget
        quotas = np.floor(raw).astype(int)
        remainders = (raw - quotas).sort_values(ascending=False, kind="stable")
        for municipality in remainders.index[:budget - quotas.sum()]:
            quotas.loc[municipality] += 1
    used = 0
    def pick(indices, target, reason, enforce_quotas=False):
        nonlocal used
        selected = 0
        for index in indices:
            if selected >= target or used >= budget:
                break
            if assigned[index] >= 0 or not feasible[index]:
                continue
            municipality = frame.iloc[index].municipality
            if enforce_quotas and quotas.loc[municipality] <= 0:
                continue
            available = np.flatnonzero((distance[index] <= limit) & (remaining > 0))
            if not len(available):
                continue
            site = available[np.argmin(distance[index, available])]
            assigned[index], reasons[index] = site, reason
            remaining[site] -= 1
            used, selected = used + 1, selected + 1
            if enforce_quotas:
                quotas.loc[municipality] -= 1
    if coverage["required"]:
        # Coverage first, in this policy's own order; scarcest municipalities first so
        # nearest-point assignment rarely blocks a later requirement.
        primary = order[0] if isinstance(order, tuple) else order
        areas = frame.municipality.to_numpy()
        slack = {name: detail["reachable_residents"] - detail["required"] for name, detail in coverage["details"].items()}
        for name in sorted(coverage["required"], key=lambda name: (slack[name], name)):
            pick([index for index in primary if areas[index] == name], coverage["required"][name], "coverage requirement")
        invited_by_area = pd.Series(areas[assigned >= 0]).value_counts()
        short = {name: (int(invited_by_area.get(name, 0)), floor) for name, floor in coverage["required"].items()
                 if invited_by_area.get(name, 0) < floor}
        if short:
            raise CoverageInfeasibleError(f"Nearest-service-point assignment met only {short} (invited, required) although a "
                                          "joint assignment exists; requirements are never relaxed automatically.")
        if quotas is not None:
            quotas = (quotas - invited_by_area.reindex(quotas.index, fill_value=0)).clip(lower=0)
    if isinstance(order, tuple):
        ranked, random_order = order
        exploration_slots = int(np.floor(budget * share + .5))
        pick(random_order, exploration_slots, "unreported outreach" if policy == UNREPORTED_POLICY else "exploration")
        pick(ranked, budget - used, "risk")
    else:
        pick(order, budget, policy, enforce_quotas=quotas is not None)
        if quotas is not None and used < budget:
            pick(order, budget - used, "quota shortfall reassigned")
    invited = assigned >= 0
    # Assignment-specific distances modify completion for MAR/MNAR; uniforms are shared by resident.
    actual_distance = np.where(invited, distance[np.arange(len(frame)), np.maximum(0, assigned)], np.nan)
    completion_p = frame.completion_probability.to_numpy().copy()
    if cfg["prototype"]["mechanism"] != "MCAR":
        completion_p = expit(logit(completion_p) + cfg["simulator"]["observation"]["completion_log_odds_per_km"]
                             * np.nan_to_num(actual_distance - frame.nearest_distance_km.to_numpy()))
    completed = invited & (frame.completion_uniform.to_numpy() < completion_p)
    result = frame[["resident_id", "municipality", "latitude", "longitude", "reported", "age", "female", "outdoor_true", "y_true"]
                   + [column for column in ("representation_weight",) if column in frame]].copy()
    result["policy"] = policy_label(policy, share)
    result["score"], result["invited"], result["completed"] = scores, invited, completed
    result["access_feasible"], result["reason"], result["distance_km"] = access_feasible, reasons, actual_distance
    result["screening_eligible"] = ~known_ckd
    result["facility_id"] = [facilities.iloc[a].facility_id if a >= 0 else None for a in assigned]
    result["positive_detected"] = completed & frame.y_true.to_numpy()
    result["invitation_probability"] = np.nan  # Conditional greedy inclusion probabilities are not inferred.
    return result


def allocation_scores(cfg, predictions, frame):
    """Saved scores of the configured allocation model, in deployment-frame order."""
    model = cfg["prototype"]["allocation_model"]
    if model not in MODELS:
        raise ValueError(f"Unknown allocation model {model!r}; choose one of {sorted(MODELS)}")
    return (predictions[(predictions.model == model) & (predictions.target_sensitivity == .9)]
            .set_index("resident_id").score.reindex(frame.resident_id).to_numpy())


def allocate(cfg, directory):
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    facilities = pd.read_parquet(directory / "facilities.parquet")
    predictions = pd.read_parquet(directory / "predictions.parquet")
    scores = allocation_scores(cfg, predictions, frame)
    outputs = [allocate_policy(cfg, frame, facilities, scores, policy, share, cfg["seed"] + 100)
               for policy, share in pipeline_policies(cfg)]
    allocations = pd.concat(outputs, ignore_index=True)
    save_frame(allocations, directory / "allocations_hidden.parquet")
    floors = coverage_requirements(cfg, frame)
    coverage = check_coverage_feasibility(floors, frame, facilities, distance_matrix(frame, facilities),
                                          cfg["allocation"]["max_distance_km"], int(cfg["allocation"]["budget_tests"]))
    invited = allocations[allocations.invited].groupby(["policy", "municipality"]).size()
    atomic_text(directory / "coverage_check.json", json.dumps(dict(
        requirements=coverage["required"], feasibility=coverage["details"],
        invitations_by_policy={policy: invited.get(policy, pd.Series(dtype=int)).to_dict() for policy in allocations.policy.unique()},
        rule="ALLOC-12: checked before allocation; infeasible requirements stop the run instead of being relaxed."), indent=2))


def allocation_metrics(records, cfg):
    rows = []
    records = records.copy()
    records["age_band"] = pd.cut(records.age, [17, 39, 59, 120], labels=["18–39", "40–59", "60+"]).astype(str)
    for policy, group in records.groupby("policy", sort=True):
        subgroups = [("all", "all", group)]
        for field in ("municipality", "reported", "age_band", "female", "outdoor_true"):
            subgroups += [(field, str(value), subset) for value, subset in group.groupby(field, observed=True)]
        for dimension, value, subset in subgroups:
            n, completed, detected = len(subset), int(subset.completed.sum()), int(subset.positive_detected.sum())
            eligible_positive = int(subset.y_true.sum())
            feasible = int(subset.access_feasible.sum())
            rows.append(dict(policy=policy, subgroup=dimension, value=value, eligible=n,
                             invitations=int(subset.invited.sum()), completions=completed, positives_detected=detected,
                             eligible_positives=eligible_positive, positives_not_detected=eligible_positive - detected,
                             positives_per_100_completed=100 * detected / completed if completed else np.nan,
                             completion_coverage=completed / n if n else np.nan,
                             feasible_population=feasible, feasible_completion_coverage=completed / feasible if feasible else np.nan,
                             access_excluded_positives=int((subset.y_true & ~subset.access_feasible).sum()),
                             not_invited_feasible_positives=int((subset.y_true & subset.access_feasible & ~subset.invited).sum()),
                             incomplete_positives=int((subset.y_true & subset.invited & ~subset.completed).sum()),
                             slot_use=int(subset.invited.sum()) / cfg["allocation"]["budget_tests"] if dimension == "all" and cfg["allocation"]["budget_tests"] else np.nan,
                             modeled_panel_cost_php=completed * cfg["prototype"]["assumed_panel_cost_php"],
                             cost_per_positive_php=completed * cfg["prototype"]["assumed_panel_cost_php"] / detected if detected else np.nan,
                             **represented(subset)))
    return pd.DataFrame(rows)


def represented(subset):
    """EVAL-05: population-weighted counts and coverage alongside the sampled-cohort figures.

    Weights are the adults each sampled resident represents in the deployment frame. Draws are
    proportional to population, so weights are equal within a cohort and the weighted coverage
    share matches the cohort share; the counts are on the represented-population scale.
    """
    if "representation_weight" not in subset:
        return dict(represented_adults=np.nan, represented_completions=np.nan,
                    represented_positives_detected=np.nan, population_weighted_coverage=np.nan)
    weight = subset.representation_weight.to_numpy(float)
    adults = weight.sum()
    completions = (weight * subset.completed.to_numpy()).sum()
    return dict(represented_adults=adults, represented_completions=completions,
                represented_positives_detected=(weight * subset.positive_detected.to_numpy()).sum(),
                population_weighted_coverage=completions / adults if adults else np.nan)


def evaluate(cfg, directory):
    metrics = allocation_metrics(pd.read_parquet(directory / "allocations_hidden.parquet"), cfg)
    metrics.to_csv(directory / "metrics.csv", index=False)
    headline = metrics[metrics.subgroup == "all"]
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".venv/matplotlib-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axis = plt.subplots(figsize=(9, 5), layout="constrained")
    axis.scatter(headline.completion_coverage * 100, headline.positives_per_100_completed, color="#34705a")
    for row in headline.itertuples():
        axis.annotate(row.policy, (row.completion_coverage * 100, row.positives_per_100_completed), xytext=(4, 4), textcoords="offset points", fontsize=8)
    axis.set(title="Detection yield versus population reach · synthetic experiment",
             xlabel="Completed panels / all eligible deployment adults (%)",
             ylabel="Initial positives per 100 completed panels")
    figure.text(.02, .01, "Source: saved AGAP-CKD run · one synthetic repetition · assumed service points and costs", fontsize=8)
    figure.savefig(directory / "efficiency_coverage.png", dpi=160)
    plt.close(figure)
    page = "<!doctype html><html><meta charset='utf-8'><title>AGAP-CKD experiment</title><body style='font:16px system-ui;max-width:1200px;margin:40px auto'>"
    page += "<h1>Screening allocation experiment</h1><p><strong>SYNTHETIC DATA — one repetition; no clinical effectiveness claim.</strong></p>"
    page += f"<p>Geography: {html.escape(cfg['prototype']['geography_mode'])}. Climate: {html.escape(climate_mode(cfg))}. Clinical states, climate-health effects, facilities, capacities, and costs are simulated.</p>"
    page += "<img src='efficiency_coverage.png' alt='Detection yield versus population reach' style='max-width:100%'>"
    page += headline.to_html(index=False, float_format=lambda value: f"{value:.3f}")
    page += "<p>Coverage denominator: all eligible deployment adults in the sampled cohort (completion_coverage) or the adults they represent (population_weighted_coverage, with represented_* counts). Residents are sampled in proportion to population, so the two shares match while the counts differ in scale. Yield denominator: completed initial panels. Positive means an initial abnormal screening flag.</p></body></html>"
    atomic_text(directory / "report.html", page)
    return metrics


def execute(cfg, stage="all", repetition=0, publish=True):
    directory = run_path(cfg)
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else dict(
        run_id=directory.name, config_hash=fingerprint(cfg), source_hash=source_hash(), configuration=cfg,
        input_checksums=input_checksums(cfg), seed=cfg["seed"], repetition=repetition,
        packages={name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scikit-learn", "h3", "streamlit")},
        started_utc=datetime.now(timezone.utc).isoformat(), stages={})
    try:
        manifest["git_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError:
        manifest["git_commit"] = None
    manifest["climate_mode"] = climate_mode(cfg)
    manifest["limitations"] = ["Synthetic outcomes and assumed climate-health effect; no empirical heat effect estimated.",
                               "Hypothetical service points and equal capacity, not verified clinics.",
                               "Simulator-known IPW; no deployable missingness correction claimed.",
                               "Single-repetition model results until make experiments completes."]
    if climate_mode(cfg) == "synthetic":
        manifest["limitations"].append("Climate exposure is an artificial fixture signal, not observed weather.")
    else:
        manifest["limitations"].append("Historical climate reanalysis is a community proxy, not personal exposure or a live forecast; incomplete source cells are excluded and disclosed in climate_frame.json.")
    stages = list(STAGES) if stage == "all" else [stage]
    for name in stages:
        try:
            manifest["stages"][name] = "running"
            atomic_text(manifest_path, json.dumps(manifest, indent=2))
            if name == "data":
                build_data(cfg, directory)
            elif name == "simulate":
                simulate(cfg, directory, repetition)
            elif name == "integrity":
                from agap.integrity import integrity  # imports this module
                integrity(cfg, directory)
            elif name == "spatial":
                from agap.spatial import spatial  # imports this module
                spatial(cfg, directory)
            elif name == "longitudinal":
                from agap.longitudinal import longitudinal  # imports this module
                longitudinal(cfg, directory, repetition)
            elif name == "surveillance":
                from agap.surveillance import surveil  # imports this module
                surveil(cfg, directory, repetition)
            else:
                {"train": train, "allocate": allocate, "evaluate": evaluate}[name](cfg, directory)
            manifest["stages"][name] = "complete"
        except Exception as exc:
            manifest["stages"][name] = f"failed: {type(exc).__name__}: {exc}"
            atomic_text(manifest_path, json.dumps(manifest, indent=2))
            raise
        atomic_text(manifest_path, json.dumps(manifest, indent=2))
    if publish and all(manifest["stages"].get(s) == "complete" for s in ("data", "simulate", "train", "allocate", "evaluate")):
        atomic_text(ROOT / "outputs/latest_run.json", json.dumps({"path": str(directory), "config_hash": fingerprint(cfg)}))
    return directory
