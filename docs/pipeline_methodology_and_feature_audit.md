# AGAP-CKD data pipeline: methodology and feature audit

Prepared 23 October 2026, from the code at commit `3a8a054`. Code references take the form `file:line`.

> All patient-level records are synthetic. Model outputs are **screening flags used to set priorities**. They are not diagnoses, CKD case counts or medical advice.

---

## 1. Overview

```
 COLLECT (manual, outside make all)       PREPARE (offline)              RUN (make all → outputs/runs/<id>/)
 ─────────────────────────────────        ─────────────────              ───────────────────────────────────
 geoBoundaries ADM2/ADM3  ─┐                                             1 data          H3 frame, facilities, climate snapshot
 WorldPop 2020 age–sex    ─┼─ make collect ─ make prepare-public ──┐     2 simulate      synthetic residents (train/val/deploy)
 PhilHealth YAKAP PDF     ─┘                (clinic queue, temps)  │     3 train         3 logistic models + thresholds
 ERA5-Land hourly (ARCO / CDS) ─ collect-climate[-arco] ─ prepare- ┼──▶  4 allocate      6 invitation policies under budget
 FNRI 2023 NNS (calibration)   ─ scripts/calibrate_traits.py       │     5 evaluate      metrics.csv, report.html, chart
 PAGASA ENSO advisory (stored only, unused)                        │     6 spatial       H3 res-7 sensitivity (GEO-04)
 OpenFreeMap tiles ─ make collect-map (display only)               │     7 longitudinal  90/180-day follow-up (SIM-09)
                                                                   │     8 surveillance  monthly series + forecast check
 config/*.yaml  (seeds, thresholds, scenario) ─────────────────────┘     9 integrity     INT-01/INT-02 checks
                                                                                     ▼
                                                     Streamlit app (make demo): Plan → approved Worklist → events
```

The orchestrator is `agap.experiment.execute` (`src/agap/experiment.py:659`). Each Makefile target is a thin script that calls one stage of it (`scripts/*.py` → `agap.cli`).

**Run identity.** A run directory is `outputs/runs/<config-hash>-<source-hash>-<input-hash>` (`experiment.py:85`). The three parts hash the configuration, every `src/agap/*.py` file, and the SHA-256 of every raw input (WorldPop, boundaries, climate and weather files). Changing a parameter, a line of code or an input file creates a new run and never overwrites an earlier one. `manifest.json` records the following for each run:
- the configuration;
- the git commit;
- package versions;
- the status of each stage;
- a list of limitations.

Every file is written atomically: a `.partial` file is written first, then `os.replace`.

### Configuration profiles

| Profile | Geography | Climate | Use |
|---|---|---|---|
| `config/params.yaml` | `fixture`: a synthetic box over Laguna with uniform population | `synthetic`: a sinusoidal fixture signal | Unit-test and CI-speed runs |
| `config/fast.yaml` / `full.yaml` | as params | as params | NFR-07 runtime profiles (2k×5, 10k×200) |
| `config/public.yaml` | WorldPop + geoBoundaries (Laguna) | synthetic | Real population, fake climate |
| `config/weather_preview.yaml` | public | Observed 7/30-day weather for **display only** (`model_use=False`) | Weather context in the app |
| `config/climate.yaml` | public | ERA5-Land `hot_dry_score` (a model feature) | **Recommended demo profile** |

Profiles inherit from one another through `extends:` (`src/agap/config.py:19`).

---

## 2. Data collection

