"""Engine 4 research gateway: eligibility reasons, states, withdrawal, cohorts, independence."""
import copy

import numpy as np
import pandas as pd
import pytest

from agap.config import load_config
from agap.experiment import allocate_policy, build_data, simulate
from agap.models.leakage import LeakageError, check_no_leakage
from agap.research import (
    LABEL, RULE_VERSION, STATES, comparison_cohort, current_states, eligibility, read_events, reasons,
    record_event, simulate_interest,
)


@pytest.fixture(scope="module")
def cohort(tmp_path_factory):
    cfg = load_config()
    directory = tmp_path_factory.mktemp("run")
    build_data(cfg, directory)
    frames = simulate(cfg, directory)
    return cfg, frames["deployment"], pd.read_parquet(directory / "facilities.parquet")


def answers(rows):
    return pd.DataFrame([dict(resident_id=f"SYN-R-{i}", age=age, dm_report=dm, htn_report=htn)
                         for i, (age, dm, htn) in enumerate(rows)])


def test_eligibility_reports_each_criterion_and_unknown_is_not_yes():
    checks = eligibility(answers([(45, 1.0, 0.0), (45, np.nan, 0.0), (39, 1.0, 1.0), (60, 0.0, 1.0)]))
    assert checks.eligible.tolist() == [True, False, False, True]
    assert (checks.rule_version == RULE_VERSION).all()
    assert reasons(checks.iloc[1]) == ["✓ Age 40 or older", "✗ Reported diabetes or hypertension (answer 'Yes')"]
    assert reasons(checks.iloc[2])[0].startswith("✗")


def test_simulated_interest_is_reproducible_and_valid(cohort):
    cfg, deployment, _ = cohort
    first, again = simulate_interest(deployment, cfg), simulate_interest(deployment, cfg)
    pd.testing.assert_frame_equal(first, again)
    assert set(first.state) <= set(STATES)
    initial = first[first.sequence.eq(0)].state.value_counts(normalize=True)
    assert abs(initial["interested"] - .35) < .05
    bad = copy.deepcopy(cfg)
    bad["research"]["interest_shares"] = {"interested": .9, "declined": .9}
    with pytest.raises(ValueError, match="sum to 1"):
        simulate_interest(deployment, bad)


def test_cohort_draws_only_eligible_interested_and_is_matched(cohort, tmp_path):
    cfg, deployment, _ = cohort
    states = current_states(simulate_interest(deployment, cfg), read_events(tmp_path / "none.jsonl"))
    matched = comparison_cohort(deployment, states, seed=1)
    assert len(matched) > 0
    checks = eligibility(deployment).set_index("resident_id")
    assert checks.loc[matched.resident_id, "eligible"].all()
    assert states.reindex(matched.resident_id).eq("interested").all()
    sizes = matched.groupby(["age_band", "sex", "group"]).size().unstack("group")
    assert (sizes.iloc[:, 0] == sizes.iloc[:, 1]).all()
    assert (matched.label == LABEL).all() and (matched.rule_version == RULE_VERSION).all()
    assert "SYNTHETIC" in LABEL and "Not consent" in LABEL


def test_withdrawal_removes_from_exports_but_keeps_history(cohort, tmp_path):
    cfg, deployment, _ = cohort
    simulated = simulate_interest(deployment, cfg)
    events = tmp_path / "research_events.jsonl"
    before = comparison_cohort(deployment, current_states(simulated, read_events(events)), seed=1)
    leaving = before.resident_id.iloc[0]
    record_event(events, leaving, "interested", True)
    record_event(events, leaving, "withdrawn", True)
    after = comparison_cohort(deployment, current_states(simulated, read_events(events)), seed=1)
    assert leaving not in set(after.resident_id)
    history = read_events(events)
    assert history.state.tolist() == ["interested", "withdrawn"] and (history.resident_id == leaving).all()
    with pytest.raises(ValueError, match="Unknown research-interest state"):
        record_event(events, leaving, "enrolled", True)


def test_research_never_changes_screening_or_allocation(cohort, tmp_path):
    cfg, deployment, facilities = cohort
    scores = np.linspace(.01, .9, len(deployment))
    original = deployment.copy(deep=True)
    before = allocate_policy(cfg, deployment, facilities, scores, "risk_ranked", .2)
    states = current_states(simulate_interest(deployment, cfg), read_events(tmp_path / "none.jsonl"))
    comparison_cohort(deployment, states, seed=1)
    record_event(tmp_path / "events.jsonl", deployment.resident_id.iloc[0], "withdrawn", False)
    pd.testing.assert_frame_equal(deployment, original)
    pd.testing.assert_frame_equal(before, allocate_policy(cfg, deployment, facilities, scores, "risk_ranked", .2))
    for column in ("research_interest", "research_state", "research_eligible"):
        with pytest.raises(LeakageError):
            check_no_leakage([column], cfg["models"]["forbidden_features"])
