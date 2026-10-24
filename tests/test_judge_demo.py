"""Exercise the connected walkthrough without writes to real report histories."""
import copy
import json
from pathlib import Path

import joblib
import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import agap.config
import agap.climate_demo
import agap.climate.available
import agap.reports
import agap.walkthrough
from agap.config import load_config
from agap.demo import compare_plans, run_summary, with_reports
from agap.decision_support import BUCKETS, evaluation_mask
from agap.reports import resident_history
from agap.experiment import allocate, build_data, evaluate, fingerprint, simulate, source_hash, train
from agap.longitudinal import longitudinal
from agap.surveillance import surveil


@pytest.fixture(scope="module")
def saved_demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("judge-demo")
    cfg = load_config()
    cfg["prototype"].update(n_train=2000, n_validation=800, n_deployment=1200)
    directory = root / "run"
    directory.mkdir()
    build_data(cfg, directory)
    simulate(cfg, directory)
    train(cfg, directory)
    allocate(cfg, directory)
    evaluate(cfg, directory)
    longitudinal(cfg, directory)
    surveil(cfg, directory)
    manifest = dict(configuration=cfg, config_hash=fingerprint(cfg), source_hash=source_hash(),
                    stages={stage: "complete" for stage in ("data", "simulate", "train", "allocate", "evaluate")})
    (directory / "manifest.json").write_text(json.dumps(manifest))
    (root / "outputs").mkdir()
    (root / "outputs/latest_run.json").write_text(json.dumps(dict(path=str(directory))))
    return root, directory, cfg


# Panel tabs inside Plan and Evaluate; the rest are top-level destinations.
NESTED_TABS = ("Residents", "Decision", "Plan settings", "Plan vs random", "Climate vs questionnaire", "Surveillance", "Safeguards")


def open_demo(saved_demo, monkeypatch, configuration=None):
    st.cache_resource.clear()
    root, _, cfg = saved_demo
    monkeypatch.setattr(agap.config, "ROOT", root)
    monkeypatch.setattr(agap.config, "load_config", lambda path=None: configuration or cfg)
    application = Path(__file__).resolve().parents[1] / "app/main.py"
    app = AppTest.from_file(str(application)).run(timeout=30)
    return sign_in(app, "Health worker (RHU)")


def sign_in(app, role):
    """Simulated sign-in: sign out of any current demo account, then choose another."""
    if any(button.label == "Sign out" for button in app.button):
        click(app, "Sign out")
    click(app, f"Sign in as {role}")
    return app


def click(app, label):
    next(button for button in app.button if button.label == label).click().run(timeout=30)
    assert not app.exception


def metric(app, label):
    return next(item.value for item in app.metric if item.label == label)


def choose_resident(app, frame):
    person = frame.loc[frame.municipality.eq(sorted(frame.municipality.unique())[0])].sort_values(["reported", "resident_id"]).iloc[0]
    app.selectbox(key="flow_resident").set_value(person.resident_id).run(timeout=30)
    assert not app.exception
    return person


def test_planner_follows_residents_without_discarding_reports_or_plan(saved_demo, monkeypatch):
    _, directory, cfg = saved_demo
    exports = []
    original_export = agap.walkthrough.invitation_export

    def capture_export(*args):
        export = original_export(*args)
        exports.append(export)
        return export

    monkeypatch.setattr(agap.walkthrough, "invitation_export", capture_export)
    app = open_demo(saved_demo, monkeypatch)
    assert not app.exception
    assert [tab.label for tab in app.tabs if tab.label not in NESTED_TABS] == [
        "Worklist", "Plan", "Resident report", "Resident weather", "Evaluate", "Data"]
    assert app.session_state["workspace_panel"] == "Residents"
    assert app.session_state["workspace_tab"] == "Plan"
    assert app.selectbox(key="workspace_page").value == "Plan"
    assert app.session_state["flow_resident"] is None
    assert not app.session_state["comparison_started"]
    assert any("not assigned yet" in item.value for item in app.info)
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    person = choose_resident(app, frame)
    selected = person.resident_id
    assert app.session_state["workspace_panel"] == "Decision"
    assert metric(app, "Invitation in the current plan") == "Not planned"
    assert any("No plan prepared" in item.value for item in app.info)
    saved_bytes = (directory / "deployment_hidden.parquet").read_bytes()
    click(app, "Compare screening plans")
    click(app, "Review / correct questionnaire")
    assert app.session_state["workspace_tab"] == "Resident report"
    assert app.selectbox(key="workspace_page").value == "Resident report"
    app.selectbox(key="report_form_DM").set_value("Y")
    click(app, "Preview this report's effect")
    assert app.session_state["report_result"]["payload"]["resident_id"] == selected
    assert app.session_state["report_result"]["payload"]["DM"] == "Y"
    assert "result" not in app.session_state["report_result"]
    after_score = metric(app, "Score after report")
    click(app, "Apply report & return to workspace")
    assert app.session_state["workspace_tab"] == "Plan"
    assert app.selectbox(key="workspace_page").value == "Plan"
    assert metric(app, "This resident's score") == after_score
    assert metric(app, "Questionnaire-only model") == after_score
    assert app.session_state["flow_resident"] == selected
    click(app, "Back to Plan")
    assert app.session_state["workspace_tab"] == "Plan"

    model = joblib.load(directory / "model_clinical.joblib")
    facilities = pd.read_parquet(directory / "facilities.parquet")
    for budget, strategy in ((100, "Prioritize higher scores"), (50, "Priority + random outreach")):
        app.slider(key="panel_budget").set_value(budget)
        app.selectbox(key="plan_choice").set_value(strategy)
        click(app, "Compare screening plans")
        assert app.session_state["comparison_settings"]["budget"] == budget
        updated = with_reports(frame, app.session_state["applied_reports"])
        scores = model.predict_proba(updated[list(model.feature_names_in_)])[:, 1]
        expected = compare_plans(updated, facilities, scores, cfg, **app.session_state["comparison_settings"])
        invited = expected["proposed"].loc[expected["proposed"].resident_id.eq(selected), "invited"].iloc[0]
        assert metric(app, "Invitation in the current plan") == ("Yes" if invited else "No")
        assert set(exports[-1].resident_id) == set(expected["proposed"].loc[expected["proposed"].invited, "resident_id"])
        assert any(f"Current plan: {budget:,} panels" in item.value for item in app.caption)
        assert any(f"Same {budget:,}-panel budget" in item.value for item in app.caption)
        assert any("Do the abnormal results persist?" in item.value for item in app.markdown)
    before_filter = exports[-1].copy()
    app.selectbox(key="flow_municipality").set_value(person.municipality).run(timeout=30)
    pd.testing.assert_frame_equal(exports[-1], before_filter)
    assert app.session_state["comparison_started"]

    other = frame.loc[frame.municipality.eq(person.municipality) & ~frame.resident_id.eq(selected)].iloc[0]
    app.selectbox(key="flow_resident").set_value(other.resident_id).run(timeout=30)
    assert not app.exception
    assert selected in app.session_state["applied_reports"]
    assert not app.session_state.get("report_result")
    assert app.session_state["comparison_started"]
    click(app, "Review / correct questionnaire")
    click(app, "Preview this report's effect")
    click(app, "Apply report & return to workspace")
    assert set(app.session_state["applied_reports"]) == {selected, other.resident_id}
    assert (directory / "deployment_hidden.parquet").read_bytes() == saved_bytes
    click(app, "Reset draft workspace")
    assert not app.session_state["comparison_started"]
    assert not app.session_state["applied_reports"]
    assert app.session_state["flow_resident"] is None