| Source | Collector | What is kept | Used for | Status |
|---|---|---|---|---|
| geoBoundaries gbOpen PHL ADM2/ADM3 (2020) | `scripts/collect_data.py` | Simplified GeoJSON + release metadata | Province clip; municipality assignment | Committed in `data/raw/boundaries/` |
| WorldPop 2020 1 km age–sex rasters (28 rasters: F/M × 15–80+) | `collect_data.py --demographics` | GeoTIFFs | Population frame and cohort sampling | Downloaded on demand (~96 MB); **unconstrained** product, whereas SRS DATA-01 asks for the constrained one |
| ERA5-Land hourly 2 m temperature + total precipitation, Dec 1990–Sep 2026 | `collect_climate_arco.py` (ECMWF ARCO Zarr) or `collect_climate.py` (CDS GRIB, 74 half-year jobs) | Yearly parquet (ARCO); zipped GRIB (CDS) | Climate exposure | ARCO extract committed and checksummed; CDS kept as a cross-check (matches within GRIB packing precision) |
| PhilHealth YAKAP register (PDF) | `prepare_public_data.py` | Names and addresses of Laguna facilities, no coordinates | Clinic **verification queue** only | Not an operational facility network |
| FNRI 2023 NNS summit deck | manual | PDF | Calibrating `dm_intercept` (`scripts/calibrate_traits.py`) | High fasting glucose stands in for self-reported DM (definitional mismatch is recorded) |
| PAGASA ENSO advisory No. 7 | manual | PDF | Nothing (E2-05) | Stored only |
| OpenFreeMap / OSM vector tiles | `collect_basemap.py` | 379 tiles, zoom 7–12 | App basemap only | Never a model input or a travel-time source |

Provenance follows SRS DATA-02. `scripts/update_manifest.py` writes `data/manifest.yaml`. It joins the metadata each collector recorded (URL, checksum, retrieval time) to the source-family metadata in `src/agap/data/sources.py:SOURCES` (publisher, licence, CRS, units, processing, limitations). An entry with any `REQUIRED_FIELDS` missing fails `tests/test_manifest.py`.

**Collection rule.** A changed remote file is never silently swapped in for a downloaded one. A missing province or municipality stops the build (DATA-03). No missing real input is ever replaced by fabricated data.

---

## 3. Processing

### 3.1 Population frame (stage `data`, `src/agap/data/geography.py`)

1. **Fixture mode** (`fixture_geography`): a box at H3 resolution 8 (121.05–121.5°E, 14.1–14.45°N) in five vertical "Fixture zones". It has one adult per cell × sex × 5-year band.
2. **Public mode** (`public_geography`):
   - Select the Laguna ADM2 polygon by name.
   - Keep each ADM3 municipality whose representative point falls inside a 0.002° buffer of that polygon.
   - Clip every WorldPop age–sex raster to the province.
   - Assign each valid pixel centre to an H3 resolution-8 cell, and sum population by `(h3, female, age_start)`.
   - Count only 2/5 of the 15–19 band (`adult_fraction_15_19 = 0.4`; ages 18–19 are 2 of its 5 years).
   - Give each H3 cell its municipality by point-in-polygon. A cell on a border takes the *closest* polygon.
3. **Population conservation (GEO-02)**: the source total, the age–sex table total and the cell total must agree within a relative 1e-6 (`population_check`). The result is written to `population_check.json`.
4. **Climate key**: `era5_cell` is the cell centre rounded to the 0.1° ERA5-Land grid. `h3_parent` is the resolution-7 parent, used in the spatial sensitivity analysis.
5. **Service points**: one hypothetical facility per municipality, at the populated cell nearest the population-weighted centroid. Each has `capacity = slots_per_facility` (100) and `verification_status="hypothetical"`.

### 3.2 Climate exposure (`make prepare-climate`, `src/agap/climate/history.py`)

1. **Hourly → local day.**
   - Convert UTC to Asia/Manila.
   - CDS rainfall arrives as accumulations within each forecast cycle (steps 1–24 from 00 UTC). It is differenced back to hourly amounts. A gap or a break in the cycle stays missing; it never becomes a dry hour.
   - Negative rounding noise down to −0.001 mm becomes 0. Anything more negative becomes missing (`clip_rain_noise`).
   - A rain interval that ends exactly at local midnight belongs to the day before.
   - A day is complete only when it has 24 valid hours for **each** variable.
2. **Windows.** Each cutoff date gets a 30-day window (and a descriptive 7-day window) of the full local days **strictly before** the cutoff. The cutoff day itself is excluded (`.shift(1)`).
3. **Reference.** The WMO 1991–2020 normal, by `era5_cell × calendar month`, is built from complete windows only. Every baseline year must have ≥ 90% complete windows. If the reference is incomplete there is no fallback: the exposure stays missing.
4. **Exposure score:**

   ```
   temperature_anomaly_z = (mean Tmax over 30 d − reference mean) / reference SD
   rainfall_deficit_z    = (reference mean rain − 30-day rain total) / reference SD
   hot_dry_score         = (temperature_anomaly_z + rainfall_deficit_z) / 2
   ```

   When a reference SD is 0, the scale is set to 1 and flagged. The score is an **assumed exposure index for the community**, not a heat index and not a personal exposure.
