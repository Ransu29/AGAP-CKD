# AGAP-CKD critical analysis: proposal, interview, SSOT and code

Review date: 23 October 2026. Branch: `analysis/critical-review-2026-10-23` (from `main` @ `3a8a054`).
Final project submission closes **24 October 2026, 11:59 PM**. Finalists are announced on 4 November, and the live demo with judges' Q&A is on 14 November ([00] Primer, pp. 9–12). Recommendations are split by those two dates.

## How to read this report

Every claim is tagged with the strongest evidence behind it:

| Tag | Meaning |
|---|---|
| **[Code]** | Implemented and observed in source, tests or a saved run |
| **[SSOT]** | Documented in `research/ssot/PRD.md` / `ARCHITECTURE.md` (on `bry-research`), which describe `main` @ `a88eb9b` |
| **[Proposed]** | Proposal, review brief, personal notes or this report. Not implemented. |
| **[Interview]** | Reported by the two dialysis nurses (Minutes.pdf; Dialysis-Nurse-Interview-Notes.pdf). This is one joint conversation, not two independent sources. |

Evidence gathered today:

- `make test` → **351 passed** (212 s).
- `leakage_scanner.py` on the seven deployed predictors → PASS.
- `parameter_register_validator.py` → PASS.
- `decision_curve.py` on the saved fixture run's deployment predictions.
- Metrics were read from the saved fixture run `outputs/runs/31eeb9a6f51e-…`. This is a single repetition under MAR with heat OR 1.2 and **synthetic sine-wave climate**, so its numbers illustrate behavior and are not results.

Interviewees are referred to by role only, because naming consent is still open (Minutes, p. 5).

### Two corrections to the brief that commissioned this review

1. **Engine numbering.** The brief lists "Engine 2 Triage & Allocation, Engine 3 Surveillance, Engine 4 Longitudinal/Research". The proposal (pp. 2–3), PRD and code instead use:
   - **E1** Reporting
   - **E2** El Niño exposure and surveillance
   - **E3** Assessment, triage and allocation
   - **E4** Genome–phenome research gateway

   Longitudinal follow-up is SIM-09/10, a simulator scenario, not an engine. Use the proposal numbering in the deck. Judges have the proposal.
2. **What the nurses said vs. what the brief attributes to them.** The nurses did **not** describe BHW/RHU record-keeping burden, missed-appointment tracking or slot recovery. They are dialysis nurses whose view of screening is second-hand (Notes, p. 1). Their heaviest task is monthly lab day at the dialysis center (Minutes, p. 3). Asked about reassigning a refused slot, they said only that "patients have the right to refuse" (Minutes, p. 4). The "Broken Bridge" they described is **refusal and denial after a nephrologist's advice, and stopping hypertension maintenance**. It is not loss to follow-up after community screening. Several features are therefore *consistent with* the interview without being *validated by* it. That distinction matters in Q&A.

---

## 1. Strategic alignment: proposal vs. prototype

### How the value proposition evolved

| Proposal promise (pp. 1–3) | Current state | Verdict |
|---|---|---|
| Common geographic grid (ERA5-Land, WorldPop, boundaries, YAKAP clinics, OSM) on H3 res 8 | **[Code]** Fixture and public geography; H3 res 8 frame; ERA5-Land snapshots in `config/climate.yaml`. YAKAP/PhilHealth register becomes a clinic *verification worksheet* (`clinics.py`), separate from the hypothetical allocator service points. OSM is display only. | Delivered, with honest downgrades: service points stay hypothetical. |
| E1 citizen reporting with quality checks; R and S generated separately under MCAR/MAR/MNAR; nonusers kept in the frame | **[Code]** Form and SMS normalization, validation, dedup and revision history (`reports.py`). Separate report, invitation and completion processes (`experiment.py:189–222`). Nonreporters stay in the cohort with missing predictors. | Delivered. |
| E2 climate exposure; clinical vs clinical+climate; zero/weak/strong heat scenarios; surveillance vs seasonal-naïve | **[Code]** `hot_dry_score`; paired model comparison; OR 1.0/1.2/1.5 grid in `make experiments`; monthly surveillance with seasonal-naïve baseline. | Delivered. Interpretation is weak (see §4). |
| E3 clinical LR, climate LR, propensity-weighted LR; geography/time split; AUROC/AUPRC/Brier/calibration/FNR; reporters vs eligible population; random / proportional / risk / risk+exploration allocation | **[Code]** All present (`experiment.py::train`, `allocate_policy`, `allocation_metrics`). | Delivered. IPW is oracle-only (see §4). |
| "MNAR sensitivity bounds otherwise" (p. 3, §5) | **Not found.** MNAR weights are labelled "oracle" (`experiment.py:330`). There is no tipping-point or δ-adjustment analysis. | **Gap against an explicit promise.** |
| H3 7 **and barangay-level** sensitivity | **[Code]** Res 7 only. Barangay level is recorded as a limitation (`spatial.py:78`). | Partial. Disclosed. |
| E4 voluntary research gateway, kept separate | **[Code]** Eligibility rule, interest states and matched comparison cohort (`research.py`). It never touches allocation. | Delivered as specified. |
| *(Not in proposal)* Approved, frozen screening round; staff worklist; contact → specimen → result → review; declined-slot recovery; archive; clinic verification | **[Code]** `workflow*.py`, SQLite with append-only events, optimistic concurrency. | New scope (see below). |

