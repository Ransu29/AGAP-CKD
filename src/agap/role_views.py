"""Demo role views: citizen, health worker and LGU / analyst share one synthetic run.

The role switch is a demonstration label, not authentication or access control. Health workers
see individual records; the LGU / analyst view shows municipal aggregates only; citizens see their
own fictional profile and plain-language status, never scores, ranks or other residents.
"""
from __future__ import annotations

import json
import math
import sqlite3

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from agap.basemap import basemap_source

from agap.citizen import (AGE_BANDS, DIAGNOSIS_ANSWERS, DRAFT_CONTENT, GUIDANCE, KIDNEY_STATES, NOT_A_DIAGNOSIS,
                          QUESTIONS, age_band, append_profile, invitation_message, latest_profile, normalize_profile)
from agap.community_map import aggregate_deck, clinic_points, municipal_positions
from agap.community_overview import cohort_summary, round_summary, round_work, suppress
from agap.registers import LOCATION_PRECISION, REGISTER_TITLE, display_text, load_clinics
from agap.provenance import deployment_period, geography_label, provenance_caption
from agap.workflow_store import active_round, worklist
from agap.workflow_ui import workflow_path

ROLES = ("Health worker (RHU)", "LGU / public-health analyst", "Citizen")
ROLE_HELP = {
    ROLES[0]: "Individual records: plan and approve screening rounds, then contact, screen, review and follow up.",
    ROLES[1]: "Municipal aggregates only, with small counts suppressed. No individual records.",
    ROLES[2]: "One fictional resident's own profile, information and invitation status. No scores or rankings.",
}


DEMO_ACCOUNT_NOTE = "Simulated sign-in for the demo: no password, no authentication and no access control."


def _sign_in(role):
    st.session_state["view_role"] = role


def _sign_out():
    st.session_state.pop("view_role", None)


def signed_in_role():
    role = st.session_state.get("view_role")
    return role if role in ROLES else None


def sign_in_screen():
    """Landing page that stands in for a login; choosing an account only sets the demo role."""
    st.subheader("Sign in")
    st.caption(DEMO_ACCOUNT_NOTE)
    for column, role in zip(st.columns(len(ROLES)), ROLES):
        with column.container(border=True):
            st.markdown(f"**{role}**")
            st.caption(ROLE_HELP[role])
            st.button(f"Sign in as {role}", key=f"sign_in_{ROLES.index(role)}", on_click=_sign_in, args=(role,),
                      type="primary", width="stretch")


def account_sidebar(role):
    with st.sidebar:
        st.markdown(f"Signed in as **{role}**")
        st.caption(f"{ROLE_HELP[role]} {DEMO_ACCOUNT_NOTE}")
        st.button("Sign out", key="sign_out", on_click=_sign_out, width="stretch",
                  help="Return to the sign-in screen to switch to another demo account.")
        st.divider()


def _round_worklist(root, run_id):
    try:
        approved = active_round(workflow_path(root), run_id)
        return approved, (worklist(workflow_path(root), approved["round_id"]) if approved else None)
    except (ValueError, RuntimeError, sqlite3.Error) as exc:
        st.error(f"Unable to load the screening round: {exc}")
        return None, None


def _street_style(cfg):
    if cfg["prototype"]["geography_mode"] != "public":
        return None  # fixture zones are illustrative: never drawn over real streets
    source = basemap_source(browser_url=st.context.url, base_path=st.get_option("server.baseUrlPath"))
    return source["style"] if source else None


def _run_geometry(directory):
    boundary = json.loads((directory / "boundary.geojson").read_text()) if (directory / "boundary.geojson").exists() else None
    cells = pd.read_parquet(directory / "cells.parquet") if (directory / "cells.parquet").exists() else None
    return boundary, cells


def _clinic_caption(clinics):
    counts = clinics.location_precision.value_counts()
    detail = " · ".join(f"{LOCATION_PRECISION[key]}: {int(counts.get(key, 0))}" for key in LOCATION_PRECISION)
    return (f"Dialysis clinics: {len(clinics)} from PhilHealth, {REGISTER_TITLE} (Laguna rows). {detail}. "
            "Freestanding clinics only; hospital-based units are listed separately by PhilHealth. Accreditation does not "
            "establish current slots, schedule or cost. Positions: © OpenStreetMap contributors (ODbL) via Overpass and "
            "Nominatim. References: data/manifest.yaml.")


