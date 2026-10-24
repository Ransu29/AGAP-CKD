# AGAP-CKD — Proposed Product Requirements Document

## Version 3 — Data-led product recalibration

**Status: PROPOSED. Direction agreed for exploration; analytical feasibility and real-world usefulness remain unvalidated.**

Updated 23 October 2026 (Asia/Manila), branch `bry-research`, commit `ecab5466a970bbee63c50508e0a56f35b6d99ed5`. This revision incorporates the subsequent product-lead discussion and research-source findings. Working-tree documentation edits are included; no software changes are made by this revision. The [current-version PRD](../../ssot/PRD.md) describes the implemented baseline at its recorded commit; it is not a claim of newly verified implementation. See [Version 3 architecture](ARCHITECTURE.md).

### Changes from the preceding proposal

- Retain the citizen-facing interface in product scope; pause only its detailed design conversation while examining the data and analytical core.
- Organize the longer-term product around no known diagnosis versus diagnosed CKD, with the latter covering both pre-dialysis and dialysis.
- Favor A: population risk-factor analysis and B: geographic service coverage, with C: empirical kidney research as an addition.
- Make D a public-data-anchored population scenario explorer; synthetic training augmentation is a separate evaluated experiment. Neither staffing shortages nor testing-capacity scarcity is an established central problem.
- Do not make heat the main driver or promise a general personal warning score. A hypothesis about heat in dialysis patients is not a demonstrated comparative effect across citizen states.

## 1. Working proposition and intended users

**AGAP-CKD is a proposed analytical system for examining population kidney-health context, geographic service coverage, and disease-stage-specific longitudinal evidence.** It may support analysts and appropriately authorized health professionals in interpreting evidence and exploring scenarios. Their adoption, institutional responsibilities and decision usefulness are unconfirmed.

Citizens are intended direct users as well as beneficiaries. The product includes a citizen-facing experience for people without a known CKD diagnosis and people diagnosed before or during dialysis, alongside the professional analytical experience. Only detailed discussion of citizen UX was paused; the interface was not removed from scope. Delivery channel, exact features and institutional integrations remain to be specified. The previously rejected mandatory printable-summary handoff is not reinstated.

The product remains kidney-health focused. Hypertension, diabetes and socioeconomic conditions provide relevant analytical context; they do not turn it into a comprehensive health platform. Useful existing modules may be reused, but existing functionality is not automatically a requirement.

### Product-lead clarification during Version 3 review

Public-health analysis remains the leading experience, but maps alone are not the intended endpoint. Population findings should motivate research questions and subgroup comparisons in the separate pre-dialysis/dialysis studies. Only compatible data and separate evaluation can justify changing an individual prediction. The analyst's specific consequential task remains unresolved; this connection alone does not establish institutional usefulness. Simulations remain optional supporting features. The product lead selected public-data-anchored population scenarios as D’s primary direction; the first scenario and output remain to be selected. Historical patient replay is not a required capability. Synthetic training augmentation is a separate experiment: any claimed benefit must be measured against appropriate baselines on held-out observed data.

### Data feasibility now controls release scope

This proposal must be read with the [SMART data contracts](DATA_SPEC.md) and [inspected feasibility findings](../../evidence/2026-10-23-data-feasibility.md). Dataset availability establishes technical feasibility, not an unmet LGU need. The broader two-state direction remains; its analytical branches are conditional capabilities, not promised completed models.

**Proposed research outcome:** an analyst can produce a defensible statement about a supported population indicator, trace its source/period/denominator and identify whether a proposed local or predictive interpretation is supported. Proposed artifact-level target: every displayed/exported quantitative conclusion includes source, population, reference period, units and evidence type; no unsupported output is silently enabled. Analyst usefulness and task success are unmeasured, with no invented adoption or time-saving target.