5. **Run snapshot** (`climate/integration.py:snapshot_climate`):
   - A source cell is admitted only if it has ≥ 95% complete dates in **every** partition.
   - A populated H3 cell whose own source cell fails that test (lakeshore cells over Laguna de Bay) is moved to the nearest supported land cell within 15 km (GEO-05). Its original cell is kept in `era5_cell_source`.
   - Cells with no supported source cell within that distance are excluded. The share of the population still represented is disclosed in `climate_frame.json`.
6. **Validation** (`validated_exposure`): keys are unique; the cutoff is a naive local midnight; scores are finite; each window ends at cutoff − 1 day and starts at cutoff − 30 days.

In **synthetic mode** the score is `sin(2π·doy/365.25) + cos(hash-phase of the cell)` (`experiment.py:106`). It is deterministic and lies in [−2, 2]. It is not a standard-normal variable.

### 3.3 Synthetic cohort (stage `simulate`, `experiment.py:125`)

The steps below run for each partition and repetition. Random-number streams are keyed `SeedSequence([repetition, component, seed])`, so a stream cannot shift when an unrelated stream changes.

1. **Geographic holdout.** 20% of populated ERA5 cells (at least 1, from at least 5 groups) are set aside for deployment only. Training and validation sample from the remaining cells.
2. **Time partitions.**

   | Partition | Dates |
   |---|---|
   | Training | 2021–2023 |
   | Validation | 2024 |
   | Deployment | Jan 2025 – Sep 2026, covering the cited 2026 El Niño |

   Each partition contains different residents (n = 3000 / 1500 / 3000).
3. **Residents.**
   - Each resident is drawn in proportion to `adult_count` over (h3, sex, age band).
   - Age is uniform within the band. The open 80+ band runs to 95.
   - `representation_weight` is the number of adults in the frame divided by n (equal within a cohort).
   - `cutoff` is the screening date. In ERA5 mode it is sampled from that cell's complete exposure dates, and `hot_dry_score` is joined **before** the outcome is synthesised.
4. **Hidden traits.**

   | Trait | Generator | Parameters |
   |---|---|---|
   | `dm_true` | logistic in age | `dm_intercept = −2.2665`, calibrated to FNRI |
   | `htn_true` | logistic in age + DM | `htn_intercept = −1.7`, `htn_dm_log_odds = 0.6` |
   | `family_true` | Bernoulli | 0.18 |
   | `outdoor_true` | Bernoulli | 0.30 |

5. **Hidden outcome.** The outcome is an *abnormal initial screen*, not CKD:

   ```
   logit P(y_true) = −3.5 + 0.045(age−40) + 1.0·DM + 0.8·HTN + 0.35·family + 0.2·outdoor + ln(heat_or)·hot_dry_score
   ```

6. **Labs, synthesised outcome-first.**
   - Each positive gets a subtype: renal (eGFR 30–59.9), albuminuric (uACR log-normal around 80, floored at 30), or both.
   - Negatives get eGFR 65–120 and uACR below 29.9.
   - Creatinine is the exact inverse of CKD-EPI 2021 (`simulate/kidney.py`).
   - eGFR is recomputed from that creatinine, and the run aborts if `eGFR<60 or uACR≥30` does not reproduce `y_true`.
7. **Participation (OBS-01).** The mechanism is MCAR, MAR or MNAR.
   - *Questionnaire reporting*: base rate 0.30. Under MAR and MNAR it also depends on age and nearest-facility distance. Under MNAR only, it also depends on `y_true`. Probabilities are clipped to [0.03, 0.97].
   - *Round-0 invitation*: depends on reporter status × proximity, `exp(−d/40)`.
   - *Completion*: base rate 0.70, with a distance term (MAR/MNAR) and a `y_true` term (MNAR).
   - The observed label exists only for round-0 completers.
   - Deployment residents carry **no** observed labels; their outcomes are potential outcomes only.
8. **Report details (SIM-02, E1-08)**, on a separate stream (`+20000`):
   - prior screening;
   - outdoor hours over 7 days;
   - the date the report became available and the event date.

   A report that becomes available after the cutoff is masked to NaN for every report field.

