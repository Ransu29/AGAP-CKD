"""Extract ERA5-Land hourly 2 m temperature and precipitation for the Laguna box from ECMWF's ARCO Zarr stores.

Same grid and timestamps as the CDS GRIB archives, read directly from the CDS-hosted ARCO data lake
with the CDS API key (no request queue). Precipitation in these stores is already de-accumulated to
hourly amounts. Writes one Parquet file per year to data/raw/era5_land/arco/ plus a JSON record
with sources, period and checksums. Existing files are never overwritten.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

import certifi

# python.org builds on macOS do not use the system certificate store; verify with certifi's bundle.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/raw/era5_land/arco"
NORTH, WEST, SOUTH, EAST = 14.7, 120.9, 13.8, 121.7  # same box as collect_climate.py
START, END = "1990-12-01T00:00", "2026-09-30T23:00"     # UTC, same span as the CDS job list
STORES = {
    "t2m": "https://arco.datastores.ecmwf.int/cadl-arco-geo-007/arco/reanalysis_era5_land/sfc-2m-temperature/geoChunked.zarr",
    "tp": "https://arco.datastores.ecmwf.int/cadl-arco-geo-009/arco/reanalysis_era5_land/sfc-pressure-precipitation/geoChunked.zarr",
}


def cds_key():
    path = Path(os.environ.get("CDSAPI_RC", Path.home() / ".cdsapirc"))
    return next(line.split(":", 1)[1].strip() for line in path.read_text().splitlines() if line.startswith("key:"))


def read_variable(variable, key):
    store = xr.open_zarr(STORES[variable], consolidated=True, chunks=None,
                         storage_options={"headers": {"Authorization": f"Bearer {key}"}})
    lat = np.flatnonzero((np.round(store.latitude.values, 1) >= SOUTH) & (np.round(store.latitude.values, 1) <= NORTH))
    lon = np.flatnonzero((np.round(store.longitude.values, 1) >= WEST) & (np.round(store.longitude.values, 1) <= EAST))
    started = time.perf_counter()
    data = store[variable].isel(latitude=lat, longitude=lon).sel(time=slice(START, END)).load()
    return data, dict(store_attrs={k: v for k, v in data.attrs.items() if isinstance(v, (str, int, float))},
                      chunks=list(store[variable].encoding.get("chunks", [])), seconds=round(time.perf_counter() - started, 1))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    key = cds_key()
    t2m, t2m_info = read_variable("t2m", key)
    tp, tp_info = read_variable("tp", key)
    if not (np.array_equal(t2m.time, tp.time) and np.array_equal(t2m.latitude, tp.latitude) and np.array_equal(t2m.longitude, tp.longitude)):
        raise SystemExit("Temperature and precipitation stores disagree on time or grid")
    expected = pd.date_range(START, END, freq="h")
    if not pd.DatetimeIndex(t2m.time.values).equals(expected):
        raise SystemExit("ARCO time axis has gaps or extra hours in the requested period")
    frame = xr.Dataset({"t2m_k": t2m, "tp_m_hourly": tp}).to_dataframe().reset_index()
    frame = frame.rename(columns={"time": "time_utc"})
    frame["latitude"], frame["longitude"] = frame.latitude.round(1), frame.longitude.round(1)
    frame["era5_cell"] = frame.latitude.map("{:.1f}".format) + "," + frame.longitude.map("{:.1f}".format)
    frame = frame[["time_utc", "era5_cell", "latitude", "longitude", "t2m_k", "tp_m_hourly"]]
    files = {}
    for year, part in frame.groupby(frame.time_utc.dt.year, sort=True):
        target = DEST / f"era5_land_arco_{year}.parquet"
        if target.exists():
            raise SystemExit(f"{target} exists; extracted files are never overwritten")
        temporary = target.with_suffix(".parquet.partial")
        part.to_parquet(temporary, index=False)
        temporary.replace(target)
        files[target.name] = dict(rows=len(part), first_utc=str(part.time_utc.min()), last_utc=str(part.time_utc.max()),
                                  bytes=target.stat().st_size, sha256=sha256(target))
    record = dict(
        source="ERA5-Land hourly ARCO Zarr (ECMWF Copernicus data stores), geo-chunked stores", stores=STORES,
        retrieved_at_utc=datetime.now(timezone.utc).isoformat(), period_utc=[START, END],
        box_north_west_south_east=[NORTH, WEST, SOUTH, EAST], grid_cells=int(frame.era5_cell.nunique()),
        hours=len(expected), variables={"t2m_k": dict(t2m_info, units="K"),
                                        "tp_m_hourly": dict(tp_info, units="m per hour, de-accumulated by ECMWF")},
        conventions="time_utc is the validity time; tp_m_hourly at time t covers the hour ending at t; 00 UTC holds the "
                    "previous day's last hour. Lake and sea grid points are missing (NaN), as in the CDS GRIB.",
        status_note="ECMWF describes this ARCO service as experimental and non-operational; this local copy is the "
                    "pipeline input, so later service changes do not affect it.",
        files=files)
    (DEST / "era5_land_arco.json").write_text(json.dumps(record, indent=2))
    print(f"t2m read in {t2m_info['seconds']}s, tp in {tp_info['seconds']}s; {len(files)} files, "
          f"{sum(f['bytes'] for f in files.values()) / 1e6:.1f} MB, {len(frame):,} rows")


if __name__ == "__main__":
    main()
