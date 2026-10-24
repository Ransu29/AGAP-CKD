"""SIM-11/12: day-0 measurement variability and diagnosis awareness (deterministic synthetic cohorts)."""
import copy

import numpy as np
import pandas as pd
import pytest

from agap.config import load_config
from agap.experiment import build_data, simulate_cohort
from agap.simulate.kidney import observed_screen_label


@pytest.fixture(scope="module")
def cohort(tmp_path_factory):
    cfg = copy.deepcopy(load_config())
    directory = tmp_path_factory.mktemp("realism")
    cells, demographics, facilities = build_data(cfg, directory)
    return cfg, cells, demographics, facilities


def simulate(cohort, count=4000, **traits):
    cfg, cells, demographics, facilities = cohort
    cfg = copy.deepcopy(cfg)
    cfg["simulator"]["traits"].update(traits)
    return simulate_cohort(cfg, cells, demographics, facilities, 0, "train", [], count=count)


def test_underlying_labs_match_the_kidney_state_and_the_flag_is_the_measured_result(cohort):
    frame = simulate(cohort)
    assert np.array_equal(observed_screen_label(frame.egfr_true, frame.uacr_true), frame.kidney_damage_true.to_numpy())
    assert np.array_equal(observed_screen_label(frame.egfr, frame.uacr) == 1, frame.y_true.to_numpy())
    # Measurement variability moves some people across a threshold in both directions.
    assert (frame.y_true & ~frame.kidney_damage_true).any() and (~frame.y_true & frame.kidney_damage_true).any()
    assert frame.egfr_true.between(59, 66).any()  # no empty band just above eGFR 60


def test_awareness_only_turns_true_conditions_into_unreported_no_answers(cohort):
    aware = simulate(cohort, dm_awareness=1.0, htn_awareness=1.0)
    unaware = simulate(cohort, dm_awareness=0.0, htn_awareness=0.0)
    reporters = aware.reported
    assert aware.loc[reporters, "dm_report"].eq(aware.loc[reporters, "dm_true"].astype(float)).all()
    assert unaware.loc[reporters, ["dm_report", "htn_report"]].eq(0).all().all()
    # The main stream is unchanged: same residents, traits, outcomes and participation.
    for column in ("dm_true", "htn_true", "kidney_damage_true", "y_true", "reported"):
        pd.testing.assert_series_equal(aware[column], unaware[column])
