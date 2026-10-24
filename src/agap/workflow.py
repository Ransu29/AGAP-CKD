"""Frozen, synthetic screening rounds and their operational event projections.

This module is deliberately independent of Streamlit and persistence. Simulator
outcomes are never copied into a round or used to choose an operational action.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import math
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from agap.experiment import UNREPORTED_POLICY, distance_matrix, fingerprint, policy_order, source_hash
from agap.reports import normalize_report
from agap.simulate.kidney import ckd_epi_2021, observed_screen_label


SCHEMA_VERSION = 1
MANILA = ZoneInfo("Asia/Manila")
QUEUES = ("Needs contact", "Awaiting screening", "Needs review / follow-up",
          "Tasks complete", "Declined / withdrawn")
RESIDENT_FIELDS = frozenset({
    "resident_id", "municipality", "h3", "era5_cell", "latitude", "longitude",
    "age", "female", "reported", "dm_report", "htn_report", "family_report",
    "outdoor_report", "prior_screen_report", "outdoor_hours_7d_report", "cutoff",
    "report_event_date", "report_available_date", "score", "priority_rank",
    "random_rank", "candidate_distances_km", "reported_known_ckd",
})
FACILITY_FIELDS = frozenset({"facility_id", "municipality", "latitude", "longitude", "capacity", "name"})
SLOT_FIELDS = frozenset({
    "slot_id", "round_id", "facility_id", "municipality", "selection_route",
    "ordering_basis", "selection_reason", "original_reason", "status", "version",
    "current_resident_id", "original_resident_id", "distance_km", "replacement_count",
})
EVENT_TYPES = frozenset({"contact", "specimen", "result", "review", "followup_complete",
                         "assignment", "report_applied", "report_attempt", "communication", "referral"})
# A contact outcome that releases an unstarted slot. Unreachable needs repeated unanswered attempts first.
RELEASING_OUTCOMES = frozenset({"Declined", "Withdrawn", "Unreachable"})
DEFAULT_UNREACHABLE_AFTER = 3
COMMUNICATION_METHODS = ("In person", "Phone call", "Home visit", "SMS")
REFERRAL_STATUSES = ("Sent", "Attended", "Did not attend", "Outcome unknown")
OPEN_REFERRAL = frozenset({"Sent", "Did not attend"})
WORKLIST_COLUMNS = [
    "resident_id", "municipality", "reported", "report_status", "questionnaire_status",
    "queue", "status", "next_action", "due_on", "owner", "contact_outcome",
    "panel_complete", "screening_flag", "creatinine", "uacr", "egfr", "specimen_date",
    "result_reference", "slot_id", "slot_state", "is_current", "facility_id",
    "selection_reason", "reason", "selection_route", "ordering_basis", "last_activity",
    "review_open", "review_disposition", "followup_open", "original_resident_id",
    "assigned_distance_km", "started", "age", "female", "latest_result_event_id",
    "slot_available_for_replacement", "review_pending", "results_communicated", "communication_needed",
    "referral_status", "referral_destination", "referral_open", "no_answer_count",
]


def _plain(value):
    """Convert numpy/pandas values to strict JSON without NaN or infinity."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_plain(item) for item in value]
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _rows(values):
    if isinstance(values, pd.DataFrame):
        return values.to_dict("records")
    return list(values or [])


def _integer(value, label, minimum=0):
    try:
        numeric = float(value)
        if isinstance(value, bool) or not math.isfinite(numeric) or numeric != int(numeric) or numeric < minimum:
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label} must be a whole number at least {minimum}.") from None
    return int(numeric)


def _reason_route(reason, policy):
    if reason in {"risk", "risk_ranked"}:
        return "priority", "priority"
    if reason in {"exploration", "random"}:
        return "outreach", "random"
    if reason == "unreported outreach":
        # A released outreach slot is offered to the next resident who had no questionnaire.
        return "outreach", "unreported"
    if reason in {"population_proportional", "quota shortfall reassigned"}:
        return "municipality", "random"
    if reason == "coverage requirement":
        return "municipality", "random" if policy in {"random", "population_proportional"} else "priority"
    raise ValueError(f"Unsupported approved invitation reason: {reason}")


