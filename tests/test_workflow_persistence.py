"""Persistent staff activity stays separate, recoverable, and transactional."""
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timezone
import json
import sqlite3
from threading import Barrier

import pytest

from agap import workflow_store as store


@pytest.fixture
def snapshot():
    residents = []
    rows = [("SYN-A", "Alpha", 2), ("SYN-B", "Alpha", 3),
            ("SYN-FAR", "Alpha", 25), ("SYN-OTHER", "Beta", 1),
            ("SYN-C", "Alpha", 4), ("SYN-D", "Alpha", 5)]
    for index, (rid, municipality, distance) in enumerate(rows):
        residents.append(dict(resident_id=rid, municipality=municipality, age=45, female=False,
                              reported=False, score=.9 - index / 10,
                              candidate_distances_km={"DEMO-F1": distance}))
    return dict(schema_version=1, run_id="frozen-original-run", model="clinical",
                provenance=dict(run_id="frozen-original-run", config_hash="cfg-1",
                                input_hash="inputs-1", source_hash="source-1"),
                settings=dict(budget=2, max_distance_km=20, policy="risk_ranked", outreach=.2,
                              outcome=dict(egfr_threshold=60, uacr_threshold=30)),
                orders=dict(priority=[r[0] for r in rows],
                            random=["SYN-D", "SYN-OTHER", "SYN-FAR", "SYN-C", "SYN-A", "SYN-B"]),
                residents=residents, facilities=[dict(facility_id="DEMO-F1", capacity=2)],
                slots=[dict(slot_id=f"slot-{index:06d}", facility_id="DEMO-F1", municipality="Alpha",
                            selection_route="priority", ordering_basis="priority", selection_reason="risk",
                            original_reason="risk", current_resident_id=rid, original_resident_id=rid,
                            status="reserved", version=0, distance_km=index + 1)
                       for index, rid in enumerate(("SYN-A", "SYN-B"), 1)],
                applied_reports={})


@pytest.fixture
def saved(tmp_path, snapshot):
    path = tmp_path / "reports" / "workflow.sqlite3"
    record = store.create_round(path, snapshot, request_id="create-round")
    return path, record


def specimen_date():
    return datetime.now(timezone.utc).date().isoformat()


def test_empty_reads_do_not_create_database(tmp_path):
    path = tmp_path / "no-database" / "workflow.sqlite3"
    assert store.active_round(path) is None
    assert store.list_rounds(path) == []
    assert not path.parent.exists()


def test_restart_restores_round_and_only_recorded_work(saved, snapshot):
    path, record = saved
    rid = record["round_id"]
    assert set(store.worklist(path, rid).queue) == {"Needs contact"}
    store.record_event(path, rid, "SYN-A", "contact", {"outcome": "Accepted"}, expected_version=0)
    store.record_event(path, rid, "SYN-A", "specimen", {"specimen_date": specimen_date()}, expected_version=1)
    store.record_event(path, rid, "SYN-A", "result",
                       {"specimen_date": specimen_date(), "creatinine": .8, "result_reference": "DEMO-LAB-A"},
                       expected_version=2)
    # Every API opens/closes its own connection, reproducing a server restart.
    restored = store.active_round(path, snapshot["run_id"])
    assert restored["round_id"] == rid and restored["version"] == 3
    assert restored["snapshot"] == store.load_round(path, rid)["snapshot"]
    assert restored["snapshot"]["slots"] == snapshot["slots"]
    cases = store.worklist(path, rid).set_index("resident_id")
    assert cases.loc["SYN-A", "queue"] == "Awaiting screening"
    assert not cases.loc["SYN-A", "panel_complete"]
    assert cases.loc["SYN-A", "screening_flag"] is None
    assert cases.loc["SYN-B", "queue"] == "Needs contact"
    assert store.get_slots(path, rid)[0]["status"] == "started"
    assert len(store.get_events(path, rid)) == 4
    assert store.active_round(path, "same-config-but-new-run") is None


