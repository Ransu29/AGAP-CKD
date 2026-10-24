"""Preview the downloaded January 2021 GRIB ZIP; requires eccodes, numpy, matplotlib.

Run: .venv/bin/python scripts/preview_era5_land.py
"""
from __future__ import annotations

import base64
import csv
from datetime import datetime
import html
import io
import json
import os
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".venv" / "matplotlib-cache"))

import eccodes
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np


def main() -> None:
    archive_path = ROOT / "data/raw/era5_land/era5_land_2021_01_temperature_precipitation.grib.zip"
    output = archive_path.parent / "preview"
    output.mkdir(exist_ok=True)
    with ZipFile(archive_path) as archive:
        data = archive.read("data.grib")

    records: dict[str, dict[datetime, np.ndarray]] = {"2t": {}, "tp": {}}
    position = 0
    latitude = longitude = None
    shape = None
    while position < len(data):
        assert data[position:position + 4] == b"GRIB"
        assert data[position + 7] == 1, "This preview expects the downloaded GRIB1 archive."
        size = int.from_bytes(data[position + 4:position + 7], "big")
        handle = eccodes.codes_new_from_message(data[position:position + size])
        try:
            variable = eccodes.codes_get(handle, "shortName")
            if variable not in records:
                raise ValueError(f"Unexpected variable: {variable}")
            timestamp = datetime.strptime(
                f"{eccodes.codes_get(handle, 'validityDate'):08d}"
                f"{eccodes.codes_get(handle, 'validityTime'):04d}", "%Y%m%d%H%M"
            )
            grid_shape = (eccodes.codes_get(handle, "Nj"), eccodes.codes_get(handle, "Ni"))
            lat = eccodes.codes_get_array(handle, "latitudes").reshape(grid_shape)
            lon = eccodes.codes_get_array(handle, "longitudes").reshape(grid_shape)
            if latitude is None:
                latitude, longitude, shape = lat, lon, grid_shape
            elif not (np.array_equal(lat, latitude) and np.array_equal(lon, longitude)):
                raise ValueError("Grid coordinates changed between fields.")
            values = eccodes.codes_get_values(handle).reshape(grid_shape)
            values = np.where(values == eccodes.codes_get(handle, "missingValue"), np.nan, values)
            units = eccodes.codes_get(handle, "units")
            if variable == "2t":
                assert units == "K"
                values = values - 273.15
            else:
                assert units == "m"
                # Preserve values as stored. Interval metadata alone is insufficient:
                # daily resets suggest cumulative values despite one-hour step ranges.
                start = eccodes.codes_get(handle, "startStep")
                end = eccodes.codes_get(handle, "endStep")
                assert eccodes.codes_get(handle, "stepUnits") == 1
                assert end - start == 1, "Rainfall needs different accumulation handling."
                values = values * 1000
            if timestamp in records[variable]:
                raise ValueError("Duplicate variable/time field")
            records[variable][timestamp] = values
        finally:
            eccodes.codes_release(handle)
        position += size

    times = sorted(records["2t"])
    assert times == sorted(records["tp"]) and len(times) == 744
    assert all((b - a).total_seconds() == 3600 for a, b in zip(times, times[1:]))
    temperature = np.stack([records["2t"][time] for time in times])
    rain = np.stack([records["tp"][time] for time in times])
    temperature_mean = np.full(shape, np.nan)
    valid = np.isfinite(temperature).sum(axis=0)
    np.divide(np.nansum(temperature, axis=0), valid, out=temperature_mean, where=valid > 0)
    rain_snapshot = rain[times.index(datetime(2021, 1, 15))]
    hourly_temp = np.nanmean(temperature, axis=(1, 2))
    hourly_rain = np.nanmean(rain, axis=(1, 2))
    rows = [(time.strftime("%Y-%m-%dT%H:%M:%SZ"), float(t), float(p))
            for time, t, p in zip(times, hourly_temp, hourly_rain)]
    with (output / "hourly_region_summary.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["valid_time_utc", "unweighted_land_grid_mean_temperature_c",
                         "unweighted_land_grid_mean_precipitation_as_stored_mm"])
        writer.writerows(rows)
    with (output / "grid_preview.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["latitude", "longitude", "january_mean_temperature_c", "precipitation_as_stored_2021_01_15_00_utc_mm"])
        for lat, lon, temp, precip in zip(latitude.flat, longitude.flat, temperature_mean.flat, rain_snapshot.flat):
            writer.writerow([lat, lon, "" if not np.isfinite(temp) else float(temp),
                             "" if not np.isfinite(precip) else float(precip)])

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), layout="constrained")
    for ax, values, title, label, cmap in [
        (axes[0, 0], temperature_mean, "January 2021 mean 2 m temperature", "Temperature (°C)", "inferno"),
        (axes[0, 1], rain_snapshot, "Stored precipitation · Jan 15, 00:00 UTC", "Precipitation as stored (mm)", "Blues"),
    ]:
        mesh = ax.pcolormesh(longitude, latitude, values, shading="nearest", cmap=cmap)
        fig.colorbar(mesh, ax=ax, label=label, shrink=0.85)
        ax.set(title=title, xlabel="Longitude (degrees east)", ylabel="Latitude (degrees north)")
        ax.set_aspect(1 / np.cos(np.deg2rad(15.5)))
    axes[1, 0].plot(times, hourly_temp, color="#9a3412", linewidth=0.8)
    axes[1, 0].set(title="Hourly mean temperature over available land grid points",
                   xlabel="Date (UTC, January 2021)", ylabel="Temperature (°C)")
    axes[1, 1].plot(times, hourly_rain, color="#1d4ed8", linewidth=0.8)
    axes[1, 1].set(title="Stored precipitation · mean over available land grid points",
                   xlabel="Valid timestamp (UTC, January 2021)", ylabel="Precipitation as stored (mm)")
    for ax in axes[1]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.grid(alpha=0.2)
    fig.suptitle("ERA5-Land · January 2021 regional preview", fontsize=15)
    fig.supxlabel("Source: Copernicus ERA5-Land, Jan 1–31, 2021 UTC · 0.1° grid · blank cells are missing/masked\n"
                  "Not clipped to Laguna · unweighted regional means · verify precipitation accumulation before calculating totals.", fontsize=9)
    fig.savefig(output / "dataset_preview.png", dpi=150)
    plt.close(fig)

    stats = {
        "hours_per_variable": len(times), "grid_rows": shape[0], "grid_columns": shape[1],
        "available_points_first_temperature_field": int(np.isfinite(temperature[0]).sum()),
        "missing_points_first_temperature_field": int(np.isnan(temperature[0]).sum()),
        "start_utc": rows[0][0], "end_utc": rows[-1][0],
        "temperature_units": "degrees Celsius", "precipitation_units": "mm as stored, not deaccumulated",
        "precipitation_note": "One-hour step metadata conflicts with apparent cumulative daily resets; accumulation interpretation requires validation before totals.",
        "latitude_bounds": [float(latitude.min()), float(latitude.max())],
        "longitude_bounds": [float(longitude.min()), float(longitude.max())],
    }
    (output / "summary.json").write_text(json.dumps(stats, indent=2) + "\n")
    embedded = base64.b64encode((output / "dataset_preview.png").read_bytes()).decode()
    table = "".join(f"<tr><td>{html.escape(time)}</td><td>{temp:.2f}</td><td>{precip:.4f}</td></tr>"
                    for time, temp, precip in rows[:12])
    page = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AGAP-CKD · ERA5-Land dataset preview</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;max-width:1200px;margin:32px auto;padding:0 24px;color:#17212b}}
