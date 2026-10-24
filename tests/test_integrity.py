"""INT-01 / INT-02: saved runs have resolvable references and valid ranges."""
import json
import shutil

import pandas as pd
import pytest

from agap.config import load_config
from agap.experiment import allocate, build_data, evaluate, simulate, train
from agap.integrity import IntegrityError, check_run
from agap.longitudinal import longitudinal


@pytest.fixture(scope="module")
def clean_run(tmp_path_factory):
    cfg = load_config()
    cfg["prototype"].update(n_train=1500, n_validation=600, n_deployment=1000)
    directory = tmp_path_factory.mktemp("runs") / "run-ok"
    directory.mkdir()
    for stage in (build_data, simulate, train, allocate, evaluate, longitudinal):
        stage(cfg, directory)
    (directory / "manifest.json").write_text(json.dumps(dict(run_id=directory.name, configuration=cfg)))
    return directory


@pytest.fixture
def run(clean_run, tmp_path):
    copy = tmp_path / clean_run.name
    shutil.copytree(clean_run, copy)
    return copy


def corrupt(run, name, change):
    path = run / name
    table = pd.read_csv(path) if name.endswith(".csv") else pd.read_parquet(path)
    table = change(table)
    table.to_csv(path, index=False) if name.endswith(".csv") else table.to_parquet(path, index=False)


def test_clean_run_passes_and_skips_missing_stage_files(run):
    result = check_run(run)
    assert len(result["checks"]) > 60
    assert result["skipped_missing_files"] == ["surveillance_monthly.parquet"]  # surveillance did not run here


@pytest.mark.parametrize("name,change,message", [
    ("predictions.parquet", lambda t: t.assign(resident_id=t.resident_id.where(t.index > 0, "SYN-GHOST-000001")),
     "predictions.parquet: every resident is a deployment resident"),
    ("allocations_hidden.parquet", lambda t: t.assign(facility_id=t.facility_id.where(t.facility_id.isna(), "SIM-999")),
     "every assigned facility exists"),
    ("allocations_hidden.parquet", lambda t: t.assign(policy=t.policy.replace("random", "lottery")), "every policy is a known policy"),
    ("deployment_hidden.parquet", lambda t: pd.concat([t, t.iloc[:1]], ignore_index=True), "resident IDs are unique"),
])
def test_broken_references_are_rejected(run, name, change, message):  # INT-01
    corrupt(run, name, change)
    with pytest.raises(IntegrityError, match=message):
        check_run(run)


def test_wrong_run_id_and_scenario_are_rejected(run):  # INT-01
    manifest = json.loads((run / "manifest.json").read_text())
    manifest["run_id"] = "another-run"
    manifest["configuration"]["prototype"]["mechanism"] = "MAYBE"
    (run / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(IntegrityError, match="run_id matches.*mechanism is MCAR"):
        check_run(run)


@pytest.mark.parametrize("name,change,message", [
    ("deployment_hidden.parquet", lambda t: t.assign(report_probability=t.report_probability.where(t.index > 0, 1.2)),
     "report_probability lies in \\[0, 1\\]"),
    ("predictions.parquet", lambda t: t.assign(score=t.score.where(t.index > 0, -0.1)), "score lies in \\[0, 1\\]"),
    ("facilities.parquet", lambda t: t.assign(capacity=t.capacity.where(t.index > 0, -5)), "capacity is nonnegative"),
    ("metrics.csv", lambda t: t.assign(completions=t.completions.where(t.index > 0, -1)), "completions is nonnegative"),
    ("metrics.csv", lambda t: t.assign(positives_per_100_completed=t.positives_per_100_completed.where(t.index > 0, 140)),
     "positives_per_100_completed lies in \\[0, 100\\]"),
])
def test_out_of_range_values_are_rejected(run, name, change, message):  # INT-02
    corrupt(run, name, change)
    with pytest.raises(IntegrityError, match=message):
        check_run(run)


def test_missing_values_are_not_range_violations(run):
    corrupt(run, "allocations_hidden.parquet", lambda t: t.assign(invitation_probability=float("nan")))
    assert check_run(run)["checks"]