### Drift or maturation?

**Legitimate maturation, with one strategic risk.** Every foundational promise except MNAR bounds and barangay sensitivity is implemented and tested. The coordination workspace is additive. It answers the proposal's own problem statement about "fragmented community health data" (p. 2) and the "Execution and Impact → Real-World Application" judging criterion (Primer, p. 10).

The risk is **narrative incoherence**. The deck may now tell three stories: climate-aware triage, ethical allocation and nurse-validated follow-up. Only the first two are what the proposal asked judges to evaluate. Evidence for the climate story weakened after the interview. Evidence for the third rests on an interview that did not test it. Section 5 proposes a single story.

---

## 2. Grounding in the clinical interview

| Pain point (interview) | What the prototype does | Fit |
|---|---|---|
| **Late presentation.** "Most had no idea… many had stopped their hypertension maintenance" (Minutes, p. 4). | Ranks *all* adults, including nonreporters, for a creatinine + uACR panel; E1 asks about DM/HTN/family history. | **Directionally aligned, mechanistically blind.** The questionnaire (`reports.py:11`: DM, HTN, FAM, OUT, PRIOR) has **no field for medication interruption, BP reading, or "told you have HTN but not taking meds"**. That is the single most actionable signal the nurses gave. |
| **Silent disease → nonreporters.** | **[Code]** In the saved run, nonreporters are 71% of the cohort (2,139/3,000) and hold **62% of positives** (252/404). Pure risk-ranking gives them **6.0% completion coverage vs 23.9% for reporters**, and still misses 202 of their 252 positives. Adding 10–30% random outreach barely moves this (6.0% → 6.6–6.7%). | **The prototype structurally deprioritises the "didn't know" population the nurses described.** This is the most important finding in this report (see §4.3, §5). |
| **Refusal, denial and fear** ("in denial and cannot accept the diagnosis", Minutes, p. 3). | **[Code]** Contact outcomes are No answer / Retry / Accepted / Declined (`workflow.py:539`). A decline releases the slot. There is no "wants explanation", "concern stated" or education record. | **Not addressed.** The 22 Oct review brief (§2, "Add education and support") specified this. It has not been built. |
| **Broken bridge after a result** (patient advised, does not act). | **[Code]** An abnormal result opens a review task. "Follow-up requested" takes a free-text action and date. There is no referral object, no referral-sent / attended / unknown states, no communication-of-result task, and no resident record beyond one round. | **Partially addressed.** The task exists, but the bridge itself (referral, attendance) is untracked. |
| **Workflow burden** (BHW/RHU). | Worklist queues, owners, due dates, Overdue/Unassigned filters, CSV export. | **Unvalidated.** The interview did not touch RHU work. It is plausible, but the claim needs an RHU conversation. |
| **Data fragmentation** ("LGU does not know who the patients are", Minutes, p. 4). | Community map and planner; the LGU view is aggregate. | Aligned in principle. There is no LGU-facing aggregate of *recorded* (not modelled) follow-up gaps yet. |
| **Heat is not a direct CKD cause** in the nurses' experience (Minutes, p. 2). | Climate is a *predictor* and a *data-generating coefficient*. | **Tension.** The code already frames climate as experimental. The deck must as well. |
| **Distance is no longer a barrier** (for dialysis) (Minutes, p. 3). | 20 km great-circle access limit (`params.yaml:39`); MAR completion decays with distance. | Not contradicted: that was dialysis access, not screening access. In the fixture run, **zero positives are access-excluded**, so the access constraint is untested in the demo profile. |
| Bloodwork-only testing; no uACR mentioned. | Panel = creatinine + uACR. | Keep uACR (KDIGO). Mark local uACR availability at RHU level as an **open assumption**, because nobody asked. |

