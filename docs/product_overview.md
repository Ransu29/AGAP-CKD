# AGAP-CKD product overview

**Accessible, Geospatial, Awareness-focused, and Population-level CKD Risk Assessment**: early interception of kidney risk.
PJDSC 2026. Prepared 23 October 2026.

> AGAP-CKD is a simulation-based proof of concept. Every resident and laboratory record is **synthetic**, and service points and their capacities are **hypothetical**. Outputs are **screening flags used to set priorities**. They are not diagnoses or medical advice. The app does not send messages or book appointments.

---

## 1. Summary

AGAP-CKD helps a rural health unit (RHU) or local government decide **who to invite** when it has fewer kidney-screening panels (creatinine + urine albumin–creatinine ratio, uACR) than at-risk adults. It then helps staff **work that list**: contact, testing, review and recovering slots that residents decline.

It combines real open data on a common H3 hexagonal grid:
- population and boundaries;
- 35 years of ERA5-Land temperature and rainfall;
- a facility register.

On top of that it simulates residents, questionnaire reports and laboratory results. The result is a full screening round that can be planned, compared and audited from start to finish, with no real patient data.

**Problem.** Chronic kidney disease (CKD) progresses with no symptoms. Screening is cheap per test but limited by budget, laboratory capacity and travel distance. Invitations that go purely by proximity or at random miss many high-risk adults. Heat and dry spells may add kidney stress for outdoor workers, but that effect is uncertain and must not be overclaimed.

**Value.**
1. Ranks residents by risk using questionnaire answers, optionally adding a community-level climate exposure.
2. Allocates a fixed budget under real limits (slots per service point, a maximum travel distance, optional minimums per municipality) and explains every decision.
3. Freezes an approved plan into a worklist that staff can act on, kept separate from what-if planning.
4. Measures what each strategy finds, and what it misses, in a reproducible simulation, including negative findings.

---

## 2. Users and their jobs

| User | Primary job | Where in the product |
|---|---|---|
| RHU screening coordinator | Approve a round, contact residents, record results, follow up on flags, refill declined slots | Plan → Worklist |
| Municipal / LGU planner | Choose budget and strategy; check coverage by municipality and access gaps | Plan controls, community map, "How this plan was formed" |
| Barangay health worker | Collect and correct questionnaires | Resident report |
| Analyst / evaluator (judges, researchers) | Check whether the climate signal or a strategy helps, with honest uncertainty | Evaluate, Resident weather, `outputs/runs/` |

---

## 3. How it works

```
 Public data             Synthetic population            Risk scoring              Allocation                 Coordination
 ───────────             ────────────────────            ────────────              ──────────                 ────────────
 WorldPop age–sex  ─┐    Residents sampled by H3  ─┐     Questionnaire-only  ─┐    Budget, slots, 20 km  ─┐   Approved round (frozen)
 geoBoundaries     ─┼──▶ Traits, reports, labs     ├──▶  or + climate model   ├──▶ strategy, municipal   ├─▶ Worklist: contact → test
 ERA5-Land climate ─┘    MCAR/MAR/MNAR reporting  ─┘     Threshold @ 90% sens.┘    minimums              ─┘   → review → recover slots
                                                                                                             ▼
                                                                     Simulation evaluation (hidden outcomes, labelled "eval")
```

1. **Data**: build the adult population on H3 resolution-8 cells, checking that the total population is conserved. Freeze the inputs of the climate frame.
2. **Simulate**: create separate cohorts for training (2021–23), validation (2024) and deployment (Jan 2025 – Sep 2026), with a geographic holdout.
3. **Train**: fit three logistic models:
   - questionnaire-only;
   - climate-augmented;
   - climate-augmented, weighted for participation.

   Set thresholds at 80% and 90% target sensitivity.
4. **Allocate**: compare random, population-proportional, pure-risk, and risk-plus-exploration (10/20/30%) invitation strategies.
5. **Evaluate**: report yield, coverage, missed positives by cause, cost per positive, and subgroup and population-weighted results.
6. **Later stages**:
   - a spatial-resolution sensitivity check;
   - 90- and 180-day follow-up;
   - monthly surveillance with a forecast check;
   - integrity checks.

