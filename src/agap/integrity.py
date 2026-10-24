"""INT-01 / INT-02 integrity checks on a completed run's saved artifacts.

INT-01: record references resolve to valid residents, facilities, scenarios and runs.
INT-02: probabilities and scores lie in [0, 1]; counts, capacities and populations are nonnegative.
Missing values are allowed where the pipeline uses them for "unknown" or "undefined"; they are
not range violations. Files from stages that did not run are skipped and listed.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from agap.experiment import atomic_text

MECHANISMS = {"MCAR", "MAR", "MNAR"}
POLICIES = {"random", "population_proportional", "risk_ranked"}
MIXED_POLICY = re.compile(r"risk_(explore|unreported)_\d{1,3}")

# INT-02: file -> columns that must lie in [0, 1], or be nonnegative, where present and not missing.
UNIT_INTERVAL = {
    "train_hidden.parquet": ["report_probability", "completion_probability", "observation_probability"],
    "validation_hidden.parquet": ["report_probability", "completion_probability", "observation_probability"],
    "deployment_hidden.parquet": ["report_probability", "completion_probability", "observation_probability"],
    "predictions.parquet": ["score", "threshold", "input_completeness", "target_sensitivity"],
    "allocations_hidden.parquet": ["score", "invitation_probability"],
    "metrics.csv": ["completion_coverage", "feasible_completion_coverage", "slot_use", "population_weighted_coverage"],
    "model_metrics.csv": ["auroc", "auprc", "brier", "sensitivity", "specificity", "fnr", "target_sensitivity"],
    "surveillance_monthly.parquet": ["reporting_coverage", "testing_coverage", "climate_supported_fraction"],
}
NONNEGATIVE = {
    "cells.parquet": ["adult_count"],
    "demographics.parquet": ["adult_count"],
    "facilities.parquet": ["capacity"],
    "deployment_hidden.parquet": ["representation_weight", "municipality_represented_adults", "nearest_distance_km", "age"],
    "allocations_hidden.parquet": ["distance_km", "representation_weight"],
    "metrics.csv": ["eligible", "invitations", "completions", "positives_detected", "eligible_positives", "positives_not_detected",
                    "feasible_population", "access_excluded_positives", "not_invited_feasible_positives", "incomplete_positives",
                    "modeled_panel_cost_php", "cost_per_positive_php", "represented_adults", "represented_completions",
                    "represented_positives_detected", "positives_per_100_completed"],
    "surveillance_monthly.parquet": ["sampled_adults", "represented_adults", "reported", "tested", "observed_abnormal",
                                     "hidden_abnormal", "hidden_undetected_abnormal"],
    "longitudinal_metrics.csv": ["included_residents", "initial_positives_detected", "followup_invited", "observed_persistent",
                                 "observed_transient", "observed_unknown"],
}
PER_HUNDRED = {"metrics.csv": ["positives_per_100_completed"],
               "surveillance_monthly.parquet": ["observed_positivity_per_100", "hidden_prevalence_per_100"]}


class IntegrityError(ValueError):
    """A saved run violates INT-01 or INT-02."""


def _read(directory, name):
    path = directory / name
    if not path.exists():
        return None
    return pd.read_csv(path) if name.endswith(".csv") else pd.read_parquet(path)


def _outside(values, low, high=np.inf):
    values = pd.to_numeric(values, errors="coerce").dropna()
    return int(((values < low) | (values > high)).sum())


def check_run(directory):
    """Return the checks performed; raise IntegrityError listing every violation."""
    problems, checks, skipped, cache = [], [], [], {}

    def frame(name):
        if name not in cache:
            cache[name] = _read(directory, name)
            if cache[name] is None:
                skipped.append(name)
        return cache[name]

    def require(condition, description):
        checks.append(description)
        if not condition:
            problems.append(description)

    # INT-01: references
    manifest = json.loads((directory / "manifest.json").read_text())
    require(manifest.get("run_id", directory.name) == directory.name, "manifest run_id matches its run folder")
    require(manifest["configuration"]["prototype"]["mechanism"] in MECHANISMS, "scenario mechanism is MCAR, MAR or MNAR")
    deployment, cells, facilities = frame("deployment_hidden.parquet"), frame("cells.parquet"), frame("facilities.parquet")
    residents = set(deployment.resident_id)
    for name in ("train_hidden.parquet", "validation_hidden.parquet", "deployment_hidden.parquet"):
        cohort = frame(name)
        if cohort is not None:
            require(cohort.resident_id.is_unique, f"{name}: resident IDs are unique")
            require(cohort.h3.isin(cells.h3).all(), f"{name}: every H3 cell exists in cells")
            require(cohort.era5_cell.isin(cells.era5_cell).all(), f"{name}: every climate cell exists in cells")
    require(facilities.facility_id.is_unique, "facilities: IDs are unique")
    for name in ("predictions.parquet", "allocations_hidden.parquet", "longitudinal_hidden.parquet"):
        records = frame(name)
        if records is not None:
            require(records.resident_id.isin(residents).all(), f"{name}: every resident is a deployment resident")
    allocations = frame("allocations_hidden.parquet")
    if allocations is not None:
        assigned = allocations.facility_id.dropna()
        require(assigned.isin(facilities.facility_id).all(), "allocations: every assigned facility exists")
        require(all(p in POLICIES or MIXED_POLICY.fullmatch(p) for p in set(allocations.policy)), "allocations: every policy is a known policy")
        require(not allocations.duplicated(["policy", "resident_id"]).any(), "allocations: one record per resident per policy")
        require(allocations.facility_id.notna().eq(allocations.invited).all(), "allocations: facility assigned exactly when invited")
    predictions = frame("predictions.parquet")
    if predictions is not None:
        require(not predictions.duplicated(["resident_id", "model", "target_sensitivity"]).any(),
                "predictions: one record per resident, model and target")
    for name in ("metrics.csv", "longitudinal_metrics.csv"):
        table = frame(name)
        if table is not None and allocations is not None:
            require(set(table.policy) <= set(allocations.policy), f"{name}: every policy appears in the allocations")

    # INT-02: ranges
    for name, columns in UNIT_INTERVAL.items():
        table = frame(name)
        for column in columns if table is not None else []:
            if column in table:
                require(_outside(table[column], 0, 1) == 0, f"{name}: {column} lies in [0, 1]")
    for name, columns in PER_HUNDRED.items():
        table = frame(name)
        for column in columns if table is not None else []:
            if column in table:
                require(_outside(table[column], 0, 100) == 0, f"{name}: {column} lies in [0, 100]")
    for name, columns in NONNEGATIVE.items():
        table = frame(name)
        for column in columns if table is not None else []:
            if column in table:
                require(_outside(table[column], 0) == 0, f"{name}: {column} is nonnegative")

    if problems:
        raise IntegrityError("Run integrity checks failed (INT-01/INT-02): " + "; ".join(problems))
    return dict(checks=checks, skipped_missing_files=sorted(set(skipped)))


def integrity(cfg, directory):
    result = check_run(directory)
    atomic_text(directory / "integrity.json", json.dumps(dict(result, passed=len(result["checks"]),
                                                              rule="INT-01 references resolve; INT-02 ranges hold"), indent=2))
    return result