### Naive or unrealistic clinical assumptions in the software

1. **Self-report equals truth.** `dm_report = dm_true` exactly for reporters (`experiment.py:202`). In the Philippines, a large share of hypertension and diabetes is undiagnosed. The nurses' patients "did not know". A model fed perfect self-report overstates discrimination and hides the population most at risk. Add a configurable awareness (sensitivity) parameter for DM and HTN reports.
2. **The day-0 screening value is noise-free and equals hidden truth** (`experiment.py:174–186`). Measurement variability (creatinine CV 5%, uACR CV 30%) is applied **only** at 90/180 days (`longitudinal.py:77–79`). Real single tests misclassify near thresholds, and the follow-up regresses toward the mean.
3. **There is an empty band between "abnormal" and "normal" labs.** eGFR is drawn from 30–59.9 or 65–120 (`params.yaml:77–78`), so no one lives at eGFR 60–65. Abnormal uACR has a median of 80 mg/g. Together with assumption 2, this yields **97% persistence** (393/404 initial positives persistent at 180 d; only 2–4 transient per policy). A nephrologist will recognise that as unrealistic. Albuminuria in particular frequently fails to persist on repeat testing. This undermines the KDIGO-persistence story the longitudinal scenario exists to tell.
4. **The hypothetical acute-event rate is high.** 218 events at 90 d and 275 at 180 d among 3,000 adults (7–9% per visit). The configured 2% rate is per reference resident; the age, DM and HTN terms inflate it. This is labelled "hypothetical", but a judge will ask.
5. **Non-response never frees a slot.** "No answer / overdue keeps the slot" (PRD F-013). In practice, silent non-response, not an explicit decline, is the dominant way slots are wasted.

---

## 3. Architecture and workflow audit

### Plan vs. Worklist separation: strong

**[Code]**

- Draft plans are session-local. They are recomputed on Compare and never alter the export when filters change.
- Approval (`workflow.py::build_round_snapshot`) freezes invitations, model, settings, service points and the replacement order into an immutable snapshot. Writes are refused after archive. Approved assignments do not change when the draft changes.
- Hidden truth is excluded from operational projections by allowlist.

This is the most defensible engineering in the repo. Show it in the demo.

### State persistence and recovery

| Capability | Status |
|---|---|
| Append-only events, stale-version rejection, idempotent requests | **[Code]** `workflow_store.py` |
| Declined-slot recovery: frozen order, same municipality and service point, recheck inside transaction, started panels cannot release | **[Code]** `workflow.py:613`, `workflow_store.py::confirm_replacement` |
| Overdue / due-today / unassigned queues sorted by due date, not score | **[Code]** `workflow_overview.py` |
| Release after N failed contacts or after X days unreachable | **Missing.** Slots held by non-responders are never recovered. |
| Resident record that outlives a round; multiple encounters or specimens | **Missing.** One specimen episode per resident per round (F-014). Cross-run rounds are deliberately not attached to new cohorts. |
| Several concurrent tasks (result review, communication, referral) | **Missing.** One generic follow-up action and date. |
| Authentication / role enforcement | **Missing by design.** Owner fields are labels (PRD §3). State this upfront. |

### Engine data contracts

