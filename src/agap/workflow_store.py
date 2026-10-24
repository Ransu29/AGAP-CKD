"""Transactional local storage for explicitly recorded screening coordination.

The immutable experiment run is never edited.  This database contains operational
snapshots and append-only staff activity, not the simulator's hidden outcomes.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4


SCHEMA_VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data/reports/screening_workflow.sqlite3"


class WorkflowConflictError(ValueError):
    """The request conflicts with recorded activity; reload before retrying."""


class WorkflowStorageError(RuntimeError):
    """The local coordination database could not complete an operation."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS rounds (
    round_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    settings_json TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    archived_at_utc TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_round_per_run
    ON rounds (run_id) WHERE status = 'active';
CREATE TABLE IF NOT EXISTS round_residents (
    round_id TEXT NOT NULL,
    resident_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (round_id, resident_id),
    FOREIGN KEY (round_id) REFERENCES rounds (round_id)
);
CREATE TABLE IF NOT EXISTS slots (
    slot_id TEXT NOT NULL,
    round_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    municipality TEXT NOT NULL,
    selection_route TEXT NOT NULL,
    ordering_basis TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('reserved', 'started', 'released')),
    current_resident_id TEXT,
    original_resident_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    payload_json TEXT NOT NULL,
    PRIMARY KEY (round_id, slot_id),
    FOREIGN KEY (round_id) REFERENCES rounds (round_id),
    FOREIGN KEY (round_id, current_resident_id)
        REFERENCES round_residents (round_id, resident_id),
    FOREIGN KEY (round_id, original_resident_id)
        REFERENCES round_residents (round_id, resident_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_current_slot_per_resident
    ON slots (round_id, current_resident_id)
    WHERE current_resident_id IS NOT NULL AND status IN ('reserved', 'started');
CREATE TABLE IF NOT EXISTS workflow_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    request_id TEXT NOT NULL UNIQUE,
    request_fingerprint TEXT NOT NULL,
    round_id TEXT NOT NULL,
    resident_id TEXT,
    slot_id TEXT,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    occurred_at_utc TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    supersedes_event_id TEXT,
    FOREIGN KEY (round_id) REFERENCES rounds (round_id),
    FOREIGN KEY (round_id, resident_id)
        REFERENCES round_residents (round_id, resident_id),
    FOREIGN KEY (round_id, slot_id) REFERENCES slots (round_id, slot_id),
    FOREIGN KEY (supersedes_event_id) REFERENCES workflow_events (event_id)
);
CREATE INDEX IF NOT EXISTS events_by_round
    ON workflow_events (round_id, sequence);
CREATE INDEX IF NOT EXISTS events_by_resident
    ON workflow_events (round_id, resident_id, sequence);
CREATE TRIGGER IF NOT EXISTS events_cannot_update
BEFORE UPDATE ON workflow_events BEGIN
    SELECT RAISE(ABORT, 'Workflow history is append-only.');
END;
CREATE TRIGGER IF NOT EXISTS events_cannot_delete
BEFORE DELETE ON workflow_events BEGIN
    SELECT RAISE(ABORT, 'Workflow history is append-only.');
END;
CREATE TRIGGER IF NOT EXISTS round_snapshot_cannot_change
BEFORE UPDATE OF run_id, settings_json, snapshot_json, created_at_utc ON rounds BEGIN
    SELECT RAISE(ABORT, 'The approved round snapshot is immutable.');
END;
CREATE TRIGGER IF NOT EXISTS resident_snapshot_cannot_change
BEFORE UPDATE ON round_residents BEGIN
    SELECT RAISE(ABORT, 'The approved resident snapshot is immutable.');
END;
CREATE TRIGGER IF NOT EXISTS resident_snapshot_cannot_delete
BEFORE DELETE ON round_residents BEGIN
    SELECT RAISE(ABORT, 'The approved resident snapshot is immutable.');
END;
CREATE TRIGGER IF NOT EXISTS slot_origin_cannot_change
BEFORE UPDATE OF facility_id, municipality, selection_route, ordering_basis,
    original_resident_id, payload_json ON slots BEGIN
    SELECT RAISE(ABORT, 'The approved slot origin is immutable.');