def test_compact_page_selector_preserves_plan_and_tracks_tab_navigation(saved_demo, monkeypatch):
    app = open_demo(saved_demo, monkeypatch)
    pages = list(agap.walkthrough.WORKSPACE_PAGES)
    selector = app.selectbox(key="workspace_page")
    assert selector.label == "Page" and selector.options == pages
    assert len([item for item in app.selectbox if item.key == "workspace_page"]) == 1
    click(app, "Compare screening plans")
    settings = dict(app.session_state["comparison_settings"])
    for page in ("Resident report", "Resident weather", "Evaluate", "Data", "Worklist", "Plan"):
        app.selectbox(key="workspace_page").set_value(page).run(timeout=30)
        assert not app.exception
        assert app.session_state["workspace_tab"] == page
        assert app.selectbox(key="workspace_page").value == page
        assert app.session_state["comparison_started"]
        assert app.session_state["comparison_settings"] == settings
    # Desktop tab callbacks and context links update the same destination key.
    app.session_state["workspace_tab"] = "Resident weather"
    app.run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="workspace_page").value == "Resident weather"
    assert [tab.label for tab in app.tabs if tab.label not in NESTED_TABS] == pages


def test_plan_formation_uses_applied_settings_and_actual_constraints():
    frame = pd.DataFrame({"municipality": ["Calamba", "Calamba", "Cabuyao"]})
    facilities = pd.DataFrame({"capacity": [7, 11]})
    cfg = {"allocation": {"max_distance_km": 12,
                           "coverage": {"minimum_invitations_per_municipality": 1,
                                        "minimum_invitations": {"Calamba": 2}}}}
    settings = dict(budget=3, strategy="Priority + random outreach", outreach=.3)
    lines = " ".join(agap.walkthrough._plan_formation_lines(frame, facilities, cfg, "clinical", settings))
    assert "Questionnaire only" in lines
    assert "up to 3 invitations from 3 cohort adults" in lines
    assert "target 30% random outreach" in lines
    assert "12 km straight-line" in lines and "2 service points provide 18 total slots" in lines
    assert "at least 3 invitations across 2 municipalities" in lines
    settings.update(strategy="Prioritize higher scores", outreach=.3)
    cfg["allocation"]["coverage"] = {}
    lines = " ".join(agap.walkthrough._plan_formation_lines(frame, facilities, cfg, "clinical", settings))
    assert "higher scores first" in lines and "30%" not in lines
    assert "no invitation minimums" in lines
    settings["strategy"] = "Share invitations by municipality"
    lines = " ".join(agap.walkthrough._plan_formation_lines(frame, facilities, cfg, "clinical", settings))
    assert "represented adult population" in lines and "Unfilled municipal quotas" in lines


def test_plan_formation_distinguishes_frozen_round_from_current_draft():
    def render():
        import pandas as pd
        from agap.walkthrough import _plan_formation
        working = pd.DataFrame({"municipality": ["Calamba", "Cabuyao"]})
        facilities = pd.DataFrame({"capacity": [18]})
        cfg = {"allocation": {"max_distance_km": 12, "coverage": {}}}
        settings = dict(budget=2, strategy="Priority + random outreach", outreach=.2)
        approved = {"snapshot": {"model": "climate", "facilities": [{"capacity": 9}, {"capacity": 13}],
                                 "settings": dict(budget=1, strategy="Prioritize higher scores", outreach=.3,
                                                  max_distance_km=7)}}
        _plan_formation(working, facilities, cfg, "clinical", settings, approved)

    app = AppTest.from_function(render).run()
    assert not app.exception
    assert any("Draft model:** Questionnaire only" in item.value for item in app.markdown)
    assert any("12 km straight-line" in item.value and "18 total slots" in item.value for item in app.markdown)
    saved = next(item.value for item in app.caption if "Approved round stays fixed" in item.value)
    assert "Questionnaire + climate" in saved and "1-panel budget" in saved
    assert "outreach 0%" in saved and "7 km access limit" in saved and "22 total service-point slots" in saved


