"""Baseline-free weather summaries; these never supply a model exposure score."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

import pandas as pd

from agap.climate.history import _daily_parts, _finish_daily, _sha256, read_archive_hourly

FILES = {"daily.parquet": "weather_daily.parquet", "windows.parquet": "weather_windows.parquet",
         "metadata.json": "weather_metadata.json"}


def weather_windows(daily, start, end):
    """Preceding 7/30 full local days, with independent completeness flags."""
    daily = daily.copy()
    daily["local_date"] = pd.to_datetime(daily.local_date)
    if daily.duplicated(["era5_cell", "local_date"]).any():
        raise ValueError("Duplicate weather cell/day")
    dates = pd.date_range(pd.Timestamp(start) - pd.Timedelta(days=30), pd.Timestamp(end) + pd.Timedelta(days=1))
    windows = []
    for cell, group in daily.groupby("era5_cell", sort=True):
        series = group.set_index("local_date").reindex(dates)
        temp = series.tmean_c.where(series.temperature_hours.eq(24))
        maximum = series.tmax_c.where(series.temperature_hours.eq(24))
        rain = series.precip_mm.where(series.precipitation_hours.eq(24))
        block = pd.DataFrame(dict(era5_cell=cell, cutoff=dates))
        for days in (7, 30):
            block[f"temperature_days_{days}d"] = temp.notna().rolling(days, min_periods=1).sum().shift(1).fillna(0).to_numpy(dtype=int)
            block[f"rainfall_days_{days}d"] = rain.notna().rolling(days, min_periods=1).sum().shift(1).fillna(0).to_numpy(dtype=int)
            block[f"tmean_{days}d_c"] = temp.rolling(days).mean().shift(1).to_numpy()
            block[f"tmax_{days}d_c"] = maximum.rolling(days).max().shift(1).to_numpy()
            block[f"rainfall_{days}d_mm"] = rain.rolling(days).sum().shift(1).to_numpy()
            block[f"complete_{days}d"] = block[f"temperature_days_{days}d"].eq(days) & block[f"rainfall_days_{days}d"].eq(days)
        windows.append(block.loc[block.cutoff.ge(pd.Timestamp(start))])
    if not windows:
        raise ValueError("No weather cells to summarize")
    return pd.concat(windows, ignore_index=True)


def prepare_available_weather(root, start="2021-01-01", end="2024-12-31"):
    root = Path(root)
    first, last = pd.Timestamp(start), pd.Timestamp(end)
    if first > last:
        raise ValueError("Weather start must precede end")
    warmup = first - pd.Timedelta(days=31)
    archives = []
    for path in sorted((root / "data/raw/era5_land/laguna_replay").glob("*.grib.zip")):
        match = re.fullmatch(r"era5_land_(\d{4})_(\d{2})-(\d{2})_temperature_precipitation.grib.zip", path.name)
        if not match:
            continue
        year, begin, finish = map(int, match.groups())
        if pd.Timestamp(year, begin, 1) <= last and pd.Timestamp(year, finish, 1) + pd.offsets.MonthEnd() >= warmup:
            archives.append(path)
    if not archives:
        raise FileNotFoundError("No downloaded archives intersect the requested weather period")
    parts, sources, previous, last_stamp = [], [], None, None
    for index, archive in enumerate(archives, 1):
        hourly = read_archive_hourly(archive)
        if last_stamp is not None and hourly.time_utc.min() <= last_stamp:
            raise ValueError("Weather archives overlap or are out of order")
        parts.append(_daily_parts(hourly, previous))
        previous = hourly.groupby("era5_cell", sort=False).tail(1).reset_index(drop=True)
        last_stamp = hourly.time_utc.max()
        sources.append(dict(path=str(archive.relative_to(root)), sha256=_sha256(archive),
                            first_utc=str(hourly.time_utc.min()), last_utc=str(last_stamp)))
        print(f"Weather {index}/{len(archives)}: {archive.name}", flush=True)
    daily = _finish_daily(pd.concat(parts, ignore_index=True))
    daily = daily.loc[daily.local_date.between(first - pd.Timedelta(days=30), last)].reset_index(drop=True)
    windows = weather_windows(daily, first, last)
    complete = windows.loc[windows.complete_30d]
    if complete.empty:
        raise ValueError("No complete 30-day weather windows; no preview is published")
    metadata = dict(source="Copernicus ERA5-Land hourly reanalysis", source_mode="cds_grib",
                    source_url="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land",
                    prepared_utc=datetime.now(timezone.utc).isoformat(), source_archives=sources,
                    processor_sha256=_sha256(Path(__file__)), daily_processor_sha256=_sha256(Path(__file__).with_name("history.py")),
                    local_timezone="Asia/Manila", requested_start=start, requested_end=end,
                    first_complete_cutoff=str(complete.cutoff.min().date()), last_complete_cutoff=str(complete.cutoff.max().date()),
                    source_cell_count=int(windows.era5_cell.nunique()), supported_cell_count=int(complete.era5_cell.nunique()),
                    daily_rows=len(daily), complete_daily_rows=int(daily.complete.sum()),
                    complete_7d_windows=int(windows.complete_7d.sum()), complete_30d_windows=int(windows.complete_30d.sum()),
                    window_rule="7 or 30 full Asia/Manila days before the context date; context day excluded; 24 valid hours required per variable/day",
                    rainfall_rule="Forecast-cycle differencing; interval ending at local midnight belongs to the preceding day; missing rainfall is never zero-filled",
                    model_use=False, baseline_available=False,
                    limitation="Historical weather context only. No seasonal anomaly, hot-dry score or climate-model prediction is calculated; resident dates/outcomes and screening scores are unchanged.")
    destination = root / "data/processed/weather/laguna"
    destination.mkdir(parents=True, exist_ok=True)
    for name, frame in (("daily.parquet", daily), ("windows.parquet", windows)):
        temporary = destination / (name + ".partial")
        frame.to_parquet(temporary, index=False)
        temporary.replace(destination / name)
    temporary = destination / "metadata.json.partial"
    temporary.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    temporary.replace(destination / "metadata.json")
    return metadata


def weather_inputs(cfg, root):
    settings = cfg.get("weather_preview", {})
    if not settings.get("enabled", False):
        return []
    folder = Path(root) / settings.get("processed_directory", "data/processed/weather/laguna")
    paths = [folder / name for name in FILES]
    if any(not path.is_file() for path in paths):
        raise FileNotFoundError("Historical weather preview is not prepared. Run make prepare-weather first.")
    return paths


def snapshot_weather(cfg, root, directory):
    for path in weather_inputs(cfg, root):
        target = Path(directory) / FILES[path.name]
        temporary = target.with_name(target.name + ".partial")
        shutil.copyfile(path, temporary)
        temporary.replace(target)


def load_weather_preview(directory):
    directory = Path(directory)
    if not all((directory / name).is_file() for name in FILES.values()):
        return None
    return dict(daily=pd.read_parquet(directory / "weather_daily.parquet"),
                windows=pd.read_parquet(directory / "weather_windows.parquet"),
                metadata=json.loads((directory / "weather_metadata.json").read_text()))
