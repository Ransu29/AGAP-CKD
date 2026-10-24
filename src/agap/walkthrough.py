"""LGU planning workspace over one immutable, synthetic demonstration cohort."""
from __future__ import annotations

import hashlib
import json
from html import escape
import sqlite3
from uuid import uuid4

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from agap.climate_demo import complete_exposure, preview_at_date, score_cohort
from agap.demo import (QUEUE_FILTER_DEFAULTS, SELECTION_REASONS, STRATEGIES, compare_plans, filter_queue, filters_for_resident, invitation_export,
                       outreach_share, parity_share, planner_queue, queue_status, selected_queue_resident, with_report, with_reports)
from agap.community_map import (COMMUNITY_METRICS, community_figure, community_hex_deck, community_street_deck,
                                selected_community, selected_hex_community)
from agap.community_overview import round_work
from agap.basemap import basemap_source
from agap.decision_support import (BUCKETS, bottleneck_counts, evaluation_mask,
                                    live_policies, marginal_swap, positives_by_questionnaire, reach_by_questionnaire, resident_chips, resident_timeline, weather_context_dates)
from agap.experiment import CoverageInfeasibleError
from agap.longitudinal import LABEL as LONGITUDINAL_LABEL, persistence_by_plan
from agap.provenance import deployment_period, geography_label, provenance_caption
from agap.mapping import municipal_features, municipal_map
from agap.citizen import known_ckd_residents, latest_profile
from agap.reports import append_report, normalize_report, parse_sms, resident_history
from agap.visuals import chips_html, contributions_figure, resident_model_shift_html, weather_timeline_figure
from agap.model_comparison import MODEL_LABELS, compare_models, comparison_export
from agap.workflow_store import active_round, get_events, record_event, worklist as round_worklist
from agap.workflow_ui import render_round_approval, render_worklist, workflow_path

QUEUE_FILTER_KEYS = dict(municipality="flow_municipality", questionnaire="queue_questionnaire",
                         access="queue_access", invitation="queue_invitation", search="queue_search")
WEATHER_CONTEXT_KEYS = ("flow_weather_date", "flow_explore_date", "flow_context_date", "flow_context_days",
                        "flow_context_user_chosen", "flow_context_window")
MAP_HEIGHT = 640
# Destinations follow the user's job: operational work (Worklist, Plan and the resident
# detail pages) never shows hidden simulator outcomes; those live only in Evaluate.
WORKLIST_TAB = "Worklist"
PLAN_TAB = "Plan"
REPORT_TAB = "Resident report"
WEATHER_TAB = "Resident weather"
EVALUATE_TAB = "Evaluate"
DATA_TAB = "Data"
WORKSPACE_PAGES = (WORKLIST_TAB, PLAN_TAB, REPORT_TAB, WEATHER_TAB, EVALUATE_TAB, DATA_TAB)


def _workflow_path(root):
    return workflow_path(root)


def _approved_round(root, run_id):
    try:
        result = active_round(_workflow_path(root), run_id)
        st.session_state.pop("workflow_load_error", None)
        return result
    except (ValueError, RuntimeError, sqlite3.Error) as exc:
        st.session_state["workflow_load_error"] = f"Unable to load the screening round: {exc}"
        st.error(st.session_state["workflow_load_error"])
        return None


@st.cache_data(show_spinner=False)
def _cached_municipal_features(root_path, province):
    return municipal_features(root_path, province)


@st.cache_data(show_spinner=False)
def plans_at(frame, facilities, scores, configuration, budget, strategy, outreach):
    return compare_plans(frame, facilities, scores, configuration, budget, strategy, outreach)


@st.cache_data(show_spinner=False)
def model_comparison_at(scored, facilities, configuration, budget, strategy, outreach):
    return compare_models(scored, facilities, configuration, budget, strategy, outreach)


def _clear_report():
    """Clear a resident's draft, preserving all applied session reports and plans."""
    for key in list(st.session_state):
        if key.startswith("report_form_") or key == "report_result":
            del st.session_state[key]
    st.session_state.pop("research_state", None)


def _score_cards(person, count, has_climate):
    variants = [("Questionnaire-only model", "clinical")]
    if has_climate:
        variants.append(("Questionnaire + public climate model", "climate"))
    for column, (label, variant) in zip(st.columns(len(variants)), variants):
        column.metric(label, f"{person[f'{variant}_score']:.1%}")
        column.write(f"Priority **#{int(person[f'{variant}_rank']):,}** of {count:,} synthetic adults")


def _apply_report_and_return(resident_id):
    saved = st.session_state.get("report_result")
    if saved is None or saved["payload"]["resident_id"] != resident_id:
        return
    if st.session_state.get("workflow_load_error"):
        st.session_state["workflow_report_error"] = "Report was not applied. Resolve the workflow storage error first."
        return
    if round_id := st.session_state.get("workflow_active_round"):
        try:
            record_event(st.session_state["workflow_database"], round_id, resident_id,
                         "report_applied", saved["payload"], actor="Demo staff",
                         request_id=saved.setdefault("apply_request_id", str(uuid4())),
                         expected_version=st.session_state.get("workflow_round_version"))
        except (ValueError, RuntimeError, sqlite3.Error) as exc:
            st.session_state["workflow_report_error"] = f"Report was not applied: {exc}"
            return
        st.session_state["workflow_notice"] = (
            "Questionnaire amendment saved. Draft scores use these answers; approved invitations stay fixed."
        )
    st.session_state["applied_reports"] = {**st.session_state["applied_reports"], resident_id: saved["payload"]}
    st.session_state.update(workspace_tab=_origin(), workspace_panel="Decision", flow_report_handoff=resident_id)


def _finish_report_handoff(queue):
    """Run after allocation, before constructing any queue/resident widgets."""
    resident_id = st.session_state.pop("flow_report_handoff", None)
    if resident_id is None:
        return
    filters = {name: st.session_state.get(key, QUEUE_FILTER_DEFAULTS[name]) for name, key in QUEUE_FILTER_KEYS.items()}
    try:
        updates = filters_for_resident(queue, resident_id, filters)
    except ValueError as exc:
        st.warning(str(exc))
        st.session_state["flow_resident"] = None
        return
    for name, value in updates.items():
        st.session_state[QUEUE_FILTER_KEYS[name]] = value
    st.session_state["flow_resident"] = resident_id
    message = f"Report applied for {resident_id}. Draft scores and any draft plan now use these answers."
    if st.session_state.get("workflow_active_round"):
        message += " The amendment is saved; approved round assignments are unchanged."
    if updates:
        labels = {"municipality": "Municipality", "questionnaire": "Questionnaire", "access": "Modeled access",
                  "invitation": "Invitation status", "search": "Resident search"}
        message += " Reset filters to keep this resident visible: " + ", ".join(labels[name] for name in updates) + "."
    st.success(message)


def _model_changed():
    if st.session_state.get("flow_resident"):
        st.session_state["flow_model_handoff"] = st.session_state["flow_resident"]
        st.session_state["workspace_panel"] = "Decision"


def _finish_model_handoff(queue):
    resident_id = st.session_state.pop("flow_model_handoff", None)
    if resident_id is None:
        return
    filters = {name: st.session_state.get(key, QUEUE_FILTER_DEFAULTS[name]) for name, key in QUEUE_FILTER_KEYS.items()}
    updates = filters_for_resident(queue, resident_id, filters)
    for name, value in updates.items():
        st.session_state[QUEUE_FILTER_KEYS[name]] = value
    st.session_state["flow_resident"] = resident_id
    st.info("Planning model changed. The same resident, applied answers and whole-cohort plan settings are retained."
            + (" Incompatible view filters were reset to keep this resident visible." if updates else ""))


def _resident_context(person, variant):
    model = MODEL_LABELS[variant]
    st.caption(f"Following {person.resident_id} · {person.municipality} · active model: {model}. "
               "Your selected resident and applied reports are shared with the screening planner.")


