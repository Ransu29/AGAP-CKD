"""Kidney-function helpers used by the synthetic data generator."""
from __future__ import annotations

import numpy as np


def ckd_epi_2021(scr_mg_dl, age, female):
    """eGFR (mL/min/1.73 m^2) from the race-free CKD-EPI 2021 creatinine equation.

    Inker LA et al., N Engl J Med 2021;385:1737-1749.
    Accepts scalars or array-likes.
    """
    scr = np.asarray(scr_mg_dl, dtype=float)
    age = np.asarray(age, dtype=float)
    female = np.asarray(female, dtype=bool)

    kappa = np.where(female, 0.7, 0.9)
    alpha = np.where(female, -0.241, -0.302)
    ratio = scr / kappa

    egfr = (
        142.0
        * np.minimum(ratio, 1.0) ** alpha
        * np.maximum(ratio, 1.0) ** -1.200
        * 0.9938 ** age
        * np.where(female, 1.012, 1.0)
    )
    return egfr


def creatinine_for_egfr(egfr, age, female):
    """Serum creatinine (mg/dL) that gives the target eGFR under CKD-EPI 2021 (exact inverse)."""
    age = np.asarray(age, dtype=float)
    female = np.asarray(female, dtype=bool)
    kappa = np.where(female, .7, .9)
    alpha = np.where(female, -.241, -.302)
    scale = 142 * .9938 ** age * np.where(female, 1.012, 1)
    ratio = np.asarray(egfr, dtype=float) / scale
    return kappa * np.where(ratio < 1, ratio ** (-1 / 1.2), ratio ** (1 / alpha))


def abnormal_screen(egfr, uacr, egfr_threshold=60.0, uacr_threshold=30.0):
    """Outcome Y: 1 if eGFR < threshold or uACR >= threshold, else 0."""
    egfr = np.asarray(egfr, dtype=float)
    uacr = np.asarray(uacr, dtype=float)
    return ((egfr < egfr_threshold) | (uacr >= uacr_threshold)).astype(int)


def observed_screen_label(egfr, uacr, egfr_threshold=60.0, uacr_threshold=30.0):
    """1 = any observed abnormal component, 0 = both normal, NaN = unknown."""
    egfr, uacr = np.broadcast_arrays(np.asarray(egfr, float), np.asarray(uacr, float))
    positive = (np.isfinite(egfr) & (egfr < egfr_threshold)) | (np.isfinite(uacr) & (uacr >= uacr_threshold))
    negative = np.isfinite(egfr) & np.isfinite(uacr) & (egfr >= egfr_threshold) & (uacr < uacr_threshold)
    return np.where(positive, 1.0, np.where(negative, 0.0, np.nan))


def measurement_factor(rng, cv, size):
    """Mean-one log-normal within-person variability factor with coefficient of variation ``cv``."""
    sigma = np.sqrt(np.log1p(cv ** 2))
    return np.exp(rng.normal(-sigma ** 2 / 2, sigma, size))