def build_round_snapshot(scored, facilities, records, cfg, run_id, model, settings,
                         manifest=None, applied_reports=None):
    """Freeze the actual approved cohort, policy order, inputs and assignments.

    ``records`` is one complete allocation, usually ``compare_plans()['proposed']``.
    The passed scored frame may contain research/evaluation fields: an explicit
    allowlist prevents those fields from entering the workflow snapshot.
    """
    scored, facilities, records = scored.copy(), facilities.copy(), records.copy()
    if scored.empty or scored.resident_id.duplicated().any():
        raise ValueError("The round needs a nonempty cohort with unique resident IDs.")
    if records.resident_id.duplicated().any() or set(records.resident_id) != set(scored.resident_id):
        raise ValueError("Approved decisions must match the whole cohort exactly once.")
    if facilities.facility_id.duplicated().any():
        raise ValueError("Service-point IDs must be unique.")
    strategy = settings.get("strategy", "Priority + random outreach")
    policies = {"Prioritize higher scores": "risk_ranked", "Priority + random outreach": "risk_ranked",
                "Priority + outreach to unreported residents": UNREPORTED_POLICY,
                "Share invitations by municipality": "population_proportional", "Random invitations": "random"}
    policy = settings.get("policy", policies.get(strategy))
    if policy is None and "policy" in records:
        policy = str(records.policy.iloc[0])
        if policy.startswith("risk_explore_"):
            policy = "risk_ranked"
        elif policy.startswith("risk_unreported_"):
            policy = UNREPORTED_POLICY
    if policy not in {"risk_ranked", "risk", "random", "population_proportional", UNREPORTED_POLICY}:
        raise ValueError("Unknown approved allocation policy.")
    mixed = strategy in ("Priority + random outreach", "Priority + outreach to unreported residents")
    share = float(settings.get("outreach", settings.get("share", .2 if mixed else 0)))
    if policy not in {"risk_ranked", UNREPORTED_POLICY} or strategy == "Prioritize higher scores":
        share = 0.0
    seed = int(settings.get("seed", cfg["seed"] + 100))
    budget = int(settings.get("budget", cfg["allocation"]["budget_tests"]))
    if budget < 0 or not 0 <= share <= 1:
        raise ValueError("Invalid approved budget or outreach share.")
    if "tie_uniform" not in scored or not np.isfinite(scored.tie_uniform).all():
        raise ValueError("Freeze the original finite allocation tie-breaks with the cohort.")
    score_column = f"{model}_score" if f"{model}_score" in scored else "score"
    scores = (scored[score_column].to_numpy(float) if score_column in scored
              else scored.resident_id.map(records.set_index("resident_id").score).to_numpy(float))
    if not np.isfinite(scores).all():
        raise ValueError("Every approved candidate needs a finite score.")
    if "score" in records:
        approved_scores = scored.resident_id.map(records.set_index("resident_id").score).to_numpy(float)
        if not np.array_equal(scores, approved_scores):
            raise ValueError("The draft scores changed after allocation. Compare the screening plan again before approval.")
    ranked = policy_order(scored, scores, "risk_ranked", 0.0, seed)
    random = policy_order(scored, scores, "random", 0.0, seed)
    primary = policy_order(scored, scores, policy, share, seed)
    primary = primary[0] if isinstance(primary, tuple) else primary
    resident_ids = scored.resident_id.astype(str).tolist()
    orders = {"priority": [resident_ids[index] for index in ranked],
              "random": [resident_ids[index] for index in random],
              "policy": [resident_ids[index] for index in primary]}
    distances = distance_matrix(scored, facilities)
    if not np.isfinite(distances).all():
        raise ValueError("All candidates and service points need finite coordinates.")
    priority_rank = {resident: index + 1 for index, resident in enumerate(orders["priority"])}
    random_rank = {resident: index + 1 for index, resident in enumerate(orders["random"])}
    residents = []
    for index, row in enumerate(scored.to_dict("records")):
        item = {key: value for key, value in row.items() if key in RESIDENT_FIELDS}
        rid = str(row["resident_id"])
        item.update(resident_id=rid, score=float(scores[index]), priority_rank=priority_rank[rid],
                    random_rank=random_rank[rid], candidate_distances_km={
                        str(facility): float(distances[index, fi]) for fi, facility in enumerate(facilities.facility_id)})
        residents.append(item)
    slots = []
    for record in records.loc[records.invited.astype(bool)].to_dict("records"):
        reason = str(record["reason"])
        route, basis = _reason_route(reason, policy)
        rid = str(record["resident_id"])
        facility_id = str(record["facility_id"])
        resident = residents[resident_ids.index(rid)]
        if facility_id not in resident["candidate_distances_km"]:
            raise ValueError("An approved assignment references an unknown service point.")
        slots.append(dict(slot_id=f"slot-{len(slots) + 1:06d}", facility_id=facility_id,
                          municipality=str(record["municipality"]), selection_route=route,
                          ordering_basis=basis, selection_reason=reason, original_reason=reason,
                          status="reserved", current_resident_id=rid, original_resident_id=rid,
                          distance_km=resident["candidate_distances_km"][facility_id], version=0,
                          replacement_count=0))
    manifest = manifest or {}
    if manifest.get("run_id", run_id) != run_id:
        raise ValueError("The approved manifest belongs to a different run.")
    checksums = manifest.get("input_checksums", {})
    provenance = dict(run_id=run_id, config_hash=manifest.get("config_hash", fingerprint(cfg)),
                      source_hash=manifest.get("source_hash"), input_checksums=checksums,
                      input_hash=hashlib.sha256(json.dumps(checksums, sort_keys=True).encode()).hexdigest()[:8],
                      git_commit=manifest.get("git_commit"), started_utc=manifest.get("started_utc"))
    frozen_settings = dict(strategy=strategy, policy=policy, budget=budget, outreach=share, seed=seed,
                           max_distance_km=float(cfg["allocation"]["max_distance_km"]),
                           unreachable_after_attempts=int(cfg.get("workflow", {}).get("unreachable_after_attempts",
                                                                                   DEFAULT_UNREACHABLE_AFTER)),
                           outcome=dict(cfg["outcome"]), coverage=cfg["allocation"].get("coverage", {}))
    snapshot = dict(schema_version=SCHEMA_VERSION, run_id=str(run_id), model=str(model),
                    provenance=provenance, settings=frozen_settings, orders=orders,
                    residents=residents, facilities=[{k: v for k, v in item.items() if k in FACILITY_FIELDS}
                                                    for item in facilities.to_dict("records")],
                    slots=slots, applied_reports=applied_reports or {}, app_source_hash=source_hash())
    return normalize_snapshot(_plain(snapshot))