def _report_step(frame, person, clinical_model, climate_model, original, root, variant):
    resident_id = person.resident_id
    st.subheader("Review or correct questionnaire answers")
    if message := st.session_state.pop("workflow_report_error", None):
        st.error(message)
    if st.session_state.get("workflow_load_error"):
        st.error("Report changes are unavailable until the workflow database can be loaded.")
        return
    _resident_context(person, variant)
    st.write(f"**{resident_id}** · age {int(person.age)} · {person.municipality}. "
             + ("Their current questionnaire is available; you can try a correction." if person.reported else "Their questionnaire answers are missing."))
    st.caption("Submit fictional answers, preview their score, then apply the report to this session. "
               "This current report is a what-if change to the saved scenario; it is not backdated into training or saved experiments.")
    st.caption("Prior tests and outdoor hours are recorded for follow-up; they do not change this model's score.")
    round_id = st.session_state.get("workflow_active_round")
    if round_id:
        st.info("The approved round keeps its invitation assignments. Applied answers are saved as amendments and update the draft comparison only.")
    transport = st.radio("Enter the report using", ["Simple form", "SMS-style text"], horizontal=True, key="report_form_transport")
    if transport == "Simple form":
        with st.form("resident_report"):
            questions = {"DM": "Previously told they have diabetes?", "HTN": "Previously told they have hypertension?",
                         "FAM": "Family history of kidney disease?", "OUT": "Regular outdoor work?",
                         "PRIOR": "Kidney test (creatinine or urine) in the past 12 months?"}
            fields = {"DM": "dm_report", "HTN": "htn_report", "FAM": "family_report", "OUT": "outdoor_report", "PRIOR": "prior_screen_report"}
            columns = st.columns(2)
            answers = {key: columns[index % 2].selectbox(label, ["Y", "N", "U", ""],
                       index=2 if pd.isna(person.get(fields[key])) else 0 if person[fields[key]] == 1 else 1,
                       format_func=lambda value: {"Y": "Yes", "N": "No", "U": "Unknown", "": "Not answered"}[value],
                       key=f"report_form_{key}") for index, (key, label) in enumerate(questions.items())}
            hours = person.get("outdoor_hours_7d_report")
            if answers["OUT"] == "N" and pd.notna(hours) and hours > 0:
                hours = 0
            answers["HRS"] = st.text_input("Outdoor hours in the last 7 days (0–168; U = unknown; blank = not answered)",
                                           value="" if pd.isna(hours) else str(int(hours)), key="report_form_hours")
            answers["DATE"] = st.date_input("Date these answers describe (within the past 30 days)", value=pd.Timestamp.today().date(), key="report_form_date").isoformat()
            submitted = st.form_submit_button("Preview this report's effect", type="primary")
        payload, errors = normalize_report(resident_id, int(person.age), answers)
    else:
        with st.form("resident_sms"):
            text = st.text_area("Example message", f"AGAP {resident_id} {int(person.age)} DM:Y HTN:U FAM:U OUT:U PRIOR:N HRS:U DATE:{pd.Timestamp.today().date().isoformat()}", key="report_form_sms")
            submitted = st.form_submit_button("Validate & preview report", type="primary")
        payload, errors = parse_sms(text)
        if payload and payload["resident_id"] != resident_id:
            errors.append("Use the selected demonstration resident's ID in the message.")
    if submitted:
        if not errors:
            try:
                with_report(frame, payload)
            except ValueError as exc:
                errors = [str(exc)]
        if round_id:
            attempt = dict(payload=payload, errors=errors, channel=transport,
                           raw_text=text if transport == "SMS-style text" else None)
            try:
                attempts = [event for event in get_events(_workflow_path(root), round_id)
                            if event["resident_id"] == resident_id and event["event_type"] == "report_attempt"]
                previous = attempts[-1].get("payload", {}) if attempts else {}
                created = not (attempts and previous.get("payload") == payload and previous.get("errors") == errors)
                if created:
                    record_event(_workflow_path(root), round_id, resident_id, "report_attempt", attempt,
                                 actor="Demo staff", request_id=str(uuid4()))
                    refreshed = active_round(_workflow_path(root), st.session_state["demo_run"])
                    st.session_state["workflow_round_version"] = refreshed["version"] if refreshed else None
            except (ValueError, RuntimeError, sqlite3.Error) as exc:
                created = False
                errors = [*errors, f"Report preview was not saved: {exc}"]
        else:
            _, created = append_report(root / "data/reports/citizen_reports.jsonl", payload, errors, transport,
                                       resident_id=resident_id, raw_text=text if transport == "SMS-style text" else None)
        if not created and not errors:
            st.info("Already recorded (duplicate submission ignored — E1-07). No new revision was created.")
        if errors:
            st.session_state.pop("report_result", None)
            for error in errors:
                st.error(error)
        else:
            # Store the submission, never a plan computed with an earlier budget.
            before = original.loc[original.resident_id.eq(resident_id)].iloc[0]
            before_by_model = {name: dict(score=float(before[f"{name}_score"]), rank=int(before[f"{name}_rank"]))
                               for name in MODEL_LABELS if f"{name}_score" in original}
            st.session_state["report_result"] = dict(payload=payload, before_by_model=before_by_model,
                                                    apply_request_id=str(uuid4()))
    saved = st.session_state.get("report_result")
    if saved and saved["payload"]["resident_id"] == resident_id:
        proposed = score_cohort(with_report(frame, saved["payload"]), clinical_model, climate_model)
        after = proposed.loc[proposed.resident_id.eq(resident_id)].iloc[0]
        before = saved.get("before_by_model", {}).get(variant)
        if before is None:  # migrate a draft from an already-open, older app
            current_before = original.loc[original.resident_id.eq(resident_id)].iloc[0]
            before = dict(score=float(current_before[f"{variant}_score"]), rank=int(current_before[f"{variant}_rank"]))
        left, right = st.columns(2)
        left.metric("Score before report", f"{before['score']:.1%}")
        right.metric("Score after report", f"{after[f'{variant}_score']:.1%}")
        left.metric("Priority position before report", f"#{before['rank']:,}")
        right.metric("Priority position after report", f"#{int(after[f'{variant}_rank']):,}")
        st.caption("Both scores use this resident's saved screening date and the same cohort. Position 1 is highest priority. "
                   "Applying the report updates the planner using the current budget and strategy, if a plan exists.")
        applied = st.session_state["applied_reports"].get(resident_id) == saved["payload"]
        st.button("Apply report & return to workspace", type="primary", disabled=applied, key="apply_report",
                  on_click=_apply_report_and_return, args=(resident_id,))
        if applied:
            st.success("Report applied. Draft scores and invitations use these answers; other residents' edits are retained."
                       + (" The approved round keeps its saved assignments." if round_id else ""))
        else:
            st.info("Preview only: apply this report to update the planner. Until then, it retains the current session's answers.")
    st.button(f"Back to {_origin()}", on_click=_open_tab, args=(_origin(),), key="report_back")
    history = resident_history(root / "data/reports/citizen_reports.jsonl", resident_id)
    if round_id:
        try:
            for event in get_events(_workflow_path(root), round_id):
                if event["resident_id"] != resident_id or event["event_type"] not in ("report_attempt", "report_applied"):
                    continue
                details = event["payload"]
                history.append(dict(report_id=event["event_id"], available_at=event.get("recorded_at"),
                    event_at=event.get("occurred_at"), valid=not details.get("errors"),
                    channel=details.get("channel", "Explicit apply"), errors=details.get("errors", []),
                    event_type=event["event_type"], source="Approved-round audit"))
        except (ValueError, RuntimeError, sqlite3.Error) as exc:
            st.error(f"Unable to load round report history: {exc}")
    with st.expander("Report revision & validation history"):
        st.caption("Validation checks format and ranges, not clinical review. This local history includes what-if previews; only explicitly applied answers enter this session. Past cutoffs are unchanged.")
        if not history:
            st.info("No local report attempts have been recorded for this resident.")
        else:
            st.dataframe(pd.DataFrame([dict(Report=r["report_id"], Event=r.get("event_type", "Legacy preview"), Available=r.get("available_at"),
                Event_date=r.get("event_at"), Valid=bool(r.get("valid")), Channel=r.get("channel"),
                Supersedes_valid=r.get("supersedes"), Previous_attempt=r.get("previous_attempt_id"),
                Errors="; ".join(r.get("errors", []))) for r in history]), hide_index=True)
            st.download_button("Download this resident's report history", json.dumps(history, indent=2),
                               f"{resident_id}_report_history.json", "application/json")


def _choose_weather_context():
    st.session_state["flow_context_user_chosen"] = True


def _available_weather(person, weather):
    metadata = weather["metadata"]
    st.markdown("**Real historical weather · preview**")
    st.caption(f"Source: ERA5-Land · Asia/Manila · available observations {metadata['requested_start']} to {metadata['requested_end']}. "
               "These summaries do not enter the screening model; seasonal anomalies require the full reference period.")
    local = weather["windows"].loc[weather["windows"].era5_cell.eq(person.era5_cell)]
    days = st.radio("Weather summary window", [7, 30], index=1, format_func=lambda value: f"{value} days", horizontal=True, key="flow_context_days")
    st.caption(f"Available 30-day windows at {metadata['supported_cell_count']} of {metadata['source_cell_count']} downloaded source cells. "
               f"This resident's source cell: {person.era5_cell}. Masked cells are not filled from another location.")
    st.caption("Context only · active model: questionnaire-only. Changing the weather view does not change scores or invitations.")
    coverage = weather_context_dates(local, person.cutoff, days)
    if coverage["default"] is None:
        st.warning(f"No complete {days}-day historical weather window is available at this resident's source cell. Try the other window length.")
        return
    saved = pd.Timestamp(person.cutoff).normalize()
    dates = pd.to_datetime(local.cutoff)
    earliest, latest = dates.min().date(), dates.max().date()
    if st.session_state.get("flow_context_window") != days and not st.session_state.get("flow_context_user_chosen"):
        st.session_state.pop("flow_context_date", None)
    st.session_state["flow_context_window"] = days
    context = st.date_input("Historical weather context date", value=coverage["default"].date(),
                            min_value=earliest, max_value=latest, key="flow_context_date", on_change=_choose_weather_context)
    context = pd.Timestamp(context)
    message = f"Saved screening date: {saved:%d %b %Y}. "
    if context == saved and coverage["saved_available"]:
        message += "This weather window matches the saved screening date. "
    elif coverage["saved_available"]:
        message += f"Showing another historical date, {context:%d %b %Y}; complete {days}-day weather is also available at the saved screening date. "
    else:
        origin = "Selected historical context" if st.session_state.get("flow_context_user_chosen") else "Automatic historical fallback"
        message += f"No complete {days}-day weather is available at that saved date. {origin}: {context:%d %b %Y}. "
        if context > saved:
            message += "This context is after screening. "
    st.info(message + "The score and invitation continue to use the questionnaire-only model.")
    selected = local.loc[local.cutoff.eq(context)]
    if selected.empty:
        st.warning("This context date has no weather record. Choose another date.")
        return
    row = selected.iloc[0]
    start, end = context - pd.Timedelta(days=days), context - pd.Timedelta(days=1)
    st.caption(f"{start:%d %b %Y}–{end:%d %b %Y} · context day excluded · temperature {int(row[f'temperature_days_{days}d'])}/{days} complete days, "
               f"rainfall {int(row[f'rainfall_days_{days}d'])}/{days} complete days.")
    if not row[f"complete_{days}d"]:
        st.warning("This weather window is incomplete. No partial mean or rainfall total is presented as a complete window.")
        return
    left, middle, right = st.columns(3)
    left.metric(f"Mean temperature · {days} days", f"{row[f'tmean_{days}d_c']:.1f} °C")
    middle.metric(f"Maximum temperature · {days} days", f"{row[f'tmax_{days}d_c']:.1f} °C")
    right.metric(f"Rainfall · {days} days", f"{row[f'rainfall_{days}d_mm']:.0f} mm")
    daily = weather["daily"]
    window = daily.loc[daily.era5_cell.eq(person.era5_cell) & daily.local_date.between(start, end)].sort_values("local_date")
    left, right = st.columns(2)
    left.plotly_chart(px.line(window, x="local_date", y=["tmean_c", "tmax_c"], labels={"local_date": "Local date", "value": "Temperature (°C)", "variable": "Daily measure"}), width="stretch")
    right.plotly_chart(px.bar(window, x="local_date", y="precip_mm", labels={"local_date": "Local date", "precip_mm": "Rainfall (mm)"}), width="stretch")
    st.download_button("Download this real weather window", window.to_csv(index=False), f"era5_land_{person.era5_cell}_{context.date()}_{days}d.csv", "text/csv")
    st.caption("[Copernicus ERA5-Land hourly reanalysis](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land) · community weather, not personal exposure.")


