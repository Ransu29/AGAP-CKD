"""Source metadata for the data manifest (SRS DATA-02).

Every manifest entry must carry the fields in REQUIRED_FIELDS. Download-specific values (URL,
checksum, retrieval time, size) come from the collector; family-level values (publisher, release,
represented dates, attribution, CRS, units, resolution, missing values, processing) come from
SOURCES. Unknown or unverified details are stated as such rather than guessed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

PLANNED_CLIMATE_ARCHIVES = 74  # scripts/collect_climate.py default job list: Dec 1990 to Sep 2026
REQUIRED_FIELDS = ("id", "publisher", "url", "release", "represented_dates", "checked_utc", "sha256", "license",
                   "attribution", "crs", "units", "resolution", "missing_values", "processing", "limitations")

_WORLDPOP = dict(
    publisher="WorldPop, School of Geography and Environmental Science, University of Southampton",
    release="Global 2000-2020 1 km, unconstrained top-down estimates",
    represented_dates="2020",
    attribution="WorldPop (www.worldpop.org); cite the dataset as listed on the WorldPop data page",
    crs="EPSG:4326", resolution="30 arc-seconds (about 1 km)",
    missing_values="Raster NoData cells and zero-count pixels are dropped before aggregation",
)

SOURCES = {
    "worldpop_population": dict(
        _WORLDPOP, units="People per pixel (all ages)",
        processing="Downloaded only; the model uses the age-sex rasters (worldpop_age_sex)"),
    "worldpop_age_sex": dict(
        _WORLDPOP, units="People per pixel in one sex and 5-year age band (15-19 through 80+)",
        processing="Clipped to the province boundary; pixel centres assigned to H3 resolution 8; 15-19 band x 2/5 as "
                   "adults; population conservation checked (GEO-02)"),
    "boundaries": dict(
        publisher="geoBoundaries (William & Mary geoLab); source data NAMRIA, PSA and OCHA Philippines",
        release="gbOpen PHL ADM2/ADM3 simplified; see the release metadata file for build date",
        represented_dates="2020 boundaries (boundaryYearRepresented)",
        attribution="geoBoundaries (Runfola et al., 2020) and the original sources named in the release metadata",
        crs="EPSG:4326", units="Polygon geometry in decimal degrees", resolution="Simplified polygons; not survey-grade",
        missing_values="Not applicable; a missing province or municipality stops the build (DATA-03)",
        processing="Province selected by name; municipalities matched by representative point; border H3 cells take the "
                   "closest municipality polygon"),
    "yakap_register": dict(
        publisher="Philippine Health Insurance Corporation (PhilHealth)",
        release="Accredited YAKAP facility register (PDF), current at retrieval",
        represented_dates="Snapshot at the retrieval date",
        attribution="PhilHealth", crs="None (no coordinates)", units="Facility names and addresses",
        resolution="Facility level, without coordinates", missing_values="Rows that cannot be parsed are not added",
        processing="Laguna section parsed into clinic_verification_queue.csv (names only, coordinates unverified)"),
    "pagasa_advisory": dict(
        publisher="DOST-PAGASA", release="ENSO Advisory No. 7 (PDF)", represented_dates="Published 2024-01-05",
        attribution="DOST-PAGASA", crs="None", units="Narrative advisory", resolution="National",
        missing_values="Not applicable", processing="Stored only; not used in analysis (E2-05)"),
    "fnri_results": dict(
        publisher="DOST Food and Nutrition Research Institute (FNRI)",
        release="2023 National Nutrition Survey results, 2024 National Nutrition Summit part 2 (PDF)",
        represented_dates="2023 survey", attribution="DOST-FNRI", crs="None", units="Survey prevalence tables",
        resolution="National and regional", missing_values="Not applicable",
        processing="Stored for definition review; no parameters extracted yet (SIM-04)"),
    "era5_land": dict(
        publisher="Copernicus Climate Change Service (C3S), ECMWF",
        release="ERA5-Land hourly data from 1950 to present (reanalysis-era5-land), Climate Data Store",
        represented_dates="December 1990 to September 2026 (1991-2020 reference, January 2021 to September 2026 replay), "
                          "from the committed ARCO extract; CDS GRIB archives are committed as they arrive as a cross-check",
        attribution="Contains modified Copernicus Climate Change Service information; Muñoz-Sabater et al. (2021), "
                    "Earth System Science Data 13, 4349-4383",
        crs="Regular 0.1 degree latitude-longitude grid (EPSG:4326)",
        units="2 m temperature in K (converted to °C); total precipitation in m accumulated from 00 UTC (converted to hourly mm)",
        resolution="0.1 degree grid (about 11 km); about 9 km native model resolution",
        missing_values="Lake and sea grid points are masked (no data); incomplete local days and windows stay missing",
        processing="Rainfall de-accumulated within each forecast cycle; Asia/Manila local days; 7- and 30-day windows; "
                   "anomalies against the 1991-2020 monthly reference (climate/history.py); lakeshore cells take the "
                   "nearest supported grid cell within 15 km"),
}


def family_for(source_id):
    """Source family of a manifest entry ID."""
    if source_id == "worldpop_population":
        return "worldpop_population"
    if source_id.startswith("worldpop_"):
        return "worldpop_age_sex"
    if source_id.startswith(("boundary_", "boundaries")):
        return "boundaries"
    if source_id.startswith("pagasa_"):
        return "pagasa_advisory"
    if source_id.startswith("fnri_"):
        return "fnri_results"
    if source_id.startswith("era5_land"):
        return "era5_land"
    if source_id in SOURCES:
        return source_id
    raise KeyError(f"No DATA-02 source metadata for manifest entry {source_id!r}")


def enrich(entry):
    """Add family metadata; values the collector recorded (URL, licence, checksum) take precedence."""
    family = SOURCES[family_for(entry["id"])]
    merged = {**family, **{key: value for key, value in entry.items() if value not in (None, "")}}
    if entry["id"].startswith("worldpop_"):
        merged["limitations"] = (entry.get("limitations", "") + " Unconstrained product, whereas SRS DATA-01 specifies "
                                 "the 2020 constrained counts.").strip()
    return merged


def missing_fields(entry):
    return [field for field in REQUIRED_FIELDS if entry.get(field) in (None, "")]


def climate_entry(raw: Path):
    """One manifest entry for ERA5-Land: the ARCO extract the pipeline uses, with CDS archives as a cross-check."""
    records = [json.loads(path.read_text()) for path in sorted((raw / "era5_land/laguna_replay").glob("*.grib.zip.json"))]
    complete = [record for record in records if record.get("status") == "complete"]
    cds_status = f"CDS GRIB cross-check: {len(complete)} of {PLANNED_CLIMATE_ARCHIVES} planned archives complete"
    arco_path = raw / "era5_land/arco/era5_land_arco.json"
    if arco_path.exists():
        arco = json.loads(arco_path.read_text())
        return enrich(dict(
            id="era5_land_laguna", path="era5_land/arco/", url="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land",
            license="CC BY 4.0", status=f"ARCO extract: {len(arco['files'])} yearly files, {arco['period_utc'][0]} to {arco['period_utc'][1]} UTC; {cds_status}",
            checked_utc=arco["retrieved_at_utc"], sha256="Per yearly file in era5_land/arco/era5_land_arco.json (verified before use)",
            release="ERA5-Land hourly, ECMWF ARCO Zarr data lake (geo-chunked stores), served with the CDS key",
            processing=SOURCES["era5_land"]["processing"].replace("Rainfall de-accumulated within each forecast cycle",
                       "Rainfall already hourly in ARCO (equal to our CDS de-accumulation within GRIB packing precision); rounding noise clipped"),
            limitations="Gridded reanalysis, a community-level proxy rather than personal exposure; lake-masked cells have no data. "
                        "ECMWF describes the ARCO service as experimental; the local extract is the pipeline input."))
    retrieved = max((record.get("retrieved_at_utc", "") for record in complete), default="")
    return enrich(dict(
        id="era5_land_laguna", path="era5_land/laguna_replay/", url="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land",
        license="CC BY 4.0", status=f"{len(complete)} of {PLANNED_CLIMATE_ARCHIVES} planned archives complete",
        checked_utc=retrieved or datetime.now(timezone.utc).isoformat(),
        sha256="Per archive, in the .grib.zip.json record next to each file",
        limitations="Gridded reanalysis, a community-level proxy rather than personal exposure; lake-masked cells have no data."))
