# Data feasibility and resulting feature candidates

**Date:** 23 October 2026. **Method:** read-only local file/schema inspection using existing Python packages; no downloads, pipelines, model fitting or application tests. This assesses available inputs, not product usefulness. See the [SMART specification](../decisions/proposed/DATA_SPEC.md).

## 1. What is secured locally

| Input | Inspection finding | Consequence |
|---|---|---|
| Saved run `31eeb9a6f51e-9ee5da3833af-44136fa3` | `manifest.json` explicitly sets `prototype.geography_mode: fixture`. `cells.parquet` has 2,515 cells, five named fixture zones and total `adult_count` 65,390. | These are illustrative frame counts, not an observed Laguna population. No local population inference from them. |
| National boundaries | ADM2 GeoJSON has 87 features; ADM3 has 1,647. Properties include `shapeName`, `shapeISO`, `shapeID`, `shapeGroup`, `shapeType`. | Do not assume a PSA code is already present. A verified crosswalk is needed before PSA joins. |
| Processed Laguna boundaries | `data/processed/public/laguna/municipalities.geojson` contains 30 features. | A real boundary display is feasible; it does not establish population counts or health estimates for those areas. |
| Clinic queue | `clinic_verification_queue.csv`: 111 records, zero with both latitude and longitude populated. | Facility verification status/counts can be inspected; point coverage/distance analysis is not ready. Registry type/capability must be checked independently. |
| Processed temperature sample | `temperature_daily.csv`: 465 rows, 15 grid cells, 1–31 January 2021. | A small historical temperature display is possible, clearly labeled sample; it is not a complete operational history. |
| Raw climate extracts | Existing annual ARCO Parquet files include temperature and precipitation; January 1991–September 2026 plus warm-up December 1990 according to source documentation. | Raw history exists, but new aggregate features would require explicit processing. Local `processed/climate` and `processed/weather` directories contain metadata only, not the required processed Parquet tables. |
| Population rasters | No raw WorldPop files found in inspected `data/raw` directory. | Manifest URLs do not prove locally secured population data. Do not relabel fixture artifacts or assume a public run is ready. |
| Empirical kidney/dialysis candidates | No acquisition/file-level inspection performed for NHANES, CKD-ROUTE or the dialysis candidates. | No empirical model target/schema or performance can yet be promised. |

## 2. Verified national indicator subset

Local source: `data/raw/fnri/2023_nns_clinical_results.pdf` (397 PDF pages). Preserve the 2023 survey reference period. Page 323 classifies high fasting glucose as ≥126 mg/dL and impaired fasting glucose as 100–125 mg/dL, as defined by that source. These are survey indicator definitions, not product diagnostic instructions.

| Indicator / source PDF page | Population | Estimate | Published 95% interval |
|---|---|---|---|
| High fasting blood glucose, p. 326 | Ages 20–59; stated n=40,877 | 7.5% | 7.1–7.8% |
| High fasting blood glucose, p. 329 | Ages 60+; stated n=13,617 | 17.2% | 16.1–18.3% |
| Impaired fasting blood glucose, p. 325 | Ages 20–59; stated n=40,877 | 22.0% | 21.5–22.6% |
| Impaired fasting blood glucose, p. 328 | Ages 60+; stated n=13,617 | 36.0% | 34.7–37.3% |

Pages 325–326 and 328–329 also provide sex, urban/rural and wealth-quintile breakdowns. Those are separate marginal tables, not jointly observed combinations. Page 330 provides a published national trend chart; do not infer comparability beyond the definitions/methods supplied. Text extraction was inspected, not a completed independently checked transcription dataset.

**Definition boundaries:** high fasting glucose is not self-reported diagnosed diabetes; national estimates are not municipal estimates; ages 20–59 are not equivalent to the proposed citizen band 18–29. Do not combine bands or sum prevalence into unique people without appropriate denominators and overlap information. No measured hypertension indicator was secured in the inspected Part 2 subset.

## 3. What follows from this data

### Feasible feature candidates using existing inputs

1. **Evidence/source catalogue:** expose actual source, reference period, population, units, availability and missingness. A link is distinct from an acquired dataset.
2. **National indicator comparison:** compare the verified glucose indicators across the source's supported groups, retaining confidence intervals and definitions. Requires checked transcription before implementation.
3. **Geographic reference view:** display the 30 Laguna boundary features with facility-verification completeness; avoid disease heatmaps and unlocated clinic pins.
4. **Fictional profile entry:** demonstrate the proposed basic citizen fields using clearly synthetic profiles. No connection to a validated individual score.

These are technically plausible candidates, not proof of a substantial LGU contribution. A national glucose comparison alone does not fulfill the proposed kidney-health decision-support proposition.

### Conditional next analyses

- **Population-weighted scenario:** only after securing compatible real population counts; report every transferred rate/relationship as a supported quantity or assumption. No scenario chosen yet.
- **Service geography:** only after supported facility coordinates and a named service definition; show missing facilities rather than imply a complete network.
- **Empirical modeling/augmentation:** only after one observed dataset's files, dictionaries, identifiers and target are inspected; evaluate on held-out observed people.
- **Heat-index context:** only after compatible humidity/dew-point inputs and processing; current temperature/rainfall fields are insufficient.

### Defer

Local CKD prevalence mapping, individual clinical warnings, progression/dialysis prediction, live historical patient replay, staffing/capacity optimization and heat-driven disease forecasts lack the required secured inputs or established task. Synthetic records do not close these evidential gaps.

## 4. Next data work, in dependency order

1. Make a checked structured extraction of the four national indicator tables, with page references and source definitions.
2. Secure and inspect compatible population totals and geographic identifiers before selecting local scaling or mapping analyses.
3. Inspect one retained empirical dataset, selected for actual access and schema suitability, before choosing its model or augmentation experiment.
4. Revisit the analyst's consequential question using the resulting data package. Select a simulation/feature only after its required inputs and interpretation are explicit.

Scope clarification: the citizen-facing interface remains in the product; this feasibility note addresses analytical inputs, not a decision to remove citizen functionality. Detailed UX is pending and fictional profiles may support the demonstration.

Citizen collection is not a prerequisite for steps 1–3. This avoids asking citizens for data before a useful task has been established. Existing source files, code and configurations remain unchanged.
