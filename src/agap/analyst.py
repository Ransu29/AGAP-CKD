"""PRD v3 analyst view: area totals from simulated checks, climate context and model quality.

The analyst sees aggregated area numbers only, never individual checks. Checks are simulated with the
PRD v3 risk-check simulator, one cohort per municipality with that municipality's WorldPop adult age
mix (the risk-factor generators are the same everywhere), and scored with the frozen risk-level model,
its saved cut-offs and the guideline floor. Every aggregate is computed from questionnaire answers
and risk levels only: hidden traits and labs are dropped before aggregation, and no abnormal-screen
rate is shown per area. Channel, reminder and sync fields are assumed and labelled illustrative.

Privacy display rules (PRD v3): areas under ``hide_below_checks`` get no values; areas under
``fade_below_checks`` are faded; top reasons are withheld under ``factors_min_checks``.
"""
from __future__ import annotations

import copy
import json
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from agap.simulate.risk_check import DONT_KNOW, HIDDEN_COLUMNS, risk_check_cohort
from agap.risk_check_service import score_frame
from agap.triage import LEVELS, benchmark, floored, rng_for

CHANNELS = ("app", "field", "sms")
EFFECT_LABELS = {"age_40_49": "Age 40–49", "age_50_59": "Age 50–59", "age_60_69": "Age 60–69", "age_70_plus": "Age 70+",
                 "female": "Female", "diabetes": "Diabetes", "hypertension": "High blood pressure",
                 "kidney_stones": "Kidney stones", "heart_disease_stroke": "Heart disease or stroke",
                 "family_history": "Family history", "overweight": "Overweight (BMI 23–27.4)", "obese": "Obese (BMI ≥ 27.5)",
                 "stopped_medicine": "Stopped medicine", "heavy_outdoor_work": "Heavy outdoor work",
                 "community_heat_per_sd": "Community heat, per SD (outcome only; not in the risk level)"}
MONTHS_TL = ("Ene", "Peb", "Mar", "Abr", "May", "Hun", "Hul", "Ago", "Set", "Okt", "Nob", "Dis")


def display_name(municipality):
    """Short name used on the map: "City of Calamba" -> "Calamba", "Cabuyao City" -> "Cabuyao"."""
    name = unicodedata.normalize("NFC", municipality)
    return name.removeprefix("City of ").removesuffix(" City").strip()


def month_label(timestamp):
    return f"{MONTHS_TL[timestamp.month - 1]} {timestamp.year}"


# --- Simulated checks -------------------------------------------------------------------------

def allocate_checks(adults, total, rng):
    """Checks per municipality: a multinomial draw in proportion to adults."""
    counts = rng.multinomial(total, adults.adults / adults.adults.sum())
    return pd.Series(counts, index=adults.municipality)


def simulate_checks(cfg, adults, model, cutoffs):
    """One row per simulated check: answers, risk level and assumed channel fields. No hidden columns."""
    settings, sim = cfg["analyst"], cfg["simulator"]["analyst_checks"]
    rng = np.random.default_rng(cfg["seed"] * 1000 + settings["seed_component"])
    counts = allocate_checks(adults, sim["total_checks"], rng)
    groups = cfg["simulator"]["risk_check"]["age_groups"]
    parts = []
    for row in adults.to_dict("records"):
        n = int(counts[row["municipality"]])
        if n == 0:
            continue
        local = copy.deepcopy(cfg)
        local["simulator"]["risk_check"]["age_group_shares"] = [row[f"share_{g}"] for g in groups]
        local["simulator"]["risk_check"]["female_share"] = row["female_share"]
        cohort = risk_check_cohort(local, n, rng)
        cohort.insert(0, "municipality", row["municipality"])
        parts.append(cohort)
    checks = pd.concat(parts, ignore_index=True)
    # Same scoring as the citizen, field and SMS channels (ADR 0003).
    levels, _, _ = score_frame(checks, model, cutoffs, cfg)
    checks["risk_level"] = np.asarray(LEVELS)[levels]
    shares = np.array([sim["channel_shares"][c] for c in CHANNELS], float)
    checks["channel"] = np.asarray(CHANNELS)[rng.choice(len(CHANNELS), len(checks), p=shares / shares.sum())]
    sms_opt_in = checks.channel.eq("sms") & (rng.random(len(checks)) < sim["sms_reminder_opt_in"])
    checks["done_reply"] = sms_opt_in & checks.risk_level.ne("Low") & (rng.random(len(checks)) < sim["done_reply_share"])
    # The analyst never sees the simulator's truth or the labs.
    return checks.drop(columns=[c for c in HIDDEN_COLUMNS if c in checks.columns])


