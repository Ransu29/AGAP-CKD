"""Download PSA 2024 Census of Population tables for Laguna from OpenSTAT and derive adults per municipality.

    python scripts/collect_psa_population.py

Two OpenSTAT (PXWeb) tables, saved unmodified to data/raw/psa/openstat/ with a manifest (URL, query,
retrieval time, SHA-256); existing files are reused, never overwritten:

- 0041A6DTPH3: total population by province, city, municipality and barangay, CALABARZON, 1 July 2024.
- 0201A6DPAG0: household population by 5-year age group, region, province and HUC, 2024.

PSA does not publish municipal age groups, so adults per municipality = the municipality's 2024 total
population x Laguna's 18+ share of household population (ages 18-19 = 2/5 of the 15-19 band). Writes
two small committed tables to data/processed/public/laguna/:

- municipal_population_psa2024.csv: total population and estimated adults (18+) per municipality.
- age_structure_psa2024.csv: Laguna's adult shares in the PRD v3 age groups (age-standardisation weights).
- barangays_psa2024.csv: barangay names and 2024 population per municipality (field tablet check records).
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import urllib.request

import pandas as pd

from agap.analyst import display_name
from agap.config import ROOT, load_config

API = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/1A/PO_2024"
TABLES = {
    "popcen2024_calabarzon_total_population.csv": ("0041A6DTPH3.px", [{"code": "Parameter", "selection": {"filter": "item", "values": ["0"]}}]),
    "popcen2024_household_population_by_age.csv": ("0201A6DPAG0.px", []),
}
RAW = ROOT / "data/raw/psa/openstat"
OUT = ROOT / "data/processed/public/laguna"
ENCODING = "cp1252"  # OpenSTAT CSV output (e.g. "Biñan")
AGE_BANDS = {"15 - 19": (15, 19), "20 - 24": (20, 24), "25 - 29": (25, 29), "30 - 34": (30, 34), "35 - 39": (35, 39),
             "40 - 44": (40, 44), "45 - 49": (45, 49), "50 - 54": (50, 54), "55 - 59": (55, 59), "60 - 64": (60, 64),
             "65 - 69": (65, 69), "70 - 74": (70, 74), "75 - 79": (75, 79), "80 - 84": (80, 84), "85 and over": (85, 120)}


def download():
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for name, (table, query) in TABLES.items():
        path = RAW / name
        if not path.exists():
            body = json.dumps({"query": query, "response": {"format": "csv"}}).encode()
            request = urllib.request.Request(f"{API}/{table}", data=body, method="POST",
                                             headers={"Content-Type": "application/json", "User-Agent": "agap-ckd/1.0"})
            with urllib.request.urlopen(request, timeout=300) as response:
                path.write_bytes(response.read())
            manifest[name] = dict(url=f"{API}/{table}", query=query, retrieved_at_utc=datetime.now(timezone.utc).isoformat())
        manifest.setdefault(name, dict(url=f"{API}/{table}", query=query))["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest["source"] = "Philippine Statistics Authority, 2024 Census of Population (POPCEN), OpenSTAT"
    manifest_path.write_text(json.dumps(manifest, indent=2))


def laguna_municipalities():
    table = pd.read_csv(RAW / "popcen2024_calabarzon_total_population.csv", encoding=ENCODING)
    table.columns = ["location", "population"]
    depth = table.location.str.len() - table.location.str.lstrip(".").str.len()
    names = table.location.str.lstrip(".")
    start = table.index[(depth == 4) & names.eq("Laguna")][0]
    end = table.index[(depth == 4) & (table.index > start)]
    block = table.loc[start:(end[0] - 1 if len(end) else table.index[-1])]
    municipalities = block[depth.loc[block.index] == 6]
    barangay_rows, town = [], None
    for index in block.index:
        if depth[index] == 6:
            town = names[index]
        elif depth[index] == 8:
            barangay_rows.append(dict(psa_name=town, barangay=names[index], total_population=int(table.population[index])))
    return (int(block.population.iloc[0]),
            pd.DataFrame(dict(psa_name=names.loc[municipalities.index].to_numpy(),
                              total_population=municipalities.population.astype(int).to_numpy())),
            pd.DataFrame(barangay_rows))


def laguna_adults_by_age(cfg):
    """Laguna household population 18+ by single year (bands spread evenly), from the 2024 age table."""
    table = pd.read_csv(RAW / "popcen2024_household_population_by_age.csv", encoding=ENCODING)
    laguna = table[table["Geographic Location"].str.lstrip(".").eq("Laguna")].set_index("Age Group")["Both Sexes"]
    ages = {}
    for band, (low, high) in AGE_BANDS.items():
        span = list(range(low, high + 1))
        for age in span:
            if age >= 18:
                ages[age] = laguna[band] / len(span)
    return ages, int(laguna["All Ages"])


def main():
    cfg = load_config()
    download()
    province_total, municipalities, barangays = laguna_municipalities()
    if municipalities.total_population.sum() != province_total:
        raise ValueError("Laguna municipal totals do not add up to the province total")
    ages, household_total = laguna_adults_by_age(cfg)
    adult_share = sum(ages.values()) / household_total
    geography = json.loads((OUT / "municipalities.geojson").read_text())
    shapes = {display_name(f["properties"]["shapeName"]): f["properties"]["shapeName"] for f in geography["features"]}
    municipalities["municipality"] = municipalities.psa_name.map(lambda n: shapes.get(display_name(n)))
    if municipalities.municipality.isna().any():
        raise ValueError(f"Unmatched PSA names: {municipalities.psa_name[municipalities.municipality.isna()].tolist()}")
    municipalities["adults_18plus"] = (municipalities.total_population * adult_share).round().astype(int)
    municipalities[["municipality", "psa_name", "total_population", "adults_18plus"]].to_csv(
        OUT / "municipal_population_psa2024.csv", index=False)
    # Barangay names for the field tablet's check record (never used in the score).
    barangays["municipality"] = barangays.psa_name.map(dict(zip(municipalities.psa_name, municipalities.municipality)))
    barangays[["municipality", "barangay", "total_population"]].to_csv(OUT / "barangays_psa2024.csv", index=False)
    rc = cfg["simulator"]["risk_check"]
    total = sum(ages.values())
    shares = [sum(n for age, n in ages.items() if low <= age <= high) / total for low, high in rc["age_group_bounds"]]
    pd.DataFrame(dict(age_group=rc["age_groups"], share=[round(s, 5) for s in shares])).to_csv(
        OUT / "age_structure_psa2024.csv", index=False)
    (OUT / "population_psa2024_notes.json").write_text(json.dumps(dict(
        source="Philippine Statistics Authority, 2024 Census of Population (reference date 1 July 2024), via OpenSTAT tables "
               "0041A6DTPH3 (municipal totals) and 0201A6DPAG0 (household population by age, province)",
        method=f"Adults 18+ per municipality = 2024 total population x Laguna's 18+ share of household population "
               f"({adult_share:.4f}); ages 18-19 are 2/5 of the 15-19 band. Age-group shares from the same Laguna table.",
        caveat="PSA publishes age groups by province, not by municipality, so every municipality gets Laguna's adult share.",
        province_total_population=province_total, adult_share=round(adult_share, 5),
        script="scripts/collect_psa_population.py"), indent=2, ensure_ascii=False))
    print(municipalities.to_string(index=False))
    print(f"Laguna {province_total:,}; adult share {adult_share:.4f}; adults {municipalities.adults_18plus.sum():,}")
    print(dict(zip(rc["age_groups"], [round(s, 4) for s in shares])))


if __name__ == "__main__":
    main()