def _weather_model_changed():
    st.session_state["flow_model"] = st.session_state["flow_weather_model"]
    _model_changed()


def _open_resident_planner():
    _open_tab(PLAN_TAB)
    _open_resident_decision()


def _weather_summary(condition):
    maximum = condition.get("preceding_mean_tmax_c")
    has_maximum = maximum is not None and pd.notna(maximum)
    value = maximum if has_maximum else condition.preceding_tmean_c
    label = "Mean daily maximum" if has_maximum else "Mean temperature"
    reference = condition.get("temperature_mean_c")
    temperature_note = "30-day temperature summary"
    if has_maximum and reference is not None and pd.notna(reference):
        temperature_note = f"{maximum-reference:+.1f} °C vs. seasonal reference"
    rain_reference = condition.get("rainfall_mean_mm")
    rain_note = "Total across the same 30 days"
    if rain_reference is not None and pd.notna(rain_reference):
        rain_note = f"{condition.preceding_precip_mm-rain_reference:+.0f} mm vs. seasonal reference"
    return (f'<div class="agap-weather-summary"><div><span>{label} · 30 days</span>'
        f'<strong>{value:.1f}<small> °C</small></strong><p>{temperature_note}</p></div>'
        f'<div><span>Rainfall · 30 days</span><strong>{condition.preceding_precip_mm:.0f}<small> mm</small></strong>'
        f'<p>{rain_note}</p></div></div>')


def _weather_resident_card(person, decision, variant, plan_state):
    with st.container(border=True, key="weather_resident"):
        st.markdown('<span class="agap-eyebrow">FOLLOWED RESIDENT</span>', unsafe_allow_html=True)
        st.subheader(person.municipality)
        st.markdown(f'<div class="agap-resident-identity">{escape(person.resident_id)}<span>Age {int(person.age)} · synthetic resident</span></div>', unsafe_allow_html=True)
        status = "Unavailable" if plan_state == "unavailable" else decision.invitation_status
        st.markdown(f'<div class="agap-current-decision"><span>CURRENT INVITATION</span><strong>{escape(status)}</strong>'
                    f'<small>{escape(MODEL_LABELS[variant])}</small></div>', unsafe_allow_html=True)
        st.button("Show in Plan", key="weather_show_planner", type="primary", width="stretch", on_click=_open_resident_planner)
        report = "No questionnaire received" if not person.reported else f"{int(decision.missing_answers)} model answers missing" if decision.missing_answers else "All model answers available"
        access = f"{decision.nearest_distance_km:.1f} km to nearest hypothetical service point"
        st.markdown(f'<dl class="agap-resident-facts"><div><dt>Reporting</dt><dd>{escape(report)}</dd></div>'
            f'<div><dt>Modeled access</dt><dd>{escape(access)}</dd></div></dl>', unsafe_allow_html=True)
        if plan_state == "ready":
            st.markdown(f"**Invitation reason:** {decision.selection_reason}")
            if decision.invitation_status == "Invited":
                st.caption(f"Assigned {decision.facility_id} · {decision.assigned_distance_km:.1f} km straight-line. Hypothetical capacity; no appointment booked.")
        elif plan_state == "unplanned":
            st.caption("Choose a screening budget and compare plans in the planner to assign invitations.")
        else:
            st.caption("Correct the plan settings in the planner to restore invitation decisions.")
        st.button("Review questionnaire", key="weather_review_report", width="stretch", on_click=_open_tab, args=(REPORT_TAB,))


def _weather_step(frame, scored, person, clinical_model, climate, weather=None, variant="clinical",
                  decision=None, comparison=None, settings=None, plan_state="unplanned"):
    cutoff = pd.Timestamp(person.cutoff).normalize()
    if climate is None:
        st.subheader("Weather context and screening score")
        _resident_context(person, variant)
        st.write(f"**{person.resident_id}** · {person.municipality} · saved screening date **{cutoff:%d %b %Y}**")
        if weather is not None:
            _available_weather(person, weather)
        else:
            st.info("This saved run uses the questionnaire-only model in the walkthrough. Public weather is not connected yet.")
        _score_cards(person, len(scored), False)
    else:
        title, control = st.columns([2.35, 1], vertical_alignment="bottom")
        with title:
            st.markdown('<span class="agap-eyebrow">PUBLIC WEATHER → MODEL PRIORITY → INVITATION</span>', unsafe_allow_html=True)
            st.subheader("Does climate change this resident’s invitation?")
            st.caption(f"{person.municipality} · resident {person.resident_id} · saved screening date {cutoff:%d %b %Y}")
        with control:
            st.session_state["flow_weather_model"] = variant
            st.radio("Active planning model", list(MODEL_LABELS), format_func=MODEL_LABELS.get,
                     horizontal=True, key="flow_weather_model", on_change=_weather_model_changed)
        decisions = comparison["decisions"] if comparison is not None else None
        st.markdown(resident_model_shift_html(person, len(scored), decisions, plan_state, variant), unsafe_allow_html=True)
        st.caption("Model scores describe simulated abnormal initial results. Differences between fitted models do not establish a climate effect or validated clinical risk.")
        exposure = climate["exposure"]
        selected = exposure.loc[exposure.era5_cell.eq(person.era5_cell) & exposure.cutoff.eq(cutoff) & complete_exposure(exposure)]
        timeline, resident = st.columns([2.35, 1], gap="medium")
        with timeline, st.container(border=True, key="weather_timeline_panel"):
            start, end = cutoff-pd.Timedelta(days=30), cutoff-pd.Timedelta(days=1)
            st.markdown(f'<div class="agap-weather-period"><h3>30 days before screening</h3>'
                        f'<small>{start:%d %b %Y}–{end:%d %b %Y} · screening day excluded</small></div>', unsafe_allow_html=True)
            if selected.empty:
                st.warning("The saved weather window is unavailable for this resident. No replacement weather is used.")
            else:
                st.markdown(_weather_summary(selected.iloc[0]), unsafe_allow_html=True)
                daily = climate["daily"]
                dates = pd.to_datetime(daily.local_date)
                window = daily.loc[daily.era5_cell.eq(person.era5_cell) & dates.between(start, end)].sort_values("local_date")
                try:
                    figure = weather_timeline_figure(window, cutoff)
                except ValueError as exc:
                    st.info(f"Daily timeline unavailable: {exc} The saved model comparison is shown above.")
                else:
                    st.plotly_chart(figure, width="stretch", key="screening_weather_timeline", theme=None,
                                    config={"displayModeBar": False, "scrollZoom": False})
                    st.caption("ERA5-Land · hover to inspect both measures on the same local day. Community weather is not a personal exposure measurement.")
                    st.download_button("Download this public climate window", window.to_csv(index=False), f"climate_{cutoff.date()}.csv", "text/csv")
        with resident:
            if decision is not None:
                _weather_resident_card(person, decision, variant, plan_state)
        with st.expander("Weather source & model inputs"):
            metadata = climate["metadata"]
            st.caption(f"Source: Copernicus ERA5-Land · source cell {person.era5_cell} · 0.1° (~9–11 km) source resolution. "
                       f"Seasonal reference: {metadata.get('baseline_start', 'declared start')}–{metadata.get('baseline_end', 'declared end')}.")
            st.write("The seasonal reference compares 30-day mean daily maximum temperature and 30-day rainfall totals at this source cell, grouped by screening calendar month. It is not a daily temperature normal or a heat-index alert.")
            st.write("The climate model uses the average of the standardized temperature anomaly and rainfall deficit. Both fitted models retain missing-answer indicators. Changing the active model preserves the cohort, reports and screening budget.")
            if settings is not None:
                st.caption(f"Paired plan: {settings['budget']:,} panels · {settings['strategy']} · same capacities, tie-breaks and random draws.")
            st.markdown("[Copernicus ERA5-Land data source](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land)")
    if climate is not None:
        with st.expander("Why does the model give this score?"):
            st.plotly_chart(contributions_figure(climate["model"] if variant == "climate" else clinical_model, person), width="stretch", key="weather_model_terms")
            st.caption("Exact additive model terms relative to its standardized reference, with the intercept as the starting value. These are not medical causes.")
        with st.expander("Optional: explore another weather date"):
            st.caption("This exploration changes scores only. It does not change the main scenario, invitations, or medical outcomes.")
            usable = climate["exposure"]
            usable = usable.loc[complete_exposure(usable) & usable.era5_cell.eq(person.era5_cell)]
            usable = usable.loc[usable.cutoff.between(pd.to_datetime(frame.cutoff).min(), pd.to_datetime(frame.cutoff).max())]
            if usable.empty:
                st.info("There are no alternative complete weather dates for this resident.")
            elif st.checkbox("Explore another date", key="flow_explore_date"):
                dates = usable.cutoff
                default = min(max(cutoff.date(), dates.min().date()), dates.max().date())
                chosen = st.date_input("Weather exploration date", value=default, min_value=dates.min().date(), max_value=dates.max().date(), key="flow_weather_date")
                preview = preview_at_date(frame, climate["exposure"], chosen, clinical_model, climate["model"])
                match = preview.loc[preview.resident_id.eq(person.resident_id)]
                if match.empty:
                    st.warning("No complete weather window for this resident on that date. The main scenario is unchanged.")
                else:
                    _score_cards(match.iloc[0], len(preview), True)
                    st.caption(f"Matched population: {len(preview):,} of {len(frame):,} residents with complete weather on this date. Main scenario remains {cutoff:%d %b %Y} for this resident.")
    st.button(f"Back to {_origin()}", on_click=_open_tab, args=(_origin(),), key="weather_back")


