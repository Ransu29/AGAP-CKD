"""Locate Laguna's PhilHealth-registered clinics with honest location precision.

    python scripts/prepare_clinic_locations.py --register dialysis   # freestanding dialysis clinics
    python scripts/prepare_clinic_locations.py --register yakap      # YAKAP primary-care clinics
    python scripts/prepare_clinic_locations.py --register all --offline

Inputs (collected separately, never fabricated): the register PDF (see agap.registers.REGISTERS),
OpenStreetMap features from the Overpass API (fetched once and saved next to the PDF), and
data/processed/public/laguna/municipalities.geojson. Barangay centres are geocoded with
OpenStreetMap Nominatim at most once per second and cached; --offline uses saved files only.

Output: data/processed/public/laguna/<register>_clinics.csv and <register>_clinics_notes.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

import pandas as pd
from pypdf import PdfReader
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agap.registers import LOCATION_PRECISION, REGISTERS, barangay_name, boundary_name, match_osm, parse_register  # noqa: E402

OUTPUT = ROOT / "data/processed/public/laguna"
NOMINATIM_CACHE = ROOT / "data/raw/philhealth/nominatim_cache.json"
USER_AGENT = "agap-ckd-prototype/0.1 (synthetic screening research demo; one-off geocoding of public clinic lists)"
OVERPASS = {
    "dialysis": '(nwr["healthcare"="dialysis"](area.a);nwr["healthcare:speciality"~"dialysis|nephrology"](area.a);'
                'nwr["name"~"[Dd]ialysis|[Hh]emodialysis|[Kk]idney|[Nn]ephro|[Rr]enal"](area.a););',
    "yakap": '(nwr["amenity"~"clinic|doctors|hospital"](area.a);nwr["healthcare"](area.a););',
}


def _request(url, data=None):
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def osm_features(key, register, offline):
    path = ROOT / register["osm"]
    if not path.exists():
        if offline:
            raise FileNotFoundError(f"{path} is missing; run without --offline once")
        query = f'[out:json][timeout:120];area["name"="Laguna"]["admin_level"="4"]["boundary"="administrative"]->.a;{OVERPASS[key]}out center tags;'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_request("https://overpass-api.de/api/interpreter",
                                            urllib.parse.urlencode(dict(data=query)).encode()), indent=1))
    elements = json.loads(path.read_text())["elements"]
    return [dict(id=f"{e['type']}/{e['id']}", name=e.get("tags", {}).get("name"),
                 lat=e.get("center", e).get("lat"), lon=e.get("center", e).get("lon")) for e in elements
            if e.get("tags", {}).get("name")]


def nominatim(query, cache, offline):
    if query in cache:
        return cache[query]
    if offline:
        return None
    results = _request("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        dict(q=query, format="jsonv2", limit=1, countrycodes="ph")))
    time.sleep(1.1)  # Nominatim usage policy: at most one request per second
    cache[query] = ({"lat": float(results[0]["lat"]), "lon": float(results[0]["lon"]),
                     "display_name": results[0].get("display_name", "")} if results else None)
    return cache[query]


def prepare(key, offline):
    register = REGISTERS[key]
    source = ROOT / register["raw"]
    lines = [line for page in PdfReader(source).pages for line in page.extract_text(extraction_mode="layout").splitlines()]
    clinics = parse_register(lines)
    clinics = clinics[clinics.province.eq("LAGUNA")].reset_index(drop=True)
    if clinics.empty:
        raise ValueError(f"No Laguna rows parsed from {source}")
    boundaries = json.loads((OUTPUT / "municipalities.geojson").read_text())["features"]
    shapes = {f["properties"]["shapeName"]: shape(f["geometry"]) for f in boundaries}
    clinics["municipality_name"] = clinics.municipality.map(lambda name: boundary_name(name, list(shapes)))
    clinics["barangay"] = clinics.street.map(barangay_name)
    town = {name: name.replace("City of ", "").replace(" City", "") for name in shapes}

    cache = json.loads(NOMINATIM_CACHE.read_text()) if NOMINATIM_CACHE.exists() else {}
    legacy = ROOT / "data/raw/dialysis/nominatim_cache.json"
    if legacy.exists():
        cache = {**json.loads(legacy.read_text()), **cache}
    barangay_points = {}
    try:
        for index, row in clinics.iterrows():
            if not isinstance(row.barangay, str) or not row.barangay:
                continue
            found = nominatim(f"{row.barangay.title()}, {town[row.municipality_name]}, Laguna, Philippines", cache, offline)
            # Keep a geocode only when it falls inside the clinic's own municipality boundary.
            if found and shapes[row.municipality_name].buffer(.005).contains(Point(found["lon"], found["lat"])):
                barangay_points[index] = found
    finally:
        NOMINATIM_CACHE.parent.mkdir(parents=True, exist_ok=True)
        NOMINATIM_CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False))

    centres = {name: polygon.representative_point() for name, polygon in shapes.items()}
    anchors = {index: (barangay_points[index]["lat"], barangay_points[index]["lon"]) if index in barangay_points
               else (centres[row.municipality_name].y, centres[row.municipality_name].x) for index, row in clinics.iterrows()}
    matches = match_osm(clinics, osm_features(key, register, offline), anchors)
    rows = []
    for index, row in clinics.iterrows():
        if index in matches:
            feature, precision = matches[index], "osm"
            lat, lon, located = feature["lat"], feature["lon"], f"OpenStreetMap {feature['id']} ({feature['name']})"
        elif index in barangay_points:
            point, precision = barangay_points[index], "barangay"
            lat, lon, located = point["lat"], point["lon"], f"Nominatim: {point['display_name']}"
        else:
            point, precision = centres[row.municipality_name], "municipality"
            lat, lon, located = point.y, point.x, "Representative point of the municipal boundary"
        rows.append({**row.to_dict(), "latitude": round(lat, 6), "longitude": round(lon, 6),
                     "location_precision": precision, "location_label": LOCATION_PRECISION[precision],
                     "location_source": located, "register_id": register["register_id"]})
    table = pd.DataFrame(rows)
    table.to_csv(OUTPUT / f"{register['output']}.csv", index=False)
    notes = dict(register_id=register["register_id"], register_title=register["title"], register_url=register["url"],
                 register_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), province="Laguna", clinics=len(table),
                 location_precision=table.location_precision.value_counts().to_dict(),
                 osm_source="OpenStreetMap contributors (ODbL), Overpass API query of Laguna",
                 geocoder="OpenStreetMap Nominatim, barangay-level queries",
                 limitations="Accreditation does not establish current capacity, schedule, cost, test capability or acceptance "
                             "of new patients. Approximate locations mark a barangay or municipality centre, not the building.")
    (OUTPUT / f"{register['output']}_notes.json").write_text(json.dumps(notes, indent=2, ensure_ascii=False))
    print(f"{key}: {len(table)} Laguna clinics -> {register['output']}.csv; precision {notes['location_precision']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--register", choices=[*REGISTERS, "all"], default="all")
    parser.add_argument("--offline", action="store_true", help="Use saved OSM features and cached geocodes only")
    arguments = parser.parse_args()
    for key in (REGISTERS if arguments.register == "all" else [arguments.register]):
        prepare(key, arguments.offline)


if __name__ == "__main__":
    main()
