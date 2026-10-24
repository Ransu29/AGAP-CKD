# AGAP-CKD — Proposed SMART Data Specification

**Version:** 3, data-first working proposal. **Date:** 23 October 2026, Asia/Manila. **Status:** proposed field contracts, not implemented collection or verified source schemas.

This narrows the [candidate inventory](../../evidence/2026-10-23-proposed-data-inventory.md). Model, simulation and feature selection follow data feasibility. It does not select a simulation, reinstate the withdrawn overlap scenario, authorize real-data collection or settle the detailed citizen-interface design. The citizen-facing interface remains in product scope; only its design discussion was paused. Fictional profiles can stand in for citizen input during the competition.

## 1. What SMART means here

- **Specific:** name the field, unit, allowed values and original source.
- **Measurable:** define validation and completeness checks; show missingness rather than require invented answers.
- **Achievable:** distinguish locally secured files, obtainable candidates and unavailable dependencies; use voluntary information people already know.
- **Relevant:** attach every field group to a bounded analytical question; no automatic model-feature inclusion.
- **Time-bound:** preserve source/reference periods, observation dates and an explicit run cutoff. Acceptance gates occur before analysis/collection, not on invented delivery dates.

Scope: adults for the proposed competition, subject to explicit source-cohort eligibility; no claim of pediatric validation. Citizen diagnosis state is reported, not clinically established by AGAP. “No” to a known diagnosis means no known diagnosis, not no disease.

## 2. Public-data contracts

**Core candidate** means needed if that analysis is retained, not already secured. Existing facts/access qualifications are catalogued in the inventory; public source pages alone do not establish file-level usability.

| ID / priority | Exact required fields | Source / feasibility | Measurable acceptance and time rule | Purpose / exclusion |
|---|---|---|---|---|
| PD-01 core population | `area_id`, `area_code_system`, `area_version`, `age_band`, `sex_category` if supplied, `population_count`, `population_type`, `reference_year` | PSA census preferred for compatible totals; WorldPop optional for gridded distribution. PSA local detail pending; raw WorldPop absent at inspection. The only saved run inspected is fixture geography, not a secured public population frame. | Counts nonnegative; bands/population type explicit; totals reconciled at a common scope with disclosed tolerance. Freeze source/checksum for the run. Never relabel 2020 as 2026. | Defined population denominators; no resident-level claims. |
| PD-02 core geography | `area_id`, `source_area_name`, `geometry`, `geometry_version`, `reference_year`, documented crosswalk | Local geoBoundaries ADM2/ADM3. PSA codes may need a verified crosswalk; do not presume they are supplied in geometry. | Unique area IDs, valid geometry, unmatched/ambiguous joins reported. Record boundary versions; do not drop unmatched areas silently. | Maps/joins; no road-routing or legal-boundary claim. |
| PD-03 conditional health context | `indicator_name`, `definition`, `estimate`, `estimate_unit`, `age_scope`, `sex_scope`, `area_scope`, `sample_size` if published, `SE/CI` if published, `survey_period` | Existing FNRI Part 2 PDF: verified glucose tables on PDF pp. 325–326/328–329, national ages 20–59 and 60+. No measured HTN table secured in this subset; other access blocked/conditional. | Preserve measured versus self-reported definitions; percentage 0–100 with denominator. Double-check any manually transcribed value against page/table. Missing CI stays unavailable. Match reference periods or disclose mismatch. | Population risk-factor description. Start with only sourced HTN/glucose indicators; expand only for a named question. Glucose cannot be relabeled diagnosed diabetes. |
| PD-04 optional socioeconomic | `area_id`, `poverty_estimate`, `unit`, `SE/CI/CV` where supplied, `reference_year` | PSA 2023 small-area tables; not yet acquired. | Preserve estimate/uncertainty and geographic version; no unsupported fine-scale allocation. | Area context only; not citizen income or personal risk. |
| PD-05 conditional service analysis | `source_facility_id` or stable local ID, `name`, `facility_type` when known, `address`, `area_id`, `latitude`, `longitude`, `coordinate_source`, `verified_at`, `capability_status`, `register_as_of` | Local PhilHealth PDF/111-row queue; coordinates all blank. DOH registry optional, access blocked. | Report located/total and known capability counts. Coordinates require evidence; unknown stays unknown. Preserve register date and each verification date. | Facility distribution. No fabricated capacity, price, opening hours, available tests or partnership. B unavailable/incomplete until locations support its claim. |
| PD-06 optional environment | `source_grid_id`, `latitude`, `longitude`, `time_utc`, `temperature_k`, `hourly_precipitation_m`, `quality/completeness` | Local ERA5-Land extract, December 1990–September 2026. | Retain units; documented conversions/local-day processing. Record source and cutoff; no future rows in a past-cutoff analysis. | Historical context only; no health linkage without compatible outcomes/locations. |
| PD-07 optional heat index | Compatible temperature plus dew point/relative humidity; `timestamp`, `location`, `method`, `index_unit`, `source_type` | New humidity/dew-point acquisition or a suitable official PAGASA series; neither secured. | Match time/location, document formula/domain/quality. Distinguish forecast, observation and reanalysis; no heat-index output from temperature/rainfall alone. | Optional environmental input, not an assumed disease-effect term. |