def _open_tab(label):
    if label in (REPORT_TAB, WEATHER_TAB) and st.session_state.get("workspace_tab") in (WORKLIST_TAB, PLAN_TAB):
        st.session_state["resident_origin"] = st.session_state["workspace_tab"]
    st.session_state["workspace_tab"] = label


def _origin():
    """The operational page a resident detail page returns to."""
    return st.session_state.get("resident_origin", PLAN_TAB)


def _page_changed():
    _open_tab(st.session_state["workspace_page"])


def _page_navigation():
    """Share one destination state between desktop tabs and the compact selector.

    CSS shows the Page selector on narrow screens and the tab header on desktop.
    The destination contents and their forms remain mounted exactly once.
    """
    current = st.session_state.get("workspace_tab", PLAN_TAB)
    if current not in WORKSPACE_PAGES:
        current = PLAN_TAB
        st.session_state["workspace_tab"] = current
    st.session_state["workspace_page"] = current
    with st.container(key="workspace_page_selector"):
        st.selectbox("Page", WORKSPACE_PAGES, key="workspace_page", on_change=_page_changed)
    with st.container(key="workspace_destinations"):
        return st.tabs(WORKSPACE_PAGES, key="workspace_tab", on_change="rerun")


def _select_queue_row(key, resident_ids):
    event = st.session_state[key]
    st.session_state["flow_resident"] = selected_queue_resident(resident_ids, event["selection"]["rows"])
    _open_resident_decision()


def _open_resident_decision():
    if st.session_state.get("flow_resident"):
        st.session_state["workspace_panel"] = "Decision"


def _select_map_community(allowed):
    name = selected_community(st.session_state["community_map"]["selection"]["points"], allowed)
    if name is not None:
        st.session_state["flow_municipality"] = name
        st.session_state["workspace_panel"] = "Residents"


def _select_hex_community(allowed):
    name = selected_hex_community(st.session_state["community_hex_map"], allowed)
    if name is not None and name != st.session_state.get("flow_municipality"):
        st.session_state["flow_municipality"] = name
        st.session_state["workspace_panel"] = "Residents"


def _select_street_community(allowed):
    name = selected_hex_community(st.session_state["community_street_map"], allowed, "communities")
    # Streamlit also refreshes selected objects when live plan metrics change.
    # That refresh must not pull the user away from Decision or Plan.
    if name is not None and name != st.session_state.get("flow_municipality"):
        st.session_state.update(flow_municipality=name, workspace_panel="Residents")


def _queue_filters(queue, planned):
    area = st.selectbox("Municipality", ["All municipalities"] + sorted(queue.municipality.unique()), key="flow_municipality")
    questionnaire = st.selectbox("Questionnaire", ["All questionnaires", "No questionnaire", "Questionnaire available", "Missing model answers"], key="queue_questionnaire")
    with st.popover("More filters", width="stretch"):
        access = st.selectbox("Modeled access", ["All access", "Within assumed access limit", "Outside assumed access limit"], key="queue_access")
        if not planned:
            st.session_state["queue_invitation"] = "All invitation statuses"
        invitation = st.selectbox("Invitation status", ["All invitation statuses", "Invited", "Not invited"], disabled=not planned, key="queue_invitation")
        search = st.text_input("Search resident ID", placeholder="SYN-…", key="queue_search")
    local = filter_queue(queue, municipality=area)
    invited = f"{int(local.invitation_status.eq('Invited').sum()):,}" if planned else "not planned"
    st.markdown(f'<div class="agap-community-summary"><span><b>{len(local):,}</b> cohort adults</span>'
                f'<span><b>{int(local.reported.sum()):,}</b> reported</span>'
                f'<span><b>{int(local.access_eligible.sum()):,}</b> within access limit</span>'
                f'<span><b>{invited}</b> invited</span></div>', unsafe_allow_html=True)
    return area, filter_queue(queue, area, questionnaire, access, invitation, search)


def _queue_table(visible, count):
    ids = tuple(visible.resident_id)
    if st.session_state.get("flow_resident") and st.session_state["flow_resident"] not in ids:
        st.info("The selected resident no longer matches the queue filters. Their applied report and the whole plan are retained; broaden the filters to find them again.")
    if st.session_state.get("flow_resident") not in ids:
        st.session_state["flow_resident"] = None
    st.caption(f"Showing {len(visible):,} of {count:,} · highest priority first")
    if visible.empty:
        st.info("No residents match these filters. Clear the search or broaden the filters.")
    else:
        selected = st.session_state.get("flow_resident")
        key = "residents_" + hashlib.sha256(repr((ids, selected)).encode()).hexdigest()[:16]
        columns = ["resident_id", "display_status"]
        displayed = visible[columns].copy()
        reports = pd.Series("Complete", index=visible.index)
        reports.loc[visible.missing_answers.gt(0)] = "Partial"
        reports.loc[~visible.reported] = "No report"
        invitations = visible.invitation_status.map({"Invited": "Invited", "Not invited": "Not selected", "Not planned": "Unplanned"})
        invitations.loc[visible.display_status.eq("Plan unavailable")] = "Unavailable"
        displayed["display_status"] = reports + " · " + invitations
        suffix = displayed.resident_id.str.replace("SYN-DEPLOYMENT-", "", regex=False)
        displayed["resident_id"] = "#" + visible["rank"].astype(str) + " · " + suffix
        st.dataframe(displayed, hide_index=True, height=250, width="stretch", key=key,
                     selection_mode="single-row", on_select=lambda table_key=key, row_ids=ids: _select_queue_row(table_key, row_ids),
                     selection_default={"selection": {"rows": [ids.index(selected)] if selected in ids else []}},
                     column_config={"resident_id": st.column_config.TextColumn("Rank · resident", width=105,
                                        help="Current priority rank and synthetic ID suffix; Decision shows the full ID."),
                                    "display_status": st.column_config.TextColumn("Report / draft", width=165,
                                        help="Questionnaire completeness and draft invitation are separate states. Open Decision for the selection reason.")})
        with st.expander("Select a resident by ID"):
            labels = {p.resident_id: f"{p.resident_id} · {p.municipality}" for p in visible.itertuples()}
            st.selectbox("Inspect resident", list(ids), index=None, placeholder="Choose a resident or select a row above", format_func=labels.get,
                         key="flow_resident", on_change=_open_resident_decision)
    selected = st.session_state.get("flow_resident")
    if st.session_state.get("flow_previous_resident") != selected:
        _clear_report()
        for context_key in WEATHER_CONTEXT_KEYS:
            st.session_state.pop(context_key, None)
        st.session_state["flow_previous_resident"] = selected
    return selected


def _inspect_evaluation_resident(resident_id, municipality):
    st.session_state.update(flow_resident=resident_id, flow_municipality=municipality,
                           queue_questionnaire="All questionnaires", queue_access="All access",
                           queue_invitation="All invitation statuses", queue_search="", workspace_tab=PLAN_TAB, workspace_panel="Decision")


def _select_evaluation_row(key, ids, areas):
    resident_id = selected_queue_resident(ids, st.session_state[key]["selection"]["rows"])
    if resident_id:
        _inspect_evaluation_resident(resident_id, areas[resident_id])


@st.cache_data(show_spinner=False)
def _map_artifacts(directory):
    boundary = json.loads((directory / "boundary.geojson").read_text()) if (directory / "boundary.geojson").exists() else None
    cells = pd.read_parquet(directory / "cells.parquet") if (directory / "cells.parquet").exists() else None
    return boundary, cells


def _plan_controls(working, scored, facilities, cfg, variant):
    maximum = len(working)
    with st.form("plan_setup"):
        if maximum > 1:
            budget = st.slider("Screening panels · whole cohort", 1, maximum, min(500, maximum), key="panel_budget")
        else:
            budget = st.number_input("Screening panels · whole cohort", min_value=1, max_value=1, value=1, key="panel_budget")
        strategy = st.selectbox("Invitation strategy", list(STRATEGIES), index=1, key="plan_choice")
        outreach = st.select_slider("Outreach share · mixed plans", [.1, .2, .3, .4, .5, .6, .7], value=.2,
                                   format_func=lambda value: f"{value:.0%}", key="outreach_choice")
        st.caption(f"Unreported outreach only changes a plan above the share pure score ranking already gives "
                   f"residents without a questionnaire. Equal invitation coverage needs about {parity_share(working):.0%} "
                   "in this cohort.")
        submitted = st.form_submit_button("Compare screening plans", type="primary", width="stretch")
    if submitted:
        st.session_state["comparison_settings"] = dict(budget=int(budget), strategy=strategy, outreach=outreach)
        st.session_state["comparison_started"] = True
    if not st.session_state["comparison_started"]:
        st.info("Invitations are not assigned yet. Choose a budget and click Compare screening plans when ready.")
        return None
    settings = st.session_state["comparison_settings"]
    share = outreach_share(settings)
    st.caption(f"Current plan: {settings['budget']:,} panels · {settings['strategy']} · outreach {share:.0%} · whole cohort. Changes apply on Compare.")
    try:
        return plans_at(working, facilities, scored[f"{variant}_score"].to_numpy(), cfg, **settings)
    except CoverageInfeasibleError as exc:
        st.error(f"This plan cannot meet the configured geographic coverage requirements. {exc}")
    except ValueError as exc:
        st.error(f"Unable to prepare this plan: {exc}")
    st.warning("No current invitation decisions or export are available for these settings. Adjust the plan and compare again.")
    return None


