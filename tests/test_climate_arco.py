"""ARCO ERA5-Land source: one rain rule, checksum-verified extracts, and equivalence with CDS GRIB."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pytest

from agap.climate.history import (
    RAIN_TOLERANCE_MM, _daily_parts, _finish_daily, _grib_messages, clip_rain_noise, deaccumulate_precipitation,
    prepare_history, read_archive_hourly, read_arco_hourly,
)
from agap.config import ROOT

CELLS = [("14.1,121.1", 14.1, 121.1), ("14.3,121.3", 14.3, 121.3)]


def test_one_rain_rule_for_every_source():
    rain = pd.Series([-0.0005, -RAIN_TOLERANCE_MM, -0.002, 0.0, 0.3])
    cleaned = clip_rain_noise(rain)
    assert cleaned.iloc[:2].tolist() == [0.0, 0.0] and np.isnan(cleaned.iloc[2]) and cleaned.iloc[3:].tolist() == [0.0, 0.3]


def test_hourly_rain_skips_deaccumulation():
    times = pd.date_range("2024-01-01 16:00", periods=48, freq="h", tz="UTC")  # local 2 and 3 January
    hourly = pd.DataFrame(dict(era5_cell="14.1,121.1", latitude=14.1, longitude=121.1, time_utc=times,
                               temperature_c=25.0, precip_mm=0.5))
    daily = _finish_daily(_daily_parts(hourly)).set_index("local_date")
    assert daily.loc["2024-01-02", "precip_mm"] == pytest.approx(12.0)  # 24 intervals: 01:00 through midnight ending 2 January
    assert daily.loc["2024-01-02", "tmean_c"] == 25.0


def write_extract(root, years=(2000, 2001, 2002)):
    """Small synthetic ARCO extract: two cells, hourly from 1 December 2000, with a yearly record."""
    folder = root / "data/raw/era5_land/arco"
    folder.mkdir(parents=True)
    files = {}
    for year in years:
        start = "2000-12-01" if year == 2000 else f"{year}-01-01"
        times = pd.date_range(start, f"{year}-12-31 23:00", freq="h")
        rows = []
        for cell, lat, lon in CELLS:
            rain = np.where(times.hour == 3, 0.001, -0.0000002)  # 1 mm at 03 UTC, rounding noise otherwise
            rows.append(pd.DataFrame(dict(time_utc=times, era5_cell=cell, latitude=lat, longitude=lon,
                                          t2m_k=np.float32(299.15), tp_m_hourly=rain.astype(np.float32))))
        name = f"era5_land_arco_{year}.parquet"
        pd.concat(rows).to_parquet(folder / name, index=False)
        files[name] = dict(sha256=hashlib.sha256((folder / name).read_bytes()).hexdigest())
    (folder / "era5_land_arco.json").write_text(json.dumps(dict(stores={}, retrieved_at_utc="2026-10-19T00:00:00+00:00", files=files)))
    return folder


def test_arco_source_prepares_daily_climate(tmp_path):
    write_extract(tmp_path)
    daily, exposure, metadata = prepare_history(tmp_path, 2001, 2001, source="arco")
    inside = daily[daily.local_date.between("2001-01-02", "2002-12-30")]
    assert inside.complete.all() and np.allclose(inside.tmean_c, 26.0, atol=1e-4)  # float32 299.15 K
    assert np.allclose(inside.precip_mm, 1.0, atol=1e-6)  # one 1 mm hour per local day; noise clipped to 0
    assert metadata["source_mode"] == "arco" and "ARCO" in metadata["rainfall_method"]
    assert exposure.complete.any()


def test_tampered_extract_is_rejected(tmp_path):
    folder = write_extract(tmp_path)
    frame = pd.read_parquet(folder / "era5_land_arco_2001.parquet")
    frame.loc[0, "t2m_k"] = 310.0
    frame.to_parquet(folder / "era5_land_arco_2001.parquet", index=False)
    with pytest.raises(ValueError, match="checksum"):
        prepare_history(tmp_path, 2001, 2001, source="arco")
    with pytest.raises(ValueError, match="source"):
        prepare_history(tmp_path, 2001, 2001, source="satellite")


CDS = ROOT / "data/raw/era5_land/laguna_replay/era5_land_2024_01-06_temperature_precipitation.grib.zip"
ARCO = ROOT / "data/raw/era5_land/arco/era5_land_arco_2024.parquet"


@pytest.mark.skipif(not (CDS.is_file() and ARCO.is_file()), reason="collected CDS and ARCO files not both present")
def test_arco_equals_cds_within_grib_precision():
    cds = read_archive_hourly(CDS)
    cds["precip_mm"] = deaccumulate_precipitation(cds)
    cds["era5_cell"] = cds.latitude.round(1).map("{:.1f}".format) + "," + cds.longitude.round(1).map("{:.1f}".format)
    arco = read_arco_hourly(ARCO)
    arco = arco[arco.time_utc.between(cds.time_utc.min(), cds.time_utc.max())]
    both = cds.merge(arco, on=["time_utc", "era5_cell"], how="outer", indicator=True, suffixes=("", "_arco"))
    assert both._merge.eq("both").all()
    assert (both.temperature_c.isna() == both.temperature_c_arco.isna()).all()
    packing = {"2t": 0.0, "tp": 0.0}
    with ZipFile(CDS) as zipped:
        data = zipped.read(next(name for name in zipped.namelist() if name.endswith(".grib")))
    import eccodes
    for message in _grib_messages(data):
        handle = eccodes.codes_new_from_message(message)
        try:
            name = eccodes.codes_get(handle, "shortName")
            packing[name] = max(packing[name], eccodes.codes_get(handle, "packingError"))
        finally:
            eccodes.codes_release(handle)
    land = both.temperature_c_arco.notna()  # lake and sea cells are missing in both (checked above)
    kelvin = both.temperature_c_arco[land] + 273.15
    t_limit = packing["2t"] + np.spacing(kelvin.astype(np.float32)).astype(float)
    assert ((both.temperature_c[land] - both.temperature_c_arco[land]).abs() <= t_limit).all()
    rain = both.precip_mm.notna() & both.precip_mm_arco.notna()
    r_limit = 1000 * (2 * packing["tp"] + 2 * np.spacing(both.precip_accum_m.abs().astype(np.float32)).astype(float))
    assert ((both.precip_mm - both.precip_mm_arco).abs()[rain] <= r_limit[rain]).all()