Map display tiles are existing presentation assets, not analytical predictors. Active exclusions remain UCI CKD, CRIC/HEMO/USRDS participant acquisition, unselected morbidity/mortality series, ENSO advisory and routing acquisition. HEMOBP is a different retained candidate from HEMO.

## 3. Citizen input: lean proposed profile

**No mandatory medical question.** These five questions are the proposed maximum base profile; each permits Unknown/Prefer not to answer. A partial record can remain usable for some descriptions, with its denominator/completeness shown. No recruitment or real intake is needed for the initial public-data analysis.

| ID | Field / exact answer format | Collection and time rule | Why keep it / limitation |
|---|---|---|---|
| CI-01 | `age_band`: 18–29, 30–39, 40–49, 50–59, 60–69, 70+, Unknown/Not answered | At voluntary profile entry; record entry date. Retain source bands separately for public joins. | Coarse grouping; proposed bands are product choices, not survey equivalence. Does not supply exact age for equations. |
| CI-02 | `municipality_code`: selected valid municipality/city, Unknown/Not answered | At profile entry; corrections allowed with history. | Coarse area comparison. No GPS/address default; selected residence does not establish exposure at work. |
| CI-03 | `reported_kidney_state`: No known CKD diagnosis / Diagnosed CKD, not receiving dialysis / Receiving dialysis / Unsure / Not answered | “What is your current known status?” at entry; changes recorded explicitly. | Separates the two citizen states and diagnosed subbranches. Self-reported routing is not diagnosis verification. |
| CI-04 | `reported_diagnosed_htn`: Yes / No / Unsure / Not answered | “Have you ever been told by a qualified health professional that you have hypertension?” with entry date. | Known diagnosis history, not a current BP classification. |
| CI-05 | `reported_diagnosed_dm`: Yes / No / Unsure / Not answered | Corresponding professional-diagnosis question, entry date. | Known diabetes history, not measured fasting glucose. |

**System metadata, not citizen questions:** `record_id`, `namespace` (synthetic/real voluntary, if later enabled), `source_channel`, `entered_at`, `schema_version`, `supersedes_id` and future notice/processing metadata. A random ID is not guaranteed anonymity. Real collection requires separately specified purpose, handling and access.

## 4. Optional citizen modules — only if a retained analysis needs them

