"""Staff-facing coordination for explicitly approved synthetic screening rounds.

The UI reads operational snapshots and recorded workflow events only. Simulation
outcomes never enter a case, a queue count, or an activity export.
"""
from __future__ import annotations

from datetime import date, datetime
from html import escape
import math
import os
from pathlib import Path
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from agap.demo import SELECTION_REASONS
from agap.workflow import COMMUNICATION_METHODS, REFERRAL_STATUSES, build_round_snapshot
from agap.workflow_presentation import action_receipt, case_progress, recovery_facts
from agap import workflow_store as store


QUEUES = (
    "Needs contact",
    "Awaiting screening",
    "Needs review / follow-up",
    "Tasks complete",
    "Declined / withdrawn",
)
DATA_STATUS = "Synthetic residents; fictional staff-entered results; hypothetical service points"
MANILA = ZoneInfo("Asia/Manila")


def workflow_path(root):
    """Keep local coordination records apart from immutable experiment outputs."""
    if override := os.environ.get("AGAP_WORKFLOW_DB"):
        return Path(override).expanduser()
    return Path(root) / "data" / "reports" / "screening_workflow.sqlite3"


def _today():
    return datetime.now(MANILA).date()


def _missing(value):
    return value is None or (not isinstance(value, (dict, list, tuple)) and bool(pd.isna(value)))


def _value(record, *names, default=None):
    for name in names:
        value = record.get(name)
        if not _missing(value):
            return value
    return default


def _label(value, default="Not recorded"):
    return default if _missing(value) or value == "" else str(value)


def _date(value, default=None):
    if _missing(value) or value == "":
        return default or _today()
    return pd.Timestamp(value).date()


def _local_time(value):
    if _missing(value) or value == "":
        return "Not recorded"
    stamp = pd.Timestamp(value)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp
    return stamp.tz_convert("Asia/Manila").strftime("%d %b %Y, %H:%M")


def _request_id(key):
    request_key = f"workflow_request_{key}"
    if request_key not in st.session_state:
        st.session_state[request_key] = str(uuid4())
    return st.session_state[request_key]


def _save(key, operation, success):
    """Acknowledge only persisted writes; preserve the token on failed retries."""
    request_id = _request_id(key)
    try:
        saved = operation(request_id)
    except (ValueError, sqlite3.Error, RuntimeError) as exc:
        st.error(f"Could not save this action: {exc} Reload the worklist if another session changed it.")
        return False
    st.session_state[f"workflow_request_{key}"] = str(uuid4())
    try:
        notice = success(saved) if callable(success) else success
    except (ValueError, sqlite3.Error, RuntimeError, KeyError, IndexError):
        # The write already committed. A receipt failure must never imply that
        # the action was lost or invite a duplicate submission.
        notice = "Action saved. Reload the worklist to inspect its current queue."
    st.session_state["workflow_notice"] = notice
    st.rerun()
    return True


def _events_frame(events, round_record):
    rows = []
    for event in events:
        row = dict(event)
        row["run_id"] = round_record["run_id"]
        row["data_status"] = DATA_STATUS
        row["occurred_at_manila"] = _local_time(row.get("occurred_at"))
        row["recorded_at_manila"] = _local_time(row.get("recorded_at"))
        rows.append(row)
    return pd.DataFrame(rows)


def _worklist_export(frame, round_record):
    export = frame.copy()
    export["round_id"] = round_record["round_id"]
    export["run_id"] = round_record["run_id"]
    export["data_status"] = DATA_STATUS
    return export


def _exports(path, round_record, frame, suffix=""):
    round_id = round_record["round_id"]
    st.download_button("Download approved round worklist", _worklist_export(frame, round_record).to_csv(index=False),
                       f"{round_id}_worklist.csv", "text/csv", key=f"workflow_export_cases_{round_id}{suffix}")
    events = _events_frame(store.get_events(path, round_id), round_record)
    st.download_button("Download activity history", events.to_csv(index=False),
                       f"{round_id}_activity.csv", "text/csv", key=f"workflow_export_events_{round_id}{suffix}")


def _saved_rounds(path, run_id):
    rounds = store.list_rounds(path)
    if not rounds:
        return
    with st.expander("Saved round history"):
        st.caption("Read-only saved rounds, including earlier experiment runs. Viewing a past run does not attach its invitations to this draft.")
        by_id = {record["round_id"]: record for record in rounds}
        selected = st.selectbox("Saved round", list(by_id),
            format_func=lambda value: f"{value} · {by_id[value]['status']} · "
                + ("current run" if by_id[value]["run_id"] == run_id else f"past run {by_id[value]['run_id']}"),
            key=f"workflow_saved_round_{run_id}")
        record = store.load_round(path, selected)
        st.caption(f"Created {_local_time(record.get('created_at'))} · {record['status']} · run {record['run_id']}")
        frame = store.worklist(path, selected)
        st.dataframe(_worklist_export(frame, record), hide_index=True, width="stretch")
        _exports(path, record, frame, suffix="_history")