| Inspected evidence | Requirement/scope consequence | User-visible behavior and acceptance condition |
|---|---|---|
| FNRI PDF has national glucose tables with intervals, ages 20–59 and 60+ | Retain a **national indicator explorer** as technically feasible proposed scope, after checked transcription. | Show exact source-defined groups and uncertainty. No “diagnosed diabetes,” local CKD cases or 18–29 equivalent derived from those tables. |
| Saved run is fixture geography with five named fixture zones | Public population analysis remains **blocked** until a genuine compatible frame is secured. | Fixture banner/exports remain explicit. No fixture counts under a Laguna population label. |
| Real Laguna geometry exists; clinic queue is 111 records with zero located | Retain a **reference map and facility-data completeness view**; coverage/distance analysis remains **blocked**. | Display geometry and 0/111 coordinate completeness with source snapshot. No fabricated facility pins or clinical service-access claims. |
| No acquired/schema-checked empirical kidney dataset | Pre-dialysis/dialysis prediction and augmentation remain **conditional**. | Explain missing prerequisites; show no invented scores or performance cards. A source listing is not a ready model. |
| Citizen inputs are proposed; no real deployment or validated clinical predictor exists | Retain **citizen-facing profile and information/guidance scope**, with detailed UX pending. Fictional profiles enable competition demonstration without real recruitment. | Unknown answers remain distinct; self-reported facts are not verified diagnoses. No synthetic prediction is presented as validated personal risk; reports cannot become population prevalence. |
| Existing temperature/rainfall lacks humidity/dew point | Historical temperature sample may be supporting context; heat index and heat-driven health forecasts remain **blocked**. | Display actual sample date/coverage. No substituted heat-index label. |
| Synthetic assumptions can be explicit, but first useful scenario is unsettled | Keep D **unselected** until a named analytical question and feasible inputs are established. | Do not implement the withdrawn overlap scenario merely because generation is possible. |

### Opportunity-to-solution reasoning

These are **opportunity hypotheses**, not participant-confirmed pain points; no importance/satisfaction scores are fabricated.

```text
Desired outcome: produce a defensible, source-traceable analytical statement
├─ Hypothesis: analyst needs to distinguish supported findings from extrapolation
│  ├─ Alternatives: source catalogue; indicator comparison; narrative evidence brief
│  └─ Selected candidate: source-linked indicator comparison, with provenance embedded
└─ Hypothesis: analyst needs to know whether local analysis is justified by coverage
   ├─ Alternatives: completeness table; boundary reference map; apparent coverage model
   └─ Selected candidate: completeness + reference geography; defer unsupported coverage model
```

**Proposed desk checks, not executed experiments:** (1) verify every transcribed indicator against its PDF page, preserving the published interval and source population; acceptance is exact source agreement for each included value. (2) walk through a fixture run and unlocated clinic list; acceptance is that neither can be exported as observed Laguna population or mapped verified service access. (3) examine candidate empirical dictionaries/files; proceed only if the chosen target's required units, identifiers and observation timing are present. These establish input/implementation feasibility, not citizen benefit, LGU demand or clinical validity.

This starting scope is not sufficient evidence that AGAP makes a major LGU contribution or fulfills the competition's analytical depth. Those questions remain open until a consequential analyst task and substantive secured-data analysis are established. Do not present a descriptive glucose viewer as the completed kidney-health proposition.

## 2. Two citizen states, three analytical branches

| Branch | Purpose and candidate question | Supported output boundary |
|---|---|---|
| **1. No known CKD diagnosis** | What population risk-factor patterns and geographic coverage can available Philippine data describe? | Aggregate patterns, observed awareness differences only where suitable data exist, and defined geographic coverage. No diagnosis or identification of undiagnosed individuals from regional tables. |
| **2A. Diagnosed CKD, before dialysis** | Which observed characteristics are associated with progression over a defined follow-up period? | Source-cohort progression/time-to-event research; repeated-measurement trajectories only if actually released. No validated Philippine patient forecast. |
| **2B. Receiving dialysis** | What can observations available earlier in treatment tell us about subsequent blood-pressure behavior or a defined event? | Research replay and predictive evaluation within the source data. No machine-setting recommendations or live clinical alerts. |

“No known diagnosis” does not mean disease-free. Diagnosed CKD does not mean dialysis. These branches have different target populations, outcomes, timelines and evidence; one shared score is inappropriate. Diagnoses and transitions remain clinical facts, not automatic model outputs.

## 3. Analytical components A–D

