"""Resident previews share a denominator and never invent missing weather."""
import numpy as np
import pandas as pd
import pytest
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from agap.climate_demo import preview_at_date, score_cohort


@pytest.fixture
def models():
    training = pd.DataFrame({
        "age": [25, 25, 70, 70, 40, 40, 55, 55],
        "dm_report": [0, 0, 1, 1, 0, 0, 1, 1],
        "hot_dry_score": [-1., 1., -1., 1., -1., 1., -1., 1.],
    })
    outcome = [0, 0, 1, 1, 0, 1, 0, 1]
    # Deliberately use a different order/subset from the production feature list:
    # the saved model, rather than a hard-coded list, defines prediction inputs.
    clinical = make_pipeline(SimpleImputer(), StandardScaler(), LogisticRegression())
    climate = make_pipeline(SimpleImputer(), StandardScaler(), LogisticRegression())
    clinical.fit(training[["dm_report", "age"]], outcome)
    climate.fit(training[["hot_dry_score", "age", "dm_report"]], outcome)
    return clinical, climate


@pytest.fixture
def residents():
    return pd.DataFrame({
        "person_id": ["A", "B", "C", "D"],
        "era5_cell": ["a", "a", "b", "c"],
        "age": [50., 50., 50., 50.],
        "dm_report": [1., 1., 1., 1.],
        "hot_dry_score": [-.2, -.2, .3, .4],
        "tie_uniform": [.7, .2, .8, .4],
        "cutoff": pd.to_datetime(["2024-01-01"] * 4),
        "hidden_outcome": [0, 1, 0, 1],
    }, index=[10, 20, 30, 40])


@pytest.fixture
def exposure():
    return pd.DataFrame({
        "era5_cell": ["a", "b", "c"],
        "cutoff": pd.to_datetime(["2024-04-30"] * 3),
        "complete": [True, False, True],
        "hot_dry_score": [2., np.nan, np.inf],
    })


@pytest.mark.parametrize("missing", ["date", "cohort", "all_windows"])
def test_unavailable_weather_returns_typed_empty_without_predicting(
        residents, exposure, models, monkeypatch, missing):
    if missing == "date":
        exposure["cutoff"] = pd.Timestamp("2024-05-01")
    elif missing == "cohort":
        exposure["era5_cell"] = ["outside_a", "outside_b", "outside_c"]
    else:
        exposure["complete"] = False

    def unexpected_prediction(*args, **kwargs):
        raise AssertionError("Empty previews must not attempt model prediction")

    for model in models:
        monkeypatch.setattr(model, "predict_proba", unexpected_prediction)
    result = preview_at_date(residents, exposure, "2024-04-30", *models)
    assert result.empty
    assert set(residents.columns).issubset(result.columns)
    for variant in ("clinical", "climate"):
        assert result[f"{variant}_score"].dtype == np.dtype("float64")
        assert result[f"{variant}_rank"].dtype == np.dtype("int64")


def test_preview_filters_both_models_to_complete_windows_and_keeps_ties_stable(
        residents, exposure, models):
    before_residents, before_exposure = residents.copy(deep=True), exposure.copy(deep=True)
    result = preview_at_date(residents, exposure, "2024-04-30", *models)
    assert result.person_id.tolist() == ["A", "B"]
    assert result.hot_dry_score.tolist() == [2., 2.]
    for variant in ("clinical", "climate"):
        assert result[f"{variant}_rank"].tolist() == [2, 1]
        assert result[f"{variant}_score"].nunique() == 1
    reordered = preview_at_date(residents.iloc[::-1], exposure, "2024-04-30", *models)
    pd.testing.assert_frame_equal(result.sort_index(), reordered.sort_index())
    pd.testing.assert_frame_equal(residents, before_residents)
    pd.testing.assert_frame_equal(exposure, before_exposure)
    pd.testing.assert_series_equal(result.cutoff, residents.loc[result.index, "cutoff"])
    pd.testing.assert_series_equal(result.hidden_outcome, residents.loc[result.index, "hidden_outcome"])


def test_preview_rejects_duplicate_cell_date_even_if_one_window_is_incomplete(
        residents, exposure, models):
    duplicate = exposure.iloc[[0]].assign(complete=False)
    with pytest.raises(ValueError, match="exactly one exposure record"):
        preview_at_date(residents, pd.concat([exposure, duplicate]), "2024-04-30", *models)


def test_score_cohort_uses_model_features_and_preserves_saved_inputs(residents, models):
    original = residents.copy(deep=True)
    result = score_cohort(residents, *models)
    for variant, model in zip(("clinical", "climate"), models):
        expected = model.predict_proba(residents[list(model.feature_names_in_)])[:, 1]
        np.testing.assert_allclose(result[f"{variant}_score"], expected)
        assert sorted(result[f"{variant}_rank"].tolist()) == [1, 2, 3, 4]
    assert result.clinical_rank.tolist() == [3, 1, 4, 2]
    pd.testing.assert_frame_equal(residents, original)
    pd.testing.assert_frame_equal(result[residents.columns], original)


def test_clinical_only_scoring_clears_stale_climate_results(residents, models):
    previously_scored = score_cohort(residents, *models)
    original = previously_scored.copy(deep=True)
    result = score_cohort(previously_scored, models[0])
    assert {"clinical_score", "clinical_rank"}.issubset(result.columns)
    assert not {"climate_score", "climate_rank"}.intersection(result.columns)
    pd.testing.assert_frame_equal(previously_scored, original)


def test_empty_clinical_only_cohort_has_only_clinical_result_columns(residents, models):
    result = score_cohort(residents.iloc[:0], models[0])
    assert result.empty
    assert result.clinical_score.dtype == np.dtype("float64")
    assert result.clinical_rank.dtype == np.dtype("int64")
    assert not {"climate_score", "climate_rank"}.intersection(result.columns)
