"""ALLOC-12: configurable geographic coverage requirements, checked before allocation."""
import copy

import numpy as np
import pandas as pd
import pytest

from agap.config import load_config
from agap.experiment import CoverageInfeasibleError, allocate_policy

POLICIES = [("random", 0), ("population_proportional", 0), ("risk_ranked", 0), ("risk_ranked", .2)]


def community(counts=(300, 100, 20), seed=0):
    """Municipality i's residents cluster around (14 + i/10, 121); each has a 100-slot point at its centre."""
    rng = np.random.default_rng(seed)
    names = [f"Area {chr(65 + i)}" for i in range(len(counts))]
    rows = []
    for i, (name, count) in enumerate(zip(names, counts)):
        for j in range(count):
            rows.append(dict(resident_id=f"SYN-T-{i}-{j:04d}", municipality=name,
                             latitude=14 + i / 10 + rng.normal(0, .005), longitude=121 + rng.normal(0, .005)))
    frame = pd.DataFrame(rows)
    count = len(frame)
    frame = frame.assign(reported=rng.random(count) < .3, age=rng.integers(18, 90, count), female=rng.random(count) < .5,
                         outdoor_true=rng.random(count) < .3, y_true=rng.random(count) < .15,
                         completion_probability=.7, nearest_distance_km=0.5,
                         completion_uniform=rng.random(count), tie_uniform=rng.random(count))
    facilities = pd.DataFrame(dict(facility_id=[f"SP-{i}" for i in range(len(counts))], municipality=names,
                                   latitude=[14 + i / 10 for i in range(len(counts))], longitude=121.0, capacity=100))
    return frame, facilities, rng.random(count)


def settings(budget=100, limit=5, **coverage):
    cfg = copy.deepcopy(load_config())
    cfg["allocation"].update(budget_tests=budget, max_distance_km=limit)
    cfg["allocation"]["coverage"] = {"minimum_invitations_per_municipality": 0, "minimum_invitations": {}, **coverage}
    return cfg


def invited_by_area(result):
    return result[result.invited].municipality.value_counts()


@pytest.mark.parametrize("policy,share", POLICIES)
def test_requirements_are_met_without_breaking_other_constraints(policy, share):
    frame, facilities, scores = community()
    cfg = settings(minimum_invitations_per_municipality=15)
    result = allocate_policy(cfg, frame, facilities, scores, policy, share)
    counts = invited_by_area(result)
    assert (counts.reindex(frame.municipality.unique(), fill_value=0) >= 15).all()
    assert result.invited.sum() <= 100 and result.resident_id.is_unique
    assert (result[result.invited].facility_id.value_counts() <= 100).all()
    assert result.reason.eq("coverage requirement").sum() >= 15


def test_no_requirement_adds_no_coverage_invitations():
    frame, facilities, scores = community()
    result = allocate_policy(settings(), frame, facilities, scores, "risk_ranked")
    assert not result.reason.eq("coverage requirement").any()
    assert invited_by_area(result).get("Area C", 0) < 15  # ranking alone need not reach the small area


def test_override_applies_to_one_municipality():
    frame, facilities, scores = community()
    result = allocate_policy(settings(minimum_invitations={"Area C": 20}), frame, facilities, scores, "risk_ranked")
    assert invited_by_area(result)["Area C"] == 20


def test_requirements_above_the_budget_fail_with_an_explanation():
    frame, facilities, scores = community()
    with pytest.raises(CoverageInfeasibleError, match="total 120 invitations but the budget is 100"):
        allocate_policy(settings(minimum_invitations_per_municipality=40), frame, facilities, scores, "random")


def test_too_few_reachable_residents_names_the_municipality():
    frame, facilities, scores = community()
    with pytest.raises(CoverageInfeasibleError, match=r"Area C needs 25 invitations but only 20 of its residents"):
        allocate_policy(settings(minimum_invitations={"Area C": 25}), frame, facilities, scores, "random")


def test_shared_capacity_is_checked_jointly():
    frame, facilities, scores = community(counts=(60, 60))
    shared = facilities.iloc[:1].assign(latitude=14.05, capacity=30)  # one point between both areas
    cfg = settings(budget=60, limit=10, minimum_invitations_per_municipality=20)
    with pytest.raises(CoverageInfeasibleError, match="shared service-point capacity can place at most 30 of the 40"):
        allocate_policy(cfg, frame, shared, scores, "random")


def test_unknown_municipality_and_invalid_values_are_rejected():
    frame, facilities, scores = community()
    with pytest.raises(CoverageInfeasibleError, match="not in this cohort"):
        allocate_policy(settings(minimum_invitations={"Atlantis": 5}), frame, facilities, scores, "random")
    with pytest.raises(CoverageInfeasibleError, match="whole numbers"):
        allocate_policy(settings(minimum_invitations_per_municipality=2.5), frame, facilities, scores, "random")


def test_proportional_quotas_count_coverage_invitations():
    frame, facilities, scores = community()
    plain = invited_by_area(allocate_policy(settings(), frame, facilities, scores, "population_proportional"))
    covered = invited_by_area(allocate_policy(settings(minimum_invitations={"Area C": 10}), frame, facilities, scores,
                                              "population_proportional"))
    assert covered.sum() == plain.sum() == 100
    assert covered["Area C"] == max(10, plain.get("Area C", 0))


