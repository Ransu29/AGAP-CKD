"""ERA5-Land local-day weather and strictly preceding screening exposures.

Rainfall is deaccumulated within each forecast cycle before conversion to local
days. Reference means/scales are learned only from declared baseline cutoffs.
The resulting hot–dry score is an assumed exposure index, not a heat index or
an epidemiologically validated risk measure.
"""
from __future__ import annotations

from calendar import monthrange
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

from agap.climate.integration import BASELINE_YEARS, PARTITION_DATES

ZONE = "Asia/Manila"
WINDOW_DAYS = 30
SHORT_WINDOW_DAYS = 7  # descriptive summary (SRS E2-02); the hot–dry score uses the 30-day window
BASELINE_COVERAGE = .9
RAIN_TOLERANCE_MM = .001  # tolerate GRIB rounding only; reject material decreases


def _utc(values):
    return pd.to_datetime(values, utc=True)


def clip_rain_noise(mm):
    """Rounding noise down to -RAIN_TOLERANCE_MM becomes 0; anything more negative is left missing.

    Applied to every source (CDS de-accumulation and ARCO hourly values) so they follow one rule.
    """
    return mm.where(mm >= -RAIN_TOLERANCE_MM).clip(lower=0)


def deaccumulate_precipitation(hourly: pd.DataFrame) -> pd.Series:
    """Return hourly mm; a gap must never become an invented dry hour.

    Required columns are era5_cell, time_utc, precip_accum_m, forecast_step.
    ERA5-Land steps 1..24 accumulate from the forecast's 00 UTC origin.
    """
    frame = hourly.copy()
    if frame.duplicated(["era5_cell", "time_utc"]).any():
        raise ValueError("Duplicate cell/hour records cannot be deaccumulated")
    frame["time_utc"] = _utc(frame.time_utc)
    frame = frame.sort_values(["era5_cell", "time_utc"])
    step = pd.to_numeric(frame.forecast_step, errors="coerce")
    accumulation = pd.to_numeric(frame.precip_accum_m, errors="coerce") * 1000
    valid_step = step.between(1, 24) & (step == np.floor(step))
    origin = frame.time_utc - pd.to_timedelta(step, unit="h")
    previous_time = frame.groupby("era5_cell", sort=False).time_utc.shift()
    previous_accumulation = accumulation.groupby(frame.era5_cell).shift()
    previous_origin = origin.groupby(frame.era5_cell).shift()
    previous_step = step.groupby(frame.era5_cell).shift()
    consecutive = ((frame.time_utc - previous_time) == pd.Timedelta(hours=1))
    same_cycle = origin.eq(previous_origin) & step.eq(previous_step + 1)
    amount = (accumulation - previous_accumulation).where(consecutive & same_cycle)
    amount = amount.where(step != 1, accumulation)
    predecessor_valid = previous_accumulation.ge(-RAIN_TOLERANCE_MM)
    amount = amount.where(step.eq(1) | predecessor_valid)
    amount = amount.where(valid_step & accumulation.ge(-RAIN_TOLERANCE_MM))
    amount = clip_rain_noise(amount)
    return amount.reindex(hourly.index).rename("precip_mm")


def _daily_parts(hourly: pd.DataFrame, previous: pd.DataFrame | None = None) -> pd.DataFrame:
    current = hourly.copy()
    current["time_utc"] = _utc(current.time_utc)
    if current.duplicated(["era5_cell", "time_utc"]).any():
        raise ValueError("Duplicate cell/hour records would corrupt daily completeness")
    current["_current"] = True
    if previous is not None and len(previous):
        prior = previous.copy()
        prior["_current"] = False
        current = pd.concat([prior, current], ignore_index=True)
    if "precip_mm" not in current:  # ARCO rain is already hourly; CDS GRIB rain is accumulated
        current["precip_mm"] = deaccumulate_precipitation(current)
    current = current.loc[current._current].copy()
    local = current.time_utc.dt.tz_convert(ZONE)
    current["local_date"] = local.dt.tz_localize(None).dt.normalize()
    keys = ["era5_cell", "latitude", "longitude", "local_date"]
    temperatures = current.groupby(keys, as_index=False).agg(
        tmax_c=("temperature_c", "max"), temperature_sum=("temperature_c", "sum"),
        temperature_hours=("temperature_c", "count"))
    # Rain describes an interval ending at validity time: an interval ending
    # exactly at local midnight belongs to the day that has just ended.
    current["local_date"] = (local - pd.Timedelta(nanoseconds=1)).dt.tz_localize(None).dt.normalize()
    rain = current.groupby(keys, as_index=False).agg(
        precip_sum=("precip_mm", "sum"), precipitation_hours=("precip_mm", "count"))
    return temperatures.merge(rain, on=keys, how="outer")