def normalize_snapshot(snapshot):
    """Validate a frozen operational snapshot and remove non-operational fields."""
    allowed = {"schema_version", "run_id", "round_id", "model", "provenance", "settings", "orders",
               "residents", "facilities", "slots", "applied_reports", "app_source_hash", "ui_source_hash"}
    value = {key: _plain(item) for key, item in snapshot.items() if key in allowed}
    if value.get("schema_version") != SCHEMA_VERSION or not value.get("run_id"):
        raise ValueError("Unsupported or unidentified screening round.")
    value["residents"] = [{key: item for key, item in resident.items() if key in RESIDENT_FIELDS}
                          for resident in value.get("residents", [])]
    value["facilities"] = [{key: item for key, item in facility.items() if key in FACILITY_FIELDS}
                           for facility in value.get("facilities", [])]
    value["slots"] = [{key: item for key, item in slot.items() if key in SLOT_FIELDS}
                      for slot in value.get("slots", [])]
    settings_fields = {"strategy", "policy", "budget", "outreach", "seed", "max_distance_km", "outcome", "coverage",
                       "unreachable_after_attempts"}
    value["settings"] = {k: v for k, v in value.get("settings", {}).items() if k in settings_fields}
    value["settings"]["outcome"] = {k: v for k, v in value["settings"].get("outcome", {}).items()
                                    if k in {"egfr_threshold", "uacr_threshold"}}
    value["settings"]["coverage"] = {k: v for k, v in value["settings"].get("coverage", {}).items()
                                     if k in {"minimum_invitations_per_municipality", "minimum_invitations"}}
    value["orders"] = {k: v for k, v in value.get("orders", {}).items() if k in {"priority", "random", "policy"}}
    residents = {str(row["resident_id"]): row for row in value["residents"]}
    facilities = {str(row["facility_id"]): row for row in value["facilities"]}
    if len(residents) != len(value["residents"]) or not residents:
        raise ValueError("Snapshot resident IDs must be unique and nonempty.")
    if len(facilities) != len(value["facilities"]) or not facilities:
        raise ValueError("Snapshot service-point IDs must be unique and nonempty.")
    for facility in facilities.values():
        facility["capacity"] = _integer(facility.get("capacity"), "Service-point capacity")
    value["settings"]["budget"] = _integer(value["settings"].get("budget"), "Panel budget")
    thresholds = value["settings"]["outcome"]
    for key in ("egfr_threshold", "uacr_threshold"):
        try:
            threshold = float(thresholds[key])
            if not math.isfinite(threshold) or threshold <= 0:
                raise ValueError()
        except (TypeError, KeyError, ValueError):
            raise ValueError("Frozen screening thresholds must be finite and positive.") from None
        thresholds[key] = threshold
    for resident in residents.values():
        distances = resident.get("candidate_distances_km", {})
        if set(distances) != set(facilities):
            raise ValueError("Freeze every resident's distances to every approved service point.")
        for distance in distances.values():
            if distance is None or isinstance(distance, bool) or not math.isfinite(float(distance)) or float(distance) < 0:
                raise ValueError("Frozen candidate distances must be finite and nonnegative.")
    for name, order in value.get("orders", {}).items():
        if len(order) != len(residents) or set(order) != set(residents):
            raise ValueError(f"The frozen {name} order must contain the entire cohort exactly once.")
    if not {"priority", "random"}.issubset(value.get("orders", {})):
        raise ValueError("The round needs frozen priority and random orders.")
    limit = float(value["settings"]["max_distance_km"])
    if not math.isfinite(limit) or limit < 0:
        raise ValueError("The frozen access limit must be finite and nonnegative.")
    policy = value["settings"].get("policy", "risk_ranked")
    if policy not in {"random", "population_proportional", "risk_ranked", "risk", UNREPORTED_POLICY}:
        raise ValueError("Unknown frozen allocation policy.")
    ids, assigned, counts = set(), set(), {}
    for slot in value["slots"]:
        rid, fid = slot["current_resident_id"], slot["facility_id"]
        if slot.get("status", "reserved") != "reserved" or rid != slot["original_resident_id"]:
            raise ValueError("A new round must contain original, reserved assignments only.")
        if slot["slot_id"] in ids or rid in assigned or rid not in residents or fid not in facilities:
            raise ValueError("Approved slots need unique IDs and unique, known residents and service points.")
        ids.add(slot["slot_id"])
        assigned.add(rid)
        if residents[rid]["municipality"] != slot["municipality"]:
            raise ValueError("The slot municipality must match its original resident.")
        distance = residents[rid].get("candidate_distances_km", {}).get(fid)
        if distance is None or not math.isfinite(float(distance)) or float(distance) > limit:
            raise ValueError("An approved slot exceeds its frozen access limit.")
        if slot.get("ordering_basis") not in {"priority", "random", "unreported"}:
            raise ValueError("Every slot needs an explicit frozen ordering basis.")
        reason = slot.get("selection_reason", slot.get("original_reason"))
        route, basis = _reason_route(reason, policy)
        if slot.get("selection_route") != route or slot["ordering_basis"] != basis:
            raise ValueError("A slot's route and ordering basis must match its original allocation reason.")
        if slot.get("original_reason", reason) != reason:
            raise ValueError("The original allocation reason cannot be rewritten.")
        slot["distance_km"] = float(distance)
        counts[fid] = counts.get(fid, 0) + 1
    if len(value["slots"]) > int(value["settings"]["budget"]):
        raise ValueError("Approved assignments exceed the panel budget.")
    if any(count > int(facilities[fid]["capacity"]) for fid, count in counts.items()):
        raise ValueError("Approved assignments exceed a frozen service-point capacity.")
    reports = {}
    for rid, report in value.get("applied_reports", {}).items():
        if rid not in residents:
            raise ValueError("An applied report references a resident outside this round.")
        # Historical valid reports keep their recorded date after reopening a round.
        submitted = _date(report.get("DATE"), "Report date") if report.get("DATE") else _today()
        normalized, errors = normalize_report(rid, residents[rid].get("age"), report, submitted=submitted)
        if errors or normalized["age"] != report.get("age") or report.get("resident_id") != rid:
            raise ValueError("Invalid applied report in approved snapshot: " + " ".join(errors))
        reports[rid] = normalized
    value["applied_reports"] = reports
    # The experiment manifest may contain extensive evaluation metadata; copy only
    # provenance, never arbitrary nested dictionaries from an external payload.
    prov_fields = {"run_id", "config_hash", "source_hash", "input_hash", "input_checksums", "git_commit", "started_utc"}
    value["provenance"] = {k: v for k, v in value.get("provenance", {}).items() if k in prov_fields}
    if value["provenance"].get("run_id", value["run_id"]) != value["run_id"]:
        raise ValueError("The snapshot and its original provenance must reference the same run.")
    json.dumps(value, allow_nan=False)
    return value