h1{{font-size:28px}}img{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%}}
th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid #ddd}}a{{color:#145d8b}}</style>
<h1>ERA5-Land · January 2021</h1>
<p>744 hourly timestamps per variable · 44 × 35 grid · 587 available and 953 missing/masked points in the first field.</p>
<p>This is the downloaded regional extent (13.8–17.2° N, 119.3–123.6° E), not a Laguna-only dataset.
Temperature is converted from Kelvin to Celsius. Precipitation is converted from metres to millimetres and shown as stored.</p>
<p><strong>Precipitation interpretation:</strong> values show apparent daily cumulative resets despite one-hour GRIB step ranges.
Verify the accumulation convention before computing hourly increments or daily totals; no rainfall totals are calculated in this preview.</p>
<img alt="Temperature and rainfall maps and hourly time series for the downloaded extent" src="data:image/png;base64,{embedded}">
<h2>Open the data as spreadsheets</h2><p>
<a href="hourly_region_summary.csv">Hourly regional summary CSV</a> ·
<a href="grid_preview.csv">Grid preview CSV</a> · <a href="summary.json">Dataset metadata</a></p>
<p>Regional summaries are simple unweighted means over available grid points. Grid CSV missing values are blank.
The precipitation map shows the stored field at January 15, 00:00 UTC.</p>
<h2>First 12 hourly records</h2><table><thead><tr><th>Valid timestamp (UTC)</th>
<th>Mean temperature (°C)</th><th>Mean precipitation as stored (mm)</th></tr></thead><tbody>{table}</tbody></table>
<p>Source: <a href="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land">Copernicus ERA5-Land</a>.
Original archive: {html.escape(archive_path.name)}. These are climate reanalysis fields, not patient records.</p></html>"""
    (output / "index.html").write_text(page)
    print(json.dumps(stats, indent=2))
    print(f"Preview: {output / 'index.html'}")


if __name__ == "__main__":
    main()