def render_round_approval(root, run_id, scored, facilities, result, cfg, variant, settings,
                          manifest=None, applied_reports=None):
    """Approve the current plan once; never build a snapshot on ordinary reruns."""
    path = workflow_path(root)
    st.subheader("Approve a demo screening round")
    st.caption("A round saves the actual invitation list and replacement order. Draft model, budget and questionnaire "
               "changes leave its approved assignments unchanged.")
    try:
        current = store.active_round(path, run_id=run_id)
    except (ValueError, sqlite3.Error, RuntimeError) as exc:
        st.error(f"Could not load saved screening rounds: {exc}")
        return None
    if current:
        st.success(f"Approved round {current['round_id']} is active. Open Worklist to record the next staff action.")
        st.caption(f"Saved run {current['run_id']} · version {current['version']}. "
                   "The current draft may differ from this approved round.")
    elif result is None:
        st.info("Prepare a screening plan before creating an approved round.")
    else:
        records = result["proposed"]
        invited = records.loc[records.invited.astype(bool)]
        st.write(f"**{len(invited):,} assigned invitations** · **{int(settings['budget']):,} panel budget** · "
                 f"{settings['strategy']}")
        st.caption(f"Model: {'Questionnaire only' if variant == 'clinical' else 'Questionnaire + public climate'} · "
                   f"{len(scored):,} synthetic adults · hypothetical service points. "
                   "All contact, specimen, result and review counts start from recorded staff actions.")
        if not invited.empty:
            st.dataframe(invited.groupby("facility_id").size().rename("Invitations").reset_index(),
                         hide_index=True, width=420, column_config={"facility_id": "Service point (hypothetical)"})
        # Approval freezes invitations for staff work, so it takes an explicit confirmation (as archiving does).
        confirmed = st.checkbox("I have reviewed these assignments; freeze them as the staff worklist",
                                key=f"workflow_create_confirm_{run_id}", disabled=invited.empty)
        if st.button("Create demo screening round", type="primary", disabled=invited.empty or not confirmed,
                     key=f"workflow_create_{run_id}"):
            def create(request_id):
                snapshot = build_round_snapshot(scored, facilities, records, cfg, run_id, variant,
                                                settings, manifest=manifest, applied_reports=applied_reports)
                store.create_round(path, snapshot, actor="Demo coordinator", request_id=request_id)
                st.session_state["workflow_open_worklist"] = True
            _save(f"create_{run_id}", create, "Demo round saved. Invitations are fixed.")
    try:
        _saved_rounds(path, run_id)
    except (ValueError, sqlite3.Error, RuntimeError) as exc:
        st.error(f"Could not load round history: {exc}")
    return current


def _case_selector(frame, round_id, selected_resident, chooser=None):
    """Browse controls render here; the case chooser renders in ``chooser`` (beside the case) when given."""
    from hashlib import sha256
    from html import escape
    from agap.workflow_overview import (
        TASK_FILTERS, display_alias, filtered_overview, next_case_id, queue_counts,
    )

    queue_key = f"workflow_queue_{round_id}"
    resident_key = f"workflow_resident_{round_id}"
    external_key = f"workflow_external_resident_{round_id}"
    task_key = f"workflow_task_filter_{round_id}"
    search_key = f"workflow_search_{round_id}"
    page_key = f"workflow_case_page_{round_id}"
    previous_key = f"workflow_previous_cases_{round_id}"
    ids = frame.resident_id.astype(str).tolist()
    if selected_resident in ids and st.session_state.get(external_key) != selected_resident:
        st.session_state[resident_key] = selected_resident
        st.session_state[previous_key] = []
    if st.session_state.get(resident_key) not in ids and ids:
        st.session_state[resident_key] = ids[0]

    counts = queue_counts(frame)
    st.markdown('<div class="agap-queue-counts" aria-label="Recorded case counts">' + ''.join(
        f'<div class="agap-queue-count"><strong>{count:,}</strong><span>{escape(queue)}</span></div>'
        for queue, count in counts.items()) + '</div>', unsafe_allow_html=True)
    # Search and the bounded list stay available without displacing the case's
    # primary action on every visit. Their state survives ordinary save reruns.
    with st.expander("Browse worklist", expanded=True):
        queue_column, task_column = st.columns(2)
        queue = queue_column.selectbox("Work queue", ["All cases", *QUEUES], key=queue_key)
        task_filter = task_column.selectbox("Task filter", TASK_FILTERS, key=task_key)
        query = st.text_input("Search worklist", key=search_key,
            placeholder="Case, full ID, municipality, owner or next action")
        rows = filtered_overview(frame, queue=queue, task_filter=task_filter, query=query, today=_today())
        signature = (queue, task_filter, query)
        signature_key = f"workflow_browse_filters_{round_id}"
        if st.session_state.get(signature_key) != signature:
            st.session_state[page_key] = 0
            st.session_state[previous_key] = []
            st.session_state[signature_key] = signature
        page_size = 10
        pages = max(1, math.ceil(len(rows) / page_size))
        page = min(max(int(st.session_state.get(page_key, 0)), 0), pages - 1)
        st.session_state[page_key] = page
        start = page * page_size
        page_rows = rows.iloc[start:start + page_size]
        page_ids = page_rows.resident_id.astype(str).tolist()
        if not rows.empty:
            st.caption(f"{len(rows):,} matching cases · staff due date first · no model-score sorting")
            table_key = f"workflow_case_table_{round_id}_{page}_" + sha256(repr(page_ids).encode()).hexdigest()[:10]

            def open_row():
                selection = st.session_state.get(table_key, {}).get("selection", {}).get("rows", [])
                if selection and 0 <= selection[0] < len(page_ids):
                    st.session_state[resident_key] = page_ids[selection[0]]

            table = page_rows[["case", "municipality", "next_action", "owner", "due_on", "queue"]].rename(columns={
                "case": "Case", "municipality": "Municipality", "next_action": "Next action",
                "owner": "Owner", "due_on": "Due", "queue": "Queue"})
            table["Owner"] = table.Owner.replace("", "Unassigned")
            table["Due"] = table.Due.replace("", "Not set")
            with st.container(key="worklist_case_overview"):
                st.dataframe(table, hide_index=True, width="stretch", height=min(388, 38 + len(table) * 35),
                    selection_mode="single-row", on_select=open_row, key=table_key)
            if pages > 1:
                previous, position, following = st.columns([1, 1, 1])
                previous.button("Previous cases", key=f"workflow_previous_page_{round_id}", disabled=page == 0,
                    on_click=lambda: st.session_state.update({page_key: max(0, page - 1)}))
                position.caption(f"Page {page + 1} of {pages}")
                following.button("Next cases", key=f"workflow_next_page_{round_id}", disabled=page + 1 >= pages,
                    on_click=lambda: st.session_state.update({page_key: page + 1}))
        else:
            st.info("No cases match these worklist filters. Your selected case stays open.")
        st.caption("Browsing changes this view only. Approved assignments, replacement order and saved activities stay unchanged.")

    if queue != "All cases" or task_filter != "All tasks" or query.strip():
        active_search = f" · search: {query.strip()}" if query.strip() else ""
        st.caption(f"Showing {len(rows):,} matching cases · {queue} · {task_filter}{active_search}")
    with chooser if chooser is not None else st.container():
        return _choose_case(frame, rows, ids, round_id, selected_resident, page_size)


