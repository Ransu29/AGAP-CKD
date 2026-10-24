"""Citizen view content: the lean V3 profile (DATA_SPEC CI-01 to CI-05) and plain-language status.

A citizen never sees a model score, rank, other residents or result values. Profiles are
self-reported, stored in the synthetic namespace and never become verified diagnoses or
population prevalence. Guidance text is draft content pending clinician review.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from agap.workflow import QUEUES

SCHEMA_VERSION = 1
AGE_BANDS = ("18–29", "30–39", "40–49", "50–59", "60–69", "70+", "Unknown / not answered")
KIDNEY_STATES = ("No known CKD diagnosis", "Diagnosed CKD, not receiving dialysis", "Receiving dialysis",
                 "Unsure", "Not answered")
DIAGNOSIS_ANSWERS = ("Yes", "No", "Unsure", "Not answered")
QUESTIONS = {
    "reported_kidney_state": "What is your current known kidney status?",
    "reported_diagnosed_htn": "Have you ever been told by a qualified health professional that you have hypertension (high blood pressure)?",
    "reported_diagnosed_dm": "Have you ever been told by a qualified health professional that you have diabetes?",
}
NOT_A_DIAGNOSIS = ("This page gives general information only. It is not a diagnosis, a risk score or medical advice. "
                   "Your answers are self-reported and are not checked against medical records.")
DRAFT_CONTENT = "Draft content · pending clinician review"

# General health information by known state (V3-011). No individual risk statement is made.
GUIDANCE = {
    "No known CKD diagnosis": [
        "Early kidney disease usually has no symptoms. Many people only learn about it when their kidneys are already badly affected.",
        "A kidney check uses two tests: a blood test (creatinine, used to estimate kidney filtering, eGFR) and a urine test "
        "(albumin-to-creatinine ratio, uACR).",
        "High blood pressure and diabetes are the most common causes of kidney disease. If you have either, ask your health "
        "center whether a kidney check is right for you.",
        "Do not stop prescribed blood-pressure or diabetes medicines without first talking to a health worker or doctor.",
    ],
    "Diagnosed CKD, not receiving dialysis": [
        "Keep your regular check-ups and laboratory tests with your doctor; they show how your kidneys change over time.",
        "Bring your latest results and medicine list to each visit.",
        "Do not stop prescribed medicines without first talking to your doctor.",
    ],
    "Receiving dialysis": [
        "Keep your dialysis schedule. If you must miss a session, tell your dialysis center as early as possible.",
        "In hot months, follow the fluid advice your care team gives you. Drinking more than advised can make the next session harder on your heart.",
        "Bring your latest results to each appointment.",
    ],
    "Unsure": [
        "If you are not sure about your kidney status, ask your barangay health worker or rural health unit.",
        "A kidney check uses a blood test and a urine test; there is no reliable home test.",
    ],
    "Not answered": [
        "You can answer later. Leaving a question blank is always allowed.",
    ],
}

# Plain-language invitation status by recorded queue; never shows scores or result values.
STATUS_MESSAGES = {
    QUEUES[0]: "You are invited for a free kidney check. A health worker will contact you.",
    QUEUES[1]: "Your screening visit is arranged or in progress. A health worker will confirm any remaining steps.",
    QUEUES[2]: "Your results are with a health worker for review. They will contact you to explain the next step.",
    QUEUES[3]: "Your recorded screening tasks are complete. Ask your health center if you have questions about your results.",
    QUEUES[4]: "You have no active invitation in this round. You can still ask your health center about a kidney check.",
}
NO_INVITATION = ("You are not in the current screening round. Invitations are limited by available tests; "
                 "not being invited does not mean your kidneys are healthy.")


def normalize_profile(resident_id, answers):
    """Validate the lean profile; every question allows a blank/unknown answer."""
    options = {"age_band": AGE_BANDS, "reported_kidney_state": KIDNEY_STATES,
               "reported_diagnosed_htn": DIAGNOSIS_ANSWERS, "reported_diagnosed_dm": DIAGNOSIS_ANSWERS}
    errors, profile = [], {"resident_id": str(resident_id)}
    if not str(resident_id).startswith("SYN-"):
        errors.append("Use a synthetic demo profile; real people are not recorded here.")
    for field, allowed in options.items():
        value = answers.get(field) or allowed[-1]
        if value not in allowed:
            errors.append(f"{field}: choose one of the listed answers.")
        profile[field] = value
    municipality = str(answers.get("municipality_code") or "").strip()
    profile["municipality_code"] = municipality or "Unknown / not answered"
    return profile, errors


def append_profile(path: Path, profile, now=None):
    """Append one self-reported profile in the synthetic namespace; history is never rewritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(profile, namespace="synthetic", source_channel="citizen demo view", schema_version=SCHEMA_VERSION,
                  entered_at=(now or datetime.now(timezone.utc)).isoformat(), verified=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def latest_profile(path: Path, resident_id):
    if not path.exists():
        return None
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    rows = [row for row in rows if row.get("resident_id") == resident_id]
    return rows[-1] if rows else None


DIAGNOSED_STATES = ("Diagnosed CKD, not receiving dialysis", "Receiving dialysis")


def known_ckd_residents(path: Path):
    """Residents whose latest self-reported profile states a known CKD diagnosis (not verified)."""
    if not path.exists():
        return set()
    latest = {}
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            latest[row.get("resident_id")] = row.get("reported_kidney_state")
    return {resident for resident, state in latest.items() if state in DIAGNOSED_STATES}


def age_band(age):
    if age is None or age != age:
        return AGE_BANDS[-1]
    age = int(age)
    return "70+" if age >= 70 else next(band for band in AGE_BANDS[:-2] if int(band[:2]) <= age <= int(band[-2:]))


def invitation_message(case):
    """Status wording from a recorded worklist case (or None when not invited)."""
    if case is None:
        return NO_INVITATION
    return STATUS_MESSAGES.get(case.get("queue"), NO_INVITATION)