Outputs: `{train,validation,deployment}_hidden.parquet` and `split.json`.

### 3.4 Risk models (stage `train`, `experiment.py:308`)

| Model | Features | Weights |
|---|---|---|
| `clinical` | `age, female, dm_report, htn_report, family_report, outdoor_report` | none |
| `climate` | clinical + `hot_dry_score` | none |
| `ipw_climate` | clinical + `hot_dry_score` | 1/`observation_probability` known to the simulator, capped at the 99th percentile and normalised. This is an **oracle** weight, not a deployable correction |

- **Pipeline**: median imputation → standard scaling, plus a missingness indicator for every feature (`MissingIndicator(features="all")`) → `LogisticRegression(C=1.0)`.
- **Fitting**: only training residents whose label was observed (round-0 completers).
- **Leakage guard**: `check_allowed_features` takes an allowlist and a denylist (`config.models.forbidden_features`). The allowlist fails closed.
- **Thresholds**: for target sensitivities of 0.80 and 0.90, take the largest score threshold that reaches the target on **observed** validation labels. If there are fewer than 10 validation positives, the threshold is `unsupported` and the flag is NaN.
- **Metrics** (`model_metrics.csv`), computed on deployment against hidden `y_true` (simulation evaluation only), both for all residents and for reporters only:
  - AUROC and AUPRC;
  - Brier score;
  - sensitivity, specificity and FNR at each threshold;
  - calibration intercept and slope from a logistic recalibration.

### 3.5 Allocation (stage `allocate`, `experiment.py:472`)

The input is the deployment cohort scored by the `climate` model (0.90 target).

| Policy | Rule |
|---|---|
| `random` | Random permutation |
| `population_proportional` | Largest-remainder quotas by the municipality's represented adults (ALLOC-08), then random order inside each municipality; unused quota is reassigned |
| `risk_ranked` | Descending score, ties broken by a per-resident uniform |
| `risk_explore_{10,20,30}` | That share of the budget goes first to a random order, the rest by risk |

**Constraints:**
- Budget of 500 tests.
- 100 slots per facility.
- Each resident goes to the nearest facility with a free slot within 20 km.
- Residents beyond 20 km of every facility are `outside access limit`.
- Optional coverage floors per municipality (ALLOC-12) are checked **before** allocation:
  - The budget must cover the total of all floors.
  - Each municipality must have enough residents and slots within reach.
  - All floors must fit together, checked with a max-flow over municipality → resident → facility.
  - A run whose floors are infeasible stops; floors are never relaxed.

**Completion** draws reuse each resident's uniform, so policies are compared on common random numbers. Under MAR and MNAR, completion is penalised for the extra distance between the assigned facility and the nearest one.

### 3.6 Evaluation and downstream stages

| Stage | Output | Content |
|---|---|---|
| `evaluate` | `metrics.csv`, `report.html`, `efficiency_coverage.png` | See below |
| `spatial` | `spatial_*` | The same residents moved to the centres of their H3 resolution-7 parents. Every policy is re-run with the same seeds; the difference measures the effect of geographic resolution (MAUP) |
| `longitudinal` | `longitudinal_metrics.csv` | Day-90 and day-180 creatinine (CV 5%) and uACR (CV 30%), eGFR decline of 1/yr, a hypothetical acute event (rate 2%, ×1.5 creatinine). "Persistent" means abnormal at day 0 **and** day 180. This is not CKD and not AKI |
| `surveillance` | `surveillance_monthly.parquet`, forecasts | 1000 synthetic screens per month, Jan 2021–Sep 2026. Seasonal-naive forecasts are compared with a regression on y(t−12), with and without the lagged hot-dry score. 12-month rolling-origin holdout, horizons of 1 and 3 months |
| `integrity` | `integrity.json` | INT-01: referential checks. INT-02: probabilities lie in [0, 1]; counts are non-negative |

`evaluate` reports, for each policy and subgroup (all, municipality, reporter status, age band, sex, outdoor work):
- invitations, completions and positives detected;
- yield per 100 completed;
- completion coverage and coverage among feasible residents;
- how missed positives break down: excluded by access, feasible but not invited, invited but did not complete;
- slot use;
- modelled cost per positive (₱500 per panel);
- counts weighted by the population each resident represents (EVAL-05).