def test_snapshot_filters_hidden_outcomes_and_remains_immutable(tmp_path, snapshot):
    dirty = copy.deepcopy(snapshot)
    forbidden = {"y_true": True, "completion_uniform": .1, "creatinine": 9.9,
                 "uacr": 999, "egfr": 1, "research_trait": "hidden"}
    dirty.update(forbidden)
    dirty["residents"][0].update(forbidden)
    dirty["slots"][0].update(forbidden)
    dirty["facilities"][0].update(forbidden)
    path = tmp_path / "workflow.sqlite3"
    record = store.create_round(path, dirty)
    original = json.dumps(record["snapshot"], sort_keys=True)
    for field in forbidden:
        assert f'"{field}"' not in original
    # A caller's later draft/report/source edits cannot mutate the approval.
    dirty["residents"][0]["score"] = 0
    dirty["provenance"]["source_hash"] = "cosmetic-ui-change"
    dirty["slots"].clear()
    assert json.dumps(store.load_round(path, record["round_id"])["snapshot"], sort_keys=True) == original


def test_loaded_snapshots_are_independent_nested_copies(saved):
    path, record = saved
    rid = record["round_id"]
    first = store.load_round(path, rid)
    second = store.load_round(path, rid)
    expected = copy.deepcopy(second["snapshot"])
    first["snapshot"]["residents"][0]["candidate_distances_km"]["DEMO-F1"] = 999
    first["snapshot"]["settings"]["outcome"]["egfr_threshold"] = 1
    first["snapshot"]["orders"]["priority"].reverse()
    first["snapshot"]["slots"].clear()
    assert second["snapshot"] == expected
    assert record["snapshot"] == expected
    assert store.load_round(path, rid)["snapshot"] == expected


def test_warm_snapshot_reads_keep_live_versions_slots_and_archive_fresh(saved):
    path, record = saved
    rid, slot_id = record["round_id"], "slot-000001"
    warm = store.load_round(path, rid)
    assert store.load_round(path, rid) == warm
    approved_snapshot = copy.deepcopy(warm["snapshot"])
    store.record_event(path, rid, "SYN-A", "contact", {"outcome": "Declined"}, expected_version=0)
    assert store.load_round(path, rid)["version"] == 1
    released = next(slot for slot in store.get_slots(path, rid) if slot["slot_id"] == slot_id)
    assert released["status"] == "released" and released["current_resident_id"] is None
    store.confirm_replacement(path, rid, slot_id, "SYN-C", expected_version=1)
    store.record_event(path, rid, "SYN-C", "specimen", {"specimen_date": specimen_date()}, expected_version=2)
    current = store.active_round(path, record["run_id"])
    assert current["version"] == 3 and current["status"] == "active"
    started = next(slot for slot in store.get_slots(path, rid) if slot["slot_id"] == slot_id)
    assert started["status"] == "started" and started["current_resident_id"] == "SYN-C"
    cases = store.worklist(path, rid).set_index("resident_id")
    assert not cases.loc["SYN-A", "is_current"]
    assert cases.loc["SYN-C", "is_current"] and cases.loc["SYN-C", "queue"] == "Awaiting screening"
    store.archive_round(path, rid, expected_version=3)
    archived = store.load_round(path, rid)
    assert archived["status"] == "archived" and archived["version"] == 4
    assert store.active_round(path, record["run_id"]) is None
    assert len(store.get_events(path, rid)) == 5
    assert store.worklist(path, rid).set_index("resident_id").loc["SYN-C", "started"]
    assert archived["snapshot"] == approved_snapshot
    assert warm["version"] == 0 and warm["status"] == "active"


def test_requests_are_idempotent_and_content_checked(saved, snapshot):
    path, record = saved
    rid = record["round_id"]
    assert store.create_round(path, snapshot, request_id="create-round")["round_id"] == rid
    first = store.record_event(path, rid, "SYN-A", "contact", {"outcome": "Accepted"},
                               request_id="one-contact", expected_version=0)
    duplicate = store.record_event(path, rid, "SYN-A", "contact", {"outcome": "Accepted"},
                                   request_id="one-contact", expected_version=0)
    assert first == duplicate
    assert store.load_round(path, rid)["version"] == 1
    assert len(store.get_events(path, rid)) == 2
    with pytest.raises(store.WorkflowConflictError, match="different activity"):
        store.record_event(path, rid, "SYN-A", "contact", {"outcome": "Declined"}, request_id="one-contact")
    with pytest.raises(store.WorkflowConflictError, match="different activity"):
        store.create_round(path, snapshot, actor="Another coordinator", request_id="create-round")


