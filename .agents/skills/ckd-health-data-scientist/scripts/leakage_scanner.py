#!/usr/bin/env python3
"""Leakage Scanner for AGAP-CKD.

Verifies that proposed feature sets or datasets do not contain forbidden
variables (e.g., eGFR, creatinine, uACR, follow-up outcomes, hidden traits).
Enforces zero-leakage constraints declared in config/params.yaml.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import yaml

# Find repository root
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = REPO_ROOT / "config" / "params.yaml"


def load_forbidden_features(config_path: Path = DEFAULT_CONFIG) -> list[str]:
    """Load forbidden feature list from params.yaml."""
    if not config_path.is_file():
        # Fallback if config is missing
        return [
            "creatinine", "egfr", "uacr", "y_true",
            "creatinine_90d", "uacr_90d", "egfr_90d", "abnormal_90d",
            "persistent_abnormal", "transient_abnormal",
        ]
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("models", {}).get("forbidden_features", [])


def check_features(features: Iterable[str], forbidden: Iterable[str]) -> list[str]:
    """Return any features that match forbidden names (case-insensitive)."""
    forbidden_set = {f.strip().lower() for f in forbidden}
    return sorted({f.strip() for f in features if f.strip().lower() in forbidden_set})


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check feature names or dataset columns against AGAP-CKD leakage rules."
    )
    parser.add_argument(
        "--features",
        type=str,
        help="Comma-separated list of feature names to inspect.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Path to CSV or text file containing column headers / feature names.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to params.yaml (defaults to repository root config/params.yaml).",
    )
    args = parser.parse_args()

    forbidden = load_forbidden_features(args.config)

    features_to_check: list[str] = []
    if args.features:
        features_to_check.extend([f.strip() for f in args.features.split(",") if f.strip()])

    if args.file:
        if not args.file.is_file():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            return 2
        # Inspect first line for CSV header, or line-by-line for text
        with open(args.file, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            if "," in first_line:
                features_to_check.extend([c.strip() for c in first_line.split(",") if c.strip()])
            else:
                features_to_check.append(first_line)
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        features_to_check.append(stripped)

    if not features_to_check:
        print("No features provided. Use --features or --file.", file=sys.stderr)
        parser.print_help()
        return 2

    violations = check_features(features_to_check, forbidden)
    if violations:
        print(f"[FAIL] Label leakage detected! Forbidden features found: {violations}", file=sys.stderr)
        print("These variables define or reflect the outcome and must NEVER be model inputs.", file=sys.stderr)
        return 1

    print(f"[PASS] All {len(features_to_check)} features passed leakage audit. No forbidden features detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
