"""SIM-04: calibrate the simulator's diabetes trait prevalence to FNRI 2023 NNS.

The FNRI 2023 National Nutrition Summit part 2 deck reports measured high fasting
blood glucose (>=126 mg/dL): 7.5% among adults 20-59 (n=40,877) and 17.2% among
older persons 60+ (n=13,617). Their sample-weighted combination, 9.9% among adults
20+, is the calibration target. This is a measured biochemical proxy, not the
simulator's self-reported "told by a doctor" trait; only the age-averaged marginal
is matched. The age slope, the diabetes-hypertension association and every other
generator stay at their registered (assumed) values. Hypertension results are not
part of this deck, so htn_intercept is not calibrated here.

Method: solve dm_intercept by bisection so the prevalence implied by the generator,
averaged over the collected Laguna WorldPop adult age distribution with the same
uniform-within-band age draws the simulator uses, equals the target.
"""
from __future__ import annotations

import numpy as np

from agap.config import ROOT, load_config
from agap.data.geography import make_geography

TARGET = (40_877 * 7.5 + 13_617 * 17.2) / (40_877 + 13_617) / 100


def age_weights(demographics):
    """Expand WorldPop 5-year bands into single adult ages, matching the simulator's draws."""
    sim = load_config("config/params.yaml")["simulator"]
    weights = {}
    for age_start, count in demographics.groupby("age_start").adult_count.sum().items():
        if age_start == 15:  # adults are ages 18-19: 2 of the band's 5 years
            weights[18] = weights.get(18, 0.0) + count / 2
            weights[19] = weights.get(19, 0.0) + count / 2
        elif age_start == sim["oldest_band_start"]:  # open band drawn uniformly over 80..95
            for age in range(age_start, sim["oldest_band_max_age"] + 1):
                weights[age] = weights.get(age, 0.0) + count / (sim["oldest_band_max_age"] + 1 - age_start)
        else:
            for age in range(age_start, age_start + 5):
                weights[age] = weights.get(age, 0.0) + count / 5
    ages = np.array(sorted(weights))
    return ages, np.array([weights[age] for age in ages], float) / sum(weights.values())


def implied_prevalence(intercept, ages, weights, slope):
    return float(np.sum(weights / (1 + np.exp(-(intercept + slope * (ages - 40))))))


def solve(target, ages, weights, slope):
    low, high = -12.0, 4.0
    for _ in range(200):
        middle = (low + high) / 2
        if implied_prevalence(middle, ages, weights, slope) < target:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def main():
    cfg = load_config("config/public.yaml")
    _, demographics, _, _ = make_geography(cfg, ROOT)
    ages, weights = age_weights(demographics)
    slope = cfg["simulator"]["traits"]["dm_log_odds_per_year"]
    intercept = solve(TARGET, ages, weights, slope)
    print(f"Calibration target: FNRI 2023 NNS high fasting blood glucose, adults 20+ = {TARGET:.4f}")
    print(f"Laguna WorldPop adult age distribution: {len(ages)} ages, {demographics.adult_count.sum():,.0f} adults")
    print(f"solved simulator.traits.dm_intercept = {intercept:.4f} (age slope stays {slope})")
    print(f"implied prevalence at the solved intercept: {implied_prevalence(intercept, ages, weights, slope):.4f}")
    htn = cfg["simulator"]["traits"]
    htn_prevalence = implied_prevalence(htn["htn_intercept"], ages, weights, htn["htn_log_odds_per_year"])
    print(f"unmodified htn_intercept {htn['htn_intercept']} implies hypertension prevalence {htn_prevalence:.4f} (stays assumed: "
          "the FNRI part 2 deck reports no blood pressure results)")


if __name__ == "__main__":
    main()