def _choose_case(frame, rows, ids, round_id, selected_resident, page_size):
    from agap.workflow_overview import display_alias, next_case_id

    resident_key = f"workflow_resident_{round_id}"
    external_key = f"workflow_external_resident_{round_id}"
    page_key = f"workflow_case_page_{round_id}"
    previous_key = f"workflow_previous_cases_{round_id}"
    selected = st.session_state.get(resident_key)
    visible = rows.resident_id.astype(str).tolist()
    options = list(visible)
    if selected in ids and selected not in options:
        options.insert(0, selected)
    if not options:
        st.session_state[external_key] = selected_resident
        return None
    labels = frame.set_index("resident_id")
    selected = st.selectbox("Round resident", options, key=resident_key,
        format_func=lambda resident_id: f"{display_alias(resident_id, ids)} · {labels.loc[resident_id, 'municipality']} · {resident_id}")
    if selected not in visible:
        current_queue = str(labels.loc[selected, "queue"])
        st.info(f"{display_alias(selected, ids)} remains open · {current_queue}. This case is outside your current filters. "
                "Use Open next case when you are ready to move on.")
    previous_ids = st.session_state.get(previous_key, [])
    candidate = next_case_id(rows, selected, previous_ids=previous_ids)

    def open_next():
        st.session_state[resident_key] = candidate
        if candidate in visible:
            st.session_state[page_key] = visible.index(candidate) // page_size

    st.button("Open next case", key=f"workflow_open_next_{round_id}", disabled=candidate is None,
              on_click=open_next)
    current_ids = rows.loc[rows.open_task, "resident_id"].astype(str).tolist()
    # Keep the old anchor until the completed/declined case is deliberately left.
    # This preserves a meaningful next case even when its saved action removes it
    # from the current queue/date/search filters.
    if selected in current_ids or selected not in previous_ids:
        st.session_state[previous_key] = current_ids
    st.session_state[external_key] = selected
    return selected


def _record(path, record, person, event_type, payload, actor, key, message):
    def receipt(event):
        frame = store.worklist(path, record["round_id"])
        current = frame.loc[frame.resident_id.eq(person["resident_id"])].iloc[0].to_dict()
        return action_receipt(event, current)

    return _save(key, lambda request_id: store.record_event(
        path, record["round_id"], str(person["resident_id"]), event_type, payload,
        actor=actor, request_id=request_id, expected_version=record["version"]), receipt)


