"""Judge-facing what-if previews; saved historical experiments stay immutable."""
from __future__ import annotations

import copy
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from agap.experiment import CLINICAL, UNREPORTED_POLICY, allocate_policy, allocation_metrics
from agap.reports import normalize_report

STRATEGIES = {
    "Prioritize higher scores": ("risk_ranked", 0.0),
    "Priority + random outreach": ("risk_ranked", .2),
    "Priority + outreach to unreported residents": (UNREPORTED_POLICY, .2),
    "Share invitations by municipality": ("population_proportional", 0.0),
}
# Mixed strategies whose outreach share comes from the planner's outreach control.
OUTREACH_STRATEGIES = ("Priority + random outreach", "Priority + outreach to unreported residents")

SELECTION_REASONS = {
    "risk": "Higher model score", "risk_ranked": "Higher model score",
    "exploration": "Random outreach", "random": "Random invitation",
    "unreported outreach": "Outreach to residents without a questionnaire",
    "population_proportional": "Municipal share",
    "coverage requirement": "Municipal coverage requirement",
    "outside access limit": "Outside the assumed access limit",
    "reported known CKD": "Reported known CKD: follow their care plan, not first screening",
    "not invited": "No slot assigned under this plan",
    "quota shortfall reassigned": "Reassigned municipal slot",
}
QUESTIONNAIRE_COLUMNS = ("dm_report", "htn_report", "family_report", "outdoor_report")
QUEUE_FILTER_DEFAULTS = dict(municipality="All municipalities", questionnaire="All questionnaires",
                             access="All access", invitation="All invitation statuses", search="")


def outreach_share(settings):
    """The outreach share a plan actually uses; zero for strategies without outreach slots."""
    return float(settings.get("outreach", 0.)) if settings.get("strategy") in OUTREACH_STRATEGIES else 0.


def parity_share(frame):
    """Outreach share giving residents with and without a questionnaire equal invitation coverage."""
    return round(float((~frame.reported.astype(bool)).mean()), 2)


def with_reports(frame, reports):
    """Apply the session's latest report per resident; never mutate run artifacts."""
    working = frame
    for resident_id, payload in reports.items():
        if resident_id != payload["resident_id"]:
            raise ValueError("Report key must match its resident ID.")
        working = with_report(working, payload)
    return working


def planner_queue(scored, variant, max_distance_km, records=None):
    """Project an explicit operational allowlist, excluding simulator truth.

    Scores/ranks and assignments are joined by ID, never by dataframe position.
    Unplanned is distinct from a computed decision not to invite someone.
    """
    columns = ["resident_id", "municipality", "age", "female", "reported", "cutoff",
               "nearest_distance_km", *QUESTIONNAIRE_COLUMNS]
    queue = scored[columns + [c for c in ("reported_known_ckd",) if c in scored]].copy()
    if queue.resident_id.duplicated().any():
        raise ValueError("Resident IDs must be unique.")
    queue["score"] = scored[f"{variant}_score"]
    queue["rank"] = scored[f"{variant}_rank"]
    queue["missing_answers"] = queue[list(QUESTIONNAIRE_COLUMNS)].isna().sum(axis=1)
    queue["access_eligible"] = queue.nearest_distance_km.le(max_distance_km)
    queue["invitation_status"] = "Not planned"
    queue["selection_reason"] = "Compare screening plans to assign invitations"
    queue["facility_id"] = pd.NA
    queue["assigned_distance_km"] = float("nan")
    if records is not None:
        if records.resident_id.duplicated().any() or set(records.resident_id) != set(queue.resident_id):
            raise ValueError("Plan decisions must match the whole cohort exactly once.")
        decisions = records.set_index("resident_id")
        invited = queue.resident_id.map(decisions.invited)
        queue["invitation_status"] = invited.map({True: "Invited", False: "Not invited"})
        queue["selection_reason"] = queue.resident_id.map(decisions.reason).map(SELECTION_REASONS)
        queue["facility_id"] = queue.resident_id.map(decisions.facility_id)
        queue["assigned_distance_km"] = queue.resident_id.map(decisions.distance_km)
    return queue.sort_values(["rank", "resident_id"]).reset_index(drop=True)


