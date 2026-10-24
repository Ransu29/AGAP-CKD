"""Prepare a real January-temperature view and clinic rows without invented coordinates."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from zipfile import ZipFile

import eccodes
import numpy as np
import pandas as pd
from pypdf import PdfReader
from shapely import contains_xy
from shapely.geometry import shape

from agap.config import ROOT, load_config
from agap.experiment import atomic_text, save_frame
from agap.mapping import municipal_features


def temperature(province, destination):
    provinces = json.loads((ROOT / "data/raw/boundaries/PHL_ADM2_simplified.geojson").read_text())
    feature = next(f for f in provinces["features"] if f["properties"]["shapeName"].casefold() == province.casefold())
    polygon = shape(feature["geometry"])
    # January 2021 sample, read from the collected Jan–Jun 2021 replay archive.
    archive = ROOT / "data/raw/era5_land/laguna_replay/era5_land_2021_01-06_temperature_precipitation.grib.zip"
    if not archive.is_file():
        raise FileNotFoundError(f"{archive.relative_to(ROOT)} not collected yet; run make collect-climate")
    records, selected = [], None
    with ZipFile(archive) as zipped:
        member = next(name for name in zipped.namelist() if name.endswith(".grib"))
        data = zipped.read(member)
    offset = 0
    while offset < len(data):
        if data[offset:offset + 4] != b"GRIB" or data[offset + 7] != 1:
            raise ValueError("Temperature reader expects the collected GRIB1 archive")
        length = int.from_bytes(data[offset + 4:offset + 7], "big")
        handle = eccodes.codes_new_from_message(data[offset:offset + length])
        try:
            if eccodes.codes_get(handle, "shortName") != "2t":
                continue
            if eccodes.codes_get(handle, "validityDate") // 100 != 202101:
                continue
            if eccodes.codes_get(handle, "units") != "K":
                raise ValueError("Unexpected temperature unit")
            if selected is None:
                lat = eccodes.codes_get_array(handle, "latitudes")
                lon = eccodes.codes_get_array(handle, "longitudes")
                selected = np.flatnonzero(contains_xy(polygon, lon, lat))
                if not len(selected):
                    raise ValueError("Downloaded climate extent does not cover selected province")
            stamp = datetime.strptime(f"{eccodes.codes_get(handle, 'validityDate'):08d}{eccodes.codes_get(handle, 'validityTime'):04d}", "%Y%m%d%H%M")
            values = eccodes.codes_get_values(handle)
            missing = eccodes.codes_get(handle, "missingValue")
            for index in selected:
                records.append(dict(time_utc=stamp, latitude=lat[index], longitude=lon[index],
                                    era5_cell=f"{lat[index]:.1f},{lon[index]:.1f}",
                                    temperature_c=np.nan if values[index] == missing else values[index] - 273.15))
        finally:
            eccodes.codes_release(handle)
            offset += length
    hourly = pd.DataFrame(records)
    hourly["local_date"] = pd.to_datetime(hourly.time_utc, utc=True).dt.tz_convert("Asia/Manila").dt.strftime("%Y-%m-%d")
    daily = hourly.groupby(["era5_cell", "latitude", "longitude", "local_date"], as_index=False).agg(
        tmax_c=("temperature_c", "max"), tmean_c=("temperature_c", "mean"), valid_hours=("temperature_c", "count"))
    daily = daily[daily.local_date.str.startswith("2021-01")].reset_index(drop=True)
    daily["complete"] = daily.valid_hours == 24
    daily.loc[~daily.complete, ["tmax_c", "tmean_c"]] = np.nan
    save_frame(daily, destination / "temperature_daily.parquet")
    daily.to_csv(destination / "temperature_daily.csv", index=False)
    print(f"Temperature: {len(daily)} cell-days, {daily.era5_cell.nunique()} cells, {daily.complete.sum()} complete cell-days")


def clinic_rows(province, destination):
    reader = PdfReader(ROOT / "data/raw/philhealth/YAKAP.pdf")
    # Preserve source lines and page evidence for verification; no unreliable automated geocoding.
    collecting, records = False, []
    heading = ""
    for page_number, page in enumerate(reader.pages, 1):
        text = page.extract_text(extraction_mode="layout") or ""
        if page_number == 1:
            heading = text.splitlines()[0].strip()
        for line in text.splitlines():
            clean = line.strip()
            if clean == province.upper():
                collecting = True
                continue
            if collecting and clean in ("LUCENA CITY", "QUEZON", "RIZAL", "BATANGAS", "CAVITE", "MIMAROPA REGION", "REGION IV-B"):
                collecting = False
            if collecting:
                match = re.match(r"^\s*(\d+)\s{2,}(.+?)\s{2,}", line)
                if match:
                    records.append(dict(source_row=match.group(1), facility_name=match.group(2).strip(),
                                        source_page=page_number, source_line=clean,
                                        coordinate_status="unverified", latitude=None, longitude=None))
    # Retain no extracted staff contacts in the reviewer-facing CSV.
    output = pd.DataFrame(records)
    if output.empty:
        raise ValueError("No clinic rows parsed; inspect source manually")
    output.drop(columns="source_line").to_csv(destination / "clinic_verification_queue.csv", index=False)
    atomic_text(destination / "clinic_source_notes.json", json.dumps(dict(register_heading=heading,
                province=province, extracted_rows=len(output), limitations="Names extracted from PDF layout; verify against source page. No coordinates or panel capability verified."), indent=2))
    print(f"Clinic verification queue: {len(output)} source rows")


def municipal_boundaries(cfg, destination):
    """Persist the pilot province's municipal polygons for inspection and reuse (NFR-11)."""
    features = municipal_features(ROOT, cfg["study_area"]["pilot_area"])
    if features is None:
        raise FileNotFoundError("Collected boundaries are required; run make collect first")
    atomic_text(destination / "municipalities.geojson", json.dumps(features))
    print(f"Municipal boundaries: {len(features['features'])} municipalities")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/public.yaml")
    cfg = load_config(parser.parse_args().config)
    destination = ROOT / "data/processed/public" / cfg["study_area"]["pilot_area"].lower()
    destination.mkdir(parents=True, exist_ok=True)
    temperature(cfg["study_area"]["pilot_area"], destination)
    clinic_rows(cfg["study_area"]["pilot_area"], destination)
    municipal_boundaries(cfg, destination)
    print(destination)


if __name__ == "__main__":
    main()
