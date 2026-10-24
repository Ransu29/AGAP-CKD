"""Connect verified historical exposure artifacts to reproducible simulations."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd


# Replay 2021 to the last complete ERA5-Land month; deployment spans the
# 2026 El Niño cited in the proposal. The committed ARCO extract
# (data/raw/era5_land/arco, December 1990 to September 2026) covers every
# period, so no Copernicus key is needed. Extend deployment and the extract
# together. The reference is the WMO 1991–2020 normal, which ends before the
# replay begins (SRS v1.1 erratum; the v1.2 fallback periods are withdrawn).
PARTITION_DATES = {
    "train": ("2021-01-01", "2023-12-31"),
    "validation": ("2024-01-01", "2024-12-31"),
    "deployment": ("2025-01-01", "2026-09-30"),
}
BASELINE_YEARS = (1991, 2020)
CLIMATE_FILES = {
    "daily.parquet": "climate_daily.parquet",
    "exposure.parquet": "climate_exposure.parquet",
    "baseline.parquet": "climate_baseline.parquet",
    "metadata.json": "climate_metadata.json",
}


def climate_mode(cfg):
    mode = cfg.get("climate", {}).get("mode", "synthetic")
    if mode not in ("synthetic", "era5_land"):
        raise ValueError(f"Unknown climate mode: {mode}")
    return mode


def climate_inputs(cfg, root):
    if climate_mode(cfg) == "synthetic":
        return []
    source = Path(root) / cfg["climate"].get("processed_directory", "data/processed/climate/laguna")
    paths = [source / name for name in CLIMATE_FILES]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("Historical climate is not prepared. Run make collect-climate and make prepare-climate. Missing: " + ", ".join(missing))
    return paths


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validated_exposure(path):
    exposure = pd.read_parquet(path)
    required = {"era5_cell", "cutoff", "hot_dry_score", "complete", "window_start", "window_end"}
    if not required.issubset(exposure.columns):
        raise ValueError(f"Climate exposure missing columns: {sorted(required - set(exposure.columns))}")
    exposure["cutoff"] = pd.to_datetime(exposure.cutoff)
    if exposure.cutoff.dt.tz is not None or not exposure.cutoff.equals(exposure.cutoff.dt.normalize()):
        raise ValueError("Exposure cutoff must be a naive local calendar date at midnight")
    if exposure.duplicated(["era5_cell", "cutoff"]).any():
        raise ValueError("Duplicate climate cell/date keys")
    complete = exposure.complete.eq(True)
    valid = exposure.loc[complete].copy()
    if valid.empty or not np.isfinite(valid.hot_dry_score).all():
        raise ValueError("Complete historical exposures must have finite scores")
    if not (pd.to_datetime(valid.window_end) == valid.cutoff - pd.Timedelta(days=1)).all():
        raise ValueError("Climate windows must end before the screening cutoff")
    if not (pd.to_datetime(valid.window_start) == valid.cutoff - pd.Timedelta(days=30)).all():
        raise ValueError("Climate windows must contain the preceding 30 local days")
    return exposure


def _grid_distance_km(latitude, longitude, era5_cells):
    """Great-circle km from each point to each 'lat,lon' source-cell centre."""
    centres = np.array([[float(value) for value in cell.split(",")] for cell in era5_cells])
    lat1, lon1 = np.deg2rad(np.asarray(latitude, float))[:, None], np.deg2rad(np.asarray(longitude, float))[:, None]
    lat2, lon2 = np.deg2rad(centres[:, 0])[None, :], np.deg2rad(centres[:, 1])[None, :]
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def snapshot_climate(cfg, root, directory, cells, demographics):
    """Freeze exact climate inputs and disclose the supported population frame.

    Masked lake/coastal source cells are not filled from synthetic climate. A cell
    must have at least 95% complete dates in EVERY partition to enter this replay.
    A populated H3 cell whose own source cell fails that test (for example a
    lakeshore cell whose nearest grid point lies over Laguna de Bay) takes the
    nearest supported source cell within climate.max_reassignment_km; its original
    source cell is kept in era5_cell_source (GEO-05). Residents remain eligible
    irrespective of questionnaire participation.
    """
    paths = climate_inputs(cfg, root)
    if not paths:
        return cells, demographics
    exposure = validated_exposure(next(path for path in paths if path.name == "exposure.parquet"))
    valid = exposure[exposure.complete.eq(True)]
    coverage, supported = {}, set(exposure.era5_cell)
    minimum = cfg["climate"].get("minimum_date_coverage", .95)
    if not 0 < minimum <= 1:
        raise ValueError("Climate minimum date coverage must be in (0, 1]")
    for name, (start, end) in PARTITION_DATES.items():
        counts = valid[valid.cutoff.between(start, end)].groupby("era5_cell").size()
        fractions = counts / len(pd.date_range(start, end))
        supported &= set(fractions[fractions >= minimum].index)
        coverage[name] = fractions.to_dict()
    limit_km = float(cfg["climate"].get("max_reassignment_km", 15))
    cells = cells.copy()
    cells["era5_cell_source"] = cells.era5_cell
    cells["climate_reassignment_km"] = np.nan
    unsupported = ~cells.era5_cell.isin(supported)
    targets = sorted(supported)
    if unsupported.any() and targets:
        distance = _grid_distance_km(cells.loc[unsupported, "latitude"], cells.loc[unsupported, "longitude"], targets)
        nearest, km = distance.argmin(axis=1), distance.min(axis=1)
        within = km <= limit_km
        rows = cells.index[unsupported][within]
        cells.loc[rows, "era5_cell"] = np.array(targets)[nearest[within]]
        cells.loc[rows, "climate_reassignment_km"] = km[within]
    cells["climate_reassigned"] = cells.era5_cell.ne(cells.era5_cell_source)
    selected = cells[cells.era5_cell.isin(supported)].copy()
    if selected.era5_cell.nunique() < 5:
        raise ValueError("Fewer than five climate-supported population cells; cannot create a geographic holdout")
    selected_demographics = demographics[demographics.h3.isin(selected.h3)].copy()
    population_total = float(demographics.adult_count.sum())
    population_supported = float(selected_demographics.adult_count.sum())
    for path in paths:
        target = directory / CLIMATE_FILES[path.name]
        temporary = target.with_name(target.name + ".partial")
        shutil.copyfile(path, temporary)
        temporary.replace(target)
    record = {
        "mode": "era5_land",
        "source_cell_count": int(cells.era5_cell_source.nunique()),
        "supported_source_cell_count": int(selected.era5_cell.nunique()),
        "excluded_source_cells": sorted(set(cells.era5_cell_source) - supported),
        "reassignment": {
            "rule": f"Populated H3 cells whose source cell lacks coverage take the nearest supported source cell within {limit_km:g} km; era5_cell_source keeps the original.",
            "max_reassignment_km": limit_km,
            "h3_cells_reassigned": int(selected.climate_reassigned.sum()),
            "adults_reassigned": float(demographics[demographics.h3.isin(selected.loc[selected.climate_reassigned, "h3"])].adult_count.sum()),
            "largest_distance_km": float(selected.climate_reassignment_km.max()) if selected.climate_reassigned.any() else 0.0,
            "source_to_assigned": {source: sorted(group.era5_cell.unique()) for source, group in selected[selected.climate_reassigned].groupby("era5_cell_source")},
            "h3_cells_still_excluded": int((~cells.era5_cell.isin(supported)).sum()),
        },
        "worldpop_modeled_adults_before_climate_filter": population_total,
        "worldpop_modeled_adults_supported": population_supported,
        "modeled_population_fraction_supported": population_supported / population_total,
        "minimum_date_coverage_per_partition": minimum,
        "date_coverage": coverage,
        "date_sampling": "Uniformly sample complete source-cell dates inside the declared partition; no climate interpolation.",
        "limitation": "Reassigned residents use climate from a neighbouring land grid cell, not the cell over their own location. Population cells with no supported source cell within the limit are excluded, so the frame may not represent every Laguna adult.",
        "input_sha256": {path.name: sha256_file(path) for path in paths},
    }
    (directory / "climate_frame.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return selected, selected_demographics


def attach_historical_exposure(frame, exposure, rng, partition, period=None):
    """Sample dates and join only available public climate, before outcome synthesis."""
    start, end = period or PARTITION_DATES[partition]
    available = exposure[exposure.complete.eq(True) & exposure.cutoff.between(start, end)].copy()
    output = frame.copy()
    for cell, indices in output.groupby("era5_cell", sort=True).groups.items():
        dates = available.loc[available.era5_cell == cell, "cutoff"].to_numpy()
        if not len(dates):
            raise ValueError(f"No complete historical climate for {cell} in {partition}")
        output.loc[indices, "cutoff"] = rng.choice(dates, size=len(indices))
    output["cutoff"] = pd.to_datetime(output.cutoff)
    columns = ["era5_cell", "cutoff", "hot_dry_score", "window_start", "window_end"]
    output = output.merge(available[columns], on=["era5_cell", "cutoff"], how="left", validate="many_to_one", sort=False)
    if len(output) != len(frame) or not np.isfinite(output.hot_dry_score).all():
        raise ValueError("Historical climate join lost residents or produced missing scores")
    output["climate_source"] = "Copernicus ERA5-Land"
    return output