def load_adults(laguna):
    """Municipal age mix from WorldPop (the only municipal age source) with adults from the PSA 2024 Census."""
    worldpop = pd.read_csv(laguna / "municipal_adults.csv").drop(columns="adults")
    psa = pd.read_csv(laguna / "municipal_population_psa2024.csv")[["municipality", "adults_18plus"]]
    adults = worldpop.merge(psa.rename(columns={"adults_18plus": "adults"}), on="municipality", validate="one_to_one")
    if len(adults) != len(psa):
        raise ValueError("WorldPop and PSA municipality names do not match")
    return adults


def load_age_weights(laguna):
    """Laguna's adult age-group shares (PSA 2024 Census), the age-standardisation weights."""
    age = pd.read_csv(laguna / "age_structure_psa2024.csv")
    return dict(zip(age.age_group, age.share))


def recorded_checks(records, cfg):
    """Checks recorded by the channels (app checks when scored, field checks when synced) as rows like
    :func:`simulate_checks`. Only checks with a risk level count: the safety pre-check and already-diagnosed
    routes have none. Answers only; no names or IDs are ever recorded."""
    rows = []
    for record in records:
        level = record.get("risk_level") or record.get("outcome")
        answers = record.get("answers") or {}
        if level not in LEVELS or not record.get("municipality") or not answers.get("age_group"):
            continue
        height, weight = answers.get("height_cm"), answers.get("weight_kg")
        bmi = weight / (height / 100) ** 2 if height and weight else np.nan
        rows.append(dict(municipality=record["municipality"], age_group=answers["age_group"], sex=answers.get("sex", ""),
                         diabetes=answers.get("diabetes", DONT_KNOW), high_blood_pressure=answers.get("high_blood_pressure", DONT_KNOW),
                         bp_reading=answers.get("bp_reading") or "", medicine=answers.get("medicine") or "",
                         heart_disease_stroke=answers.get("heart_disease_stroke", DONT_KNOW),
                         kidney_stones=answers.get("kidney_stones", DONT_KNOW), family_history=answers.get("family_history", DONT_KNOW),
                         heavy_outdoor_work=answers.get("heavy_outdoor_work", DONT_KNOW), bmi_reported=bmi,
                         kidney_status=answers.get("kidney_status", DONT_KNOW), risk_level=level,
                         channel=record.get("channel", "field"), done_reply=False, recorded=True))
    return pd.DataFrame(rows)


def overview_with_recorded(simulated, records, adults, cfg, weights, base):
    """A1/A2 recomputed over the simulated checks plus checks recorded by the channels, so a field or app
    check reaches the map. ``base`` is the built overview; its run and source fields are kept."""
    recorded = recorded_checks(records, cfg)
    if recorded.empty:
        return base
    combined = pd.concat([simulated.assign(recorded=False), recorded], ignore_index=True)
    area = overview(combined, adults, cfg, weights)
    for key in ("built_with", "model_run"):
        if key in base:
            area[key] = base[key]
    by_channel = recorded.channel.value_counts().to_dict()
    area["summary"]["recorded_checks"] = dict(total=len(recorded), by_channel=by_channel)
    area["sources"]["recorded"] = (f"Includes {len(recorded)} check(s) recorded on this demo through the app or field tablet "
                                   f"(scored with the same model), added to the simulated checks.")
    return area


# --- Area aggregates --------------------------------------------------------------------------

