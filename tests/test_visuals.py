"""Explanations reconstruct the fitted score; gap charts partition one sample."""
import numpy as np
import pandas as pd
import pytest
from scipy.special import expit

from agap.climate_demo import model_contributions
from agap.experiment import CLINICAL, model_pipeline
from agap.visuals import chips_html, contributions_figure, resident_model_shift_html, visibility_gap_figure, weather_timeline_figure


@pytest.mark.parametrize("climate", [False, True])
def test_waterfall_reconstructs_fitted_decision_with_missing_inputs(climate):
    rng = np.random.default_rng(123)
    features = CLINICAL + (["hot_dry_score"] if climate else [])
    training = pd.DataFrame(rng.normal(size=(100, len(features))), columns=features)
    training.loc[::3, "dm_report"] = np.nan
    training.loc[::5, "family_report"] = np.nan
    target = (training.age + training.dm_report.fillna(.4) > 0).astype(int)
    model = model_pipeline(features).fit(training, target)
    for index in (0, 1, 3):
        person = training.iloc[index]
        terms = model_contributions(model, person)
        assert list(terms) == ["feature", "input", "contribution", "missing"]
        total = terms.attrs["intercept"] + terms.contribution.sum()
        np.testing.assert_allclose(total, model.decision_function(training.iloc[[index]])[0], atol=1e-12)
        np.testing.assert_allclose(expit(total), model.predict_proba(training.iloc[[index]])[0, 1], atol=1e-12)
        figure = contributions_figure(model, person)
        assert len(figure.data) == 1 and figure.data[0].type == "waterfall"
        assert list(figure.data[0].measure) == ["absolute"] + ["relative"] * len(features) + ["total"]
        np.testing.assert_allclose(figure.data[0].x,
            [terms.attrs["intercept"], *terms.sort_values("contribution").contribution, total])


def test_badge_text_and_attributes_are_html_escaped():
    html = chips_html([('answer\" onclick=\"bad', '<script>"bad"</script>')])
    assert "<script>" not in html and 'answer" onclick="bad' not in html
    assert "&lt;script&gt;" in html and "&quot;" in html


@pytest.fixture
def weather_window():
    return pd.DataFrame(dict(local_date=pd.date_range("2025-01-01", periods=30),
        tmean_c=np.linspace(24, 26, 30), tmax_c=np.linspace(29, 32, 30), precip_mm=np.arange(30)))


def test_weather_timeline_shares_one_axis_and_excludes_the_screening_day(weather_window):
    original = weather_window.copy(deep=True)
    figure = weather_timeline_figure(weather_window.iloc[::-1], "2025-01-31")
    assert [trace.name for trace in figure.data] == ["Daily maximum", "Daily mean", "Daily rainfall"]
    assert {trace.xaxis for trace in figure.data} == {"x"}
    assert [trace.yaxis for trace in figure.data] == ["y", "y", "y2"]
    np.testing.assert_allclose(figure.data[0].y, weather_window.tmax_c)
    np.testing.assert_allclose(figure.data[2].y, weather_window.precip_mm)
    assert max(figure.data[0].x) < pd.Timestamp("2025-01-31")
    assert figure.layout.shapes[0].x0 == pd.Timestamp("2025-01-31")
    assert figure.layout.hovermode == "x unified" and figure.layout.hoversubplots == "axis"
    assert "°C" in figure.layout.yaxis.title.text and "mm" in figure.layout.yaxis2.title.text
    pd.testing.assert_frame_equal(weather_window, original)


@pytest.mark.parametrize("issue", ["missing day", "duplicate", "screening day", "missing value", "negative rain"])
def test_weather_timeline_rejects_incomplete_or_future_observations(weather_window, issue):
    if issue == "missing day":
        weather_window = weather_window.iloc[:-1]
    elif issue == "duplicate":
        weather_window.loc[0, "local_date"] = weather_window.local_date.iloc[1]
    elif issue == "screening day":
        weather_window.loc[0, "local_date"] = pd.Timestamp("2025-01-31")
    elif issue == "missing value":
        weather_window.loc[0, "tmax_c"] = np.nan
    else:
        weather_window.loc[0, "precip_mm"] = -1
    with pytest.raises(ValueError):
        weather_timeline_figure(weather_window, "2025-01-31")


@pytest.mark.parametrize("clinical,climate,verdict,detail", [
    (False, True, "Invitation added with climate", "different invitation"),
    (True, False, "Invitation removed with climate", "different invitation"),
    (True, True, "Invitation unchanged", "Invited by both models"),
    (False, False, "Invitation unchanged", "Not invited by either model"),
])
def test_resident_verdict_uses_actual_invitations_instead_of_score_rank(clinical, climate, verdict, detail):
    person = pd.Series(dict(resident_id="SYN-A", clinical_score=.9, climate_score=.1, clinical_rank=1, climate_rank=100))
    decisions = pd.DataFrame(dict(resident_id=["SYN-A"], clinical_invited=[clinical], climate_invited=[climate]))
    html = resident_model_shift_html(person, 100, decisions, "ready", "clinical")
    assert verdict in html and detail in html
    assert 'is-active" data-model="clinical"' in html
    assert "90.0%" in html and "10.0%" in html
    pending = resident_model_shift_html(person, 100, plan_state="unplanned")
    assert "Invitations not planned" in pending and "Invitation unchanged" not in pending
    failed = resident_model_shift_html(person, 100, plan_state="unavailable")
    assert "Invitation comparison unavailable" in failed and "Not invited by either" not in failed


@pytest.fixture
def monthly():
    return pd.DataFrame(dict(municipality=["A", "A", "B"],
        month=pd.to_datetime(["2026-01-01", "2026-02-01", "2026-01-01"]),
        sampled_adults=[100, 100, 70], tested=[20, 0, 30],
        observed_abnormal=[3, 0, 2], hidden_undetected_abnormal=[7, 0, 9], hidden_abnormal=[10, 0, 11]))


def test_visibility_gap_uses_same_area_month_counts_and_explicit_zero(monthly):
    original = monthly.copy(deep=True)
    figure = visibility_gap_figure(monthly, "A", "2026-01-01")
    assert [trace.x[0] for trace in figure.data] == [3, 7]
    assert "simulator truth" in figure.data[1].name
    assert list(figure.data[0].customdata[0]) == [100, 20]
    assert "count" in figure.layout.xaxis.title.text
    zero = visibility_gap_figure(monthly, "A", "2026-02-01")
    assert sum(trace.x[0] for trace in zero.data) == 0
    assert "No abnormal flags" in zero.layout.annotations[0].text
    assert visibility_gap_figure(monthly, "B", "2026-02-01") is None
    pd.testing.assert_frame_equal(monthly, original)


@pytest.mark.parametrize("issue", ["duplicate", "partition", "negative", "missing"])
def test_visibility_gap_rejects_invalid_accounting(monthly, issue):
    if issue == "duplicate":
        monthly = pd.concat([monthly, monthly.iloc[[0]]])
    elif issue == "partition":
        monthly.loc[0, "hidden_abnormal"] = 11
    elif issue == "negative":
        monthly.loc[0, "observed_abnormal"] = -1
    else:
        monthly.loc[0, "hidden_undetected_abnormal"] = np.nan
    with pytest.raises(ValueError):
        visibility_gap_figure(monthly, "A", "2026-01-01")
