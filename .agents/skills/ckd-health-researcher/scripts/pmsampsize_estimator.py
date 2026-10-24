#!/usr/bin/env python3
"""Sample Size Estimator for CKD Prediction Models (Riley et al. 2020 criteria).

Calculates minimum sample size and candidate parameter limits for clinical prediction
models with binary outcomes (e.g., initial abnormal screening flag), moving beyond
the outdated '10 events per variable' rule.

References:
  Riley RD, et al. Calculating the sample size required for developing a clinical
  prediction model. BMJ 2020;368:m441.
"""
from __future__ import annotations

import argparse
import math
import sys


def norm_ppf(p: float) -> float:
    """Rational approximation for inverse normal CDF (probit)."""
    if not (0.0 < p < 1.0):
        raise ValueError("Probability p must be in (0, 1).")
    # Acklam's approximation
    a = [-3.969683028665376e+01, 2.204091104255533e+02, -2.755581241083242e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]

    q = min(p, 1.0 - p)
    if q > 0.02425:
        r = q - 0.5
        r2 = r * r
        res = (((((a[0]*r2 + a[1])*r2 + a[2])*r2 + a[3])*r2 + a[4])*r2 + a[5])*r / \
              (((((b[0]*r2 + b[1])*r2 + b[2])*r2 + b[3])*r2 + b[4])*r2 + 1.0)
    else:
        r = math.sqrt(-2.0 * math.log(q))
        res = (((((c[0]*r + c[1])*r + c[2])*r + c[3])*r + c[4])*r + c[5]) / \
              ((((d[0]*r + d[1])*r + d[2])*r + d[3])*r + 1.0)
    return res if p > 0.5 else -res


def estimate_sample_size(
    c_statistic: float,
    prevalence: float,
    parameters: int,
    shrinkage: float = 0.90,
    margin_of_error: float = 0.05,
) -> dict[str, float]:
    """Calculate sample size for binary outcome prediction model."""
    phi = prevalence
    p = parameters
    s = shrinkage

    # Maximum Cox-Snell R2
    ln_l_null = phi * math.log(phi) + (1.0 - phi) * math.log(1.0 - phi)
    r2_max = 1.0 - math.exp(2.0 * ln_l_null)

    # Approximate apparent Cox-Snell R2 from anticipated C-statistic
    # Standard deviation of linear predictor from C-statistic
    sigma_lp = math.sqrt(2.0) * norm_ppf(c_statistic)
    var_lp = sigma_lp ** 2
    # R2 on continuous latent scale approx
    r2_latent = var_lp / (var_lp + (math.pi ** 2 / 3.0))
    r2_cs = min(r2_latent * r2_max, 0.99 * r2_max)

    # Criterion 1: Shrinkage factor S (overfitting / optimism control)
    denom_1 = (s - 1.0) * math.log(1.0 - (r2_cs / s))
    n1 = p / denom_1 if denom_1 > 0 else 0

    # Criterion 2: Margin of error in overall risk (intercept precision)
    # 95% CI width <= 2 * margin_of_error
    n2 = ((1.96 / margin_of_error) ** 2) * ((1.0 - phi) / phi)

    # Criterion 3: Small difference in apparent vs adjusted Nagelkerke R2 (approx 0.05)
    r2_nagelkerke = r2_cs / r2_max
    denom_3 = -math.log(1.0 - (r2_cs / (r2_nagelkerke - 0.05 * r2_max))) if (r2_nagelkerke - 0.05 * r2_max) > 0 else 0.001
    n3 = p / max(0.0001, denom_3)

    n_required = math.ceil(max(n1, n2, n3))
    events_required = math.ceil(n_required * phi)
    epv = events_required / p if p > 0 else 0.0

    return {
        "n_required": n_required,
        "events_required": events_required,
        "events_per_parameter": round(epv, 2),
        "n_criterion_1_shrinkage": math.ceil(n1),
        "n_criterion_2_intercept": math.ceil(n2),
        "n_criterion_3_r2_diff": math.ceil(n3),
        "cox_snell_r2_est": round(r2_cs, 4),
        "max_cox_snell_r2": round(r2_max, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Estimate minimum sample size for clinical prediction model (Riley et al. 2020)."
    )
    parser.add_argument("--c-statistic", type=float, required=True, help="Expected AUROC / C-statistic (e.g., 0.80).")
    parser.add_argument("--prevalence", type=float, required=True, help="Outcome prevalence in target cohort (e.g., 0.12).")
    parser.add_argument("--parameters", type=int, required=True, help="Number of candidate model parameters (including splines/dummies).")
    parser.add_argument("--shrinkage", type=float, default=0.90, help="Target shrinkage / 1 - optimism (default: 0.90).")
    parser.add_argument("--margin-of-error", type=float, default=0.05, help="Precision margin of error for overall risk (default: 0.05).")
    args = parser.parse_args()

    if not (0.5 < args.c_statistic < 1.0):
        print("Error: c-statistic must be between 0.5 and 1.0", file=sys.stderr)
        return 2
    if not (0.0 < args.prevalence < 1.0):
        print("Error: prevalence must be between 0.0 and 1.0", file=sys.stderr)
        return 2

    res = estimate_sample_size(
        c_statistic=args.c_statistic,
        prevalence=args.prevalence,
        parameters=args.parameters,
        shrinkage=args.shrinkage,
        margin_of_error=args.margin_of_error,
    )

    print("\n--- Riley Criteria Sample Size Estimation ---")
    print(f"Target Outcome Prevalence:  {args.prevalence:.1%}")
    print(f"Expected AUROC:             {args.c_statistic:.2f}")
    print(f"Candidate Parameters (p):   {args.parameters}")
    print(f"Target Shrinkage (S):       {args.shrinkage:.2f}")
    print("-" * 45)
    print(f"Criterion 1 (Shrinkage S >= {args.shrinkage}):       N = {res['n_criterion_1_shrinkage']}")
    print(f"Criterion 2 (Intercept Margin of Error <= {args.margin_of_error}): N = {res['n_criterion_2_intercept']}")
    print(f"Criterion 3 (R² Optimism Margin <= 0.05):    N = {res['n_criterion_3_r2_diff']}")
    print("=" * 45)
    print(f"TOTAL RECOMMENDED SAMPLE SIZE:  N = {res['n_required']}")
    print(f"EXPECTED EVENTS REQUIRED:       Events = {res['events_required']}")
    print(f"RESULTING EVENTS PER PARAMETER: EPV = {res['events_per_parameter']} (compare to obsolete 10 EPV rule)")
    print("=" * 45 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
