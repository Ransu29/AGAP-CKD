"""Explicit fixture or public population geography. Facilities remain hypothetical."""
from __future__ import annotations

import json
from pathlib import Path

import h3
import numpy as np
import pandas as pd
from shapely.geometry import Point, box, mapping, shape

POPULATION_TOLERANCE = 1e-6  # GEO-02: largest allowed relative difference after H3 aggregation


def population_check(source_total, demographics, cells):
    """GEO-02 / AT-01: the clipped source population must survive H3 aggregation."""
    totals = dict(source=float(source_total), demographics=float(demographics.adult_count.sum()),
                  cells=float(cells.adult_count.sum()))
    difference = max(abs(value - totals["source"]) for value in totals.values()) / max(abs(totals["source"]), 1e-12)
    if difference > POPULATION_TOLERANCE:
        raise ValueError(f"Population not conserved after H3 aggregation: {totals}, relative difference "
                         f"{difference:.2e} exceeds the {POPULATION_TOLERANCE:g} tolerance")
    return dict(totals, relative_difference=difference, tolerance=POPULATION_TOLERANCE,
                municipality_totals=cells.groupby("municipality").adult_count.sum().round(3).to_dict(),
                rule="Adult population inside the study boundary (15-19 band x 2/5) equals the H3 cell and age-sex totals.")


def fixture_geography(resolution=8):
    polygon = box(121.05, 14.1, 121.5, 14.45)
    identifiers = sorted(h3.geo_to_cells(mapping(polygon), resolution))
    cells = pd.DataFrame([dict(h3=cell, latitude=h3.cell_to_latlng(cell)[0],
                               longitude=h3.cell_to_latlng(cell)[1]) for cell in identifiers])
    cells["municipality"] = "Fixture zone " + (np.minimum(((cells.longitude - 121.05) / .09).astype(int), 4) + 1).astype(str)
    demographics = pd.DataFrame([dict(h3=cell, female=sex, age_start=age, adult_count=1.0)
                                 for cell in identifiers for sex in (0, 1) for age in range(20, 85, 5)])
    # Cell totals come from the age-sex table so both describe the same population (GEO-02).
    cells["adult_count"] = cells.h3.map(demographics.groupby("h3").adult_count.sum())
    demographics.attrs["source_population"] = float(demographics.adult_count.sum())
    boundary = {"type": "FeatureCollection", "features": [dict(type="Feature", properties={"name": "Illustrative fixture extent"}, geometry=mapping(polygon))]}
    return cells, demographics, boundary