def standardised_share(age_group, flag, weights):
    """Directly age-standardised share with a 95% normal-approximation range.

    ``weights`` are the Laguna adult age-group shares. Age groups with no checks in the area are
    dropped and the remaining weights renormalised. The variance sum(w^2 p (1 - p) / n) uses
    p = (x + 0.5) / (n + 1) so that a group with 0% or 100% still contributes uncertainty.
    """
    frame = pd.DataFrame(dict(group=age_group, flag=np.asarray(flag, bool)))
    stats = frame.groupby("group").flag.agg(["sum", "count"])
    w = pd.Series(weights).reindex(stats.index).fillna(0.0)
    w = w / w.sum()
    rate = float((w * stats["sum"] / stats["count"]).sum())
    p_var = (stats["sum"] + 0.5) / (stats["count"] + 1)
    se = float(np.sqrt((w ** 2 * p_var * (1 - p_var) / stats["count"]).sum()))
    return rate, max(0.0, rate - 1.96 * se), min(1.0, rate + 1.96 * se)


def factor_shares(checks, cfg):
    """Shares of the PRD v3 modifiable factors, from answers only."""
    obese_cut = cfg["simulator"]["risk_check"]["traits"]["bmi_obese_cut"]
    return {
        "Unknown BP or sugar": (checks.diabetes.eq(DONT_KNOW) | checks.high_blood_pressure.eq(DONT_KNOW)).mean(),
        "Heavy outdoor work": checks.heavy_outdoor_work.eq("Yes").mean(),
        f"Obesity (BMI ≥ {obese_cut:g})": checks.bmi_reported.ge(obese_cut).mean(),
        "Stopped medicine": checks.medicine.eq("Stopped").mean(),
    }


def awareness_gap(checks):
    return float((checks.diabetes.eq(DONT_KNOW) | checks.high_blood_pressure.eq(DONT_KNOW)).mean())


def channel_split(checks):
    return {c: round(100 * float(checks.channel.eq(c).mean()), 1) for c in CHANNELS}


def municipality_rows(checks, adults, cfg, period_end, weights):
    """One record per municipality with the PRD v3 display rules applied (values withheld, not just hidden).

    ``adults`` gives each municipality's adults (the coverage denominator); ``weights`` are the age-group
    shares the Medium/High share is standardised to."""
    settings, sim = cfg["analyst"], cfg["simulator"]["analyst_checks"]
    province_factors = factor_shares(checks, cfg)
    rng = np.random.default_rng(cfg["seed"] * 1000 + settings["seed_component"] + 1)
    low, high = sim["field_sync_lag_hours"]
    rows = []
    for row in adults.itertuples(index=False):
        local = checks[checks.municipality == row.municipality]
        n = len(local)
        lag = float(rng.uniform(low, high))
        record = dict(municipality=row.municipality, name=display_name(row.municipality), checks=n, adults=int(row.adults),
                      hidden=n < settings["hide_below_checks"],
                      faded=settings["hide_below_checks"] <= n < settings["fade_below_checks"])
        if record["hidden"]:
            record.update(medium_high_share=None, range_low=None, range_high=None, coverage_pct=None,
                          awareness_gap=None, channel_split=None, factors=None, done_replies=None, last_synced=None)
            rows.append(record)
            continue
        share, lo, hi = standardised_share(local.age_group, local.risk_level.ne("Low"), weights)
        record.update(medium_high_share=round(100 * share, 1), range_low=round(100 * lo, 1), range_high=round(100 * hi, 1),
                      crude_medium_high_share=round(100 * float(local.risk_level.ne("Low").mean()), 1),
                      coverage_pct=round(100 * n / row.adults, 3), awareness_gap=round(100 * awareness_gap(local), 1),
                      channel_split=channel_split(local), done_replies=int(local.done_reply.sum()),
                      last_synced=(period_end - pd.Timedelta(hours=lag)).isoformat(timespec="minutes")
                      if local.channel.eq("field").any() else None)
        if n >= settings["factors_min_checks"]:
            factors = [dict(label=label, share=round(100 * float(value), 1),
                            difference_pts=round(100 * float(value - province_factors[label]), 1))
                       for label, value in factor_shares(local, cfg).items()]
            record["factors"] = sorted(factors, key=lambda f: f["difference_pts"], reverse=True)
        else:
            record["factors"] = None
        rows.append(record)
    return rows