| From → to | Contract | Assessment |
|---|---|---|
| E1 → E3 | Schema-v2 report (`DM/HTN/FAM/OUT/PRIOR` = Y/N/U/None, `HRS`, `DATE`). Only DM/HTN/FAM/OUT reach the model; PRIOR and HRS are recorded but not predictors. Late reports are masked at cutoff. | Clean and leakage-safe. PRIOR is a wasted signal: a recent normal panel should lower priority. |
| E2 → E3 | `hot_dry_score` per resident from the ERA5 cell, 30-day window at cutoff. | Clean. Scientifically weak: an acute 30-day exposure predicting a *chronic* prevalent abnormality (see §4.2). |
| E2 surveillance | Monthly aggregate flags per 100 tested. Hidden columns are rejected before forecasting. | Clean. Climate helped at 1-month horizon (MAE 1.82 vs 2.18 without climate) and **hurt at 3 months** (2.22 vs 2.17). Report both. |
| E3 → Worklist | Immutable snapshot, then slots and events. | Strong. |
| SIM-09 longitudinal ↔ Worklist | Deliberately disjoint: simulator follow-up never populates staff records. | Correct separation. The UI should say so where both appear. |
| E4 | Reads reported answers only; outputs a matched cohort CSV. It never writes back. | Correct isolation. |

There is no HTTP or API layer: Streamlit calls domain code directly (ARCHITECTURE §1). That is fine for a prototype. Judges scoring "Scalability and Deployment" (Primer, p. 12) will ask. Have one slide that names the seam: domain modules plus SQLite would sit behind an API with an auth and audit layer.

---

## 4. Clinical data science and methodological rigor

### 4.1 Safety and framing: pass

- **[Code]** A grep of `app/`, `src/`, `README.md` and the presenter script found no use of "diagnosis" except negations ("not a diagnosis"). The one hit, `docs/demo_presenter_script.md:283`, reads "create a review task rather than a CKD diagnosis".
- Outcome comments, the longitudinal `LABEL`, and the PRD glossary all preserve flag ≠ diagnosis and persistent-abnormal ≠ CKD.
- The KDIGO >3-month chronicity criterion is represented by the 180-day persistence definition. **Recommendation:** name KDIGO's ≥90-day criterion explicitly in UI copy next to "still abnormal at 180 days". Assumption 3 in §2 currently makes persistence nearly automatic, so the label is technically right but empirically hollow.

### 4.2 Zero leakage and measurement reality

- **Leakage: pass.** An allowlist (`check_allowed_features` against `CLINICAL + hot_dry_score`) is enforced before fitting, plus a forbidden list in `params.yaml`. The scanner passes on all seven predictors. Deployment labels are cleared (`experiment.py:224`). Minor defense-in-depth gap: `forbidden_features` omits `dm_true`, `htn_true`, `family_true`, `outdoor_true`, `observation_probability`, `completion_probability` and `observed_label`. The allowlist blocks them today; add them so the scanner is self-sufficient.
- **Measurement variability: partial.** It is correctly parameterised and sourced (`params.yaml:115–116`), but only for follow-up (assumption 2 in §2).
- **Circularity of the climate finding.** This is the issue a data-science judge will raise first:
  - The outcome is generated as `log(heat_or) × hot_dry_score` (`experiment.py:173`).
  - The climate model is a logistic regression on the *same* additive form.
  - Logistic regression is therefore the correctly specified model. Calibration slope ≈ 1.00 is guaranteed rather than earned.
  - Any climate "gain" recovers an assumed coefficient. In the saved run: AUROC 0.782 → 0.787, AUPRC 0.365 → 0.369.
  - Decision-curve net benefit at threshold 0.10 is 0.070 vs 0.072. Both beat treat-all (0.039) and treat-none.

  The OR grid 1.0/1.2/1.5 in `make experiments` is the right defence. Lead with **"under OR = 1.0 the climate model gains nothing, as it should"**, not with the gain.
- **Clinical plausibility of the exposure window.** A 30-day hot–dry score predicting a *prevalent* eGFR <60 or uACR ≥30 is weak biology. CKDu hypotheses concern cumulative, repeated occupational exposure. At minimum, add a seasonal or cumulative exposure variant, or frame the 30-day score explicitly as "recent heat context for outreach timing", not aetiology.

### 4.3 Selection bias (MCAR / MAR / MNAR)