END;
"""


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Unsupported workflow value: {type(value).__name__}")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=_json_default)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _timestamp(value):
    """Store UTC even when callers provide an aware local datetime/date."""
    if value is None:
        return _now()
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Use an ISO date or date-time for the activity.") from exc
    if not isinstance(value, datetime):
        raise ValueError("Use an ISO date or date-time for the activity.")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _fingerprint(operation, **content):
    return hashlib.sha256(_json({"operation": operation, **content}).encode()).hexdigest()


def _request_id(request_id):
    if request_id is None:
        return str(uuid4())
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("A request ID must be a nonempty string.")
    return request_id


def _actor(actor):
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("Record the demo staff member responsible for this activity.")
    return actor.strip()


def _connect(path, create=False):
    path = Path(path)
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.exists():
        raise ValueError("The screening coordination database does not exist yet.")
    connection = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise WorkflowStorageError("This coordination database needs a supported schema migration.")
        if create:
            connection.executescript(_SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        elif version != SCHEMA_VERSION:
            raise WorkflowStorageError("The coordination database has not been initialized.")
    except BaseException:
        connection.close()
        raise
    return connection


@contextmanager
def _connection(path, write=False):
    connection = None
    try:
        connection = _connect(path, create=write)
        if write:
            connection.execute("BEGIN IMMEDIATE")
        yield connection
        if write:
            connection.commit()
    except sqlite3.IntegrityError as exc:
        if connection is not None and connection.in_transaction:
            connection.rollback()
        raise WorkflowConflictError(f"The activity conflicts with saved coordination records: {exc}") from exc
    except sqlite3.Error as exc:
        if connection is not None and connection.in_transaction:
            connection.rollback()
        raise WorkflowStorageError("Could not save or read coordination records. Reload and retry; "
                                   f"the database may be busy ({exc}).") from exc
    except BaseException:
        if connection is not None and connection.in_transaction:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()


@lru_cache(maxsize=8)
def _validated_snapshot_json(serialized):
    """Validate identical approval content once; never cache mutable live state.

    The key contains the exact stored bytes, so changed or corrupted content
    must pass validation again. Return immutable text rather than a shared
    dictionary; each caller gets its own freshly parsed operational snapshot.
    """
    from agap.workflow import normalize_snapshot

    saved = json.loads(serialized)
    if saved != normalize_snapshot(saved):
        raise ValueError("Stored operational snapshot changed.")
    return serialized


def _round(row):
    if row is None:
        raise ValueError("This screening round was not found.")
    try:
        snapshot = json.loads(_validated_snapshot_json(row["snapshot_json"]))
        if snapshot.get("round_id") != row["round_id"] or snapshot["run_id"] != row["run_id"]:
            raise ValueError("Stored round identity or operational snapshot changed.")
        if json.loads(row["settings_json"]) != snapshot["settings"]:
            raise ValueError("Stored round settings do not match the approved snapshot.")
    except (KeyError, TypeError, ValueError) as exc:
        raise WorkflowStorageError("The saved screening round failed validation. "
                                   "Its snapshot needs review before recording more activity.") from exc
    return dict(round_id=row["round_id"], run_id=row["run_id"], status=row["status"],
                version=row["version"], snapshot=snapshot,
                created_at=row["created_at_utc"], archived_at=row["archived_at_utc"])


def _load(connection, round_id):
    return _round(connection.execute("SELECT * FROM rounds WHERE round_id = ?", (round_id,)).fetchone())


def _slots(connection, round_id):
    result = []
    replacements = {row["slot_id"]: row["total"] for row in connection.execute(
        """SELECT slot_id, count(*) AS total FROM workflow_events
           WHERE round_id = ? AND event_type = 'replacement' GROUP BY slot_id""", (round_id,))}
    for row in connection.execute("SELECT * FROM slots WHERE round_id = ? ORDER BY slot_id", (round_id,)):
        slot = json.loads(row["payload_json"])
        slot.update({name: row[name] for name in (
            "slot_id", "round_id", "facility_id", "municipality", "selection_route", "ordering_basis",
            "status", "current_resident_id", "original_resident_id", "version")})
        slot["replacement_count"] = replacements.get(row["slot_id"], 0)
        result.append(slot)
    return result


def _event(row):
    return dict(sequence=row["sequence"], event_id=row["event_id"], request_id=row["request_id"],
                round_id=row["round_id"], resident_id=row["resident_id"], slot_id=row["slot_id"],
                event_type=row["event_type"], actor=row["actor"],
                occurred_at=row["occurred_at_utc"], recorded_at=row["recorded_at_utc"],
                payload=json.loads(row["payload_json"]), supersedes_event_id=row["supersedes_event_id"])


def _events(connection, round_id):
    return [_event(row) for row in connection.execute(
        "SELECT * FROM workflow_events WHERE round_id = ? ORDER BY sequence", (round_id,))]


def _duplicate(connection, request_id, fingerprint):
    row = connection.execute("SELECT * FROM workflow_events WHERE request_id = ?", (request_id,)).fetchone()
    if row is None:
        return None
    if row["request_fingerprint"] != fingerprint:
        raise WorkflowConflictError("This request ID was already used for different activity. "
                                    "Reload before submitting a new action.")
    return _event(row)


def _assert_writable(round_record, expected_version=None):
    if round_record["status"] != "active":
        raise WorkflowConflictError("This round is archived and its history is read-only.")
    if expected_version is not None and expected_version != round_record["version"]:
        raise WorkflowConflictError("This round changed in another session. Reload before submitting the action.")


def _append(connection, *, request_id, fingerprint, round_id, event_type, actor, payload,
            resident_id=None, slot_id=None, occurred_at=None):
    event_id, recorded_at = f"EVENT-{uuid4().hex}", _now()
    occurred_at = _timestamp(occurred_at) if occurred_at is not None else recorded_at
    supersedes = payload.get("supersedes_event_id")
    if supersedes:
        previous = connection.execute("SELECT round_id, resident_id FROM workflow_events WHERE event_id = ?",
                                      (supersedes,)).fetchone()
        if previous is None or previous["round_id"] != round_id or previous["resident_id"] != resident_id:
            raise ValueError("A correction must refer to this resident's existing activity in the same round.")
    connection.execute("""INSERT INTO workflow_events
        (event_id, request_id, request_fingerprint, round_id, resident_id, slot_id, event_type, actor,
         occurred_at_utc, recorded_at_utc, payload_json, supersedes_event_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event_id, request_id, fingerprint, round_id, resident_id, slot_id, event_type, actor,
         occurred_at, recorded_at, _json(payload), supersedes))
    return _event(connection.execute("SELECT * FROM workflow_events WHERE event_id = ?", (event_id,)).fetchone())