| Component | Proposed scope | Access/feasibility condition |
|---|---|---|
| **A — Population risk-factor patterns** | Descriptive profiles and subgroup differences. With suitable survey microdata, examine measured versus previously known conditions and associated characteristics. | FNRI service is unavailable to the product lead. Microdata, compatible questions/measurements, weights and geographic resolution are not secured. With tables only, restrict analysis to published indicators and resolution. |
| **B — Geographic service coverage** | Map population and specified service locations; compare population-to-facility measures and geographic coverage. | Existing clinic queue has names but blank coordinates. Verify location and define service type before analysis. Facility presence is not test capability, affordability, access behavior or spare capacity. |
| **C — Empirical kidney research** | NHANES cross-sectional measurements for a separate research question; CKD-ROUTE as a candidate for pre-dialysis outcomes; dialysis-session data as a candidate for treatment-time analysis. | These are separate studies, not pooled local patient data. Released file contents and identifiers must be inspected before selecting targets/horizons. |
| **D — Public-data-anchored population scenarios** | Generate fictional populations constrained by specified public statistics; vary unsupported relationships, missingness or other explicit assumptions and examine which conclusions remain stable. Time horizons are optional only when an appropriate mechanism exists. | First scenario/output and secured calibration inputs remain unresolved. Synthetic population size is not independent evidence. No local patient histories, live feed or historical replay is required. Synthetic training is evaluated separately on held-out observed data. |

A and B are preferred core directions, not guaranteed deliverables. C is an empirical addition subject to scope. D should explain a specific question rather than exist only for visual impact. No extra interviews are required to complete the proposal; their absence limits claims about usefulness.

### D scenario decision: reopened

The product lead withdrew the initial risk-factor-overlap scenario because its contribution to an LGU decision had not been established. It is not an active requirement. Public-data-anchored synthetic scenarios remain an agreed methodological direction, and synthetic training remains a separate experiment with held-out observed evaluation. The specific scenario, intended LGU role and consequential decision remain open. Published program responsibilities are researchable context; local usefulness cannot be inferred from them. No additional interview access or institutional knowledge is required from the product lead to continue desk research.

## 4. Sources, access and evidence

The following status reflects repository inspection and source checks from 22 October, updated with the user's FNRI outage report; data downloads and file-level inspection of new candidates have not occurred.

