"""Engine 2 surveillance: monthly panel, observed/hidden summaries and forecast comparison."""
import numpy as np
import pandas as pd
import pytest

from agap.config import ROOT, load_config
from agap.data.geography import make_geography
from agap.surveillance import (
    PROVINCE, TARGET, forecast_comparison, forecast_gains, monthly_summary, simulate_panel, surveillance_months,
)


@pytest.fixture(scope="module")
def panel():
    cfg = load_config()
    cfg["surveillance"]["monthly_sample"] = 60
    cells, demographics, facilities, _ = make_geography(cfg, ROOT)
    return simulate_panel(cfg, cells, demographics, facilities)


def test_panel_covers_every_month_with_dates_inside_that_month(panel):
    months, _ = surveillance_months()
    assert list(panel.month.drop_duplicates()) == list(months.start_time)
    assert (panel.cutoff.dt.to_period("M").dt.start_time == panel.month).all()
    assert panel.groupby("month").size().eq(60).all()
    assert panel.resident_id.is_unique


def test_monthly_counts_reconcile(panel):
    summary = monthly_summary(panel)
    assert (summary.tested <= summary.sampled_adults).all()
    assert (summary.observed_abnormal <= summary.tested).all()
    assert (summary.observed_abnormal <= summary.hidden_abnormal).all()
    assert not (panel.round0_completed & ~panel.round0_invited).any()  # OBS-05: testing requires invitation
    assert (panel.round0_completed & ~panel.reported).any()  # outreach reaches nonreporters
    province = summary[summary.municipality.eq(PROVINCE)].set_index("month")
    local = summary[~summary.municipality.eq(PROVINCE)].groupby("month")
    for column in ("sampled_adults", "tested", "observed_abnormal", "hidden_abnormal"):
        pd.testing.assert_series_equal(province[column], local[column].sum(), check_names=False)
    rates = province.dropna(subset=[TARGET])
    assert np.allclose(rates[TARGET], 100 * rates.observed_abnormal / rates.tested)


def monthly_series(values, start="2021-01"):
    months = pd.period_range(start, periods=len(values), freq="M").start_time
    rng = np.random.default_rng(1)
    return pd.DataFrame({"month": months, TARGET: values, "mean_hot_dry_score": rng.normal(size=len(values))})


def test_seasonal_naive_is_exact_for_a_repeating_year():
    series = monthly_series(np.tile(10 + 3 * np.sin(np.arange(12) / 12 * 2 * np.pi), 5))
    _, metrics = forecast_comparison(series)
    naive = metrics[metrics.method.eq("seasonal_naive")]
    assert naive.mae.max() == pytest.approx(0) and naive.holdout_months.eq(12).all()


def test_forecasts_never_use_months_after_their_origin():
    series = monthly_series(np.random.default_rng(2).normal(12, 2, 60))
    forecasts, _ = forecast_comparison(series)
    origin = forecasts.origin_month.sort_values().iloc[len(forecasts) // 2]
    changed = series.copy()
    future = changed.month > origin
    changed.loc[future, TARGET] = 999.0
    changed.loc[future, "mean_hot_dry_score"] = -999.0
    again, _ = forecast_comparison(changed)
    keys = ["target_month", "horizon_months"]
    before = forecasts[forecasts.origin_month.eq(origin)].set_index(keys)
    after = again.set_index(keys).loc[before.index]
    for method in ("seasonal_naive", "candidate_no_climate", "candidate"):
        pd.testing.assert_series_equal(before[method], after[method])


def test_candidate_learns_a_lagged_climate_signal():
    rng = np.random.default_rng(3)
    climate = rng.normal(size=72)
    target = 10 + np.tile(np.sin(np.arange(12) / 2), 6) + np.r_[0, 2 * climate[:-1]] + rng.normal(0, .05, 72)
    series = pd.DataFrame({"month": pd.period_range("2021-01", periods=72, freq="M").start_time,
                           TARGET: target, "mean_hot_dry_score": climate})
    _, metrics = forecast_comparison(series, horizons=(1,))
    mae = metrics.set_index("method").mae
    assert mae["candidate"] < mae["seasonal_naive"] / 2
    assert forecast_gains(metrics).climate_gain.iloc[0] > 0


def test_unrelated_climate_adds_no_gain_but_regression_still_beats_naive():
    """Independent monthly noise: regression wins by pulling to the mean, not through climate."""
    gains = []
    for seed in range(20):
        rng = np.random.default_rng(seed)
        series = pd.DataFrame({"month": pd.period_range("2021-01", periods=69, freq="M").start_time,
                               TARGET: rng.normal(13, 2.5, 69), "mean_hot_dry_score": rng.normal(size=69)})
        gains.append(forecast_gains(forecast_comparison(series, horizons=(1,))[1]).iloc[0])
    gains = pd.DataFrame(gains)
    assert abs(gains.climate_gain.mean()) < 3 * gains.climate_gain.std() / np.sqrt(len(gains))
    assert gains.regression_gain.mean() > 0.3


def test_hidden_columns_and_long_horizons_are_rejected():
    series = monthly_series(np.ones(48))
    with pytest.raises(ValueError, match="Hidden"):
        forecast_comparison(series.assign(hidden_prevalence_per_100=1.0))
    with pytest.raises(ValueError, match="Horizons"):
        forecast_comparison(series, horizons=(13,))
