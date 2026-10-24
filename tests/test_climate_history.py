"""Climate processing: rainfall deaccumulation, Manila local days and exposure windows."""
import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agap.climate.history import (
    SHORT_WINDOW_DAYS, WINDOW_DAYS, _daily_parts, _finish_daily, _grib_messages, build_exposure,
    deaccumulate_precipitation, hourly_to_daily, read_archive_hourly,
)
from agap.climate.integration import BASELINE_YEARS, PARTITION_DATES

ROOT = Path(__file__).resolve().parents[1]
CELL = "14.2,121.2"


def era5_hourly(start, hours, temperature=lambda t: 26.0, rain_mm=lambda t: 0.0):
    """Hourly records shaped like ERA5-Land: 00 UTC is step 24 of the previous day's cycle."""
    times = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    step = np.where(times.hour == 0, 24, times.hour)
    origin = times - pd.to_timedelta(step, unit="h")
    amounts = pd.Series([rain_mm(t) for t in times], dtype=float)
    accumulation = amounts.groupby(np.asarray(origin)).cumsum() / 1000
    return pd.DataFrame(dict(era5_cell=CELL, latitude=14.2, longitude=121.2, time_utc=times,
                             temperature_c=[temperature(t) for t in times],
                             precip_accum_m=accumulation.to_numpy(), forecast_step=step))


def local_day(t):
    """Local Manila day that a rainfall interval ending at t belongs to."""
    return (t - pd.Timedelta(nanoseconds=1)).tz_convert("Asia/Manila").day


def test_deaccumulation_recovers_hourly_amounts():
    frame = era5_hourly("2024-01-01 00:00", 49, rain_mm=lambda t: t.hour / 10)
    mm = deaccumulate_precipitation(frame)
    # The first 00 UTC record is step 24 of a cycle whose earlier steps are absent.
    assert np.isnan(mm.iloc[0])
    expected = frame.time_utc.dt.hour / 10
    assert np.allclose(mm.iloc[1:], expected.iloc[1:])


def test_deaccumulation_gap_stays_missing_not_dry():
    frame = era5_hourly("2024-01-01 00:00", 49, rain_mm=lambda t: 1.0).drop(index=5)
    mm = deaccumulate_precipitation(frame)
    assert np.isnan(mm.loc[6])  # cannot be split from the missing hour
    assert mm.loc[7] == pytest.approx(1.0)
    assert mm.loc[25] == pytest.approx(1.0)  # next cycle's step 1 is self-contained


def test_deaccumulation_rejects_material_decreases_only():
    frame = era5_hourly("2024-01-01 00:00", 24)
    frame.loc[3, "precip_accum_m"] = .0005 / 1000  # 0.0005 mm, then back to zero: rounding
    frame.loc[10, "precip_accum_m"] = 2 / 1000  # 2 mm, then back to zero: corrupt
    mm = deaccumulate_precipitation(frame)
    assert mm.loc[4] == 0
    assert np.isnan(mm.loc[11])


def test_deaccumulation_rejects_duplicate_hours():
    frame = era5_hourly("2024-01-01 00:00", 24)
    with pytest.raises(ValueError, match="Duplicate"):
        deaccumulate_precipitation(pd.concat([frame, frame.iloc[:1]], ignore_index=True))


def test_daily_values_follow_manila_local_days():
    # 16:00 UTC on 1 January is local midnight starting 2 January (UTC+8).
    frame = era5_hourly("2024-01-01 16:00", 49,
                        temperature=lambda t: 20 + t.tz_convert("Asia/Manila").day + t.tz_convert("Asia/Manila").hour / 100,
                        rain_mm=lambda t: {2: .5, 3: .25}.get(local_day(t), 9.0))
    daily = hourly_to_daily(frame).set_index("local_date")
    jan2, jan3 = daily.loc["2024-01-02"], daily.loc["2024-01-03"]
    assert jan2.complete and jan3.complete
    assert jan2.tmean_c == pytest.approx(22 + np.arange(24).mean() / 100)
    assert jan2.tmax_c == pytest.approx(22.23)
    # Rain ending at local midnight belongs to the day that just ended.
    assert jan2.precip_mm == pytest.approx(12.0)
    assert jan3.precip_mm == pytest.approx(6.0)
    assert not daily.loc["2024-01-01"].complete and np.isnan(daily.loc["2024-01-01"].precip_mm)
    assert not daily.loc["2024-01-04"].complete


