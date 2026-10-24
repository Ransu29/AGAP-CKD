# Model Card Template: AGAP-CKD Screening Risk Model

> **Context:** All patient-level data in AGAP-CKD are synthetic. Model outputs are screening triage flags, not diagnoses.

## 1. Model Details
- **Model Name:** [e.g., Clinical-Only Logistic / Climate-Augmented Risk Model / Propensity-Weighted Triage]
- **Version & Commit:** [e.g., v1.2 (`git rev-parse --short HEAD`)]
- **Date & Author:** [Date, Agent/Author]
- **Target Population:** Synthetic adult population ($\ge 18$ years), calibrated to Laguna province, Philippines.
- **Intended Purpose:** Prioritise outreach invitations and allocate scarce urine albumin/creatinine ratio (uACR) and serum creatinine testing panels under fixed clinic budgets.
- **Out-of-Scope Uses:** Diagnostic decision-making, individual clinical management, acute kidney injury detection, prescription decisions, or use on pediatric populations.

## 2. Clinical Framing & Non-Negotiable Boundaries
- [ ] **Screening Flag $\neq$ Diagnosis:** Confirmed CKD requires structural or functional abnormalities persisting $>3$ months (KDIGO 2024). A single abnormal screening test is only an initial abnormal flag.
- [ ] **Leakage Audit Completed:** `scripts/leakage_scanner.py` passed with 0 violations. None of `forbidden_features` (e.g. `creatinine`, `egfr`, `uacr`, `y_true`, or 90/180-day follow-up values) are in the feature set.
- [ ] **Operating Point:** Operating threshold tuned to fixed target sensitivity: **90%** (configured in `config/params.yaml`).

## 3. Features & Data Sources
- **Demographic & Clinical:** Age, sex, self-reported diabetes, self-reported hypertension, family history of kidney disease.
- **Environmental & Geospatial:** ERA5-Land heat index anomalies, extreme heat exposure days, distance to nearest Rural Health Unit (RHU) / dialysis facility.
- **Participation & Observation Model:** Model trained accounting for reporting mechanism ([MCAR / MAR / MNAR]).

## 4. Performance Metrics (with 95% Confidence Intervals)

| Metric Layer | Metric Name | Score | 95% CI | Baseline Comparison |
|---|---|---|---|---|
| **Discrimination** | AUROC | | [ , ] | vs Clinical-only baseline |
| | AUPRC | | [ , ] | vs Prevalence baseline |
| **Calibration** | Calibration Intercept | | [ , ] | Target: 0.0 |
| | Calibration Slope | | [ , ] | Target: 1.0 (flag if < 0.8) |
| | Brier Score | | [ , ] | |
| **Clinical Utility** | Sensitivity (Target 90%) | | [ , ] | |
| | Specificity | | [ , ] | |
| | PPV (Positive Predictive Value) | | [ , ] | |
| | Net Benefit (at screening threshold) | | [ , ] | vs Screen All & Screen None |

## 5. Decision Curve Analysis (DCA) Summary
*Run `python .agents/skills/ckd-health-data-scientist/scripts/decision_curve.py --file <predictions.csv>` and paste summary:*
- **Screens Conducted per 1,000:** [X]
- **Cases Detected per 1,000:** [Y]
- **Avoided Unnecessary Screens per 1,000:** [Z]

## 6. Fairness & Subgroup Performance Audit
Evaluate calibration and sensitivity across subgroups to ensure equitable triage:
- **Sex:** Male vs. Female
- **Age Bands:** 18–39, 40–59, 60+
- **Geography:** High-density urban (e.g., Calamba, Santa Rosa) vs. rural / upland municipalities
- **Occupational Heat Exposure:** Outdoor agricultural/manual workers vs. indoor workers

## 7. Human-in-the-Loop & Operational Safety
- Staff (Barangay Health Workers, screening nurses) can override priority flags in the screening workspace.
- Unused or declined screening slots are returned to the pool for reallocation (slot recovery).
- All patient-level records are marked synthetic; no personal identifiers are persisted or shared.