def test_filter_empty_state_clears_selection_but_keeps_whole_plan(saved_demo, monkeypatch):
    _, directory, _ = saved_demo
    app = open_demo(saved_demo, monkeypatch)
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    choose_resident(app, frame)
    click(app, "Compare screening plans")
    settings = dict(app.session_state["comparison_settings"])
    app.text_input(key="queue_search").set_value("no-such-resident").run(timeout=30)
    assert not app.exception
    assert app.session_state["flow_resident"] is None
    assert app.session_state["comparison_started"]
    assert app.session_state["comparison_settings"] == settings
    assert any("No residents match" in item.value for item in app.info)


@pytest.mark.parametrize("questionnaire", ["No questionnaire", "Missing model answers"])
def test_apply_report_returns_to_resident_and_only_relaxes_conflicting_filters(saved_demo, monkeypatch, questionnaire):
    _, directory, _ = saved_demo
    app = open_demo(saved_demo, monkeypatch)
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    person = choose_resident(app, frame)
    original_files = {name: (directory / name).read_bytes() for name in (
        "deployment_hidden.parquet", "allocations_hidden.parquet", "metrics.csv", "longitudinal_hidden.parquet")}
    app.selectbox(key="flow_municipality").set_value(person.municipality).run(timeout=30)
    app.selectbox(key="queue_questionnaire").set_value(questionnaire).run(timeout=30)
    app.text_input(key="queue_search").set_value(person.resident_id).run(timeout=30)
    access = "Within assumed access limit" if person.nearest_distance_km <= 20 else "Outside assumed access limit"
    app.selectbox(key="queue_access").set_value(access).run(timeout=30)
    click(app, "Compare screening plans")
    settings = dict(app.session_state["comparison_settings"])
    click(app, "Review / correct questionnaire")
    for key, value in (("DM", "Y"), ("HTN", "N"), ("FAM", "N"), ("OUT", "N")):
        app.selectbox(key=f"report_form_{key}").set_value(value)
    app.text_input(key="report_form_hours").set_value("")
    click(app, "Preview this report's effect")
    assert app.session_state["flow_resident"] == person.resident_id
    assert app.session_state["queue_questionnaire"] == questionnaire
    assert not app.session_state["applied_reports"]
    preview_score = metric(app, "Score after report")
    click(app, "Apply report & return to workspace")
    assert app.session_state["workspace_tab"] == "Plan"
    assert app.session_state["flow_resident"] == person.resident_id
    assert app.session_state["queue_questionnaire"] == "All questionnaires"
    assert app.session_state["queue_search"] == person.resident_id
    assert app.session_state["queue_access"] == access
    assert app.session_state["flow_municipality"] == person.municipality
    assert app.session_state["comparison_settings"] == settings
    assert metric(app, "This resident's score") == preview_score
    assert any("Reset filters" in item.value and "Questionnaire" in item.value for item in app.success)
    assert "flow_report_handoff" not in app.session_state
    for name, data in original_files.items():
        assert (directory / name).read_bytes() == data


def test_invalid_report_cannot_change_current_plan(saved_demo, monkeypatch):
    _, directory, _ = saved_demo
    app = open_demo(saved_demo, monkeypatch)
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    choose_resident(app, frame)
    click(app, "Compare screening plans")
    before = metric(app, "This resident's score"), metric(app, "Invitation in the current plan")
    click(app, "Review / correct questionnaire")
    app.text_input(key="report_form_hours").set_value("200")
    click(app, "Preview this report's effect")
    assert not app.session_state["applied_reports"]
    assert not app.session_state.get("report_result")
    assert any("HRS" in item.value for item in app.error)
    assert (metric(app, "This resident's score"), metric(app, "Invitation in the current plan")) == before


def test_applying_report_before_planning_does_not_assign_invitations(saved_demo, monkeypatch):
    _, directory, _ = saved_demo
    app = open_demo(saved_demo, monkeypatch)
    choose_resident(app, pd.read_parquet(directory / "deployment_hidden.parquet"))
    click(app, "Review / correct questionnaire")
    app.selectbox(key="report_form_DM").set_value("Y")
    click(app, "Preview this report's effect")
    click(app, "Apply report & return to workspace")
    assert app.session_state["applied_reports"]
    assert not app.session_state["comparison_started"]
    assert metric(app, "Invitation in the current plan") == "Not planned"
    assert next(item for item in app.get("download_button") if item.proto.label == "Download whole-plan invitation preview").proto.disabled


def test_infeasible_request_hides_previous_decisions_and_disables_export(saved_demo, monkeypatch):
    from agap.experiment import CoverageInfeasibleError
    _, directory, _ = saved_demo
    app = open_demo(saved_demo, monkeypatch)
    choose_resident(app, pd.read_parquet(directory / "deployment_hidden.parquet"))
    click(app, "Compare screening plans")

    def infeasible(*args, **kwargs):
        raise CoverageInfeasibleError("Shared service capacity cannot meet the municipal floors")

    monkeypatch.setattr(agap.walkthrough, "plans_at", infeasible)
    app.slider(key="panel_budget").set_value(1)
    click(app, "Compare screening plans")
    assert any("Shared service capacity" in item.value for item in app.error)
    assert metric(app, "Invitation in the current plan") == "Unavailable"
    assert any("Plan unavailable" in item.value for item in app.warning)
    assert next(item for item in app.get("download_button") if item.proto.label == "Download whole-plan invitation preview").proto.disabled