| ID / module | Exact fields | Measurement/date rule and feasibility | Boundary |
|---|---|---|---|
| CI-06 demographics | `sex_variable`, original category/definition; exact `age_years` only where an appropriate equation requires it | Optional; allow Unknown/Not answered. Do not infer sex or exact age from names or age-band midpoint. | Public-demographic matching versus clinical equation inputs are distinct needs. |
| CI-07 family/testing history | `family_kidney_history` Y/N/U; `prior_kidney_test` Y/N/U; known test type; approximate month/year with `date_precision` | Voluntary known history. If a question uses “last 12 months,” record that exact window and anchor date. | No invented exact dates; no automatic predictor selection. |
| CI-08 existing laboratory result | `analyte`, `value`, `unit`, `specimen_date` or known month/year, `date_precision`, `reported_source`; lab-reported `egfr` separately | Citizen enters an existing result only. Preserve serum/urine distinction; units required for interpretation. Missing date may permit storage but not a trend/time-cutoff claim. No upload or new test requirement. | Creatinine, UACR and UPCR are different measurements. Manual entry stays self-reported; cannot substitute UPCR for UACR. |
| CI-09 existing home/clinic readings | `systolic_bp`, `diastolic_bp`, `unit=mmHg`, `measured_date`, measurement context if known; `weight`, `unit`, `measured_date` | Optional spot entry; dates supplied if known, no sensor feed assumed. Missing units/dates block incompatible derived calculations. | No diagnosis, validated trajectory or personal warning from one entry. |
| CI-10 outdoor activity | `outdoor_work` Y/N/U; integer `outdoor_hours_7d` 0–168/U; `period_end_date` | Optional retrospective seven-day report; contradictory answers flagged for clarification. | Not measured dose and not an established kidney-model feature. |
| CI-11 diagnosed context | Reported CKD stage if known, source/date; dialysis modality if known | Only for diagnosed branch and selected task; allow Unknown. | Professionally provided information remains self-reported until verified. |
| CI-12 dialysis measurements | Patient-known pre/post-treatment weight, prescribed dry-weight target, units and session date | Extended candidate only; no guaranteed availability or required regular logging. | No treatment/machine settings, fluid prescription or assumed live monitoring. |

**Defer:** smoking/alcohol/activity questionnaires, detailed medication lists, symptoms, barrier tracking, free-text medical narratives, exact income and service-contact details until a named purpose justifies them. **No default collection:** names, phone/email, national/PhilHealth IDs, exact birth date, precise address/GPS or medical-file uploads. This narrows the broader inventory without deleting its historical candidate list.

## 5. Synthetic records: what to generate and what not to imply

| ID | Fields / generation contract | Measurable acceptance / time rule | Legitimate use |
|---|---|---|---|
| SY-01 synthetic base profiles | `synthetic_id`, `age_band`, `area_id`, supported demographic categories, `source_constraint_ids`, `seed` | Unique synthetic IDs; declared target shares/counts compared with generated ones. Report sampling error separately from source uncertainty. Source period retained. | Fictional profiles/scale demonstration; not sampled actual citizens. |
| SY-02 health/history states | Synthetic reported HTN/DM/family/prior-testing/diagnosis state **only when needed**; per-field `basis` = sourced constraint / empirical generator / assumed | Definitions match calibration sources. Unsupported marginals/joint relationships labeled assumed, with scenario/version. No arbitrary disease rate silently inserted. | Conditional population scenarios; not observed local cases or estimated true CKD prevalence. No chosen overlap simulation. |
| SY-03 missing inputs | Per-field missingness mask, mechanism/scenario, parameter/rate, random seed | Report imposed versus natural missingness; all rates within 0–1. Do not convert Unknown/Not answered to No. | Information-dependence/robustness experiments. |
| SY-04 optional timelines | Synthetic event/sample dates, sequences and hypothetical outcome if a specified temporal experiment is retained | Chronological/unit consistency, documented horizon/mechanism and reproducible seed. Identify invented timing explicitly. | Feasible demonstration without local histories; cannot validate progression or heat effects. Not required for initial scope. |
| SY-05 augmentation records | Generated predictors/labels, parent source-cohort version, generator version, training partition ID | Partition observed participants first; generator never sees held-out evaluation people/outcomes. Compare real-only, synthetic-only and combined models on the same observed evaluation set. | Test whether augmentation helps a defined task. No benefit claim if only synthetic evaluation exists. |