def test_missing_hours_make_the_day_incomplete():
    frame = era5_hourly("2024-01-01 16:00", 49, rain_mm=lambda t: .5)
    frame.loc[5, "temperature_c"] = np.nan
    frame.loc[30, "precip_accum_m"] = np.nan
    daily = hourly_to_daily(frame).set_index("local_date")
    jan2, jan3 = daily.loc["2024-01-02"], daily.loc["2024-01-03"]
    assert jan2.temperature_hours == 23 and np.isnan(jan2.tmean_c) and not jan2.complete
    assert jan2.precip_mm == pytest.approx(12.0)
    # The missing accumulation also blocks the following hour; no partial daily total.
    assert jan3.precipitation_hours == 22 and np.isnan(jan3.precip_mm) and not jan3.complete


def test_archive_boundary_carries_the_previous_accumulation():
    frame = era5_hourly("2024-01-01 00:00", 96, rain_mm=lambda t: .2)
    whole = hourly_to_daily(frame)
    first, second = frame.iloc[:40], frame.iloc[40:]  # split mid-cycle
    previous = first.groupby("era5_cell").tail(1)
    joined = _finish_daily(pd.concat([_daily_parts(first), _daily_parts(second, previous)], ignore_index=True))
    pd.testing.assert_frame_equal(joined, whole, check_dtype=False)  # concat may change datetime resolution
    unjoined = _finish_daily(pd.concat([_daily_parts(first), _daily_parts(second)], ignore_index=True))
    assert unjoined.complete.sum() < whole.complete.sum()


