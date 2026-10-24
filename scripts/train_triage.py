"""Retrain the PRD v3 risk-level model and benchmark it against the Thai simplified score.

    make triage            # or: python scripts/train_triage.py

Writes to outputs/ (git-ignored): model_clinical.joblib, triage_cutoffs.json, triage_coefficients.csv,
triage_benchmark.csv, triage_prevalence_sensitivity.csv, validation_features.csv (model inputs only,
for the leakage scanner), validation_labels.csv, and triage_dca_model.csv / triage_dca_thai.csv
(y_true, y_prob inputs for decision_curve.py). The method is documented in
notebooks/03_retrain_prd_v3_model.ipynb.
"""
from __future__ import annotations

import json
import subprocess

from agap.config import ROOT, load_config
from agap.triage import prevalence_sensitivity, save_artifacts, train_and_evaluate


def main():
    cfg = load_config()
    result = train_and_evaluate(cfg)
    sensitivity = prevalence_sensitivity(result["model"], result["cutoffs"], cfg)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    save_artifacts(result, cfg, sensitivity, ROOT / "outputs", commit or None)
    print(result["benchmark"].round(3).to_string(index=False))
    print(json.dumps(result["cutoffs"], indent=2))


if __name__ == "__main__":
    main()
