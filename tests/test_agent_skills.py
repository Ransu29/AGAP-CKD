"""Tests for agent skills tools and validators."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from agap.config import ROOT

SKILLS_DIR = ROOT / ".agents" / "skills"
DATA_SCIENTIST_SCRIPTS = SKILLS_DIR / "ckd-health-data-scientist" / "scripts"
RESEARCHER_SCRIPTS = SKILLS_DIR / "ckd-health-researcher" / "scripts"


def test_leakage_scanner_detects_forbidden_features():
    scanner = DATA_SCIENTIST_SCRIPTS / "leakage_scanner.py"
    res_bad = subprocess.run(
        [sys.executable, str(scanner), "--features", "age,sex,egfr"],
        capture_output=True,
        text=True,
    )
    assert res_bad.returncode == 1
    assert "Label leakage detected" in res_bad.stderr
    assert "egfr" in res_bad.stderr

    res_good = subprocess.run(
        [sys.executable, str(scanner), "--features", "age,sex,heat_index_mean"],
        capture_output=True,
        text=True,
    )
    assert res_good.returncode == 0
    assert "[PASS]" in res_good.stdout


def test_decision_curve_net_benefit_calculation(tmp_path: Path):
    dca_script = DATA_SCIENTIST_SCRIPTS / "decision_curve.py"
    csv_file = tmp_path / "test_preds.csv"
    csv_file.write_text("y_true,y_prob\n1,0.8\n0,0.1\n1,0.4\n0,0.05\n0,0.2\n")

    res = subprocess.run(
        [sys.executable, str(dca_script), "--file", str(csv_file), "--thresholds", "0.1,0.2", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    import json
    data = json.loads(res.stdout)
    assert len(data) == 2
    assert "net_benefit_model" in data[0]
    assert data[0]["threshold"] == 0.1
    assert data[0]["cases_found_per_1000"] > 0


def test_pmsampsize_estimator_returns_expected_bounds():
    estimator = RESEARCHER_SCRIPTS / "pmsampsize_estimator.py"
    res = subprocess.run(
        [sys.executable, str(estimator), "--c-statistic", "0.80", "--prevalence", "0.12", "--parameters", "8"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "TOTAL RECOMMENDED SAMPLE SIZE" in res.stdout
    assert "EVENTS PER PARAMETER" in res.stdout


def test_parameter_register_validator_passes():
    validator = RESEARCHER_SCRIPTS / "parameter_register_validator.py"
    res = subprocess.run(
        [sys.executable, str(validator)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "[PASS] Parameter Register Audit Successful" in res.stdout