`make experiments` (`src/agap/cli.py:32`) crosses 3 participation mechanisms × `heat_or ∈ {1.0, 1.2, 1.5}` × repetitions. It reports paired differences between policies, with Monte Carlo uncertainty labelled separately from variability across repetitions.

### 3.7 Final output and app

- **Run artefacts**, in `outputs/runs/<id>/`:
  - frozen inputs (parquet and geojson);
  - hidden cohorts;
  - models (`.joblib`);
  - `predictions.parquet`, `model_metrics.csv` and `weight_diagnostics.json`;
  - `allocations_hidden.parquet`, `coverage_check.json` and `metrics.csv`;
  - the report and chart;
  - files from the downstream stages;
  - `manifest.json`.

  `outputs/latest_run.json` points to the newest run that completed stages 1–5.
- **App** (`make demo`; `app/main.py`, `src/agap/workflow*.py`):
  - A **Plan**: an editable scenario of model, budget and strategy. A plan never changes an approved worklist.
  - A **Worklist**: a round snapshot that is saved and approved. It records events for contact, fictional lab results and declined slots, with replacement candidates.
  - CSV export of the invitations.
  - A comparison of the climate and questionnaire models on identical draws (`model_comparison.py`).
  - Hidden outcomes appear only in panels labelled "(eval)" (`decision_support.py`).

---

## 4. Feature audit (current state)

### 4.1 Model features

`leakage_scanner.py` was run on 23 Oct 2026 against `age,female,dm_report,htn_report,family_report,outdoor_report,hot_dry_score`: **PASS (7/7)**.

| Feature | Source | Available at prediction time? | Missingness | Notes |
|---|---|---|---|---|
| `age` | WorldPop band + uniform draw | Yes | None | Enters as a linear term; the simulator is also linear in age |
| `female` | WorldPop sex raster | Yes | None | **No effect in the outcome generator**, so it is pure noise in this simulation; kept for realism |
| `dm_report` | Self-report (Engine 1) | Yes, if reported before the cutoff | ~70% missing (non-reporters + late reports) | Perfect recall: report = truth when reported |
| `htn_report` | Self-report | Same | Same | Same |
| `family_report` | Self-report | Same | Same | Same |
| `outdoor_report` | Self-report | Same | Same | Binary only; the richer `outdoor_hours_7d_report` exists but is unused |
| `hot_dry_score` | ERA5-Land anomaly or the fixture signal | Yes; the window ends at cutoff − 1 | None after the climate frame filter | **Circular by construction**: the same variable enters the outcome generator with OR `heat_or` (§5.1) |
| missingness indicators (×7) | `MissingIndicator(features="all")` | Yes | n/a | All four report indicators are collinear (missing together); flags for always-present columns are all zero |

### 4.2 Columns generated but not used as features

| Column | Why it could matter | Status |
|---|---|---|
| `prior_screen_report` | Earlier screening changes both risk and participation | Generated (SIM-02), used only in the UI and research gateway |
| `outdoor_hours_7d_report` | A dose measure of heat exposure; interacts with `hot_dry_score` | Generated, unused |
| `nearest_distance_km` | Drives participation under MAR; useful for modelling propensity | Used in allocation only |
| `report_available_date − cutoff` (report age) | How stale the inputs are | Used only to mask late reports |
| 7-day climate window (`preceding_tmax_7d_c`, `preceding_precip_7d_mm`) | Acute heat or dehydration signal | Computed and shown in the app; not a feature |
| Municipality / H3 parent | Area-level baseline risk | Not a feature (correct for now; see §6.2) |

### 4.3 Forbidden columns (verified absent)

`creatinine, egfr, uacr, y_true`, every `*_90d` and `*_180d` follow-up column, `persistent_abnormal` and `transient_abnormal`, hidden traits (`*_true`), and research attributes. The rule is enforced in `train` (allowlist + denylist), in surveillance (hidden columns prefixed `hidden_` are rejected as forecast inputs) and by `tests/test_leakage.py`.

---

## 5. Audit findings

### 5.1 Methodological