def test_coverage_invitations_count_towards_proportional_quotas():
    # Quotas are exactly 60/20/20 of 100, so counting Area C's 15 coverage invitations twice would show.
    frame, facilities, scores = community(counts=(300, 100, 100))
    result = allocate_policy(settings(minimum_invitations={"Area C": 15}), frame, facilities, scores, "population_proportional")
    assert invited_by_area(result).to_dict() == {"Area A": 60, "Area B": 20, "Area C": 20}


def test_greedy_shortfall_fails_instead_of_relaxing():
    # Area X can only reach SP-1. Area Y is nearest SP-1 but can also reach SP-2, so a joint
    # assignment exists, yet nearest-point assignment of the scarcer Area Y first uses up SP-1.
    frame, _, scores = community(counts=(50, 12))
    frame["latitude"] = np.where(frame.municipality.eq("Area A"), 13.95, 14.02)
    frame["municipality"] = frame.municipality.map({"Area A": "Area X", "Area B": "Area Y"})
    facilities = pd.DataFrame(dict(facility_id=["SP-1", "SP-2"], municipality=["Area X", "Area Y"],
                                   latitude=[14.0, 14.1], longitude=121.0, capacity=[10, 100]))
    with pytest.raises(CoverageInfeasibleError, match="Nearest-service-point assignment met only"):
        allocate_policy(settings(budget=30, limit=10, minimum_invitations_per_municipality=10),
                        frame, facilities, scores, "random")


def test_proportional_quotas_follow_represented_population_not_sample_counts():
    # ALLOC-08: sample counts 300/100/100 would give 60/20/20 of 100 slots; represented adults give 50/20/30.
    frame, facilities, scores = community(counts=(300, 100, 100))
    by_counts = invited_by_area(allocate_policy(settings(), frame, facilities, scores, "population_proportional"))
    frame["municipality_represented_adults"] = frame.municipality.map({"Area A": 50_000.0, "Area B": 20_000.0, "Area C": 30_000.0})
    by_population = invited_by_area(allocate_policy(settings(), frame, facilities, scores, "population_proportional"))
    assert by_counts.to_dict() == {"Area A": 60, "Area B": 20, "Area C": 20}
    assert by_population.to_dict() == {"Area A": 50, "Area C": 30, "Area B": 20}


def test_unreported_outreach_fills_its_share_from_nonreporters_highest_score_first():
    frame, facilities, scores = community()
    cfg = settings(budget=100)
    result = allocate_policy(cfg, frame, facilities, scores, "risk_plus_unreported", .2)
    outreach = result[result.reason.eq("unreported outreach")]
    assert len(outreach) == 20 and not outreach.reported.any()
    eligible = result[~result.reported.astype(bool)].sort_values("score", ascending=False)
    assert set(outreach.resident_id) == set(eligible.resident_id.head(20))
    assert result.invited.sum() == 100 and result.policy.iloc[0] == "risk_unreported_20"


def test_unreported_outreach_raises_nonreporter_coverage_over_pure_risk_for_the_same_budget():
    frame, facilities, _ = community()
    # Scores favour reporters, as when missing answers lower a resident's modeled score.
    scores = np.where(frame.reported, .6, .2) + np.random.default_rng(1).random(len(frame)) / 10
    cfg = settings(budget=100)
    risk = allocate_policy(cfg, frame, facilities, scores, "risk_ranked", 0)
    outreach = allocate_policy(cfg, frame, facilities, scores, "risk_plus_unreported", .2)
    def reach(result):
        return result[~result.reported.astype(bool)].invited.sum()
    assert reach(outreach) > reach(risk) and outreach.invited.sum() == risk.invited.sum()
    again = allocate_policy(cfg, frame, facilities, scores, "risk_plus_unreported", .2)
    assert again.invited.equals(outreach.invited)


def test_parity_share_equalises_invitation_coverage_by_questionnaire_status():
    from agap.demo import parity_share
    frame, facilities, _ = community()
    scores = np.where(frame.reported, .6, .2) + np.random.default_rng(1).random(len(frame)) / 10
    share = parity_share(frame)
    assert share == round(float((~frame.reported).mean()), 2)
    result = allocate_policy(settings(budget=100), frame, facilities, scores, "risk_plus_unreported", share)
    coverage = result.groupby("reported").invited.mean()
    assert abs(coverage[False] - coverage[True]) < .02


def test_residents_reporting_known_ckd_are_never_invited_for_first_screening():
    frame, facilities, scores = community()
    frame["reported_known_ckd"] = False
    top = np.argsort(-scores)[:10]
    frame.loc[top, "reported_known_ckd"] = True
    for policy, share in POLICIES + [("risk_plus_unreported", .5)]:
        result = allocate_policy(settings(budget=100), frame, facilities, scores, policy, share)
        known = result.resident_id.isin(frame.loc[top, "resident_id"])
        assert not result.loc[known, "invited"].any()
        assert result.loc[known, "reason"].eq("reported known CKD").all()
        assert result.loc[known, "access_feasible"].all() and not result.loc[known, "screening_eligible"].any()
        assert result.invited.sum() == 100