def _contact_form(path, record, person, actor, prefix):
    with st.expander("Record contact", expanded=_value(person, "queue") == "Needs contact"):
        with st.form(f"{prefix}_contact"):
            attempts = int(record["snapshot"]["settings"].get("unreachable_after_attempts", 3))
            unanswered = int(_value(person, "no_answer_count", default=0) or 0)
            outcomes = ["No answer", "Retry requested", "Accepted", "Declined"] + (["Unreachable"] if unanswered >= attempts else [])
            outcome = st.selectbox("Contact outcome", outcomes, key=f"{prefix}_contact_outcome",
                                   help=f"Unreachable becomes available after {attempts} unanswered attempts "
                                        f"({unanswered} recorded so far) and releases the slot for a replacement.")
            with st.expander("Optional contact note & retry date"):
                note = st.text_area("Contact note (optional)", key=f"{prefix}_contact_note")
                retry = st.date_input("Retry or next-action date", value=_today(), key=f"{prefix}_contact_due")
                if bool(_value(person, "followup_open", default=False)):
                    st.caption("This contact is recorded in history. The open follow-up keeps its next action and date "
                               "until staff explicitly edit or complete that task.")
            submitted = st.form_submit_button("Save contact outcome")
        if submitted:
            payload = dict(outcome=outcome, note=note)
            if outcome in ("No answer", "Retry requested"):
                payload.update(due_on=retry.isoformat(), next_action="Retry contact")
            elif outcome in ("Declined", "Unreachable") or _value(person, "next_action") == "Retry contact":
                payload.update(due_on="", next_action="")
            _record(path, record, person, "contact", payload, actor, f"{prefix}_contact",
                    "Contact outcome saved. The queue reflects the recorded action.")
        st.caption("No answer or an overdue date keeps the case open. A decline before testing, or confirming the resident is "
                   "unreachable after repeated unanswered attempts, releases the slot.")


def _specimen_and_results(path, record, person, actor, prefix):
    started = _value(person, "slot_state", "slot_status") == "started"
    with st.expander("Screening visit & results", expanded=_value(person, "queue") == "Awaiting screening"):
        st.caption("Use fictional demonstration values. Creatinine: mg/dL. uACR: mg/g. "
                   "One screening episode per resident in this round; revisions preserve the earlier values.")
        if not started:
            with st.form(f"{prefix}_specimen"):
                specimen = st.date_input("Specimen collection date", value=_today(), key=f"{prefix}_specimen_date")
                submitted = st.form_submit_button("Record specimen collection")
            if submitted:
                _record(path, record, person, "specimen", dict(specimen_date=specimen.isoformat()), actor,
                        f"{prefix}_specimen", "Specimen collection saved. This slot has started and cannot be released.")
            st.info("Record specimen collection before entering screening results.")
            return
        st.caption(f"Specimen collected: {_label(_value(person, 'specimen_date'))}. This panel's slot is consumed.")
        with st.form(f"{prefix}_result"):
            creatinine_value = _value(person, "creatinine")
            uacr_value = _value(person, "uacr")
            creatinine = st.text_input("Creatinine (mg/dL; blank = unavailable)",
                value="" if creatinine_value is None else str(creatinine_value), key=f"{prefix}_creatinine")
            uacr = st.text_input("uACR (mg/g; blank = unavailable)",
                value="" if uacr_value is None else str(uacr_value), key=f"{prefix}_uacr")
            specimen = st.date_input("Result specimen date", value=_date(_value(person, "specimen_date")),
                                     key=f"{prefix}_result_date", disabled=True)
            reference = st.text_input("Result reference (optional)",
                                     value=_label(_value(person, "result_reference"), default=""),
                                     key=f"{prefix}_result_reference")
            submitted = st.form_submit_button("Save panel results")
        if submitted:
            try:
                creatinine = float(creatinine) if creatinine.strip() else None
                uacr = float(uacr) if uacr.strip() else None
                if creatinine is not None and (not math.isfinite(creatinine) or creatinine <= 0):
                    raise ValueError("Creatinine must be finite and greater than zero.")
                if uacr is not None and (not math.isfinite(uacr) or uacr < 0):
                    raise ValueError("uACR must be finite and nonnegative.")
                payload = dict(creatinine=creatinine,
                               creatinine_unit="mg/dL", uacr=uacr,
                               uacr_unit="mg/g", specimen_date=specimen.isoformat(), result_reference=reference)
            except ValueError as exc:
                if "finite" in str(exc):
                    st.error(str(exc))
                else:
                    st.error("Enter a numeric creatinine and uACR value, or leave the unavailable component blank.")
            else:
                _record(path, record, person, "result", payload, actor, f"{prefix}_result",
                        "Panel results saved. Screening completeness and review tasks were updated.")
        st.caption("An abnormal screening result requires review; a single result does not diagnose CKD. "
                   "A normal available component with a missing test remains an incomplete panel.")