1. **The climate model's advantage is built in.** `hot_dry_score` enters both the outcome generator (`experiment.py:173`) and the `climate` model, as the same variable with the same linear form. So the climate model has the correct functional form by design. Any AUROC gain over `clinical` is a property of the simulation, not evidence. The model card and the app should say so next to every comparison between the two models. A stress test with misspecification would show it (§6.3).
2. **Thresholds are set on a selected sample.**
   - The sensitivity threshold uses *observed* validation labels, which only round-0 completers have. Under MAR and MNAR these over-represent reporters, people near facilities and (under MNAR) negatives. The 0.90 target therefore holds for completers, not for the deployment population.
   - `ipw_climate` corrects the *fit* with weights, but its threshold is still taken from unweighted ROC points.
3. **The weights are oracle weights.** `ipw_climate` uses the true `observation_probability`. This is disclosed (`weight_source`), but no estimated-propensity version exists, so a deployable correction has never been tested.
4. **Self-reports are perfect.** When a resident reports, `*_report` equals `*_true`. There is no misclassification or under-awareness, yet undiagnosed DM and HTN are common in community screening. Model performance is optimistic.
5. **`female` has no causal role** in the generator, while the CKD-EPI equation depends on sex, so lab values differ by sex but the outcome does not. That is defensible, but the null effect should be recorded in the parameter register.
6. **Missingness indicators are collinear.** The four report indicators are identical, apart from late-report masking, which is also all-or-nothing. One `reported` indicator would carry the same information, and the model would be easier to interpret.
7. **Calibration is assessed only by intercept and slope.** There is no reliability curve, no net-benefit analysis in the pipeline, and no decision curve, although the project has `decision_curve.py` (AGENTS.md checklist item 5).
8. **The longitudinal "persistence" check ignores day 90.** It uses day 0 and day 180 only. That matches the KDIGO > 3-month rule. However, the uACR CV of 30% plus a floor at the uACR threshold means that many "transient" cases are measurement noise around 30 mg/g. Report sensitivity to the floor.

### 5.2 Configuration hygiene (CLAUDE.md rule 2: "never hardcode numbers")

| Hardcoded in code | Config key that exists but is **not read** |
|---|---|
| Policy list and exploration shares `(.1,.2,.3)` (`experiment.py:571`, `spatial.py:20`, `integrity.py:16`) | `allocation.policies` (with a different name, `risk_based`), `allocation.exploration_shares` |
| Sensitivity targets `(.8, .9)` (`experiment.py:344`); allocation uses `.9` (`:570`) | `triage.target_sensitivity: 0.90` |
| Scenario grid `MCAR/MAR/MNAR × heat_or (1.0,1.2,1.5)` (`cli.py:34-35`) | `scenarios.participation_mechanisms`, `scenarios.heat_effect: [zero, weak, strong]` |
| Spatial resolutions `{8: h3, 7: h3_parent}` (`spatial.py`) | `h3.sensitivity_resolutions: [7]` |
| — | `n_repetitions: 200` (`prototype.repetitions` is the one read) |
| Holdout share `.2` of climate cells (`experiment.py:275`), `LogisticRegression(C=1.0, max_iter=500)`, weight cap quantile (read) | none |
| `outcome.egfr_threshold` is not passed to `observed_screen_label` (defaults 60/30 in `kidney.py`) | `outcome.egfr_threshold`, `outcome.uacr_threshold` (only the uACR one is read, `experiment.py:183`) |

If someone edits those YAML keys, nothing changes.

### 5.3 Documentation drift

- `docs/synthesis_disclosure.md` still contains `TBD` in its generation steps, parameters and limitations. It lists "facility locations, roads" as real inputs, but facilities are hypothetical and roads are display only.
- `data/README.md` says that data files are not committed and that `make data` downloads them. In fact the ARCO climate extract and the boundaries **are** committed, and downloads go through `make collect*`.
- `docs/data_contracts.md` describes tables that do not exist (`h3_cells.parquet`, `scores.parquet`, `obs_*` columns, `heat_index`). The real contracts are the run artefacts in §3.7.
- `README.md` lists `src/agap/evaluate/` as the home of metrics. That package is empty; the metrics live in `experiment.py`.

### 5.4 Code structure

