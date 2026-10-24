# AGAP-CKD

**Accessible, Geospatial, Awareness-focused, and Population-level CKD Risk Assessment**
*Early interception of kidney risk* — PJDSC 2026

> All patient-level data in this repository are **synthetic**. The prototype gives a **risk level**
> (a priority for a kidney test), never a diagnosis or medical advice.

AGAP-CKD is a short **kidney risk check** for adults in Laguna who have never had a kidney test. It tells
them whether to get a simple blood and urine test, by app, by SMS, or through a field health worker's
offline tablet, and gives provincial planners area totals of where risk and awareness gaps concentrate.
Requirements are in [PRD v3](docs/AGAP-CKD-PRD-v3.md) and the [screen content plan](docs/AGAP-CKD-Screen-Content-Plan.md).

## The prototype

| View | Who | What it does |
|---|---|---|
| **Citizen app** | Adult in Laguna | Consent, safety pre-check, the PRD v3 questionnaire, risk level (Low / Medium / High) with the next step and date, reasons, tips and PhilHealth YAKAP facilities; Learn and Care pages |
| **SMS** | Resident with a basic phone | The same check as a numbered-reply SMS conversation (simulated; no real messages are sent) |
| **Field health worker tablet** | Barangay health worker or midwife | The same check read aloud in a large layout, a referral note for Medium/High, and Sync |
| **Analyst** | Provincial or LGU planner | Province map by municipality (age-standardised share at Medium or High, coverage, awareness gap), municipality detail, climate context and model quality |

**One risk check for every channel** ([ADR 0003](docs/ADR/0003-one-offline-web-app-for-all-channels.md)): the
same questions, the same frozen logistic-regression model, its saved cut-offs and the **guideline floor**
([ADR 0002](docs/ADR/0002-guideline-floor-overrides-model.md): diabetes or high blood pressure is never "Low").
Heat is never part of a person's level ([ADR 0001](docs/ADR/0001-heat-out-of-individual-risk-level.md)). The
model's probability is never shown. The cross-reference of each rule to its code and test is in
[`docs/channel-consistency.md`](docs/channel-consistency.md).

## Quick start

Requirements: Python 3.12+ (tested with 3.14), Node.js 20+ (tested with 22), `make`.

```bash
git clone https://github.com/Ransu29/AGAP-CKD.git
cd AGAP-CKD
python3 -m venv .venv && source .venv/bin/activate   # Windows: py -m venv .venv; .venv\Scripts\activate
pip install -r requirements.txt
(cd frontend && npm ci)

# Build the data once (a few minutes; no download or API key needed)
make prepare-climate   # ERA5-Land daily table from the committed extract
make triage            # train the risk-level model, set its cut-offs, benchmark it
make analyst           # analyst map, climate and model-quality data

# Run (two terminals)
make api               # FastAPI on http://127.0.0.1:8000
make web               # open http://127.0.0.1:5173
```

Tests: `make test` (Python, about 4 minutes) and `make test-fe` (frontend). Project audits:
`python .agents/skills/ckd-health-data-scientist/scripts/leakage_scanner.py --features <list>` and
`python .agents/skills/ckd-health-researcher/scripts/parameter_register_validator.py`.

## How it works

```
frontend (React, Vite)  ──/api──▶  api/main.py (FastAPI)
  citizen · SMS · field · analyst      ├─ /api/risk-check/*  ─▶ src/agap/risk_check_service.py ─▶ frozen model (outputs/)
                                       └─ /api/analyst/*     ─▶ outputs/analyst/*.json (make analyst)
```

**Risk-level model** ([notebook](notebooks/03_retrain_prd_v3_model.ipynb), `src/agap/triage.py`)

- **Outcome:** an *abnormal kidney screen*, one measured eGFR < 60 or urine ACR ≥ 30 (KDIGO 2024); a screening
  outcome, not a diagnosis.
- **Data:** a simulated development cohort of Laguna adults (`src/agap/simulate/risk_check.py`): Laguna's age
  structure, odds ratios from the Thai simplified score study and other sources, diagnosis awareness with
  "I don't know", truncated labs and noisy day-0 measurement. Prevalence is set to 12.76% (Tran et al., 2017).
  Every parameter is classified as source-supported, derived or assumed in
  [`config/parameter_register.yaml`](config/parameter_register.yaml).
- **Model:** L2 logistic regression on 18 questionnaire features. Lab values, hidden traits, kidney status and
  heat are never inputs (leakage guard).
- **Cut-offs**, set on a validation cohort and saved with the run: Medium-or-High catches ≥ 85% of abnormal
  screens; High has ≥ 2× the overall abnormal rate. The guideline floor is applied after the model.
- **Benchmark:** the Thai simplified score on the same held-out people, plus a prevalence sensitivity check at
  8%, 12.8% and 18%.

**Analyst view** (`src/agap/analyst.py`, `scripts/build_analyst.py`): 4,300 simulated checks scored by the same
risk check, spread by adult population (PSA 2024 Census); Medium/High share age-standardised to Laguna; privacy
rules (areas under 10 checks withheld, 10–49 faded, top reasons hidden under 30). Checks recorded by the app and
the tablet are added. Climate context: monthly rainfall and hot days (heat index ≥ 41 °C) from ERA5-Land.

## Key results (simulated data)