def _review_form(path, record, person, actor, prefix):
    review_open = bool(_value(person, "review_pending", "review_open", default=False))
    followup_open = bool(_value(person, "followup_open", default=False))
    started = bool(_value(person, "started", default=False))
    if not review_open and not followup_open and not started:
        return
    with st.expander("Review & follow-up", expanded=review_open or followup_open):
        if review_open or (started and not followup_open):
            with st.form(f"{prefix}_review"):
                disposition = st.selectbox("Review disposition", ["Complete", "Follow-up requested"],
                                           key=f"{prefix}_review_disposition")
                note = st.text_area("Review note", key=f"{prefix}_review_note")
                next_action = st.text_input("Follow-up action (required when requested)", key=f"{prefix}_review_action")
                due = st.date_input("Follow-up due date", value=_today(), key=f"{prefix}_review_due")
                submitted = st.form_submit_button("Save review disposition")
            if submitted:
                payload = dict(disposition=disposition, note=note)
                if disposition == "Follow-up requested":
                    payload.update(next_action=next_action, due_on=due.isoformat())
                _record(path, record, person, "review", payload, actor, f"{prefix}_review",
                        "Review disposition saved.")
        if followup_open:
            with st.form(f"{prefix}_followup"):
                note = st.text_area("Follow-up completion note (optional)", key=f"{prefix}_followup_note")
                submitted = st.form_submit_button("Complete follow-up task")
            if submitted:
                _record(path, record, person, "followup_complete", dict(note=note), actor,
                        f"{prefix}_followup", "Follow-up completion saved.")
        st.caption("Follow-up dates and actions are staff-entered demonstration tasks, not automatic clinical prescriptions.")
    _results_and_referral(path, record, person, actor, prefix)


def _results_and_referral(path, record, person, actor, prefix):
    """Close the bridge after screening: explain reviewed results, then track any referral to its outcome."""
    if not bool(_value(person, "started", default=False)):
        return
    communicated = bool(_value(person, "results_communicated", default=False))
    needed = bool(_value(person, "communication_needed", default=False))
    status = _label(_value(person, "referral_status"), default="")
    with st.expander("Results explained & referral", expanded=needed or bool(_value(person, "referral_open", default=False))):
        st.caption(("Results explained to the resident. " if communicated else "Results not yet explained to the resident. ")
                   + (f"Referral: {status} — {_label(_value(person, 'referral_destination'), default='')}." if status
                      else "No referral recorded."))
        with st.form(f"{prefix}_communication"):
            method = st.selectbox("How the reviewed results were explained", COMMUNICATION_METHODS, key=f"{prefix}_comm_method")
            by = st.text_input("Explained by (demo staff)", value="Demo nurse", key=f"{prefix}_comm_by")
            note = st.text_area("Questions or concerns the resident raised (optional)", key=f"{prefix}_comm_note")
            submitted = st.form_submit_button("Record results explained")
        if submitted:
            _record(path, record, person, "communication", dict(method=method, explained_by=by, note=note), actor,
                    f"{prefix}_communication", "Recorded that the results were explained.")
        with st.form(f"{prefix}_referral"):
            options = ["Sent"] if not status else list(REFERRAL_STATUSES)
            new_status = st.selectbox("Referral status", options, key=f"{prefix}_ref_status")
            destination = st.text_input("Referred to (clinic, hospital or specialist)",
                                        value=_label(_value(person, "referral_destination"), default=""), key=f"{prefix}_ref_dest")
            note = st.text_area("Referral note (optional)", key=f"{prefix}_ref_note")
            submitted = st.form_submit_button("Save referral status")
        if submitted:
            _record(path, record, person, "referral", dict(status=new_status, destination=destination, note=note), actor,
                    f"{prefix}_referral", "Referral status saved.")
        st.caption("Staff record what happened; the prototype does not book appointments or contact hospitals. "
                   "'Did not attend' keeps the referral open; 'Outcome unknown' closes it while saying so.")


def _assignment_form(path, record, person, actor, prefix):
    complete = _value(person, "queue") == "Tasks complete"
    with st.expander("Owner & next action"):
        st.caption("These fields edit the current queue instruction; they do not create a separate task.")
        if complete:
            st.caption("Recorded tasks are complete. Update the owner here; use Review & follow-up to request a new dated task.")
        with st.form(f"{prefix}_assignment"):
            owner = st.text_input("Responsible demo staff member", value=_label(_value(person, "owner"), default="Demo staff"),
                                  key=f"{prefix}_owner")
            action = st.text_input("Next action", value="" if complete else _label(_value(person, "next_action"), default=""),
                                   key=f"{prefix}_action", disabled=complete)
            due = st.date_input("Action due date", value=None if complete else _date(_value(person, "due_on")),
                                key=f"{prefix}_due", disabled=complete)
            submitted = st.form_submit_button("Save owner" if complete else "Save owner & next action")
        if submitted:
            payload = dict(owner=owner)
            if not complete:
                payload.update(next_action=action, due_on=due.isoformat())
            _record(path, record, person, "assignment", payload,
                    actor, f"{prefix}_assignment", "Owner saved." if complete else "Owner and next action saved.")


