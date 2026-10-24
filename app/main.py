"""Synthetic screening planning and staff coordination over a saved cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml

from agap.config import ROOT, load_config
from agap.climate.integration import BASELINE_YEARS, PARTITION_DATES
from agap.climate_demo import load_climate_preview
from agap.climate.available import load_weather_preview
from agap.clinic_ui import render_clinic_verification
from agap.demo import load_demo, run_summary
from agap.decision_support import evidence_scorecard
from agap.experiment import execute, fingerprint, source_hash
from agap.provenance import deployment_period, geography_banner, geography_label, provenance_caption
from agap.role_views import ROLES, account_sidebar, render_citizen, render_lgu_overview, sign_in_screen, signed_in_role
from agap.walkthrough import render_walkthrough
from agap.research import (
    CRITERIA as RESEARCH_CRITERIA, LABEL as RESEARCH_LABEL, RULE_VERSION, STATES as RESEARCH_STATES,
    comparison_cohort, current_states, eligibility, read_events, reasons as research_reasons, record_event, simulate_interest,
)
from agap.surveillance import LABEL as SURVEILLANCE_LABEL, PROVINCE, TARGET, forecast_gains
from agap.visuals import visibility_gap_figure

st.set_page_config(page_title="AGAP-CKD · Screening coordinator", page_icon="A", layout="wide", initial_sidebar_state="auto")
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--config", default=None)
arguments, _ = parser.parse_known_args(sys.argv[1:])
cfg = load_config(arguments.config)

st.html(Path(__file__).parent / "workspace.css")
st.html('<header class="agap-brand"><span class="agap-mark">A</span><strong>AGAP-CKD</strong>'
            '<h1>Community screening workspace</h1></header>')
st.html('<div class="agap-disclaimer" role="note"><b>Synthetic demo</b><span>Residents and results are simulated</span>'
        '<span>A screening flag is not a diagnosis</span><span>Climate is a community-level proxy</span>'
        '<span>Service points are hypothetical</span></div>')
if geography_banner(cfg):
    st.warning(geography_banner(cfg))
role = signed_in_role()
if role is None:
    sign_in_screen()
    st.stop()
account_sidebar(role)


def prepare_demo():
    try:
        execute(cfg)
    except (FileNotFoundError, ValueError) as exc:
        st.error(str(exc))
        st.stop()
    st.cache_resource.clear()
    st.cache_data.clear()
    st.rerun()

required = ("manifest.json", "deployment_hidden.parquet", "facilities.parquet", "model_clinical.joblib")
latest = ROOT / "outputs/latest_run.json"
directory = Path(json.loads(latest.read_text())["path"]) if latest.exists() else None
if directory is not None and not all((directory / name).exists() for name in required):
    directory = None
if directory is not None:
    saved_manifest = json.loads((directory / "manifest.json").read_text())
    if saved_manifest["config_hash"] != fingerprint(cfg):
        st.info("The saved run belongs to another setup. Prepare a run for the requested configuration to continue.")
        directory = None
if directory is None:
    st.subheader("Prepare the demonstration")
    st.write("This creates a synthetic community and screening plans. It usually takes a few seconds.")
    if cfg.get("climate", {}).get("mode") == "era5_land":
        climate_folder = ROOT / cfg["climate"].get("processed_directory", "data/processed/climate/laguna")
        if not all((climate_folder / name).exists() for name in ("daily.parquet", "exposure.parquet", "baseline.parquet", "metadata.json")):
            st.info("Prepare the historical climate inputs first with `make prepare-climate` (uses the bundled ARCO extract), then rebuild this profile. Collect climate only if that extract is missing.")
            st.stop()
    if st.button("Prepare demo", type="primary"):
        with st.spinner("Preparing the synthetic community…"):
            prepare_demo()
    st.stop()
manifest = json.loads((directory / "manifest.json").read_text())
active = manifest["configuration"]
run = run_summary(manifest, directory.name)
with st.sidebar, st.expander("Active run and assumptions"):
    st.markdown(f"**Scenario:** {run['scenario']} · **Sources:** {run['sources']} · **Run:** `{run['run_id']}` "
                f"(repetition {run['repetition']}, started {run['started']}) · **{run['status']}**")
if not all(manifest["stages"].get(stage) == "complete" for stage in ("data", "simulate", "train", "allocate", "evaluate")):
    st.error("The demonstration did not finish preparing. Prepare it again to continue.")
    if st.button("Prepare demo", type="primary"):
        prepare_demo()
    st.stop()


@st.cache_resource
def demo_at(path):
    return load_demo(Path(path))


@st.cache_data
def followup_at(path, day=180):
    path = Path(path) / "longitudinal_hidden.parquet"
    if not path.exists():
        return None
    frame = pd.read_parquet(path)
    columns = ["resident_id", "followup_included", "persistent_abnormal", "transient_abnormal",
               f"visit_uniform_{day}d", f"abnormal_{day}d"]
    return frame[[name for name in columns if name in frame]]


@st.cache_data
def surveillance_at(path):
    path = Path(path)
    if not (path / "surveillance_monthly.parquet").exists():
        return None
    return (pd.read_parquet(path / "surveillance_monthly.parquet"), pd.read_parquet(path / "surveillance_forecasts.parquet"),
            pd.read_csv(path / "surveillance_forecast_metrics.csv"), json.loads((path / "surveillance.json").read_text()))


@st.cache_resource
def climate_at(path):
    return load_climate_preview(Path(path))


@st.cache_resource
def weather_at(path):
    return load_weather_preview(Path(path))


frame, facilities, clinical_model, _ = demo_at(str(directory))
climate = climate_at(str(directory))
weather = weather_at(str(directory))
if active.get("weather_preview", {}).get("enabled") and weather is None:
    st.error("This weather-preview run is missing its saved weather files. Run make prepare-weather, then rebuild this profile.")
    st.stop()
if active.get("climate", {}).get("mode") == "era5_land" and climate is None:
    st.error("This climate run is missing weather snapshots or its climate model. Prepare the run again to continue.")
    if st.button("Refresh demo"):
        prepare_demo()
    st.stop()
if manifest["source_hash"] != source_hash():
    st.warning("The saved demonstration uses an earlier setup. Prepare it again to use the current setup.")
    if st.button("Refresh demo"):
        prepare_demo()

if role == ROLES[2]:
    render_citizen(frame, active, ROOT, directory.name, facilities)
    st.stop()
if role == ROLES[1]:
    # Aggregates only: no resident-level worklist, plan or research records.
    overview_tab, surveillance_tab, safeguards_tab, data_tab = st.tabs(["Community overview", "Surveillance", "Safeguards", "Data"])
    with overview_tab:
        render_lgu_overview(frame, active, ROOT, directory.name, directory)
    areas = dict(surveillance=surveillance_tab, safeguards=safeguards_tab, data=data_tab)
    working_frame, selected_resident = frame, None
else:
    areas, working_frame, selected_resident = render_walkthrough(
        frame, facilities, clinical_model, climate, active, directory.name, ROOT,
        followup=followup_at(str(directory), active.get("longitudinal", {}).get("persistence_day", 180)), weather=weather, directory=directory,
    )

with areas["safeguards"]:
    st.subheader("Saved-run engineering safeguards")
    for column, (label, value, detail) in zip(st.columns(4), evidence_scorecard(directory)):
        column.metric(label, value)
        column.caption(detail)
    st.caption("These saved experiment artifacts describe pipeline safeguards, not clinical validation. IPW diagnostics refer to the saved "
               "weighted climate model and spatial diagnostics to the saved allocation model, not the live planner's report-edited "
               "population or model choice.")
    st.subheader("What is real and what is simulated")
    st.markdown("**Working:** validated reporting → draft comparison → approved worklist → recorded contact, specimens and results → review tasks and declined-slot recovery.")
    if active["prototype"]["geography_mode"] == "public":
        st.markdown("**Public inputs:** Laguna boundaries and modeled 2020 population/age–sex surfaces inform the public-geography cohort.")
    else:
        st.markdown("**Geography in this run:** illustrative fixture zones. Public Laguna boundaries and modeled population are used only by the public profile.")
    simulated = "residents, medical outcomes, service locations, capacities, attendance and costs"
    if climate is None:
        simulated += ", and model exposure"
    st.markdown(f"**Simulated inputs:** {simulated}.")
    climate = climate_at(str(directory))
    if climate is None and weather is not None:
        st.markdown(f"**Real weather context is connected:** ERA5-Land hourly temperature and rainfall processed into 7-day and 30-day summaries for {weather['metadata']['requested_start']} to {weather['metadata']['requested_end']}. These run-local files have source checksums. The questionnaire-only model supplies the walkthrough's scores and invitations; the seasonal climate model awaits its reference period.")
        with st.expander("Weather processing and source provenance"):
            st.json(weather["metadata"])
            st.download_button("Download weather provenance", json.dumps(weather["metadata"], indent=2), "weather_metadata.json", "application/json")
    elif climate is None:
        st.markdown("**Climate integration is not present in this saved run:** this is a fixture/questionnaire-only demonstration.")
    else:
        climate_frame_path = directory / "climate_frame.json"
        climate_frame_metadata = json.loads(climate_frame_path.read_text()) if climate_frame_path.exists() else {}
        st.markdown(f"**Climate is connected:** Copernicus ERA5-Land temperatures and rainfall, a {BASELINE_YEARS[0]}–{BASELINE_YEARS[1]} reference, Philippine local-day processing, and the preceding 30 full days inform a second synthetic model. This run represents {climate_frame_metadata.get('modeled_population_fraction_supported', 0):.1%} of modeled WorldPop adults with sufficient climate coverage.")
        st.markdown("**Health outcomes remain synthetic:** the assumed temperature/rainfall effect is set in the simulator, not estimated from patient data. A score difference is not evidence of causation or validated kidney risk.")
    st.markdown("**Clinic verification is unfinished:** the downloaded register provides identities and addresses; it does not establish coordinates or panel availability. The current plan uses hypothetical service points.")
    with st.expander("Technical results and saved experiment details"):
        st.caption("These are the original saved experiment results. What-if reports and panel-budget changes above do not modify them.")
        st.dataframe(pd.read_csv(directory / "model_metrics.csv"), hide_index=True)
        st.caption(provenance_caption(f"saved run {directory.name[:12]} · model_metrics.csv", geography_label(active), deployment_period(),
                                      "AUROC, AUPRC, Brier, calibration (unitless)", "simulation evaluation (hidden truth)"))
        st.json(json.loads((directory / "weight_diagnostics.json").read_text()))
        st.json(manifest)
        st.download_button("Download saved experiment metrics", (directory / "metrics.csv").read_bytes(), "saved_experiment_metrics.csv", "text/csv")

with areas["data"]:
    st.subheader("Clinic verification")
    render_clinic_verification(ROOT, active["study_area"]["pilot_area"])
    st.subheader("Data sources")
    st.caption("Residents are grouped on H3 resolution-8 cells (about 0.74 km²); ERA5-Land climate stays at 0.1° (about 9–11 km). "
               "Access is straight-line distance; the street map is display only and does not verify routes or laboratory capability.")
    source_file = ROOT / "data/manifest.yaml"
    if source_file.exists():
        sources = yaml.safe_load(source_file.read_text())["datasets"]
        with st.expander(f"{len(sources)} collected source files, with checksums and limitations"):
            for source in sources:
                st.markdown(f"[{source['id']}]({source['url']}) — {source.get('limitations','')}")
    if role == ROLES[0]:  # individual-level research interest stays in the health-worker view
        st.subheader("Research interest (demo)")
        with st.container(key="research_demo"):
            st.warning(RESEARCH_LABEL)
            st.write("Voluntary interest is separate from screening: nothing here changes scores, invitations or allocation priority.")
            st.caption("This optional research example uses the applied session answers. Research interest never changes screening priority.")
            checks = eligibility(working_frame).set_index("resident_id")
            events_file = ROOT / "data/reports" / directory.name / "research_events.jsonl"
            manual = read_events(events_file)
            states = current_states(simulate_interest(working_frame, active, manifest.get("repetition", 0)), manual)
            st.markdown(f"**Eligibility rule {RULE_VERSION}:** " + "; ".join(label for _, label in RESEARCH_CRITERIA)
                        + ". Uses reported answers only; 'Unknown' or no report never counts as yes.")
            if selected_resident is None:
                st.info("Select a resident on the Plan page to inspect or record research interest.")
            else:
                resident_id = selected_resident
                st.write(f"**Following {resident_id}** — the same resident selected on the Plan page.")
                row = checks.loc[resident_id]
                st.write(f"**{'Eligible' if row.eligible else 'Not eligible'}** under rule {RULE_VERSION}: " + " · ".join(research_reasons(row)))
                st.write(f"Current research-interest state: **{states.get(resident_id, 'not expressed')}**")
                new_state = st.selectbox("Record a new state", RESEARCH_STATES, key="research_state")
                if st.button("Save research-interest state"):
                    record_event(events_file, resident_id, new_state, row.eligible)
                    st.rerun()
            summary = states.reindex(frame.resident_id).fillna("not expressed").value_counts()
            st.caption("Current states in this cohort (simulated interest plus manual changes): "
                       + ", ".join(f"{state} {int(summary.get(state, 0)):,}" for state in RESEARCH_STATES))
            cohort = comparison_cohort(working_frame, states, active["seed"] + 500)
            st.markdown("**Comparison cohort:** residents reporting outdoor work matched 1:1 by age band and sex with residents reporting none. "
                        "Only eligible residents whose latest state is 'interested' are drawn; declined and withdrawn residents are excluded.")
            if cohort.empty:
                st.info("No matched pairs are available under the current states.")
            else:
                st.dataframe(cohort.groupby(["age_band", "sex", "group"]).size().unstack("group", fill_value=0).reset_index(), hide_index=True)
                st.download_button("Export comparison cohort (synthetic demonstration)", cohort.to_csv(index=False), "research_comparison_cohort.csv", "text/csv")
            if len(manual):
                st.caption("Audit history of manual state changes (append-only; withdrawal never deletes history):")
                st.dataframe(manual, hide_index=True)

with areas["surveillance"]:
    st.subheader("Monthly synthetic screening surveillance")
    st.caption(SURVEILLANCE_LABEL)
    surveillance = surveillance_at(str(directory))
    if surveillance is None or "candidate_no_climate" not in set(surveillance[2].method):
        st.info("This saved run has no current surveillance results. Run `make surveillance` (or `make all`) with the same configuration, then reload.")
    else:
        monthly, forecasts, forecast_metrics, surveillance_meta = surveillance
        st.write(f"Each month, a fresh sample of **{surveillance_meta['monthly_sample']:,} synthetic adults** is screened under the simulated reporting and testing process, {surveillance_meta['first_month'][:7]} to {surveillance_meta['last_month'][:7]}.")
        areas = [PROVINCE] + sorted(set(monthly.municipality) - {PROVINCE})
        area = st.selectbox("Area", areas, key="surveillance_area")
        local = monthly.loc[monthly.municipality.eq(area)].sort_values("month")
        months = list(pd.to_datetime(local.month).drop_duplicates())
        if st.session_state.get("surveillance_month") not in months:
            st.session_state["surveillance_month"] = months[-1]
        month = st.select_slider("Visibility-gap month", months, format_func=lambda value: value.strftime("%b %Y"), key="surveillance_month")
        st.subheader("Simulation visibility gap: observed vs. undetected abnormal flags (simulator truth)")
        gap = visibility_gap_figure(monthly, area, month)
        if gap is None:
            st.info("No saved simulation sample is available for this area and month.")
        else:
            st.plotly_chart(gap, key="visibility_gap", width="stretch")
        st.caption("Synthetic outcomes: observed + undetected = all abnormal flags in this sampled group. "
                   "This is a reporting/testing visibility gap, not external validation, a diagnosis or a measured climate effect. "
                   "Saved monthly simulations use fresh samples; planner report/budget edits do not change these counts.")
        st.markdown("**Observed:** what a health office would see")
        positivity = px.line(local, x="month", y=TARGET, labels={"month": "Month", TARGET: "Abnormal flags per 100 tested"}, color_discrete_sequence=["#285a46"], hover_data={"observed_abnormal": True, "tested": True})
        positivity.update_layout(template="plotly_white", height=300, margin=dict(t=15, b=15))
        st.plotly_chart(positivity, width="stretch")
        coverage = local.melt(id_vars="month", value_vars=["reporting_coverage", "testing_coverage"], var_name="Measure", value_name="Share of sampled adults")
        coverage["Measure"] = coverage.Measure.map({"reporting_coverage": "Reported", "testing_coverage": "Tested"})
        coverage_figure = px.line(coverage, x="month", y="Share of sampled adults", color="Measure", labels={"month": "Month"}, color_discrete_map={"Reported": "#709986", "Tested": "#285a46"})
        coverage_figure.update_layout(template="plotly_white", height=260, margin=dict(t=15, b=15), yaxis_tickformat=".0%")
        st.plotly_chart(coverage_figure, width="stretch")
        st.caption(provenance_caption("saved monthly surveillance simulation", f"{surveillance_meta['monthly_sample']:,} fresh {geography_label(active)} per month",
                                      f"{surveillance_meta['first_month'][:7]} to {surveillance_meta['last_month'][:7]}",
                                      "abnormal flags per 100 tested; share of sampled adults", "synthetic simulation"))
        st.caption("Denominator for both coverage lines: synthetic adults sampled that month. Positivity denominator: adults tested that month. Tested people include nonreporters reached by outreach.")
        st.markdown("**Forecast check:** does recent climate improve the forecast of next months' positivity?")
        forecast_names = {"seasonal_naive": "Same month last year (seasonal naïve)", "candidate_no_climate": "Regression on last year, no climate", "candidate": "Regression on last year + origin-month hot–dry score"}
        table = forecast_metrics.assign(method=forecast_metrics.method.map(forecast_names))
        table = table.rename(columns={"method": "Forecast", "horizon_months": "Horizon (months)", "holdout_months": "Holdout months", "mae": "MAE", "rmse": "RMSE"})
        st.dataframe(table[["Forecast", "Horizon (months)", "Holdout months", "MAE", "RMSE"]], hide_index=True)
        gains = forecast_gains(forecast_metrics).rename(columns={"horizon_months": "Horizon (months)", "regression_gain": "Gain from regression alone", "climate_gain": "Gain from adding climate"})
        st.dataframe(gains, hide_index=True)
        st.caption("Gains are reductions in MAE (abnormal flags per 100 tested). 'Regression alone' beats seasonal naïve partly by pulling towards the average of a noisy monthly sample, with or without any climate effect. Only 'Gain from adding climate' measures what the hot–dry score adds; with no assumed heat effect it should be close to zero.")
        horizon = st.radio("Forecast horizon", sorted(forecasts.horizon_months.unique()), horizontal=True, format_func=lambda value: f"{value} month{'s' if value > 1 else ''} ahead", key="surveillance_horizon")
        chosen = forecasts.loc[forecasts.horizon_months.eq(horizon)].melt(id_vars="target_month", value_vars=["actual", "seasonal_naive", "candidate_no_climate", "candidate"], var_name="Series", value_name="Abnormal flags per 100 tested")
        chosen["Series"] = chosen.Series.map({"actual": "Observed", "seasonal_naive": "Seasonal naïve", "candidate_no_climate": "Regression, no climate", "candidate": "Regression + climate"})
        holdout = px.line(chosen, x="target_month", y="Abnormal flags per 100 tested", color="Series", markers=True, labels={"target_month": "Holdout month"}, color_discrete_map={"Observed": "#24372b", "Seasonal naïve": "#b36c30", "Regression, no climate": "#9aa79f", "Regression + climate": "#507c9a"})
        holdout.update_layout(template="plotly_white", height=300, margin=dict(t=15, b=15))
        st.plotly_chart(holdout, width="stretch")
        st.caption("MAE and RMSE are in abnormal flags per 100 tested, province level, over the same holdout months for every forecast. Every forecast uses only months up to its origin. One synthetic repetition; differences are not evidence of a real climate effect.")
        with st.expander("Hidden-population evaluation (simulator truth, not observable in practice)"):
            hidden = local[["month", "sampled_adults", "hidden_abnormal", "hidden_prevalence_per_100", "observed_abnormal", "hidden_undetected_abnormal"]].rename(columns={
                "month": "Month", "sampled_adults": "Sampled adults", "hidden_abnormal": "Hidden abnormal flags", "hidden_prevalence_per_100": "Hidden per 100 sampled",
                "observed_abnormal": "Observed abnormal flags", "hidden_undetected_abnormal": "Undetected abnormal flags"})
            st.dataframe(hidden, hide_index=True)
            st.caption("These counts use the simulator's hidden outcomes for every sampled adult. A real health office could not see them; they show how much the reporting and testing process misses.")