def public_geography(root: Path, province: str, resolution=8, adult_fraction_15_19=.4):
    import rasterio
    from rasterio.mask import mask

    directory = root / "data/raw/boundaries"
    provinces = json.loads((directory / "PHL_ADM2_simplified.geojson").read_text())
    matches = [f for f in provinces["features"] if f["properties"]["shapeName"].casefold() == province.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one province named {province}; found {len(matches)}")
    polygon = shape(matches[0]["geometry"])
    municipal = json.loads((directory / "PHL_ADM3_simplified.geojson").read_text())["features"]
    municipalities = [(f["properties"]["shapeName"], shape(f["geometry"])) for f in municipal
                      if polygon.buffer(.002).covers(shape(f["geometry"]).representative_point())]
    if not municipalities:
        raise ValueError("No municipality geometry matched the study province")
    rows, source_total = [], 0.0
    for sex in ("f", "m"):
        for age in range(15, 85, 5):
            path = root / f"data/raw/worldpop/age_sex/phl_{sex}_{age}_2020_1km.tif"
            with rasterio.open(path) as raster:
                values, transform = mask(raster, [mapping(polygon)], crop=True, filled=False)
                valid = ~np.ma.getmaskarray(values[0]) & (values[0].data > 0)
                rr, cc = np.where(valid)
                source_total += float(values[0].data[valid].sum()) * (adult_fraction_15_19 if age == 15 else 1.0)
                x, y = rasterio.transform.xy(transform, rr, cc)
                for lon, lat, count in zip(x, y, values[0].data[valid]):
                    rows.append(dict(h3=h3.latlng_to_cell(lat, lon, resolution), female=int(sex == "f"),
                                     age_start=age, adult_count=float(count) * (adult_fraction_15_19 if age == 15 else 1.0)))
    demographics = pd.DataFrame(rows).groupby(["h3", "female", "age_start"], as_index=False).adult_count.sum()
    if demographics.empty:
        raise ValueError("No adult WorldPop mass inside study province")
    cells = demographics.groupby("h3", as_index=False).adult_count.sum()
    cells["latitude"] = cells.h3.map(lambda c: h3.cell_to_latlng(c)[0])
    cells["longitude"] = cells.h3.map(lambda c: h3.cell_to_latlng(c)[1])
    def municipality(row):
        point = Point(row.longitude, row.latitude)
        for name, geometry in municipalities:
            if geometry.covers(point):
                return name
        # Border cells are assigned to the closest municipality polygon, explicitly a derived rule.
        return min(municipalities, key=lambda item: item[1].distance(point))[0]
    cells["municipality"] = cells.apply(municipality, axis=1)
    demographics.attrs["source_population"] = source_total
    boundary = {"type": "FeatureCollection", "features": matches}
    return cells, demographics, boundary


def make_geography(cfg, root):
    mode = cfg["prototype"]["geography_mode"]
    if mode == "fixture":
        cells, demographics, boundary = fixture_geography(cfg["h3"]["main_resolution"])
    elif mode == "public":
        cells, demographics, boundary = public_geography(root, cfg["study_area"]["pilot_area"], cfg["h3"]["main_resolution"],
                                                         cfg["simulator"]["adult_fraction_15_19"])
    else:
        raise ValueError(f"Unknown geography mode: {mode}")
    demographics.attrs["population_check"] = population_check(demographics.attrs["source_population"], demographics, cells)
    cells["era5_cell"] = cells.apply(lambda r: f"{round(r.latitude, 1):.1f},{round(r.longitude, 1):.1f}", axis=1)
    cells["h3_parent"] = cells.h3.map(lambda c: h3.cell_to_parent(c, 7))
    # Registered clinics are real places, so they only apply to public geography; fixture zones keep hypothetical points.
    if mode == "public" and cfg["allocation"].get("service_points", "hypothetical") == "yakap_register":
        return cells, demographics, registered_service_points(cfg, root, set(cells.municipality)), boundary
    # Hypothetical service points at municipality population-centre cells, never real clinic coordinates.
    facilities = []
    for index, (name, group) in enumerate(cells.groupby("municipality", sort=True)):
        centre = group.loc[((group.latitude - np.average(group.latitude, weights=group.adult_count)) ** 2
                           + (group.longitude - np.average(group.longitude, weights=group.adult_count)) ** 2).idxmin()]
        facilities.append(dict(facility_id=f"SIM-{index:03d}", municipality=name,
                               latitude=centre.latitude, longitude=centre.longitude,
                               capacity=cfg["allocation"]["slots_per_facility"], verification_status="hypothetical"))
    return cells, demographics, pd.DataFrame(facilities), boundary


YAKAP_LOCATIONS = "data/processed/public/laguna/yakap_clinics.csv"


def registered_service_points(cfg, root: Path, municipalities):
    """PhilHealth YAKAP-accredited clinics as screening points, located with stated precision.

    Real register identities and approximate-or-mapped positions; screening capacity per site is an
    assumed setting and creatinine/uACR capability is unverified (V3-003).
    """
    path = root / YAKAP_LOCATIONS
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run scripts/prepare_clinic_locations.py --register yakap")
    clinics = pd.read_csv(path)
    clinics = clinics[clinics.municipality_name.isin(municipalities)]
    if clinics.empty:
        raise ValueError("No located YAKAP clinic lies in the study municipalities")
    return pd.DataFrame(dict(
        facility_id=clinics.register_id + "-" + clinics.entry.astype(int).astype(str),
        name=clinics.name.str.strip(), municipality=clinics.municipality_name,
        latitude=clinics.latitude.astype(float), longitude=clinics.longitude.astype(float),
        capacity=int(cfg["allocation"]["slots_per_registered_site"]),
        verification_status="registered; location " + clinics.location_precision + "; panel capability unverified",
    )).reset_index(drop=True)
