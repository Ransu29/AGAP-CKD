"""A model comparison changes scores, never the sample or simulation draws."""
import numpy as np
import pandas as pd
import pytest

from agap.config import load_config
from agap.model_comparison import compare_models, comparison_export, invitation_changes, model_diagnostics


@pytest.fixture
def cohort():
    frame = pd.DataFrame(dict(resident_id=list("ABCDEF"), municipality="Town", latitude=14.2,
        longitude=121.2, reported=[False, True, False, True, False, True], age=[65, 60, 55, 50, 45, 40],
        female=False, outdoor_true=False, y_true=[True, True, True, False, False, False],
        completion_probability=.9, completion_uniform=.1, nearest_distance_km=0., tie_uniform=np.arange(6)/10,
        hot_dry_score=np.arange(6)/3, clinical_score=[.9, .8, .7, .3, .2, .1],
        climate_score=[.1, .2, .3, .7, .8, .9]))
    facilities = pd.DataFrame(dict(facility_id=["SIM-1"], latitude=[14.2], longitude=[121.2], capacity=[3]))
    return frame, facilities


def test_paired_plans_preserve_inputs_share_random_draws_and_report_negative_results(cohort):
    frame, facilities = cohort
    before, sites = frame.copy(deep=True), facilities.copy(deep=True)
    cfg = load_config()
    comparison = compare_models(frame, facilities, cfg, 3, "Prioritize higher scores")
    clinical, climate = [comparison["plans"][name] for name in ("clinical", "climate")]
    pd.testing.assert_series_equal(clinical["random"].invited, climate["random"].invited)
    pd.testing.assert_series_equal(clinical["random"].completed, climate["random"].completed)
    assert set(clinical["proposed"].resident_id) == set(climate["proposed"].resident_id) == set(frame.resident_id)
    assert comparison["evaluation"].invitations.tolist() == [3, 3]
    assert comparison["evaluation"].positives_detected.tolist() == [3, 0]
    assert comparison["evaluation"].positives_not_detected.tolist() == [0, 3]
    assert comparison["decisions"].change.value_counts().to_dict() == {"Removed with climate": 3, "Added with climate": 3}
    assert not {"y_true", "outdoor_true", "positive_detected", "completed", "completion_uniform"} & set(comparison["decisions"])
    exported = comparison_export(comparison["decisions"].assign(y_true=frame.y_true), "run-test", "clinical",
                                 dict(budget=3, strategy="Prioritize higher scores", outreach=.3))
    assert "y_true" not in exported and exported.run_id.eq("run-test").all()
    assert exported.active_model.eq("clinical").all() and exported.outreach_share.eq(0).all()
    assert exported.data_status.str.startswith("Synthetic").all()
    for plan in (clinical, climate):
        assert plan["proposed"].invited.sum() <= min(3, facilities.capacity.sum())
    pd.testing.assert_frame_equal(frame, before)
    pd.testing.assert_frame_equal(facilities, sites)


def test_comparison_joins_by_id_and_rejects_different_denominators(cohort):
    frame, facilities = cohort
    comparison = compare_models(frame, facilities, load_config(), 3, "Priority + random outreach")
    clinical = comparison["plans"]["clinical"]["proposed"]
    climate = comparison["plans"]["climate"]["proposed"]
    pd.testing.assert_frame_equal(invitation_changes(frame, clinical.iloc[::-1], climate.iloc[::-1]), comparison["decisions"])
    with pytest.raises(ValueError, match="same residents"):
        invitation_changes(frame, clinical.iloc[:-1], climate)


def test_identical_models_have_no_invitation_changes_and_keep_access_constraints(cohort):
    frame, facilities = cohort
    frame = frame.assign(climate_score=frame.clinical_score)
    frame.loc[0, "latitude"] = 16.
    comparison = compare_models(frame, facilities, load_config(), 3, "Prioritize higher scores")
    assert not comparison["decisions"].change.isin(["Added with climate", "Removed with climate"]).any()
    for plan in comparison["plans"].values():
        assert not plan["proposed"].loc[0, "invited"]


def test_missing_climate_or_invalid_scores_cannot_be_compared(cohort):
    frame, facilities = cohort
    missing = frame.copy()
    missing.loc[0, "hot_dry_score"] = np.nan
    with pytest.raises(ValueError, match="complete saved climate"):
        compare_models(missing, facilities, load_config(), 3, "Prioritize higher scores")
    frame.loc[0, "climate_score"] = 1.1
    with pytest.raises(ValueError, match="finite probability"):
        model_diagnostics(frame)


def test_calibration_bins_account_for_every_resident_and_single_class_is_explicit(cohort):
    frame, _ = cohort
    frame = frame.assign(y_true=False, clinical_score=[0, .1, .2, .8, .9, 1.])
    metrics, bins = model_diagnostics(frame)
    assert metrics.auroc.isna().all() and metrics.auprc.isna().all()
    assert bins.groupby("model").residents.sum().to_dict() == {"clinical": 6, "climate": 6}
    assert bins.abnormal_fraction.eq(0).all()
    expected = np.square(frame.clinical_score).mean()
    assert metrics.set_index("model").loc["clinical", "brier"] == pytest.approx(expected)