def _lgu_map(frame, cfg, directory, cases, minimum, clinics, root):
    names = sorted(frame.municipality.unique())
    boundary, cells = _run_geometry(directory)
    points = municipal_positions(names, frame, cells)
    options = ["Questionnaire coverage"] + (["Open follow-up work"] if cases is not None and not cases.empty else [])
    measure = st.selectbox("Colour municipalities by", options, key="lgu_metric")
    adults = frame.groupby("municipality").size()
    reported = frame.reported.astype(bool).groupby(frame.municipality).sum()
    work = round_work(cases) if cases is not None else None
    values, labels = [], []
    for name in names:
        if measure == "Questionnaire coverage":
            total, part = int(adults[name]), int(reported[name])
            noun = "with a questionnaire"
        else:
            total = int(work.invited.get(name, 0)) if work is not None else 0
            part = int(work.open_tasks.get(name, 0)) if work is not None else 0
            noun = "invitations with open tasks"
        shown = total >= minimum and part >= minimum
        values.append(part / total if shown else np.nan)
        labels.append(f"{part / total:.0%} {noun}" if shown else f"Suppressed (fewer than {minimum})")
    points["value"], points["value_label"] = values, labels
    points["adults_label"] = [f"{suppress(adults[name], minimum)} cohort adults" for name in names]
    show_clinics = clinics is not None and st.checkbox("Show PhilHealth-accredited dialysis clinics", value=True, key="lgu_clinics")
    st.pydeck_chart(aggregate_deck(points, _street_style(cfg), boundary, clinics if show_clinics else None),
                    key="lgu_map", height=520, width="stretch")
    st.caption("Circles: municipalities in the synthetic cohort (grey = suppressed). Red dots: dialysis clinics; solid = mapped building, "
               "lighter = barangay centre, hollow = municipality centre (approximate).")
    if show_clinics:
        st.caption(_clinic_caption(clinics))
    yakap = load_clinics(root, "yakap")
    if yakap is not None:
        counts = yakap.location_precision.value_counts()
        st.caption(f"YAKAP primary-care clinics ({len(yakap)} registered in Laguna) serve as screening points on real-geography "
                   f"runs: {int(counts.get('osm', 0))} mapped buildings, {int(counts.get('barangay', 0))} barangay centres, "
                   f"{int(counts.get('municipality', 0))} municipality centres. Kidney test capability and capacity are not verified.")


def render_lgu_overview(frame, cfg, root, run_id, directory=None):
    minimum = int(cfg["privacy"]["min_cell_size"])
    population = geography_label(cfg)
    st.subheader("Community screening overview")
    st.caption(f"Municipal aggregates only. Counts from 1 to {minimum - 1} are shown as <{minimum}; "
               "individual residents and results stay in the health-worker view.")
    approved, cases = _round_worklist(root, run_id)
    if directory is not None:
        _lgu_map(frame, cfg, directory, cases, minimum, load_clinics(root), root)
    st.markdown("**Questionnaire reach and access** · synthetic cohort")
    st.dataframe(cohort_summary(frame, cfg["allocation"]["max_distance_km"], minimum), hide_index=True)
    st.caption(provenance_caption("saved synthetic cohort · questionnaire status at the saved cutoff", population, deployment_period(),
                                  "residents; % of cohort adults", "synthetic simulation"))
    st.markdown("**Recorded screening work** · approved round")
    if approved is None:
        st.info("No approved screening round for this run yet. A health worker creates one from the screening plan.")
        return
    st.dataframe(round_summary(cases, minimum), hide_index=True)
    st.caption(provenance_caption(f"approved round {approved['round_id'][:8]} · staff-recorded demo activity",
                                  "residents invited in this round, including replaced invitations", "round start to today",
                                  "residents per queue", "recorded demo activity"))
    st.caption("Queues reflect what staff recorded, not clinical outcomes. A follow-up gap means unfinished recorded work, "
               "not a missed diagnosis.")