def _plan_formation_lines(working, facilities, cfg, variant, settings):
    """Explain allocation using model-visible inputs and configured constraints."""
    budget = int(settings["budget"])
    strategy = settings["strategy"]
    share = outreach_share(settings)
    lines = [f"**Draft model:** {MODEL_LABELS[variant]}. **Budget:** up to {budget:,} invitations "
             f"from {len(working):,} cohort adults; one panel per invited resident."]
    if strategy == "Priority + random outreach":
        lines.append(f"**Selection:** target {share:.0%} random outreach among reachable residents, then fill remaining "
                     "slots by score using fixed tie-breaks. Capacity, access and municipal minimums can change the final split.")
    elif strategy == "Priority + outreach to unreported residents":
        lines.append(f"**Selection:** target {share:.0%} of slots for reachable residents without a questionnaire, highest "
                     "score first, then fill remaining slots by score. Missing answers lower scores, so without this share "
                     "residents who never reported are rarely invited. Capacity, access and municipal minimums can change the split.")
    elif strategy == "Prioritize higher scores":
        lines.append("**Selection:** higher scores first, using fixed tie-breaks. Any municipal coverage minimums are placed first.")
    else:
        lines.append("**Selection:** municipal shares follow represented adult population, with a fixed random order within each "
                     "municipality. Unfilled municipal quotas may be reassigned.")
    lines.append(f"**Access and capacity:** assign the nearest available hypothetical service point within "
                 f"{float(cfg['allocation']['max_distance_km']):g} km straight-line; never exceed its capacity. "
                 f"{len(facilities):,} service points provide {int(facilities.capacity.sum()):,} total slots.")
    coverage = cfg["allocation"].get("coverage") or {}
    overrides = coverage.get("minimum_invitations") or {}
    minimum = int(coverage.get("minimum_invitations_per_municipality", 0))
    requirements = {name: int(overrides.get(name, minimum)) for name in working.municipality.unique()}
    nonzero = [value for value in requirements.values() if value > 0]
    lines.append(f"**Municipal coverage:** at least {sum(nonzero):,} invitations across {len(nonzero):,} municipalities "
                 "with configured minimums; infeasible requirements stop allocation." if nonzero else
                 "**Municipal coverage:** no invitation minimums are configured.")
    return lines


def _plan_formation(working, facilities, cfg, variant, settings, approved):
    with st.expander("How this plan was formed"):
        for line in _plan_formation_lines(working, facilities, cfg, variant, settings):
            st.markdown(line)
        st.caption("Applied questionnaire answers affect draft scores. View filters do not change allocation. "
                   "Unused budget can remain when access or service capacity prevents assignment.")
        if approved:
            frozen = approved["snapshot"]
            frozen_settings = frozen["settings"]
            frozen_share = outreach_share(frozen_settings)
            frozen_capacity = sum(int(site["capacity"]) for site in frozen["facilities"])
            st.caption(f"Approved round stays fixed: {MODEL_LABELS[frozen['model']]} · {int(frozen_settings['budget']):,}-panel budget · "
                       f"{frozen_settings['strategy']} · outreach {frozen_share:.0%} · "
                       f"{float(frozen_settings['max_distance_km']):g} km access limit · "
                       f"{frozen_capacity:,} total service-point slots. "
                       "Changes here prepare a separate draft; they do not reassign approved invitations.")


def _citizen_profile(profile):
    with st.expander("Citizen-submitted profile (self-reported, not verified)", expanded=bool(profile)):
        if not profile:
            st.caption("This resident has not submitted a profile in the citizen view.")
            return
        st.write(f"Known kidney status: **{profile['reported_kidney_state']}** · told they have hypertension: "
                 f"**{profile['reported_diagnosed_htn']}** · told they have diabetes: **{profile['reported_diagnosed_dm']}** · "
                 f"age group {profile['age_band']}")
        st.caption(f"Entered {profile['entered_at'][:10]} through the citizen demo view. Self-reported answers are not "
                   "verified diagnoses and do not change model inputs. A reported known CKD diagnosis removes the resident "
                   "from first-screening invitations; confirm it and follow their care plan.")


def _resident_detail(person, decision, model, count, variant, current=None, max_distance_km=20, profile=None):
    st.subheader("Resident decision")
    if person is None:
        st.info("Select a resident row or use the resident selector to inspect their answers and invitation decision.")
        return
    st.markdown(f"**{person.resident_id}**")
    st.caption(f"{person.municipality} · priority #{int(decision['rank']):,} of {count:,} · synthetic resident")
    unavailable = current is None and st.session_state.get("comparison_started", False)
    status = "Unavailable" if unavailable else {"Invited": "Yes", "Not invited": "No"}.get(decision.invitation_status, "Not planned")
    invitation, score = st.columns(2)
    invitation.metric("Invitation in the current plan", status)
    score.metric("This resident's score", f"{decision.score:.1%}")
    if unavailable:
        st.warning("Plan unavailable. Correct the budget or strategy above, then compare again.")
    elif decision.invitation_status == "Not planned":
        st.info("No plan prepared. Open Plan settings, choose a budget, then compare screening plans.")
        st.button("Open plan controls", key="open_plan_controls", on_click=lambda: st.session_state.update(workspace_panel="Plan settings"), width="stretch")
    elif decision.invitation_status == "Invited":
        st.write(f"**Reason:** {decision.selection_reason} · assigned {decision.facility_id} ({decision.assigned_distance_km:.1f} km).")
        st.caption("Hypothetical capacity reserved; no appointment booked.")
    else:
        st.write(f"**Not invited:** {decision.selection_reason}.")
    facts = resident_chips(person, decision, max_distance_km)
    facts = [(category, text) for category, text in facts if category not in ("invited", "uninvited")
             and (category != "answer" or text.endswith(": Yes"))]
    st.markdown(chips_html(facts), unsafe_allow_html=True)
    _citizen_profile(profile)
    st.button("Review / correct questionnaire", on_click=_open_tab, args=(REPORT_TAB,), key="review_report",
                  type="primary" if decision.missing_answers else "secondary", width="stretch")
    st.button("View resident weather", on_click=_open_tab, args=(WEATHER_TAB,), key="view_weather", width="stretch")
    with st.expander("Why this score?"):
        st.plotly_chart(contributions_figure(model, person), width="stretch", key="planner_model_terms")
        st.caption(f"{'Questionnaire + public climate' if variant == 'climate' else 'Questionnaire-only'} model · synthetic outcome. "
                   "Intercept + input/missingness terms = total log-odds. Associations, not medical causes or validated clinical risk.")
    questions = [("Diabetes", "dm_report"), ("Hypertension", "htn_report"), ("Family history", "family_report"), ("Outdoor work", "outdoor_report")]
    with st.expander("Questionnaire answers"):
        for label, column in questions:
            value = person[column]
            st.write(f"{label}: **{'Unknown / not answered' if pd.isna(value) else 'Yes' if value == 1 else 'No'}**")


def _resident_timeline(person, current, followup, history, applied, day):
    with st.expander(f"Selected resident {person.resident_id} · simulated screening & follow-up timeline"):
        st.caption("Simulation evaluation, not actual clinical attendance. Report validation is a schema check. "
                   "Follow-up climate eligibility and simulated attendance are separate checks.")
        for stage, status in resident_timeline(person, current, followup, history, applied, day):
            st.markdown(f"**{stage}**")
            st.write(status)


def _select_bottleneck(policies):
    for point in st.session_state["bottleneck_chart"]["selection"]["points"]:
        data = point.get("customdata", [])
        if isinstance(data, (list, tuple)) and len(data) >= 3 and data[0] in BUCKETS and data[2] in policies:
            st.session_state.update(eval_category=data[0], eval_policy=data[2])
            break


# Readable headers and fixed decimals for resident tables on the Evaluate page.
EVALUATION_COLUMNS = {
    "resident_id": st.column_config.TextColumn("Resident"),
    "municipality": st.column_config.TextColumn("Municipality"),
    "age": st.column_config.NumberColumn("Age", format="%d"),
    "reported": st.column_config.CheckboxColumn("Reported"),
    "score": st.column_config.NumberColumn("Score", format="percent"),
    "nearest_distance_km": st.column_config.NumberColumn("Nearest point (km)", format="%.1f"),
    "reason": st.column_config.TextColumn("Selection reason"),
    "assigned_km": st.column_config.NumberColumn("Assigned (km)", format="%.1f"),
}