def filter_queue(queue, municipality="All municipalities", questionnaire="All questionnaires",
                 access="All access", invitation="All invitation statuses", search=""):
    """View filters only: this function never feeds allocation or export."""
    keep = pd.Series(True, index=queue.index)
    if municipality != "All municipalities":
        keep &= queue.municipality.eq(municipality)
    if questionnaire == "No questionnaire":
        keep &= ~queue.reported
    elif questionnaire == "Questionnaire available":
        keep &= queue.reported
    elif questionnaire == "Missing model answers":
        keep &= queue.missing_answers.gt(0)
    if access != "All access":
        keep &= queue.access_eligible.eq(access == "Within assumed access limit")
    if invitation != "All invitation statuses":
        keep &= queue.invitation_status.eq(invitation)
    if search.strip():
        keep &= queue.resident_id.str.contains(search.strip(), case=False, regex=False)
    return queue.loc[keep].reset_index(drop=True)


def queue_status(queue, plan_state="unplanned"):
    """Readable operational states; no probability thresholds or inferred causes."""
    if plan_state not in ("unplanned", "ready", "unavailable"):
        raise ValueError("Unknown plan state")
    if plan_state == "unavailable":
        return pd.Series("Plan unavailable", index=queue.index, name="Status")
    if plan_state == "ready":
        return queue.selection_reason.map(
            lambda value: str(value).strip() if pd.notna(value) and str(value).strip() else "Reason unavailable"
        ).rename("Status")
    known = queue.reported_known_ckd.fillna(False).astype(bool) if "reported_known_ckd" in queue else pd.Series(False, index=queue.index)
    values = np.select([
        known, ~np.isfinite(queue.nearest_distance_km), ~queue.access_eligible,
        ~queue.reported, queue.missing_answers.gt(0),
    ], ["Reported known CKD · care plan", "Distance unavailable", "Outside access limit", "No report · reachable",
        "Missing answers · reachable"],
        default="Complete model answers · reachable")
    return pd.Series(values, index=queue.index, name="Status")


def selected_queue_resident(resident_ids, rows):
    """Dataframe events refer to input row positions, not native sort order."""
    if not rows or not 0 <= rows[0] < len(resident_ids):
        return None
    return resident_ids[rows[0]]


def filters_for_resident(queue, resident_id, filters):
    """Relax only view predicates hiding an explicitly followed resident."""
    person = queue.loc[queue.resident_id.eq(resident_id)]
    if person.empty:
        raise ValueError("The followed resident is absent from the current cohort.")
    return {name: default for name, default in QUEUE_FILTER_DEFAULTS.items()
            if filter_queue(person, **{name: filters.get(name, default)}).empty}


def invitation_export(queue, run_id, model, settings):
    """Export only invited operational records from the unfiltered whole plan."""
    columns = ["resident_id", "municipality", "reported", "score", "selection_reason",
               "facility_id", "assigned_distance_km"]
    export = queue.loc[queue.invitation_status.eq("Invited"), columns].copy()
    export["run_id"] = run_id
    export["model"] = model
    export["budget_panels"] = settings["budget"]
    export["strategy"] = settings["strategy"]
    export["outreach_share"] = outreach_share(settings)
    export["data_status"] = "Synthetic residents; hypothetical service points; invitation preview"
    return export


def with_report(frame, payload):
    """Apply one hypothetical report to model-visible columns, without hidden traits."""
    normalized, errors = normalize_report(payload["resident_id"], payload["age"], payload)
    if errors:
        raise ValueError(" ".join(errors))
    matches = frame.resident_id == normalized["resident_id"]
    if matches.sum() != 1:
        raise ValueError("Choose a resident from this demonstration cohort.")
    if int(frame.loc[matches, "age"].iloc[0]) != normalized["age"]:
        raise ValueError("This demonstration keeps the resident's known age fixed.")
    output = frame.copy(deep=True)
    output.loc[matches, "reported"] = True
    for key, column in (("DM", "dm_report"), ("HTN", "htn_report"), ("FAM", "family_report"), ("OUT", "outdoor_report"),
                        ("PRIOR", "prior_screen_report")):
        # Unknown ("U") and not answered (None) are both missing model inputs.
        output.loc[matches, column] = {"Y": 1.0, "N": 0.0}.get(normalized[key], np.nan)
    output.loc[matches, "outdoor_hours_7d_report"] = float(normalized["HRS"]) if isinstance(normalized["HRS"], int) else np.nan
    return output