def render_citizen(frame, cfg, root, run_id, facilities=None):
    st.subheader("My kidney screening")
    st.info("Demo: choose a fictional resident to see what they would see. Real people are not recorded here.")
    approved, cases = _round_worklist(root, run_id)
    invited = list(cases.resident_id) if cases is not None else []
    ids = invited + sorted(set(frame.resident_id) - set(invited))
    resident_id = st.selectbox("Fictional profile", ids, key="citizen_profile",
                               help="Residents in the current screening round are listed first.")
    person = frame.loc[frame.resident_id.eq(resident_id)].iloc[0]
    path = root / "data/reports" / run_id / "citizen_profiles.jsonl"
    saved = latest_profile(path, resident_id) or {}
    st.markdown("**Invitation status**")
    case = cases.loc[cases.resident_id.eq(resident_id)].iloc[0].to_dict() if resident_id in invited else None
    st.write(invitation_message(case))
    if case is not None and case.get("is_current") and case.get("facility_id"):
        st.caption(f"Screening point: {_point_label(facilities, case['facility_id'])}. No appointment is booked by this demo.")
    with st.form(f"citizen_form_{resident_id}"):
        st.markdown("**About you** · every question is optional")
        band = st.selectbox("Age group", AGE_BANDS, index=AGE_BANDS.index(saved.get("age_band", age_band(person.age))))
        municipality = st.text_input("Municipality or city", value=saved.get("municipality_code", person.municipality))
        state = st.radio(QUESTIONS["reported_kidney_state"], KIDNEY_STATES,
                         index=KIDNEY_STATES.index(saved.get("reported_kidney_state", "Not answered")))
        htn = st.radio(QUESTIONS["reported_diagnosed_htn"], DIAGNOSIS_ANSWERS, horizontal=True,
                       index=DIAGNOSIS_ANSWERS.index(saved.get("reported_diagnosed_htn", "Not answered")))
        dm = st.radio(QUESTIONS["reported_diagnosed_dm"], DIAGNOSIS_ANSWERS, horizontal=True,
                      index=DIAGNOSIS_ANSWERS.index(saved.get("reported_diagnosed_dm", "Not answered")))
        submitted = st.form_submit_button("Save my answers", type="primary")
    if submitted:
        profile, errors = normalize_profile(resident_id, dict(age_band=band, municipality_code=municipality,
                                                              reported_kidney_state=state,
                                                              reported_diagnosed_htn=htn, reported_diagnosed_dm=dm))
        if errors:
            st.error(" ".join(errors))
        else:
            saved = append_profile(path, profile)
            st.success("Saved to this fictional profile. Your answers are self-reported and are not a diagnosis.")
    state = saved.get("reported_kidney_state", "Not answered")
    if state in ("Diagnosed CKD, not receiving dialysis", "Receiving dialysis"):
        st.info("You reported a known kidney diagnosis. First-time screening invitations go to people without one, so "
                "a health worker will check your record and keep you with your doctor's care plan instead.")
    st.markdown(f"**Information for: {state}**")
    for line in GUIDANCE[state]:
        st.markdown(f"- {line}")
    st.caption(f"{DRAFT_CONTENT}. {NOT_A_DIAGNOSIS}")
    _citizen_places(person, state, case, facilities, cfg, root)