def _bottleneck_inspector(result, queue, settings):
    policies = live_policies(result, settings)
    counts = bottleneck_counts(policies)
    st.markdown("**Why were abnormal cases missed?**")
    picture = px.bar(counts, x="Share", y="Plan", color="Category", orientation="h", text="Count",
                     custom_data=["Category", "Count", "Plan"], category_orders={"Category": list(BUCKETS)},
                     # Found carries the one data hue; the three ways of missing step down in neutrals.
                     color_discrete_sequence=["#12796d", "#8fa39b", "#c4d0cb", "#7a5646"],
                     labels={"Share": "Share of all eligible hidden positives", "Plan": "Live policy"})
    picture.update_layout(barmode="stack", xaxis_tickformat=".0%", xaxis_range=[0, 1], height=310,
                          legend=dict(orientation="h", y=-.3), margin=dict(l=0, r=10, t=10, b=40))
    picture.update_traces(hovertemplate="%{customdata[2]}<br>%{customdata[0]}: %{customdata[1]} (%{x:.1%})<extra></extra>")
    st.plotly_chart(picture, key="bottleneck_chart", on_select=lambda: _select_bottleneck(policies),
                    selection_mode="points", width="stretch")
    st.caption("Each bar splits the same eligible hidden positives. Click a segment or choose a category below. "
               "All plans use the live inputs, active model, whole-cohort budget and shared random draws.")
    if st.session_state.get("eval_policy") not in policies:
        st.session_state["eval_policy"] = settings["strategy"] if settings["strategy"] in policies else (
            "Pure risk · 0% outreach" if settings["strategy"] == "Prioritize higher scores" else f"Priority + {settings['outreach']:.0%} outreach")
    label = st.selectbox("Evaluation policy", list(policies), key="eval_policy")
    category = st.radio("Inspect evaluation category", ["All invited", *BUCKETS], horizontal=True, key="eval_category")
    records = policies[label]
    ids = set(records.loc[evaluation_mask(records, category), "resident_id"])
    inspected = queue.loc[queue.resident_id.isin(ids), ["resident_id", "municipality", "age", "reported", "score", "nearest_distance_km"]].copy()
    decisions = records.set_index("resident_id")
    inspected["reason"] = inspected.resident_id.map(decisions.reason).map(SELECTION_REASONS)
    inspected["assigned_km"] = inspected.resident_id.map(decisions.distance_km)
    st.caption(f"{len(inspected):,} residents · {label} · {category}. This evaluation filter does not change the operational queue or export.")
    if inspected.empty:
        st.info("No residents fall in this category for this plan.")
    else:
        ids = tuple(inspected.resident_id)
        key = "eval_rows_" + hashlib.sha256(repr((label, category, ids)).encode()).hexdigest()[:14]
        areas = dict(zip(inspected.resident_id, inspected.municipality))
        st.dataframe(inspected, hide_index=True, height=220, key=key, selection_mode="single-row",
                     on_select=lambda: _select_evaluation_row(key, ids, areas), column_config=EVALUATION_COLUMNS)
        pick, go_to = st.columns([3, 1], vertical_alignment="bottom")
        selected = pick.selectbox("Evaluation resident to inspect", list(ids), index=None, key=key + "_resident")
        go_to.button("Inspect evaluation resident in planner", disabled=selected is None, width="stretch",
                     on_click=_inspect_evaluation_resident, args=(selected, areas.get(selected)))
        st.caption("Selecting a row opens that resident's planner details and clears view filters. Their operational invitation still refers to the selected main strategy.")
    swaps = marginal_swap(result["risk"], result["mixed"])
    st.markdown(f"**What changed between pure risk and {settings['outreach']:.0%} outreach?**")
    st.dataframe(swaps, hide_index=True, column_config={"Mean_score": st.column_config.NumberColumn("Mean score", format="percent"),
                 "Mean_age": st.column_config.NumberColumn("Mean age", format="%.1f"),
                 "Reported_share": st.column_config.NumberColumn("Reported", format="percent"),
                 "Access_feasible_share": st.column_config.NumberColumn("Access feasible", format="percent")})
    found_risk = int(result["risk"].positive_detected.sum())
    found_mix = int(result["mixed"].positive_detected.sum())
    st.write(f"Pure risk detected **{found_risk}** initial abnormal flags; {settings['outreach']:.0%} outreach detected **{found_mix}** "
             f"({found_mix-found_risk:+d}). Invitation changes above describe the actual set differences, including shared-capacity effects.")
    st.caption("Uniform outreach among reachable residents does not make completed tests an unbiased province-wide prevalence sample: "
               "distance and service-capacity limits remain, and completion can be non-random under MAR/MNAR. Empty groups have undefined means.")


def _municipal_plan_map(working, queue, records, facilities, cfg, root, variant):
    """Keep upstream municipal summaries aligned with the live planner model."""
    summary = records.groupby("municipality", as_index=False).agg(
        invited=("invited", "sum"), completed=("completed", "sum"))
    summary = summary.merge(queue.groupby("municipality", as_index=False).score.mean(), on="municipality")
    metrics = {"Invitations": ("invited", "Invited synthetic adults", ",.0f"),
               "Completed screening": ("completed", "Completed screening panels", ",.0f"),
               "Mean screening score": ("score", "Mean abnormal-flag probability", ".1%")}
    if "municipality_represented_adults" in working:
        represented = working.groupby("municipality", as_index=False).municipality_represented_adults.first()
        summary = summary.merge(represented, on="municipality")
        metrics["Represented adults"] = ("municipality_represented_adults", "Modeled adults represented", ",.0f")
    if variant == "climate" and "hot_dry_score" in working:
        summary = summary.merge(working.groupby("municipality", as_index=False).hot_dry_score.mean(), on="municipality")
        metrics["Mean hot–dry score"] = ("hot_dry_score", "Mean hot–dry anomaly score", ".2f")
    st.markdown("**Municipal plan summaries**")
    column, title, number_format = metrics[st.selectbox("Map metric", list(metrics), key="map_metric")]
    figure = municipal_map(summary.rename(columns={column: "value"})[["municipality", "value"]],
                           _cached_municipal_features(str(root), cfg["study_area"]["pilot_area"]),
                           facilities, color_title=title, value_format=number_format)
    if figure is None:
        st.caption("Municipal map needs collected public boundaries and matching municipality names; no map is shown for fixture zones.")
    else:
        st.plotly_chart(figure, width="stretch", key="municipal_plan_map")
        st.caption("Local geoBoundaries ADM3 geometry; no map tiles or external geographic assets. "
                   "Values use the live plan and active model; service points and screening outcomes are synthetic.")


def _plan_export(result, queue, settings, run_id, variant):
    if result is None:
        st.caption(f"{len(queue):,} synthetic adults · one shared screening budget · view filters never change allocation.")
        st.download_button("Download whole-plan invitation preview", data="", file_name="invitation_preview.csv", disabled=True, key="plan_export", width="stretch")
        return
    summary = result["proposed_summary"]
    st.markdown(f"**Whole-cohort plan:** {int(summary['invitations']):,} invitations · {settings['budget']:,} available panels · {len(queue):,} cohort adults")
    export = invitation_export(queue, run_id, variant, settings)
    st.download_button("Download whole-plan invitation preview", export.to_csv(index=False),
                       f"invitations_{run_id}.csv", "text/csv", disabled=export.empty, key="plan_export", type="primary", width="stretch")
    st.caption("Whole cohort, independent of view filters · hypothetical service points · no invitations sent.")


def _plan_summary(result, queue, cfg):
    """Operational plan facts only; simulated outcomes stay on the Evaluate page."""
    if result is None:
        return
    records = result["proposed"]
    invited = records.loc[records.invited.astype(bool)]
    budget = int(st.session_state["comparison_settings"]["budget"])
    outside = int((~records.access_feasible.astype(bool)).sum())
    st.markdown(f'<div class="agap-plan-summary" aria-label="Draft plan summary">'
                f'<div><strong>{len(invited):,}</strong><span>of {budget:,} panels assigned</span></div>'
                f'<div><strong>{invited.municipality.nunique():,}</strong><span>of {queue.municipality.nunique():,} municipalities reached</span></div>'
                f'<div><strong>{invited.facility_id.nunique():,}</strong><span>service points used</span></div>'
                f'<div><strong>{outside:,}</strong><span>residents beyond {float(cfg["allocation"]["max_distance_km"]):g} km</span></div>'
                '</div>', unsafe_allow_html=True)
    settings = st.session_state["comparison_settings"]
    st.markdown("**Who this plan reaches** · invitations by questionnaire status")
    st.dataframe(reach_by_questionnaire(queue), hide_index=True, column_config={
        "Invitation coverage": st.column_config.ProgressColumn(format="percent", min_value=0., max_value=1.)})
    st.caption(provenance_caption(f"draft plan · {settings['strategy']} · {int(settings['budget']):,} panels",
                                  f"{len(queue):,} {geography_label(cfg)}", deployment_period(),
                                  "residents invited; % of residents in each group", "synthetic simulation"))
    st.caption("Operational counts only; no hidden outcome is used. Residents who never reported are not known to be at lower risk.")
    st.button("Evaluate this plan with simulated outcomes", key="open_evaluate", on_click=_open_tab, args=(EVALUATE_TAB,))


def _plan_results(result, queue, settings, run_id, variant, followup, persistence_day,
                  working, facilities, cfg, root):
    if result is None:
        return
    summary = result["proposed_summary"]
    st.subheader("Does this plan find more abnormal screens than random invitations?")
    st.caption(f"Same {int(settings['budget']):,}-panel budget, cohort, capacities, access limit and simulation draws. "
               "One simulated round; a difference in either direction is possible.")
    random_found = int(result["random_summary"]["positives_detected"])
    left, right = st.columns(2)
    for column, label, metrics in ((right, "Random invitations", result["random_summary"]),
                                   (left, settings["strategy"], summary)):
        found = int(metrics["positives_detected"])
        # Both cards carry a delta line so the pair ends level; random is the baseline.
        column.metric("Abnormal initial results found", found, border=True,
                      delta=f"{found - random_found:+d} vs random" if metrics is summary else "Baseline",
                      delta_color="normal" if metrics is summary else "off", delta_arrow="auto" if metrics is summary else "off")
        column.caption(f"{label} · {int(metrics['invitations']):,} invited → {int(metrics['completions']):,} simulated completions")
    st.dataframe(positives_by_questionnaire(result["proposed"]), hide_index=True)
    st.caption(provenance_caption("draft plan and simulator hidden outcomes", f"{len(queue):,} {geography_label(cfg)}",
                                  deployment_period(), "initial abnormal screening flags (not diagnoses)",
                                  "simulation evaluation (hidden truth)"))
    _bottleneck_inspector(result, queue, settings)
    _municipal_plan_map(working, queue, result["proposed"], facilities, cfg, root, variant)
    if followup is not None:
        day = persistence_day
        st.markdown(f"**Do the abnormal results persist?** Simulated repeat tests at {day} days")
        st.dataframe(persistence_by_plan((("Random invitations", result["random"]),
                                        (settings["strategy"], result["proposed"])), followup, day), hide_index=True)
        st.caption(LONGITUDINAL_LABEL + " Counts use simulated follow-up results, not actual repeat attendance. "
                   "Residents without sufficient follow-up coverage are excluded.")


