"""A register entry never becomes a usable clinic without dated evidence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd
import pytest

from agap.clinics import normalize_verification, read_verifications, save_verification, verification_queue


@pytest.fixture
def catalogue():
    return pd.DataFrame(dict(facility_id=["YAKAP-20260930-1", "YAKAP-20260930-2"],
                             facility_name=["Fixture clinic A", "Fixture clinic B"], source_page=[69, 70]))


@pytest.fixture
def confirmed():
    return dict(latitude="14.2", longitude="121.2", creatinine="Available", uacr="Available", capacity_panels="10",
                checked_on="2026-10-20", evidence_source="Fixture verification reference", notes="Fixture only")


def test_register_identity_alone_is_unverified(catalogue):
    queue = verification_queue(catalogue, [])
    assert queue.status.eq("Unverified").all()
    assert queue.latitude.isna().all() and queue.capacity_panels.isna().all()
    assert queue.uacr.eq("Not checked").all()
    assert queue.remaining_checks.str.contains("dated evidence").all()


def test_partial_evidence_does_not_imply_panel_readiness(tmp_path, catalogue, confirmed):
    partial = dict(confirmed, uacr="Not checked", capacity_panels="")
    save_verification(tmp_path / "clinics.sqlite3", catalogue, catalogue.facility_id[0], partial)
    queue = verification_queue(catalogue, read_verifications(tmp_path / "clinics.sqlite3"))
    assert queue.status.tolist() == ["Needs verification", "Unverified"]
    assert "uacr" in queue.iloc[0].remaining_checks


def test_saves_are_idempotent_revisions_preserve_evidence_and_invalid_writes_are_rejected(tmp_path, catalogue, confirmed):
    path = tmp_path / "clinics.sqlite3"
    identity = catalogue.facility_id[0]
    first, created = save_verification(path, catalogue, identity, confirmed)
    assert created
    duplicate, created = save_verification(path, catalogue, identity, dict(confirmed, capacity_panels="10.0"))
    assert not created and duplicate["record_id"] == first["record_id"]
    second, created = save_verification(path, catalogue, identity, dict(confirmed, capacity_panels="8"))
    assert created and second["supersedes"] == first["record_id"]
    history = read_verifications(path)
    assert len(history) == 2 and history[0]["payload"]["capacity_panels"] == 10
    queue = verification_queue(catalogue, history)
    assert queue.iloc[0].status == "Ready for pilot review" and queue.iloc[0].capacity_panels == 8
    assert queue.iloc[1].status == "Unverified"
    with pytest.raises(ValueError):
        save_verification(path, catalogue, identity, dict(confirmed, evidence_source=""))
    assert read_verifications(path) == history


@pytest.mark.parametrize("change", [dict(latitude="nan"), dict(longitude=""), dict(capacity_panels="1.5"),
    dict(capacity_panels="-1"), dict(uacr="Not checked"), dict(evidence_source=""), dict(checked_on=None),
    dict(checked_on="2026-10-21")])
def test_invalid_or_unsupported_confirmations_cannot_be_saved(confirmed, change):
    with pytest.raises(ValueError):
        normalize_verification(dict(confirmed, **change), today=date(2026, 10, 20))


def test_concurrent_saves_have_unique_ids_and_a_complete_revision_chain(tmp_path, catalogue, confirmed):
    path = tmp_path / "clinics.sqlite3"
    def save(index):
        return save_verification(path, catalogue, catalogue.facility_id[0], dict(confirmed, notes=str(index)))
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(save, range(3)))
    history = read_verifications(path)
    assert len(history) == 3 and len({row["record_id"] for row in history}) == 3
    assert [row["supersedes"] for row in history] == [None, history[0]["record_id"], history[1]["record_id"]]