def test_failed_append_rolls_back_slot_and_round_version(saved, monkeypatch):
    path, record = saved
    rid = record["round_id"]
    before = (store.load_round(path, rid), store.get_slots(path, rid), store.get_events(path, rid))

    def failed_append(*args, **kwargs):
        raise RuntimeError("simulated failure after slot update")

    monkeypatch.setattr(store, "_append", failed_append)
    with pytest.raises(RuntimeError, match="simulated failure"):
        store.record_event(path, rid, "SYN-A", "specimen", {"specimen_date": specimen_date()})
    assert (store.load_round(path, rid), store.get_slots(path, rid), store.get_events(path, rid)) == before


def test_stale_browser_version_is_rejected_without_partial_activity(saved):
    path, record = saved
    rid = record["round_id"]
    store.record_event(path, rid, "SYN-A", "contact", {"outcome": "No answer"}, expected_version=0)
    with pytest.raises(store.WorkflowConflictError, match="another session"):
        store.record_event(path, rid, "SYN-B", "contact", {"outcome": "Accepted"}, expected_version=0)
    assert store.load_round(path, rid)["version"] == 1
    assert len(store.get_events(path, rid)) == 2


def test_active_round_uniqueness_and_archive_preserves_history(saved, snapshot):
    path, record = saved
    rid = record["round_id"]
    with pytest.raises(store.WorkflowConflictError, match="already has an active round"):
        store.create_round(path, snapshot)
    store.record_event(path, rid, "SYN-A", "contact", {"outcome": "Accepted"})
    archived = store.archive_round(path, rid, request_id="archive", expected_version=1)
    assert archived["status"] == "archived" and archived["archived_at"]
    assert store.active_round(path, snapshot["run_id"]) is None
    assert len(store.get_events(path, rid)) == 3
    assert len(store.worklist(path, rid)) == 2
    assert store.archive_round(path, rid, request_id="archive") == archived
    with pytest.raises(store.WorkflowConflictError, match="archived"):
        store.record_event(path, rid, "SYN-A", "contact", {"outcome": "No answer"})
    another = store.create_round(path, snapshot)
    assert another["round_id"] != rid
    assert len(store.list_rounds(path, snapshot["run_id"])) == 2
    assert store.load_round(path, rid)["status"] == "archived"


def test_replacement_reuses_slot_and_keeps_declined_resident_history(saved):
    path, record = saved
    rid, slot_id = record["round_id"], "slot-000001"
    untouched = store.get_slots(path, rid)[1]
    store.record_event(path, rid, "SYN-A", "contact", {"outcome": "Declined"})
    proposal = store.propose_replacement(path, rid, slot_id)
    assert proposal["resident_id"] == "SYN-C"  # skip assigned, unreachable and other municipality
    assert proposal["round_version"] == 1
    assert proposal["distance_km"] == 4
    confirmed = store.confirm_replacement(path, rid, slot_id, "SYN-C", request_id="replacement", expected_version=1)
    assert store.confirm_replacement(path, rid, slot_id, "SYN-C", request_id="replacement", expected_version=1) == confirmed
    slots = store.get_slots(path, rid)
    assert len(slots) == 2 and slots[1] == untouched
    assert slots[0]["status"] == "reserved" and slots[0]["current_resident_id"] == "SYN-C"
    assert slots[0]["original_resident_id"] == "SYN-A"
    cases = store.worklist(path, rid).set_index("resident_id")
    assert cases.loc["SYN-A", "queue"] == "Declined / withdrawn"
    assert not cases.loc["SYN-A", "is_current"]
    assert cases.loc["SYN-C", "queue"] == "Needs contact"
    assert cases.is_current.sum() == 2
    assert confirmed["payload"]["previous_resident_id"] == "SYN-A"
    store.record_event(path, rid, "SYN-C", "specimen", {"specimen_date": specimen_date()})
    assert store.get_slots(path, rid)[0]["status"] == "started"
    with pytest.raises(ValueError, match="cannot be released"):
        store.record_event(path, rid, "SYN-C", "contact", {"outcome": "Withdrawn"})


def test_concurrent_replacement_confirmations_have_one_winner(saved):
    path, record = saved
    rid, slot_id = record["round_id"], "slot-000001"
    store.record_event(path, rid, "SYN-A", "contact", {"outcome": "Declined"})
    barrier = Barrier(2)

    def confirm(request):
        barrier.wait(timeout=5)
        try:
            return store.confirm_replacement(path, rid, slot_id, "SYN-C", request_id=request, expected_version=1)
        except store.WorkflowConflictError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(confirm, ("browser-one", "browser-two")))
    assert sum(isinstance(item, dict) for item in outcomes) == 1
    assert sum(isinstance(item, store.WorkflowConflictError) for item in outcomes) == 1
    assert store.load_round(path, rid)["version"] == 2
    assert len([e for e in store.get_events(path, rid) if e["event_type"] == "replacement"]) == 1


