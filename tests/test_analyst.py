"""PRD v3 analyst view: simulated checks, privacy display rules, standardisation, climate and model quality."""
import copy
import json

import numpy as np
import pandas as pd
import pytest

from agap.analyst import (climate_context, display_name, model_quality, overview, simulate_checks,
                          standardised_share)
from agap.climate.heat_index import heat_index_c
from agap.config import ROOT, load_config
from agap.simulate.risk_check import HIDDEN_COLUMNS, risk_check_cohort
from agap.triage import encode_features, fit_model


@pytest.fixture(scope="module")
def cfg():
    cfg = copy.deepcopy(load_config())
    cfg["simulator"]["analyst_checks"]["total_checks"] = 400
    return cfg


@pytest.fixture(scope="module")
def model(cfg):
    train = risk_check_cohort(cfg, 3000, np.random.default_rng(11))
    return fit_model(encode_features(train, cfg), train.y_true, cfg)


CUTOFFS = dict(t_medium=0.07, t_high=0.12)


@pytest.fixture(scope="module")
def adults(cfg):
    groups = cfg["simulator"]["risk_check"]["age_groups"]
    shares = cfg["simulator"]["risk_check"]["age_group_shares"]
    rows = [("City of Calamba", 900_000), ("Los Baños", 80_000), ("Famy", 5_000)]
    return pd.DataFrame([dict(municipality=name, adults=n, female_share=0.51,
                              **{f"share_{g}": s for g, s in zip(groups, shares)}) for name, n in rows])


@pytest.fixture(scope="module")
def checks(cfg, adults, model):
    return simulate_checks(cfg, adults, model, CUTOFFS)


def test_checks_hold_answers_and_levels_only(checks, cfg):
    assert len(checks) == cfg["simulator"]["analyst_checks"]["total_checks"]
    assert not set(HIDDEN_COLUMNS) & set(checks.columns)
    assert set(checks.risk_level) <= {"Low", "Medium", "High"}
    assert set(checks.channel) <= {"app", "field", "sms"}
    # A DONE reply needs an SMS opt-in with a Medium or High level.
    assert not (checks.done_reply & (checks.channel.ne("sms") | checks.risk_level.eq("Low"))).any()


def test_checks_are_deterministic(cfg, adults, model, checks):
    pd.testing.assert_frame_equal(checks, simulate_checks(cfg, adults, model, CUTOFFS))


def test_floor_applies_to_simulated_checks(checks):
    explicit = checks.diabetes.eq("Yes") | checks.high_blood_pressure.eq("Yes") | checks.bp_reading.eq("High")
    assert checks.loc[explicit, "risk_level"].ne("Low").all()


def weights(cfg):
    rc = cfg["simulator"]["risk_check"]
    return dict(zip(rc["age_groups"], rc["age_group_shares"]))


def test_privacy_rules_withhold_values(checks, adults, cfg):
    rows = {m["name"]: m for m in overview(checks, adults, cfg, weights(cfg))["municipalities"]}
    rules = cfg["analyst"]
    big, mid, small = rows["Calamba"], rows["Los Baños"], rows["Famy"]
    assert small["checks"] < rules["hide_below_checks"] and small["hidden"]
    assert all(small[k] is None for k in ("medium_high_share", "coverage_pct", "awareness_gap", "factors", "done_replies"))
    assert rules["hide_below_checks"] <= mid["checks"] < rules["fade_below_checks"] and mid["faded"]
    assert mid["medium_high_share"] is not None
    assert (mid["factors"] is None) == (mid["checks"] < rules["factors_min_checks"])
    assert big["checks"] >= rules["fade_below_checks"] and not big["faded"] and len(big["factors"]) == 4
    assert big["range_low"] <= big["medium_high_share"] <= big["range_high"]


def test_standardised_share_reweights_age_groups():
    groups = ["young"] * 100 + ["old"] * 100
    flags = [False] * 100 + [True] * 100
    rate, low, high = standardised_share(groups, flags, {"young": 0.8, "old": 0.2})
    assert rate == pytest.approx(0.2)
    assert low < rate < high
    # An age group with no checks is dropped and the remaining weights renormalised.
    rate, _, _ = standardised_share(["old"] * 10, [True] * 10, {"young": 0.8, "old": 0.2})
    assert rate == pytest.approx(1.0)