def test_live_evidence_and_category_inspector_use_active_model(saved_demo, monkeypatch):
    _, directory, cfg = saved_demo
    captures = {}
    build_map = agap.walkthrough.community_figure
    build_municipal_map = agap.walkthrough.municipal_map
    count_bottlenecks = agap.walkthrough.bottleneck_counts

    def capture_map(queue, *args, **kwargs):
        captures["queue"] = queue.copy()
        return build_map(queue, *args, **kwargs)

    def capture_counts(policies):
        captures["policies"] = policies
        return count_bottlenecks(policies)

    def capture_municipal_map(summary, *args, **kwargs):
        captures["municipal_summary"] = summary.copy()
        return build_municipal_map(summary, *args, **kwargs)

    monkeypatch.setattr(agap.walkthrough, "community_figure", capture_map)
    monkeypatch.setattr(agap.walkthrough, "bottleneck_counts", capture_counts)
    monkeypatch.setattr(agap.walkthrough, "municipal_map", capture_municipal_map)
    originals = {name: (directory / name).read_bytes() for name in (
        "deployment_hidden.parquet", "allocations_hidden.parquet", "metrics.csv", "longitudinal_hidden.parquet")}
    app = open_demo(saved_demo, monkeypatch)
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    person = choose_resident(app, frame)
    app.slider(key="panel_budget").set_value(100)
    click(app, "Compare screening plans")
    model = joblib.load(directory / "model_clinical.joblib")
    expected_scores = pd.Series(model.predict_proba(frame[list(model.feature_names_in_)])[:, 1], index=frame.resident_id)
    mapped = captures["queue"].set_index("resident_id").score.reindex(frame.resident_id)
    pd.testing.assert_series_equal(mapped, expected_scores, check_names=False)
    app.selectbox(key="map_metric").set_value("Mean screening score").run(timeout=30)
    assert not app.exception
    assert "Mean hot–dry score" not in app.selectbox(key="map_metric").options
    pd.testing.assert_series_equal(
        captures["municipal_summary"].set_index("municipality").value,
        captures["queue"].groupby("municipality").score.mean(), check_names=False)
    app.radio(key="eval_category").set_value(BUCKETS[2]).run(timeout=30)
    assert not app.exception
    label = app.session_state["eval_policy"]
    records = captures["policies"][label]
    expected_ids = set(records.loc[evaluation_mask(records, BUCKETS[2]), "resident_id"])
    tables = [item.value for item in app.dataframe if {"reason", "assigned_km"} <= set(item.value)]
    assert (set(tables[0].resident_id) if tables else set()) == expected_ids
    app.radio(key="eval_category").set_value("All invited").run(timeout=30)
    selector = next(item for item in app.selectbox if item.label == "Evaluation resident to inspect")
    resident_id = selector.options[0]
    selector.set_value(resident_id).run(timeout=30)
    click(app, "Inspect evaluation resident in planner")
    assert app.session_state["flow_resident"] == resident_id
    assert app.session_state["flow_municipality"] == frame.set_index("resident_id").loc[resident_id, "municipality"]
    for name, content in originals.items():
        assert (directory / name).read_bytes() == content


def test_malformed_sms_and_cross_channel_duplicate_are_visible_in_history(saved_demo, monkeypatch):
    root, directory, _ = saved_demo
    app = open_demo(saved_demo, monkeypatch)
    person = choose_resident(app, pd.read_parquet(directory / "deployment_hidden.parquet"))
    click(app, "Compare screening plans")
    click(app, "Review / correct questionnaire")
    for key, value in (("DM", "N"), ("HTN", "U"), ("FAM", "U"), ("OUT", "Y"), ("PRIOR", "N")):
        app.selectbox(key=f"report_form_{key}").set_value(value)
    app.text_input(key="report_form_hours").set_value("37")
    click(app, "Preview this report's effect")
    click(app, "Apply report & return to workspace")
    path = root / "data/reports/citizen_reports.jsonl"
    first = resident_history(path, person.resident_id)[-1]
    app.radio(key="report_form_transport").set_value("SMS-style text").run(timeout=30)
    app.text_area(key="report_form_sms").set_value(f"AGAP {person.resident_id} {int(person.age)} DM:Y DM:N")
    click(app, "Validate & preview report")
    rejected = resident_history(path, person.resident_id)[-1]
    assert not rejected["valid"] and rejected["resident_id"] == person.resident_id
    assert any("duplicate field" in item.value for item in app.error)
    assert app.session_state["applied_reports"][person.resident_id]["DM"] == "N"
    today = pd.Timestamp.today().date().isoformat()
    app.text_area(key="report_form_sms").set_value(f"AGAP {person.resident_id} {int(person.age)} DM:Y HTN:U FAM:U OUT:Y PRIOR:N HRS:37 DATE:{today}")
    click(app, "Validate & preview report")
    correction = resident_history(path, person.resident_id)[-1]
    assert correction["supersedes"] == first["report_id"]
    click(app, "Apply report & return to workspace")
    before = path.read_bytes()
    app.radio(key="report_form_transport").set_value("Simple form").run(timeout=30)
    click(app, "Preview this report's effect")
    assert path.read_bytes() == before
    assert any("duplicate submission ignored" in item.value for item in app.info)


def test_plan_step_offers_the_municipal_map_with_a_fixture_fallback(saved_demo, monkeypatch):
    app = open_demo(saved_demo, monkeypatch)
    assert not app.exception
    click(app, "Compare screening plans")
    assert not app.exception
    app.selectbox(key="map_metric").set_value("Mean screening score").run(timeout=30)
    assert not app.exception
    assert any("no map is shown" in item.value for item in app.caption)  # fixture zones have no real polygons


def test_requested_climate_profile_cannot_display_a_synthetic_run(saved_demo, monkeypatch):
    requested = copy.deepcopy(saved_demo[2])
    requested["climate"] = dict(mode="era5_land", processed_directory="data/processed/climate/laguna")
    app = open_demo(saved_demo, monkeypatch, requested)
    assert not app.exception
    assert not app.tabs
    assert any("another setup" in item.value for item in app.info)
    assert any("Prepare the historical climate inputs first" in item.value for item in app.info)


