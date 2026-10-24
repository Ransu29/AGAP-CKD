"""NFR-07 / NFR-08 benchmark: stage runtimes, 10,000-resident allocation, cached dashboard filtering.

Builds one run of the chosen profile (default config/full.yaml) in a temporary folder, times every
pipeline stage and each allocation policy, then drives the dashboard with Streamlit's AppTest.
Results go to outputs/benchmarks/ as JSON and are printed as a table.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
import platform
import subprocess
import tempfile
import time
from pathlib import Path

import pandas as pd

import agap.config
from agap.config import ROOT, load_config
from agap.experiment import allocate, allocate_policy, allocation_scores, build_data, evaluate, fingerprint, simulate, source_hash, train
from agap.longitudinal import longitudinal
from agap.surveillance import surveil

ALLOCATION_TARGET_S, DASHBOARD_TARGET_S = 5.0, 2.0
POLICIES = [("random", 0), ("population_proportional", 0), ("risk_ranked", 0)] + [("risk_ranked", s) for s in (.1, .2, .3)]


def laptop():
    def sysctl(key):
        try:
            return subprocess.check_output(["sysctl", "-n", key], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    memory = sysctl("hw.memsize")
    return dict(system=f"{platform.system()} {platform.release()}", machine=platform.machine(),
                cpu=sysctl("machdep.cpu.brand_string") or platform.processor(), cores=os.cpu_count(),
                memory_gb=round(int(memory) / 2 ** 30, 1) if memory else None, python=platform.python_version(),
                packages={name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scikit-learn", "streamlit")})


def timed(function, *args):
    started = time.perf_counter()
    result = function(*args)
    return result, time.perf_counter() - started


def dashboard(cfg, directory):
    """Time a cold load, a warm rerun and cached interactions in the real app script."""
    from streamlit.testing.v1 import AppTest
    manifest = dict(configuration=cfg, config_hash=fingerprint(cfg), source_hash=source_hash(), run_id=directory.name,
                    stages={stage: "complete" for stage in ("data", "simulate", "train", "allocate", "evaluate")})
    (directory / "manifest.json").write_text(json.dumps(manifest, default=str))
    (directory.parent / "outputs").mkdir(exist_ok=True)
    (directory.parent / "outputs/latest_run.json").write_text(json.dumps(dict(path=str(directory))))
    agap.config.ROOT = directory.parent  # the app reads saved runs relative to ROOT
    app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=300)
    times = {}
    _, times["cold load"] = timed(app.run)
    _, times["warm rerun"] = timed(app.run)
    compare = next(button for button in app.button if button.label == "Compare screening plans")
    _, times["compare plans (first, computes allocation)"] = timed(compare.click().run)
    compare = next(button for button in app.button if button.label == "Compare screening plans")
    _, times["compare plans again (cached)"] = timed(compare.click().run)
    area = app.selectbox(key="surveillance_area")
    _, times["surveillance area filter (cached)"] = timed(area.set_value(area.options[1]).run)
    _, times["surveillance area filter back (cached)"] = timed(app.selectbox(key="surveillance_area").set_value(area.options[0]).run)
    if app.exception:
        raise RuntimeError(f"Dashboard raised: {app.exception}")
    return times


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/full.yaml")
    args = parser.parse_args()
    cfg = load_config(args.config)
    prototype = cfg["prototype"]
    with tempfile.TemporaryDirectory() as scratch:
        directory = Path(scratch) / "run"
        directory.mkdir()
        stages = {}
        for name, function in (("data", build_data), ("simulate", simulate), ("train", train), ("allocate", allocate),
                               ("evaluate", evaluate), ("longitudinal", longitudinal), ("surveillance", surveil)):
            _, stages[name] = timed(function, cfg, directory)
            print(f"stage {name}: {stages[name]:.1f}s", flush=True)
        frame = pd.read_parquet(directory / "deployment_hidden.parquet")
        facilities = pd.read_parquet(directory / "facilities.parquet")
        predictions = pd.read_parquet(directory / "predictions.parquet")
        scores = allocation_scores(cfg, predictions, frame)
        allocation = {}
        for policy, share in POLICIES:
            _, allocation[f"{policy}{f' {share:.0%}' if share else ''}"] = timed(allocate_policy, cfg, frame, facilities, scores, policy, share, cfg["seed"] + 100)
        print("allocation:", {k: round(v, 2) for k, v in allocation.items()}, flush=True)
        interactions = dashboard(cfg, directory)
        print("dashboard:", {k: round(v, 2) for k, v in interactions.items()}, flush=True)
    repetition = sum(stages.values())
    scenarios = 9  # 3 missingness mechanisms x 3 heat effects in make experiments
    cached = {k: v for k, v in interactions.items() if "cached" in k}
    result = dict(
        measured_utc=datetime.now(timezone.utc).isoformat(), config=args.config, laptop=laptop(),
        residents=dict(train=prototype["n_train"], validation=prototype["n_validation"], deployment=len(frame)),
        stage_seconds=stages, one_repetition_seconds=repetition,
        experiments_estimate_hours=repetition * scenarios * prototype["repetitions"] / 3600,
        allocation_seconds=allocation, allocation_target_seconds=ALLOCATION_TARGET_S,
        allocation_meets_target=max(allocation.values()) <= ALLOCATION_TARGET_S,
        dashboard_seconds=interactions, dashboard_target_seconds=DASHBOARD_TARGET_S,
        dashboard_cached_meets_target=max(cached.values()) <= DASHBOARD_TARGET_S,
        note="Dashboard times are server-side script reruns measured with Streamlit AppTest; browser rendering is not included.")
    out = ROOT / "outputs/benchmarks"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"benchmark-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("one_repetition_seconds", "experiments_estimate_hours", "allocation_meets_target", "dashboard_cached_meets_target")}, indent=2))
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
