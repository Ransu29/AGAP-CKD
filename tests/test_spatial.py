"""GEO-04 spatial sensitivity: the same residents and outcomes at H3 resolution 7."""
import h3
import numpy as np
import pandas as pd
import pytest

from agap.config import load_config
from agap.experiment import allocate, build_data, pipeline_policies, simulate, train
from agap.spatial import located_at, ranking_summary, spatial


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    cfg = load_config()
    cfg["prototype"].update(n_train=2000, n_validation=800, n_deployment=1500)
    directory = tmp_path_factory.mktemp("run")
    for stage in (build_data, simulate, train, allocate):
        stage(cfg, directory)
    table, summary = spatial(cfg, directory)
    return cfg, directory, table, summary


def test_residents_and_outcomes_are_reaggregated_not_regenerated(run):
    _, directory, _, _ = run
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    facilities = pd.read_parquet(directory / "facilities.parquet")
    coarse = located_at(frame, facilities, 7)
    moved = {"latitude", "longitude", "nearest_distance_km", "area"}
    pd.testing.assert_frame_equal(coarse.drop(columns=list(moved)), frame.drop(columns=list(moved & set(frame.columns))))
    assert (coarse.area == frame.h3.map(lambda cell: h3.cell_to_parent(cell, 7))).all()
    assert coarse.area.nunique() < frame.h3.nunique()
    centre = h3.cell_to_latlng(coarse.area.iloc[0])
    assert np.allclose(coarse[["latitude", "longitude"]].iloc[0], centre)


def test_resolution_8_reproduces_the_saved_allocation(run):
    _, directory, table, _ = run
    saved = pd.read_parquet(directory / "allocations_hidden.parquet")
    fine = table[table.resolution.eq(8)].set_index("policy")
    for policy, records in saved.groupby("policy"):
        assert fine.loc[policy, "invitations"] == records.invited.sum()
        assert fine.loc[policy, "positives_detected"] == records.positive_detected.sum()


def test_every_policy_is_compared_at_both_resolutions(run):
    _, directory, table, summary = run
    assert set(table.resolution) == {8, 7} and table.groupby("resolution").policy.nunique().eq(len(pipeline_policies(load_config()))).all()
    assert (table.invitations <= 500).all() and (table.areas_reached <= table.areas).all()
    assert set(summary["policy_order"]) == {7, 8} and isinstance(summary["ranking_changed"], bool)
    assert (directory / "spatial_sensitivity.csv").exists() and (directory / "spatial_sensitivity.json").exists()


def test_ranking_change_is_detected():
    table = pd.DataFrame(dict(resolution=[8, 8, 7, 7], policy=["a", "b", "a", "b"], positives_detected=[10, 5, 4, 6]))
    summary = ranking_summary(table)
    assert summary["policy_order"] == {8: ["a", "b"], 7: ["b", "a"]} and summary["ranking_changed"]
    assert summary["largest_change_in_positives_detected"] == 6
    assert not ranking_summary(table.assign(positives_detected=[10, 5, 9, 6]))["ranking_changed"]


def test_unsupported_resolution_is_rejected(run):
    _, directory, _, _ = run
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    with pytest.raises(ValueError, match="resolutions"):
        located_at(frame, pd.read_parquet(directory / "facilities.parquet"), 6)