`make all` runs the pipeline; `make demo` opens the app. For the full methodology see `docs/pipeline_methodology_and_feature_audit.md`.

---

## 4. Features

### 4.1 Plan

| Feature | What it does |
|---|---|
| **Community map** | A 2D street map of Laguna from a bundled offline OpenFreeMap pack, plus an optional 3D H3 hex view and a plain outline fallback. Clicking a community filters the resident queue |
| **Resident queue and decision card** | A searchable queue. Each resident shows the draft invitation, the actual reason they were or were not selected, their known inputs and modelled access |
| **"Why this score?"** | An optional waterfall showing how much each input contributed to the score |
| **Budget and strategy controls** | Panel budget, strategy (risk / outreach mix), active planning model. Draft edits apply only on submit |
| **Compare screening plans** | Side-by-side strategy outcomes on the same residents and random draws |
| **"How this plan was formed"** | Plain-language account of the model, budget, outreach share, capacity, access limit and minimums per municipality |
| **Municipal coverage minimums** | Checked for feasibility before allocation, including a joint capacity test; they are never relaxed silently |
| **Invitation CSV export** | Always covers the whole cohort, whatever filters are on screen |

### 4.2 Resident report

- Questionnaire review and correction for fictional form and SMS inputs: diabetes, hypertension, family history, outdoor work, prior screening, outdoor hours in the last 7 days.
- Previewing a report never changes the plan. Only **Apply report** does, and applied reports persist within the session.
- A report that arrives after the screening date is masked and does not count.
- Shows revision history, rejected attempts and duplicates across channels.

### 4.3 Worklist (approved round)

- **Create demo screening round** freezes:
  - the model and scores;
  - the selection reasons;
  - capacities and thresholds;
  - the distance limit;
  - the full priority order and the order for replacements.
- **Five queues**: Needs contact, Awaiting screening, Needs review / follow-up, Tasks complete, Declined / withdrawn.
- **Case work**:
  - record contact outcomes, specimen collection and fictional results (creatinine mg/dL, uACR mg/g);
  - eGFR is calculated with CKD-EPI 2021;
  - set owners, due dates and next actions.
- **Safe flags**:
  - An abnormal component opens a *review task*, not a diagnosis.
  - A partial panel stays incomplete.
  - Revisions keep earlier values.
- **Slot recovery**: a decline before testing releases the slot. A replacement is proposed from the frozen order, in the same municipality and service point and within the access limit, then confirmed by staff. No answer, or an overdue case, never frees a slot.
- **Browse and filter** cases (overdue, due today, unassigned), with a 10-case page and short aliases.
- **Persistence**: storage is local SQLite and survives reloads. Rounds can be archived with read-only history and exports.

### 4.4 Resident weather and climate comparison

- Compares invitations under the questionnaire-only and climate models on the same cohort, budget, strategy and draws: which residents are added, removed or unchanged, with optional markers on the map.
- For each resident it shows 30 days of temperature and rainfall on a shared local-day axis, marks the screening date, and compares against the 1991–2020 seasonal reference.
- Shows where the climate data came from: the source ERA5 cell, cells reassigned along the lakeshore, and the share of the population covered.

### 4.5 Evaluate and Data

- **Simulation evaluation**:
  - comparison with random invitation;
  - a four-part chart of missed cases: outside the access limit, feasible but not invited, invited but did not complete, found;
  - a table of swaps between pure risk and outreach;
  - calibration.

  Hidden outcomes appear only here, labelled "(eval)".
- **Community surveillance**:
  - monthly synthetic screening flags, Jan 2021 – Sep 2026;
  - the gap between observed and undetected flags;
  - seasonal-naive forecasts compared with forecasts that include climate.