def _finish_daily(parts: pd.DataFrame) -> pd.DataFrame:
    keys = ["era5_cell", "latitude", "longitude", "local_date"]
    daily = parts.groupby(keys, as_index=False).agg(
        tmax_c=("tmax_c", "max"), temperature_sum=("temperature_sum", "sum"),
        temperature_hours=("temperature_hours", "sum"), precip_mm=("precip_sum", "sum"),
        precipitation_hours=("precipitation_hours", "sum"))
    for column in ("temperature_hours", "precipitation_hours"):
        daily[column] = daily[column].astype(int)
        if daily[column].gt(24).any():
            raise ValueError("More than 24 observations in a local day: overlapping climate sources")
    daily["tmean_c"] = daily.temperature_sum / daily.temperature_hours.replace(0, np.nan)
    daily.loc[daily.temperature_hours != 24, ["tmax_c", "tmean_c"]] = np.nan
    daily.loc[daily.precipitation_hours != 24, "precip_mm"] = np.nan
    daily["complete"] = (daily.temperature_hours == 24) & (daily.precipitation_hours == 24)
    return daily.drop(columns="temperature_sum").sort_values(["era5_cell", "local_date"]).reset_index(drop=True)


def hourly_to_daily(hourly: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hourly temperature and accumulated rain, preserving missing days."""
    return _finish_daily(_daily_parts(hourly))


def _baseline_guard(daily: pd.DataFrame, baseline_start: int, baseline_end: int):
    if baseline_start > baseline_end:
        raise ValueError("Baseline start must be before baseline end")
    required = pd.period_range(f"{baseline_start}-01", f"{baseline_end}-12", freq="M")
    present = pd.DatetimeIndex(daily.local_date).to_period("M").unique()
    missing = required.difference(present)
    if len(missing):
        shown = ", ".join(str(item) for item in missing[:6])
        raise ValueError(f"Incomplete {baseline_start}–{baseline_end} baseline: missing {len(missing)} months ({shown}); no fallback baseline is allowed")
    warmup = pd.Timestamp(baseline_start, 1, 1) - pd.Timedelta(days=WINDOW_DAYS)
    if pd.Timestamp(daily.local_date.min()) > warmup:
        raise ValueError(f"Baseline requires preceding 30-day warmup from {warmup.date()}")


def build_exposure(daily: pd.DataFrame, baseline_start: int = BASELINE_YEARS[0],
                   baseline_end: int = BASELINE_YEARS[1]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return cutoff exposures and baseline statistics, without future-day inputs.

    Every year of the baseline must contribute at least 90% complete windows to
    a cell/calendar-month reference. An unavailable reference remains missing.
    A valid zero-variance reference uses a unit scale and is explicitly flagged;
    it does not claim a standard-normal anomaly.
    """
    daily = daily.copy()
    daily["local_date"] = pd.to_datetime(daily.local_date).dt.normalize()
    if daily.duplicated(["era5_cell", "local_date"]).any():
        raise ValueError("Duplicate climate cell/day")
    _baseline_guard(daily, baseline_start, baseline_end)
    dates = pd.date_range(daily.local_date.min(), daily.local_date.max() + pd.Timedelta(days=1), freq="D")
    windows = []
    for cell, subset in daily.groupby("era5_cell", sort=True):
        values = subset.set_index("local_date").reindex(dates)
        temp = values.tmean_c.where(values.temperature_hours.eq(24))
        maximum = values.tmax_c.where(values.temperature_hours.eq(24))
        rainfall = values.precip_mm.where(values.precipitation_hours.eq(24))
        block = pd.DataFrame({
            "era5_cell": cell, "cutoff": dates,
            "temperature_days": temp.notna().rolling(WINDOW_DAYS, min_periods=1).sum().shift(1).fillna(0).astype(int).to_numpy(),
            "precipitation_days": rainfall.notna().rolling(WINDOW_DAYS, min_periods=1).sum().shift(1).fillna(0).astype(int).to_numpy(),
            "preceding_tmean_c": temp.rolling(WINDOW_DAYS).mean().shift(1).to_numpy(),
            "preceding_mean_tmax_c": maximum.rolling(WINDOW_DAYS).mean().shift(1).to_numpy(),
            "preceding_tmax_c": maximum.rolling(WINDOW_DAYS).max().shift(1).to_numpy(),
            "preceding_precip_mm": rainfall.rolling(WINDOW_DAYS).sum().shift(1).to_numpy(),
            "temperature_days_7d": temp.notna().rolling(SHORT_WINDOW_DAYS, min_periods=1).sum().shift(1).fillna(0).astype(int).to_numpy(),
            "precipitation_days_7d": rainfall.notna().rolling(SHORT_WINDOW_DAYS, min_periods=1).sum().shift(1).fillna(0).astype(int).to_numpy(),
            "preceding_tmean_7d_c": temp.rolling(SHORT_WINDOW_DAYS).mean().shift(1).to_numpy(),
            "preceding_tmax_7d_c": maximum.rolling(SHORT_WINDOW_DAYS).max().shift(1).to_numpy(),
            "preceding_precip_7d_mm": rainfall.rolling(SHORT_WINDOW_DAYS).sum().shift(1).to_numpy(),
        })
        windows.append(block)
    exposure = pd.concat(windows, ignore_index=True)
    exposure["complete_7d"] = exposure.temperature_days_7d.eq(SHORT_WINDOW_DAYS) & exposure.precipitation_days_7d.eq(SHORT_WINDOW_DAYS)
    exposure["cutoff_month"] = exposure.cutoff.dt.month
    exposure["window_start"] = exposure.cutoff - pd.Timedelta(days=WINDOW_DAYS)
    exposure["window_end"] = exposure.cutoff - pd.Timedelta(days=1)
    reference = exposure.loc[exposure.cutoff.dt.year.between(baseline_start, baseline_end)].copy()
    reference["baseline_year"] = reference.cutoff.dt.year
    reference["valid_window"] = reference.temperature_days.eq(WINDOW_DAYS) & reference.precipitation_days.eq(WINDOW_DAYS)
    references = []
    n_years = baseline_end - baseline_start + 1
    for (cell, month), values in reference.groupby(["era5_cell", "cutoff_month"], sort=True):
        counts = values.groupby("baseline_year").valid_window.sum()
        complete_years = sum(counts.get(year, 0) >= np.ceil(BASELINE_COVERAGE * monthrange(year, month)[1])
                             for year in range(baseline_start, baseline_end + 1))
        valid = values.loc[values.valid_window]
        mean_temp = valid.preceding_mean_tmax_c.mean()
        sd_temp = valid.preceding_mean_tmax_c.std(ddof=1)
        mean_rain, sd_rain = valid.preceding_precip_mm.mean(), valid.preceding_precip_mm.std(ddof=1)
        baseline_complete = complete_years == n_years and len(valid) >= 2
        references.append(dict(
            era5_cell=cell, cutoff_month=month, baseline_start=baseline_start, baseline_end=baseline_end,
            temperature_mean_c=mean_temp, temperature_sd_c=sd_temp,
            rainfall_mean_mm=mean_rain, rainfall_sd_mm=sd_rain,
            baseline_window_count=len(valid), baseline_years_complete=complete_years,
            baseline_complete=baseline_complete,
            temperature_scale_constant=bool(pd.notna(sd_temp) and sd_temp < 1e-8),
            rainfall_scale_constant=bool(pd.notna(sd_rain) and sd_rain < 1e-8)))
    baseline = pd.DataFrame(references)
    exposure = exposure.merge(baseline, on=["era5_cell", "cutoff_month"], how="left", validate="many_to_one")
    temp_scale = exposure.temperature_sd_c.mask(exposure.temperature_scale_constant, 1.)
    rain_scale = exposure.rainfall_sd_mm.mask(exposure.rainfall_scale_constant, 1.)
    window_complete = exposure.temperature_days.eq(WINDOW_DAYS) & exposure.precipitation_days.eq(WINDOW_DAYS)
    exposure["complete"] = window_complete & exposure.baseline_complete.fillna(False)
    exposure["temperature_anomaly_z"] = ((exposure.preceding_mean_tmax_c - exposure.temperature_mean_c) / temp_scale).where(exposure.complete)
    exposure["rainfall_deficit_z"] = ((exposure.rainfall_mean_mm - exposure.preceding_precip_mm) / rain_scale).where(exposure.complete)
    exposure["hot_dry_score"] = (exposure.temperature_anomaly_z + exposure.rainfall_deficit_z) / 2
    exposure["status"] = np.select(
        [~window_complete, ~exposure.baseline_complete.fillna(False),
         exposure.temperature_scale_constant | exposure.rainfall_scale_constant],
        ["incomplete_30_day_window", "incomplete_baseline", "complete_constant_reference_scale"],
        default="complete")
    return exposure, baseline


def _grib_messages(data: bytes):
    """Read both GRIB editions; fail on truncation instead of losing hours."""
    offset = 0
    while offset < len(data):
        if data[offset:offset + 4] != b"GRIB":
            raise ValueError(f"Expected GRIB message at byte {offset}")
        edition = data[offset + 7]
        if edition == 1:
            size = int.from_bytes(data[offset + 4:offset + 7], "big")
        elif edition == 2:
            size = int.from_bytes(data[offset + 8:offset + 16], "big")
        else:
            raise ValueError(f"Unsupported GRIB edition {edition}")
        message = data[offset:offset + size]
        if size < 12 or len(message) != size or message[-4:] != b"7777":
            raise ValueError("Truncated or malformed GRIB message")
        yield message
        offset += size


def read_archive_hourly(archive: Path) -> pd.DataFrame:
    """Decode all 2t/tp messages, including masked coast and border grid cells."""
    import eccodes

    chunks = {"2t": [], "tp": []}
    with ZipFile(archive) as zipped:
        members = sorted(name for name in zipped.namelist() if name.lower().endswith((".grib", ".grb", ".grib2")))
        if not members:
            raise ValueError(f"No GRIB member in {archive.name}")
        for member in members:
            for message in _grib_messages(zipped.read(member)):
                handle = eccodes.codes_new_from_message(message)
                try:
                    variable = eccodes.codes_get(handle, "shortName")
                    if variable not in chunks:
                        continue
                    unit = eccodes.codes_get(handle, "units")
                    if unit != ("K" if variable == "2t" else "m"):
                        raise ValueError(f"Unexpected {variable} unit: {unit}")
                    stamp = pd.to_datetime(f"{eccodes.codes_get(handle, 'validityDate'):08d}{eccodes.codes_get(handle, 'validityTime'):04d}", format="%Y%m%d%H%M", utc=True)
                    latitude = eccodes.codes_get_array(handle, "latitudes")
                    longitude = eccodes.codes_get_array(handle, "longitudes")
                    values = eccodes.codes_get_values(handle).astype(float)
                    missing = eccodes.codes_get(handle, "missingValue")
                    values[(values == missing) | ~np.isfinite(values)] = np.nan
                    block = pd.DataFrame(dict(
                        time_utc=stamp, latitude=latitude, longitude=longitude,
                        era5_cell=[f"{lat:.1f},{lon:.1f}" for lat, lon in zip(latitude, longitude)]))
                    if variable == "2t":
                        block["temperature_c"] = values - 273.15
                    else:
                        if eccodes.codes_get(handle, "stepType") != "accum":
                            raise ValueError("Rainfall requires accumulated forecast steps")
                        if int(eccodes.codes_get(handle, "stepUnits")) != 1:
                            raise ValueError("Rainfall forecast steps must be measured in hours")
                        block["precip_accum_m"] = values
                        block["forecast_step"] = int(eccodes.codes_get(handle, "endStep"))
                    chunks[variable].append(block)
                finally:
                    eccodes.codes_release(handle)
    if any(not chunks[key] for key in chunks):
        raise ValueError(f"Archive {archive.name} must contain both 2t and tp")
    temperature, rain = (pd.concat(chunks[key], ignore_index=True) for key in ("2t", "tp"))
    keys = ["era5_cell", "time_utc", "latitude", "longitude"]
    return temperature.merge(rain, on=keys, how="outer", validate="one_to_one").sort_values(["time_utc", "era5_cell"]).reset_index(drop=True)


ARCO_DIRECTORY = "data/raw/era5_land/arco"
SOURCES = ("cds_grib", "arco")


def arco_files(root: Path):
    """ARCO yearly extracts listed in era5_land_arco.json, each checked against its recorded SHA-256."""
    folder = Path(root) / ARCO_DIRECTORY
    record_path = folder / "era5_land_arco.json"
    if not record_path.exists():
        raise FileNotFoundError("No ARCO extract found; run make collect-climate-arco first")
    record = json.loads(record_path.read_text())
    files = []
    for name, expected in sorted(record["files"].items()):
        path = folder / name
        if not path.exists() or _sha256(path) != expected["sha256"]:
            raise ValueError(f"ARCO extract {name} is missing or does not match its recorded checksum")
        files.append(path)
    return files, record


def read_arco_hourly(path: Path) -> pd.DataFrame:
    """One ARCO yearly extract as hourly rows with °C temperature and clipped hourly rain in mm."""
    frame = pd.read_parquet(path)
    return pd.DataFrame(dict(
        time_utc=pd.to_datetime(frame.time_utc).dt.tz_localize("UTC"), era5_cell=frame.era5_cell,
        latitude=frame.latitude, longitude=frame.longitude,
        temperature_c=frame.t2m_k.astype(float) - 273.15,
        precip_mm=clip_rain_noise(frame.tp_m_hourly.astype(float) * 1000)))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_history(root: str | Path, baseline_start: int = BASELINE_YEARS[0],
                    baseline_end: int = BASELINE_YEARS[1], source: str = "cds_grib") -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Build audited daily and preceding-window artifacts from downloaded archives or the ARCO extract."""
    root = Path(root)
    if source not in SOURCES:
        raise ValueError(f"Climate source must be one of {SOURCES}")
    if source == "arco":
        archives, arco_record = arco_files(root)
        read = read_arco_hourly
    else:
        archives, arco_record = sorted((root / "data/raw/era5_land/laguna_replay").glob("*.grib.zip")), None
        read = read_archive_hourly
    if not archives:
        raise FileNotFoundError("No Laguna replay GRIB archives found; collect the declared baseline and replay first")
    parts, sources, previous = [], [], None
    last_timestamp = None
    for index, archive in enumerate(archives, 1):
        hourly = read(archive)
        if last_timestamp is not None and hourly.time_utc.min() <= last_timestamp:
            raise ValueError("Climate archives overlap or are not named in chronological order")
        parts.append(_daily_parts(hourly, previous))
        previous = hourly.groupby("era5_cell", sort=False).tail(1).reset_index(drop=True)
        last_timestamp = hourly.time_utc.max()
        sources.append(dict(path=str(archive.relative_to(root)), sha256=_sha256(archive),
                            bytes=archive.stat().st_size, first_utc=str(hourly.time_utc.min()), last_utc=str(last_timestamp)))
        print(f"Climate {index}/{len(archives)}: {archive.name}", flush=True)
    daily = _finish_daily(pd.concat(parts, ignore_index=True))
    exposure, baseline = build_exposure(daily, baseline_start, baseline_end)
    replay = exposure.loc[exposure.cutoff.between(PARTITION_DATES["train"][0], PARTITION_DATES["deployment"][1])]
    metadata = dict(
        source="Copernicus ERA5-Land hourly reanalysis" + (" via the ECMWF ARCO Zarr data lake" if source == "arco" else ""),
        source_mode=source, source_url="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land",
        arco_extract=dict(stores=arco_record["stores"], retrieved_at_utc=arco_record["retrieved_at_utc"]) if arco_record else None,
        requested_bbox_north_west_south_east=[14.7, 120.9, 13.8, 121.7],
        local_timezone=ZONE, temperature_unit="degrees Celsius", precipitation_unit="millimetres",
        source_archives=sources, processor_sha256=_sha256(Path(__file__)),
        first_local_day=str(daily.local_date.min().date()), last_local_day=str(daily.local_date.max().date()),
        grid_cells=int(daily.era5_cell.nunique()), daily_rows=len(daily), complete_daily_rows=int(daily.complete.sum()),
        baseline_start=baseline_start, baseline_end=baseline_end, window_days=WINDOW_DAYS,
        short_window_days=SHORT_WINDOW_DAYS,
        short_window_rule="7 full local days preceding cutoff, cutoff day excluded; descriptive summary with its own completeness flag (complete_7d), not used by the hot–dry score",
        baseline_definition="Means and sample standard deviations of the 30-day mean of daily maximum temperature and 30-day rainfall total, grouped by grid cell and cutoff calendar month, among complete cutoff windows in the declared baseline years; at least 90% valid windows in every baseline year/month",
        baseline_minimum_year_month_coverage=BASELINE_COVERAGE,
        rainfall_method=("ARCO hourly precipitation, de-accumulated by ECMWF (verified equal to our CDS GRIB de-accumulation within GRIB packing precision). " if source == "arco" else
                         "ERA5-Land forecast step1 is the first hourly amount; steps2..24 subtract the preceding accumulation within the same forecast cycle. Missing predecessor remains missing. ")
                        + "Rounding noise down to -0.001 mm becomes 0; more negative values remain missing. Interval ending at local midnight belongs to preceding day.",
        daily_completeness="24 valid distinct local-hour observations required separately for temperature and precipitation; incomplete variables remain missing",
        cutoff_rule="Only the 30 full local days preceding cutoff are used; cutoff day is excluded",
        index_formula="((preceding_mean_tmax_c - baseline_mean_30day_mean_daily_tmax_c) / baseline_sd_30day_mean_daily_tmax_c + (baseline_rainfall_mean - preceding_precip_mm) / baseline_rainfall_sd) / 2",
        constant_reference_rule="Reference SD below1e-8 uses unit scale and is flagged. This is a descriptive index, not a standard-normal score.",
        replay_complete_rows=int(replay.complete.sum()), replay_rows=len(replay),
        cell_readiness=[dict(era5_cell=cell, complete_replay_windows=int(group.complete.sum()), total_replay_windows=len(group))
                        for cell, group in replay.groupby("era5_cell")],
        limitations=["Reanalysis represents gridded conditions, not individual exposure.",
                     "Rainfall deficit and temperature anomaly are descriptive; their health effects remain assumed in synthetic outcomes.",
                     "Missing/coastal cells are retained and cannot produce a climate score without a complete reference and window.",
                     "This hot–dry score is not PAGASA's humidity-based heat index."])
    destination = root / "data/processed/climate/laguna"
    destination.mkdir(parents=True, exist_ok=True)
    for name, frame in (("daily", daily), ("exposure", exposure), ("baseline", baseline)):
        temporary = destination / f"{name}.parquet.tmp"
        frame.to_parquet(temporary, index=False)
        temporary.replace(destination / f"{name}.parquet")
    temporary = destination / "metadata.json.tmp"
    temporary.write_text(json.dumps(metadata, indent=2) + "\n")
    temporary.replace(destination / "metadata.json")
    return daily, exposure, metadata