def create_round(path, snapshot, actor="Demo coordinator", request_id=None):
    """Freeze a validated operational snapshot; never reattach another run's round."""
    from agap.workflow import normalize_snapshot

    snapshot = normalize_snapshot(snapshot)
    actor, request_id = _actor(actor), _request_id(request_id)
    fingerprint = _fingerprint("create_round", snapshot=snapshot, actor=actor)
    run_id = str(snapshot.get("run_id") or "")
    if not run_id:
        raise ValueError("A screening round must identify its original experiment run.")
    with _connection(path, write=True) as connection:
        duplicate = _duplicate(connection, request_id, fingerprint)
        if duplicate:
            return _load(connection, duplicate["round_id"])
        if connection.execute("SELECT 1 FROM rounds WHERE run_id = ? AND status = 'active'", (run_id,)).fetchone():
            raise WorkflowConflictError("This run already has an active round. Open or archive it before creating another.")
        round_id = snapshot.get("round_id") or f"ROUND-{uuid4().hex}"
        snapshot = {**snapshot, "round_id": round_id}
        created = _now()
        connection.execute("""INSERT INTO rounds
            (round_id, run_id, status, version, settings_json, snapshot_json, created_at_utc)
            VALUES (?, ?, 'active', 0, ?, ?, ?)""",
            (round_id, run_id, _json(snapshot.get("settings", {})), _json(snapshot), created))
        for resident in snapshot["residents"]:
            connection.execute("INSERT INTO round_residents (round_id, resident_id, payload_json) VALUES (?, ?, ?)",
                               (round_id, resident["resident_id"], _json(resident)))
        for slot in snapshot["slots"]:
            current = slot.get("current_resident_id", slot.get("resident_id"))
            original = slot.get("original_resident_id", current)
            connection.execute("""INSERT INTO slots
                (slot_id, round_id, facility_id, municipality, selection_route, ordering_basis,
                 status, current_resident_id, original_resident_id, version, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, 'reserved', ?, ?, 0, ?)""",
                (slot["slot_id"], round_id, slot["facility_id"], slot["municipality"],
                 slot["selection_route"], slot["ordering_basis"], current, original, _json(slot)))
        _append(connection, request_id=request_id, fingerprint=fingerprint, round_id=round_id,
                event_type="round_created", actor=actor,
                payload={"run_id": run_id, "slot_count": len(snapshot["slots"])}, occurred_at=created)
        return _load(connection, round_id)