def _model_comparison(scored, facilities, cfg, settings, variant, run_id, comparison=None):
    st.subheader("Climate impact on invitations")
    st.caption(f"Active plan: {MODEL_LABELS[variant]}. Both models use the same {len(scored):,} residents, "
               "saved dates, applied answers, budget, strategy, service capacities, tie-breaks and random draws. "
               "Only model scores change. View filters never change this comparison.")
    try:
        if comparison is None:
            comparison = model_comparison_at(scored, facilities, cfg, **settings)
    except (ValueError, CoverageInfeasibleError) as exc:
        st.warning(f"Paired model comparison unavailable: {exc}. The active plan is unchanged on the Plan page.")
        return
    decisions = comparison["decisions"]
    added = int(decisions.change.eq("Added with climate").sum())
    removed = int(decisions.change.eq("Removed with climate").sum())
    left, middle, right = st.columns(3)
    left.metric("Added with climate", added)
    middle.metric("Removed with climate", removed)
    right.metric("Unchanged invitation decisions", len(decisions)-added-removed)
    changed = decisions.loc[decisions.change.isin(["Added with climate", "Removed with climate"])]
    if changed.empty:
        st.info("Both models invite the same residents under these settings. A score difference need not change an invitation.")
    else:
        category = st.radio("Changed invitations to inspect", ["All changes", "Added with climate", "Removed with climate"],
                            horizontal=True, key="flow_model_change_filter")
        inspected = changed if category == "All changes" else changed.loc[changed.change.eq(category)]
        ids = tuple(inspected.resident_id)
        areas = dict(zip(inspected.resident_id, inspected.municipality))
        key = "flow_model_change_rows_" + hashlib.sha256(repr(ids).encode()).hexdigest()[:12]
        st.dataframe(inspected, hide_index=True, height=220, width="stretch", key=key,
                     selection_mode="single-row", on_select=lambda table_key=key, row_ids=ids, row_areas=areas:
                     _select_evaluation_row(table_key, row_ids, row_areas),
                     column_config={"clinical_score": st.column_config.NumberColumn("Questionnaire score", format="%.3f"),
                                    "climate_score": st.column_config.NumberColumn("Climate model score", format="%.3f")})
        st.caption("Select a row to follow that resident on the Plan page. Their decision and export always use the active planning model.")
    exported = comparison_export(decisions, run_id, variant, settings)
    st.download_button("Download model invitation comparison", exported.to_csv(index=False),
                       "model_invitation_comparison.csv", "text/csv", key="model_comparison_export")
    st.subheader("Model evaluation · synthetic outcomes")
    evaluation = comparison["evaluation"]
    found = evaluation.set_index("model").positives_detected
    delta = int(found["climate"]-found["clinical"])
    st.write(f"Climate model minus questionnaire-only model: **{delta:+d} simulated abnormal initial results found** at the same budget.")
    st.caption("Simulator truth only. Health outcomes include an assumed climate effect; these are not patient outcomes or evidence of clinical benefit. "
               "Single-run differences do not establish statistical significance. Positive, negative and zero differences are reported without choosing a winner automatically.")
    st.dataframe(evaluation.rename(columns={"label": "Model", "invitations": "Invited", "completions": "Completed",
        "positives_detected": "Abnormal flags found", "positives_not_detected": "Abnormal flags missed",
        "eligible_positives": "All eligible abnormal flags"}).drop(columns="model"), hide_index=True)
    st.dataframe(comparison["diagnostics"].drop(columns="model").rename(columns={
        "label": "Model", "residents": "Residents", "auroc": "AUROC", "auprc": "AUPRC", "brier": "Brier score"}), hide_index=True)
    chart = go.Figure(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Perfect calibration",
                                line=dict(color="#a6b2be", dash="dash")))
    for name, points in comparison["calibration"].groupby("label", sort=False):
        chart.add_trace(go.Scatter(x=points.mean_score, y=points.abnormal_fraction,
            customdata=points.residents, mode="lines+markers", name=name,
            hovertemplate="Mean score %{x:.1%}<br>Abnormal fraction %{y:.1%}<br>%{customdata} residents<extra>%{fullData.name}</extra>"))
    chart.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(title="Mean predicted probability", range=[0, 1], tickformat=".0%"),
        yaxis=dict(title="Simulated abnormal fraction", range=[0, 1], tickformat=".0%"), legend=dict(orientation="h"))
    st.plotly_chart(chart, key="model_calibration", width="stretch")
    st.caption("Fixed 0.1-wide probability bins; empty bins omitted and counts shown on hover. Models are not refitted or recalibrated here. "
               "These diagnostics use the current report scenario and whole deployment cohort; saved training/test artifacts remain unchanged.")