- **Strong.** Mechanisms are explicitly separated across reporting, invitation and completion. Observation probabilities are stored. Labels exist only for Round-0 completers. Reporter vs all-population metrics are reported separately. Weight support and ESS are exported (ESS 609 of 624 labels; minimum observation probability 0.144, so no positivity violation).
- **Weak.**
  1. IPW uses **simulator-known** probabilities. Real deployments must *estimate* them, and under MNAR they cannot be estimated. The proposal promised MNAR sensitivity bounds; they are absent.
  2. The model treats missingness as a predictor (missing-indicator plus median imputation). Under MAR in this simulator that is legitimate. Its *consequence* is the 4× coverage gap against nonreporters in §2. That is a fairness and equity problem, not a statistical one. Under MNAR with negative report odds (`report_mnar_log_odds: -0.8`), nonreporters are *sicker*, and the gap becomes harmful.
  3. Random exploration is untargeted, so it does not repair the gap. **Reach among nonreporters needs to become a first-class, reported allocation constraint.**

---

## 5. Gap analysis and recommendations

### Top 3 vulnerabilities a judge will challenge

1. **"Your climate result is baked in."** A data scientist will ask this. The simulator injects OR 1.2 and the model recovers it; in the demo profile the exposure is a sine wave. Defence: the OR = 1.0 null scenario, the surveillance result where climate hurt at 3 months, and the framing "we built the test harness that a real climate–kidney signal would have to pass".
2. **"Your triage ignores the people the nurses described."** A nephrologist or health-equity judge will ask this. Nonreporters hold 62% of positives but receive 6% coverage under risk-ranking. Self-report is assumed perfect, and the questionnaire cannot capture "stopped my BP medicine".
3. **"What happens after the abnormal result?"** A health informaticist will ask this. There is no referral tracking, result communication, education record or resident record across rounds. Non-responders hold slots forever. Persistence is 97% because day-0 labs are noise-free. The "bridge" is asserted, not modelled or tracked.

### What to build next

**Before 24 Oct (submission; hours, not days).** Prefer disclosure and small config/UI changes over new subsystems.

1. **Surface the nonreporter coverage gap and offer a reach floor.** Show "coverage among nonreporters vs reporters" in the plan results.
   - The data already exists in `allocation_metrics` (`experiment.py:588–597`); expose it in `decision_support.py` and `walkthrough.py::_plan_results`.
   - Add one planner strategy: "Priority + nonreporter outreach share". Draw exploration slots from nonreporters rather than at random, in `demo.STRATEGIES` and `experiment.policy_order`.
   - Put the share in `params.yaml` and the register.

   This converts vulnerability 2 into a headline feature, and it is a small change.
2. **Add a medication-interruption question to E1.** Add `MED` (Y/N/U: "stopped or ran out of BP/sugar medicine in the past 3 months") to `reports.py:11`, the SMS parser and the form. Record it but keep it out of the model (like PRIOR) until simulated. This directly encodes the nurses' strongest observation. The slide line is "the interview changed our questionnaire".
3. **Fix the deck and README framing.**
   - Use proposal engine numbering.
   - Treat the interview as **problem validation** (late awareness, fragmentation, education), not feature validation.
   - List known simulator limitations explicitly: perfect self-report, noise-free day-0 labs, oracle IPW, missing MNAR bounds, fixture climate.

   Judges reward stated limitations under "Challenges and Mitigation Strategies" (Primer, p. 10).

**Before 14 Nov (finals; days).**

1. **Measurement realism and persistence.**
   - Apply analytical and biological variability to day-0 observed labs; keep `y_true` on the underlying value.
   - Close the eGFR 60–65 gap with a continuous distribution.
   - Re-run SIM-09 and report transient vs persistent honestly.
   - Add self-report awareness parameters for DM and HTN.
   - Files: `experiment.py::simulate_cohort`, `params.yaml` `simulator.laboratory`, `parameter_register.yaml`, `tests/test_longitudinal.py`, `tests/test_kidney.py`.
2. **The bridge: referral and communication tasks plus non-response release.** Implement the 22 Oct brief's §2–3 minimal slice:
   - **Contact outcome:** add "wants explanation / concern stated", with optional concern text.
   - **Tasks:** separate result communication and referral tasks with sent / attended / unknown states.
   - **Non-response release:** a staff-confirmed slot release after a configured number of unanswered attempts.
   - Files: `workflow.py` (`EVENT_TYPES`, `normalize_event`, `_state`), `workflow_ui.py::_contact_form` / `_review_form`, `workflow_store.py` allowlists.
   - The defensible metric is *time from result to recorded communication or referral*, not outcomes.