def test_weather_exploration_cannot_change_main_scores_or_invitations(saved_demo, monkeypatch):
    """Controlled weather fixture: an in-range date has no data for this person."""
    _, directory, _ = saved_demo
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    first_area = sorted(frame.municipality.unique())[0]
    person = frame.loc[frame.municipality.eq(first_area)].sort_values(["reported", "resident_id"]).iloc[0]
    cutoff = pd.Timestamp(person.cutoff)
    middle, end = cutoff + pd.Timedelta(days=1), cutoff + pd.Timedelta(days=2)
    exposure = pd.DataFrame(dict(
        era5_cell=[person.era5_cell, "another-source-cell", person.era5_cell],
        cutoff=[cutoff, middle, end], complete=True, hot_dry_score=[person.hot_dry_score, 0., 2.],
        preceding_tmean_c=26., preceding_precip_mm=100.,
    ))
    daily = pd.DataFrame(dict(era5_cell=person.era5_cell,
        local_date=pd.date_range(cutoff-pd.Timedelta(days=30), cutoff-pd.Timedelta(days=1)),
        tmean_c=26., tmax_c=31., precip_mm=3.))
    climate = dict(model=joblib.load(directory / "model_climate.joblib"), exposure=exposure,
                   daily=daily, metadata=dict(baseline_start=1991, baseline_end=2020))
    monkeypatch.setattr(agap.climate_demo, "load_climate_preview", lambda path: climate)
    app = open_demo(saved_demo, monkeypatch)
    assert not app.exception
    choose_resident(app, frame)
    click(app, "Compare screening plans")
    selected = app.session_state["flow_resident"]
    score, invitation = metric(app, "This resident's score"), metric(app, "Invitation in the current plan")
    click(app, "View resident weather")
    app.checkbox(key="flow_explore_date").check().run(timeout=30)
    assert not app.exception
    app.date_input(key="flow_weather_date").set_value(middle.date()).run(timeout=30)
    assert not app.exception
    assert any("No complete weather window for this resident" in item.value for item in app.warning)
    assert app.session_state["flow_resident"] == selected
    assert metric(app, "This resident's score") == score
    assert metric(app, "Invitation in the current plan") == invitation
    app.date_input(key="flow_weather_date").set_value(end.date()).run(timeout=30)
    assert not app.exception
    assert metric(app, "This resident's score") == score
    assert metric(app, "Invitation in the current plan") == invitation


def test_baseline_free_weather_context_does_not_change_scores(saved_demo, monkeypatch):
    from agap.climate.available import weather_windows
    _, directory, _ = saved_demo
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    person = frame.loc[frame.municipality.eq(sorted(frame.municipality.unique())[0])].sort_values(["reported", "resident_id"]).iloc[0]
    dates = pd.date_range('2023-12-01', '2024-01-31')
    daily = pd.DataFrame(dict(era5_cell=person.era5_cell, local_date=dates, tmean_c=26., tmax_c=31.,
                             precip_mm=2., temperature_hours=24, precipitation_hours=24))
    weather = dict(daily=daily, windows=weather_windows(daily, '2024-01-01', '2024-01-31'),
                   metadata=dict(requested_start='2024-01-01', requested_end='2024-01-31', supported_cell_count=1, source_cell_count=2))
    monkeypatch.setattr(agap.climate.available, 'load_weather_preview', lambda path: weather)
    app = open_demo(saved_demo, monkeypatch)
    assert not app.exception
    choose_resident(app, frame)
    click(app, 'Compare screening plans')
    click(app, "View resident weather")
    assert metric(app, 'Mean temperature · 30 days') == '26.0 °C'
    assert metric(app, 'Rainfall · 30 days') == '60 mm'
    assert any('saved screening date' in item.value.lower() and 'questionnaire-only' in item.value for item in app.info)
    assert any('Automatic historical fallback' in item.value for item in app.info)
    score, invitation = metric(app, "This resident's score"), metric(app, 'Invitation in the current plan')
    app.date_input(key='flow_context_date').set_value(pd.Timestamp('2024-01-15').date()).run(timeout=30)
    app.radio(key='flow_context_days').set_value(7).run(timeout=30)
    assert not app.exception
    assert metric(app, 'Rainfall · 7 days') == '14 mm'
    assert metric(app, "This resident's score") == score
    assert metric(app, 'Invitation in the current plan') == invitation
    assert not any(item.label == 'Questionnaire + public climate model' for item in app.metric)


def test_weather_alternate_date_does_not_claim_saved_coverage_is_missing(saved_demo, monkeypatch):
    from agap.climate.available import weather_windows
    _, directory, _ = saved_demo
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    person = frame.loc[frame.municipality.eq(sorted(frame.municipality.unique())[0])].sort_values(["reported", "resident_id"]).iloc[0]
    saved = pd.Timestamp(person.cutoff).normalize()
    daily = pd.DataFrame(dict(era5_cell=person.era5_cell,
        local_date=pd.date_range(saved-pd.Timedelta(days=30), saved+pd.Timedelta(days=9)),
        tmean_c=26., tmax_c=31., precip_mm=2., temperature_hours=24, precipitation_hours=24))
    windows = weather_windows(daily, saved, saved+pd.Timedelta(days=9))
    gap = saved+pd.Timedelta(days=5)
    windows.loc[windows.cutoff.eq(gap), "complete_30d"] = False
    weather = dict(daily=daily, windows=windows,
                   metadata=dict(requested_start=str(saved.date()), requested_end=str((saved+pd.Timedelta(days=9)).date()),
                                 supported_cell_count=1, source_cell_count=1))
    monkeypatch.setattr(agap.climate.available, "load_weather_preview", lambda path: weather)
    app = open_demo(saved_demo, monkeypatch)
    choose_resident(app, frame)
    click(app, "Compare screening plans")
    click(app, "View resident weather")
    assert any("matches the saved screening date" in item.value for item in app.info)
    before = metric(app, "This resident's score"), metric(app, "Invitation in the current plan")
    chosen = (saved+pd.Timedelta(days=2)).date()
    app.date_input(key="flow_context_date").set_value(chosen).run(timeout=30)
    assert not app.exception
    assert any("also available at the saved screening date" in item.value for item in app.info)
    assert not any("Automatic historical fallback" in item.value for item in app.info)
    app.radio(key="flow_context_days").set_value(7).run(timeout=30)
    assert app.date_input(key="flow_context_date").value == chosen
    assert metric(app, "Rainfall · 7 days") == "14 mm"
    app.radio(key="flow_context_days").set_value(30).run(timeout=30)
    app.date_input(key="flow_context_date").set_value(gap.date()).run(timeout=30)
    assert not app.exception
    assert any("window is incomplete" in item.value for item in app.warning)
    assert not any(item.label == "Mean temperature · 30 days" for item in app.metric)
    assert (metric(app, "This resident's score"), metric(app, "Invitation in the current plan")) == before
    assert app.session_state["flow_resident"] == person.resident_id


