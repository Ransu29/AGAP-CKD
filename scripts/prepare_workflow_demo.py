#!/usr/bin/env python3
"""Prepare an isolated, approved synthetic round for the guided demonstration.

Example:
    .venv/bin/python scripts/prepare_workflow_demo.py --config config/climate.yaml \
        --output-dir outputs/workflow-demo

Only the round approval is recorded. Contact, specimens, laboratory results and
review remain unrecorded until a person performs those actions in the app.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import sys

import joblib
import pandas as pd
import pyarrow.parquet as parquet

from agap.climate_demo import score_cohort
from agap.config import ROOT, load_config
from agap.experiment import CLINICAL, allocate_policy, distance_matrix, fingerprint, source_hash
from agap.models.leakage import check_allowed_features
from agap.workflow import RESIDENT_FIELDS, build_round_snapshot, replacement_candidate
from agap import workflow_store as store


DATA_STATUS = "Synthetic residents; suggested fictional laboratory values; hypothetical service points"
REQUIRED_STAGES = ("data", "simulate", "train", "allocate", "evaluate")


def _configuration(root, manifest, requested):
    recorded = manifest.get("configuration")
    if not isinstance(recorded, dict) or fingerprint(recorded) != manifest.get("config_hash"):
        raise ValueError("The run manifest has no consistent saved configuration.")
    if requested:
        path = Path(requested).expanduser()
        path = path if path.is_absolute() else root / path
        cfg = load_config(path)
        if fingerprint(cfg) != manifest["config_hash"]:
            raise ValueError("The requested configuration differs from the completed run; rebuild that profile first.")
        return cfg, path.resolve()
    for path in sorted((root / "config").glob("*.yaml")):
        try:
            cfg = load_config(path)
        except (KeyError, TypeError, ValueError):
            continue
        if fingerprint(cfg) == manifest["config_hash"]:
            return cfg, path.resolve()
    raise ValueError("No local configuration matches the saved run. Supply its matching --config file.")


def _operational_inputs(directory, cfg, model):
    model_path = directory / f"model_{model}.joblib"
    if not model_path.is_file():
        raise ValueError(f"The saved run has no {model} model.")
    saved_model = joblib.load(model_path)
    features = list(saved_model.feature_names_in_)
    allowed = CLINICAL + (["hot_dry_score"] if model == "climate" else [])
    check_allowed_features(features, allowed, cfg["models"]["forbidden_features"])
    names = set(parquet.ParquetFile(directory / "deployment_hidden.parquet").schema.names)
    columns = (set(RESIDENT_FIELDS) - {"score", "priority_rank", "random_rank", "candidate_distances_km"}) | {
        "tie_uniform", "nearest_distance_km", "municipality_represented_adults", *features}
    required = {"resident_id", "municipality", "latitude", "longitude", "age", "female", "reported", "tie_uniform", *features}
    if required - names:
        raise ValueError(f"The saved cohort lacks required operational inputs: {sorted(required - names)}")
    # Read only observable resident/model inputs. No hidden outcome, laboratory
    # measurement, latent trait or attendance draw is read from the run file.
    frame = pd.read_parquet(directory / "deployment_hidden.parquet", columns=sorted(columns & names))
    facilities = pd.read_parquet(directory / "facilities.parquet")
    if frame.empty or facilities.empty:
        raise ValueError("The completed run must contain residents and hypothetical service points.")
    if "nearest_distance_km" not in frame:
        frame["nearest_distance_km"] = distance_matrix(frame, facilities).min(axis=1)
    clinical = saved_model if model == "clinical" else joblib.load(directory / "model_clinical.joblib")
    check_allowed_features(list(clinical.feature_names_in_), CLINICAL, cfg["models"]["forbidden_features"])
    # Both saved models may need clinical columns even when filming climate.
    missing = set(clinical.feature_names_in_) - set(frame)
    if missing:
        extra = pd.read_parquet(directory / "deployment_hidden.parquet", columns=["resident_id", *sorted(missing)])
        frame = frame.merge(extra, on="resident_id", how="left", validate="one_to_one", sort=False)
    scored = score_cohort(frame, clinical, saved_model if model == "climate" else None)
    # allocate_policy also computes research evaluation fields. These fixed dummy
    # bookkeeping inputs make those unused outputs empty, without loading hidden
    # simulation truth. They never influence invitations or enter the snapshot.
    allocation_inputs = scored.assign(completion_probability=.5, completion_uniform=1., y_true=False, outdoor_true=False)
    return scored, allocation_inputs, facilities


def _scenario_cases(snapshot):
    people = {row["resident_id"]: row for row in snapshot["residents"]}
    slots = snapshot["slots"]
    ordered = sorted(slots, key=lambda slot: (bool(people[slot["original_resident_id"]].get("reported")),
                                              people[slot["original_resident_id"]]["priority_rank"], slot["slot_id"]))
    if not ordered:
        raise ValueError("No feasible invitations were assigned; a guided round cannot be prepared.")
    main = ordered[0]
    donor, proposal = None, None
    for slot in slots:
        if slot["slot_id"] == main["slot_id"]:
            continue
        trial = deepcopy(slots)
        released = next(row for row in trial if row["slot_id"] == slot["slot_id"])
        released.update(status="released", current_resident_id=None)
        candidate = replacement_candidate(snapshot, trial, [], slot["slot_id"])
        if candidate is not None:
            donor, proposal = slot, candidate
            break
    return dict(
        main_resident_id=main["original_resident_id"],
        main_questionnaire_available=bool(people[main["original_resident_id"]].get("reported")),
        main_selection_basis="Approved invitation; prefer a missing questionnaire, then frozen priority order",
        donor_resident_id=donor["original_resident_id"] if donor else None,
        donor_slot_id=donor["slot_id"] if donor else None,
        replacement_resident_id=proposal["resident_id"] if proposal else None,
        replacement_selection_basis=proposal["selection_basis"] if proposal else None,
        replacement_facility_id=proposal["facility_id"] if proposal else None,
        replacement_municipality=proposal["municipality"] if proposal else None,
        replacement_distance_km=proposal["distance_km"] if proposal else None,
        recovery_available=proposal is not None,
        recovery_note=("Proposed using a hypothetical released copy only; no decline or replacement has been recorded."
                       if proposal else "No distinct donor has a feasible same-service-point, same-municipality replacement in this frozen round."),
    )


def prepare_guided_demo(database, config_path=None, output_dir=None, model="clinical", *, root=ROOT,
                        allow_source_mismatch=False):
    """Approve one isolated round and return a reproducible, truth-free script."""
    root, database = Path(root).resolve(), Path(database).expanduser().resolve()
    if database == (root / "data/reports/screening_workflow.sqlite3").resolve():
        raise ValueError("Use an isolated --database, not the application's normal coordination database.")
    if any(record["status"] == "active" for record in store.list_rounds(database)):
        raise ValueError("This demo database already has an active round. Use another --database or archive it in the app; nothing was overwritten.")
    latest_path = root / "outputs/latest_run.json"
    if not latest_path.is_file():
        raise ValueError("There is no completed latest run. Build the requested profile first.")
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    directory = Path(latest["path"])
    directory = directory if directory.is_absolute() else root / directory
    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("run_id") != directory.name:
        raise ValueError("The saved run directory and manifest identity differ.")
    if not all(manifest.get("stages", {}).get(stage) == "complete" for stage in REQUIRED_STAGES):
        raise ValueError("The saved run has not completed data, simulation, training, allocation and evaluation.")
    cfg, selected_config = _configuration(root, manifest, config_path)
    if latest.get("config_hash", manifest["config_hash"]) != manifest["config_hash"]:
        raise ValueError("The latest-run pointer and manifest configuration hashes differ.")
    source_matches = manifest.get("source_hash") == source_hash()
    if not source_matches and not allow_source_mismatch:
        raise ValueError("The completed run predates the current Python source. Rebuild after the source freeze, or use --allow-source-mismatch explicitly for development.")
    if model not in {"clinical", "climate"}:
        raise ValueError("Choose clinical or climate for the guided round.")
    scored, allocation_inputs, facilities = _operational_inputs(directory, cfg, model)
    settings = dict(budget=min(500, len(scored)), strategy="Priority + random outreach", outreach=.2)
    planning_cfg = deepcopy(cfg)
    planning_cfg["allocation"]["budget_tests"] = settings["budget"]
    records = allocate_policy(planning_cfg, allocation_inputs, facilities, scored[f"{model}_score"].to_numpy(),
                              "risk_ranked", .2, seed=cfg["seed"] + 100)
    snapshot = build_round_snapshot(scored, facilities, records, cfg, directory.name, model, settings, manifest=manifest)
    cases = _scenario_cases(snapshot)
    # All validation and scenario selection happens before creating a persisted
    # approval. Never reset, unlink or modify an existing active round.
    record = store.create_round(database, snapshot, actor="Guided demo coordinator")
    launch = [str(root / ".venv/bin/python"), "-m", "streamlit", "run", str(root / "app/main.py"),
              "--", "--config", str(selected_config)]
    scenario = dict(
        schema_version=1, data_status=DATA_STATUS, prepared_utc=datetime.now(timezone.utc).isoformat(),
        database=str(database), run_id=record["run_id"], round_id=record["round_id"],
        original_provenance=snapshot["provenance"], source_matches_current=source_matches,
        model=model, settings=snapshot["settings"], approved_invitations=len(snapshot["slots"]),
        cases=cases, persisted_actions=["round_created"],
        suggested_fictional_inputs=dict(
            questionnaire="Use fictional answers with today's event date; preview then explicitly apply. Approved invitations stay fixed.",
            specimen_date="Use the actual filming date, after explicitly recording specimen collection.",
            partial_panel=dict(creatinine=.8, creatinine_unit="mg/dL", uacr=None),
            unflagged_panel=dict(creatinine=.8, creatinine_unit="mg/dL", uacr=10, uacr_unit="mg/g"),
            flagged_amendment=dict(creatinine=.8, creatinine_unit="mg/dL", uacr=100, uacr_unit="mg/g"),
            result_reference="FICTIONAL-DEMO-001"),
        launch_command=f"AGAP_WORKFLOW_DB={shlex.quote(str(database))} " + shlex.join(launch),
        steps=["Open Worklist and select main_resident_id.",
               "Review/correct the questionnaire, preview, then explicitly apply the fictional report.",
               "Record Accepted contact and specimen collection for the main resident.",
               "Enter the suggested partial panel, then complete it; optionally amend uACR to 100 to open a review task.",
               "Record a review or staff-entered follow-up task.",
               "Select donor_resident_id, record an explicit decline before specimen collection, then confirm the proposed replacement.",
               "Open Climate comparison; distinguish draft counterfactual invitations from the approved worklist.",
               "Export the approved worklist and activity history."],
    )
    if not cases["recovery_available"]:
        scenario["steps"][5] = "Slot recovery is unavailable for this frozen run; explain the saved constraint rather than inventing a replacement."
    if output_dir is not None:
        output = Path(output_dir).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        # Distinct round IDs prevent accidentally replacing an earlier filming script.
        scenario_path = output / f"{record['round_id']}_scenario.json"
        with scenario_path.open("x", encoding="utf-8") as handle:
            json.dump(scenario, handle, indent=2, allow_nan=False)
            handle.write("\n")
        scenario["scenario_file"] = str(scenario_path)
    return scenario


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Configuration matching the completed latest run (otherwise discovered locally).")
    parser.add_argument("--database", type=Path, default=ROOT / "data/reports/guided_workflow.sqlite3",
                        help="Isolated SQLite file; the normal application database is refused.")
    parser.add_argument("--output-dir", type=Path, help="Optionally write the scenario JSON, e.g. outputs/workflow-demo.")
    parser.add_argument("--model", choices=["clinical", "climate"], default="clinical")
    parser.add_argument("--allow-source-mismatch", action="store_true", help="Development only: retain an older run's original identity.")
    args = parser.parse_args(argv)
    try:
        scenario = prepare_guided_demo(args.database, args.config, args.output_dir, args.model,
                                       allow_source_mismatch=args.allow_source_mismatch)
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        parser.exit(1, f"Could not prepare the guided demonstration: {exc}\n")
    print(json.dumps(scenario, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
