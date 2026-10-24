"""Local clinic evidence collection; never changes the experiment's facilities."""
from datetime import date
import sqlite3

import pandas as pd
import streamlit as st

from agap.clinics import (CAPABILITIES, clinic_catalogue, read_verifications,
                          save_verification, verification_queue)


def render_clinic_verification(root, pilot_area):
    source = root / "data/processed/public" / pilot_area.lower() / "clinic_verification_queue.csv"
    if not source.exists():
        st.info("The clinic source register has not been prepared for this profile.")
        return
    database = root / "data/reports/clinic_verifications.sqlite3"
    try:
        catalogue = clinic_catalogue(source)
        history = read_verifications(database)
    except (ValueError, sqlite3.DatabaseError) as exc:
        st.error(f"Clinic verification data could not be loaded: {exc}")
        return
    queue = verification_queue(catalogue, history)
    st.caption("Source: PhilHealth YAKAP register dated 30 September 2026. Names and source pages are a verification queue, not proof of coordinates or lab capability. "
               "These records are separate from the hypothetical service points used by the screening plan.")
    if message := st.session_state.pop("clinic_saved_notice", None):
        st.success(message)
    left, middle, right = st.columns(3)
    left.metric("Clinic register entries", len(queue))
    middle.metric("Ready for pilot review", int(queue.status.eq("Ready for pilot review").sum()))
    right.metric("Still need verification", int(queue.status.ne("Ready for pilot review").sum()))
    st.download_button("Download clinic verification worksheet", queue.to_csv(index=False),
                       "laguna_clinic_verification.csv", "text/csv", key="clinic_worksheet")
    choices = dict(zip(catalogue.facility_id, catalogue.facility_name))
    selected = st.selectbox("Clinic to verify", list(choices), format_func=choices.get, key="clinic_to_verify")
    row = queue.set_index("facility_id").loc[selected]
    def text(value):
        return "" if pd.isna(value) else str(value)
    st.write(f"**{choices[selected]}** · register page {int(row.source_page)} · {row.status}")
    with st.form("clinic_verification_" + selected):
        left, right = st.columns(2)
        latitude = left.text_input("Verified latitude", value="" if pd.isna(row.latitude) else str(row.latitude))
        longitude = right.text_input("Verified longitude", value="" if pd.isna(row.longitude) else str(row.longitude))
        creatinine = left.selectbox("Creatinine availability", CAPABILITIES, index=CAPABILITIES.index(row.creatinine))
        uacr = right.selectbox("uACR availability", CAPABILITIES, index=CAPABILITIES.index(row.uacr))
        capacity = st.text_input("Complete screening panels per screening round", value="" if pd.isna(row.capacity_panels) else str(int(row.capacity_panels)),
                                help="One panel includes both tests. Leave blank until the clinic confirms capacity for the intended round.")
        evidence = st.text_input("Verification evidence / source", value=text(row.evidence_source), max_chars=1000,
                                 help="Use a public document URL or a traceable team verification reference.")
        checked = st.date_input("Date checked", value=date.fromisoformat(text(row.checked_on)) if text(row.checked_on) else None)
        notes = st.text_area("Verification notes", value=text(row.notes), max_chars=3000)
        submitted = st.form_submit_button("Save clinic verification", type="primary")
    if submitted:
        try:
            record, created = save_verification(database, catalogue, selected, dict(latitude=latitude, longitude=longitude,
                creatinine=creatinine, uacr=uacr, capacity_panels=capacity, checked_on=checked,
                evidence_source=evidence, notes=notes))
        except (ValueError, sqlite3.DatabaseError) as exc:
            st.error(str(exc))
        else:
            st.session_state["clinic_saved_notice"] = (f"Saved {record['record_id']}." if created else "These details are already recorded; no duplicate revision was added.")
            st.rerun()
    # The worksheet download keeps every column; the on-screen list shows what a verifier scans for.
    st.dataframe(queue.astype(object).where(queue.notna(), "—"), hide_index=True, width="stretch", height=320,
                 column_order=["facility_name", "status", "creatinine", "uacr", "capacity_panels", "checked_on", "remaining_checks"],
                 column_config={"facility_name": st.column_config.TextColumn("Clinic", width="large"),
                                "status": "Status", "creatinine": "Creatinine", "uacr": "uACR",
                                "capacity_panels": "Panels per round", "checked_on": "Checked on",
                                "remaining_checks": st.column_config.TextColumn("Still to check", width="large")})
    records = [dict(record_id=record["record_id"], recorded_at=record["available_at"], supersedes=record["supersedes"], **record["payload"])
               for record in history if record["facility_id"] == selected]
    if records:
        with st.expander("Clinic verification history"):
            st.dataframe(pd.DataFrame(records), hide_index=True)