def test_run_summary_names_scenario_sources_and_run():
    cfg = load_config("config/climate.yaml")
    cfg["prototype"].update(mechanism="MNAR", heat_or=1.5)
    summary = run_summary(dict(configuration=cfg, climate_mode="era5_land", run_id="abc-123", repetition=4,
                               started_utc="2026-10-18T13:20:05+00:00"), "ignored")
    assert summary["scenario"] == "MNAR missingness · assumed heat odds ratio 1.5"
    assert summary["sources"] == "public WorldPop and boundary data · ERA5-Land historical climate"
    assert summary["run_id"] == "abc-123" and summary["repetition"] == 4 and summary["started"] == "2026-10-18 13:20 UTC"
    fixture = run_summary(dict(configuration=load_config()), "run-folder")
    assert fixture["sources"] == "illustrative fixture geography · synthetic fixture climate" and fixture["run_id"] == "run-folder"


def test_map_toggle_stable_status_and_optional_explanation_preserve_resident_and_explicit_submit(saved_demo, monkeypatch):
    _, directory, _ = saved_demo
    app = open_demo(saved_demo, monkeypatch)
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    person = choose_resident(app, frame)
    queue = next(table.value for table in app.dataframe if "display_status" in table.value)
    assert "No report · Unplanned" in set(queue.display_status)
    assert not next(expander for expander in app.expander if expander.label == "Why this score?").proto.expanded
    assert any(item.key == "community_map" for item in app.get("plotly_chart"))
    assert not app.get("deck_gl_json_chart")
    app.radio(key="flow_map_mode").set_value("3D H3 hex map").run(timeout=30)
    assert not app.exception
    assert len(app.get("deck_gl_json_chart")) == 1
    assert not any(item.key == "community_map" for item in app.get("plotly_chart"))
    assert app.session_state["flow_resident"] == person.resident_id
    app.radio(key="flow_map_mode").set_value("2D community map").run(timeout=30)
    assert not app.exception and not app.get("deck_gl_json_chart")
    assert app.session_state["flow_resident"] == person.resident_id
    click(app, "Compare screening plans")
    settings = dict(app.session_state["comparison_settings"])
    app.slider(key="panel_budget").set_value(40)
    assert app.session_state["comparison_settings"] == settings
    queue = next(table.value for table in app.dataframe if "display_status" in table.value)
    assert not queue.display_status.str.contains("Unplanned").any()
    assert queue.display_status.str.startswith(("No report", "Partial", "Complete")).all()
    click(app, "Compare screening plans")
    assert app.session_state["comparison_settings"]["budget"] == 40


def test_visibility_gap_area_and_month_controls_use_saved_samples_after_report_edit(saved_demo, monkeypatch):
    import agap.visuals
    _, directory, _ = saved_demo
    original = (directory / "surveillance_monthly.parquet").read_bytes()
    monthly = pd.read_parquet(directory / "surveillance_monthly.parquet")
    captures = []
    build = agap.visuals.visibility_gap_figure

    def capture(data, area, month):
        figure = build(data, area, month)
        captures.append((area, pd.Timestamp(month), [trace.x[0] for trace in figure.data]))
        return figure

    monkeypatch.setattr(agap.visuals, "visibility_gap_figure", capture)
    app = open_demo(saved_demo, monkeypatch)
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    person = choose_resident(app, frame)
    app.selectbox(key="surveillance_area").set_value(person.municipality).run(timeout=30)
    months = sorted(pd.to_datetime(monthly.loc[monthly.municipality.eq(person.municipality), "month"]).unique())
    assert pd.Timestamp(app.select_slider(key="surveillance_month").value) == pd.Timestamp(months[-1])
    app.select_slider(key="surveillance_month").set_value(pd.Timestamp(months[0])).run(timeout=30)
    assert not app.exception
    area, month, counts = captures[-1]
    row = monthly.loc[monthly.municipality.eq(area) & pd.to_datetime(monthly.month).eq(month)].iloc[0]
    assert counts == [row.observed_abnormal, row.hidden_undetected_abnormal]
    before = captures[-1]
    click(app, "Review / correct questionnaire")
    app.selectbox(key="report_form_DM").set_value("Y")
    click(app, "Preview this report's effect")
    click(app, "Apply report & return to workspace")
    assert captures[-1] == before
    assert (directory / "surveillance_monthly.parquet").read_bytes() == original


def test_fixture_runs_offer_only_the_outline_map_and_map_views_preserve_the_plan(saved_demo, monkeypatch):
    _, directory, _ = saved_demo
    app = open_demo(saved_demo, monkeypatch)
    person = choose_resident(app, pd.read_parquet(directory / "deployment_hidden.parquet"))
    click(app, "Compare screening plans")
    before = metric(app, "This resident's score"), metric(app, "Invitation in the current plan")
    settings = dict(app.session_state["comparison_settings"])
    basemap = app.selectbox(key="flow_basemap")
    # Illustrative fixture zones must never be drawn over real streets.
    assert basemap.options == ["Outline map"] and basemap.disabled and basemap.value == "Outline map"
    assert not app.get("deck_gl_json_chart")
    app.radio(key="flow_map_mode").set_value("3D H3 hex map").run(timeout=30)
    assert not app.exception and len(app.get("deck_gl_json_chart")) == 1
    assert app.session_state["comparison_settings"] == settings
    assert app.session_state["flow_resident"] == person.resident_id
    assert (metric(app, "This resident's score"), metric(app, "Invitation in the current plan")) == before