Synthetic record count is an engineering/scenario choice, not evidence sample size. Matching public margins does not establish joint relationships, representativeness or clinical validity. Increasing generated records does not create new real observations. Synthetic output is not automatically privacy-safe; any empirical generator needs source-term and disclosure review before sharing.

## 6. Separate observed research inputs

Choose **one** empirical study after actual file inspection; do not require all sources. No foreign dataset is merged with citizens as if the records describe the same population.

| Candidate | Minimum fields needed for the proposed research task | Proceed condition |
|---|---|---|
| NHANES cross-sectional measurement study | Source participant ID, eligible age/sex inputs, serum creatinine and/or urine ACR for a defined endpoint, candidate predictors, relevant survey weights/design and missingness | Verify matching-cycle modules, units and eligible sample; define measured abnormality rather than confirmed chronicity. |
| CKD-ROUTE pre-dialysis study | Source participant ID, baseline predictors, clearly defined outcome/event indicator, follow-up/event/censoring time | Inspect workbook; if times absent, narrow task. Serial trajectory claims require actual repeated measurements, not just cohort follow-up. |
| Mendeley dialysis study | Predictors, exact hypotension-label definition, measurement stage; patient/session IDs for repeated-record evaluation | Verify retained fields and no future-input leakage. Without IDs/time information, narrow or decline the predictive claim. |
| HEMOBP alternative | Patient/session IDs, ordered BP measurements and prior-only context | Confirm actual file access first. Historical replay remains optional, not a dependency. |

Data dictionaries and terms are gates, not paperwork to postpone. Source references/statuses are in the inventory; no new files were acquired here.

## 7. Acceptance gates before feature selection

| Gate / time boundary | Measurable criterion | Action if unmet |
|---|---|---|
| **G1 — Before an analysis is called available** | Every consumed source has an actual local snapshot, schema, source/version, period, checksum and use terms recorded. | Mark unavailable; no source listing masquerades as ready data. |
| **G2 — Before comparing public indicators** | Definitions, denominator, age/sex scope, geography and period checked for every comparison; all mismatches explicit. | Restrict to side-by-side context or omit comparison. |
| **G3 — Before real citizen collection** | Every retained question has a documented purpose; optional/Unknown handling, notice, access and retention specified. | Use fictional profiles only. No mandatory medical uploads/logging. |
| **G4 — Before synthetic generation** | Each generated variable classified sourced/empirical/assumed; mathematical consistency checks specified; scenario/source versions recorded. | Do not present it as source-constrained. |
| **G5 — Before claiming augmentation benefit** | Real held-out participant evaluation, baseline comparison, calibration/error and relevant subgroup checks with uncertainty. | Report simulation-only behavior; no predictive-improvement claim. |
| **G6 — Before selecting feature/simulation** | Named user question, feasible inputs, defined output and interpretation limit identified. | Keep idea unselected; do not add data just to justify a feature. |

No numeric model-performance target or citizen completion target is invented. Runtime, source-update cadence and collection frequency remain unspecified until deployment/task requirements exist. Freeze the submitted demonstration's sources at an explicit cutoff; disclose older source periods rather than call them current.

## 8. Recommended smallest feasible package

**Public-data-only first:** compatible population/boundaries plus whichever definition-matched health indicators are actually secured. Add facilities only when coordinate completeness supports the intended coverage analysis; poverty and weather are optional contextual layers.

**Citizen side:** an in-scope citizen interface with a five-question proposed profile, all medical answers optional, demonstrable using fictional profiles for the competition; detailed UX/output remains open. No citizen data are needed to start public-data analysis; real voluntary reports later describe reporting participants, not population prevalence.

**Synthetic side:** source-constrained base profiles, clearly assumed additional variables and optional missingness scenarios. Select neither a disease forecast nor a specific simulation until G6 is met. Add one observed-data study only when its access/schema is verified. This is a feasible data boundary, not a final product-usefulness claim.

## Inspection follow-up

See [23 October data feasibility findings](../../evidence/2026-10-23-data-feasibility.md) for actual local counts, source pages, supported feature candidates and unresolved dependencies. Availability and source definitions take precedence over the desired schema.
