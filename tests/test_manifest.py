"""DATA-02: every collected source has complete manifest metadata."""
import json

import pytest
import yaml

from agap.config import ROOT
from agap.data.sources import REQUIRED_FIELDS, SOURCES, climate_entry, enrich, family_for, missing_fields


def test_committed_manifest_entries_have_every_data_02_field():
    manifest = yaml.safe_load((ROOT / "data/manifest.yaml").read_text())
    incomplete = {item["id"]: missing_fields(item) for item in manifest["datasets"] if missing_fields(item)}
    assert not incomplete
    assert any(item["id"] == "era5_land_laguna" for item in manifest["datasets"])
    assert not any(item["id"] == "era5_existing" for item in manifest["datasets"])  # obsolete January 2021 file


def test_every_family_supplies_the_metadata_fields():
    collector_fields = {"id", "url", "checked_utc", "sha256", "license", "limitations"}
    for name, family in SOURCES.items():
        assert set(REQUIRED_FIELDS) - collector_fields <= set(family), name


def test_collector_values_win_and_unknown_sources_fail():
    entry = enrich(dict(id="boundary_adm3", url="https://example.org/b", license="CC BY 3.0 IGO", checked_utc="t",
                        sha256="abc", limitations="Simplified."))
    assert entry["license"] == "CC BY 3.0 IGO" and entry["publisher"].startswith("geoBoundaries") and not missing_fields(entry)
    assert "constrained" in enrich(dict(id="worldpop_f_40", limitations="Modeled."))["limitations"]
    assert family_for("worldpop_population") == "worldpop_population" and family_for("worldpop_m_80") == "worldpop_age_sex"
    with pytest.raises(KeyError, match="DATA-02"):
        family_for("mystery_source")


def test_climate_entry_summarises_archive_records(tmp_path):
    folder = tmp_path / "era5_land/laguna_replay"
    folder.mkdir(parents=True)
    for name, status in (("2024_01-06", "complete"), ("2024_07-12", "complete"), ("2023_01-06", "running")):
        (folder / f"era5_land_{name}_temperature_precipitation.grib.zip.json").write_text(
            json.dumps(dict(status=status, retrieved_at_utc=f"2026-10-18T0{len(name) % 9}:00:00+00:00")))
    entry = climate_entry(tmp_path)
    assert entry["status"] == "2 of 74 planned archives complete" and not missing_fields(entry)
    assert entry["publisher"].startswith("Copernicus") and "Muñoz-Sabater" in entry["attribution"]
