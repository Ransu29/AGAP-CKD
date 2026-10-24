"""Download one month of ERA5-Land temperature and rainfall from Copernicus."""
from __future__ import annotations

import argparse
import calendar
import os
from pathlib import Path
from zipfile import ZipFile

import cdsapi


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2021)
    parser.add_argument("--month", type=int, choices=range(1, 13), default=1)
    parser.add_argument(
        "--area", type=float, nargs=4, default=[17.2, 119.3, 13.8, 123.6],
        metavar=("NORTH", "WEST", "SOUTH", "EAST"),
    )
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--retry-max", type=int, default=10)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    credentials = root / ".cdsapirc"
    if credentials.is_file() and "CDSAPI_RC" not in os.environ:
        os.environ["CDSAPI_RC"] = str(credentials)

    request = {
        "variable": ["2m_temperature", "total_precipitation"],
        "year": f"{args.year:04d}",
        "month": f"{args.month:02d}",
        "day": [f"{day:02d}" for day in range(1, calendar.monthrange(args.year, args.month)[1] + 1)],
        "time": [f"{hour:02d}:00" for hour in range(24)],
        "data_format": "grib",
        "download_format": "zip",
        "area": args.area,
    }
    output = root / "data" / "raw" / "era5_land"
    target = output / f"era5_land_{args.year:04d}_{args.month:02d}_temperature_precipitation.grib.zip"
    if target.exists():
        raise SystemExit(f"Refusing to overwrite existing download: {target}")

    client = cdsapi.Client(timeout=args.timeout, retry_max=args.retry_max)
    output.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")
    print(f"Requesting {args.year:04d}-{args.month:02d}, all days and hours; area={args.area}", flush=True)
    client.retrieve("reanalysis-era5-land", request, str(partial))
    with ZipFile(partial) as archive:
        if archive.testzip() is not None:
            raise SystemExit("Downloaded archive failed its integrity check.")
        if not archive.namelist():
            raise SystemExit("Downloaded archive is empty.")
        print(f"Archive verified: {len(archive.namelist())} entries", flush=True)
    partial.replace(target)
    print(f"Saved: {target}", flush=True)


if __name__ == "__main__":
    main()
