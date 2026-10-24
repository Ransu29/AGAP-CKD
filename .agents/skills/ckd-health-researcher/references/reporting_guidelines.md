# Reporting Guidelines and Templates

Use the official checklist (EQUATOR Network, https://www.equator-network.org)
and cite the version you used.

## Checklist map

| Study type | Guideline | Risk-of-bias / appraisal tool |
|---|---|---|
| Prediction model development/validation (incl. ML) | TRIPOD+AI (2024) | PROBAST (+AI) |
| Observational study | STROBE | ROBINS-I / ROBINS-E |
| Routinely collected data (EHR, registry, claims) | RECORD (extends STROBE) | ROBINS-I |
| Diagnostic accuracy (e.g. point-of-care creatinine/uACR) | STARD 2015 | QUADAS-2 / QUADAS-AI |
| Randomised trial of an AI intervention | CONSORT-AI / SPIRIT-AI (protocol) | RoB 2 |
| Early live clinical evaluation of AI decision support | DECIDE-AI | — |
| Systematic review / meta-analysis | PRISMA 2020 | AMSTAR 2 |
| Economic evaluation | CHEERS 2022 | — |
| Simulation study | ADEMP (Morris, White & Crowther 2019) | — |
| Sex and gender reporting | SAGER | — |
| Certainty of a body of evidence | GRADE | — |

## Methods-section template (prediction study)

1. **Source of data** — design, setting, dates; synthetic/simulated if so.
2. **Participants** — eligibility, recruitment, how screening participation arose.
3. **Outcome** — definition, equation (CKD-EPI 2021), thresholds, timing,
   single vs. confirmed measurement, blinding to predictors.
4. **Predictors** — definition, timing relative to prediction, units; excluded
   outcome-defining variables (leakage control).
5. **Sample size** — Riley criteria; events available.
6. **Missing data** — amount per variable, assumed mechanism, handling.
7. **Analysis** — model type, tuning, internal validation (bootstrap/CV),
   calibration method, threshold selection rule, software and versions, seeds.
8. **Performance measures** — discrimination, calibration, net benefit, with CIs.
9. **Fairness / subgroups** — pre-specified groups and metrics.
10. **Ethics and data governance** — approval, consent, privacy safeguards.

## Results-section template

1. Flow diagram (eligible → measured → analysed), with reasons for exclusion.
2. Participant characteristics by outcome status (table 1).
3. Model specification (full equation or link to code and config).
4. Performance with CIs; calibration plot; decision curve.
5. Subgroup performance table.
6. Sensitivity analyses and how conclusions change.

## Limitations prompts

- Is the outcome a single measurement rather than confirmed CKD?
- Who was not tested, and how might they differ?
- Are climate/geographic exposures area-level (ecological)?
- Were parameters assumed rather than observed? Which ones drive results?
- Would the findings transport to another province, country or care level?