- `experiment.py` (712 lines) holds every stage: I/O, simulation, training, allocation and evaluation. `src/agap/models/`, `allocation/` and `evaluate/` are empty or nearly so, unlike the layout the README describes. This is not urgent, but it is why config keys drift unnoticed.
- `allocate_policy.pick` is a Python loop over residents with `frame.iloc[index]` inside it. It runs in O(n × facilities) with pandas overhead. That is fine at n = 3000, but it will dominate `full.yaml` (10k × 200 repetitions).

---

## 6. Planned and not yet implemented

This section draws on `docs/srs_traceability.md`, `prototype_plan.md`, `prototype_upgrade_spec_v2.0.md`, `revised_implementation_plan_2026-10-22.md`, `srs_erratum_v1.1.md` and the technical review.

**SRS status.** 114 of 118 requirements are ✅, 2 are partial and 2 are N/A.

| Requirement | Status | Detail |
|---|---|---|
| DATA-01 | Partial | Uses unconstrained WorldPop rather than the constrained product; no OSM roads, so distances are straight-line; only one PAGASA advisory |
| E2-05 | Partial | Advisory dates are kept, but advisories are not used in analysis |
| GEO-03/04 | Limited | No barangay boundaries, so sensitivity covers H3 7 vs 8 only |
| NFR-07/08 | Pending | The full 200-repetition Monte Carlo suite and the runtime of the real-data profile are "waiting on data" |

### 6.1 Data and collection
- Constrained WorldPop 2020; OSM road network and travel-time distances.
- Verified clinic coordinates and creatinine/uACR capability. No real confirmations have been supplied, and the YAKAP register is still a verification queue only.
- Definition-matched prevalence for HTN and self-reported DM (FNRI part 1 or PSA microdata).
- The full PAGASA advisory series, if ENSO is to be used.
- The SRS v1.1 erratum (the climate periods) is still a draft awaiting team sign-off.

### 6.2 Modelling and features
- An **estimated** observation-propensity model, replacing the oracle IPW (`prototype_plan.md` "Next work").
- Calibration plots and diagnostics for the population that completed tests.
- Repeated comparisons of the clinical and climate models over the scenario grid ("not built", per the handoff §6).
- Stronger spatial validation.
- P2 outdoor-hours report warning (`report_warnings`): **deferred**.
- BATO S1/S2/S3 risk stratification: **deferred**.
- The revised plan states that the care workflow "does not need another prediction model". Later comparisons against transparent criteria reviewed by a clinician depend on Gate 0, agreement with an RHU reviewer, which is not recorded.

### 6.3 Evaluation
- The persistence and climate comparisons rest on one run. In that run, the climate model's AUROC, AUPRC and Brier score were slightly *worse* than the clinical model's (`prototype_review_2026-10-21.md`).
- No usability study with health workers has been done.

### 6.4 Care-coordination layer (revised implementation plan, *proposed* and not started)
None of the `care_*.py` modules or `tests/test_care*` exist yet. The plan covers:
- storage v2 with seven care tables;
- legacy round import;
- idempotent commands;
- **Release A**: a continuing resident record, education and contact agreement (EN/FIL), Today's tasks, testing episodes and result review, referrals;
- **Release B**: a verified service finder, patient-reported BP, an LGU community dashboard, and four-destination navigation;
- acceptance tests AT-01 to AT-22 for care.

### 6.5 App and UI items still open from `ux_audit.md`
- Story tab, Analyst view, a result card, a disclaimer banner, and a plain-language pass. I found no matches in the code, so these appear unimplemented.
- Deliberately skipped: mobile layout, auto-plan.

### 6.6 Open items from the technical review
- The SRS never defines whether the cutoff boundary is `<` or `≤`. The code uses a strict `<` (the window ends at cutoff − 1).
- One ERA5 cell covers about 120 km², not 81. Distinct cells are not independent observations, which matters for the five-cell geographic holdout.
- Top-k allocation gives excluded residents an invitation probability of zero. Positivity therefore fails for any later outcome-weighted analysis of allocated residents.

---

## 7. Suggested improvements to the feature set

Ordered by value per unit of effort. Each one keeps the zero-leakage rule: every input must be known at the screening cutoff.

### 7.1 Use what is already generated (low effort)