def test_model_switch_updates_scores_exports_and_report_previews_on_one_unchanged_cohort(saved_demo, monkeypatch):
    root, directory, cfg = saved_demo
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    clinical_model = joblib.load(directory / "model_clinical.joblib")
    climate_model = joblib.load(directory / "model_climate.joblib")
    exposure = frame[["era5_cell", "cutoff", "hot_dry_score"]].drop_duplicates(["era5_cell", "cutoff"]).assign(
        complete=True, preceding_tmean_c=30., preceding_precip_mm=100.)
    daily = pd.DataFrame(columns=["era5_cell", "local_date", "tmean_c", "tmax_c", "precip_mm"])
    connected = dict(model=climate_model, exposure=exposure, daily=daily,
                     metadata=dict(baseline_start=1991, baseline_end=2020))
    monkeypatch.setattr(agap.climate_demo, "load_climate_preview", lambda path: connected)
    captures = []
    original_export = agap.walkthrough.invitation_export
    def capture(*args):
        result = original_export(*args)
        captures.append(result)
        return result
    monkeypatch.setattr(agap.walkthrough, "invitation_export", capture)
    original = {name: (directory / name).read_bytes() for name in (
        "deployment_hidden.parquet", "model_clinical.joblib", "model_climate.joblib", "predictions.parquet")}
    app = open_demo(saved_demo, monkeypatch)
    assert not app.exception and app.session_state["flow_model"] == "clinical"
    app.selectbox(key="flow_model").set_value("climate").run(timeout=30)
    person = choose_resident(app, frame)
    click(app, "Compare screening plans")
    settings = dict(app.session_state["comparison_settings"])
    assert any(item.value == "Climate impact on invitations" for item in app.subheader)
    app.selectbox(key="flow_model").set_value("clinical").run(timeout=30)
    assert not app.exception and app.session_state["flow_resident"] == person.resident_id
    assert app.session_state["comparison_settings"] == settings
    score = clinical_model.predict_proba(frame.loc[frame.resident_id.eq(person.resident_id), list(clinical_model.feature_names_in_)])[0, 1]
    assert metric(app, "This resident's score") == f"{score:.1%}"
    assert captures[-1].model.eq("clinical").all()
    click(app, "Review / correct questionnaire")
    app.selectbox(key="report_form_DM").set_value("Y")
    click(app, "Preview this report's effect")
    assert metric(app, "Score before report") == f"{score:.1%}"
    app.selectbox(key="flow_model").set_value("climate").run(timeout=30)
    climate_score = climate_model.predict_proba(frame.loc[frame.resident_id.eq(person.resident_id), list(climate_model.feature_names_in_)])[0, 1]
    assert not app.exception and metric(app, "Score before report") == f"{climate_score:.1%}"
    expected_after = metric(app, "Score after report")
    click(app, "Apply report & return to workspace")
    assert metric(app, "This resident's score") == expected_after
    assert app.session_state["flow_resident"] == person.resident_id
    assert app.session_state["comparison_settings"] == settings
    assert captures[-1].model.eq("climate").all()
    assert not {"y_true", "positive_detected", "completed"} & set(captures[-1])
    for name, data in original.items():
        assert (directory / name).read_bytes() == data


def test_weather_decision_and_model_controls_preserve_the_actual_plan(saved_demo, monkeypatch):
    from agap.climate_demo import score_cohort
    from agap.model_comparison import compare_models
    _, directory, cfg = saved_demo
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    clinical = joblib.load(directory / "model_clinical.joblib")
    climate_model = joblib.load(directory / "model_climate.joblib")
    exposure = frame[["era5_cell", "cutoff", "hot_dry_score"]].drop_duplicates(["era5_cell", "cutoff"]).assign(
        complete=True, preceding_tmean_c=26., preceding_precip_mm=90.)
    choose_area = sorted(frame.municipality.unique())[0]
    person = frame.loc[frame.municipality.eq(choose_area)].sort_values(["reported", "resident_id"]).iloc[0]
    daily = pd.DataFrame(dict(era5_cell=person.era5_cell,
        local_date=pd.date_range(pd.Timestamp(person.cutoff)-pd.Timedelta(days=30), periods=30),
        tmean_c=26., tmax_c=31., precip_mm=3.))
    connected = dict(model=climate_model, exposure=exposure, daily=daily, metadata=dict(baseline_start=1991, baseline_end=2020))
    monkeypatch.setattr(agap.climate_demo, "load_climate_preview", lambda path: connected)
    app = open_demo(saved_demo, monkeypatch)
    person = choose_resident(app, frame)
    click(app, "View resident weather")
    assert any("Invitations not planned" in item.value for item in app.markdown)
    click(app, "Compare screening plans")
    settings = dict(app.session_state["comparison_settings"])
    comparison = compare_models(score_cohort(frame, clinical, climate_model), pd.read_parquet(directory / "facilities.parquet"), cfg, **settings)
    expected = comparison["decisions"].set_index("resident_id").loc[person.resident_id]
    actual = next(item.value for item in app.markdown if 'class="agap-model-shift"' in item.value)
    for variant in ("clinical", "climate"):
        assert f'{expected[f"{variant}_score"]:.1%}' in actual
    unchanged = expected.clinical_invited == expected.climate_invited
    assert ("Invitation unchanged" if unchanged else f'Invitation {"added" if expected.climate_invited else "removed"} with climate') in actual
    assert any(item.key == "screening_weather_timeline" for item in app.get("plotly_chart"))
    app.radio(key="flow_weather_model").set_value("clinical").run(timeout=30)
    assert not app.exception
    assert app.session_state["flow_model"] == "clinical" and app.session_state["workspace_tab"] == "Resident weather"
    assert app.session_state["flow_resident"] == person.resident_id and app.session_state["comparison_settings"] == settings
    assert metric(app, "Invitation in the current plan") == ("Yes" if expected.clinical_invited else "No")
    click(app, "Show in Plan")
    assert app.session_state["workspace_tab"] == "Plan" and app.session_state["workspace_panel"] == "Decision"
    assert app.session_state["flow_municipality"] in ("All municipalities", choose_area)
    assert app.session_state["flow_resident"] == person.resident_id