validate_snapshot = normalize_snapshot


def _today():
    return datetime.now(MANILA).date()


def _date(value, label, future=True):
    try:
        if isinstance(value, datetime):
            value = value.date()
        parsed = value if isinstance(value, date) else date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a date written YYYY-MM-DD.") from None
    if not future and parsed > _today():
        raise ValueError(f"{label} cannot be in the future.")
    return parsed


def _text(value, label="Text", required=False):
    result = "" if value is None else str(value).strip()
    if len(result) > 4000:
        raise ValueError(f"{label} must be at most 4,000 characters.")
    if required and not result:
        raise ValueError(f"{label} is required.")
    return result


def _events(events):
    rows = _rows(events)
    # Sequence is recording order; occurrence times can be backdated by staff.
    return sorted(enumerate(rows), key=lambda pair: (pair[1].get("sequence", pair[0]), pair[0]))


def _state(snapshot, slots, events):
    residents = {r["resident_id"]: r for r in snapshot["residents"]}
    states = {}
    reports = dict(snapshot.get("applied_reports", {}))
    for _, event in _events(events):
        if event.get("event_type") == "report_applied":
            payload = event.get("payload") or {}
            reports[event.get("resident_id")] = payload.get("report", payload)

    def assigned(rid, slot):
        if rid in residents and rid not in states:
            states[rid] = dict(resident=residents[rid], slot=dict(slot), contact_outcome="", started=False,
                               panel_complete=False, screening_flag=None, creatinine=None, uacr=None,
                               egfr=None, specimen_date=None, result_reference="", review_open=False,
                               followup_open=False, review_disposition="", next_action="", due_on="",
                               owner="", last_activity="", report=reports.get(rid), latest_result_event_id=None,
                               results_communicated=False, referral_status="", referral_destination="",
                               referral_open=False, no_answer_count=0)
    for slot in snapshot["slots"]:
        assigned(slot["original_resident_id"], slot)
    for _, event in _events(events):
        rid, kind = event.get("resident_id"), event.get("event_type")
        payload = event.get("payload", event.get("payload_json", {})) or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        if kind == "replacement":
            replacement_id = payload.get("resident_id", rid)
            match = next((s for s in _rows(slots) if s["slot_id"] == event.get("slot_id")), None)
            if match:
                assigned(replacement_id, match)
        if rid not in states:
            continue
        state = states[rid]
        if kind not in {"round_created", "round_archived", "report_attempt"}:
            state["last_activity"] = event.get("recorded_at", event.get("recorded_at_utc", ""))
        if kind == "contact":
            state["contact_outcome"] = payload.get("outcome", "")
            state["no_answer_count"] += state["contact_outcome"] == "No answer"
            # Contact updates have their own audit payload. They must not replace
            # the action/deadline of an unfinished clinical follow-up task.
            if not state["followup_open"]:
                if state["contact_outcome"] in {"Accepted"} | RELEASING_OUTCOMES:
                    state["next_action"], state["due_on"] = "", ""
                for name in ("due_on", "next_action"):
                    if name in payload:
                        state[name] = payload[name] or ""
        elif kind in {"specimen", "specimen_collected"}:
            state["started"] = True
            state["specimen_date"] = payload.get("specimen_date")
            if not state["followup_open"]:
                state["next_action"], state["due_on"] = "", ""
        elif kind in {"result", "result_recorded"}:
            state["started"] = True
            state["latest_result_event_id"] = event.get("event_id")
            for name in ("creatinine", "uacr", "egfr", "specimen_date", "result_reference", "panel_complete", "screening_flag"):
                if name in payload:
                    state[name] = payload[name]
            # A correction cannot implicitly close a review that was opened.
            if state["screening_flag"] is True or (state["creatinine"] is not None and state["egfr"] is None):
                state["review_open"] = True
                if not state["followup_open"]:
                    state["next_action"], state["due_on"] = "", ""
            elif state["panel_complete"] and not state["review_open"] and not state["followup_open"]:
                # An assignment describes the current queue's work. Finishing
                # that work closes its generic instruction and deadline.
                state["next_action"], state["due_on"] = "", ""
        elif kind == "review":
            state["review_disposition"] = payload.get("disposition", "")
            state["review_open"] = False
            if payload.get("disposition") == "Follow-up requested":
                state["followup_open"] = True
                state["next_action"], state["due_on"] = payload["next_action"], payload["due_on"]
            elif not state["followup_open"]:
                state["next_action"], state["due_on"] = "", ""
        elif kind == "followup_complete":
            state["followup_open"] = False
            state["next_action"], state["due_on"] = "", ""
        elif kind == "assignment":
            for name in ("owner", "due_on", "next_action"):
                if name in payload:
                    state[name] = payload[name] or ""
        elif kind == "report_applied":
            state["report"] = payload.get("report", payload)
        elif kind == "communication":
            state["results_communicated"] = True
        elif kind == "referral":
            state["referral_status"] = payload.get("status", "")
            state["referral_destination"] = payload.get("destination") or state["referral_destination"]
            state["referral_open"] = state["referral_status"] in OPEN_REFERRAL
    for slot in _rows(slots):
        rid = slot.get("current_resident_id")
        if rid in residents:
            assigned(rid, slot)
            states[rid]["slot"] = dict(slot)
    return states


