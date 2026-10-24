"""E3-14 / AT-08: weighting validity, diagnostics and claim scope."""
import copy
import json
import shutil

import pandas as pd
import pytest

from agap.config import load_config
from agap.experiment import build_data, simulate, train


def small(mechanism="MAR"):
    cfg = copy.deepcopy(load_config())
    cfg["prototype"].update(n_train=2000, n_validation=800, n_deployment=800, mechanism=mechanism)
    return cfg


@pytest.fixture(scope="module")
def simulated(tmp_path_factory):
    cfg = small()
    directory = tmp_path_factory.mktemp("runs") / "base"
    directory.mkdir()
    build_data(cfg, directory)
    simulate(cfg, directory)
    return cfg, directory


@pytest.fixture
def run(simulated, tmp_path):
    cfg, base = simulated
    shutil.copytree(base, tmp_path / "run")
    return cfg, tmp_path / "run"


def outputs(directory):
    diagnostics = json.loads((directory / "weight_diagnostics.json").read_text())[0]
    metrics = pd.read_csv(directory / "model_metrics.csv")
    return diagnostics, metrics.groupby("model").population_claim.first()


def test_full_support_allows_a_population_wide_claim_with_diagnostics(run):
    cfg, directory = run
    train(cfg, directory)
    diagnostics, claims = outputs(directory)
    assert diagnostics["zero_probability_residents"] == 0 and claims["ipw_climate"] == "population-wide"
    assert 0 < diagnostics["effective_sample_size"] <= diagnostics["observed_training_labels"]
    assert diagnostics["weight_cap"] > 0 and diagnostics["min_observation_probability"] > 0
    assert claims["clinical"] == claims["climate"] == "unweighted model; no weighting claim"


def test_zero_probability_residents_block_the_population_wide_claim(run):
    cfg, directory = run
    training = pd.read_parquet(directory / "train_hidden.parquet")
    unobserved = training.index[training.observed_label.isna()][:25]
    training.loc[unobserved, "observation_probability"] = 0.0  # residents the process can never reach
    training.to_parquet(directory / "train_hidden.parquet", index=False)
    train(cfg, directory)
    diagnostics, claims = outputs(directory)
    assert diagnostics["zero_probability_residents"] == 25
    assert diagnostics["zero_probability_share"] == pytest.approx(25 / len(training))
    assert claims["ipw_climate"].startswith("not population-wide: 25 of") and "supported subpopulation" in claims["ipw_climate"]


def test_observed_resident_with_zero_probability_stops_training(run):
    cfg, directory = run
    training = pd.read_parquet(directory / "train_hidden.parquet")
    training.loc[training.index[training.observed_label.notna()][:1], "observation_probability"] = 0.0
    training.to_parquet(directory / "train_hidden.parquet", index=False)
    with pytest.raises(ValueError, match="zero observation probability"):
        train(cfg, directory)


def test_mnar_weights_carry_the_oracle_label(tmp_path):
    cfg = small("MNAR")
    build_data(cfg, tmp_path)
    simulate(cfg, tmp_path)
    train(cfg, tmp_path)
    diagnostics, _ = outputs(tmp_path)
    metrics = pd.read_csv(tmp_path / "model_metrics.csv")
    assert diagnostics["weight_source"] == "oracle MNAR"
    assert set(metrics.loc[metrics.model.eq("ipw_climate"), "weight_source"]) == {"oracle MNAR"}
