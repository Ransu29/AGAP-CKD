"""GEO-02 population conservation and NFR-05 resumable experiment batches."""
import json

import pandas as pd
import pytest

import agap.cli
import agap.experiment
from agap.config import ROOT, load_config
from agap.data.geography import make_geography, population_check


def test_fixture_population_is_conserved():
    _, demographics, _, _ = make_geography(load_config(), ROOT)
    check = demographics.attrs["population_check"]
    assert check["source"] == check["demographics"] == check["cells"] > 0
    assert check["relative_difference"] == 0 and sum(check["municipality_totals"].values()) == pytest.approx(check["cells"])


def test_lost_population_stops_the_build():
    cells = pd.DataFrame(dict(h3=["a", "b"], municipality="Area", adult_count=[60.0, 40.0]))
    demographics = pd.DataFrame(dict(h3=["a", "b"], adult_count=[60.0, 40.0]))
    assert population_check(100.0, demographics, cells)["relative_difference"] == 0
    with pytest.raises(ValueError, match="not conserved"):
        population_check(101.0, demographics, cells)  # one adult dropped during aggregation
    with pytest.raises(ValueError, match="not conserved"):
        population_check(100.0, demographics, cells.assign(adult_count=[60.0, 41.0]))


@pytest.mark.skipif(not (ROOT / "data/raw/worldpop/age_sex/phl_f_15_2020_1km.tif").is_file(),
                    reason="collected WorldPop age-sex rasters not present")
def test_collected_laguna_population_is_conserved():
    _, demographics, _, _ = make_geography(load_config("config/public.yaml"), ROOT)
    check = demographics.attrs["population_check"]
    assert check["relative_difference"] <= check["tolerance"] and check["source"] > 1e6


@pytest.fixture
def small_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(agap.experiment, "ROOT", tmp_path)
    monkeypatch.setattr(agap.cli, "ROOT", tmp_path)
    cfg = load_config()
    cfg["prototype"].update(n_train=600, n_validation=300, n_deployment=400, repetitions=1)
    cfg["surveillance"]["monthly_sample"] = 20
    return cfg, tmp_path


def run_batch(cfg, capsys):
    agap.cli.experiments(cfg)
    lines = [line for line in capsys.readouterr().out.splitlines() if " OR=" in line]
    return [line.split(": ")[1].split(" ")[0] for line in lines]


def test_experiment_batch_resumes_completed_repetitions(small_batch, capsys):
    cfg, root = small_batch
    assert run_batch(cfg, capsys) == ["ran"] * 9
    first = pd.read_csv(next((root / "outputs/experiments").iterdir()) / "replications.csv")
    assert run_batch(cfg, capsys) == ["reused"] * 9
    again = pd.read_csv(next((root / "outputs/experiments").iterdir()) / "replications.csv")
    pd.testing.assert_frame_equal(first, again)  # same seeds, same results
    # An interrupted repetition (stage not complete) is run again; the others are reused.
    broken = sorted((root / "outputs/runs").iterdir())[0] / "manifest.json"
    manifest = json.loads(broken.read_text())
    manifest["stages"]["surveillance"] = "running"
    broken.write_text(json.dumps(manifest))
    assert sorted(run_batch(cfg, capsys)) == ["ran"] + ["reused"] * 8


def test_residents_carry_representation_weights(tmp_path):
    cfg = load_config()
    agap.experiment.build_data(cfg, tmp_path)
    frames = agap.experiment.simulate(cfg, tmp_path)
    demographics = pd.read_parquet(tmp_path / "demographics.parquet")
    cells = pd.read_parquet(tmp_path / "cells.parquet")
    for name, frame in frames.items():
        frame_cells = cells[cells.era5_cell.isin(frame.era5_cell.unique())]
        frame_adults = demographics[demographics.h3.isin(frame_cells.h3)].adult_count.sum()
        assert frame.representation_weight.nunique() == 1
        assert frame.representation_weight.sum() == pytest.approx(frame_adults), name  # SIM-01
        municipal = demographics.merge(frame_cells[["h3", "municipality"]], on="h3").groupby("municipality").adult_count.sum()
        assert frame.groupby("municipality").municipality_represented_adults.first().to_dict() == pytest.approx(municipal[frame.municipality.unique()].to_dict())


@pytest.mark.parametrize("name,size,repetitions,geography,climate", [
    ("fast", 2000, 5, "fixture", "synthetic"), ("full", 10000, 200, "fixture", "synthetic"),
    ("climate_full", 10000, 200, "public", "era5_land")])
def test_run_profiles_match_nfr_07(name, size, repetitions, geography, climate):
    cfg = load_config(f"config/{name}.yaml")
    prototype = cfg["prototype"]
    assert prototype["n_train"] == prototype["n_deployment"] == size and prototype["repetitions"] == repetitions
    assert prototype["geography_mode"] == geography and cfg.get("climate", {}).get("mode", "synthetic") == climate
