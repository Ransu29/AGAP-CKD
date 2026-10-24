"""Download hourly ERA5-Land temperature and humidity from Open-Meteo and derive the daily maximum heat index.

    python scripts/collect_heat_index.py [--start 2025-10-01 --end 2026-09-30]

The committed ERA5-Land ARCO extract has temperature and rainfall but no humidity, so the PRD v3
"hot day" (heat index >= 41 C) cannot be computed from it. Open-Meteo's historical API serves the
same ERA5-Land reanalysis (CC BY 4.0) with 2 m relative humidity and needs no key.

For each ERA5-Land cell that holds Laguna adults (data/processed/public/laguna/municipal_era5_cells.csv)
the hourly series is saved unmodified to data/raw/open_meteo/ (git-ignored Parquet, with a manifest).
Open-Meteo returns the nearest land grid point, so cells over Laguna de Bay take a neighbouring land
cell; the returned coordinates are recorded. The daily maximum of the hourly NWS heat index (Rothfusz
regression with its adjustments, the formula PAGASA's heat index follows) is written to the small
committed table data/processed/public/laguna/heat_index_daily_era5land.csv.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import urllib.parse
import urllib.request

import pandas as pd

from agap.climate.heat_index import heat_index_c
from agap.config import ROOT

API = "https://archive-api.open-meteo.com/v1/archive"
RAW = ROOT / "data/raw/open_meteo"
OUT = ROOT / "data/processed/public/laguna/heat_index_daily_era5land.csv"
BATCH = 10


def fetch(cells, start, end):
    params = dict(latitude=",".join(f"{lat:.1f}" for lat, _ in cells), longitude=",".join(f"{lon:.1f}" for _, lon in cells),
                  start_date=start, end_date=end, hourly="temperature_2m,relative_humidity_2m", models="era5_land",
                  timezone="Asia/Manila")
    url = f"{API}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "agap-ckd/1.0"}), timeout=300) as response:
        payload = json.loads(response.read())
    payload = payload if isinstance(payload, list) else [payload]
    frames = []
    for (lat, lon), series in zip(cells, payload):
        hourly = series["hourly"]
        frames.append(pd.DataFrame(dict(era5_cell=f"{lat:.1f},{lon:.1f}", grid_latitude=series["latitude"],
                                        grid_longitude=series["longitude"], local_time=pd.to_datetime(hourly["time"]),
                                        temperature_c=hourly["temperature_2m"], humidity_pct=hourly["relative_humidity_2m"])))
    return pd.concat(frames, ignore_index=True), url


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", default="2025-10-01")
    parser.add_argument("--end", default="2026-09-30")
    arguments = parser.parse_args()
    weights = pd.read_csv(ROOT / "data/processed/public/laguna/municipal_era5_cells.csv")
    cells = sorted({tuple(float(v) for v in cell.split(",")) for cell in weights.era5_cell})
    RAW.mkdir(parents=True, exist_ok=True)
    raw_path = RAW / f"era5_land_hourly_t2m_rh_{arguments.start}_{arguments.end}.parquet"
    if raw_path.exists():
        hourly, urls = pd.read_parquet(raw_path), []
    else:
        parts, urls = [], []
        for index in range(0, len(cells), BATCH):
            frame, url = fetch(cells[index:index + BATCH], arguments.start, arguments.end)
            parts.append(frame)
            urls.append(url)
        hourly = pd.concat(parts, ignore_index=True)
        hourly.to_parquet(raw_path, index=False)
        (RAW / f"{raw_path.stem}.manifest.json").write_text(json.dumps(dict(
            source="Open-Meteo Historical Weather API, ERA5-Land model (Copernicus ERA5-Land, CC BY 4.0)", requests=urls,
            retrieved_at_utc=datetime.now(timezone.utc).isoformat(), cells=len(cells),
            sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest()), indent=2))
    hourly = hourly.dropna(subset=["temperature_c", "humidity_pct"]).copy()
    hourly["heat_index_c"] = heat_index_c(hourly.temperature_c, hourly.humidity_pct)
    hourly["local_date"] = hourly.local_time.dt.date
    daily = hourly.groupby(["era5_cell", "grid_latitude", "grid_longitude", "local_date"]).agg(
        max_heat_index_c=("heat_index_c", "max"), max_temperature_c=("temperature_c", "max"), hours=("heat_index_c", "size")
    ).reset_index()
    daily["complete"] = daily.hours.eq(24)
    daily.round({"max_heat_index_c": 2, "max_temperature_c": 2}).to_csv(OUT, index=False)
    print(f"{len(cells)} cells, {daily.local_date.min()} to {daily.local_date.max()}, {len(daily):,} cell-days; "
          f"days with heat index >= 41 C: {(daily.max_heat_index_c >= 41).sum():,}")


if __name__ == "__main__":
    main()