def list_rounds(path=DEFAULT_PATH, run_id=None):
    if not Path(path).exists():
        return []
    with _connection(path) as connection:
        if run_id is None:
            rows = connection.execute("SELECT * FROM rounds ORDER BY created_at_utc DESC, round_id")
        else:
            rows = connection.execute("SELECT * FROM rounds WHERE run_id = ? ORDER BY created_at_utc DESC, round_id",
                                      (str(run_id),))
        return [_round(row) for row in rows]


def active_round(path=DEFAULT_PATH, run_id=None):
    if not Path(path).exists():
        return None
    with _connection(path) as connection:
        if run_id is None:
            row = connection.execute("SELECT * FROM rounds WHERE status = 'active' ORDER BY created_at_utc DESC LIMIT 1").fetchone()
        else:
            row = connection.execute("SELECT * FROM rounds WHERE status = 'active' AND run_id = ?", (str(run_id),)).fetchone()
        return _round(row) if row is not None else None


def load_round(path, round_id):
    with _connection(path) as connection:
        return _load(connection, round_id)


def get_slots(path, round_id):
    with _connection(path) as connection:
        _load(connection, round_id)
        return _slots(connection, round_id)


def get_events(path, round_id):
    with _connection(path) as connection:
        _load(connection, round_id)
        return _events(connection, round_id)


def worklist(path, round_id):
    """Read a consistent snapshot before deriving queues from recorded events."""
    from agap.workflow import project_worklist

    with _connection(path) as connection:
        connection.execute("BEGIN")
        round_record = _load(connection, round_id)
        slots, events = _slots(connection, round_id), _events(connection, round_id)
        connection.commit()
    return project_worklist(round_record["snapshot"], slots, events)


def record_event(path, round_id, resident_id, event_type, payload, actor="Demo staff", occurred_at=None,
                 request_id=None, expected_version=None):
    """Validate and atomically append activity with its slot/version change."""
    from agap.workflow import normalize_event

    if event_type in {"round_created", "round_archived", "replacement"}:
        raise ValueError("Use the dedicated round or replacement operation for this activity.")
    actor, request_id = _actor(actor), _request_id(request_id)
    fingerprint = _fingerprint("record_event", round_id=round_id, resident_id=resident_id,
                               event_type=event_type, payload=payload, actor=actor, occurred_at=occurred_at)
    with _connection(path, write=True) as connection:
        duplicate = _duplicate(connection, request_id, fingerprint)
        if duplicate:
            return duplicate
        round_record = _load(connection, round_id)
        _assert_writable(round_record, expected_version)
        slots, events = _slots(connection, round_id), _events(connection, round_id)
        normalized = normalize_event(round_record["snapshot"], slots, events, resident_id,
                                     event_type, payload, occurred_at=occurred_at)
        slot = next((item for item in slots if item.get("current_resident_id") == resident_id
                     and item["status"] in {"reserved", "started"}), None)
        slot_id = slot["slot_id"] if slot else None
        if event_type in {"specimen", "specimen_collected", "result", "result_recorded"}:
            if slot is None:
                raise ValueError("This resident has no current screening slot.")
            connection.execute("UPDATE slots SET status = 'started', version = version + 1 WHERE round_id = ? AND slot_id = ?",
                               (round_id, slot_id))
        if event_type == "contact" and str(normalized.get("outcome", "")).lower() in {"declined", "withdrawn", "unreachable"}:
            if slot is None or slot["status"] != "reserved":
                raise ValueError("Only an unstarted slot can be released after a decline, withdrawal or confirmed unreachability.")
            connection.execute("""UPDATE slots SET status = 'released', current_resident_id = NULL,
                                  version = version + 1 WHERE round_id = ? AND slot_id = ?""", (round_id, slot_id))
        event = _append(connection, request_id=request_id, fingerprint=fingerprint, round_id=round_id,
                        resident_id=resident_id, slot_id=slot_id, event_type=event_type,
                        actor=actor, payload=normalized, occurred_at=occurred_at)
        connection.execute("UPDATE rounds SET version = version + 1 WHERE round_id = ?", (round_id,))
        return event