Frozen run `3fa0a298f6ea` (commit `de2888e`, seed 2026); held-out test cohort of 5,000 simulated adults.

| | AGAP model + floor | Thai simplified score |
|---|---|---|
| Abnormal screens caught (Medium or High) | **86.5%** | 58.5% |
| AUROC | **0.711** | 0.691 |
| Abnormal rate Low / Medium / High | 5.5% / 8.6% / 23.7% | 7.7% / 17.8% / 44.0% |
| Share referred (Medium or High) | 69.3% | 32.7% |

The guideline floor changed 19 of 5,000 levels. The High tier misses its 2× target out of sample (23.7% vs
24.8%) and in every prevalence scenario. These are results on simulated people and say nothing yet about real
clinical accuracy.

## Data sources

| Source | Used for | Licence |
|---|---|---|
| ERA5-Land hourly reanalysis (Copernicus C3S; Muñoz-Sabater et al., 2021), via the ECMWF ARCO data lake | Temperature and rainfall (extract committed in `data/raw/era5_land/arco/`) | CC BY 4.0 |
| ERA5-Land temperature and humidity via the Open-Meteo archive | Heat index for hot days (`scripts/collect_heat_index.py`) | CC BY 4.0 |
| WorldPop 2020 age–sex rasters (Bondarenko et al., 2020) | Laguna age structure, municipal age mix | CC BY 4.0 |
| PSA 2024 Census of Population (OpenSTAT) | Adults per municipality, age-standardisation weights, barangays (`scripts/collect_psa_population.py`) | Public statistics |
| geoBoundaries ADM2/ADM3 | Province and municipality boundaries | CC BY 3.0 IGO |
| PhilHealth YAKAP accredited clinics (CY 2026) | Facility list, all "not yet verified, call ahead" | Public register; redistribution terms not established |

What is committed and what is downloaded is described in [`data/README.md`](data/README.md); sources, checksums
and licences are in [`data/manifest.yaml`](data/manifest.yaml). Generated outputs (`outputs/`) and recorded demo
checks (`data/reports/`) are not committed. Seeds, thresholds and settings live in
[`config/params.yaml`](config/params.yaml).

## Limitations

- All validation is on simulated data; prevalence is borrowed from a Vietnamese study (no population-based
  Philippine study was found). Effect sizes tagged "assumed" are not evidence.
- The Medium cut-off refers about 69% of adults, and High misses its 2× target out of sample.
- Analyst-map differences between municipalities come only from age structure; channel split, last sync and
  DONE replies are illustrative.
- The heat index is a 0.1° grid estimate and counts fewer hot days than PAGASA station data.
- Scoring runs in the local API; in-browser offline scoring, real SMS and facility verification are Phase 2.
- Taglish copy needs native-speaker review.

## Repository structure

```
agap-ckd/
├── api/main.py              # REST API for the prototype (risk check, field sync, analyst data)
├── frontend/                # React + TypeScript + Vite app (see frontend/README.md)
├── src/agap/
│   ├── risk_check_service.py   # one risk check for every channel (answers → level, next step, facilities)
│   ├── triage.py               # risk-level model, cut-offs, guideline floor, Thai benchmark
│   ├── analyst.py              # analyst area totals, climate context, model quality
│   ├── simulate/               # synthetic residents and the PRD v3 risk-check cohort
│   ├── climate/                # ERA5-Land processing and heat index
│   ├── data/, models/, allocation/, evaluate/   # earlier simulation pipeline
├── scripts/                 # entry points used by the Makefile and data collection scripts
├── config/                  # params.yaml (every number) and parameter_register.yaml (provenance)
├── data/                    # see data/README.md
├── docs/                    # PRD v3, screen content plan, glossary, ADRs, channel cross-reference
├── notebooks/               # 03_retrain_prd_v3_model.ipynb (method, results, verification)
├── tests/                   # pytest suite
├── app/                     # earlier Streamlit prototype (make demo)
├── references.txt           # proposal references (APA 7th)
└── outputs/                 # generated, not committed
```

## Earlier simulation pipeline

The project began as a simulation of climate-aware test allocation. That pipeline and its Streamlit app remain
for reference and testing, but PRD v3 moved test allocation to future work: the risk level is the first step of
allocation. The app separates editable **Plan** scenarios from a saved staff **Worklist** and keeps hidden
simulated outcomes on a separate **Evaluate** page.

```bash
make all                              # small, explicitly synthetic fixture pipeline
make all CONFIG=config/climate.yaml   # real Laguna geography + ERA5-Land climate (inputs bundled)
make demo                             # Streamlit at http://localhost:8501 (CONFIG=... to override)
```

## References

The proposal's references are in [`references.txt`](references.txt) (APA 7th). The references for the risk-level
model (Thakkinstian et al., 2011; Bang et al., 2007; Tran et al., 2017; Garofalo et al., 2017; and others) are
listed in APA 7th at the end of the [retraining notebook](notebooks/03_retrain_prd_v3_model.ipynb) and in
[PRD v3](docs/AGAP-CKD-PRD-v3.md#references).

## Contributing

1. Create a branch from `main` (e.g. `engine3-allocation`).
2. Run `make test` before opening a pull request.
3. At least one teammate reviews before merging.

## License

MIT — see [LICENSE](LICENSE).
