"""Bring data/manifest.yaml up to SRS DATA-02 without downloading anything.

Adds family metadata to every collected entry, replaces the ERA5-Land entries with one entry for the
collected archives, and fails if any entry still lacks a required field.
"""
from datetime import datetime, timezone

import yaml

from agap.config import ROOT
from agap.data.sources import climate_entry, enrich, missing_fields


def main():
    path = ROOT / "data/manifest.yaml"
    manifest = yaml.safe_load(path.read_text())
    datasets = [enrich(item) for item in manifest["datasets"] if not item["id"].startswith("era5")]
    datasets.append(climate_entry(ROOT / "data/raw"))
    incomplete = {item["id"]: missing_fields(item) for item in datasets if missing_fields(item)}
    if incomplete:
        raise SystemExit(f"Manifest entries missing DATA-02 fields: {incomplete}")
    manifest.update(datasets=datasets, updated_utc=datetime.now(timezone.utc).isoformat())
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))
    print(f"{path}: {len(datasets)} entries, all DATA-02 fields present")


if __name__ == "__main__":
    main()
