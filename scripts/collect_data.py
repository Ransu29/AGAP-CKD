"""Download public inputs; record checksums, provenance, and failures without fallback.

No patient data and no credentialed network requests are made by this script.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import requests
import yaml

from agap.data.sources import climate_entry, enrich, missing_fields

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"


def download(item):
    item = dict(item)
    path = RAW / item["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not path.exists():
            response = requests.get(item["url"], timeout=(15, 180), stream=True)
            response.raise_for_status()
            partial = path.with_suffix(path.suffix + ".partial")
            with partial.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    handle.write(chunk)
            if partial.stat().st_size == 0:
                raise ValueError("Empty download")
            if path.suffix == ".pdf" and not partial.read_bytes().startswith(b"%PDF"):
                raise ValueError("Server did not return a PDF")
            partial.replace(path)
        item.update(status="downloaded", bytes=path.stat().st_size,
                    sha256=hashlib.file_digest(path.open("rb"), "sha256").hexdigest(),
                    checked_utc=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        item.update(status="failed", error=str(exc))
    print(f"{item['status']}: {item['path']}", flush=True)
    return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demographics", action="store_true", help="Also collect all adult age–sex rasters")
    args = parser.parse_args()
    catalog = [
        dict(id="worldpop_population", path="worldpop/phl_ppp_2020_1km_Aggregated.tif",
             url="https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2020/PHL/phl_ppp_2020_1km_Aggregated.tif",
             license="CC BY 4.0; attribute WorldPop and original release", crs="EPSG:4326",
             limitations="2020 modeled all-age population; 1 km raster, not resident addresses."),
        dict(id="yakap_register", path="philhealth/YAKAP.pdf",
             url="https://www.philhealth.gov.ph/partners/providers/facilities/accredited/YAKAP.pdf",
             license="Public official register; redistribution terms not established", crs=None,
             limitations="Current snapshot; names/addresses require coordinate verification. No panel capacity established."),
        dict(id="pagasa_2024_01", path="pagasa/2024_01_05_enso.pdf",
             url="https://pubfiles.pagasa.dost.gov.ph/pagasaweb/files/climate/elninolanina/01052024_ENSO_Advisory7_OS.pdf",
             license="Public official advisory; redistribution terms not established", crs=None,
             limitations="One published advisory; not a complete historical series. Publication date 2024-01-05."),
        dict(id="fnri_2023_results", path="fnri/2023_nns_clinical_results.pdf",
             url="https://enutrition.fnri.dost.gov.ph/uploads/2024%20National%20Nutrition%20Summit_Part%202.pdf",
             license="Public report; redistribution terms not established", crs=None,
             limitations="Definitions and denominators must be reviewed before parameter extraction; no automatic DM/HTN calibration."),
    ]
    # In the Philippines ADM2 is province; ADM1 is region.
    for level in (2, 3):
        url = f"https://www.geoboundaries.org/api/current/gbOpen/PHL/ADM{level}/"
        metadata = download(dict(id=f"boundary_metadata_{level}", path=f"boundaries/ADM{level}_metadata.json",
                                 url=url, license="See boundary metadata", limitations="Release metadata", crs=None))
        catalog.append(metadata)
        if metadata["status"] == "downloaded":
            meta = json.loads((RAW / metadata["path"]).read_text())
            catalog.append(dict(id=f"boundary_adm{level}", path=f"boundaries/PHL_ADM{level}_simplified.geojson",
                                url=meta["simplifiedGeometryGeoJSON"], license=meta["boundaryLicense"],
                                crs="EPSG:4326", limitations=f"Simplified {meta['boundaryYearRepresented']} boundaries; not survey-grade."))
    if args.demographics:
        base = "https://data.worldpop.org/GIS/AgeSex_structures/Global_2000_2020_1km/unconstrained/2020/PHL"
        for sex in ("f", "m"):
            for age in range(15, 85, 5):
                name = f"phl_{sex}_{age}_2020_1km.tif"
                catalog.append(dict(id=f"worldpop_{sex}_{age}", path=f"worldpop/age_sex/{name}",
                                    url=f"{base}/{name}", license="CC BY 4.0; attribute WorldPop", crs="EPSG:4326",
                                    limitations="Modeled 2020 age–sex counts; 15–19 adult fraction assumed 2/5; 80+ open band."))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(download, catalog))
    # DATA-02: every entry carries publisher, release, dates, attribution, CRS, units, resolution,
    # missing-value conventions and processing history; ERA5-Land archives are one family entry.
    results = [enrich(item) for item in results] + [climate_entry(RAW)]
    incomplete = {item["id"]: missing_fields(item) for item in results if missing_fields(item) and item["status"] != "failed"}
    if incomplete:
        raise SystemExit(f"Manifest entries missing DATA-02 fields: {incomplete}")
    manifest = {"checked_utc": datetime.now(timezone.utc).isoformat(), "datasets": results}
    target = ROOT / "data/manifest.yaml"
    target.write_text(yaml.safe_dump(manifest, sort_keys=False))
    print(f"Manifest: {target}")
    if any(item["status"] == "failed" for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
