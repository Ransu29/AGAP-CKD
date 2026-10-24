"""Build the citizen facility list from the PhilHealth YAKAP register extract.

    python scripts/build_citizen_facilities.py

Source: data/processed/public/laguna/clinic_verification_queue.csv, extracted from PhilHealth's "List of
Accredited YAKAP Clinics for CY 2026 Updated as of September 30, 2026" (Laguna rows). The register has no
municipality column, so a facility is placed in a municipality only when the town's name appears in the
facility name; barangay-named units whose town cannot be told from the name are left out rather than
guessed. Only hospitals and public health centers are kept (PRD v3: general hospitals and health centers);
lying-in, maternity, rehabilitation and stand-alone diagnostic clinics are dropped.

Every entry is "Not yet verified, call ahead" and "Can do kidney tests: Unknown" (PRD v3 facility list).
Writes data/processed/public/laguna/facilities_yakap.csv.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from agap.analyst import display_name
from agap.config import ROOT

LAGUNA = ROOT / "data/processed/public/laguna"
EXCLUDE = re.compile(r"LYING|MATERNITY|REHABILITATION|DIAGNOSTIC LABORATORY|INDUSTRIAL|PHARMACY|CARD CLINICS|MEDICINA DE MERCADO")
HEALTH_CENTER = re.compile(r"RURAL HEALTH|\bRHU\b|HEALTH OFFICE|HEALTH CENTER|HEALTH UNIT")
HOSPITAL = re.compile(r"HOSPITAL|MEDICAL CENTER")
# Abbreviations and spellings in the register, mapped to the boundary file's short names.
ALIASES = {"STA. MARIA": "Santa Maria", "STA MARIA": "Santa Maria", "STA. ROSA": "Santa Rosa", "STA ROSA": "Santa Rosa",
           "CANLUBANG": "Calamba", "BALIBAGO": "Santa Rosa"}


KEEP_UPPER = {"RHU", "II", "I", "LPH", "UP", "UPH", "CHO", "INC", "INC."}
SMALL = {"of", "and", "the", "de"}


def display_case(name):
    """Register names are upper case; show them in title case, keeping acronyms."""
    words = []
    for index, word in enumerate(name.split()):
        if word.strip("(),.").upper() in KEEP_UPPER:
            words.append(word.upper() if word.upper() not in {"INC", "INC."} else word.capitalize())
        elif index and word.lower() in SMALL:
            words.append(word.lower())
        else:
            words.append("-".join(part[:1].upper() + part[1:].lower() for part in word.split("-")))
    return " ".join(words)


def facility_type(name):
    if EXCLUDE.search(name):
        return None
    if HEALTH_CENTER.search(name):
        return "Health center"
    if HOSPITAL.search(name):
        return "Hospital"
    return None


def municipality_for(name, towns):
    """The one town named in the facility name, or None when none or several are named."""
    upper = name.upper()
    found = {short for short in towns if re.search(rf"\b{re.escape(short.upper())}\b", upper)}
    found |= {town for alias, town in ALIASES.items() if alias in upper}
    return found.pop() if len(found) == 1 else None


def main():
    geography = json.loads((LAGUNA / "municipalities.geojson").read_text())
    towns = {display_name(f["properties"]["shapeName"]): f["properties"]["shapeName"] for f in geography["features"]}
    register = pd.read_csv(LAGUNA / "clinic_verification_queue.csv")
    rows = []
    for record in register.itertuples(index=False):
        name = " ".join(str(record.facility_name).replace('"', " ").split())
        kind = facility_type(name.upper())
        town = municipality_for(name, towns)
        if kind and town:
            rows.append(dict(name=display_case(name).rstrip(" ,").replace(", INC", ", Inc"),
                             type=kind, municipality=towns[town], kidney_tests="Unknown",
                             verification="Not yet verified, call ahead",
                             source=f"PhilHealth YAKAP accredited clinics CY 2026 (as of 30 Sep 2026), p. {record.source_page}"))
    table = pd.DataFrame(rows).drop_duplicates("name")
    # Public health centers first (usually free), then hospitals; alphabetical within each.
    table = table.sort_values(["municipality", "type", "name"], key=lambda s: s.map({"Health center": 0, "Hospital": 1}).fillna(s) if s.name == "type" else s)
    table.to_csv(LAGUNA / "facilities_yakap.csv", index=False)
    missing = sorted(set(towns.values()) - set(table.municipality))
    print(f"{len(table)} facilities in {table.municipality.nunique()} municipalities; none matched in: {missing}")


if __name__ == "__main__":
    main()
