"""Derive Laguna's adults per municipality, their age mix, and ERA5-Land cell weights from WorldPop.

    python scripts/build_municipal_adults.py   # needs the WorldPop 2020 age-sex rasters in data/raw/worldpop/

Writes two small committed tables to data/processed/public/laguna/ so that the analyst view and its
tests do not need the (untracked) rasters:

- municipal_adults.csv: adults (18+) per municipality, the PRD v3 age-group shares and the female share.
  Coverage in the analyst view is checks / adults. The PSA census tables are not in the repository,
  so WorldPop 2020 (CC BY 4.0) stands in for them.
- municipal_era5_cells.csv: each municipality's adults split across ERA5-Land 0.1-degree cells, used
  to population-weight the climate context.
"""
from __future__ import annotations

import json

import pandas as pd

from agap.config import ROOT, load_config
from agap.data.geography import make_geography

OUT = ROOT / "data/processed/public/laguna"


def age_group_shares(group, cfg):
    """Age-group shares of one municipality's adults, spreading each 5-year WorldPop band evenly over its ages."""
    sim, rc = cfg["simulator"], cfg["simulator"]["risk_check"]
    weights = {}
    for age_start, count in group.groupby("age_start").adult_count.sum().items():
        if age_start == 15:
            ages = [18, 19]
        elif age_start == sim["oldest_band_start"]:
            ages = list(range(age_start, sim["oldest_band_max_age"] + 1))
        else:
            ages = list(range(age_start, age_start + 5))
        for age in ages:
            weights[age] = weights.get(age, 0.0) + count / len(ages)
    total = sum(weights.values())
    return [sum(w for age, w in weights.items() if low <= age <= high) / total for low, high in rc["age_group_bounds"]]


def main():
    cfg = load_config("config/public.yaml")
    cells, demographics, _, _ = make_geography(cfg, ROOT)
    demographics = demographics.merge(cells[["h3", "municipality", "era5_cell"]], on="h3")
    rows = []
    for name, group in demographics.groupby("municipality", sort=True):
        shares = age_group_shares(group, cfg)
        rows.append(dict(municipality=name, adults=round(group.adult_count.sum()),
                         **{f"share_{label}": round(share, 5) for label, share in
                            zip(cfg["simulator"]["risk_check"]["age_groups"], shares)},
                         female_share=round(group.loc[group.female == 1, "adult_count"].sum() / group.adult_count.sum(), 5)))
    adults = pd.DataFrame(rows)
    weights = demographics.groupby(["municipality", "era5_cell"], as_index=False).adult_count.sum()
    weights["weight"] = weights.adult_count / weights.groupby("municipality").adult_count.transform("sum")
    OUT.mkdir(parents=True, exist_ok=True)
    adults.to_csv(OUT / "municipal_adults.csv", index=False)
    weights[["municipality", "era5_cell", "weight"]].round(5).to_csv(OUT / "municipal_era5_cells.csv", index=False)
    (OUT / "municipal_adults_notes.json").write_text(json.dumps(dict(
        source="WorldPop 2020 constrained age-sex rasters, 1 km (CC BY 4.0), clipped to Laguna (geoBoundaries ADM2/ADM3)",
        method="Adults 18+ = WorldPop 20+ bands plus 2/5 of the 15-19 band; each 1 km cell is assigned to an H3 cell and its "
               "municipality (border cells to the nearest polygon). Age-group shares spread each 5-year band evenly over its ages.",
        caveat="Modelled population estimates, not the PSA census. Coverage = checks / these adults.",
        script="scripts/build_municipal_adults.py",
        total_adults=int(adults.adults.sum())), indent=2, ensure_ascii=False))
    print(adults.to_string(index=False))
    print(f"Total adults: {adults.adults.sum():,}")


if __name__ == "__main__":
    main()