GEOGRAPHY_SOURCES = {"fixture": "illustrative fixture geography", "public": "public WorldPop and boundary data"}
CLIMATE_SOURCES = {"synthetic": "synthetic fixture climate", "era5_land": "ERA5-Land historical climate"}


def run_summary(manifest, run_id):
    """NFR-10: active scenario, source mode, run identifier and synthetic-data status for the page header."""
    prototype = manifest["configuration"]["prototype"]
    climate = manifest.get("climate_mode") or manifest["configuration"].get("climate", {}).get("mode", "synthetic")
    started = manifest.get("started_utc", "")
    sources = f"{GEOGRAPHY_SOURCES[prototype['geography_mode']]} · {CLIMATE_SOURCES[climate]}"
    if manifest["configuration"].get("weather_preview", {}).get("enabled"):
        sources += " · real ERA5-Land weather context (not model input)"
    return dict(
        scenario=f"{prototype['mechanism']} missingness · assumed heat odds ratio {prototype['heat_or']:g}",
        sources=sources,
        run_id=manifest.get("run_id", run_id), repetition=int(manifest.get("repetition", 0)),
        started=f"{started[:16].replace('T', ' ')} UTC" if started else "start time not recorded",
        status="Synthetic residents and medical outcomes")


def summary_for(records, cfg):
    return allocation_metrics(records, cfg).query("subgroup == 'all'").iloc[0].to_dict()


def compare_plans(frame, facilities, scores, cfg, budget, strategy, outreach=.2):
    if strategy not in STRATEGIES:
        raise ValueError("Unknown screening plan")
    if isinstance(budget, bool) or not isinstance(budget, (int, np.integer)) or not 1 <= budget <= len(frame):
        raise ValueError("Budget must be a whole number between 1 and the cohort size.")
    if not 0 <= outreach <= 1:
        raise ValueError("Outreach share must be between zero and one.")
    preview_cfg = copy.deepcopy(cfg)
    preview_cfg["allocation"]["budget_tests"] = int(budget)
    policy, share = STRATEGIES[strategy]
    if strategy in OUTREACH_STRATEGIES:
        share = outreach
    # Stable draws make changes in the preview attributable to the chosen plan.
    baseline = allocate_policy(preview_cfg, frame, facilities, scores, "random", seed=cfg["seed"] + 100)
    proposed = allocate_policy(preview_cfg, frame, facilities, scores, policy, share, seed=cfg["seed"] + 100)
    risk = proposed if strategy == "Prioritize higher scores" else allocate_policy(
        preview_cfg, frame, facilities, scores, "risk_ranked", 0., seed=cfg["seed"] + 100)
    mixed = proposed if strategy == "Priority + random outreach" else allocate_policy(
        preview_cfg, frame, facilities, scores, "risk_ranked", outreach, seed=cfg["seed"] + 100)
    return dict(random=baseline, proposed=proposed,
                risk=risk, mixed=mixed,
                random_summary=summary_for(baseline, preview_cfg),
                proposed_summary=summary_for(proposed, preview_cfg))


def load_demo(directory: Path):
    # Only load artifacts generated locally by this project, never uploaded pickle files.
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    facilities = pd.read_parquet(directory / "facilities.parquet")
    model = joblib.load(directory / "model_clinical.joblib")
    scores = model.predict_proba(frame[CLINICAL])[:, 1]
    return frame, facilities, model, scores


def report_preview(frame, facilities, model, original_scores, cfg, budget, strategy, payload, outreach=.2):
    updated = with_report(frame, payload)
    features = list(model.feature_names_in_)
    scores = model.predict_proba(updated[features])[:, 1]
    original_plan = compare_plans(frame, facilities, original_scores, cfg, budget, strategy, outreach)
    updated_plan = compare_plans(updated, facilities, scores, cfg, budget, strategy, outreach)
    index = int(np.flatnonzero((frame.resident_id == payload["resident_id"]).to_numpy())[0])
    def position(values):
        ordering = np.lexsort((frame.tie_uniform.to_numpy(), -np.asarray(values)))
        return int(np.flatnonzero(ordering == index)[0]) + 1
    return dict(original=original_plan, updated=updated_plan, index=index,
                score_before=float(original_scores[index]), score_after=float(scores[index]),
                position_before=position(original_scores), position_after=position(scores))