def propose_replacement(path, round_id, slot_id):
    from agap.workflow import replacement_candidate

    with _connection(path) as connection:
        connection.execute("BEGIN")
        round_record = _load(connection, round_id)
        _assert_writable(round_record)
        proposal = replacement_candidate(round_record["snapshot"], _slots(connection, round_id),
                                         _events(connection, round_id), slot_id)
        connection.commit()
    if proposal is not None:
        proposal = {**proposal, "round_version": round_record["version"]}
    return proposal


def confirm_replacement(path, round_id, slot_id, resident_id, actor="Demo coordinator", request_id=None,
                        expected_version=None):
    """Recheck the frozen eligible order while holding SQLite's write lock."""
    from agap.workflow import replacement_candidate

    actor, request_id = _actor(actor), _request_id(request_id)
    fingerprint = _fingerprint("confirm_replacement", round_id=round_id, slot_id=slot_id,
                               resident_id=resident_id, actor=actor)
    with _connection(path, write=True) as connection:
        duplicate = _duplicate(connection, request_id, fingerprint)
        if duplicate:
            return duplicate
        round_record = _load(connection, round_id)
        _assert_writable(round_record, expected_version)
        slots, events = _slots(connection, round_id), _events(connection, round_id)
        slot = next((item for item in slots if item["slot_id"] == slot_id), None)
        if slot is None or slot["status"] != "released":
            raise WorkflowConflictError("This slot is no longer available for replacement. Reload the worklist.")
        proposal = replacement_candidate(round_record["snapshot"], slots, events, slot_id)
        if proposal is None or proposal["resident_id"] != resident_id:
            raise WorkflowConflictError("The eligible replacement changed or is unavailable. Review a new proposal.")
        previously_assigned = {item["original_resident_id"] for item in slots}
        previously_assigned.update(event["resident_id"] for event in events if event["event_type"] == "replacement")
        if resident_id in previously_assigned or any(item.get("current_resident_id") == resident_id
                                                    and item["status"] != "released" for item in slots):
            raise WorkflowConflictError("This resident was already assigned in the approved round.")
        if proposal.get("facility_id", slot["facility_id"]) != slot["facility_id"] or proposal.get("municipality", slot["municipality"]) != slot["municipality"]:
            raise WorkflowConflictError("A replacement must preserve the slot's service point and municipality.")
        max_distance = float(round_record["snapshot"].get("settings", {}).get("max_distance_km", 20.0))
        distance = float(proposal["distance_km"])
        if not 0 <= distance <= max_distance:
            raise WorkflowConflictError("The proposed resident exceeds the approved access limit.")
        previous = next((event["resident_id"] for event in reversed(events)
                         if event["slot_id"] == slot_id and event["event_type"] == "contact"
                         and str(event["payload"].get("outcome", "")).lower() in {"declined", "withdrawn"}),
                        slot["original_resident_id"])
        connection.execute("""UPDATE slots SET status = 'reserved', current_resident_id = ?, version = version + 1
                              WHERE round_id = ? AND slot_id = ?""", (resident_id, round_id, slot_id))
        event = _append(connection, request_id=request_id, fingerprint=fingerprint, round_id=round_id,
                        resident_id=resident_id, slot_id=slot_id, event_type="replacement", actor=actor,
                        payload={**proposal, "resident_id": resident_id, "new_resident_id": resident_id,
                                 "previous_resident_id": previous, "original_resident_id": slot["original_resident_id"]})
        connection.execute("UPDATE rounds SET version = version + 1 WHERE round_id = ?", (round_id,))
        return event


def archive_round(path, round_id, actor="Demo coordinator", request_id=None, expected_version=None):
    actor, request_id = _actor(actor), _request_id(request_id)
    fingerprint = _fingerprint("archive_round", round_id=round_id, actor=actor)
    with _connection(path, write=True) as connection:
        duplicate = _duplicate(connection, request_id, fingerprint)
        if duplicate:
            return _load(connection, round_id)
        round_record = _load(connection, round_id)
        _assert_writable(round_record, expected_version)
        archived = _now()
        _append(connection, request_id=request_id, fingerprint=fingerprint, round_id=round_id,
                event_type="round_archived", actor=actor, payload={}, occurred_at=archived)
        connection.execute("""UPDATE rounds SET status = 'archived', archived_at_utc = ?, version = version + 1
                              WHERE round_id = ?""", (archived, round_id))
        return _load(connection, round_id)