def overview(checks, adults, cfg, weights):
    """A1/A2 data. ``adults``: municipality and adults (PSA 2024); ``weights``: Laguna age-group shares (PSA 2024)."""
    settings = cfg["analyst"]
    period_end = pd.Timestamp(settings["checks_period_end"]) + pd.Timedelta(hours=18)
    period_start = (pd.Timestamp(settings["checks_period_end"]) - pd.DateOffset(months=settings["period_months"])
                    + pd.DateOffset(days=1))
    share, lo, hi = standardised_share(checks.age_group, checks.risk_level.ne("Low"), weights)
    return dict(
        province="Laguna",
        period=dict(start=period_start.date().isoformat(), end=settings["checks_period_end"],
                    label=f"{month_label(period_start)} – {month_label(period_end)}"),
        rules=dict(hide_below_checks=settings["hide_below_checks"], fade_below_checks=settings["fade_below_checks"],
                   factors_min_checks=settings["factors_min_checks"]),
        summary=dict(checks=len(checks), adults=int(adults.adults.sum()),
                     coverage_pct=round(100 * len(checks) / adults.adults.sum(), 3),
                     medium_high_share=round(100 * share, 1), range_low=round(100 * lo, 1), range_high=round(100 * hi, 1),
                     awareness_gap=round(100 * awareness_gap(checks), 1), channel_split=channel_split(checks),
                     done_replies=int(checks.done_reply.sum())),
        municipalities=municipality_rows(checks, adults, cfg, period_end, weights),
        sources=dict(
            checks="Simulated with the PRD v3 risk-check simulator and scored with the frozen risk-level model, its saved "
                   "cut-offs and the guideline floor. Same risk-factor generators in every municipality; only the "
                   "age mix differs (WorldPop 2020, the only municipal age source).",
            standardisation="Direct age standardisation to Laguna's adult age structure (PSA 2024 Census), 5 PRD v3 age groups.",
            adults="Adults = PSA 2024 Census municipal population x Laguna's 18+ share (PSA publishes age groups by "
                   "province only).",
            illustrative="Channel split, last sync, DONE replies and top reasons are illustrative: no SMS or field data exist yet."),
    )


# --- Climate context --------------------------------------------------------------------------

def last_complete_months(daily, months):
    """The ``months`` calendar months ending with the last month that has every day in the data."""
    dates = daily.local_date.drop_duplicates().sort_values()
    last = dates.max()
    end = last.to_period("M") if (last + pd.Timedelta(days=1)).month != last.month else last.to_period("M") - 1
    return pd.period_range(end=end, periods=months, freq="M")


def _complete_months(frame, value_columns):
    """Per ERA5 cell and month, keep only months with every day present."""
    by_cell = frame.groupby(["era5_cell", "period"]).agg(days=("local_date", "size"), **value_columns).reset_index()
    return by_cell[by_cell.days == by_cell.period.dt.days_in_month].drop(columns="days")


