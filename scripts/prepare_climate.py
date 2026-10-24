"""Prepare complete ERA5-Land baseline/replay archives for the climate demo."""
import argparse

from agap.climate.history import prepare_history
from agap.climate.integration import BASELINE_YEARS
from agap.config import ROOT, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-start", type=int, default=BASELINE_YEARS[0])
    parser.add_argument("--baseline-end", type=int, default=BASELINE_YEARS[1])
    parser.add_argument("--config", default="config/climate.yaml", help="climate.source: arco or cds_grib")
    args = parser.parse_args()
    source = load_config(args.config)["climate"].get("source", "cds_grib")
    daily, exposure, _ = prepare_history(ROOT, args.baseline_start, args.baseline_end, source)
    print(f"Climate source: {source}")
    print(f"Prepared {len(daily):,} cell-days and {int(exposure.complete.sum()):,} complete cutoff windows")


if __name__ == "__main__":
    main()
