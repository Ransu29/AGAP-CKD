"""Plain presentation facts derived solely from recorded coordination state."""
from __future__ import annotations

import pandas as pd


def _present(value):
    return value is not None and not bool(pd.isna(value)) and value != ""


def case_progress(person):
    """Describe each recorded stage without inferring contact or clinical clearance."""
    contact = person.get("contact_outcome")
    specimen = person.get("specimen_date")
    components = sum(_present(person.get(name)) for name in ("creatinine", "uacr"))
    review_pending = bool(person.get("review_pending", False))
    followup_open = bool(person.get("followup_open", False))
    disposition = person.get("review_disposition")
    if review_pending:
        review, review_state = "Review open", "open"
    elif followup_open:
        review, review_state = "Follow-up open", "open"
    elif disposition == "Complete":
        review, review_state = "Review complete", "recorded"
    elif disposition == "Follow-up requested":
        review, review_state = "Follow-up complete", "recorded"
    else:
        review, review_state = "No review task open", "pending"
    panel = f"{components} of 2 recorded"
    if components == 1:
        panel += " · incomplete"
    return [
        dict(stage="Contact", detail=str(contact) if _present(contact) else "Not recorded",
             state="recorded" if _present(contact) else "pending"),
        dict(stage="Specimen", detail=f"Recorded {specimen}" if _present(specimen) else "Not recorded",
             state="recorded" if _present(specimen) else "pending"),
        dict(stage="Panel", detail=panel, state="recorded" if components == 2 else "pending"),
        dict(stage="Review / follow-up", detail=review, state=review_state),
    ]


def action_receipt(event, person):
    """Name a committed action and its resulting operational queue."""
    kind, payload = event["event_type"], event.get("payload", {})
    if kind == "contact":
        action = f"Contact {payload['outcome'].lower()} saved"
    elif kind == "specimen":
        action = "Specimen collection saved; this slot has started"
    elif kind == "result":
        components = sum(_present(payload.get(name)) for name in ("creatinine", "uacr"))
        action = f"Panel results saved · {components} of 2 components recorded"
    elif kind == "review":
        action = "Follow-up requested" if payload["disposition"] == "Follow-up requested" else "Review completed"
    elif kind == "followup_complete":
        action = "Follow-up task completed"
    elif kind == "communication":
        action = "Results explained to the resident"
    elif kind == "referral":
        action = f"Referral {payload['status'].lower()} saved"
    else:
        action = "Owner and task details saved"
    return f"{action}. Now {person['queue'].lower()}."


def recovery_facts(snapshot, person, proposal, slots, worklist):
    """Expose the proposal's saved checks and the effect of filling one slot.

    Proposal selection and transaction validation remain in the domain/store.
    These facts do not rank candidates or change any approved assignment.
    """
    candidate = next(row for row in snapshot["residents"] if row["resident_id"] == proposal["resident_id"])
    slot = next(row for row in slots if row["slot_id"] == person["slot_id"])
    facility = next(row for row in snapshot["facilities"] if row["facility_id"] == slot["facility_id"])
    distance = candidate["candidate_distances_km"][slot["facility_id"]]
    limit = float(snapshot["settings"]["max_distance_km"])
    active = [row for row in slots if row["status"] in {"reserved", "started"}]
    assigned = set(worklist.resident_id.astype(str))
    checks = [
        ("Declined or unreachable before testing", person.get("contact_outcome") in {"Declined", "Withdrawn", "Unreachable"}
         and not bool(person.get("started")) and slot["status"] == "released"),
        ("Same municipality", candidate["municipality"] == slot["municipality"] == proposal["municipality"]),
        ("Same service point", proposal["facility_id"] == slot["facility_id"]),
        (f"Within saved {limit:g} km access limit", 0 <= float(distance) <= limit),
        ("Never assigned in this round", proposal["resident_id"] not in assigned),
    ]
    if proposal["ordering_basis"] == "unreported":
        checks.append(("No questionnaire at approval", not candidate.get("reported")))
    facility_occupied = sum(row["facility_id"] == slot["facility_id"] for row in active)
    budget, capacity = int(snapshot["settings"]["budget"]), int(facility["capacity"])
    checks.append(("Capacity available", len(active) < budget and facility_occupied < capacity))
    basis = proposal["ordering_basis"]
    return dict(checks=checks, distance_km=float(distance), access_limit_km=limit,
                ordering_basis=basis,
                order_position=snapshot["orders"]["priority" if basis == "unreported" else basis].index(proposal["resident_id"]) + 1,
                round_occupied=len(active), budget=budget, facility_occupied=facility_occupied,
                facility_capacity=capacity, eligible=all(passed for _, passed in checks))