def render_walkthrough(frame, facilities, clinical_model, climate, cfg, run_id, root, followup=None, weather=None, directory=None):
    """Return supporting tab handles and the current whole-cohort session inputs."""
    if frame.empty:
        st.error("This saved run has no residents. Prepare the demonstration again.")
        st.stop()
    run_changed = st.session_state.get("demo_run") != run_id
    if run_changed:
        _clear_report()
        for key in list(st.session_state):
            if key.startswith(("flow_", "queue_", "eval_")) or key in ("panel_budget", "plan_choice", "outreach_choice", "workspace_tab", "workspace_panel", "community_map", "community_street_map", "community_hex_map", "bottleneck_chart"):
                del st.session_state[key]
        st.session_state.update(demo_run=run_id, applied_reports={}, comparison_started=False,
                               comparison_settings=dict(budget=min(500, len(frame)), strategy="Priority + random outreach", outreach=.2))
    elif "applied_reports" not in st.session_state:
        # Migrate an already-open walkthrough session on Streamlit's hot reload.
        previous = st.session_state.pop("report_applied", None)
        st.session_state["applied_reports"] = {previous["resident_id"]: previous} if previous else {}
        _clear_report()
    approved = _approved_round(root, run_id)
    st.session_state["workflow_database"] = str(_workflow_path(root))
    st.session_state["workflow_active_round"] = approved["round_id"] if approved else None
    st.session_state["workflow_round_version"] = approved["version"] if approved else None
    if approved:
        restored = dict(approved["snapshot"].get("applied_reports", {}))
        try:
            for event in get_events(_workflow_path(root), approved["round_id"]):
                if event["event_type"] == "report_applied":
                    restored[event["resident_id"]] = event["payload"]
        except (ValueError, RuntimeError, sqlite3.Error) as exc:
            st.session_state["workflow_load_error"] = f"Unable to load report amendments: {exc}"
            st.error(st.session_state["workflow_load_error"])
        st.session_state["applied_reports"] = {**st.session_state["applied_reports"], **restored}
    if run_changed or "workspace_tab" not in st.session_state:
        st.session_state["workspace_tab"] = WORKLIST_TAB if approved else PLAN_TAB
    if st.session_state.pop("workflow_open_worklist", False):
        st.session_state["workspace_tab"] = WORKLIST_TAB
    with st.sidebar:
        if st.button("Reset draft workspace"):
            st.session_state.pop("demo_run", None)
            st.rerun()
        st.caption("Reset clears draft selections and comparisons. Approved rounds and their report amendments, activities and histories are retained.")
    climate_model = climate["model"] if climate is not None else None
    working = with_reports(frame, st.session_state["applied_reports"])
    # Self-reported citizen profiles (unverified) route known-CKD residents to their care plan.
    profiles = root / "data/reports" / run_id / "citizen_profiles.jsonl"
    working = working.assign(reported_known_ckd=working.resident_id.isin(known_ckd_residents(profiles)))
    scored = score_cohort(working, clinical_model, climate_model)
    tabs = dict(zip(WORKSPACE_PAGES, _page_navigation()))
    comparison = None
    worklist_selected = None
    with tabs[WORKLIST_TAB]:
        with st.container(key="screening_worklist_stage"):
            if approved:
                worklist_selected = render_worklist(root, approved, st.session_state.get("flow_resident"))
            else:
                st.info("No approved round yet. Compare a draft plan, then approve it to start the staff worklist.")
                st.button("Open Plan", key="worklist_open_plan", on_click=_open_tab, args=(PLAN_TAB,))
    with tabs[PLAN_TAB], st.container(key="screening_plan_stage"):
        st.caption(f"{len(working):,} synthetic adults · {int((~working.reported).sum()):,} without a questionnaire · "
                   f"{st.session_state['comparison_settings']['budget']:,} panels · draft planning")
        with st.container(key="workspace_mobile_toggle"):
            mobile_view = st.radio("Workspace view", ["Tasks", "Map"], horizontal=True, key="workspace_mobile_view", label_visibility="collapsed")
        with st.container(key="responsive_mode_" + mobile_view.lower()):
            left, right = st.columns([2.8, 1], gap="small")
            with left:
                with st.container(key="map_workspace"):
                    view_control, model_control, background_control = st.columns([1.4, 1.1, .8], vertical_alignment="center")
                    mode = view_control.radio("Map view", ["2D community map", "3D H3 hex map"], horizontal=True, key="flow_map_mode", label_visibility="collapsed")
                    available_models = list(MODEL_LABELS) if climate_model is not None else ["clinical"]
                    if st.session_state.get("flow_model") not in available_models:
                        st.session_state["flow_model"] = "clinical"
                    variant = model_control.selectbox("Planning model", available_models, format_func=MODEL_LABELS.get,
                        key="flow_model", on_change=_model_changed, disabled=climate_model is None, label_visibility="collapsed",
                        help="Changes scores, invitations, map summaries and export together; existing budget/strategy and reports are retained.")
                    # Fixture zones are an illustrative box, not real places: never draw them over real streets.
                    backgrounds = ["Street map", "Outline map"] if cfg["prototype"]["geography_mode"] == "public" else ["Outline map"]
                    if st.session_state.get("flow_basemap") not in backgrounds:
                        st.session_state["flow_basemap"] = backgrounds[0]
                    background = background_control.selectbox("Map background", backgrounds, key="flow_basemap",
                        label_visibility="collapsed", disabled=len(backgrounds) == 1,
                        help=None if len(backgrounds) > 1 else "Street map is off for fixture runs: the zones are illustrative, not real Laguna places.")
                    map_panel = st.container()
            with right:
                with st.container(border=True, height=MAP_HEIGHT + 38, key="workspace_tools"):
                    residents_panel, decision_panel, plan_panel = st.tabs(["Residents", "Decision", "Plan settings"], key="workspace_panel", on_change="rerun")
                    with plan_panel:
                        st.subheader("Prepare screening invitations")
                        st.caption(f"Active planning model: {MODEL_LABELS[variant]}")
                        result = _plan_controls(working, scored, facilities, cfg, variant)
                        _plan_formation(working, facilities, cfg, variant,
                                        st.session_state["comparison_settings"], approved)
                    queue = planner_queue(scored, variant, cfg["allocation"]["max_distance_km"], result["proposed"] if result else None)
                    plan_state = "ready" if result is not None else "unavailable" if st.session_state["comparison_started"] else "unplanned"
                    queue["display_status"] = queue_status(queue, plan_state)
                    if result is not None and climate_model is not None:
                        try:
                            comparison = model_comparison_at(scored, facilities, cfg, **st.session_state["comparison_settings"])
                        except (ValueError, CoverageInfeasibleError):
                            # The full comparison below explains the error; no stale
                            # markers or resident verdict are shown in the meantime.
                            comparison = None
                    _finish_report_handoff(queue)
                    _finish_model_handoff(queue)
                    if worklist_selected:
                        filters = {name: st.session_state.get(key, QUEUE_FILTER_DEFAULTS[name]) for name, key in QUEUE_FILTER_KEYS.items()}
                        for name, value in filters_for_resident(queue, worklist_selected, filters).items():
                            st.session_state[QUEUE_FILTER_KEYS[name]] = value
                        st.session_state["flow_resident"] = worklist_selected
                    with residents_panel:
                        with st.container(key="community_workspace"):
                            st.subheader("Community resident queue")
                            area, visible = _queue_filters(queue, result is not None)
                            selected = _queue_table(visible, len(queue))
                    person = scored.loc[scored.resident_id.eq(selected)].iloc[0] if selected else None
                    decision = queue.loc[queue.resident_id.eq(selected)].iloc[0] if selected else None
                    day = cfg.get("longitudinal", {}).get("persistence_day", 180)
                    current = result["proposed"].set_index("resident_id").loc[selected] if result is not None and selected else None
                    visit = followup.loc[followup.resident_id.eq(selected)] if followup is not None and selected else pd.DataFrame()
                    history = resident_history(root / "data/reports/citizen_reports.jsonl", selected) if selected else []
                    with decision_panel:
                        with st.container(key="resident_decision"):
                            _resident_detail(person, decision, climate_model if variant == "climate" else clinical_model, len(frame), variant,
                                             current, cfg["allocation"]["max_distance_km"],
                                             latest_profile(profiles, selected) if selected else None)
                    with plan_panel:
                        _plan_export(result, queue, st.session_state["comparison_settings"], run_id, variant)
            with map_panel:
                boundary, cells = _map_artifacts(directory) if directory is not None else (None, None)
                work = None
                if approved:
                    try:
                        work = round_work(round_worklist(_workflow_path(root), approved["round_id"]))
                    except (ValueError, RuntimeError, sqlite3.Error):
                        work = None
                choices = ["Without a questionnaire"] + (["Invitation coverage (draft plan)"] if result is not None else []) \
                    + (["Open follow-up work (approved round)"] if work is not None else []) + ["Mean model score"]
                default = 2 if work is not None and result is not None else 1 if (work is not None or result is not None) else 0
                if st.session_state.get("community_metric") not in choices:
                    st.session_state["community_metric"] = choices[default]
                metric_name = st.selectbox("Colour communities by", choices, key="community_metric",
                                           help="Circle colour; circle size is always the number of cohort adults.")
                metric = COMMUNITY_METRICS[metric_name][0]
                st.markdown('<div class="agap-map-label">' + escape(COMMUNITY_METRICS[metric_name][1]) + '</div>', unsafe_allow_html=True)
                show_changes = st.session_state.get("map_show_changes", False)
                changes = comparison["decisions"] if comparison is not None and show_changes else None
                source = basemap_source(browser_url=st.context.url, base_path=st.get_option("server.baseUrlPath")) if background == "Street map" else None
                if mode == "2D community map" and source:
                    deck = community_street_deck(queue, frame, facilities, source["style"], boundary, cells,
                                                  result is not None, selected, model_changes=changes, metric=metric, work=work)
                    st.pydeck_chart(deck, key="community_street_map", on_select=lambda: _select_street_community(set(queue.municipality)),
                        selection_mode="single-object", width="stretch", height=MAP_HEIGHT,
                        alt="OpenStreetMap street basemap with selectable synthetic community summaries")
                    st.caption("Select a community, then a resident. Circle size: cohort adults · colour: the measure chosen above · "
                               "white dots: hypothetical screening points · amber: selected resident.")
                elif mode == "2D community map":
                    figure = community_figure(queue, frame, facilities, boundary, cells, result is not None, area, selected, run_id,
                                              model_changes=changes, metric=metric, work=work)
                    figure.update_layout(height=MAP_HEIGHT)
                    st.plotly_chart(figure, key="community_map", on_select=lambda: _select_map_community(set(queue.municipality)),
                                    selection_mode="points", width="stretch")
                    st.caption("Select a community, then a resident. Circle size: cohort adults · colour: the measure chosen above.")
                else:
                    deck = community_hex_deck(queue, frame, facilities, boundary, cells, result is not None, area, selected,
                                              basemap_style=source["style"] if source else None, model_changes=changes)
                    st.pydeck_chart(deck, key="community_hex_map", on_select=lambda: _select_hex_community(set(queue.municipality)),
                                    selection_mode="single-object", width="stretch", height=MAP_HEIGHT,
                                    alt="Synthetic resident counts by H3 cell; click a column to select its community")
                    st.caption("Column height: cohort adults (90 display metres/adult, not terrain). Color: invitation coverage after planning, mean score before. Click a hex to select its community.")
                if changes is not None:
                    added, removed = (int(changes.change.eq(label).sum()) for label in ("Added with climate", "Removed with climate"))
                    st.markdown(f'<div class="agap-map-changes" aria-label="Paired model invitation changes"><b>Same budget · model comparison</b>'
                        f'<span><i class="agap-map-added"></i>{added:,} added with climate</span>'
                        f'<span><i class="agap-map-removed"></i>{removed:,} removed with climate</span>'
                        '<small>Resident list in Evaluate</small></div>', unsafe_allow_html=True)
                if source:
                    availability = "Local street pack · available offline" if source["offline"] else "Online street tiles · internet required (make collect-map for offline streets)"
                    st.caption(availability + " · [OpenFreeMap](https://openfreemap.org/) · © [OpenMapTiles](https://openmaptiles.org/) · Data from [OpenStreetMap](https://www.openstreetmap.org/copyright).")
        _plan_summary(result, queue, cfg)
        if climate_model is not None and result is not None:
            st.checkbox("Show climate invitation changes on the map", key="map_show_changes")
        with st.container(key="round_approval"):
            manifest = json.loads((directory / "manifest.json").read_text()) if directory is not None else None
            render_round_approval(root, run_id, scored, facilities, result, cfg, variant,
                                  st.session_state["comparison_settings"], manifest,
                                  st.session_state["applied_reports"])
    with tabs[EVALUATE_TAB], st.container(key="evaluate_area"):
        st.markdown('<div class="agap-sim-banner" role="note"><b>SIMULATION TRUTH</b> Hidden simulated outcomes, '
                    'not visible in practice. Nothing here changes the plan, worklist or exports.</div>', unsafe_allow_html=True)
        plan_eval, climate_eval, surveillance_area, safeguards_area = st.tabs(
            ["Plan vs random", "Climate vs questionnaire", "Surveillance", "Safeguards"])
        with plan_eval:
            if result is None:
                st.info("Compare screening plans on the Plan page to evaluate them here.")
            else:
                _plan_results(result, queue, st.session_state["comparison_settings"], run_id, variant, followup, day,
                              working, facilities, cfg, root)
            if person is not None:
                _resident_timeline(person, current, visit.iloc[0] if not visit.empty else None, history,
                                   selected in st.session_state["applied_reports"], day)
        with climate_eval:
            if climate_model is None:
                st.info("This run has no climate model. Use the climate profile to compare models.")
            elif result is None:
                st.info("Compare screening plans on the Plan page to compare both models at the same budget.")
            else:
                _model_comparison(scored, facilities, cfg, st.session_state["comparison_settings"], variant, run_id, comparison)
    with tabs[DATA_TAB]:
        data_area = st.container()
    with tabs[REPORT_TAB]:
        if person is None:
            st.info("Select a resident on the Plan or Worklist page before entering a report.")
        else:
            _report_step(working, person, clinical_model, climate_model, scored, root, variant)
    with tabs[WEATHER_TAB]:
        if approved:
            st.info("This is a draft model comparison. The approved screening round keeps its saved assignments, model and replacement order.")
        if person is None:
            st.info("Select a resident on the Plan or Worklist page to view their weather context and score.")
        else:
            with st.container(key="weather_workspace"):
                _weather_step(working, scored, person, clinical_model, climate, weather, variant, decision,
                              comparison, st.session_state["comparison_settings"] if result is not None else None, plan_state)
    return dict(surveillance=surveillance_area, safeguards=safeguards_area, data=data_area), working, selected
