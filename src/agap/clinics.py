"""Evidence-backed clinic verification, separate from simulated service points.

Register membership supplies an identity only. Team-entered facts keep their
source/date; append-only SQLite revisions make local concurrent saves atomic.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pandas as pd

CAPABILITIES = ("Not checked", "Available", "Unavailable")
FIELDS = ("latitude", "longitude", "creatinine", "uacr", "capacity_panels", "checked_on", "evidence_source", "notes")
REGISTER_ID = "YAKAP-20260930"


def clinic_catalogue(path):
    frame = pd.read_csv(path)
    if frame.source_row.duplicated().any() or frame.facility_name.isna().any():
        raise ValueError("Clinic source rows must be unique and named.")
    frame["facility_id"] = REGISTER_ID + "-" + frame.source_row.astype(int).astype(str)
    return frame[["facility_id", "facility_name", "source_page"]].copy()


def normalize_verification(details, today=None):
    today = today or datetime.now(ZoneInfo("Asia/Manila")).date()
    output = {"evidence_source": str(details.get("evidence_source") or "").strip(),
              "notes": str(details.get("notes") or "").strip()}
    for field, low, high in (("latitude", -90, 90), ("longitude", -180, 180)):
        raw = details.get(field)
        try:
            value = None if raw is None or str(raw).strip() == "" else float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field.title()} must be a valid decimal-degree coordinate.") from exc
        if isinstance(raw, bool):
            raise ValueError(f"{field.title()} must be a valid decimal-degree coordinate.")
        if value is not None and (not math.isfinite(value) or not low <= value <= high):
            raise ValueError(f"{field.title()} must be a valid decimal-degree coordinate.")
        output[field] = value
    if (output["latitude"] is None) != (output["longitude"] is None):
        raise ValueError("Provide both coordinates, or leave both blank until checked.")
    for field in ("creatinine", "uacr"):
        output[field] = details.get(field, "Not checked")
        if output[field] not in CAPABILITIES:
            raise ValueError(f"Unknown {field} availability status.")
    raw = details.get("capacity_panels")
    try:
        capacity = None if raw is None or str(raw).strip() == "" else float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Capacity must be a whole number of complete screening panels.") from exc
    if capacity is not None and (isinstance(raw, bool) or not math.isfinite(capacity) or capacity < 0 or not capacity.is_integer()):
        raise ValueError("Capacity must be a nonnegative whole number of complete panels per screening round.")
    output["capacity_panels"] = int(capacity) if capacity is not None else None
    if capacity and (output["creatinine"] != "Available" or output["uacr"] != "Available"):
        raise ValueError("A positive complete-panel capacity requires both creatinine and uACR to be confirmed available.")
    raw_date = details.get("checked_on")
    try:
        checked = date.fromisoformat(str(raw_date)) if raw_date else None
    except ValueError as exc:
        raise ValueError("Choose a valid verification date.") from exc
    if checked and checked > today:
        raise ValueError("The verification date cannot be in the future.")
    # An empty/draft entry cannot turn a register listing into verification.
    facts = output["latitude"] is not None or capacity is not None or any(output[field] != "Not checked" for field in ("creatinine", "uacr"))
    if not facts:
        raise ValueError("Record at least one checked fact; unknown entries already remain in the queue.")
    if not checked or not output["evidence_source"]:
        raise ValueError("Checked facts require an evidence source and verification date.")
    if len(output["evidence_source"]) > 1000 or len(output["notes"]) > 3000:
        raise ValueError("Keep the source below 1,000 characters and notes below 3,000.")
    output["checked_on"] = checked.isoformat()
    output["capacity_unit"] = "complete screening panels per screening round"
    return output


def _event(row):
    identity, facility_id, timestamp, payload, fingerprint, previous = row
    return dict(record_id=f"CLINIC-{identity:06d}", facility_id=facility_id, available_at=timestamp,
                payload=json.loads(payload), fingerprint=fingerprint,
                supersedes=f"CLINIC-{previous:06d}" if previous else None)


def read_verifications(path):
    if not Path(path).exists():
        return []
    with closing(sqlite3.connect(path)) as connection:
        return [_event(row) for row in connection.execute("SELECT * FROM clinic_verifications ORDER BY id")]


def save_verification(path, catalogue, facility_id, details, today=None):
    if facility_id not in set(catalogue.facility_id):
        raise ValueError("Choose a facility from the source register.")
    payload = normalize_verification(details, today)
    serialized = json.dumps(payload, sort_keys=True, allow_nan=False)
    fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=10)) as connection, connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS clinic_verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, facility_id TEXT NOT NULL,
            available_at TEXT NOT NULL, payload TEXT NOT NULL, fingerprint TEXT NOT NULL, previous_id INTEGER)""")
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute("SELECT * FROM clinic_verifications WHERE facility_id=? ORDER BY id DESC LIMIT 1", (facility_id,)).fetchone()
        if previous and previous[4] == fingerprint:
            return _event(previous), False
        timestamp = datetime.now(timezone.utc).isoformat()
        cursor = connection.execute("INSERT INTO clinic_verifications (facility_id,available_at,payload,fingerprint,previous_id) VALUES (?,?,?,?,?)",
                                    (facility_id, timestamp, serialized, fingerprint, previous[0] if previous else None))
        return _event((cursor.lastrowid, facility_id, timestamp, serialized, fingerprint, previous[0] if previous else None)), True


def verification_queue(catalogue, history):
    latest = {record["facility_id"]: record for record in history}
    rows = []
    for clinic in catalogue.to_dict("records"):
        record = latest.get(clinic["facility_id"])
        payload = record["payload"] if record else {}
        row = dict(clinic, **{field: payload.get(field) for field in FIELDS})
        for field in ("creatinine", "uacr"):
            row[field] = row[field] or "Not checked"
        missing = []
        if row["latitude"] is None:
            missing.append("coordinates")
        for field in ("creatinine", "uacr"):
            if row[field] != "Available":
                missing.append(field)
        if not row["capacity_panels"]:
            missing.append("positive complete-panel capacity")
        if not row["checked_on"] or not row["evidence_source"]:
            missing.append("dated evidence")
        row["status"] = "Unverified" if not record else "Ready for pilot review" if not missing else "Needs verification"
        row["remaining_checks"] = "; ".join(missing)
        row["latest_record"] = record["record_id"] if record else None
        rows.append(row)
    return pd.DataFrame(rows)