3. **MNAR sensitivity analysis.** A δ-adjustment or tipping-point table: how much would the outcome odds among nonreporters have to differ before policy rankings flip? This closes the explicit proposal promise and is cheap given the existing experiment grid (`cli.py::experiments`).

### Presentation narrative

One spine, three acts. Keep to 3 minutes in the video and 10 minutes on stage.

1. **The problem (nurse-grounded).** "Most first-time dialysis patients had no idea. Many had stopped their BP medicine." (dialysis head nurse, Batangas; paraphrased.) PhilHealth's largest spend is hemodialysis. The LGU does not know who the patients are. → *CKD is found too late, and nobody holds the list.*
2. **The decision (data science, honest).** Limited panels. Whom to invite? Show random vs proportional vs risk vs risk+nonreporter outreach under MCAR/MAR/MNAR. Show that climate is tested against a **null**: "we don't claim heat causes CKD; we built the harness that a climate signal must beat, and at OR 1.0 it correctly adds nothing." Show the equity trade-off explicitly.
3. **The follow-through (operational).** A frozen, auditable round. One resident's journey: contact, concern, panel, missing component visible, review, referral tracked. One declined slot reused under the original rules. Close on "a screening flag is not a diagnosis; our job is to make sure no flag is lost."

Close Q&A prep with the four questions in §5's vulnerabilities and the stated simulator limitations. Do not claim the nurses validated slot recovery or RHU workflow. Say instead that an RHU interview is the next discovery step.

---

## Appendix: evidence log

| Check | Result |
|---|---|
| `python -m pytest -q` | 351 passed, 212.8 s |
| `leakage_scanner.py --features age,female,dm_report,htn_report,family_report,outdoor_report,hot_dry_score` | PASS |
| `parameter_register_validator.py` | PASS |
| DCA, fixture run, clinical vs climate, deployment n=3,000, prevalence 13.5% | NB@0.10: 0.0698 vs 0.0722 (treat-all 0.0385); NB@0.20: 0.0336 vs 0.0349 (treat-all −0.082) |
| Model metrics (`model_metrics.csv`) | AUROC clinical 0.782 / climate 0.787 / IPW 0.786; calibration slope 0.99 / 1.00 / 0.97 |
| Allocation (`metrics.csv`, 500 slots) | Detected positives: random 51, proportional 50, risk 123, risk+10/20/30% 117/110/110 |
| Longitudinal (`longitudinal_metrics.csv`) | 393/404 initial positives persistent at 180 d |
| Surveillance (`surveillance_forecast_metrics.csv`) | MAE h=1: naïve 2.98, no-climate 2.18, climate 1.82; h=3: 2.98 / 2.17 / 2.22 |

The saved run is a fixture profile with one repetition. Numbers are illustrative of mechanism, not estimates of real-world performance.

---

## Addendum (23 Oct, evening): Version 3 PRD comparison and implementation

### Comparison with the Version 3 PRD (`origin/bry-research` @ `59ddc35`)

Team decisions recorded on 23 October:

- **Submission:** the current build, framed with Version 3's rules. V3 analytics (A–D) go under Future Directions.
- **Users:** three separate views (citizen, health worker, LGU / analyst).
- **Version 3:** team-approved as the requirements baseline.

| Version 3 rule | How this branch applies it |
|---|---|
| V3-011 citizen interface for the two citizen states (no known diagnosis; diagnosed before or during dialysis) | **[Code]** Citizen view (`src/agap/citizen.py`, `role_views.render_citizen`). It uses DATA_SPEC CI-01 to CI-05 wording. Every answer is optional. Profiles are stored in the synthetic namespace with `verified=False`. Guidance depends on the stated kidney state and is marked as draft pending clinician review. No score, rank or result value is shown. |
| V3-013 every displayed number names source, population, period, unit and evidence type | **[Code]** `src/agap/provenance.py::provenance_caption`, applied to the plan coverage card, simulation evaluation, LGU tables, surveillance and saved model metrics. A missing part raises an error instead of being omitted. |
| V3-014 / fixture data never labelled as Laguna | **[Code]** `geography_banner` warns on fixture runs. `geography_label` says "not the Laguna population". The Evidence page no longer claims public Laguna inputs on fixture runs. |
| DATA_SPEC defers medication lists and barrier tracking | Respected. The medicine-interruption question and the "wants explanation" contact outcome are **not** implemented. |
| V3 §7: allocation is "no longer the product center" | Allocation stays as the submission's demo. The new strategy is the equity fix, not a new product center. |