def project_worklist(snapshot, slots, events):
    """Project only recorded operational work, retaining replaced residents."""
    slot_rows = _rows(slots)
    slots_by_id = {s["slot_id"]: s for s in slot_rows}
    last_holders = {s["slot_id"]: s["original_resident_id"] for s in snapshot["slots"]}
    for _, event in _events(events):
        if event.get("event_type") == "replacement":
            last_holders[event.get("slot_id")] = (event.get("payload") or {}).get("resident_id", event.get("resident_id"))
    current = {s.get("current_resident_id"): s for s in slot_rows
               if s.get("status", s.get("state", "reserved")) != "released"}
    states = _state(snapshot, slot_rows, events)
    output = []
    for rid, state in states.items():
        resident, slot = state["resident"], state["slot"]
        is_current = rid in current
        # An abnormal flag is not finished at review: the resident must hear the reviewed result,
        # and a referral stays open until attendance or an unknown outcome is recorded.
        communication_needed = (state["screening_flag"] is True and bool(state["review_disposition"])
                                and not state["results_communicated"])
        review_open = state["review_open"] or state["followup_open"] or communication_needed or state["referral_open"]
        declined = state["contact_outcome"] in RELEASING_OUTCOMES or not is_current
        if review_open:
            review_action = "Review screening flag"
            if state["egfr"] is None and state["creatinine"] is not None and state["screening_flag"] is not True:
                review_action = "Review unavailable eGFR calculation"
            elif state["screening_flag"] is False:
                review_action = "Review corrected screening results"
            if state["review_open"]:
                pending = review_action
            elif communication_needed:
                pending = "Explain reviewed results to resident"
            elif state["referral_open"]:
                pending = ("Confirm referral attendance" if state["referral_status"] == "Sent"
                           else "Follow up missed referral")
            else:
                pending = "Complete follow-up task"
            queue, default_action = QUEUES[2], pending
        elif declined:
            queue, default_action = QUEUES[4], "No active invitation"
        elif state["panel_complete"]:
            queue, default_action = QUEUES[3], "Recorded tasks complete"
        elif state["contact_outcome"] == "Accepted" or state["started"]:
            queue, default_action = QUEUES[1], "Complete missing panel results" if state["started"] else "Record screening visit"
        else:
            queue, default_action = QUEUES[0], "Contact resident"
        reported = bool(resident.get("reported")) or bool(state["report"])
        report_status = "Questionnaire available" if reported else "No questionnaire"
        reason = slot.get("selection_reason", slot.get("original_reason", ""))
        distance = resident.get("candidate_distances_km", {}).get(slot["facility_id"])
        row = dict(resident_id=rid, municipality=resident.get("municipality"), reported=reported,
                   report_status=report_status, questionnaire_status=report_status, queue=queue, status=queue,
                   next_action=(default_action if state["review_open"] or queue == QUEUES[3]
                                or (queue == QUEUES[2] and not state["followup_open"])
                                else state["next_action"] or default_action),
                   due_on="" if queue == QUEUES[3] else state["due_on"], owner=state["owner"],
                   contact_outcome=state["contact_outcome"], panel_complete=state["panel_complete"],
                   screening_flag=state["screening_flag"], creatinine=state["creatinine"], uacr=state["uacr"],
                   egfr=state["egfr"], specimen_date=state["specimen_date"], result_reference=state["result_reference"],
                   slot_id=slot["slot_id"], slot_state=slots_by_id.get(slot["slot_id"], slot).get("status", "reserved"),
                   is_current=is_current, facility_id=slot["facility_id"], selection_reason=reason, reason=reason,
                   selection_route=slot.get("selection_route", ""), ordering_basis=slot.get("ordering_basis", ""),
                   last_activity=state["last_activity"], review_open=review_open, review_disposition=state["review_disposition"],
                   followup_open=state["followup_open"], original_resident_id=slot.get("original_resident_id"),
                   assigned_distance_km=distance, started=state["started"], age=resident.get("age"), female=resident.get("female"),
                   latest_result_event_id=state["latest_result_event_id"], review_pending=state["review_open"],
                   results_communicated=state["results_communicated"], communication_needed=communication_needed,
                   referral_status=state["referral_status"], referral_destination=state["referral_destination"],
                   referral_open=state["referral_open"], no_answer_count=state["no_answer_count"],
                   slot_available_for_replacement=(slots_by_id.get(slot["slot_id"], slot).get("status") == "released"
                                                   and last_holders.get(slot["slot_id"]) == rid))
        output.append(row)
    return pd.DataFrame(output, columns=WORKLIST_COLUMNS)