def _replacement(path, record, person, actor, prefix, frame, slots):
    if not bool(_value(person, "slot_available_for_replacement", default=(
            _value(person, "slot_state", "slot_status") == "released"))):
        return
    with st.expander("Recover this released slot", expanded=True):
        st.caption("Use the approved round's frozen order and access limit, at the same service point and municipality. "
                   "Other residents' assignments remain fixed.")
        proposal = store.propose_replacement(path, record["round_id"], person["slot_id"])
        if proposal is None:
            st.info("No eligible replacement remains within this slot's saved constraints. The slot stays open.")
            return
        if hasattr(proposal, "to_dict"):
            proposal = proposal.to_dict()
        elif not isinstance(proposal, dict):
            proposal = vars(proposal)
        from agap.workflow_overview import display_alias

        cohort_ids = [row["resident_id"] for row in record["snapshot"]["residents"]]
        facts = recovery_facts(record["snapshot"], person, proposal, slots, frame)
        st.html('<div class="agap-recovery-comparison">'
                '<div><span>Declined invitation</span>'
                f'<strong>{escape(display_alias(person["resident_id"], cohort_ids))}</strong>'
                f'<p>{escape(_label(person.get("municipality")))} · {escape(_label(person.get("facility_id")))}</p>'
                '<small>Unused slot released · history retained</small></div>'
                '<div><span>Proposed replacement</span>'
                f'<strong>{escape(display_alias(proposal["resident_id"], cohort_ids))}</strong>'
                f'<p>{escape(proposal["municipality"])} · {escape(proposal["facility_id"])}</p>'
                f'<small>{facts["distance_km"]:.1f} km to the same service point</small></div></div>')
        order_label = {"priority": "priority score / saved tie order", "random": "saved random outreach order",
                       "unreported": "priority order among residents without a questionnaire",
                       "policy": "saved policy order"}.get(facts["ordering_basis"], facts["ordering_basis"])
        st.write(f"**Next eligible in {order_label}** · position {facts['order_position']:,} in the frozen cohort order")
        st.html('<ul class="agap-recovery-checks">' + ''.join(
            f'<li><strong>{"Pass" if passed else "Check failed"}</strong> {escape(label)}</li>'
            for label, passed in facts["checks"]) + '</ul>')
        st.caption(f"Reserved or started slots — round: {facts['round_occupied']:,}/{facts['budget']:,} → "
                   f"{facts['round_occupied'] + 1:,}/{facts['budget']:,}; "
                   f"service point: {facts['facility_occupied']:,}/{facts['facility_capacity']:,} → "
                   f"{facts['facility_occupied'] + 1:,}/{facts['facility_capacity']:,} after assignment.")
        with st.expander("Replacement identifiers"):
            st.code(f"Declined resident: {person['resident_id']}\nReplacement: {proposal['resident_id']}\nSlot: {person['slot_id']}")
        if st.button("Assign replacement", key=f"{prefix}_replace", type="primary", disabled=not facts["eligible"]):
            _save(f"{prefix}_replace", lambda request_id: store.confirm_replacement(
                path, record["round_id"], person["slot_id"], proposal["resident_id"], actor=actor,
                request_id=request_id, expected_version=record["version"]),
                f"Replacement {display_alias(proposal['resident_id'], cohort_ids)} assigned · needs contact. "
                f"Round slots occupied: {facts['round_occupied'] + 1:,}/{facts['budget']:,}. "
                "The original decline remains in history.")


def _case_summary(person, cohort_ids):
    from agap.workflow_overview import display_alias

    st.subheader(f"{display_alias(person['resident_id'], cohort_ids)} · {_label(person.get('municipality'))}")
    st.write(f"**Next action:** {_label(person.get('next_action'))}")
    owner, due = _value(person, "owner"), _value(person, "due_on")
    st.caption(f"Owner: {_label(owner, default='Unassigned')} · Due: {_label(due, default='Not set')}")
    due = _value(person, "due_on")
    if due and _date(due) < _today() and _value(person, "queue") not in ("Tasks complete", "Declined / withdrawn"):
        st.warning("This recorded staff task is overdue. Its date does not release the screening slot.")
    reason = _value(person, "selection_reason", "reason")
    reason = SELECTION_REASONS.get(reason, reason)
    st.caption(f"{_label(reason)} · Service point {_label(person.get('facility_id'))}")
    st.html('<ol class="agap-case-progress" aria-label="Recorded case progress">' + ''.join(
        f'<li class="is-{stage["state"]}"><span>{escape(stage["stage"])}</span>'
        f'<strong>{escape(stage["detail"])}</strong></li>' for stage in case_progress(person)) + '</ol>')