### Implemented on `feat/views-outreach-provenance` (uncommitted)

1. **"Priority + outreach to unreported residents" strategy.** A share of slots goes first to residents without a questionnaire, highest score first.
   - **Files:** `experiment.py::policy_order`, `allocate_policy`, `pipeline_policies`.
   - **Planner:** shown with a coverage-by-questionnaire card and a parity hint.
   - **Approved rounds:** freeze the strategy. A declined outreach slot is refilled from the next resident without a questionnaire (`workflow.py::replacement_candidate`, basis `unreported`).
   - **Pipeline:** the saved pipeline, spatial sensitivity and repeated experiments include `risk_unreported_50`.
2. **Role views.** A simulated sign-in screen with demo accounts for Health worker (RHU), LGU / public-health analyst, and Citizen; the sidebar shows the signed-in role and a Sign out button for switching.
   - **LGU / analyst:** municipal aggregates only, with counts of 1–4 shown as "<5" (`privacy.min_cell_size`).
   - **Labelling:** this is a demo role switch, not access control.
3. **Provenance labels and fixture banner** (above).

**What the share sweep shows** (saved fixture run, MAR, heat OR 1.2, one repetition, 500 panels):

| Plan | Positives found | Non-respondent coverage | Respondent coverage |
|---|---|---|---|
| Pure score | 123 | 6.0% | 23.9% |
| Unreported outreach 20% | 122 | 6.1% | 23.5% |
| Unreported outreach 50% (default) | 122 | 8.3% | 17.7% |
| Unreported outreach ~71% (parity) | 117 | 10.8% | 10.8% |
| Random | 51 | 10.1% | 13.1% |

A share at or below what pure ranking already gives non-respondents (~39% of slots here) changes nothing. Parity closes the coverage gap for about 5% fewer initial abnormal flags. These are synthetic, single-run numbers. Repeated MCAR/MAR/MNAR results are in `outputs/experiments/` (fast profile).

### Repeated experiments (fast profile, `outputs/experiments/bf0dc0ff5821-399574450f5f`)

**Setup:** 45 runs, MCAR/MAR/MNAR × heat OR 1.0/1.2/1.5 × 5 repetitions. Each run has 2,000 deployment adults and 500 panels. Values are means per mechanism.

| Mechanism | Plan | Positives found | Found among non-respondents | Coverage, no questionnaire | Coverage, answered |
|---|---|---|---|---|---|
| MCAR | Score only | 108.3 | 72.1 | 17.7% | 17.9% |
| MCAR | Unreported outreach 50% | 108.1 | 74.7 | 18.3% | 16.5% |
| MAR | Score only | 99.0 | 59.5 | 14.6% | 19.6% |
| MAR | Unreported outreach 50% | 97.9 | 61.5 | 15.2% | 17.8% |
| MNAR | Score only | 72.9 | 63.1 | 16.6% | 8.4% |
| MNAR | Unreported outreach 50% | 72.7 | 63.2 | 16.7% | 7.9% |

**Correction to §2 and §5.** The coverage gap against non-respondents is large only in the default 3,000-adult MAR run (6.0% vs 23.9%). It is modest under MAR in the fast profile, where 500 panels cover 25% of the cohort. It **reverses under MNAR**: when sicker people report less, the model's missing-answer indicator already moves non-respondents up the ranking.

The 50% outreach strategy costs at most about one detection in roughly 100. It narrows the gap where one exists and is neutral otherwise. Present it as a **safeguard whose value depends on the participation mechanism**, which is unknown in practice. Do not present it as a universal gain.

---

## Addendum (23 Oct, night): gaps closed on `feat/views-outreach-provenance`

All four "build before the finals" items from the gap list were built. They are uncommitted, with tests. The suite ran 390 passed; `leakage_scanner.py` and `parameter_register_validator.py` both pass.