| Source | Status and potential use | Limitation |
|---|---|---|
| Existing local files | ERA5-Land annual Parquet extracts; boundaries; FNRI results PDF; 111-row Laguna clinic queue; synthetic saved cohorts and outcomes. See [data sources](../../../docs/data_sources.md). | Clinic coordinates are blank; synthetic labs/outcomes are not observations. Raw WorldPop rasters were not found in the inspected raw directory; identify provenance of each saved frame. |
| [FNRI public-use process](https://enutrition.fnri.dost.gov.ph/puf-dataset.php) | Previously readable listing described request/approval and CSV dictionaries. | Website returns service unavailable to user. Do not make access a prerequisite or claim participant data have been obtained. |
| [World Bank–hosted FNRI presentation](https://thedocs.worldbank.org/en/doc/246d27a49b82e45544a2950a4d919315-0090062025/original/ph-FNRI-Trends-regional-patterns-diet-nutrition-2025March.pdf) | Alternate host for published trends. | Not microdata and not evidence for individual associations. |
| [PSA poverty tables](https://psa.gov.ph/statistics/poverty-sae/stat-tables), [population tables](https://psa.gov.ph/statistics/population-and-housing/stat-tables) | Municipal poverty estimates with uncertainty; population releases for compatible denominators. | Check years, geography, identifiers and age bands. Poverty is an area estimate, not individual income. |
| [NHANES urine measurements](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/ALB_CR_L.htm), [serum biochemistry](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/BIOPRO_L.htm) | Public US observed measurements; candidate cross-sectional research. | Not a longitudinal CKD progression cohort. Single measurements do not establish chronicity; source-population findings do not validate Philippine use. |
| [CKD-ROUTE, Iimori et al. (2018)](https://doi.org/10.5061/dryad.kq23s) | Dryad lists `ROUTE_proteinuria_dataset.xlsx`; Japanese pre-dialysis G2–G5 cohort, 1,138 enrolled. Published endpoints include >50% eGFR loss or dialysis initiation, cardiovascular events and death. | Workbook not inspected. Verify exact rows, repeated measures, event times/censoring and usable sample. The original analysis's 927 participants are not automatically the file's row count. |
| [Dialysis dataset, Gomez-Pulido (2021)](https://doi.org/10.17632/7kmtsmsgfw.1) | Public Mendeley listing: datasets extracted from 98,015 sessions/758 patients; repeated within-session parameters and hypotension target; CC BY 4.0. | Complete valid sessions selected; derivative sample sizes vary. Patient IDs, chronology and pre-outcome feature availability not established. |
| [HEMOBP, Lin et al. (2019)](https://doi.org/10.1038/s41597-019-0319-8) | Data paper describes Taiwan treatment records: 1,075 patients, 165,986 sessions and irregular blood-pressure/machine measurements. | Figshare access unconfirmed. Body/dialysate temperatures are not outdoor heat. Treatment responses can affect later measurements. |

**Approved data cleanup (23 October 2026):** UCI CKD, CRIC/HEMO/USRDS participant files, unselected PSA/DOH morbidity/mortality series, the single ENSO advisory, and road-routing acquisition are out of active scope. Preserve historical/local files. Display basemaps remain; NHANES, CKD-ROUTE and dialysis candidates remain under review. See the [data inventory](../../evidence/2026-10-23-proposed-data-inventory.md#9-sources-removed-from-active-version-3-scope). HEMOBP is distinct from HEMO.

The joint nurse interview remains one contextual source. [Minutes](../../validation/interviews/Minutes%20%281%29.pdf), pp. 1–4, describe dialysis practice, monthly lab workload, follow-up calls and wishes. The [synthesis](../../validation/interviews/Dialysis-Nurse-Interview-Notes.pdf), pp. 1–3 and 6–7, includes team interpretation. Ambiguous earlier-awareness wording does not show that referred patients arrive unaware, community screening is absent, or AGAP is validated. Naming/quotation permission remains unconfirmed.

## 5. Proposed requirements and acceptance conditions

Version 3 IDs replace the earlier P-series as the proposal's current requirements; current implementation F-IDs remain unchanged.

| ID | Requirement and observable condition |
|---|---|
| **V3-001** | Distinguish all three analytical branches and dataset populations. Every result names branch, target, period, geography and source. No universal risk label. |
| **V3-002** | A uses observed tables/microdata at supported resolution. Unknown awareness status cannot be inferred from a prevalence table; survey estimates retain weights/uncertainty where applicable. |
| **V3-003** | B distinguishes registered facility, verified coordinates, verified capability and assumed availability. Missing locations are counted and visible, not silently fabricated. |
| **V3-004** | Each C study specifies unit, prediction origin, target, horizon, eligible cohort and missingness. Feature availability precedes its prediction target. |
| **V3-005** | Progression analysis handles follow-up/censoring; dialysis analysis handles repeated patient/session records. Random row splits alone are not sufficient evidence of generalization. |
| **V3-006** | D distinguishes source-constrained characteristics from assumed relationships and reports sensitivity across plausible scenarios. No required timestamped patient data. Any later forecast/replay remains separately scoped and evaluated. |
| **V3-007** | Heat index requires compatible temperature/humidity inputs; current temperature/precipitation extract is insufficient. No unsupported heat-to-disease multiplier or clinical warning. |
| **V3-008** | Public, observed foreign cohort and synthetic namespaces remain separate. A generator for augmentation fits only within the training partition; real-only, synthetic-only and combined training comparisons use untouched observed evaluation participants and appropriate simple baselines. Calibration and subgroup performance accompany discrimination. No claim of local clinical validity from foreign evaluation. |
| **V3-009** | Every run/export records source/version, transformations, parameters, cohort selection, actual model and limitations. Reuse existing provenance machinery where applicable. |
| **V3-010** | Show meaningful simple baselines, appropriate uncertainty and subgroup performance where supported. Better predictive performance is not evidence of treatment benefit or adoption. |
| **V3-011** | Retain a citizen-facing interface covering the two citizen states and diagnosed subbranches, with proposed voluntary profile inputs and understandable information/guidance. Detailed UX and action choices remain open. Demonstrate with fictional profiles where needed; real collection/deployment and integrations require their own implementation and data-handling specifications. Demo labels imply neither authentication nor clinical validity. |
| **V3-012** | Competition claims match secured artifacts. Blocked access or missing fields narrows the analysis; no invented data, partnerships or completed validation. |
| **V3-013** | Every displayed quantitative conclusion includes source/page or artifact, population/denominator, period, unit and evidence type. National survey measures are not relabeled local diagnoses. |
| **V3-014** | Capability availability reflects actual artifacts and checked contracts. Missing population, coordinates, research fields or humidity blocks dependent outputs with a specific reason; no silent synthetic fallback. |

## 6. Proposed citizen and analyst journeys

**Citizen experience (in scope; detailed design pending):** choose the applicable reported kidney-health state → optionally provide purpose-justified information → receive understandable information/guidance appropriate to that state. Exact content, outputs, next actions, saved-state behavior and channel remain to be designed. This is a scope outline, not an approved UX or validated prediction workflow. The competition may demonstrate the experience with fictional profiles. No mandatory document handoff, questionnaire diagnosis or unvalidated personal warning is implied.

The citizen and professional experiences coexist. Any future use of real voluntary citizen records in professional aggregates needs defined population/period/completeness and permission boundaries; it cannot silently merge with public census counts or synthetic residents.


**Population branch:** inspect source availability → select a supported indicator/period → compare only published population groups and uncertainty → inspect geographic reference/completeness separately → export source-linked statements. Population-weighted, service-coverage and local-health outputs appear only after their data gates are met.

**Pre-dialysis branch:** select a research cohort → inspect inclusion and follow-up → compare descriptive outcomes/baselines → examine held-out progression estimates or verified repeated-measurement replay → read source-population limits.

**Dialysis branch (conditional):** after a dataset and study are feasible, inspect cohort/label and held-out evaluation. Temporal replay is an optional later view only with suitable released timing; no patient histories or replay are required for the starting scope. This does not control a machine or advise a patient.

**Scenario branch (unselected):** establish a named question → confirm inputs and assumptions → select a method/output → compare scenarios with explicit uncertainty. A temporal horizon is needed only for a justified temporal mechanism. Changing a predictor does not establish a causal effect.

## 7. Existing-build reuse and competition boundary

F-001–003/008/026 provide run, population, mapping and provenance foundations; revise data adapters/labels as needed. F-004–007 remain synthetic reporting/scoring mechanisms, not newly validated clinical models. F-009/024/025 may support optional sensitivity experiments; scarcity-based invitation allocation is no longer the product center. F-010/011 retain historical environmental context. F-012–018 remain optional fictional workflow examples, without claiming the interview established a coordination need. F-019 supplies facility-verification concepts, not a confirmed service network. F-020 is outside the main story; F-021–023 remain synthetic analyses until a distinct observed-data implementation exists.

**Current technically supported starting scope:** source catalogue, checked national-indicator comparison, geographic reference/completeness view and a proposed citizen-facing experience demonstrable with fictional profiles. Its exact UX/output remains open. These are proposed features, not implemented work. Public population weighting, geographic coverage, C models/augmentation and D simulations are conditional upgrades, not release promises. Select the substantive empirical/scenario extension only after actual files support a meaningful question. The existing data do not yet justify claiming a complete LGU decision-support product or adequate competition analytical depth.

The [primer](../../evidence/competition/%5B00%5D%20Primer.pdf), pp. 10–14, supplies the recorded 24 October 2026, 11:59 PM deadline, repository, ≤20-slide deck including references/appendices and ≤3-minute video constraints; no amendment is verified here. Meaningful data acquisition, method selection, held-out evaluation and reproducibility serve the analytical brief. Any interactive extension must serve a supported analytical question; visual novelty does not establish health impact or technical validity.

## 8. Open decisions and success measures

Still unresolved: secured A variables/geographic resolution; B service type/coordinates; actual CKD-ROUTE schema; dialysis identifier/timing availability; which one empirical study fits the competition; D’s first population scenario/output and justified parameter ranges; intended institutional decision and usefulness. These are bounded research questions, not requests for additional interviews or approvals.

Proposed technical success: reproducible source-linked results, leakage-aware evaluation, visible missingness and appropriately scoped uncertainty. Citizen benefit, real-world clinical performance, institutional adoption, prevention and treatment outcomes remain unmeasured. All new components are proposed; no tests, pipelines or models were executed for this document revision.