def test_repeated_declines_preserve_history_and_do_not_reinvite_used_candidates(saved):
    path, record = saved
    rid, slot_id = record["round_id"], "slot-000001"
    store.record_event(path, rid, "SYN-A", "contact", {"outcome": "Declined"})
    store.confirm_replacement(path, rid, slot_id, "SYN-C")
    store.record_event(path, rid, "SYN-C", "contact", {"outcome": "Declined"})
    released = store.get_slots(path, rid)[0]
    assert released["status"] == "released" and released["replacement_count"] == 1
    assert store.propose_replacement(path, rid, slot_id)["resident_id"] == "SYN-D"
    event = store.confirm_replacement(path, rid, slot_id, "SYN-D")
    assert event["payload"]["previous_resident_id"] == "SYN-C"
    assert event["payload"]["original_resident_id"] == "SYN-A"
    assert store.get_slots(path, rid)[0]["replacement_count"] == 2
    store.record_event(path, rid, "SYN-D", "contact", {"outcome": "Declined"})
    assert store.propose_replacement(path, rid, slot_id) is None
    cases = store.worklist(path, rid)
    assert len(cases) == 4 and cases.is_current.sum() == 1
    assert store.load_round(path, rid)["snapshot"]["slots"][0].get("replacement_count", 0) == 0


def test_report_attempts_do_not_apply_and_explicit_applications_survive_reload(saved):
    path, record = saved
    rid = record["round_id"]
    report = dict(resident_id="SYN-C", age=45, DM="Y", HTN="N", FAM=None, OUT=None,
                  PRIOR=None, HRS=None, DATE=specimen_date())
    store.record_event(path, rid, "SYN-C", "report_attempt",
                       {"payload": report, "errors": [], "channel": "form", "raw_text": None})
    assert len(store.worklist(path, rid)) == 2
    applied = store.record_event(path, rid, "SYN-C", "report_applied", report)
    assert applied["payload"] == report
    assert store.get_events(path, rid)[-1]["payload"] == report
    assert store.load_round(path, rid)["snapshot"]["residents"][4]["reported"] is False
    assert store.load_round(path, rid)["snapshot"]["applied_reports"] == {}


def test_event_order_is_recording_order_and_stored_in_utc(saved):
    path, record = saved
    rid = record["round_id"]
    store.record_event(path, rid, "SYN-A", "contact", {"outcome": "Accepted"},
                       occurred_at="2026-10-21T10:00:00+08:00")
    store.record_event(path, rid, "SYN-A", "contact", {"outcome": "No answer"},
                       occurred_at="2026-10-20T10:00:00+08:00")
    events = store.get_events(path, rid)
    assert [event["sequence"] for event in events] == sorted(event["sequence"] for event in events)
    assert events[1]["occurred_at"] == "2026-10-21T02:00:00+00:00"
    assert events[2]["occurred_at"] == "2026-10-20T02:00:00+00:00"
    assert store.worklist(path, rid).set_index("resident_id").loc["SYN-A", "contact_outcome"] == "No answer"


def test_database_enforces_foreign_keys_unique_owners_and_append_only_events(saved):
    path, record = saved
    rid = record["round_id"]
    with store._connection(path, write=True) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(store.WorkflowConflictError):
        with store._connection(path, write=True) as connection:
            connection.execute("UPDATE slots SET current_resident_id = 'SYN-A' WHERE round_id = ? AND slot_id = 'slot-000002'", (rid,))
    with pytest.raises(store.WorkflowConflictError):
        with store._connection(path, write=True) as connection:
            connection.execute("UPDATE slots SET current_resident_id = 'SYN-NOT-IN-COHORT' WHERE round_id = ? AND slot_id = 'slot-000002'", (rid,))
    with pytest.raises(store.WorkflowConflictError, match="append-only"):
        with store._connection(path, write=True) as connection:
            connection.execute("DELETE FROM workflow_events WHERE round_id = ?", (rid,))
    assert len(store.get_events(path, rid)) == 1


