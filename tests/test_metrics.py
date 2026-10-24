"""EVAL-05: rates with denominators; sampled-cohort versus population-weighted coverage."""
import numpy as np
import pandas as pd
import pytest

from agap.config import load_config
from agap.experiment import allocation_metrics


def records(weights=None, completed=(True, True, False, False), detected=(True, False, False, False)):
    frame = pd.DataFrame(dict(policy="p", resident_id=list("abcd"), municipality=["A", "A", "B", "B"], age=[45, 50, 60, 70],
                              female=[True, False, True, False], outdoor_true=False, reported=[True, False, True, False],
                              y_true=[True, False, True, False], access_feasible=True, invited=list(completed),
                              completed=list(completed), positive_detected=list(detected)))
    return frame if weights is None else frame.assign(representation_weight=weights)


def overall(table):
    return table[table.subgroup.eq("all")].iloc[0]


def test_equal_weights_keep_the_share_and_scale_the_counts():
    row = overall(allocation_metrics(records(weights=[250.0] * 4), load_config()))
    assert row.completion_coverage == row.population_weighted_coverage == 0.5
    assert row.represented_adults == 1000 and row.represented_completions == 500 and row.represented_positives_detected == 250


def test_unequal_weights_give_a_population_weighted_estimate():
    # Residents a and b (completed) stand for 100 adults each; c and d for 400 each.
    row = overall(allocation_metrics(records(weights=[100.0, 100.0, 400.0, 400.0]), load_config()))
    assert row.completion_coverage == 0.5
    assert row.population_weighted_coverage == pytest.approx(200 / 1000)
    municipal = allocation_metrics(records(weights=[100.0, 100.0, 400.0, 400.0]), load_config())
    municipal = municipal[municipal.subgroup.eq("municipality")].set_index("value")
    assert municipal.loc["A", "represented_adults"] == 200 and municipal.loc["B", "population_weighted_coverage"] == 0


def test_without_weights_population_figures_are_undefined_not_zero():
    row = overall(allocation_metrics(records(), load_config()))
    assert np.isnan(row.population_weighted_coverage) and np.isnan(row.represented_adults)


def test_every_rate_has_its_denominator():
    table = allocation_metrics(records(weights=[250.0] * 4), load_config())
    denominators = {"completion_coverage": "eligible", "positives_per_100_completed": "completions",
                    "feasible_completion_coverage": "feasible_population", "population_weighted_coverage": "represented_adults"}
    for rate, denominator in denominators.items():
        assert rate in table and denominator in table, rate
