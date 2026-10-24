# ADEMP Simulation Study Protocol Template: AGAP-CKD

> Follows the ADEMP framework (Morris, White & Crowther 2019) for simulation studies in clinical prediction, spatial epidemiology, and healthcare resource allocation.

## 1. Aims (A)
- **Primary Scientific Question:** [e.g., Does climate-augmented triage increase case-detection yield under extreme heat anomalies compared to clinical-only triage?]
- **Secondary Questions:** [e.g., How robust is allocation equity across municipalities when participation is Missing Not At Random (MNAR)?]
- **Target Audience / Stakeholder:** Public health planners, provincial health officers (Laguna), nephrologists.

## 2. Data-Generating Mechanisms (D)
- **Population Base:** Synthetic resident frame on H3 resolution 8 cells (sensitivity test at H3 res 7) generated from WorldPop age-sex rasters.
- **Clinical Generator:**
  - Diabetes and Hypertension generated via logistic models calibrated to national health data (FNRI 2023 NNS).
  - True biological state ($Y_{true}$): Race-free CKD-EPI 2021 eGFR $< 60$ mL/min/1.73 m² or uACR $\ge 30$ mg/g.
- **Climate Scenarios:**
  - ERA5-Land heat index anomalies across Laguna municipalities.
  - Heat effect scenarios: `[zero, weak, strong]` (defined in `config/params.yaml`).
- **Observation / Participation Mechanisms:**
  - `MCAR`: Random outreach response.
  - `MAR`: Participation dependent on observed age and facility proximity.
  - `MNAR`: Participation dependent on unobserved true renal vulnerability and heat exposure.
- **Longitudinal Dynamics (SIM-09):**
  - Follow-up at 90 and 180 days.
  - Measurement variability: Serum creatinine CV 5%, uACR CV 30%.
  - Annualized eGFR decline: 1.0 mL/min/1.73 m²/year.
  - Persistent abnormal ($> 90$ days) vs. transient abnormality.

## 3. Estimands & Targets (E)
- **Primary Estimand:** Case detection yield (True Positive cases identified per 100 screening panels allocated).
- **Secondary Estimands:**
  - Positive Predictive Value (PPV) at target sensitivity 90%.
  - Geographic Gini coefficient (equity of allocation across municipalities).
  - Number Needed to Screen (NNS) to detect one persistent abnormality.

## 4. Methods (M)
- **Candidate Models:**
  1. Random / Population-proportional baseline.
  2. Clinical-only logistic regression (age, sex, DM, HTN).
  3. Climate-augmented model (clinical features + ERA5-Land heat index anomalies).
  4. Inverse-Probability-Weighted (IPW) model to adjust for non-random participation.
- **Allocation Policies:**
  - Budget: 500 tests across study area (100 per participating facility).
  - Maximum travel distance: 20 km.
  - Exploration shares: 0.0, 0.1, 0.2, 0.3 (epsilon-greedy exploration).

## 5. Performance Measures (P)
- **Statistical Performance:**
  - Empirical bias and Mean Squared Error (MSE) of predicted risks.
  - Calibration slope and intercept across repetitions.
  - Monte Carlo Standard Error (MCSE) for all summary statistics.
- **Repetitions & Seeds:**
  - Profile: `config/fast.yaml` ($N=2,000 \times 5$ reps) for rapid validation; `config/full.yaml` ($N=10,000 \times 200$ reps) for publication results.
  - Master seed: `2026` (never hard-coded; imported from `config/params.yaml`).

## 6. Parameter Provenance Audit
- [ ] Run `python .agents/skills/ckd-health-researcher/scripts/parameter_register_validator.py`.
- [ ] All generator parameters verified in `config/parameter_register.yaml` with evidence classification (`source-supported`, `derived`, `assumed`).
