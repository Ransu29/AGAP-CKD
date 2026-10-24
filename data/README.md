# Data

Most data files are **not committed**; folders are kept with `.gitkeep`. The exceptions are small or shared sources the team needs without a download key: the ERA5-Land ARCO extract (`raw/era5_land/arco/`), administrative boundaries, the PhilHealth YAKAP, FNRI and PAGASA source PDFs, and the small derived tables listed below.

| Folder | Contents | How it is produced |
|---|---|---|
| `raw/` | Downloaded public inputs (WorldPop, boundaries, facility list, OSM roads, ERA5-Land, ENSO index, PSA, Open-Meteo) | `make data`, `make collect-climate-arco` and the `scripts/collect_*.py` scripts (sources in `data/manifest.yaml`) |
| `processed/` | Cleaned inputs aggregated to H3 cells | `make data` |
| `synthetic/` | Simulated individuals, reports, and test results | `make simulate` |

All individual-level records are synthetic. Generator parameters and their provenance are in `config/parameter_register.yaml`.

## Small committed derived tables (analyst view)

These are committed so the analyst view and its tests work without the WorldPop rasters, which are not tracked.

| File | Contents | Source and method |
|---|---|---|
| `processed/public/laguna/municipal_adults.csv` | Adults 18+ per municipality, PRD v3 age-group shares, female share | WorldPop 2020 constrained age-sex rasters, 1 km (CC BY 4.0, © WorldPop), clipped with geoBoundaries ADM2/ADM3. `python scripts/build_municipal_adults.py`. Modelled estimates, not the PSA census |
| `processed/public/laguna/municipal_era5_cells.csv` | Each municipality's adults split across ERA5-Land 0.1° cells | Same script; weights population-weight the climate context |
| `processed/public/laguna/municipal_adults_notes.json` | Source, method and caveat for the two tables | Same script |
| `processed/public/laguna/municipal_population_psa2024.csv` | 2024 total population and estimated adults (18+) per municipality: the coverage denominator | PSA 2024 Census of Population via OpenSTAT (tables 0041A6DTPH3, 0201A6DPAG0). `python scripts/collect_psa_population.py`. Adults = municipal total x Laguna's 18+ share, because PSA publishes age groups by province only |
| `processed/public/laguna/age_structure_psa2024.csv` | Laguna adult shares in the 5 PRD v3 age groups: the age-standardisation weights | Same script and tables |
| `processed/public/laguna/population_psa2024_notes.json` | Source, method and adult share | Same script |
| `processed/public/laguna/heat_index_daily_era5land.csv` | Daily maximum heat index and temperature per ERA5-Land cell, Oct 2025 – Sep 2026 | Open-Meteo archive, ERA5-Land model (Copernicus, CC BY 4.0): hourly temperature and humidity. `python scripts/collect_heat_index.py`; NWS heat index formula in `src/agap/climate/heat_index.py`. Cells over Laguna de Bay take the nearest land grid point |
| `processed/public/laguna/barangays_psa2024.csv` | Laguna's 681 barangays with 2024 population, per municipality: the field tablet's check record (never used in the score) | Same PSA script and table (0041A6DTPH3) |

Raw downloads stay uncommitted: `raw/psa/openstat/` (PSA CSVs + manifest) and `raw/open_meteo/` (hourly Parquet + manifest). The scripts re-download them when missing.

**Building the analyst view on a fresh clone** (outputs are git-ignored):

1. `make prepare-climate`: ERA5-Land daily table from the committed ARCO extract.
2. `make triage`: the frozen PRD v3 risk-level run (model, cut-offs, benchmark).
3. `make analyst`: `outputs/analyst/{overview,climate,model_quality}.json`, served by `make api`.

Without these the analyst API returns 503 with the command to run.