def _number(value, label, positive):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, bool):
            raise ValueError()
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0 or (positive and numeric == 0):
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{label} must be finite and {'greater than zero' if positive else 'nonnegative'}.") from None
    return numeric


def normalize_event(snapshot, slots, events, resident_id, event_type, payload, occurred_at=None):
    """Validate a staff event against current persisted state; return safe payload."""
    if event_type not in EVENT_TYPES:
        raise ValueError("Unsupported workflow event.")
    if not isinstance(payload, dict):
        raise ValueError("Event payload must be an object.")
    residents = {row["resident_id"]: row for row in snapshot["residents"]}
    if resident_id not in residents:
        raise ValueError("Choose a resident from this approved round.")
    resident = residents[resident_id]
    if event_type in {"report_applied", "report_attempt"}:
        if event_type == "report_attempt":
            errors = payload.get("errors", [])
            if not isinstance(errors, list) or any(not isinstance(e, str) for e in errors):
                raise ValueError("Report errors must be a list of messages.")
            report = payload.get("payload")
            if report is not None:
                if not isinstance(report, dict):
                    raise ValueError("A report attempt must contain a report object or null.")
                # Invalid submissions may retain only the report schema, never arbitrary fields.
                report = {k: _plain(v) for k, v in report.items() if k in {"resident_id", "age", "DM", "HTN", "FAM", "OUT", "PRIOR", "HRS", "DATE"}}
            return dict(payload=report, errors=[_text(e) for e in errors], channel=_text(payload.get("channel", "form")),
                        raw_text=None if payload.get("raw_text") is None else _text(payload["raw_text"]))
        report = payload.get("report", payload)
        normalized, errors = normalize_report(resident_id, resident.get("age"), report, submitted=_today())
        if report.get("resident_id") != resident_id or report.get("age") != resident.get("age"):
            errors.append("Report ID and known adult age must match the round.")
        if errors:
            raise ValueError(" ".join(errors))
        return normalized
    states = _state(snapshot, slots, events)
    if resident_id not in states:
        raise ValueError("This resident has not received an invitation in the round.")
    state = states[resident_id]
    current = next((slot for slot in _rows(slots) if slot.get("current_resident_id") == resident_id
                    and slot.get("status", slot.get("state")) != "released"), None)
    if current is None:
        raise ValueError("This invitation is no longer active.")
    completed = state["panel_complete"] and not state["review_open"] and not state["followup_open"]
    clean = {}
    if "note" in payload:
        clean["note"] = _text(payload["note"], "Note")
    if event_type == "contact":
        if completed:
            raise ValueError("This case has no open task. New contact activity is unavailable for a completed case.")
        outcomes = {v.casefold(): v for v in ("No answer", "Retry requested", "Accepted", *sorted(RELEASING_OUTCOMES))}
        outcome = outcomes.get(str(payload.get("outcome", "")).strip().casefold())
        if outcome is None:
            raise ValueError("Choose a supported contact outcome.")
        if outcome in RELEASING_OUTCOMES and (state["started"] or current.get("status") == "started"):
            raise ValueError("A slot cannot be released after specimen collection or testing starts.")
        attempts = int(snapshot["settings"].get("unreachable_after_attempts", DEFAULT_UNREACHABLE_AFTER))
        if outcome == "Unreachable" and state["no_answer_count"] < attempts:
            raise ValueError(f"Record at least {attempts} unanswered contact attempts before marking the resident unreachable.")
        clean["outcome"] = outcome
        for key in ("next_action", "due_on"):
            if key in payload:
                clean[key] = (_date(payload[key], "Due date").isoformat() if payload[key] else "") if key == "due_on" else _text(payload[key])
    elif event_type in {"specimen", "result"}:
        specimen = _date(payload.get("specimen_date"), "Specimen date", future=False).isoformat()
        if state["specimen_date"] and state["specimen_date"] != specimen:
            raise ValueError("This round has one screening episode; amend results for the same specimen date.")
        clean["specimen_date"] = specimen
        if event_type == "result":
            creatinine = _number(payload.get("creatinine", state["creatinine"]), "Creatinine", True)
            uacr = _number(payload.get("uacr", state["uacr"]), "uACR", False)
            if creatinine is None and uacr is None:
                raise ValueError("Record at least one laboratory component.")
            if payload.get("creatinine_unit", "mg/dL") != "mg/dL" or payload.get("uacr_unit", "mg/g") != "mg/g":
                raise ValueError("Supported units are creatinine mg/dL and uACR mg/g.")
            age, female = resident.get("age"), resident.get("female")
            egfr = None
            if creatinine is not None and age is not None and female is not None:
                try:
                    valid_age = math.isfinite(float(age)) and 18 <= float(age) <= 110
                    valid_sex = female in (False, True, 0, 1)
                    if valid_age and valid_sex:
                        egfr = float(ckd_epi_2021(creatinine, float(age), bool(female)))
                except (TypeError, ValueError):
                    pass
            thresholds = snapshot["settings"]["outcome"]
            flag = float(observed_screen_label(egfr if egfr is not None else np.nan,
                                              uacr if uacr is not None else np.nan,
                                              thresholds["egfr_threshold"], thresholds["uacr_threshold"]))
            clean.update(creatinine=creatinine, uacr=uacr, creatinine_unit="mg/dL", uacr_unit="mg/g", egfr=egfr,
                         panel_complete=creatinine is not None and uacr is not None,
                         screening_flag=bool(flag) if math.isfinite(flag) else None,
                         result_reference=_text(payload.get("result_reference", state["result_reference"]), "Result reference"))
            latest_result = state["latest_result_event_id"]
            if payload.get("supersedes_event_id") not in {None, latest_result}:
                raise ValueError("Amend the latest saved result revision; reload the case.")
            if latest_result:
                clean["supersedes_event_id"] = latest_result
    elif event_type == "review":
        disposition = payload.get("disposition")
        if disposition not in {"Complete", "Follow-up requested"}:
            raise ValueError("Choose Complete or Follow-up requested.")
        if not state["started"]:
            raise ValueError("Record screening activity before a review.")
        clean["disposition"] = disposition
        if disposition == "Follow-up requested":
            clean["next_action"] = _text(payload.get("next_action"), "Next action", required=True)
            clean["due_on"] = _date(payload.get("due_on"), "Due date").isoformat()
    elif event_type == "communication":
        if state["latest_result_event_id"] is None:
            raise ValueError("Record screening results before recording that they were explained.")
        method = payload.get("method")
        if method not in COMMUNICATION_METHODS:
            raise ValueError("Choose how the results were explained.")
        clean.update(method=method, explained_by=_text(payload.get("explained_by"), "Explained by", required=True))
    elif event_type == "referral":
        if not state["started"]:
            raise ValueError("Record screening activity before a referral.")
        status = payload.get("status")
        if status not in REFERRAL_STATUSES:
            raise ValueError("Choose a supported referral status.")
        destination = _text(payload.get("destination"), "Referral destination")
        if status == "Sent" and not destination:
            raise ValueError("Name where the resident was referred.")
        if status != "Sent" and not state["referral_status"]:
            raise ValueError("Record the referral as sent before recording its outcome.")
        clean.update(status=status, destination=destination)
    elif event_type == "followup_complete":
        if not state["followup_open"]:
            raise ValueError("There is no open follow-up task to complete.")
    elif event_type == "assignment":
        clean["owner"] = _text(payload.get("owner"), "Demo staff owner", required=True)
        if completed:
            if _text(payload.get("next_action")) or payload.get("due_on"):
                raise ValueError("This case has no open task. Completed cases allow owner changes only.")
            return _plain(clean)
        if "next_action" in payload:
            clean["next_action"] = _text(payload["next_action"])
        if "due_on" in payload:
            clean["due_on"] = _date(payload["due_on"], "Due date").isoformat() if payload["due_on"] else ""
    return _plain(clean)