def climate_context(daily, heat, cell_weights, cfg):
    """Monthly hot days, peak heat index, rainfall and mean daily maximum per municipality.

    ``daily``: ERA5-Land daily temperature and rainfall (ARCO extract). ``heat``: daily maximum heat index per
    ERA5-Land cell (Open-Meteo ERA5-Land temperature and humidity). Both are population-weighted to
    municipalities; cells without a complete month are dropped and the weights renormalised.
    """
    settings = cfg["analyst"]
    threshold = settings["heat_index_hot_c"]
    daily = daily.assign(local_date=pd.to_datetime(daily.local_date))
    heat = heat.assign(local_date=pd.to_datetime(heat.local_date))
    months = last_complete_months(daily, settings["period_months"])
    weather = daily[daily.complete & daily.local_date.dt.to_period("M").isin(months)].assign(
        period=lambda d: d.local_date.dt.to_period("M"))
    weather = _complete_months(weather, dict(rain_mm=("precip_mm", "sum"), mean_tmax_c=("tmax_c", "mean")))
    hot = heat[heat.complete & heat.local_date.dt.to_period("M").isin(months)].assign(
        period=lambda d: d.local_date.dt.to_period("M"), hot=lambda d: d.max_heat_index_c >= threshold)
    hot = _complete_months(hot, dict(hot_days=("hot", "sum"), peak_heat_index_c=("max_heat_index_c", "max")))

    def weighted(by_cell, columns):
        merged = cell_weights.merge(by_cell, on="era5_cell")
        merged["w"] = merged.weight / merged.groupby(["municipality", "period"]).weight.transform("sum")
        for column in columns:
            merged[column] = merged.w * merged[column]
        return merged.groupby(["municipality", "period"])[columns].sum()

    # Hot days and rainfall are population-weighted averages; the peak is the hottest cell's peak.
    table = weighted(weather, ["rain_mm", "mean_tmax_c"]).join(weighted(hot, ["hot_days"]), how="outer")
    peak = cell_weights.merge(hot, on="era5_cell").groupby(["municipality", "period"]).peak_heat_index_c.max()
    table = table.join(peak, how="left").reset_index()
    out = {}
    for municipality, group in table.groupby("municipality"):
        series = [dict(month=row.period.strftime("%Y-%m"), label=MONTHS_TL[row.period.month - 1],
                       hot_days=None if pd.isna(row.hot_days) else round(float(row.hot_days), 1),
                       peak_heat_index_c=None if pd.isna(row.peak_heat_index_c) else round(float(row.peak_heat_index_c), 1),
                       rain_mm=None if pd.isna(row.rain_mm) else round(float(row.rain_mm), 1),
                       mean_tmax_c=None if pd.isna(row.mean_tmax_c) else round(float(row.mean_tmax_c), 1))
                  for row in group.sort_values("period").itertuples(index=False)]
        out[display_name(municipality)] = dict(municipality=municipality, series=series)
    first, last = months[0].to_timestamp(), months[-1].to_timestamp()
    return dict(period=dict(start=months[0].strftime("%Y-%m"), end=months[-1].strftime("%Y-%m"),
                            label=f"{month_label(first)} – {month_label(last)}"),
                heat_index_hot_c=threshold,
                hot_day_definition=f"Days whose highest hourly heat index reached {threshold:g}°C or more (NWS formula, "
                                   f"as used by PAGASA), averaged over the municipality's ERA5-Land cells weighted by adults",
                source="ERA5-Land reanalysis (Copernicus, 0.1°): temperature and rainfall from the ARCO extract; humidity "
                       "for the heat index via the Open-Meteo archive. A grid estimate smooths peaks, so it usually counts "
                       "fewer hot days than PAGASA's station heat index.",
                note="Context only: not used in the risk level · community-level estimate",
                municipalities=out)


# --- Model quality ----------------------------------------------------------------------------

def _level_rates(row):
    return [round(100 * row[f"abnormal_rate_{level.lower()}"], 1) for level in LEVELS]


