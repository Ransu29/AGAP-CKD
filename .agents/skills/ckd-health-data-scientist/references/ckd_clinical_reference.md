# CKD Clinical Reference for Data Scientists

Quick reference for building CKD data products. Verify against the current
guideline before using any value in a clinical-facing context; record the
source in `config/parameter_register.yaml` when a value enters the pipeline.

## Definition and staging (KDIGO 2024)

CKD = abnormalities of kidney structure or function, present for **> 3 months**,
with implications for health. Markers include eGFR < 60 mL/min/1.73 m² or
albuminuria (ACR ≥ 30 mg/g, ≥ 3 mg/mmol).

| GFR category | eGFR (mL/min/1.73 m²) | Description |
|---|---|---|
| G1 | ≥ 90 | Normal or high |
| G2 | 60–89 | Mildly decreased |
| G3a | 45–59 | Mildly to moderately decreased |
| G3b | 30–44 | Moderately to severely decreased |
| G4 | 15–29 | Severely decreased |
| G5 | < 15 | Kidney failure |

| Albuminuria category | ACR (mg/g) | ACR (mg/mmol) |
|---|---|---|
| A1 | < 30 | < 3 |
| A2 | 30–300 | 3–30 |
| A3 | > 300 | > 30 |

Risk is read from the combined G × A "heat map", not from either axis alone.

## eGFR: CKD-EPI 2021 (race-free, creatinine)

```
eGFR = 142 × min(Scr/κ, 1)^α × max(Scr/κ, 1)^−1.200 × 0.9938^Age × 1.012 [if female]
κ = 0.7 (female), 0.9 (male);  α = −0.241 (female), −0.302 (male);  Scr in mg/dL
```

Creatinine µmol/L ÷ 88.4 = mg/dL. Implemented in `src/agap/simulate/kidney.py`.
Not valid for children, AKI (non-steady state), extremes of muscle mass; cystatin C
(CKD-EPI 2021 creatinine–cystatin) improves accuracy when available.

## Acute kidney injury (KDIGO 2012)

Any of: serum creatinine rise ≥ 0.3 mg/dL within 48 h; rise to ≥ 1.5× baseline
within 7 days; urine output < 0.5 mL/kg/h for 6 h. AKI confounds single-time-point
CKD screening — repeat testing distinguishes transient from persistent abnormality.

## Risk tools

| Tool | Predicts | Inputs | Notes |
|---|---|---|---|
| KFRE (Tangri) 4-variable | Kidney failure at 2 and 5 years | Age, sex, eGFR, ACR | Validated for eGFR < 60; KDIGO 2024 suggests 5-year risk ≥ 3–5% to inform nephrology referral |
| KFRE 8-variable | Same | + calcium, phosphate, bicarbonate, albumin | Marginal gain over 4-variable |
| CKD Prognosis Consortium equations | Incident eGFR < 60 | Demographics, comorbidities | For screening-population risk |

## Measurement variability (within-person)

| Measure | Typical CV | Implication |
|---|---|---|
| Serum creatinine | ≈ 4–6% | Small eGFR changes near 60 are noise |
| Spot uACR | ≈ 30% or more | Confirm albuminuria with 2 of 3 samples over 3–6 months |

## Risk factors relevant to community screening

Diabetes, hypertension, age, obesity, family history of kidney disease,
cardiovascular disease, nephrotoxic drugs (NSAIDs, some herbal remedies), history
of AKI, low birth weight, and **occupational heat stress / dehydration**
(CKD of unknown or non-traditional cause, e.g. agricultural workers in hot
climates). Treat heat–kidney effects as a hypothesis with emerging evidence, and
area-level climate exposure as ecological, not individual, exposure.

## Endpoints in CKD research

- Kidney failure (dialysis, transplant, or eGFR < 15).
- Sustained eGFR decline of ≥ 40% (accepted surrogate, FDA/EMA workshop).
- eGFR slope (chronic slope after acute treatment effect).
- Albuminuria change (supportive surrogate).
- Death is a **competing risk** for kidney failure in older cohorts.