| Gap | What changed | Where |
|---|---|---|
| Diagnosed residents competed for first screening | A citizen profile stating diagnosed CKD or dialysis (self-reported) removes the resident from first-screening invitations, with the reason "Reported known CKD". Approved-round replacements skip them. Health workers see the citizen profile, labelled self-reported and unverified. | `experiment.allocate_policy`, `citizen.known_ckd_residents`, `walkthrough._citizen_profile`, `workflow.replacement_candidate` |
| Screening points were hypothetical | Real-geography runs invite residents to the 111 PhilHealth YAKAP-accredited Laguna clinics: 52 at OpenStreetMap-mapped buildings, 19 at barangay centres, 40 at municipality centres. Capacity (20 per site) is assumed and panel capability unverified. Fixture runs keep hypothetical points. Name matching was tightened after hand review exposed false pairs. | `scripts/prepare_clinic_locations.py`, `registers.py`, `data/geography.registered_service_points`, `config/public.yaml` |
| No follow-through after an abnormal result | A reviewed abnormal result stays open until staff record that it was explained (in person, phone, home visit or SMS). A referral is tracked through Sent → Attended / Did not attend / Outcome unknown; "Did not attend" stays open. After 3 unanswered calls (configurable, frozen per round) staff may mark the resident Unreachable, which releases the slot for replacement. | `workflow.py` (`communication`, `referral`, `Unreachable`), `workflow_ui._results_and_referral`, `workflow_store.record_event` |
| Simulator too clean (97% persistence, perfect self-report) | SIM-11: a latent kidney-damage state drives the declared odds ratios. Underlying labs are continuous and truncated, not capped. The day-0 screen is one noisy measurement (creatinine CV 5%, uACR CV 30%), and Y is that measured flag. SIM-12: only 60% of people with DM or HTN know it (assumed, registered). | `experiment.simulate_cohort`, `longitudinal.simulate_followup`, `params.yaml`, `parameter_register.yaml` |

### Effect of the simulator change (climate profile, one repetition, 3,000 deployment adults)

| Measure | Before | After |
|---|---|---|
| Initial flags that persist at 180 days | 97% | 75% |
| Flags without underlying damage (false positive at day 0) | 0 by construction | 64 of 226 |
| Damage missed by the day-0 test | 0 by construction | 4 of 166 |
| Questionnaire model AUROC / calibration slope | 0.77 / 0.90 | 0.70 / 0.81 |

The lower AUROC is the honest cost of noisy labels and unaware reporters, not a regression.

A first attempt used uniform and capped lab draws, which piled people at the thresholds: 129 false flags and AUROC 0.61. Truncated, bell-shaped draws fixed that artifact.

Score ranking now concentrates on persistent cases: 33 persistent vs 3 transient among detected positives, against 8 vs 6 for random invitations.

### Repeated experiments with the new simulator (`outputs/experiments/43021e26f341-dee17b5d8f84`; 45 runs, fast profile)

| Mechanism | Plan | Positives found | Coverage, no questionnaire | Coverage, answered |
|---|---|---|---|---|
| MCAR | Score only / 50% unreported outreach | 100.7 / 101.0 | 17.8% / 18.3% | 16.6% / 15.6% |
| MAR | Score only / 50% unreported outreach | 93.6 / 94.1 | 13.5% / 14.4% | 21.7% / 19.5% |
| MNAR | Score only / 50% unreported outreach | 68.1 / 67.7 | 16.6% / 16.7% | 8.8% / 8.3% |

Score ranking finds about twice as many initial flags as random under every mechanism, including heat OR 1.0. The gain therefore comes from the clinical questionnaire, not the climate term. The outreach safeguard remains neutral on detections and narrows the gap only under MAR.

### Still open

- **Analyses not yet built:**
  - the MNAR sensitivity table;
  - the climate null shown in the app;
  - a resident record across rounds;
  - hospital-based dialysis units;
  - Filipino and SMS citizen channels;
  - clinician review of the citizen guidance text.
- **Not yet confirmed with real people or clinics:**
  - an RHU / BHW workflow interview;
  - whether each YAKAP clinic can actually run creatinine and uACR tests.
