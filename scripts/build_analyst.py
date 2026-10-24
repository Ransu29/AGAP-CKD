"""Build the PRD v3 analyst view's data: area totals, climate context and model quality.

    make analyst            # or: python scripts/build_analyst.py

Needs the frozen risk-level run in outputs/ (make triage) and the processed ERA5-Land daily table
(make prepare-climate). Uses the committed PSA 2024 population tables (scripts/collect_psa_population.py),
WorldPop municipal age mix (scripts/build_municipal_adults.py) and daily heat index
(scripts/collect_heat_index.py). Writes git-ignored JSON to outputs/analyst/, which api/main.py serves.
"""
from __future__ import annotations

import json
import subprocess

import joblib
import pandas as pd

from agap.analyst import climate_context, load_adults, load_age_weights, model_quality, overview, simulate_checks
from agap.config import ROOT, load_config
from agap.experiment import fingerprint

OUTPUTS = ROOT / "outputs"
LAGUNA = ROOT / "data/processed/public/laguna"


def main():
    cfg = load_config()
    bundle = joblib.load(OUTPUTS / "model_clinical.joblib")
    if not isinstance(bundle, dict) or "model" not in bundle:
        raise SystemExit("outputs/model_clinical.joblib is not the PRD v3 risk-level model; run `make triage` first")
    cutoffs = json.loads((OUTPUTS / "triage_cutoffs.json").read_text())
    adults = load_adults(LAGUNA)
    weights = load_age_weights(LAGUNA)
    directory = OUTPUTS / "analyst"
    directory.mkdir(parents=True, exist_ok=True)

    checks = simulate_checks(cfg, adults, bundle["model"], cutoffs)
    # Kept so the API can add checks recorded by the channels without re-simulating.
    checks.to_parquet(directory / "checks.parquet", index=False)
    area = overview(checks, adults, cfg, weights)
    quality = model_quality(OUTPUTS, cfg, ROOT / "config/parameter_register.yaml", bundle["model"])
    # The map comes from today's config and code; the model it scores with is the frozen run.
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    area["built_with"] = dict(config_fingerprint=fingerprint(cfg), git_commit=commit or None, seed=cfg["seed"])
    area["model_run"] = quality["run"]
    (directory / "overview.json").write_text(json.dumps(area, indent=1, ensure_ascii=False))
    (directory / "model_quality.json").write_text(json.dumps(quality, indent=1, ensure_ascii=False))

    daily = pd.read_parquet(ROOT / "data/processed/climate/laguna/daily.parquet")
    heat = pd.read_csv(LAGUNA / "heat_index_daily_era5land.csv")
    cells = pd.read_csv(LAGUNA / "municipal_era5_cells.csv")
    climate = climate_context(daily, heat, cells, cfg)
    (directory / "climate.json").write_text(json.dumps(climate, indent=1, ensure_ascii=False))

    summary = area["summary"]
    print(f"Checks {summary['checks']:,} · coverage {summary['coverage_pct']}% · Medium/High {summary['medium_high_share']}% "
          f"· awareness gap {summary['awareness_gap']}%")
    print(f"Faded areas: {sum(m['faded'] for m in area['municipalities'])} · hidden: {sum(m['hidden'] for m in area['municipalities'])}")
    print(f"Floor effect: {quality['floor']} · climate {climate['period']['label']}, {len(climate['municipalities'])} municipalities")
    print("Calamba climate:", [(m["label"], m["hot_days"], m["peak_heat_index_c"]) for m in climate["municipalities"]["Calamba"]["series"]])


if __name__ == "__main__":
    main()
