"""Derive the risk-check cohort's Laguna age structure and calibrate its outcome intercept (SIM-04).

1. Age-group and female shares: Laguna adults in the collected WorldPop 2020 age-sex rasters
   (census-based modelled counts; the PSA census tables are not in the repository). Five-year
   bands are split into single ages exactly as scripts/calibrate_traits.py does.
2. Outcome intercept: Monte Carlo bisection on a fixed-seed population so the measured abnormal
   kidney screen (eGFR < 60 or urine ACR >= 30, one visit, population level before routing) equals
   simulator.risk_check.target_prevalence (12.76%, Tran 2017, Long An, Vietnam).

Prints the values to copy into config/params.yaml; nothing is written automatically.
Requires the WorldPop rasters (make collect, then make prepare-public) for step 1.
"""
from __future__ import annotations

import argparse
import copy

import numpy as np

from agap.config import ROOT, load_config
from agap.data.geography import make_geography
from agap.simulate.risk_check import calibrate_intercept


def age_group_shares(demographics, cfg):
    sim, rc = cfg["simulator"], cfg["simulator"]["risk_check"]
    weights = {}
    for age_start, count in demographics.groupby("age_start").adult_count.sum().items():
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
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-age-structure", action="store_true", help="Keep the configured age shares")
    arguments = parser.parse_args()
    cfg = load_config("config/params.yaml")
    rc = cfg["simulator"]["risk_check"]
    if not arguments.skip_age_structure:
        public = load_config("config/public.yaml")
        _, demographics, _, _ = make_geography(public, ROOT)
        shares = age_group_shares(demographics, cfg)
        female = float(demographics.loc[demographics.female == 1, "adult_count"].sum() / demographics.adult_count.sum())
        print(f"Laguna WorldPop adults: {demographics.adult_count.sum():,.0f}")
        print("age_group_shares:", [round(value, 4) for value in shares], "for", rc["age_groups"])
        print(f"female_share: {female:.4f}")
        cfg = copy.deepcopy(cfg)
        rc = cfg["simulator"]["risk_check"]
        rc["age_group_shares"], rc["female_share"] = [round(v, 4) for v in shares], round(female, 4)
    level = cfg["triage"]["risk_level"]
    seed = cfg["seed"] * 1000 + level["seed_components"]["calibration"]
    intercept, share = calibrate_intercept(cfg, rc["target_prevalence"], level["calibration_n"], seed)
    print(f"outcome_intercept: {intercept:.4f} (measured abnormal-screen share {share:.4f}, target {rc['target_prevalence']})")


if __name__ == "__main__":
    main()
