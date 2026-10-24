"""Read-only staff task browsing over recorded coordination cases.

These helpers deliberately use no model scores, allocation order or simulator
outcomes. Filtering and display order never change the approved round.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import re
from zoneinfo import ZoneInfo

import pandas as pd


QUEUES = (
    "Needs contact", "Awaiting screening", "Needs review / follow-up",
    "Tasks complete", "Declined / withdrawn",
)
OPEN_QUEUES = frozenset(QUEUES[:3])
TASK_FILTERS = ("All tasks", "Overdue", "Due today", "Unassigned")
OVERVIEW_COLUMNS = (
    "resident_id", "case", "municipality", "queue", "next_action", "owner", "due_on",
    "open_task", "overdue", "due_today",
)


def display_alias(resident_id, resident_ids=None):
    """Return a stable short case label without changing its stored identity.

    Deployment IDs have a unique numeric suffix in this prototype. Other short
    fixture IDs remain readable; arbitrary long identifiers use a digest. An
    optional cohort detects digest collisions and expands the distinguishing
    suffix without depending on the cohort's ordering.
    """
    resident_id = str(resident_id)
    if match := re.fullmatch(r"SYN-DEPLOYMENT-(\d+)", resident_id):
        return f"Resident {match[1]}"
    if len(resident_id) <= 12:
        return f"Case {resident_id}"
    digest = hashlib.sha256(resident_id.encode()).hexdigest()
    length = 8
    if resident_ids is not None:
        others = [hashlib.sha256(str(value).encode()).hexdigest() for value in resident_ids
                  if str(value) != resident_id and len(str(value)) > 12
                  and not re.fullmatch(r"SYN-DEPLOYMENT-(\d+)", str(value))]
        while any(other[:length] == digest[:length] for other in others) and length < len(digest):
            length += 4
    return f"Case {digest[:length]}"


def _text(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _due(value):
    if not _text(value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (ValueError, TypeError):
        return None


def overview_rows(frame, today=None):
    """Copy operational case fields and order open tasks by staff-entered date.

    Undated open tasks follow dated tasks; closed cases follow open work. Full
    resident IDs provide a stable tie break, never a risk score or frozen route.
    """
    today = today or datetime.now(ZoneInfo("Asia/Manila")).date()
    if isinstance(today, datetime):
        today = today.date()
    if not isinstance(today, date):
        today = pd.Timestamp(today).date()
    if frame.empty:
        return pd.DataFrame(columns=OVERVIEW_COLUMNS)
    ids = frame.resident_id.astype(str)
    if ids.duplicated().any():
        raise ValueError("Worklist browsing requires one case per resident.")
    rows = pd.DataFrame({"resident_id": ids})
    rows["case"] = [display_alias(value, ids) for value in ids]
    for name in ("municipality", "queue", "next_action", "owner", "due_on"):
        rows[name] = frame[name].map(_text) if name in frame else ""
    dates = rows.due_on.map(_due)
    rows["open_task"] = rows.queue.isin(OPEN_QUEUES)
    rows["overdue"] = [opened and due is not None and due < today
                       for opened, due in zip(rows.open_task, dates)]
    rows["due_today"] = [opened and due == today for opened, due in zip(rows.open_task, dates)]
    rows["_closed"] = ~rows.open_task
    rows["_date"] = [due.isoformat() if opened and due else "9999-12-31"
                     for opened, due in zip(rows.open_task, dates)]
    return rows.sort_values(["_closed", "_date", "resident_id"], kind="stable").loc[:, OVERVIEW_COLUMNS].reset_index(drop=True)


def filtered_overview(frame, queue="All cases", task_filter="All tasks", query="", today=None):
    """Apply staff filters to a copied overview; counts/allocations stay intact."""
    if queue not in ("All cases", *QUEUES):
        raise ValueError("Choose a supported work queue.")
    if task_filter not in TASK_FILTERS:
        raise ValueError("Choose a supported task filter.")
    rows = overview_rows(frame, today=today)
    if rows.empty:
        return rows
    if queue != "All cases":
        rows = rows.loc[rows.queue.eq(queue)]
    if task_filter == "Overdue":
        rows = rows.loc[rows.overdue]
    elif task_filter == "Due today":
        rows = rows.loc[rows.due_today]
    elif task_filter == "Unassigned":
        rows = rows.loc[rows.open_task & rows.owner.eq("")]
    terms = str(query).casefold().split()
    if terms and not rows.empty:
        text = rows[["resident_id", "case", "municipality", "next_action", "owner"]].agg(" ".join, axis=1).str.casefold()
        for term in terms:
            rows = rows.loc[text.loc[rows.index].str.contains(term, regex=False)]
    return rows.reset_index(drop=True)


def queue_counts(frame):
    """Count recorded case states, including retained historical invitations."""
    if frame.empty:
        return {queue: 0 for queue in QUEUES}
    return {queue: int(frame.queue.eq(queue).sum()) for queue in QUEUES}


def next_case_id(rows, selected_id, previous_ids=()):
    """Propose a next visible open case, only for an explicit staff action.

    Remembering the previous list lets a just-completed case advance from its
    former position instead of always returning to the first remaining case.
    """
    current = rows.loc[rows.open_task, "resident_id"].astype(str).tolist()
    if selected_id in current:
        position = current.index(selected_id)
        remaining = current[position + 1:] + current[:position]
        return remaining[0] if remaining else None
    previous_ids = list(previous_ids)
    if selected_id in previous_ids:
        position = previous_ids.index(selected_id)
        following = previous_ids[position + 1:] + previous_ids[:position]
        if candidate := next((value for value in following if value in current), None):
            return candidate
    return current[0] if current else None