def _case_details(person):
    st.write(f"**Full resident ID:** {person['resident_id']}")
    reason = _value(person, "selection_reason", "reason")
    reason = SELECTION_REASONS.get(reason, reason)
    panel = "Complete" if bool(_value(person, "panel_complete", default=False)) else "Incomplete"
    invitation = _value(person, "invitation_status")
    if invitation is None:
        invitation = "Active invitation" if bool(_value(person, "is_current", default=False)) else "Historical invitation"
        if _value(person, "contact_outcome") in ("Declined", "Withdrawn"):
            invitation = "Declined / withdrawn"
    st.write(f"**Invitation:** {invitation} · {_label(reason)}")
    st.caption(f"Service point: {_label(person.get('facility_id'))} · Questionnaire: "
               f"{_label(_value(person, 'questionnaire_status', 'report_status'))} · "
               f"Contact: {_label(person.get('contact_outcome'))}")
    flag = _value(person, "screening_flag")
    screening = "Review flag" if flag is True or flag == 1 else "No flag in recorded panel" if flag is False or flag == 0 else "Not determined"
    st.write(f"**Panel:** {panel} · **Screening result:** {screening}")
    egfr = _value(person, "egfr")
    st.caption(f"eGFR: {'unavailable' if egfr is None else f'{float(egfr):.1f} mL/min/1.73 m²'} · "
               f"Review task: {'Open' if bool(_value(person, 'review_open', default=False)) else 'None open'}")


def _round_details(record, frame, slots):
    with st.expander("Round details"):
        st.caption(f"Round {record['round_id']} · run {record['run_id']} · {record['status']} · version {record['version']}. "
                   "Counts come from saved staff actions. Draft changes do not rewrite these invitations.")
        settings = record["snapshot"]["settings"]
        model_label = "Questionnaire only" if record["snapshot"].get("model") == "clinical" else "Questionnaire + public climate"
        st.caption(f"Approved model: {model_label} · {int(settings['budget']):,} panels · "
                   f"{settings.get('strategy', 'Saved policy')} · outreach {float(settings.get('outreach', 0)):.0%}.")
        facilities = record["snapshot"]["facilities"]
        capacity = sum(int(facility["capacity"]) for facility in facilities)
        st.caption(f"Frozen access limit: {float(settings['max_distance_km']):g} km straight-line · "
                   f"{len(facilities):,} hypothetical service points · total saved capacity {capacity:,} panels. "
                   "Replacement uses the declined slot's saved route, municipality and service point.")
        st.caption(DATA_STATUS + ". Demo actor names do not provide authenticated access.")
        st.caption(" · ".join(f"{queue}: {int(frame.queue.eq(queue).sum()):,}" for queue in QUEUES))
        slot_frame = pd.DataFrame(slots)
        if not slot_frame.empty:
            state_column = "status" if "status" in slot_frame else "state"
            status = slot_frame[state_column]
            reassigned = (slot_frame.replacement_count.fillna(0).gt(0) if "replacement_count" in slot_frame else
                          slot_frame.current_resident_id.notna() & slot_frame.current_resident_id.ne(slot_frame.original_resident_id))
            st.caption(f"Slots — reserved: {int(status.eq('reserved').sum()):,} · started: {int(status.eq('started').sum()):,} · "
                       f"released: {int(status.eq('released').sum()):,} · reassigned: {int(reassigned.sum()):,}")


def _coverage_shortfalls(record, slots):
    slot_frame = pd.DataFrame(slots)
    if slot_frame.empty:
        return
    settings = record["snapshot"]["settings"]
    coverage = settings.get("coverage") or {}
    overrides = coverage.get("minimum_invitations") or {}
    municipalities = {resident["municipality"] for resident in record["snapshot"]["residents"]}
    occupied = slot_frame.loc[slot_frame.status.isin(["reserved", "started"])].groupby("municipality").size()
    shortages = []
    for municipality in sorted(municipalities):
        required = int(overrides.get(municipality, coverage.get("minimum_invitations_per_municipality", 0)))
        assigned = int(occupied.get(municipality, 0))
        if assigned < required:
            shortages.append(f"{municipality}: {assigned}/{required} occupied slots")
    if shortages:
        st.warning("Open geographic coverage shortfalls: " + "; ".join(shortages)
                   + ". Saved coverage requirements remain in effect; recover eligible released slots explicitly.")


def _open_context(destination):
    st.session_state.update(workspace_tab=destination, resident_origin="Worklist")


