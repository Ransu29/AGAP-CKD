"""Collect resumable ERA5-Land hourly temperature and precipitation for Laguna.

Default: 1991–2020 reference climate and January 2021 to September 2026
replay, with December 1990 padding before the reference. Credentials are read by cdsapi and never saved
in provenance. Jobs are persisted before polling, so restarting reuses the
same remote request instead of submitting duplicates. Existing verified files
are immutable. Six-month requests keep two-variable field counts below 12,000.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from zipfile import ZipFile

import cdsapi


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/raw/era5_land/laguna_replay"
DATASET = "reanalysis-era5-land"
AREA = [14.7, 120.9, 13.8, 121.7]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def save_json(path: Path, record: dict) -> None:
    temp = path.with_suffix(path.suffix + ".partial")
    temp.write_text(json.dumps(record, indent=2) + "\n")
    temp.replace(path)


def request_for(year: int, months: list[int]) -> dict:
    return {
        "variable": ["2m_temperature", "total_precipitation"],
        "year": str(year),
        "month": [f"{month:02d}" for month in months],
        # CDS ignores days that are not present in shorter months.
        "day": [f"{day:02d}" for day in range(1, 32)],
        "time": [f"{hour:02d}:00" for hour in range(24)],
        "data_format": "grib",
        "download_format": "zip",
        "area": AREA,
    }


def verify_archive(path: Path) -> dict:
    with ZipFile(path) as archive:
        if bad := archive.testzip():
            raise ValueError(f"Archive CRC failed for {bad}")
        entries = [info for info in archive.infolist() if not info.is_dir()]
        if not entries:
            raise ValueError("Archive contains no files")
        for entry in entries:
            with archive.open(entry) as stream:
                if stream.read(4) != b"GRIB":
                    raise ValueError(f"Unexpected non-GRIB archive member: {entry.filename}")
        return {
            "bytes": path.stat().st_size,
            "sha256": digest(path),
            "archive_members": [
                {"name": e.filename, "uncompressed_bytes": e.file_size, "crc32": f"{e.CRC:08x}"}
                for e in entries
            ],
        }


def collect(year: int, months: list[int], args: argparse.Namespace) -> str:
    period = f"{year}_{months[0]:02d}-{months[-1]:02d}"
    target = DEST / f"era5_land_{period}_temperature_precipitation.grib.zip"
    metadata = target.with_suffix(target.suffix + ".json")
    request = request_for(year, months)
    fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    existing_metadata = metadata.exists()
    record = json.loads(metadata.read_text()) if existing_metadata else {
        "dataset": DATASET,
        "dataset_url": "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land",
        "request": request,
        "request_sha256": fingerprint,
        "path": str(target.relative_to(ROOT)),
        "purpose": "1991–2020 reference and 2021–2026 historical replay; local-day boundary padding",
        "license": "CC BY 4.0; Copernicus Climate Change Service information",
        "created_at_utc": utc_now(),
    }
    if record.get("request_sha256") != fingerprint:
        raise ValueError(f"Request mismatch; refusing to reuse {metadata.name}")
    if target.exists():
        checked = verify_archive(target)
        if record.get("sha256") and record["sha256"] != checked["sha256"]:
            raise ValueError(f"Checksum mismatch for existing {target.name}; refusing replacement")
        record.update(checked, status="complete", verified_at_utc=utc_now())
        save_json(metadata, record)
        print(f"Verified cached {period}: {checked['bytes']:,} bytes", flush=True)
        return "cached"
    if args.offline:
        print(f"Missing {period} (offline check)", flush=True)
        return "missing"
    if existing_metadata and record.get("status") == "submitting" and not record.get("request_id"):
        raise RuntimeError(
            f"{period}: previous submission has no acknowledgement. Reconcile the CDS job list "
            "and add its request_id to metadata before retrying, to avoid duplicate jobs."
        )
    if record.get("status") in {"failed", "rejected", "dismissed", "deleted"}:
        if not args.retry_failed:
            raise RuntimeError(f"{period}: saved remote job failed. Inspect metadata; use --retry-failed to resubmit explicitly.")
        record.setdefault("previous_jobs", []).append({
            "request_id": record.pop("request_id", None),
            "status": record.get("status"),
        })
    client = cdsapi.Client(
        timeout=args.timeout, retry_max=3, sleep_max=10, quiet=True,
        progress=False, wait_until_complete=False,
    )
    if record.get("request_id"):
        remote = client.client.get_remote(record["request_id"])
        print(f"Resuming {period}: {record['request_id']}", flush=True)
    else:
        # Record intent before submitting. Do not retry failed POSTs ourselves:
        # if acknowledgement is lost, the operator can reconcile CDS jobs.
        record.update(status="submitting", last_checked_at_utc=utc_now())
        save_json(metadata, record)
        remote = client.retrieve(DATASET, request)
        record.update(request_id=remote.request_id, status="submitted", submitted_at_utc=utc_now())
        save_json(metadata, record)
        print(f"Submitted {period}: {remote.request_id}", flush=True)
    if args.submit_only:
        return "submitted"
    last_status = None
    while True:
        status = remote.status
        record.update(status=status, last_checked_at_utc=utc_now())
        save_json(metadata, record)
        if status != last_status:
            print(f"{period}: {status}", flush=True)
            last_status = status
        if status == "successful":
            break
        if status not in {"accepted", "running"}:
            raise RuntimeError(f"{period}: remote status {status}; saved request ID allows diagnosis")
        time.sleep(args.poll_seconds)
    partial = target.with_suffix(target.suffix + ".partial")
    remote.download(str(partial))
    checked = verify_archive(partial)
    partial.replace(target)
    record.update(checked, status="complete", retrieved_at_utc=utc_now(), verified_at_utc=utc_now())
    save_json(metadata, record)
    print(f"Saved {period}: {checked['bytes']:,} bytes, {len(checked['archive_members'])} GRIB members", flush=True)
    return "downloaded"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", help="Subset of calendar years; defaults to entire protocol")
    parser.add_argument("--months", type=int, nargs="+", choices=range(1, 13), help="Subset of months, applied to each --years year")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--poll-seconds", type=float, default=15)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--submit-only", action="store_true", help="Submit at most --workers jobs and exit")
    parser.add_argument("--retry-failed", action="store_true", help="Explicitly permit replacement of failed remote jobs")
    parser.add_argument("--offline", action="store_true", help="Only verify already downloaded archives")
    args = parser.parse_args()
    if args.months and not args.years:
        parser.error("--months requires --years")
    if args.poll_seconds < 1:
        parser.error("--poll-seconds must be at least 1")
    if any(year < 1950 or year > datetime.now().year for year in args.years or []):
        parser.error("Years must fall in the ERA5-Land record (1950 through current year)")
    credentials = ROOT / ".cdsapirc"
    if credentials.is_file() and "CDSAPI_RC" not in os.environ:
        os.environ["CDSAPI_RC"] = str(credentials)
    DEST.mkdir(parents=True, exist_ok=True)
    if args.years:
        jobs = [(year, sorted(set(args.months))) for year in args.years] if args.months else [
            (year, months) for year in args.years for months in (list(range(1, 7)), list(range(7, 13)))
        ]
    else:
        # Replay first: it makes the working demonstration available while the
        # longer reference period downloads. Within replay, newest years first.
        # Periods must not overlap (prepare_history rejects overlap) and must
        # match archives already collected, so 2017 keeps its earlier December
        # padding file and 2026 stops at the last complete month.
        halves = (list(range(1, 7)), list(range(7, 13)))
        jobs = [(2026, list(range(1, 7))), (2026, [7, 8, 9])]
        jobs += [(year, months) for year in range(2025, 2017, -1) for months in halves]
        jobs += [(2017, list(range(1, 7))), (2017, list(range(7, 12))), (2017, [12])]
        jobs += [(year, months) for year in range(2016, 2010, -1) for months in halves]
        jobs += [(1990, [12])]
        jobs += [(year, months) for year in range(1991, 2011) for months in halves]
    if args.submit_only:
        jobs = jobs[:args.workers]
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(collect, year, months, args): (year, months) for year, months in jobs}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                period = futures[future]
                # API exception bodies can include URLs. Print type and a short
                # diagnostic, never headers, client objects, keys or credentials.
                message = str(exc).splitlines()[0][:300]
                failures.append(period)
                print(f"FAILED {period}: {type(exc).__name__}: {message}", file=sys.stderr, flush=True)
    if failures:
        print(f"{len(failures)} request(s) failed; metadata and completed files retained.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
