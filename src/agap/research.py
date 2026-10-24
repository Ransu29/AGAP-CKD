"""Engine 4 voluntary research gateway: synthetic interest, eligibility and comparison cohorts.

A separate demonstration (E4-01..E4-07). Eligibility uses reported answers only, never
hidden traits. Nothing here feeds screening scores, invitations or allocation (E4-05);
interest is simulated on its own random stream. Outputs are synthetic research-workflow
demonstrations: not consent, enrolment, an institutional partnership or genomic findings.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from agap.experiment import rng_for

RULE_VERSION = "demo-1"
STATES = ("not expressed", "interested", "declined", "withdrawn")
RESEARCH_COMPONENT = 50  # rng component; screening streams never use it
LABEL = ("SYNTHETIC RESEARCH-WORKFLOW DEMONSTRATION. Not consent, study enrolment, an institutional "
         "partnership or genomic findings.")
CRITERIA = (
    ("age_40_plus", "Age 40 or older"),
    ("reported_dm_or_htn", "Reported diabetes or hypertension (answer 'Yes')"),
)


def eligibility(frame):
    """Per-criterion results from reported answers; unknown or unreported never counts as yes."""
    checks = pd.DataFrame({"resident_id": frame.resident_id.to_numpy(),
                           "age_40_plus": frame.age.to_numpy(float) >= 40,
                           "reported_dm_or_htn": frame.dm_report.eq(1).to_numpy() | frame.htn_report.eq(1).to_numpy()})
    checks["eligible"] = checks[[name for name, _ in CRITERIA]].all(axis=1)
    checks["rule_version"] = RULE_VERSION
    return checks


def reasons(row):
    """Readable reason for each criterion of one eligibility row."""
    return [f"{'✓' if row[name] else '✗'} {label}" for name, label in CRITERIA]


def simulate_interest(frame, cfg, repetition=0):
    """Initial interest events for every resident, drawn on the research stream only."""
    settings = cfg.get("research", {})
    shares = settings.get("interest_shares", {"interested": .35, "declined": .15, "not expressed": .50})
    if set(shares) - set(STATES) or abs(sum(shares.values()) - 1) > 1e-9:
        raise ValueError(f"research.interest_shares must use states {STATES[:3]} and sum to 1")
    rng = rng_for(cfg["seed"], repetition, RESEARCH_COMPONENT)
    states = list(shares)
    drawn = rng.choice(states, size=len(frame), p=[shares[state] for state in states])
    events = pd.DataFrame(dict(resident_id=frame.resident_id.to_numpy(), state=drawn, sequence=0,
                               source="simulated", rule_version=RULE_VERSION))
    withdrawing = (drawn == "interested") & (rng.random(len(frame)) < settings.get("later_withdrawal_share", .10))
    withdrawals = events[withdrawing].assign(state="withdrawn", sequence=1)
    return pd.concat([events, withdrawals], ignore_index=True)


def record_event(path: Path, resident_id, state, eligible):
    """Append one manual state change; history is never rewritten (E4-06)."""
    if state not in STATES:
        raise ValueError(f"Unknown research-interest state: {state}")
    path.parent.mkdir(parents=True, exist_ok=True)
    event = dict(resident_id=resident_id, state=state, eligible=bool(eligible), rule_version=RULE_VERSION,
                 source="manual", time_utc=datetime.now(timezone.utc).isoformat())
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
    return event


def read_events(path: Path):
    if not path.exists():
        return pd.DataFrame(columns=["resident_id", "state", "source", "rule_version"])
    return pd.DataFrame([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()])


def current_states(simulated, manual):
    """Latest state per resident: manual events follow simulated ones in recorded order."""
    history = pd.concat([simulated.assign(order=simulated.sequence),
                         manual.assign(order=100 + np.arange(len(manual)))], ignore_index=True)
    return history.sort_values("order", kind="stable").groupby("resident_id").tail(1).set_index("resident_id").state


def comparison_cohort(frame, states, seed, ratio=1):
    """Match reported outdoor workers to non-outdoor workers by age band and sex (E4-04).

    Draws only from residents who are eligible under the current rule AND whose latest state
    is 'interested'; declined, withdrawn and not-expressed residents are never included.
    """
    checks = eligibility(frame).set_index("resident_id")
    pool = frame.set_index("resident_id").join(checks[["eligible"]])
    pool["state"] = states.reindex(pool.index).fillna("not expressed")
    pool = pool[pool.eligible & pool.state.eq("interested") & pool.outdoor_report.isin([0, 1])].copy()
    pool["age_band"] = pd.cut(pool.age, [39, 49, 59, 69, 200], labels=["40–49", "50–59", "60–69", "70+"]).astype(str)
    rng = np.random.default_rng(seed)
    rows = []
    for (band, female), group in pool.groupby(["age_band", "female"], sort=True):
        index = group[group.outdoor_report.eq(1)]
        candidates = group[group.outdoor_report.eq(0)]
        take = min(len(index), len(candidates) // ratio)
        if not take:
            continue
        index = index.iloc[rng.permutation(len(index))[:take]]
        comparison = candidates.iloc[rng.permutation(len(candidates))[:take * ratio]]
        for name, members in (("index: reported outdoor work", index), ("comparison: no outdoor work", comparison)):
            rows.append(pd.DataFrame(dict(resident_id=members.index, group=name, age_band=band,
                                          sex=np.where(female, "F", "M"), municipality=members.municipality.to_numpy())))
    columns = ["resident_id", "group", "age_band", "sex", "municipality"]
    cohort = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=columns)
    return cohort.assign(rule_version=RULE_VERSION, label=LABEL)