- **Clinic verification workspace**: 111 facilities from the PhilHealth YAKAP register, all starting unverified. Staff can record checked coordinates, panel capability and capacity, with dated evidence. Revisions are append-only and the queue downloads as a worksheet. Verified clinics do **not** yet replace the hypothetical service points.
- **Research gateway (demo)**: synthetic interest, eligibility (40 or older and a reported DM or HTN) and withdrawal. It is kept completely separate from screening decisions.
- **Run safeguards**: the evidence header reads the saved integrity results. A missing artefact shows as unavailable, never as a pass.

### 4.6 Data and reproducibility

| Feature | Detail |
|---|---|
| Content-addressed runs | `outputs/runs/<config>-<code>-<inputs>/`. A change to any parameter, code or input creates a new run and never overwrites an old one |
| Provenance manifest | `data/manifest.yaml` records the publisher, licence, checksum, CRS, units and processing for each source |
| Configuration profiles | fixture (offline test), public (real population), weather preview, **climate (recommended demo)**, fast and full experiment profiles |
| Experiment grid | `make experiments`: 3 participation mechanisms × 3 climate effect sizes × repetitions, with paired differences and labelled Monte Carlo uncertainty |
| Offline operation | Bundled map tiles, fonts and climate extract. A browser check confirms there are no internet calls |
| Tests | About 35 pytest modules, plus Playwright browser checks (`make verify-browser`) |

---

## 5. Safety, trust and data principles

1. **A screening flag is not a diagnosis.** Every label, export and report says "abnormal screening flag", "review task" or "persistent abnormal pattern", never "CKD" or "AKI".
2. **Zero leakage.** Laboratory values, hidden outcomes, follow-up measurements and hidden traits are on a configured denylist. Model inputs must also be on an allowlist, which fails closed. Climate windows end the day before the screening date.
3. **Hidden outcomes are kept separate.** Simulated truth appears only in views labelled as evaluation. It never fills staff tasks, worklists or exports.
4. **A plan cannot overwrite an approved round.** Draft changes never alter approved invitations.
5. **No silent fallback.** A missing input, an infeasible coverage minimum or an incomplete climate reference stops the run with an explanation. Nothing is invented to fill the gap.
6. **Honest uncertainty.** Negative findings are shown. The climate effect is labelled an assumed simulation input, and the participation weights are labelled as known only to the simulator.

---

## 6. Roadmap (planned, not yet built)

| Area | Item | Status |
|---|---|---|
| Care coordination, Release A | Continuing resident record; education and contact agreement (EN/FIL); Today's tasks; testing episodes with clinical review; referrals | Proposed (`docs/revised_implementation_plan_2026-10-22.md`) |
| Care coordination, Release B | Verified service finder; patient-reported blood pressure; LGU community dashboard; four-destination navigation | Proposed |
| Data | Constrained WorldPop; OSM road travel times; verified clinic coordinates and capacity; definition-matched HTN/DM prevalence; full PAGASA ENSO series | Open (SRS DATA-01 partial) |
| Modelling | Estimated (not oracle) participation weights; calibration plots; repeated clinical-vs-climate comparisons; new features from the feature audit | Open |
| Evaluation | Full 200-repetition Monte Carlo suite; usability session with health workers | Waiting on data and time |
| UX | Story tab, analyst view, result card, disclaimer banner, plain-language pass; mobile layout | Open / deferred |
| Deferred on purpose | BATO S1–S3 stratification; outdoor-hours report warning; scenario switcher | Deferred |

---

## 7. Known limitations

- Every clinical state, laboratory value, behaviour, service point, capacity and cost is simulated or assumed.
- The climate–kidney effect is an **assumed simulator coefficient**, not an estimate. In one saved run the climate model scored slightly worse than the questionnaire-only model.
- The climate score is a community-level proxy from about 9–11 km reanalysis cells. It is not personal exposure and not a forecast.
- Distances are straight-line. The basemap is display only.
- WorldPop 2020 is used for every year from 2021 to 2026. Barangay-level analysis is not possible without verified boundaries.
- This is a desktop coordinator prototype; the phone layout is not finished.

For a full list of findings and suggested feature improvements, see `docs/pipeline_methodology_and_feature_audit.md`.
