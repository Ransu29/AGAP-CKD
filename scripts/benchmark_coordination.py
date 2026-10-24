"""Measure server-side coordination interactions against the completed demo run.

All staff actions use temporary SQLite storage. Experiment artifacts and the
normal worklist are never changed. AppTest excludes browser/GPU rendering.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import tempfile
import time
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

import agap.config
from agap.config import ROOT, load_config
from agap.experiment import fingerprint, source_hash
from agap import workflow_store as store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/climate.yaml")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/benchmarks/coordination.json")
    args = parser.parse_args()
    cfg = load_config(args.config)
    directory = Path(json.loads((ROOT / "outputs/latest_run.json").read_text())["path"])
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["config_hash"] != fingerprint(cfg) or manifest["source_hash"] != source_hash():
        raise ValueError("Build the current configuration with make all before benchmarking.")
    if not all(value == "complete" for value in manifest["stages"].values()):
        raise ValueError("Complete the saved run before benchmarking.")
    times = {}

    def measured(label, operation):
        started = time.perf_counter()
        operation()
        times[label] = round(time.perf_counter() - started, 4)
        if app.exception:
            raise RuntimeError(f"The app failed during {label}: {app.exception}")
        print(f"{label}: {times[label]:.3f}s", flush=True)

    def click(label):
        next(button for button in app.button if button.label == label).click().run()

    with tempfile.TemporaryDirectory(prefix="agap-coordination-timing-") as temporary:
        db = Path(temporary) / "workflow.sqlite3"
        with patch.object(agap.config, "load_config", return_value=cfg), patch.dict(
                os.environ, {"AGAP_WORKFLOW_DB": str(db)}):
            st.cache_resource.clear()
            st.cache_data.clear()
            app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=60)
            measured("cold_plan", app.run)
            measured("warm_plan", app.run)
            measured("compare_first", lambda: click("Compare screening plans"))
            measured("compare_cached", lambda: click("Compare screening plans"))
            app.checkbox(key=f"workflow_create_confirm_{directory.name}").check().run()
            measured("approve_round", lambda: click("Create demo screening round"))
            record = store.active_round(db, run_id=directory.name)
            if record is None or app.session_state["workspace_tab"] != "Worklist":
                raise RuntimeError("The benchmark did not open its isolated approved round.")
            measured("warm_worklist", app.run)
            measured("contact_save", lambda: click("Save contact outcome"))
            if not any(event["event_type"] == "contact" for event in store.get_events(db, record["round_id"])):
                raise RuntimeError("The measured contact action was not persisted.")
            measured("work_queue_filter", lambda: app.selectbox(
                key=f"workflow_queue_{record['round_id']}").set_value("Needs contact").run())
            projection = []
            for _ in range(10):
                started = time.perf_counter()
                store.worklist(db, record["round_id"])
                projection.append(time.perf_counter() - started)
    result = dict(
        measured_utc=datetime.now(timezone.utc).isoformat(), config=args.config, run_id=directory.name,
        residents=len(record["snapshot"]["residents"]), slots=len(record["snapshot"]["slots"]),
        timings_seconds=times,
        projection_seconds=dict(min=min(projection), mean=sum(projection)/len(projection), max=max(projection)),
        targets_seconds=dict(warm_rerun=2, allocation=5),
        targets_met=dict(warm_plan=times["warm_plan"] < 2, warm_worklist=times["warm_worklist"] < 2,
                         allocation_including_ui=times["compare_first"] < 5),
        environment=dict(platform=platform.platform(), python=platform.python_version(),
                         streamlit=importlib.metadata.version("streamlit")),
        limitation="Server-side AppTest timing; excludes browser/GPU rendering. One local sample per interaction; not a load test.",
        database="Temporary isolated database, deleted on exit; saved experiment files unchanged.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(f"Saved {args.output}")
    return 0 if all(result["targets_met"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