def model_quality(outputs, cfg, register_path, model=None):
    """A4 from the frozen run's saved artifacts (never recomputed numbers, except the floor effect)."""
    outputs = Path(outputs)
    cutoffs = json.loads((outputs / "triage_cutoffs.json").read_text())
    table = pd.read_csv(outputs / "triage_benchmark.csv").set_index("arm")
    sensitivity = pd.read_csv(outputs / "triage_prevalence_sensitivity.csv")
    arms = {"thai": "Thai simplified score", "agap": "AGAP model + guideline floor", "agap_alone": "AGAP model alone"}
    rows = {key: dict(caught_pct=round(100 * table.loc[arm, "sensitivity"], 1),
                      abnormal_rate_pct=_level_rates(table.loc[arm]),
                      referred_pct=round(100 * table.loc[arm, "referred_share"], 1),
                      auroc=round(float(table.loc[arm, "auroc"]), 3)) for key, arm in arms.items()}
    floor = None
    if model is not None:
        floor = floor_effect(cfg, model, cutoffs, table.loc[arms["agap"], "auroc"])
    scenarios = []
    for target, group in sensitivity.groupby("target_prevalence"):
        g = group.set_index("arm")
        prevalence = float(g.cohort_prevalence.iloc[0])
        high = float(g.loc[arms["agap"], "abnormal_rate_high"])
        scenarios.append(dict(target_prevalence_pct=round(100 * target, 1), cohort_prevalence_pct=round(100 * prevalence, 1),
                              high_rate_pct=round(100 * high, 1), thai_high_rate_pct=round(100 * float(g.loc[arms["thai"], "abnormal_rate_high"]), 1),
                              target_rate_pct=round(100 * cutoffs["rules"]["high_min_prevalence_multiple"] * prevalence, 1),
                              meets_target=bool(high >= cutoffs["rules"]["high_min_prevalence_multiple"] * prevalence)))
    register = yaml.safe_load(Path(register_path).read_text())["parameters"]
    odds = cfg["simulator"]["risk_check"]["odds_ratios"]
    effects = []
    for name, value in odds.items():
        entry = register[f"simulator.risk_check.odds_ratios.{name}"]
        effects.append(dict(item=EFFECT_LABELS.get(name, name.replace("_", " ")), odds_ratio=value, tag=entry["class"],
                            evidence=entry.get("source") or entry.get("derivation") or entry.get("note")))
    return dict(
        run=dict(config_fingerprint=cutoffs["config_fingerprint"], git_commit=cutoffs["git_commit"], seed=cutoffs["seed"],
                 n_test=cutoffs["n_test"], n_validation=cutoffs["n_validation"], n_train=cutoffs["n_train"]),
        cohort="Held-out test cohort",
        **rows,
        cutoffs=dict(medium=round(cutoffs["t_medium"], 4), high=round(cutoffs["t_high"], 4),
                     validation_caught_pct=round(100 * cutoffs["medium_or_high_sensitivity"], 1),
                     validation_high_rate_pct=round(100 * cutoffs["high_abnormal_rate"], 1),
                     rule=f"Medium-or-High catches ≥ {round(100 * cutoffs['rules']['medium_min_sensitivity'])}% of abnormal "
                          f"screens. High has ≥ {cutoffs['rules']['high_min_prevalence_multiple']:g}× the overall abnormal rate. "
                          f"Set on the validation cohort and saved with the run."),
        floor=floor,
        prevalence_sensitivity=scenarios,
        outcome="Abnormal kidney screen = eGFR < 60 or urine ACR ≥ 30 (one measurement; not a diagnosis).",
        prevalence_source="12.76% derived from Tran 2017 (Long An, Vietnam; same definition). No population-based "
                          "Philippine study was found.",
        effect_sizes=effects,
    )


def floor_effect(cfg, model, cutoffs, expected_auroc):
    """How many held-out test levels the guideline floor raised. Regenerates the test cohort and checks it
    reproduces the saved benchmark before counting."""
    from agap.simulate.risk_check import risk_check_cohort as cohort_for

    rules = cfg["triage"]["risk_level"]
    test = cohort_for(cfg, rules["n_test"], rng_for(cfg, "test"))
    table, scored = benchmark(test, model, cutoffs, cfg)
    reproduced = float(table.set_index("arm").loc["AGAP model + guideline floor", "auroc"])
    if not np.isclose(reproduced, expected_auroc, atol=1e-9):
        raise ValueError(f"Test cohort does not reproduce the frozen benchmark (AUROC {reproduced} vs {expected_auroc})")
    after = floored(scored["levels"], scored["floor"])
    changed = after != scored["levels"]
    return dict(changed=int(changed.sum()), n=int(len(after)), changed_pct=round(100 * float(changed.mean()), 1),
                to_medium=int((changed & (after == 1)).sum()), to_high=int((changed & (after == 2)).sum()))