| Change | Rationale | Where |
|---|---|---|
| Add `outdoor_hours_7d_report` in place of, or alongside, `outdoor_report` | A dose measure; enables the interaction below | `CLINICAL` list, `experiment.py:39` |
| Add `prior_screen_report` | A known predictor of both risk and participation | same |
| Replace the 7 missingness indicators with one `reported` flag | Removes collinearity; easier to interpret | `model_pipeline` |
| Add the interaction `outdoor_hours_7d_report × hot_dry_score` | Heat stress at work is the plausible pathway (CKDnT); a community index matters mainly for people outdoors | `model_pipeline` (`PolynomialFeatures(interaction_only)` on two columns, or a precomputed column) |
| Add the 7-day `preceding_tmax_7d_c` anomaly as a second climate feature | Separates acute heat or dehydration from 30-day dryness | already in `climate_exposure.parquet` |

Each change needs a matching change in the **generator** (an interaction term or 7-day effect with its own parameter in `params.yaml` and `parameter_register.yaml`). Otherwise the new feature is pure noise and the comparison says nothing. Run each change as an experiment arm with the effect set to zero and to non-zero.

### 7.2 Make the simulation honest about what the model can learn (medium)

1. **Misspecified climate arms.** Let the generator use a transform the model does not see, for example `max(0, hot_dry_score − 1)` (a threshold effect), or temperature only rather than the averaged score. That shows how much of the climate model's advantage survives a wrong functional form (finding 5.1-1).
2. **Self-report error.** Add `awareness` parameters (P(report = 1 | true = 1) < 1, small false positives) for DM and HTN, sourced from the awareness rates in the FNRI and NNS hypertension and diabetes data where available. This is the largest realism gain for the least code.
3. **A sex effect or explicit null.** Either give `female` a sourced log-odds or drop it from the model and record why.
4. **BMI / obesity and a history of cardiovascular disease.** These are standard CKD screening factors (KDIGO, CKD-PC). FNRI NNS publishes obesity prevalence, so the generator can be calibrated the same way as `dm_intercept`. Add them as hidden traits plus a self-reported (or measured, for BMI) feature.
5. **Use of nephrotoxic drugs or herbal remedies (NSAIDs).** This is cheap to ask on a questionnaire. Keep its effect "assumed" in the register until sourced.

### 7.3 Fix the parts that decide who gets invited (medium)

1. **Set the threshold with weights.** For `ipw_climate`, choose the threshold on a weighted ROC curve, or report the sensitivity achieved on all deployment residents next to the target so the gap is visible.
2. **Estimate propensities.** Add a model `ipw_estimated` that fits P(observed | age, distance, reported) on training residents (all of them, not only completers), with the same cap. It should sit next to the oracle IPW, so the gain from correcting selection bias can actually be deployed.
3. **Area-level random effect or municipality baseline.** Use this only if the generator gains area-level variation in risk. Today it has none, so the feature would only fit noise.
4. **Decision-curve analysis in the pipeline.** Call `compute_net_benefit` from `.agents/skills/ckd-health-data-scientist/scripts/decision_curve.py` on deployment predictions in `evaluate`, and add net benefit against test-all and test-none at threshold probabilities of 5–30% to `model_metrics.csv`.

### 7.4 Configuration clean-up (small, do first)

Wire up, or delete, the dead keys listed in §5.2. Change nothing else. Each wiring is a one-line change that reads the config value instead of the literal. Add one test per key, asserting that changing it changes the output. Deletion is the smaller change wherever nobody expects to vary the key. `scenarios.heat_effect` should map to `heat_or` values explicitly in YAML, for example `{zero: 1.0, weak: 1.2, strong: 1.5}`.

### 7.5 Not recommended

- **Municipality or H3 as categorical features.** No area-level variation in risk is simulated, so they would add parameters without adding signal, and they would encode the geographic holdout.
- **eGFR or uACR from round 0 as a feature for later rounds.** That is a leakage path: the denylist must keep blocking `creatinine`, `egfr` and `uacr`, including for repeat screens.
- **Gradient boosting or other complex learners.** The generator is logistic-additive, so a GLM is the correctly specified model. A complex learner would only matter after misspecified arms (7.2-1) exist.

---

## 8. Verification for this document

- `leakage_scanner.py` on the current feature list: PASS.
- No code was changed, so the parameter register and pytest checks were not re-run for this document. Run them for any change made from §7.
