"""Read-only diagnostics for live plans; hidden outcomes remain evaluation-only."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

BUCKETS = ("Found (eval)", "Invited but incomplete (eval)",
           "Feasible but uninvited (eval)", "Outside access limit (eval)")


def resident_chips(person, decision, max_distance_km):
    """Factual reported answers and operational access/decision information only."""
    chips = [("demographic", f"Age {int(person.age)}")]
    if not person.reported:
        chips.append(("missing", "No questionnaire submitted"))
    elif decision.missing_answers:
        chips.append(("missing", f"{int(decision.missing_answers)} of 4 model answers missing"))
    else:
        chips.append(("reported", "All 4 model answers reported"))
    for column, label in (("dm_report", "Diabetes"), ("htn_report", "Hypertension"),
                          ("family_report", "Family history"), ("outdoor_report", "Outdoor work")):
        value = person.get(column)
        if pd.notna(value):
            chips.append(("answer", f"{label}: {'Yes' if value == 1 else 'No'}"))
    distance = decision.nearest_distance_km
    if pd.isna(distance) or not np.isfinite(distance):
        chips.append(("access", "Nearest point: distance unavailable"))
    else:
        label = "Within" if decision.access_eligible else "Outside"
        chips.append(("access", f"{label} {max_distance_km:g} km limit ({distance:.1f} km)"))
    if decision.get("display_status") == "Plan unavailable":
        chips.append(("uninvited", "Plan unavailable"))
    elif decision.invitation_status == "Invited":
        reason = decision.selection_reason if pd.notna(decision.selection_reason) else "Reason unavailable"
        assignment = (f" · {decision.facility_id} ({decision.assigned_distance_km:.1f} km)"
                      if pd.notna(decision.get("facility_id")) and pd.notna(decision.get("assigned_distance_km")) else "")
        chips.append(("invited", f"Invited · {reason}{assignment}"))
    elif decision.invitation_status == "Not invited":
        reason = decision.selection_reason if pd.notna(decision.selection_reason) else "Reason unavailable"
        chips.append(("uninvited", f"Not invited · {reason}"))
    return chips


def weather_context_dates(local, saved_cutoff, days=30):
    """Coverage/default for one source cell and window; never replace missing data."""
    if days not in (7, 30):
        raise ValueError("Weather context requires a 7-day or 30-day window.")
    saved = pd.Timestamp(saved_cutoff).normalize()
    complete = local[f"complete_{days}d"].fillna(False).astype(bool)
    dates = pd.DatetimeIndex(pd.to_datetime(local.loc[complete, "cutoff"])).normalize().unique().sort_values()
    earlier = dates[dates <= saved]
    default = earlier[-1] if len(earlier) else dates[0] if len(dates) else None
    return dict(saved_available=saved in dates, default=default)


def evaluation_mask(records, category):
    if category == "All invited":
        return records.invited.astype(bool)
    positive = records.y_true.astype(bool)
    masks = {
        BUCKETS[0]: positive & records.invited & records.completed,
        BUCKETS[1]: positive & records.invited & ~records.completed,
        BUCKETS[2]: positive & records.access_feasible & ~records.invited,
        BUCKETS[3]: positive & ~records.access_feasible,
    }
    return masks[category]


QUESTIONNAIRE_GROUPS = (("Questionnaire submitted", True), ("No questionnaire", False))


def reach_by_questionnaire(queue):
    """Operational invitation coverage by questionnaire status; uses no hidden outcome."""
    invited = queue.invitation_status.eq("Invited")
    rows = []
    for label, reported in QUESTIONNAIRE_GROUPS:
        group = queue.reported.astype(bool).eq(reported)
        residents, count = int(group.sum()), int((group & invited).sum())
        rows.append({"Questionnaire": label, "Residents": residents, "Invited": count,
                     "Invitation coverage": count / residents if residents else np.nan})
    return pd.DataFrame(rows)


def positives_by_questionnaire(records):
    """Simulation evaluation only: hidden initial positives found, split by questionnaire status."""
    rows = []
    for label, reported in QUESTIONNAIRE_GROUPS:
        group = records.loc[records.reported.astype(bool).eq(reported)]
        positives, found = int(group.y_true.sum()), int(group.positive_detected.sum())
        rows.append({"Questionnaire": label, "Hidden initial positives (eval)": positives,
                     "Found (eval)": found, "Share found (eval)": found / positives if positives else np.nan})
    return pd.DataFrame(rows)


def live_policies(result, settings):
    policies = {"Random invitations": result["random"], "Pure risk · 0% outreach": result["risk"],
                f"Priority + {settings['outreach']:.0%} outreach": result["mixed"]}
    if settings["strategy"] not in ("Prioritize higher scores", "Priority + random outreach"):
        policies[settings["strategy"]] = result["proposed"]
    return policies


def bottleneck_counts(policies):
    rows = []
    for label, records in policies.items():
        eligible = int(records.y_true.sum())
        counts = [int(evaluation_mask(records, category).sum()) for category in BUCKETS]
        if sum(counts) != eligible:
            raise ValueError("Hidden-positive bottleneck categories must partition the eligible positives.")
        rows.extend(dict(Plan=label, Category=category, Count=count,
                         Share=count / eligible if eligible else 0., Eligible=eligible)
                    for category, count in zip(BUCKETS, counts))
    return pd.DataFrame(rows)


def marginal_swap(risk, mixed):
    """Observed differences between invitation sets, without assuming a mechanism."""
    risk_ids = set(risk.loc[risk.invited, "resident_id"])
    mixed_ids = set(mixed.loc[mixed.invited, "resident_id"])
    rows = []
    for label, records, ids in (("Displaced pure-risk invitees", risk, risk_ids - mixed_ids),
                                ("Added mixed-plan invitees", mixed, mixed_ids - risk_ids)):
        subset = records.loc[records.resident_id.isin(ids)]
        rows.append(dict(Group=label, Residents=len(subset), Mean_score=subset.score.mean(),
                         Mean_age=subset.age.mean(), Reported_share=subset.reported.mean(),
                         Access_feasible_share=subset.access_feasible.mean()))
    return pd.DataFrame(rows)


def resident_timeline(person, current, followup=None, history=(), applied=False, day=180):
    """Clinical-looking stages are explicitly simulated, never inferred from eligibility."""
    if applied:
        report = "Validated · what-if applied"
    elif person.reported:
        report = "Available in saved synthetic run"
    elif history and not history[-1].get("valid"):
        report = "Validation failed · latest attempt excluded"
    elif history:
        report = "Validated preview only · not applied"
    else:
        report = "No report"
    invitation, screening, visit = "Not planned", "Not planned", "Not planned"
    if current is not None:
        invitation = (f"Invited · {current.reason} · {current.facility_id}" if current.invited
                      else f"Not invited · {current.reason}")
        screening = ("Completed panel" if current.completed else "Invited · did not complete" if current.invited
                     else "No panel · not invited")
        if current.positive_detected:
            screening += " · eval truth: abnormal initial flag detected"
            required = ["followup_included", f"visit_uniform_{day}d", f"abnormal_{day}d"]
            if followup is None or any(name not in followup for name in required):
                visit = "Unavailable in this saved run"
            elif not followup.followup_included:
                visit = "Excluded · incomplete climate coverage at required follow-up visits"
            elif not np.isfinite(followup[f"visit_uniform_{day}d"]) or not np.isfinite(person.completion_probability):
                visit = "Unavailable attendance inputs"
            elif followup[f"visit_uniform_{day}d"] >= person.completion_probability:
                visit = f"Missed {day}d visit · observed unknown"
            else:
                outcome = "Persistent abnormal (eval)" if followup[f"abnormal_{day}d"] else "Normal again (eval)"
                visit = f"Attended {day}d · {outcome}"
        else:
            visit = "Not applicable · no abnormal initial screen detected"
    return [("Report validation", report), ("Simulated invitation", invitation),
            ("Simulated screening", screening), (f"Follow-up · {day}d evaluation", visit)]


def evidence_scorecard(directory):
    """Missing artifacts mean unavailable, never a fabricated pass or default zero."""
    def read(name):
        try:
            return json.loads((directory / name).read_text())
        except (OSError, ValueError):
            return None

    cards = []
    population = read("population_check.json")
    if isinstance(population, dict) and all(key in population for key in ("relative_difference", "tolerance")):
        error, tolerance = population["relative_difference"], population["tolerance"]
        cards.append(("Population conservation", "Passed" if error <= tolerance else "Failed", f"Relative error {error:.2e} · tolerance {tolerance:g}"))
    else:
        cards.append(("Population conservation", "Unavailable", "No complete population check artifact"))
    integrity = read("integrity.json")
    if isinstance(integrity, dict) and "passed" in integrity and isinstance(integrity.get("checks"), list):
        complete = bool(integrity["checks"]) and integrity["passed"] == len(integrity["checks"]) and not integrity.get("skipped_missing_files")
        cards.append(("Pipeline safeguards", f"{integrity['passed']} passed" if complete else "Incomplete",
                      "References and range checks · engineering safeguards"))
    else:
        cards.append(("Pipeline safeguards", "Unavailable", "No complete integrity artifact"))
    weights = read("weight_diagnostics.json")
    weight = next((row for row in weights if isinstance(row, dict) and row.get("model") == "ipw_climate"), None) if isinstance(weights, list) else None
    if weight and all(key in weight for key in ("effective_sample_size", "min_population_observation_probability", "population_claim")):
        cards.append(("IPW support · saved model", f"ESS {weight['effective_sample_size']:.1f}",
                      f"Minimum population observation probability {weight['min_population_observation_probability']:.3g} · "
                      f"{weight['population_claim']} · {weight.get('weight_source', 'weight source unavailable')}"))
    else:
        cards.append(("IPW support · saved model", "Unavailable", "No complete weighting diagnostics"))
    spatial = read("spatial_sensitivity.json")
    if isinstance(spatial, dict) and isinstance(spatial.get("ranking_changed"), bool):
        cards.append(("Spatial sensitivity · saved model", "Ranking changed" if spatial["ranking_changed"] else "Ranking stable",
                      "Policy ordering at H3 resolutions 8 and 7 · saved allocation-model experiment"))
    else:
        cards.append(("Spatial sensitivity · saved model", "Unavailable", "No spatial sensitivity artifact"))
    return cards
