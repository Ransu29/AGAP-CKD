#!/usr/bin/env python3
"""Decision Curve Analysis (DCA) and Clinical Utility Evaluator for AGAP-CKD.

Computes decision-curve net benefit (Vickers & Elkin) across risk thresholds:
  Net Benefit = (TP / N) - (FP / N) * (pt / (1 - pt))
Compares the screening model against "Screen All" and "Screen None" strategies.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Sequence


def compute_net_benefit(
    y_true: Sequence[int],
    y_prob: Sequence[float],
    thresholds: Sequence[float],
) -> list[dict[str, float]]:
    n = len(y_true)
    if n == 0 or len(y_prob) != n:
        raise ValueError("y_true and y_prob must be non-empty and of equal length.")

    total_events = sum(y_true)
    prevalence = total_events / n

    results = []
    for pt in thresholds:
        if not (0.0 < pt < 1.0):
            continue

        odds = pt / (1.0 - pt)

        # Model evaluation at threshold pt
        tp = sum(1 for yt, yp in zip(y_true, y_prob) if yp >= pt and yt == 1)
        fp = sum(1 for yt, yp in zip(y_true, y_prob) if yp >= pt and yt == 0)
        flagged = tp + fp

        nb_model = (tp / n) - (fp / n) * odds
        nb_all = prevalence - (1.0 - prevalence) * odds
        nb_none = 0.0

        # Clinical metrics scaled per 1,000 people
        screened_per_1k = (flagged / n) * 1000
        cases_found_per_1k = (tp / n) * 1000
        unnecessary_saved_per_1k = max(0.0, (nb_model - nb_all) / odds * 1000)

        results.append({
            "threshold": round(pt, 4),
            "net_benefit_model": round(nb_model, 4),
            "net_benefit_all": round(nb_all, 4),
            "net_benefit_none": 0.0,
            "screened_per_1000": round(screened_per_1k, 1),
            "cases_found_per_1000": round(cases_found_per_1k, 1),
            "unnecessary_tests_saved_per_1000": round(unnecessary_saved_per_1k, 1),
        })

    return results


def format_table(results: list[dict[str, float]]) -> str:
    headers = [
        "Threshold",
        "NB (Model)",
        "NB (All)",
        "NB (None)",
        "Screens/1k",
        "Cases/1k",
        "Avoided Screens/1k",
    ]
    lines = [
        f"{headers[0]:<10} | {headers[1]:<11} | {headers[2]:<9} | {headers[3]:<9} | {headers[4]:<11} | {headers[5]:<9} | {headers[6]:<18}",
        "-" * 95,
    ]
    for r in results:
        lines.append(
            f"{r['threshold']:<10.3f} | {r['net_benefit_model']:<11.4f} | {r['net_benefit_all']:<9.4f} | "
            f"{r['net_benefit_none']:<9.4f} | {r['screened_per_1000']:<11.1f} | {r['cases_found_per_1000']:<9.1f} | "
            f"{r['unnecessary_tests_saved_per_1000']:<18.1f}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute Decision Curve Net Benefit for CKD screening models."
    )
    parser.add_argument("--file", type=Path, required=True, help="Path to CSV with predictions.")
    parser.add_argument("--y-true", type=str, default="y_true", help="Column name for binary ground truth (0/1).")
    parser.add_argument("--y-prob", type=str, default="y_prob", help="Column name for predicted probability [0, 1].")
    parser.add_argument(
        "--thresholds",
        type=str,
        default="0.02,0.05,0.10,0.15,0.20,0.25,0.30",
        help="Comma-separated decision thresholds (default: 0.02 to 0.30).",
    )
    parser.add_argument("--json", action="store_true", help="Output results in JSON format.")
    args = parser.parse_args()

    if not args.file.is_file():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        return 2

    thresholds = [float(t.strip()) for t in args.thresholds.split(",") if t.strip()]

    y_true: list[int] = []
    y_prob: list[float] = []

    with open(args.file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if args.y_true not in reader.fieldnames or args.y_prob not in reader.fieldnames:
            print(
                f"Error: Required columns '{args.y_true}' and '{args.y_prob}' not found in CSV headers: {reader.fieldnames}",
                file=sys.stderr,
            )
            return 2
        for row in reader:
            try:
                y_true.append(int(float(row[args.y_true])))
                y_prob.append(float(row[args.y_prob]))
            except ValueError:
                continue

    if not y_true:
        print("Error: No valid rows parsed from file.", file=sys.stderr)
        return 2

    results = compute_net_benefit(y_true, y_prob, thresholds)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("\nDecision Curve Analysis (DCA) - Clinical Net Benefit:")
        print(format_table(results))
        print(
            "\nInterpretation: A model is clinically useful at a given threshold if its Net Benefit (Model)"
            "\nexceeds both Net Benefit (All) and Net Benefit (None = 0.0)."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
