"""Command entry points share the implementation used by the local app."""
import argparse
import copy
import json
import time

import numpy as np
import pandas as pd

from agap.config import ROOT, load_config
from agap.experiment import STAGES, atomic_text, execute, fingerprint, input_checksums, run_path, source_hash


def completed_run(cfg):
    """NFR-05: an existing run of exactly this configuration, code and inputs with every stage complete.

    Seeds derive from the repetition number, so reusing a completed run never changes them.
    Anything incomplete, failed or from a different setup is run again.
    """
    directory = run_path(cfg)
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists() or not (directory / "metrics.csv").exists():
        return None
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get("config_hash") != fingerprint(cfg) or manifest.get("source_hash") != source_hash()
            or manifest.get("input_checksums") != input_checksums(cfg)
            or not all(manifest.get("stages", {}).get(stage) == "complete" for stage in STAGES)):
        return None
    return directory


def experiments(cfg):
    results = []
    for mechanism in ("MCAR", "MAR", "MNAR"):
        for heat_or in (1.0, 1.2, 1.5):
            for repetition in range(cfg["prototype"]["repetitions"]):
                trial = copy.deepcopy(cfg)
                trial["prototype"].update(mechanism=mechanism, heat_or=heat_or, repetition=repetition)
                directory = completed_run(trial)
                status = "reused" if directory else "ran"
                if directory is None:
                    directory = execute(trial, repetition=repetition, publish=False)
                metrics = pd.read_csv(directory / "metrics.csv")
                metrics = metrics[metrics.subgroup == "all"].copy()
                metrics["mechanism"], metrics["heat_or"], metrics["repetition"] = mechanism, heat_or, repetition
                results.append(metrics)
                print(f"{mechanism} OR={heat_or} rep={repetition}: {status} {directory}", flush=True)
    combined = pd.concat(results, ignore_index=True)
    destination = ROOT / "outputs/experiments" / f"{fingerprint(cfg)}-{source_hash()}"
    destination.mkdir(parents=True, exist_ok=True)
    combined.to_csv(destination / "replications.csv", index=False)
    rows = []
    for (mechanism, heat_or), group in combined.groupby(["mechanism", "heat_or"]):
        baseline = group[group.policy == "random"].set_index("repetition")
        for policy, subset in group.groupby("policy"):
            for metric in ("positives_detected", "positives_per_100_completed", "completion_coverage"):
                paired = (subset.set_index("repetition")[metric] - baseline[metric]).dropna()
                mean = paired.mean()
                sd = paired.std(ddof=1) if len(paired) > 1 else np.nan
                mcse = sd / np.sqrt(len(paired))
                rows.append(dict(mechanism=mechanism, heat_or=heat_or, policy=policy, metric=metric,
                                 mean_difference_from_random=mean, repetitions=len(paired),
                                 between_repetition_sd=sd, monte_carlo_se=mcse,
                                 mean_difference_mc95_low=mean - 1.96 * mcse,
                                 mean_difference_mc95_high=mean + 1.96 * mcse,
                                 repetition_q025=paired.quantile(.025), repetition_q975=paired.quantile(.975)))
    pd.DataFrame(rows).to_csv(destination / "paired_differences.csv", index=False)
    atomic_text(destination / "manifest.json", json.dumps(dict(configuration=cfg,
                note="Monte Carlo intervals conditional on fixed simulator and public inputs; not clinical effectiveness intervals."), indent=2))
    print(f"Paired summaries: {destination}")


def main(stage):
    parser = argparse.ArgumentParser(description=f"AGAP-CKD {stage}")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    cfg = load_config(args.config)
    started = time.perf_counter()
    if stage == "experiments":
        experiments(cfg)
    else:
        directory = execute(cfg, stage)
        print(f"[{stage}] {directory}")
    print(f"Elapsed: {time.perf_counter() - started:.2f}s")