def daily_climate(start="2000-12-01", end="2003-12-31", seed=0):
    """Complete daily rows: noisy baseline-like weather, then a hot, dry 2003."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq="D")
    hot_dry = dates.year == 2003
    return pd.DataFrame(dict(
        era5_cell=CELL, latitude=14.2, longitude=121.2, local_date=dates,
        tmean_c=np.where(hot_dry, 29.0, 26 + rng.normal(0, .5, len(dates))),
        tmax_c=np.where(hot_dry, 33.0, 30 + rng.normal(0, .5, len(dates))),
        precip_mm=np.where(hot_dry, 0.0, rng.gamma(2, 2.5, len(dates))),
        temperature_hours=24, precipitation_hours=24, complete=True))


def exposure_at(exposure, cutoff):
    return exposure.set_index("cutoff").loc[cutoff]


def test_window_uses_only_the_30_days_before_cutoff():
    daily = daily_climate()
    cutoff = pd.Timestamp("2003-03-15")
    daily.loc[daily.local_date.eq(cutoff), ["tmean_c", "tmax_c"]] = 100.0  # the cutoff day itself must not leak in
    exposure, _ = build_exposure(daily, 2001, 2002)
    row = exposure_at(exposure, cutoff)
    window = daily[daily.local_date.between(cutoff - pd.Timedelta(days=WINDOW_DAYS), cutoff - pd.Timedelta(days=1))]
    assert len(window) == WINDOW_DAYS
    assert row.preceding_tmean_c == pytest.approx(window.tmean_c.mean())
    assert row.preceding_mean_tmax_c == pytest.approx(window.tmax_c.mean())
    assert row.preceding_precip_mm == pytest.approx(window.precip_mm.sum())
    assert row.window_start == window.local_date.min() and row.window_end == window.local_date.max()


def test_seven_day_window_uses_only_the_7_days_before_cutoff():
    daily = daily_climate()
    cutoff = pd.Timestamp("2002-08-15")
    daily.loc[daily.local_date.eq(cutoff), ["tmean_c", "tmax_c", "precip_mm"]] = 100.0
    row = exposure_at(build_exposure(daily, 2001, 2002)[0], cutoff)
    window = daily[daily.local_date.between(cutoff - pd.Timedelta(days=SHORT_WINDOW_DAYS), cutoff - pd.Timedelta(days=1))]
    assert len(window) == SHORT_WINDOW_DAYS and row.complete_7d
    assert row.preceding_tmean_7d_c == pytest.approx(window.tmean_c.mean())
    assert row.preceding_tmax_7d_c == pytest.approx(window.tmax_c.max())
    assert row.preceding_precip_7d_mm == pytest.approx(window.precip_mm.sum())


def test_seven_day_completeness_is_separate_from_30_day():
    daily = daily_climate()
    daily.loc[daily.local_date.eq("2003-03-12"), "precipitation_hours"] = 23  # inside both windows
    daily.loc[daily.local_date.eq("2003-04-01"), "temperature_hours"] = 23  # inside the 30-day window only
    exposure, _ = build_exposure(daily, 2001, 2002)
    both = exposure_at(exposure, pd.Timestamp("2003-03-15"))
    assert both.precipitation_days_7d == SHORT_WINDOW_DAYS - 1
    assert not both.complete_7d and np.isnan(both.preceding_precip_7d_mm)
    longer_only = exposure_at(exposure, pd.Timestamp("2003-04-20"))
    assert longer_only.complete_7d and np.isfinite(longer_only.preceding_tmean_7d_c)
    assert not longer_only.complete and np.isnan(longer_only.hot_dry_score)


def test_hot_dry_period_scores_above_its_baseline():
    exposure, baseline = build_exposure(daily_climate(), 2001, 2002)
    row = exposure_at(exposure, pd.Timestamp("2003-03-15"))
    reference = baseline.set_index("cutoff_month").loc[3]
    assert row.complete and row.status == "complete"
    assert row.temperature_anomaly_z == pytest.approx((row.preceding_mean_tmax_c - reference.temperature_mean_c) / reference.temperature_sd_c)
    assert row.rainfall_deficit_z == pytest.approx((reference.rainfall_mean_mm - row.preceding_precip_mm) / reference.rainfall_sd_mm)
    assert row.temperature_anomaly_z > 0 and row.rainfall_deficit_z > 0 and row.hot_dry_score > 0


def test_missing_day_makes_the_window_incomplete_not_zero():
    daily = daily_climate()
    daily.loc[daily.local_date.eq("2003-03-10"), "temperature_hours"] = 23
    exposure, _ = build_exposure(daily, 2001, 2002)
    affected = exposure_at(exposure, pd.Timestamp("2003-03-15"))
    assert affected.temperature_days == WINDOW_DAYS - 1
    assert not affected.complete and affected.status == "incomplete_30_day_window"
    assert np.isnan(affected.hot_dry_score)
    assert exposure_at(exposure, pd.Timestamp("2003-04-15")).complete


def test_sparse_baseline_month_is_not_used():
    daily = daily_climate()
    daily.loc[daily.local_date.between("2001-07-01", "2001-07-05"), "temperature_hours"] = 23
    exposure, baseline = build_exposure(daily, 2001, 2002)
    assert not baseline.set_index("cutoff_month").loc[7].baseline_complete
    july = exposure_at(exposure, pd.Timestamp("2003-07-20"))
    assert not july.complete and july.status == "incomplete_baseline" and np.isnan(july.hot_dry_score)


def test_baseline_must_be_complete_with_warmup():
    daily = daily_climate()
    with pytest.raises(ValueError, match="baseline"):
        build_exposure(daily[~daily.local_date.dt.to_period("M").eq("2002-06")], 2001, 2002)
    with pytest.raises(ValueError, match="warmup"):
        build_exposure(daily[daily.local_date >= "2001-01-01"], 2001, 2002)


def test_declared_periods_are_ordered_and_separate():
    assert inspect.signature(build_exposure).parameters["baseline_start"].default == BASELINE_YEARS[0]
    assert inspect.signature(build_exposure).parameters["baseline_end"].default == BASELINE_YEARS[1]
    spans = [tuple(map(pd.Timestamp, PARTITION_DATES[name])) for name in ("train", "validation", "deployment")]
    assert all(start <= end for start, end in spans)
    assert all(earlier[1] < later[0] for earlier, later in zip(spans, spans[1:]))
    assert pd.Timestamp(BASELINE_YEARS[1], 12, 31) < spans[0][0]


def test_grib_framing_detects_truncation_and_unknown_editions():
    grib1 = b"GRIB" + (16).to_bytes(3, "big") + b"\x01" + b"\x00" * 4 + b"7777"
    grib2 = b"GRIB" + b"\x00\x00\x00\x02" + (20).to_bytes(8, "big") + b"7777"
    assert list(_grib_messages(grib1 + grib2)) == [grib1, grib2]
    with pytest.raises(ValueError, match="Truncated"):
        list(_grib_messages(grib1 + grib1[:-1]))
    with pytest.raises(ValueError, match="edition"):
        list(_grib_messages(grib1[:7] + b"\x03" + grib1[8:]))


ARCHIVE = ROOT / "data/raw/era5_land/laguna_replay/era5_land_2024_01-06_temperature_precipitation.grib.zip"


@pytest.mark.skipif(not ARCHIVE.is_file(), reason="collected ERA5-Land archive not present")
def test_collected_archive_hourly_rain_sums_to_daily_accumulation():
    hourly = read_archive_hourly(ARCHIVE)
    assert set(hourly.forecast_step.unique()) == set(range(1, 25))
    cell = hourly.dropna(subset=["precip_accum_m"]).era5_cell.iloc[0]
    one = hourly[hourly.era5_cell.eq(cell)].sort_values("time_utc").reset_index(drop=True)
    one["mm"] = deaccumulate_precipitation(one)
    assert (one.mm.dropna() >= 0).all()
    one["origin"] = one.time_utc - pd.to_timedelta(one.forecast_step, unit="h")
    cycles = one.groupby("origin").agg(hours=("mm", "count"), total=("mm", "sum"), step24=("precip_accum_m", "last"))
    cycles = cycles[cycles.hours == 24]
    assert len(cycles) > 150
    assert np.allclose(cycles.total, cycles.step24 * 1000, atol=1e-3)
