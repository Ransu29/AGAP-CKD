"""Climate integration: lake-masked source cells and months without climate data."""
import copy
import json

import numpy as np
import pandas as pd
import pytest

from agap.climate.integration import PARTITION_DATES, snapshot_climate
from agap.config import ROOT, load_config
from agap.data.geography import make_geography
from agap.surveillance import simulate_panel

DATES = pd.date_range(PARTITION_DATES["train"][0], PARTITION_DATES["deployment"][1], freq="D")


def exposure_for(cells, masked=(), gap_month=None):
    """Complete daily exposure for each source cell; masked cells and the gap month are incomplete."""
    rows = []
    for cell in cells:
        complete = np.full(len(DATES), cell not in masked)
        if gap_month is not None:
            complete &= DATES.to_period("M") != pd.Period(gap_month)
        rows.append(pd.DataFrame(dict(era5_cell=cell, cutoff=DATES, complete=complete,
                                      hot_dry_score=np.where(complete, 0.5, np.nan),
                                      window_start=DATES - pd.Timedelta(days=30), window_end=DATES - pd.Timedelta(days=1))))
    return pd.concat(rows, ignore_index=True)


def climate_config(tmp_path, exposure, **climate):
    source = tmp_path / "climate"
    source.mkdir()
    exposure.to_parquet(source / "exposure.parquet", index=False)
    for name in ("daily", "baseline"):
        pd.DataFrame({"era5_cell": []}).to_parquet(source / f"{name}.parquet", index=False)
    (source / "metadata.json").write_text("{}")
    cfg = load_config("config/climate.yaml")
    cfg["climate"].update(processed_directory=str(source), **climate)
    return cfg


LAND = ["14.1,121.1", "14.1,121.2", "14.1,121.3", "14.3,121.1", "14.3,121.3", "14.3,121.5"]
LAKE = "14.2,121.3"


def population():
    """One H3 area at each land cell, two lakeshore areas inside the lake cell, one far away."""
    points = [(cell, *map(float, cell.split(","))) for cell in LAND]
    points += [(LAKE, 14.17, 121.30), (LAKE, 14.22, 121.32), ("13.5,120.5", 13.5, 120.5)]
    cells = pd.DataFrame([dict(h3=f"h{i}", latitude=lat, longitude=lon, municipality="Area", adult_count=100.0, era5_cell=cell)
                          for i, (cell, lat, lon) in enumerate(points)])
    demographics = cells[["h3"]].assign(female=0, age_start=40, adult_count=100.0)
    return cells, demographics


def test_lakeshore_areas_take_the_nearest_supported_cell(tmp_path):
    cells, demographics = population()
    cfg = climate_config(tmp_path, exposure_for(LAND + [LAKE, "13.5,120.5"], masked=(LAKE, "13.5,120.5")))
    directory = tmp_path / "run"
    directory.mkdir()
    selected, kept = snapshot_climate(cfg, ROOT, directory, cells, demographics)
    lakeshore = selected[selected.era5_cell_source.eq(LAKE)]
    assert len(lakeshore) == 2 and lakeshore.climate_reassigned.all()
    assert set(lakeshore.era5_cell) <= set(LAND)
    assert lakeshore.climate_reassignment_km.between(0, 15).all()
    assert not selected.loc[~selected.era5_cell_source.eq(LAKE), "climate_reassigned"].any()
    assert "h8" not in set(selected.h3) and "h8" not in set(kept.h3)  # far area: nothing within 15 km
    record = json.loads((directory / "climate_frame.json").read_text())
    assert record["reassignment"]["h3_cells_reassigned"] == 2 and record["reassignment"]["h3_cells_still_excluded"] == 1
    assert record["reassignment"]["adults_reassigned"] == 200.0
    assert record["modeled_population_fraction_supported"] == pytest.approx(8 / 9)


def test_reassignment_limit_is_respected(tmp_path):
    cells, demographics = population()
    cfg = climate_config(tmp_path, exposure_for(LAND + [LAKE], masked=(LAKE,)), max_reassignment_km=1)
    directory = tmp_path / "run"
    directory.mkdir()
    selected, _ = snapshot_climate(cfg, ROOT, directory, cells, demographics)
    assert not selected.era5_cell_source.eq(LAKE).any() and not selected.climate_reassigned.any()


def test_surveillance_skips_a_month_without_climate_instead_of_failing():
    cfg = copy.deepcopy(load_config("config/climate.yaml"))
    cfg["prototype"]["geography_mode"] = "fixture"
    cfg["surveillance"]["monthly_sample"] = 20
    cells, demographics, facilities, _ = make_geography(cfg, ROOT)
    panel = simulate_panel(cfg, cells, demographics, facilities, exposure=exposure_for(sorted(cells.era5_cell.unique()), gap_month="2022-03"))
    assert panel.attrs["months_without_climate"] == ["2022-03"]
    assert pd.Timestamp("2022-03-01") not in set(panel.month)
    assert panel.month.nunique() == len(pd.period_range(DATES[0], DATES[-1], freq="M")) - 1
    with pytest.raises(ValueError, match="No surveillance month"):
        simulate_panel(cfg, cells, demographics, facilities, exposure=exposure_for(sorted(cells.era5_cell.unique()), masked=set(cells.era5_cell)))
