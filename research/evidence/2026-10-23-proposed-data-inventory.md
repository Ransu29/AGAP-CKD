# AGAP-CKD — Proposed Data Inventory

**Date:** 23 October 2026. **Status:** inventory for scope decisions, not a collection mandate or final schema. This covers the retained source families and candidate inputs for Version 3, with scrapped sources recorded separately below. The first cleanup was approved by the product lead on 23 October 2026. Sources marked available have published listings; new candidate files have not been downloaded or schema-verified. Public visibility does not imply unrestricted redistribution.

## 1. Reading the inventory

- **Local:** file/artifact inspected in the repository; quality/completeness may still be limited.
- **Published candidate:** official documentation/listing inspected, not acquired or analysis-ready.
- **Blocked/restricted:** access unavailable, approval-dependent or otherwise unsuitable as an immediate dependency.
- **Proposed input:** a possible citizen/staff field, not currently implemented for real people.
- **Synthetic/derived:** generated or computed data, never an independent observed source.

The citizen-facing interface remains in product scope; only its detailed design conversation was paused. Enumerating inputs does not settle its UX or authorize real collection. Choose fields only when a named analysis or useful task needs them; do not make citizens complete every item. Existing code accepts synthetic residents only.

## 2. Public population and contextual sources

| ID | Source and relevant data | Resolution/time and current status | Possible use / limit |
|---|---|---|---|
| PUB-01 | PSA census: population totals, age/sex where released, geographic identifiers | 2020 and newer 2024 releases; **published candidate**. Required local breakdown still to inspect. [Tables](https://psa.gov.ph/statistics/population-and-housing/stat-tables) | Denominators and demographic context; do not invent unreleased fine-scale age groups. |
| PUB-02 | WorldPop modeled population, age/sex raster counts | 2020, approximately 1 km; listed in local manifest, raw rasters not found during inspection; saved derivatives require run-provenance check. [Publisher index](https://data.worldpop.org/GIS/AgeSex_structures/Global_2000_2020_1km/unconstrained/2020/PHL/) | Spatial population distribution; modeled counts are not resident addresses or current census counts. |
| PUB-03 | geoBoundaries: municipality/city and province geometry, release metadata | Local ADM2/ADM3 files; represented boundaries 2020 per recorded metadata. [ADM2](https://www.geoboundaries.org/api/current/gbOpen/PHL/ADM2/), [ADM3](https://www.geoboundaries.org/api/current/gbOpen/PHL/ADM3/) | Geographic joins/maps; resolve versions/codes and naming mismatches. |
| PUB-04 | PSA poverty small-area estimates: incidence, magnitude, standard error/CV/confidence interval and geographic codes where supplied | 2023 municipal/city tables; **published candidate**. [Tables](https://psa.gov.ph/statistics/poverty-sae/stat-tables) | Area socioeconomic context, not individual income or clinical risk. |
| PUB-05 | FNRI published indicators: blood-pressure measures, fasting glucose, body size/nutritional status, smoking, alcohol, physical activity; relevant age/sex/region breakdowns | Local Part 2 results PDF; other tables **candidates**, FNRI website unavailable to user. [Catalogue](https://enutrition.fnri.dost.gov.ph/presentation.php?year=2023), [alternate-host presentation](https://thedocs.worldbank.org/en/doc/246d27a49b82e45544a2950a4d919315-0090062025/original/ph-FNRI-Trends-regional-patterns-diet-nutrition-2025March.pdf) | Descriptive context/calibration of matching variables. Measured high glucose is not self-reported diagnosed diabetes. Check definitions, period, denominator and uncertainty per table. |
| PUB-06 | FNRI microdata: potentially measurements, diagnosis/medication history, demographics and survey design variables | **Blocked/conditional**; exact fields, years, weights, identifiers and geographic release unverified. [Access process](https://enutrition.fnri.dost.gov.ph/puf-dataset.php) | Candidate awareness/subgroup analysis only when compatible fields actually exist. Tables cannot reconstruct joint individual records. |

## 3. Public services and environment

| ID | Source/data | Status | Possible use / limit |
|---|---|---|---|
| PUB-08 | PhilHealth YAKAP register: names, addresses/source pages, accreditation snapshot | Local source PDF and **111-row Laguna verification queue**, no populated coordinates. [Publisher](https://www.philhealth.gov.ph/partners/providers/facilities/accredited/) | Facility identity/inventory. Accreditation does not establish renal panel availability, opening hours, cost, capacity or partnership. |
| PUB-09 | DOH National Health Facility Registry: facility type, address and any released location attributes | **Candidate; registry returned 403**. [Official DOH access instructions](https://www.foi.gov.ph/requests/total-number-of-hospitals-in-the-philippines/) | Broader primary-care/hospital/dialysis inventory if obtainable; verify fields and coordinates. |
| PUB-10 | ERA5-Land: time, grid ID, latitude/longitude, 2 m temperature, precipitation | **Local** annual Parquet extracts December 1990–September 2026. [Publisher](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land) | Historical environmental context; not live forecasts, personal exposure or observed health outcomes. |
| PUB-11 | Dew-point temperature or relative humidity for heat-index calculation | **Additional candidate, not in inspected extract**. [ERA5-Land time series](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-timeseries?tab=download) | Derive humidity/heat index only using compatible times/locations and documented method. Temperature plus rainfall alone is insufficient. |
| PUB-12 | PAGASA heat-index observations/outlooks | **Optional candidate**; usable series/API/archive not secured. [Heat index](https://www.pagasa.dost.gov.ph/weather/heat-index/) | Distinguish observations and outlooks from reanalysis. ENSO advisory excluded from active scope. |
| PUB-13 | OpenStreetMap/OpenFreeMap display assets | **Retained for display only:** local bounded Laguna map pack. [Attribution](https://www.openstreetmap.org/copyright) | No road-network acquisition or routing engine in active scope; visible roads do not establish travel time. |

Actual test capability, current availability, prices, operating hours, clinical contact and partner commitment are **not secured public inputs**. They need separately dated evidence before operational use; do not fill them with plausible fictional values and label them verified.

## 4. Public research participant datasets — separate from citizen input

| ID | Dataset and candidate variables/outcomes | Access/status and boundary |
|---|---|---|
| RES-01 | NHANES: age/sex and survey-design fields; urine ACR and serum creatinine confirmed in documentation. BP, diabetes history and other modules require matching-cycle dictionary checks. | **Published candidate, US**. [Urine](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/ALB_CR_L.htm), [serum](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/BIOPRO_L.htm). Cross-sectional measurement analysis; not serial progression or Philippine validation. |
| RES-02 | CKD-ROUTE: baseline characteristics, kidney measurements/proteinuria and progression/follow-up outcomes; exact workbook fields pending | **Public Dryad listing**, Japanese pre-dialysis cohort. [Dataset](https://doi.org/10.5061/dryad.kq23s). No promise of serial records until inspected. Preserve UPCR versus UACR distinction. |
| RES-03 | Mendeley dialysis datasets: clinical parameters recorded at five within-session points, age/sex and hypotension label; exact predictors/IDs/times pending | **Public listing**, derivative CSVs selected from complete valid sessions. [Dataset](https://doi.org/10.17632/7kmtsmsgfw.1). Verify which fields precede labels; no automatic longitudinal evaluation without identifiers. |
| RES-04 | HEMOBP: participant/session keys, measurement times, BP, weights, machine settings | **Paper verified; file access unconfirmed**, Taiwan. [Descriptor](https://doi.org/10.1038/s41597-019-0319-8). Body/dialysate temperatures are not environmental heat index. |

## 5. Citizen-entered information — proposed inventory

No real citizen form or collection has been authorized by this list. **Shared** means relevant to more than one branch, not mandatory. All medical entries remain self-reported unless independently verified. Unknown, No and Not answered must remain distinct.

| ID | Field group / proposed fields | Applicable branch / need and limit |
|---|---|---|
| CIT-01 | Random/pseudonymous record ID | Shared; generated system identifier, not a national or medical-record number. Existing demo IDs are `SYN-*`, not real identities. |
| CIT-02 | Age or age band; sex variable only where required by a named analysis/equation | Shared, conditional. Choose the least detail needed; age band for aggregates may not support a clinical equation. No exact birth date by default. |
| CIT-03 | Municipality/city; optional barangay only if a defined task justifies it | Shared geographic context. No exact address/GPS by default. Small-group privacy and representativeness require controls. |
| CIT-04 | Known CKD diagnosis: Yes/No/Unknown; whether currently receiving dialysis; diagnosis/stage/date only if known | Branch routing as reported status, not app diagnosis. Unknown diagnosis is not absence. Reported stage must have source/date where provided. |
| CIT-05 | Previously told by a professional of hypertension or diabetes: Yes/No/Unknown | Population/risk-factor context. Distinct from a new measured BP/glucose value. Existing synthetic `HTN`/`DM` flags provide normalization concepts only. |
| CIT-06 | Family history of kidney disease: Yes/No/Unknown | Optional contextual field, existing synthetic `FAM`. Not automatically a justified new-model predictor. |
| CIT-07 | Prior kidney testing: known test type and approximate date, or Unknown | Optional assessment-history research. Existing `PRIOR` flag is coarser; no precise timeline should be invented. |
| CIT-08 | Outdoor work/activity; approximate hours in a stated recent period | Optional environmental research. Existing synthetic `OUT`/`HRS` uses last seven days; reported hours are not measured heat dose. Collect only if a retained analysis needs them. |
| CIT-09 | Smoking, physical activity, height/weight and alcohol categories | **Extended candidates**, not minimum intake. Use only a justified, defined measure; no assumed equivalence with survey questions or clinical predictors. |
| CIT-10 | Professionally provided CKD stage, known underlying cause, transplant status or dialysis modality | Diagnosed branch, conditional. Patient may not know; preserve reported provenance. Transplant support is outside selected scope. |
| CIT-11 | Creatinine value/unit/sample date; urine ACR or urine protein/creatinine value/unit/sample date; lab-reported eGFR if available | Diagnosed/research candidate; optional manual transcription only if useful. Distinguish specimen date from entry date and urine from serum creatinine. Never require a person to obtain new tests merely to use the demo. |
| CIT-12 | BP value(s), measurement date and basic measurement context; weight/value/unit/date | Optional monitoring candidate, not established requirement. One-off readings do not create a validated longitudinal model. No live sensor feed assumed. |
| CIT-13 | Dialysis type; usual treatment schedule; patient-known pre/post-treatment weight or care-team dry-weight target, if relevant | Dialysis branch **extended candidates only**. These are not self-management instructions; no app-chosen fluid target, treatment setting or dialysis prescription. |
| CIT-14 | Whether an agreed follow-up/test was completed; optional barrier categories such as cost, time, transport or uncertainty | Future workflow research only. No existing unmet coordination need or actual provider receipt is established. Self-reported completion differs from verified service data. |
| CIT-15 | Optional questions/information preferences | Future education research; no unrestricted clinical symptom/medication chat or automatic triage implied. |

**Do not collect by default:** names, phone/email, PhilHealth/national IDs, full address, exact date of birth, medical-file uploads, medication/dose lists, detailed symptom histories, income amounts or continuous location. Any future exception needs a defined useful task, processing basis, notice, retention and appropriate access. A contact field would require a genuine responding service; none is confirmed.

**Current implementation reference:** `src/agap/reports.py::normalize_report` schema v2 accepts synthetic ID, fixed known age, `DM`, `HTN`, `FAM`, `OUT`, `PRIOR`, `HRS`, `DATE`. Its range/date rules and 30-day report window are demo behavior, not automatically a real intake policy. SMS-style parsing is not a messaging integration. `PersonalNotes.md` contains candidate patient logs, not confirmed requirements.

## 6. Staff-verified, synthetic and derived data

| Type | Fields | Provenance/limit |
|---|---|---|
| Staff-verified observations — conditional future | Verification status, verifier/source, lab analyte/value/unit, specimen/result date, correction/supersession | Verification is a separate fact, not granted by a citizen tick-box. Existing workflow records are fictional. |
| Synthetic population | Synthetic ID, source-constrained demographics, generated health traits/reports, assumed relationships, missingness and scenario membership | Generator provenance, assumption ranges and seed required. Not real people or independent epidemiological evidence. |
| Synthetic outcomes/time series | Assumed labs, progression/events, attendance or treatment trajectories, when needed for a declared experiment | Outcomes follow a generator; they do not validate the generating assumptions. Local histories/timestamps are not required for hypothetical simulation. |
| Derived geographic measures | H3/municipality assignment, counts, rates with denominators, defined coverage/distance, completeness | Do not confuse geographic reach with actual service use. |
| Derived environmental measures | Local-day temperature/rainfall, windows, anomalies; heat index only with suitable added inputs | Match geography/time; contextual exposure, not automatically a clinical predictor. |
| Derived kidney measures/model outputs | eGFR from appropriate inputs/equation; research target, score, horizon, uncertainty and evaluation metrics | Computation is not diagnosis. Patient-entered versus verified inputs remain distinguishable. |
| Scenario/training metadata | Source/version, generator assumptions, distributions, seed, partitions, actual model, augmentation ratio and metrics | Partition observed people before fitting generator; no evaluation data leakage; no benefit claim without observed evaluation. |
| Collection metadata — future | Entry date, reported event/sample date when known, channel, source, notice/version, correction links | System entry timestamps are easy to create; historical medical timestamps are not inferred. Retention/hosting remain unspecified. |

## 7. Reference material, not datasets

Competition primer, submitted proposal, interview originals/synthesis, personal notes, clinical guidance and published program/legal documents inform scope or definitions. They are not participant training data. The two nurse PDFs describe one joint conversation, not independent corroboration. Population planning's institutional usefulness remains unresolved.

## 8. Immediate feasibility boundary

Start by inspecting secured public files and compatible tables; no citizen recruitment is needed for that step. Use fictional citizen profiles for the competition where appropriate. Real voluntary reports, if ever collected, describe reporting participants, not all residents; absence of reports is not absence of disease.

Minimum citizen input is **not yet selected** because detailed citizen tasks/UX remain open. The lean candidate set for a future profile is coarse demographic/location context plus known diagnosis state and known HTN/DM/history; lab values and dialysis details stay optional and purpose-dependent. Public-data-only analysis and simulation must work at zero registered citizens. The withdrawn risk-factor-overlap scenario remains withdrawn; this inventory does not select it again.

## 9. Sources removed from active Version 3 scope

**Product-lead decision: 23 October 2026.** These are not acquisition, training or implementation dependencies. Existing downloaded files and historical research remain preserved. IDs are reserved rather than reassigned.

| Former ID / source | Cleanup decision and reason |
|---|---|
| RES-05 — UCI CKD benchmark | Removed: small classification benchmark does not support the selected longitudinal research questions. |
| RES-06 — CRIC, HEMO and USRDS participant files | Removed from immediate scope: request/access restrictions make them unsuitable dependencies for this build. HEMO is distinct from HEMOBP, which remains under review. |
| PUB-07 — PSA/DOH morbidity/mortality tables | Removed: no selected compatible series or named analysis. This does not discard mortality endpoints contained within a retained research cohort when needed for correct analysis. |
| PUB-12 former ENSO component — single PAGASA advisory | Removed: one advisory does not support a retained analytical question. Heat-index candidate sources remain separate and optional. |
| PUB-13 former road-routing component | Removed: no confirmed routing task. Existing basemap assets remain for display. |

Still under review: NHANES (RES-01), CKD-ROUTE (RES-02), Mendeley dialysis (RES-03), and HEMOBP (RES-04). None is automatically committed as a model source; file access/schema feasibility and the selected analytical task determine retention.
