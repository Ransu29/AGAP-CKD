"""Exploratory surveillance of synthetic abnormal screening flags (SRS E2-07 to E2-11).

Each month a fresh synthetic screening sample is drawn from the run's population
frame with the existing outcome and observation equations. Observed summaries and
hidden-population evaluation summaries are kept in separate columns; hidden
columns carry a ``hidden_`` prefix and are never forecast inputs. Counts are
synthetic abnormal screening flags, not CKD incidence, cases or AKI surveillance.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from agap.climate.integration import PARTITION_DATES, climate_mode, validated_exposure
from agap.experiment import atomic_text, save_frame, simulate_cohort

PROVINCE = "Province total"
SURVEILLANCE_COMPONENT = 1000  # rng component offset; partitions use 1-30
TARGET = "observed_positivity_per_100"
METHODS = ("seasonal_naive", "candidate_no_climate", "candidate")
LABEL = ("Synthetic abnormal screening flags from a simulated monthly screening sample. "
         "Not CKD incidence, cases or AKI surveillance; the climate relationship is an assumed "
         "simulation input, not evidence that El Niño causes kidney disease.")


def surveillance_months():
    start, end = PARTITION_DATES["train"][0], PARTITION_DATES["deployment"][1]
    return pd.period_range(start, end, freq="M"), pd.Timestamp(end)


def simulate_panel(cfg, cells, demographics, facilities, repetition=0, exposure=None):
    """Draw one screening sample per month; each sample only uses that month's dates.

    A month with no climate-supported population (for example a source data gap) is
    skipped, not imputed, and listed in panel.attrs["months_without_climate"].
    """
    count = int(cfg.get("surveillance", {}).get("monthly_sample", 1000))
    months, last_day = surveillance_months()
    total_adults = float(demographics.adult_count.sum())
    columns = ["resident_id", "month", "municipality", "era5_cell", "cutoff", "hot_dry_score", "reported",
               "round0_invited", "round0_completed", "observed_label", "y_true",
               "representation_weight", "climate_supported_fraction"]
    frames, skipped = [], []
    for index, month in enumerate(months):
        period = (month.start_time.normalize(), min(month.end_time.normalize(), last_day))
        month_cells = cells
        if exposure is not None:
            available = exposure.loc[exposure.complete.eq(True) & exposure.cutoff.between(*period), "era5_cell"]
            month_cells = cells[cells.era5_cell.isin(available.unique())]
        month_demographics = demographics[demographics.h3.isin(month_cells.h3)]
        represented = float(month_demographics.adult_count.sum())
        if month_demographics.empty:
            skipped.append(str(month))
            continue
        frame = simulate_cohort(cfg, month_cells, month_demographics, facilities, repetition, "surveillance",
                                heldout=[], exposure=exposure, period=period, count=count,
                                component=SURVEILLANCE_COMPONENT + index)
        frame["resident_id"] = [f"SYN-SURV-{month.strftime('%Y%m')}-{i:06d}" for i in range(count)]
        frame["month"] = month.start_time
        frame["representation_weight"] = represented / count
        frame["climate_supported_fraction"] = represented / total_adults
        frames.append(frame[columns])
    if not frames:
        raise ValueError("No surveillance month has climate-supported population; check the climate inputs")
    panel = pd.concat(frames, ignore_index=True)
    panel.attrs["months_without_climate"] = skipped
    return panel


def monthly_summary(panel):
    """Month × municipality rows plus a province total, with every numerator and denominator."""
    frame = panel.assign(
        tested=panel.round0_completed.astype(bool),
        observed_abnormal=panel.observed_label.eq(1),
        hidden_abnormal=panel.y_true.astype(bool))
    aggregations = dict(
        sampled_adults=("resident_id", "size"), represented_adults=("representation_weight", "sum"),
        mean_hot_dry_score=("hot_dry_score", "mean"), climate_supported_fraction=("climate_supported_fraction", "first"),
        reported=("reported", "sum"), tested=("tested", "sum"), observed_abnormal=("observed_abnormal", "sum"),
        hidden_abnormal=("hidden_abnormal", "sum"))
    local = frame.groupby(["month", "municipality"], as_index=False).agg(**aggregations)
    province = frame.groupby("month", as_index=False).agg(**aggregations).assign(municipality=PROVINCE)
    summary = pd.concat([province, local], ignore_index=True)
    for column in ("sampled_adults", "reported", "tested", "observed_abnormal", "hidden_abnormal"):
        summary[column] = summary[column].astype(int)
    summary["reporting_coverage"] = summary.reported / summary.sampled_adults
    summary["testing_coverage"] = summary.tested / summary.sampled_adults
    summary[TARGET] = 100 * summary.observed_abnormal / summary.tested.where(summary.tested > 0)
    summary["hidden_prevalence_per_100"] = 100 * summary.hidden_abnormal / summary.sampled_adults
    summary["hidden_undetected_abnormal"] = summary.hidden_abnormal - summary.observed_abnormal
    return summary.sort_values(["month", "municipality"]).reset_index(drop=True)


def forecast_comparison(series, holdout_months=12, horizons=(1, 3), minimum_training_months=6):
    """Rolling-origin forecasts over the last holdout months, using past months only.

    series: one row per month with ``month``, the observed target and ``mean_hot_dry_score``.
    Seasonal naïve predicts y(t-12). The candidate regresses y(s) on y(s-12) and the hot-dry
    score at s-h, fitted on months up to the origin t-h, then predicts from y(t-12) and the
    origin month's hot-dry score. candidate_no_climate is the same regression on the same
    months without the hot-dry term, so climate's contribution can be separated from the
    regression's pull towards the average (see forecast_gains).
    """
    hidden = [column for column in series.columns if column.startswith("hidden_")]
    if hidden:
        raise ValueError(f"Hidden evaluation columns cannot be forecast inputs: {hidden}")
    if any(h < 1 or h > 12 for h in horizons):
        raise ValueError("Horizons must be 1-12 months so seasonal naïve uses only past months")
    indexed = series.assign(month=pd.PeriodIndex(series.month, freq="M")).set_index("month").sort_index()
    y, x = indexed[TARGET], indexed.mean_hot_dry_score
    targets = indexed.index[-holdout_months:]
    rows = []
    for horizon in horizons:
        for target in targets:
            origin = target - horizon
            past = [s for s in indexed.index
                    if s <= origin and s - 12 in y.index and s - horizon in x.index
                    and np.isfinite([y[s], y[s - 12], x[s - horizon]]).all()]
            candidate = without_climate = np.nan
            features = [y.get(target - 12, np.nan), x.get(origin, np.nan)]
            if len(past) >= minimum_training_months and np.isfinite(features).all():
                design = np.array([[1.0, y[s - 12], x[s - horizon]] for s in past])
                observed = np.array([y[s] for s in past])
                beta = np.linalg.lstsq(design, observed, rcond=None)[0]
                candidate = float(beta @ np.array([1.0, *features]))
                beta = np.linalg.lstsq(design[:, :2], observed, rcond=None)[0]
                without_climate = float(beta @ np.array([1.0, features[0]]))
            rows.append(dict(target_month=target.start_time, origin_month=origin.start_time, horizon_months=horizon,
                             actual=y.get(target, np.nan), seasonal_naive=y.get(target - 12, np.nan),
                             candidate_no_climate=without_climate, candidate=candidate, training_months=len(past)))
    forecasts = pd.DataFrame(rows)
    metrics = []
    for horizon, group in forecasts.groupby("horizon_months"):
        for method in METHODS:
            scored = group.dropna(subset=["actual", method])
            error = scored[method] - scored.actual
            metrics.append(dict(method=method, horizon_months=horizon, holdout_months=len(scored),
                                first_target=group.target_month.min(), last_target=group.target_month.max(),
                                mae=float(error.abs().mean()) if len(scored) else np.nan,
                                rmse=float(np.sqrt((error ** 2).mean())) if len(scored) else np.nan))
    return forecasts, pd.DataFrame(metrics)


def forecast_gains(metrics):
    """Per horizon: MAE reduction from the regression itself and from adding the hot-dry term.

    Positive climate_gain means the climate term reduced error; under a zero assumed heat
    effect it should be close to zero. A candidate win over seasonal naïve alone is not
    evidence that climate helps.
    """
    mae = metrics.pivot(index="horizon_months", columns="method", values="mae")
    return pd.DataFrame({"horizon_months": mae.index,
                         "regression_gain": (mae.seasonal_naive - mae.candidate_no_climate).to_numpy(),
                         "climate_gain": (mae.candidate_no_climate - mae.candidate).to_numpy()})


def surveil(cfg, directory, repetition=0):
    settings = cfg.get("surveillance", {})
    cells = pd.read_parquet(directory / "cells.parquet")
    demographics = pd.read_parquet(directory / "demographics.parquet")
    facilities = pd.read_parquet(directory / "facilities.parquet")
    exposure = validated_exposure(directory / "climate_exposure.parquet") if climate_mode(cfg) == "era5_land" else None
    panel = simulate_panel(cfg, cells, demographics, facilities, repetition, exposure)
    summary = monthly_summary(panel)
    province = summary.loc[summary.municipality.eq(PROVINCE), ["month", TARGET, "mean_hot_dry_score"]]
    forecasts, metrics = forecast_comparison(province, int(settings.get("holdout_months", 12)),
                                             tuple(settings.get("horizons", (1, 3))))
    save_frame(summary, directory / "surveillance_monthly.parquet")
    save_frame(forecasts, directory / "surveillance_forecasts.parquet")
    metrics.to_csv(directory / "surveillance_forecast_metrics.csv", index=False)
    atomic_text(directory / "surveillance.json", json.dumps(dict(
        label=LABEL, monthly_sample=int(settings.get("monthly_sample", 1000)),
        months=len(summary.month.unique()), first_month=str(summary.month.min().date()),
        last_month=str(summary.month.max().date()), target=TARGET,
        holdout_months=int(settings.get("holdout_months", 12)), horizons=list(settings.get("horizons", (1, 3))),
        climate=climate_mode(cfg), mechanism=cfg["prototype"]["mechanism"], heat_or=cfg["prototype"]["heat_or"],
        hidden_columns="Columns prefixed hidden_ use simulator truth for evaluation only and are not observable in practice.",
        months_without_climate=panel.attrs.get("months_without_climate", []),
        repetition=repetition), indent=2))
    return summary, forecasts, metrics