def test_display_name_matches_map_labels():
    assert display_name("City of Calamba") == "Calamba"
    assert display_name("Cabuyao City") == "Cabuyao"
    assert display_name("Biñan") == display_name("Biñan") == "Biñan"


def test_climate_context_counts_heat_index_hot_days(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["analyst"].update(period_months=2, heat_index_hot_c=41)
    dates = pd.date_range("2002-01-01", "2002-02-28", freq="D")
    frames, heat = [], []
    for cell, offset, hot_days in (("14.2,121.1", 0.0, 4), ("14.3,121.1", 1.0, 8)):
        frames.append(pd.DataFrame(dict(era5_cell=cell, local_date=dates, tmax_c=30.0 + offset, precip_mm=1.0 + offset,
                                        complete=True)))
        heat.append(pd.DataFrame(dict(era5_cell=cell, local_date=dates, complete=True,
                                      max_heat_index_c=np.where(dates.day <= hot_days, 41.0 + offset, 35.0))))
    weights = pd.DataFrame(dict(municipality=["City of Calamba", "City of Calamba"],
                                era5_cell=["14.2,121.1", "14.3,121.1"], weight=[0.75, 0.25]))
    result = climate_context(pd.concat(frames), pd.concat(heat), weights, cfg)
    assert result["period"]["start"] == "2002-01" and result["period"]["end"] == "2002-02"
    january = result["municipalities"]["Calamba"]["series"][0]
    assert january["hot_days"] == pytest.approx(0.75 * 4 + 0.25 * 8)
    assert january["peak_heat_index_c"] == 42.0
    assert january["rain_mm"] == pytest.approx(31 * (0.75 * 1.0 + 0.25 * 2.0), abs=0.05)


def test_model_quality_reads_frozen_artifacts(tmp_path, cfg):
    arms = ["Thai simplified score", "AGAP model alone", "AGAP model + guideline floor"]
    columns = dict(auroc=[0.69, 0.71, 0.711], sensitivity=[0.585, 0.863, 0.865], referred_share=[0.33, 0.69, 0.693],
                   abnormal_rate_low=[0.077, 0.055, 0.055], abnormal_rate_medium=[0.178, 0.086, 0.086],
                   abnormal_rate_high=[0.44, 0.237, 0.237])
    pd.DataFrame(dict(arm=arms, **columns)).to_csv(tmp_path / "triage_benchmark.csv", index=False)
    pd.DataFrame(dict(target_prevalence=[0.08] * 3, cohort_prevalence=[0.07] * 3, arm=arms,
                      abnormal_rate_high=[0.3, 0.13, 0.15])).to_csv(tmp_path / "triage_prevalence_sensitivity.csv", index=False)
    (tmp_path / "triage_cutoffs.json").write_text(json.dumps(dict(
        t_medium=0.0711, t_high=0.1208, medium_or_high_sensitivity=0.852, high_abnormal_rate=0.229,
        config_fingerprint="abc123", git_commit="def456", seed=2026, n_train=10, n_validation=10, n_test=10,
        rules=dict(medium_min_sensitivity=0.85, high_min_prevalence_multiple=2.0))))
    result = model_quality(tmp_path, cfg, ROOT / "config/parameter_register.yaml")
    assert result["agap"] == dict(caught_pct=86.5, abnormal_rate_pct=[5.5, 8.6, 23.7], referred_pct=69.3, auroc=0.711)
    assert result["thai"]["auroc"] == 0.69
    assert result["run"]["config_fingerprint"] == "abc123"
    assert result["prevalence_sensitivity"] == [dict(target_prevalence_pct=8.0, cohort_prevalence_pct=7.0, high_rate_pct=15.0,
                                                     thai_high_rate_pct=30.0, target_rate_pct=14.0, meets_target=True)]
    assert {e["tag"] for e in result["effect_sizes"]} <= {"source-supported", "derived", "assumed"}
    assert result["floor"] is None


def test_heat_index_matches_nws_reference_values():
    # NWS heat index chart: 90 F at 70% RH -> 106 F; 96 F at 65% RH -> 121 F; below 80 F the simple form applies.
    assert heat_index_c((90 - 32) * 5 / 9, 70) * 9 / 5 + 32 == pytest.approx(105.9, abs=1)
    assert heat_index_c((96 - 32) * 5 / 9, 65) * 9 / 5 + 32 == pytest.approx(121, abs=1.5)
    assert heat_index_c(20.0, 50) < 21.0