def _km(lat1, lon1, lat2, lon2):
    radians = math.pi / 180
    a = (math.sin((lat2 - lat1) * radians / 2) ** 2
         + math.cos(lat1 * radians) * math.cos(lat2 * radians) * math.sin((lon2 - lon1) * radians / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


def _point_label(facilities, facility_id):
    """Service point name with its status: registered clinics are real, SIM points hypothetical."""
    if facilities is None or facility_id not in set(facilities.facility_id):
        return f"{facility_id} (hypothetical)"
    point = facilities.loc[facilities.facility_id.eq(facility_id)].iloc[0]
    if str(facility_id).startswith("SIM-") or "name" not in point or not isinstance(point.get("name"), str):
        return f"{facility_id} (hypothetical demo location)"
    return (f"{display_text(point['name'])}, {point['municipality']} (PhilHealth YAKAP-accredited; kidney test availability "
            "not yet confirmed)")


def nearby_clinics(clinics, latitude, longitude, municipality, count=3):
    """Clinics in the resident's own municipality plus the nearest others, by straight-line distance."""
    table = clinics.assign(distance_km=[_km(latitude, longitude, lat, lon) for lat, lon in zip(clinics.latitude, clinics.longitude)])
    own = table.municipality_name.eq(municipality)
    return pd.concat([table[own], table[~own].nsmallest(count, "distance_km")]).sort_values("distance_km")


def _citizen_places(person, state, case, facilities, cfg, root):
    st.markdown("**Where to go**")
    diagnosed = state in ("Diagnosed CKD, not receiving dialysis", "Receiving dialysis")
    layers, table = [], None
    if facilities is not None and case is not None and case.get("is_current") and case.get("facility_id") in set(facilities.facility_id):
        point = facilities.loc[facilities.facility_id.eq(case["facility_id"])].iloc[0]
        layers.append(pdk.Layer("ScatterplotLayer", [dict(longitude=point.longitude, latitude=point.latitude,
            title="Your screening point", line1=_point_label(facilities, case["facility_id"]),
            line2="No appointment is booked by this demo", line3="")], id="screening_point", get_position="[longitude, latitude]",
            get_fill_color=[40, 110, 200, 230], get_radius=9, radius_units=pdk.types.String("pixels"), pickable=True))
    if diagnosed:
        clinics = load_clinics(root)
        if clinics is None or cfg["prototype"]["geography_mode"] != "public":
            st.info("Dialysis clinic locations are shown on the real-geography profile only.")
        else:
            table = nearby_clinics(clinics, float(person.latitude), float(person.longitude), person.municipality)
            layers += [pdk.Layer("ScatterplotLayer", clinic_points(table), id="dialysis_clinics",
                                 get_position="[longitude, latitude]", get_fill_color="fill_color",
                                 get_line_color=[120, 30, 20, 255], stroked=True, line_width_min_pixels=1.5,
                                 get_radius="radius", radius_units=pdk.types.String("pixels"), pickable=True)]
            if state == "Receiving dialysis":
                st.write("PhilHealth-accredited dialysis clinics in and near your area. Call first: a clinic needs your "
                         "nephrologist's dialysis order and recent results, and slots depend on the clinic.")
            else:
                st.write("For reference only: these clinics provide dialysis if your doctor advises it. Keep seeing your own "
                         "doctor for regular check-ups.")
    else:
        st.write("For a kidney check, ask your barangay health worker or Rural Health Unit. Dialysis clinics are not "
                 "screening sites, so they are not listed here.")
    if not layers:
        return
    area = pdk.Layer("ScatterplotLayer", [dict(longitude=float(person.longitude), latitude=float(person.latitude),
        title="Your area (approximate)", line1=str(person.municipality), line2="", line3="")], id="home_area",
        get_position="[longitude, latitude]", get_fill_color=[238, 154, 42, 230], get_radius=8,
        radius_units=pdk.types.String("pixels"), pickable=True)
    view = pdk.ViewState(latitude=float(person.latitude), longitude=float(person.longitude), zoom=11)
    style = _street_style(cfg)
    st.pydeck_chart(pdk.Deck(layers=[area, *layers], map_provider="maplibre" if style else None,
                             map_style=style or "__MAP_STYLE__", initial_view_state=view,
                             tooltip={"html": "<b>{title}</b><br/>{line1}<br/>{line2}<br/>{line3}"}),
                    key="citizen_map", height=380, width="stretch")
    st.caption("Amber: your area (approximate) · blue: your demo screening point · red: dialysis clinics "
               "(solid = mapped building, lighter = barangay centre, hollow = municipality centre).")
    if table is not None:
        listing = pd.DataFrame({
            "Clinic": table.name.map(display_text), "Address": table.street.map(display_text) + ", " + table.municipality_name,
            "Telephone": table.telephone.fillna("not listed"), "Straight-line distance": table.distance_km.map(lambda v: f"{v:.1f} km"),
            "Location on map": table.location_label})
        st.dataframe(listing, hide_index=True)
        st.caption(f"Source: PhilHealth, {REGISTER_TITLE}. Distances are straight-line from your approximate area, not travel time. "
                   "Accreditation does not guarantee an available slot. "
                   "Positions © OpenStreetMap contributors (ODbL).")