def test_clinic_evidence_can_be_saved_without_changing_the_experiment(saved_demo, monkeypatch):
    from datetime import date
    from agap.clinics import read_verifications
    root, directory, _ = saved_demo
    public = root / "data/processed/public/laguna"
    public.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(dict(source_row=[1756, 1757], facility_name=["Fixture clinic A", "Fixture clinic B"], source_page=[69, 69])).to_csv(
        public / "clinic_verification_queue.csv", index=False)
    before = (directory / "facilities.parquet").read_bytes()
    app = open_demo(saved_demo, monkeypatch)
    assert not app.exception and metric(app, "Ready for pilot review") == "0"
    click(app, "Save clinic verification")
    assert any("at least one checked fact" in item.value for item in app.error)
    for label, value in (("Verified latitude", "14.2"), ("Verified longitude", "121.2"),
                          ("Complete screening panels per screening round", "10"),
                          ("Verification evidence / source", "Fixture verification reference")):
        next(item for item in app.text_input if item.label == label).set_value(value)
    next(item for item in app.selectbox if item.label == "Creatinine availability").set_value("Available")
    next(item for item in app.selectbox if item.label == "uACR availability").set_value("Available")
    next(item for item in app.date_input if item.label == "Date checked").set_value(date(2026, 10, 20))
    click(app, "Save clinic verification")
    assert metric(app, "Ready for pilot review") == "1"
    records = read_verifications(root / "data/reports/clinic_verifications.sqlite3")
    assert len(records) == 1
    assert (directory / "facilities.parquet").read_bytes() == before
    app.selectbox(key="clinic_to_verify").set_value("YAKAP-20260930-1757").run(timeout=30)
    assert not app.exception
    assert next(item for item in app.text_input if item.label == "Verified latitude").value == ""


def test_citizen_view_shows_status_and_information_without_scores(saved_demo, monkeypatch):
    app = open_demo(saved_demo, monkeypatch)
    assert any("Fictional geography" in item.value for item in app.warning)
    sign_in(app, "Citizen")
    assert not app.exception
    text = " ".join(item.value for item in app.markdown) + " ".join(item.value for item in app.caption)
    assert "My kidney screening" in " ".join(item.value for item in app.subheader)
    assert "not a diagnosis" in text and not app.metric
    assert not any("score" in item.value.lower() for item in app.markdown)


def test_lgu_view_shows_only_suppressed_aggregates(saved_demo, monkeypatch):
    app = open_demo(saved_demo, monkeypatch)
    sign_in(app, "LGU / public-health analyst")
    assert not app.exception
    table = app.dataframe[0].value
    assert "Municipality" in table.columns and "resident_id" not in table.columns
    assert any("Evidence: synthetic simulation" in item.value for item in app.caption)


def test_app_opens_on_a_simulated_sign_in_screen_and_sign_out_returns_there(saved_demo, monkeypatch):
    st.cache_resource.clear()
    root, _, cfg = saved_demo
    monkeypatch.setattr(agap.config, "ROOT", root)
    monkeypatch.setattr(agap.config, "load_config", lambda path=None: cfg)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/main.py")).run(timeout=30)
    assert not app.exception and "Sign in" in [item.value for item in app.subheader]
    assert {button.label for button in app.button} >= {"Sign in as Health worker (RHU)", "Sign in as Citizen"}
    assert not app.tabs
    sign_in(app, "LGU / public-health analyst")
    assert any("Signed in as **LGU / public-health analyst**" in item.value for item in app.sidebar.markdown)
    click(app, "Sign out")
    assert "Sign in" in [item.value for item in app.subheader]


def test_citizen_reporting_dialysis_is_routed_out_of_first_screening(saved_demo, monkeypatch):
    root, directory, _ = saved_demo
    app = open_demo(saved_demo, monkeypatch)
    sign_in(app, "Citizen")
    resident = app.selectbox(key="citizen_profile").value
    app.radio[0].set_value("Receiving dialysis")
    click(app, "Save my answers")
    assert any("known kidney diagnosis" in item.value for item in app.info)
    sign_in(app, "Health worker (RHU)")
    click(app, "Compare screening plans")
    app.selectbox(key="flow_resident").set_value(resident).run(timeout=30)
    assert not app.exception
    assert any("Citizen-submitted profile" in item.label for item in app.expander)
    assert any("Reported known CKD" in str(item.value) for item in app.markdown)
    (root / "data/reports" / directory.name / "citizen_profiles.jsonl").unlink()


def test_plan_page_keeps_simulated_outcomes_on_the_evaluate_page(saved_demo, monkeypatch):
    app = open_demo(saved_demo, monkeypatch)
    click(app, "Compare screening plans")
    plan = next(tab for tab in app.tabs if tab.label == "Plan")
    evaluate = next(tab for tab in app.tabs if tab.label == "Evaluate")
    hidden = "Abnormal initial results found"
    assert not [item for item in plan.metric if item.label == hidden]
    assert [item for item in evaluate.metric if item.label == hidden]
    assert any("panels assigned" in item.value for item in plan.markdown)
    assert any("SIMULATION TRUTH" in item.value for item in evaluate.markdown)
    click(app, "Evaluate this plan with simulated outcomes")
    assert app.session_state["workspace_tab"] == "Evaluate"
