"""Shared form/SMS validation and append-only synthetic report revisions."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

SCHEMA_VERSION = 2
FIELDS = ("DM", "HTN", "FAM", "OUT", "PRIOR")  # Y, N or U; omitted = not answered (None)
HOURS_MAX = 168  # outdoor hours over the 7 days ending on the event date
MAX_EVENT_LAG_DAYS = 30
KEYS = FIELDS + ("HRS", "DATE")


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def normalize_report(resident_id, age, answers, submitted: date | None = None, max_lag_days=MAX_EVENT_LAG_DAYS):
    """Validate one report (schema v2). Omitted answers stay None, distinct from 'U' and 'N'."""
    submitted = submitted or date.today()
    errors = []
    if not re.fullmatch(r"SYN-[A-Z0-9-]{1,32}", str(resident_id)):
        errors.append("Use a synthetic ID starting SYN-; do not enter names or phone numbers.")
    try:
        numeric = float(age)
        parsed_age = int(numeric)
        if numeric != parsed_age or not 18 <= parsed_age <= 110:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        parsed_age = None
        errors.append("Age must be a whole number from 18 to 110.")
    values = {}
    for field in FIELDS:
        raw = answers.get(field)
        if _blank(raw):
            values[field] = None
            continue
        value = str(raw).strip().upper()
        if value not in ("Y", "N", "U"):
            errors.append(f"{field}: use Y, N or U, or leave it out.")
        values[field] = value
    hours = answers.get("HRS")
    if _blank(hours):
        hours = None
    elif str(hours).strip().upper() == "U":
        hours = "U"
    elif re.fullmatch(r"\d{1,3}", str(hours).strip()) and int(str(hours).strip()) <= HOURS_MAX:
        hours = int(str(hours).strip())
    else:
        errors.append(f"HRS: outdoor hours in the last 7 days must be a whole number from 0 to {HOURS_MAX}, or U.")
    if values["OUT"] == "N" and isinstance(hours, int) and hours > 0:
        errors.append("HRS: outdoor hours must be 0 when OUT is N.")
    event_date = answers.get("DATE")
    if _blank(event_date):
        event_date = submitted.isoformat()
    else:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(event_date).strip()):
                raise ValueError()
            parsed = date.fromisoformat(str(event_date).strip())
            if parsed > submitted:
                errors.append("DATE: the event date cannot be after the submission date.")
            elif parsed < submitted - timedelta(days=max_lag_days):
                errors.append(f"DATE: the event date must be within {max_lag_days} days before submission.")
            event_date = parsed.isoformat()
        except ValueError:
            errors.append("DATE: use a real date written YYYY-MM-DD.")
    payload = {"resident_id": str(resident_id), "age": parsed_age, **values, "HRS": hours, "DATE": event_date}
    return payload, errors


def parse_sms(text, submitted: date | None = None):
    tokens = text.strip().upper().split()
    if len(tokens) < 3 or tokens[0] != "AGAP":
        return None, ["Format: AGAP SYN-DEMO 45 DM:Y HTN:N FAM:U OUT:Y PRIOR:N HRS:12 DATE:2026-10-15"]
    answers = {}
    for token in tokens[3:]:
        if token.count(":") != 1:
            return None, [f"Invalid token: {token}"]
        key, value = token.split(":")
        if key not in KEYS or key in answers:
            return None, [f"Unknown or duplicate field: {key}"]
        answers[key] = value
    return normalize_report(tokens[1], tokens[2], answers, submitted)


def record_resident_id(record):
    """Resolve both current envelopes and legacy payload-only report records."""
    return record.get("resident_id") or (record.get("payload") or {}).get("resident_id")


def resident_history(path: Path, resident_id):
    if not path.exists():
        return []
    return [record for line in path.read_text().splitlines() if line.strip()
            and record_resident_id(record := json.loads(line)) == resident_id]


def _attempt_fingerprint(resident_id, payload, errors):
    return hashlib.sha256(json.dumps(dict(resident_id=resident_id, payload=payload, errors=errors),
                                     sort_keys=True).encode()).hexdigest()


def append_report(path: Path, payload, errors, channel, resident_id=None, raw_text=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    history = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    resident = (payload or {}).get("resident_id") or resident_id
    fingerprint = _attempt_fingerprint(resident, payload, errors)
    previous = [r for r in history if record_resident_id(r) == resident] if resident else []
    # Recompute legacy fingerprints using the new envelope; channel and raw
    # formatting do not distinguish equivalent normalized submissions.
    if previous and _attempt_fingerprint(resident, previous[-1].get("payload"), previous[-1].get("errors", [])) == fingerprint:
        return previous[-1], False
    valid_previous = [r for r in previous if r.get("valid")]
    now = datetime.now(timezone.utc).isoformat()
    # E1-08: event_at is the reported event date; available_at is when the report arrived.
    record = dict(report_id=f"REPORT-{len(history) + 1:06d}", resident_id=resident, payload=payload, errors=errors,
                  valid=not errors, channel=channel, available_at=now, schema_version=SCHEMA_VERSION,
                  event_at=payload.get("DATE") if payload else None,
                  supersedes=valid_previous[-1]["report_id"] if not errors and valid_previous else None,
                  previous_attempt_id=previous[-1]["report_id"] if previous else None,
                  raw_text=raw_text, fingerprint=fingerprint)
    # One local demo process writes reports. Concurrent multi-user storage is future work.
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record, True


def reports_at(path: Path, cutoff):
    latest = {}
    if path.exists():
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record["valid"] and record["available_at"] <= cutoff:
                latest[record_resident_id(record)] = record
    return list(latest.values())