validate_event = normalize_event


def replacement_candidate(snapshot, slots, events, slot_id):
    """Propose the next never-assigned resident in the slot's frozen route order."""
    slot_rows = _rows(slots)
    slot = next((row for row in slot_rows if row["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown screening slot.")
    if slot.get("status", slot.get("state")) != "released":
        raise ValueError("Only explicitly released, unused slots can be recovered.")
    ever_assigned = set(_state(snapshot, slot_rows, events))
    # Include metadata even if older persistence versions did not record a replacement event.
    for row in slot_rows:
        ever_assigned.update(r for r in (row.get("original_resident_id"), row.get("current_resident_id")) if r)
    for _, event in _events(events):
        if event.get("event_type") == "contact" and (event.get("payload") or {}).get("outcome") in RELEASING_OUTCOMES:
            ever_assigned.add(event.get("resident_id"))
    residents = {row["resident_id"]: row for row in snapshot["residents"]}
    basis = slot["ordering_basis"]
    facility, municipality = slot["facility_id"], slot["municipality"]
    limit = snapshot["settings"]["max_distance_km"]
    # Unreported outreach follows the frozen priority order among residents without a questionnaire at approval.
    for rid in snapshot["orders"]["priority" if basis == "unreported" else basis]:
        candidate = residents[rid]
        distance = candidate.get("candidate_distances_km", {}).get(facility)
        if rid in ever_assigned or candidate["municipality"] != municipality:
            continue
        if basis == "unreported" and candidate.get("reported"):
            continue
        if candidate.get("reported_known_ckd"):
            continue
        if distance is None or not math.isfinite(float(distance)) or not 0 <= float(distance) <= limit:
            continue
        return dict(slot_id=slot_id, resident_id=rid, facility_id=facility, municipality=municipality,
                    distance_km=float(distance), selection_reason=slot.get("selection_reason", slot.get("original_reason", "")),
                    selection_route=slot["selection_route"], ordering_basis=basis, selection_basis=basis,
                    slot_version=int(slot.get("version", 0)))
    return None