def render_worklist(root, round_record, selected_resident=None):
    """Render the saved worklist and return selection without editing root widgets."""
    if round_record is None:
        st.info("Prepare and approve a demo screening round to open the staff worklist.")
        return None
    path = workflow_path(root)
    round_id = round_record["round_id"]
    try:
        record = store.load_round(path, round_id)
        frame = store.worklist(path, round_id)
        slots = store.get_slots(path, round_id)
    except (ValueError, sqlite3.Error, RuntimeError) as exc:
        st.error(f"Could not load the saved worklist: {exc}")
        return None
    notice = st.session_state.pop("workflow_notice", None)
    if notice:
        st.success(notice)
    rendered_version_key = f"workflow_rendered_version_{round_id}"
    previous_version = st.session_state.get(rendered_version_key)
    if previous_version is not None and previous_version != record["version"] and not notice:
        st.warning("This saved round changed since the worklist was displayed. The cases have been reloaded; "
                   "review the current case and submit the action again. Earlier unsaved worklist form values were not applied.")
    st.session_state[rendered_version_key] = record["version"]
    st.subheader("Approved round worklist")
    approved_settings = record["snapshot"]["settings"]
    st.caption(f"Synthetic demo · Approved budget: {int(approved_settings['budget']):,} panels")
    _coverage_shortfalls(record, slots)
    if frame.empty:
        st.info("No invitations were saved in this round.")
        return None
    # List and detail: the case list and round-level tools on the left, the chosen case on the right.
    # On a phone the columns stack and the case pane comes first, so its primary action stays near the top.
    list_pane, case_pane = st.columns([1, 1], gap="large")
    with case_pane:
        case_area = st.container(key="worklist_case_pane")
        chooser = case_area.container()
    with list_pane:
        selected = _case_selector(frame, round_id, selected_resident, chooser)
        _round_details(record, frame, slots)
        with st.expander("Approved round downloads"):
            _exports(path, record, frame)
        if record["status"] == "active":
            with st.expander("Archive demo round"):
                st.caption("Archiving ends new activity in this round and preserves every case, event and unfinished-task count.")
                confirmed = st.checkbox("Archive this demo round and keep its history", key=f"workflow_archive_confirm_{round_id}")
                if st.button("Archive demo round", disabled=not confirmed, key=f"workflow_archive_{round_id}"):
                    _save(f"archive_{round_id}", lambda request_id: store.archive_round(
                        path, round_id, actor=st.session_state.get(f"workflow_actor_{round_id}", "Demo staff"),
                        request_id=request_id, expected_version=record["version"]), "Demo round archived. Its activity history is retained.")
    with case_area:
        if selected is not None:
            person = frame.loc[frame.resident_id.eq(selected)].iloc[0].to_dict()
            _case_summary(person, [row["resident_id"] for row in record["snapshot"]["residents"]])
            prefix = f"workflow_{round_id}_{selected}_v{record['version']}"
            actions = st.container()
            # Evaluate the actor before handling any submitted action, while placing
            # editable staff/context controls after the primary task in the page.
            with st.expander("Recording staff & context"):
                actor = st.text_input("Recording demo staff member", value="Demo staff", key=f"workflow_actor_{round_id}")
                st.caption("This is a demonstration actor label, not authenticated access.")
                st.button("Review / correct questionnaire", key=f"workflow_report_{round_id}_{selected}",
                          on_click=_open_context, args=("Resident report",))
                st.button("View resident weather", key=f"workflow_climate_{round_id}_{selected}",
                          on_click=_open_context, args=("Resident weather",))
            with actions:
                if record["status"] == "active":
                    is_current = bool(_value(person, "is_current", default=True))
                    released = _value(person, "slot_state", "slot_status") == "released"
                    try:
                        if is_current and not released and _value(person, "queue") != "Declined / withdrawn":
                            queue = _value(person, "queue")
                            if queue == "Needs review / follow-up":
                                _review_form(path, record, person, actor, prefix)
                                _specimen_and_results(path, record, person, actor, prefix)
                                _contact_form(path, record, person, actor, prefix)
                            elif queue == "Awaiting screening":
                                _specimen_and_results(path, record, person, actor, prefix)
                                _contact_form(path, record, person, actor, prefix)
                                _review_form(path, record, person, actor, prefix)
                            elif queue == "Tasks complete":
                                _specimen_and_results(path, record, person, actor, prefix)
                                _review_form(path, record, person, actor, prefix)
                            else:
                                _contact_form(path, record, person, actor, prefix)
                                _specimen_and_results(path, record, person, actor, prefix)
                                _review_form(path, record, person, actor, prefix)
                            _assignment_form(path, record, person, actor, prefix)
                        elif released:
                            _replacement(path, record, person, actor, prefix, frame, slots)
                        else:
                            st.info("This resident's original invitation is retained as history. A replacement has its own active case.")
                            replacements = [event for event in store.get_events(path, round_id)
                                if event["event_type"] == "replacement"
                                and event.get("payload", {}).get("previous_resident_id") == selected]
                            if replacements:
                                replacement_id = replacements[-1]["resident_id"]
                                st.button("Open replacement case", key=f"{prefix}_open_replacement",
                                    on_click=lambda: st.session_state.update({
                                        f"workflow_resident_{round_id}": replacement_id}))
                    except (ValueError, sqlite3.Error, RuntimeError) as exc:
                        st.error(f"Could not prepare this action: {exc}")
                else:
                    st.info("This round is archived. Its saved cases and activity history remain available for review and export.")
            with st.expander("Case details"):
                _case_details(person)
            with st.expander("Dated activity history"):
                events = store.get_events(path, round_id)
                own = [event for event in events if event.get("resident_id") == selected or (
                    event.get("event_type") == "replacement" and
                    event.get("payload", {}).get("previous_resident_id") == selected)]
                if own:
                    history = _events_frame(own, record)
                    columns = [name for name in ("sequence", "occurred_at_manila", "recorded_at_manila", "event_type", "actor", "payload") if name in history]
                    st.dataframe(history[columns], hide_index=True, width="stretch")
                    st.caption("Times are shown in Asia/Manila. The saved event timestamps use UTC.")
                else:
                    st.info("No staff activities have been recorded for this resident yet.")
    return selected
