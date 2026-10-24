"""Aggregate LGU / analyst view: municipal counts only, with small cells suppressed.

Individual records stay in the health-worker view. Counts come from the synthetic cohort's
model-visible fields or from recorded demo activity; no hidden simulator outcome is used.
"""
from __future__ import annotations

import pandas as pd

from agap.workflow import QUEUES
from agap.workflow_overview import overview_rows

TOTAL = "All municipalities"
ROUND_COLUMNS = ("Invited", *QUEUES, "Overdue open tasks")


def suppress(count, minimum):
    """Display a count, hiding 1..minimum-1 so a small group cannot point to a person."""
    count = int(count)
    return f"<{minimum}" if 0 < count < minimum else f"{count:,}"


def _share(numerator, denominator, minimum):
    return f"{numerator / denominator:.0%}" if denominator >= minimum and numerator >= minimum else "suppressed"


def cohort_summary(frame, max_distance_km, minimum):
    """Adults, questionnaire coverage and access by municipality, from model-visible fields only."""
    rows = []
    groups = [(name, group) for name, group in frame.groupby("municipality", sort=True)] + [(TOTAL, frame)]
    for name, group in groups:
        adults = len(group)
        reported = int(group.reported.astype(bool).sum())
        reachable = int(group.nearest_distance_km.le(max_distance_km).sum())
        rows.append({"Municipality": name, "Cohort adults": suppress(adults, minimum),
                     "Questionnaire submitted": suppress(reported, minimum),
                     "Questionnaire coverage": _share(reported, adults, minimum),
                     "Within access limit": _share(reachable, adults, minimum)})
    return pd.DataFrame(rows)


def round_work(worklist, today=None):
    """Numeric recorded work per municipality for map colouring (health-worker view; not suppressed)."""
    columns = ["invited", "open_tasks", "overdue", "open_share"]
    if worklist is None or worklist.empty:
        return pd.DataFrame(columns=columns)
    overview = overview_rows(worklist, today=today)
    work = overview.groupby("municipality").agg(invited=("resident_id", "size"), open_tasks=("open_task", "sum"),
                                                overdue=("overdue", "sum"))
    work["open_share"] = work.open_tasks / work.invited
    return work[columns]


def round_summary(worklist, minimum, today=None):
    """Recorded work in an approved round by municipality; replaced residents remain counted as invited."""
    if worklist.empty:
        return pd.DataFrame(columns=["Municipality", *ROUND_COLUMNS])
    overview = overview_rows(worklist, today=today)
    counts = []
    for name, group in list(overview.groupby("municipality", sort=True)) + [(TOTAL, overview)]:
        row = {"Municipality": name, "Invited": len(group)}
        row.update({queue: int(group.queue.eq(queue).sum()) for queue in QUEUES})
        row["Overdue open tasks"] = int(group.overdue.sum())
        counts.append(row)
    table = pd.DataFrame(counts)
    for column in ROUND_COLUMNS:
        table[column] = table[column].map(lambda value: suppress(value, minimum))
    return table
