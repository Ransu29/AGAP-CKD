# AGAP-CKD

A citizen risk check that tells adults in Laguna who have never had a kidney test whether they should get one.

## Language

**Risk check**:
The short self-reported questionnaire a citizen or health worker fills in, ending in a risk level.
_Avoid_: Screening, test, screening test

**Risk level**:
Low, Medium or High: the citizen-facing band of how likely it is that the person has undiagnosed kidney problems. Never a diagnosis.
_Avoid_: Score, result, screening result, positive/negative

**Abnormal kidney screen**:
A simulated person with eGFR below 60 or urine ACR of 30 or more; the outcome the model learns to predict. Internal term only, never shown to citizens.
_Avoid_: CKD case, positive, diagnosis

**Guideline floor**:
The minimum risk level a person gets from diabetes or hypertension, whatever the model says, so the app never contradicts kidney-testing guidelines.
_Avoid_: Override, rule bump

**Safety pre-check**:
The questions asked before the risk check that send minors, pregnant people and people with kidney warning symptoms straight to a doctor, without a risk level.
_Avoid_: Triage, exclusion screen

**Field health worker**:
A health worker, such as a barangay health worker or midwife, who brings the offline risk check to remote areas and does not run kidney tests.
_Avoid_: RHU health worker, BHW user, tester

**Referral note**:
The short note a field health worker gives a Medium or High resident, naming their risk level, top reason and the nearest facility that can test.
_Avoid_: Referral slip, prescription, request form

**Re-check**:
Answering the risk check again at a later date. Not a lab test.
_Avoid_: Re-screen, re-test, follow-up test

**Kidney test**:
A blood test (creatinine for eGFR) and a urine test (albumin-to-creatinine ratio), done together at a facility.
_Avoid_: Blood test (alone), screening, check

**Next check date**:
The month shown on every result telling the person when to do their next re-check or kidney test.
_Avoid_: Due date, follow-up date

**People checked**:
The residents who completed a risk check in an area. This is the base for every analyst figure, which describes them, not the whole population.
_Avoid_: Residents, population, cases

**Coverage**:
Risk checks completed in an area divided by its adult population.
_Avoid_: Reach, penetration, uptake

**Awareness gap**:
The share of people checked in an area who answered "I don't know" to diabetes or high blood pressure.
_Avoid_: Unknown rate, missing data

**Benchmark score**:
A published non-laboratory CKD score (the Thai simplified score) run on the same simulated people, so the model's performance is shown against a known reference.
_Avoid_: Baseline model, SCORED