def test_approved_snapshot_cannot_be_overwritten_by_activity(saved):
    path, record = saved
    rid = record["round_id"]
    statements = [
        ("UPDATE rounds SET run_id = 'different-run' WHERE round_id = ?", (rid,)),
        ("UPDATE rounds SET snapshot_json = '{}' WHERE round_id = ?", (rid,)),
        ("UPDATE round_residents SET payload_json = '{}' WHERE round_id = ?", (rid,)),
        ("UPDATE slots SET facility_id = 'different-site' WHERE round_id = ?", (rid,)),
    ]
    for statement, parameters in statements:
        with pytest.raises(store.WorkflowConflictError, match="immutable"):
            with store._connection(path, write=True) as connection:
                connection.execute(statement, parameters)
    assert store.load_round(path, rid) == record


def test_invalid_stored_snapshot_is_rejected_before_more_activity(saved):
    path, record = saved
    rid = record["round_id"]
    # Simulate an old/imported/corrupt database, bypassing normal immutable writes.
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER round_snapshot_cannot_change")
        changed = copy.deepcopy(record["snapshot"])
        changed["run_id"] = "another-run"
        connection.execute("UPDATE rounds SET snapshot_json = ? WHERE round_id = ?", (json.dumps(changed), rid))
    with pytest.raises(store.WorkflowStorageError, match="failed validation"):
        store.load_round(path, rid)
    with pytest.raises(store.WorkflowStorageError, match="failed validation"):
        store.record_event(path, rid, "SYN-A", "contact", {"outcome": "Accepted"})
    # The failed read/write never appends staff activity.
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM workflow_events WHERE round_id = ?", (rid,)).fetchone()[0] == 1


@pytest.mark.parametrize("changed_field", ["round_id", "run_id", "settings_json"])
def test_warm_snapshot_cannot_hide_fresh_row_identity_or_settings_mismatch(saved, changed_field):
    path, record = saved
    rid = record["round_id"]
    assert store.load_round(path, rid) == record
    assert store.load_round(path, rid) == record
    lookup_id = rid
    # Simulate an imported/corrupt row. The already validated snapshot bytes
    # remain identical, so live row checks must independently reject the row.
    with sqlite3.connect(path) as connection:
        original_json = connection.execute("SELECT snapshot_json FROM rounds WHERE round_id = ?", (rid,)).fetchone()[0]
        connection.execute("DROP TRIGGER round_snapshot_cannot_change")
        if changed_field == "round_id":
            lookup_id = rid + "-MISMATCH"
            connection.execute("UPDATE rounds SET round_id = ? WHERE round_id = ?", (lookup_id, rid))
        elif changed_field == "run_id":
            connection.execute("UPDATE rounds SET run_id = 'different-run' WHERE round_id = ?", (rid,))
        else:
            settings = copy.deepcopy(record["snapshot"]["settings"])
            settings["budget"] += 1
            connection.execute("UPDATE rounds SET settings_json = ? WHERE round_id = ?", (json.dumps(settings), rid))
        assert connection.execute("SELECT snapshot_json FROM rounds WHERE round_id = ?", (lookup_id,)).fetchone()[0] == original_json
    with pytest.raises(store.WorkflowStorageError, match="failed validation"):
        store.load_round(path, lookup_id)
    with pytest.raises(store.WorkflowStorageError, match="failed validation"):
        store.record_event(path, lookup_id, "SYN-A", "contact", {"outcome": "Accepted"})
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM workflow_events").fetchone()[0] == 1


def test_unknown_schema_version_is_not_silently_overwritten(saved):
    path, record = saved
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 999")
    with pytest.raises(store.WorkflowStorageError, match="schema migration"):
        store.load_round(path, record["round_id"])


def test_confirmed_unreachable_resident_releases_the_slot_in_storage(saved):
    path, record = saved
    rid = record["round_id"]
    attempts = store.load_round(path, rid)["snapshot"]["settings"].get("unreachable_after_attempts", 3)
    for _ in range(attempts):
        store.record_event(path, rid, "SYN-A", "contact", {"outcome": "No answer"})
    store.record_event(path, rid, "SYN-A", "contact", {"outcome": "Unreachable"})
    slot = next(item for item in store.get_slots(path, rid) if item["slot_id"] == "slot-000001")
    assert slot["status"] == "released" and slot["current_resident_id"] is None
    assert store.propose_replacement(path, rid, "slot-000001")["resident_id"] == "SYN-C"
