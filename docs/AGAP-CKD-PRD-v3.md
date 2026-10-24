# AGAP-CKD PRD v3

Oct 23, 2026 · revised from v2 after the PRD audit

AGAP-CKD is a short **risk check** that tells adults in Laguna who have never had a kidney test whether they should get one, by app, SMS, or a field health worker's offline tablet. It follows Philippine and international guidelines: it targets people at risk and never tells healthy people with no risk factors to get a kidney test.

Terms in **bold** are defined in [GLOSSARY.md](GLOSSARY.md). Decisions that are hard to reverse are in [ADR/](ADR/). The per-screen content is in [AGAP-CKD-Screen-Content-Plan.md](AGAP-CKD-Screen-Content-Plan.md).

## What changed from v2

| Area | v2 | v3 | Why |
| --- | --- | --- | --- |
| Test named in copy | "a kidney blood test" | "a simple blood and urine test" | CKD includes albuminuria (urine ACR), which a blood test misses (KDIGO 2024) |
| Outcome the model predicts | Not defined | **Abnormal kidney screen**: eGFR < 60 or urine ACR ≥ 30 | Matches KDIGO and the Southeast Asian scores |
| Model vs guideline | Model alone sets the level | **Guideline floor** applied after the model | A person with diabetes must never be told "Low" |
| Heat | In each person's risk level | Removed from the risk level; kept as an advisory card, the outdoor-work item, and analyst context | [ADR 0001](ADR/0001-heat-out-of-individual-risk-level.md) |
| Before the questions | Nothing | Consent screen and **safety pre-check** | RA 10173; people with symptoms need a doctor, not a risk level |
| Questionnaire | 12 items, incl. salty/sweet food | Kidney stones and heart disease/stroke added; salty/sweet removed; branching and recall windows | Thai and SCORED scores; evidence review |
| Health worker | RHU health worker, can test | **Field health worker** with an offline tablet, cannot test, gives a **referral note** | Reaches remote areas without internet |
| Cut-offs | "High = 1 in 5 abnormal" | Defined by what they catch, robust to prevalence | See [Risk level](#risk-level) |
| Headline numbers | Standalone | Shown next to a **benchmark score** (Thai simplified score) | Avoids circular self-validation |
| SMS | Mocked answers | Full flow: opt-in keyword, consent, reminders, resume, single-segment messages | SMS research |
| Re-check | "Check again in a year" | Interval per state and age, tied to guidelines | See [Next steps and re-check intervals](#next-steps-and-re-check-intervals) |
| Analyst view | Raw shares by grid | Age-standardised, municipality only, coverage, awareness gap, privacy thresholds | See [Analyst view](#analyst-view) |

## Three views

| View | User | Job | Key screens |
| --- | --- | --- | --- |
| Citizen | Adult in Laguna who has never had a kidney test | Find out whether to get tested, and what to do now | Onboarding, consent, safety pre-check, questions, result |
| Field health worker | Barangay health worker or midwife bringing the tablet to remote areas; does not run kidney tests | Run the same risk check offline and give Medium/High residents a referral note | Today's checks, consent script, same form in a larger layout, referral note, sync |
| Analyst | Provincial or LGU health planner | See where risk and gaps are concentrated, and why | Province map, municipality detail, coverage, climate context, model quality |

Every channel (app, SMS, field tablet) uses the same questions, the same model and the same guideline floor, so a risk level means the same thing however it was collected ([ADR 0003](ADR/0003-one-offline-web-app-for-all-channels.md)).

## Citizen flow

1. **Onboarding:** three cards: what the kidneys do; that early kidney disease has no symptoms; that only a blood and urine test can check your kidneys.
2. **Invitation:** "Would you like to know if you may be at risk for kidney problems?" Never call it screening or a test.
3. **Consent:** what is collected, why, who sees it (only area totals), how long it is kept. Agree / Not now. "Not now" leads to the education cards only.
4. **Safety pre-check:** under 18, pregnant, or swelling / foamy, bloody or very little urine. Any yes → "Please see a doctor soon" with the facility list, and no risk level.
5. **Questions:** the questionnaire below, in its fixed order, one per screen, with progress shown.
6. **Result:** risk level, the not-a-diagnosis line, the next step and its date, the top reasons (illustrative), heat advisory when triggered, tips, the worried-reader note for Medium/High, and where to get checked.
7. **Partner booking:** "Book through a partner facility", shown as coming soon (Phase 2).

## Questionnaire v3

Every item has "I don't know". Questions are asked in this order on every channel, so a person who stops partway still gets a meaningful result.

| # | Item | Input | Recall window | Shown when | Why it is asked | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | Safety pre-check | One combined yes / no | Now | Always, first | Routes people who need a doctor | Practice |
| 1 | Age group | 18–39 / 40–49 / 50–59 / 60–69 / 70+ | — | Always | Strongest predictor in every score | Strong: Bang 2007; Thakkinstian 2011 |
| 2 | Sex | Female / Male | — | Always | Female sex scores +1 in SCORED (not because of the kidney equation, which needs a lab value) | Moderate: Bang 2007 |
| 3 | Municipality | Dropdown (Laguna's 30) | Now | Always | Facility list, heat card, area totals | Not used in the score |
| 4 | Diabetes | Yes / No / I don't know | "Has a doctor ever told you…" | Always | Guideline risk group | Strong: Bang 2007; KDIGO 2024 |
| 5 | High blood pressure | Yes / No / I don't know | "Has a doctor ever told you…" | Always | Guideline risk group | Strong: Bang 2007; KDIGO 2024 |
| 6 | Taking BP or sugar medicine | Regularly / Sometimes miss / Stopped / No medicine given / I don't know | Past 2 weeks | Item 4 or 5 = Yes | Adherence is linked to less kidney failure; used mainly for tips and reasons | Moderate (kidney failure outcome): Roy 2013; Chang 2015 |
| 7 | BP reading | Normal / High / Not measured / I don't know | Measured in the past 12 months; older counts as I don't know | Item 5 = No or I don't know | Self-reported "no" misses many cases; "High" counts as item 5 = Yes | Weak to moderate: Molenaar 2007; Abalos 2024 |
| 8 | Heart disease or stroke | Yes / No / I don't know | "Ever" | Always | SCORED item | Strong: Bang 2007 |
| 9 | Kidney stones | Yes / No / I don't know | "Ever" | Always | Thai score item | Moderate: Thakkinstian 2011 |
| 10 | Family history of kidney disease or dialysis | Yes / No / I don't know | "Ever" | Always | QKidney predictor; 20% of dialysis patients report an affected relative | Moderate: Hippisley-Cox 2010; Freedman 1997 |
| 11 | Height and weight | Numbers (cm or ft/in; kg or lb) or I don't know | Current | Always | BMI with Asian cut-offs (overweight ≥ 23, obese ≥ 27.5) | Moderate: Garofalo 2017; WHO 2004; PHEX 2026 |
| 12 | Heavy outdoor work | Yes / No / I don't know | "These days" | Always | Heat-stress mechanism of CKDu | Weak, effect assumed: Flouris 2018; Johnson 2019 |
| 13 | Kidney status | Never tested / Tested normal in the past 12 months / Told something was wrong / I don't know | Past 12 months | Always, last | Routes people already diagnosed to care | KDIGO 2024 |

**Removed:** salty or sweet processed food (no direct evidence; Du 2022 studied ultra-processed food in general).

**Item wording rules:** write the adherence item in the team's own words (MMAS-8 is a licensed questionnaire). Tagalog/Taglish wording is reviewed by a native speaker before the demo.

## Risk level

The model's score becomes Low, Medium or High. The score itself is never shown to citizens.

**How the level is set, in order**

1. **Scoring "I don't know":** for diabetes and high blood pressure, "I don't know" enters the model as Yes. Self-report misses many cases (Molenaar 2007), so "don't know" must never lower the level.
2. **Model:** the logistic regression gives a probability of an **abnormal kidney screen**.
3. **Cut-offs (from validation data, saved with the run):**
   - Medium-or-High is set where it catches **at least 85%** of abnormal screens.
   - High is set where the abnormal rate is **at least twice the overall prevalence**.
4. **Guideline floor** ([ADR 0002](ADR/0002-guideline-floor-overrides-model.md)):
   - Diabetes = Yes or high blood pressure = Yes (including a "High" BP reading) → at least **Medium**.
   - Both, or either one with age ≥ 60 → **High**.

| Level | What the citizen sees | Next step shown |
| --- | --- | --- |
| Low | "Your answers show a lower chance of kidney problems." | Healthy-habit tips and the next re-check date |
| Medium, without diabetes or high BP | "Some of your answers raise your chance of kidney problems." | "Get your BP and blood sugar checked at your health center first" |
| Medium, with diabetes or high BP | "Some of your answers raise your chance of kidney problems." | "Get a simple blood and urine test for your kidneys" plus the facility list |
| High | "Several of your answers raise your chance of kidney problems." | "Get a simple blood and urine test for your kidneys soon" plus the facility list |

**Wording rules**

- Every result says: "This is not a diagnosis. Only a blood and urine test can check your kidneys."
- Never use "you have CKD", "positive", "screening result" or "likely CKD". In simulation most High results are not abnormal, so High means "higher chance", never "probably sick".
- People with no risk factors never see "get a kidney test" (2026 Philippine Periodic Health Exam guideline, PHEX).
- Every result shows "Answer again sooner if you're diagnosed with diabetes or high BP, start or stop medicine, turn 50, 60 or 70, gain or lose a lot of weight, or after pregnancy."

## Next steps and re-check intervals

A **re-check** (answering the questionnaire again) is different from a **kidney test** (blood and urine lab). Once a person needs a kidney test, the app stops offering re-checks and reminds them to get the test instead.

| State after a check | Next step | When | Basis |
| --- | --- | --- | --- |
| Low, aged 40+ or any risk factor | Re-check | 12 months | USPSTF 2021 BP screening, Grade A |
| Low, aged 18–39, no risk factors, BP measured normal in the past 12 months | Re-check | 3 years | USPSTF 2021 (3–5 years; lower end chosen) |
| Medium without diabetes or high BP | Get BP and sugar checked, then re-check | When results are known; reminder at day 30 | PHEX 2026 (no kidney test for people without risk) |
| Medium or High with diabetes | Kidney test, then yearly | Reminders at day 7 and 30; then yearly | ADA Standards of Care 2026; KDIGO 2024 |
| Medium or High with high BP, no diabetes | Kidney test, then yearly | Same as above | **Practice-based**: KDIGO 2024 says there is no evidence-based interval |
| Told something was wrong | Go to care; leaves the risk check | Never re-check | — |

**Blood-sugar prompt:** anyone aged 40 or older, or with BMI ≥ 23, who answers No or I don't know to diabetes sees "Get your blood sugar checked" with its own date (PHEX 2026). The repeat is every 3 years if normal (USPSTF 2021, ADA 2026) and yearly if told prediabetes.

**Next date shown everywhere:** every result screen, SMS result and referral note shows "Next check: ⟨month year⟩" or "Next kidney test: ⟨month year⟩". App users and field-check residents get their date this way, without anything being stored about them.

**Pre-filling (app only):** answers that don't change (sex, height, stones, heart disease/stroke, family history) are saved on the phone and pre-filled next time with "Still correct?". SMS and field checks ask everything again.

## SMS channel

SMS covers people with basic phones. It uses the same items, order, model and floor as the app.

**Flow**

1. The resident texts **CHECK** to start.
2. A one-message privacy notice asks them to reply 1 to agree.
3. The safety pre-check is one combined yes/no.
4. Items follow in questionnaire order, with progress shown ("3/12").
5. The result arrives in 2–3 messages: risk level and the not-a-diagnosis line; one reason and the next step with its date; one facility.
6. Reminder opt-in is a separate question: "Can we send you up to 3 reminders? 1=Oo 2=Hindi".

**Message rules**

- Each message is one segment of ≤ 160 GSM-7 characters: no emoji, no curly quotes. "ñ" (as in Biñan) must be tested on real handsets.
- Replies are numbered, with **0 = Hindi ko alam** on every item.
- Loose replies are accepted ("1", "1.", "isa"). Anything unclear is re-asked once.
- Height and weight are accepted in either unit and echoed back to confirm ("165 cm, 70 kg? 1=Oo 2=Mali").
- **STOP**, **HELP** and **BACK** work at every step. **TULOY** resumes after a timeout. A stopped check still gets a risk level from the items answered, with the guideline floor applied.

**Reminders (retention)**

- **Medium/High:** reminders at day 7 and day 30 with the facility, plus "reply DONE if you got tested".
- **Low:** one re-check reminder at the next re-check date.
- **Limits:** at most 3 reminders per check, sent only between 7 AM and 9 PM. SMS reminders raise attendance by about 14% (Cochrane, Gurol-Urganci 2013).
- **Repeat answers:** if a person who opted in answers again within 30 days and gets a lower level than an earlier Medium/High, the reply says "Your earlier result still stands until you get a kidney test."

**Phone numbers**

- Stored only for people who agreed to reminders, separately from their answers.
- Stored together with the last risk level only.
- Deleted after the last reminder, on STOP, or at 13 months at most.
- A yearly reminder asks for consent again.

**Not in Phase 1:** load incentives, USSD (sessions time out in 2–3 minutes), and Messenger (Phase 2).

## Field health worker view

- **Who:** barangay health workers and midwives who visit remote areas with a tablet and do not run kidney tests.
- **Consent:** the worker reads a short consent script aloud and ticks "resident agreed". Residents who decline get the education cards only.
- **Same check:** the same pre-check, questions, model and floor, in a larger layout, working without internet.
- **Referral note** for Medium/High residents:
  - contents: risk level, top reason, next step, the nearest facility that can test, and the next date;
  - format: shown large so the resident can copy it onto paper, or the worker can write it on a card.
- **Today's checks:** check number, time, barangay and risk level. No names or ID numbers. Also shows the count of re-checks due this month in the areas the worker visits.
- **Sync:** checks are saved on the tablet, with a "3 checks waiting to sync" counter and a sync button once online. Conflict handling is Phase 2.
- **Optional reminders:** a resident may give a family member's number for reminders, with that person's consent, under the SMS phone-number rules.

## Facility list

- **Contents:** real general hospitals and health centers per municipality, each labelled "Not yet verified, call ahead". No logos.
- **Test field:** each entry has "Can do kidney tests (blood and urine): Yes / No / Unknown". All entries are Unknown for the demo.

## Analyst view

The analyst sees **aggregated area numbers only**, never individual checks.

- **Province map:**
  - **What it shows:** the age-standardised share of **people checked** at Medium or High, by municipality only (no neighbourhood grid), over the last 12 months.
  - **Display rules:** areas with < 10 checks are hidden; areas with < 50 are faded; a confidence range shows on hover.
  - **Label:** "among people checked", never "residents".
  - **Note:** "Includes people who don't know their BP or sugar status."
- **Municipality detail:**
  - number of checks, and the share done by field health workers vs the app;
  - **coverage** (checks ÷ adult population, PSA census);
  - **awareness gap** (share answering "I don't know" to diabetes or high blood pressure);
  - "last synced" for field areas;
  - "got tested" DONE replies, labelled "self-reported, SMS opt-ins only".
- **Top reasons:** the modifiable factors (stopped medicine, obesity, unknown BP or sugar status, heavy outdoor work) most over-represented compared with the province. Hidden for areas with < 30 checks. Illustrative for the demo.
- **Climate context:** heat and rainfall over time, in its own tab, labelled "Context only: not used in the risk level" and "community-level estimate".
- **Model quality** (collapsed, for judges): the model vs the benchmark score, cut-offs, the prevalence sensitivity check, and the run ID.
- **Every analyst screen** carries a "Simulated data" banner in the demo.
- **Counting:** the map counts checks, not people. Repeat checks are a known limitation.

## Privacy

- **Consent:** consent before questions on every channel (RA 10173: health data is sensitive personal information).
- **No identities stored:** no names or ID numbers are collected. Phone numbers are kept only under the SMS rules.
- **Small areas:** hidden below 10 checks; top reasons hidden below 30 checks; no cross-tabs by age or sex within an area.
- **Phase 2:** a data-sharing agreement with the LGU before any real data reaches analysts.

## Model and data changes tonight

1. **Simulator variables:**
   - Add: medicine adherence, family history, BMI (Asian cut-offs), BP reading, heart disease/stroke, kidney stones, heavy outdoor work.
   - Each effect is tagged source-supported, derived or assumed (see the [effect table](#simulator-effect-sizes)).
   - Remove salty/sweet food.
2. **Outcome:** the **abnormal kidney screen** is eGFR < 60 **or** urine ACR ≥ 30.
3. **Prevalence (derived):**
   - **Method:** set risk by age group, then adjust so that, on Laguna's adult age structure (PSA census), the overall abnormal-screen share is about **12–13%**.
   - **Basis:** Vietnam, Tran 2017: 12.76%, same definition. No population-based Philippine study was found.
   - **Caveat:** single-visit surveys overcount true CKD, which needs 3 months of abnormal results.
4. **Model:**
   - Retrain the same logistic regression. (The meeting called it "polynomial regression"; the code uses logistic regression, so use that name.)
   - Keep the leakage check.
   - **Remove the climate feature from the risk level** ([ADR 0001](ADR/0001-heat-out-of-individual-risk-level.md)).
5. **Cut-offs:** set them using the rule in [Risk level](#risk-level) on validation data, and save them with the run.
6. **Benchmark:** compute the Thai simplified score (age, diabetes, hypertension, kidney stones) on the same simulated people. Report both side by side: share of abnormal screens in Medium/High, abnormal rate per level, and AUC. The Thai score had a C-statistic of about 0.74 after validation.
7. **Prevalence sensitivity:** re-run the frozen model at 8%, 12.8% and 18% prevalence and report how the abnormal rate per level shifts.
8. **Freeze:** rebuild once, record the run ID, and take every slide number from that run.

**Fallback:** if the retrained model is not passing tests by 3:00 AM Oct 24:
- keep the frozen model, with the guideline floor added;
- show the new questions as "collected for the next model version";
- list retraining as future work.

### Simulator effect sizes

These are rough starting values for the simulator, not pooled estimates.

| Item | Suggested effect | Tag | Source |
| --- | --- | --- | --- |
| Age group | Largest driver; SCORED points 50–59 = 2, 60–69 = 3, ≥70 = 4 | Source-supported | Bang 2007 |
| Female sex | OR ≈ 1.2 | Source-supported | Bang 2007 |
| Diabetes, hypertension | OR ≈ 1.5–2.5 each | Source-supported | Bang 2007; Kshirsagar 2008; Thakkinstian 2011 |
| Heart disease or stroke | OR ≈ 1.5–2 | Derived | Bang 2007 (+1 point) |
| Kidney stones | OR ≈ 1.5–2 | Derived | Thakkinstian 2011 |
| Family history | RR ≈ 1.5–2 | Assumed | Hippisley-Cox 2010 (predictor; HR not extracted) |
| Obese (BMI ≥ 27.5) | RR ≈ 1.3 for low eGFR, 1.5 for albuminuria; overweight ≈ 1.0–1.2 | Source-supported | Garofalo 2017 |
| Stopped medicine (vs taking) | ×1.1–1.5 | Derived | Roy 2013 (HR 0.67 for adherent); Chang 2015 (HR 1.11) |
| Heavy outdoor work | OR ≈ 1.2–1.5 | Assumed | Flouris 2018 (prevalence only) |

## Future roadmap (Phase 2)

- **Status tracking:** tested, diagnosed, referred for dialysis, with dates and reminders. Monitoring follows the KDIGO 2024 grid (1 to 4+ times a year by stage), to be verified against the KDIGO figure (p. S197) before use.
- **Check-ins:** BP and blood sugar for people with home devices; weight quarterly.
- **Health app integration:** read data from phone wellness apps instead of asking.
- **Education for diagnosed patients:** what to do with CKD, and why to continue dialysis.
- **Partner booking:** book a test at a partner facility that shares equipment and staff availability.
- **Real SMS channel:** confirm the short code and billing with Globe or Smart.
- **Messenger bot** using the same flow. Load incentive on completion if budget allows (about +6–10 points of completion in studies).
- **Real explanations:** compute each person's top reasons from the model.
- **Offline sync conflicts** and encryption at rest on field tablets.
- **Data-sharing agreement** with the LGU.
- **Genome research gateway (Engine 4):** confirmed CKD patients may opt in to genetic studies through a partner such as the Philippine Genome Center, with ethics approval and consent.

## Risks and what we must not claim

| Risk | Why it matters | What to say instead |
| --- | --- | --- |
| Retraining tonight | Every number changes less than 24 hours before submission | Use the 3:00 AM fallback; never mix old and new numbers |
| Proposal promised test allocation | The submitted concept describes allocating limited confirmatory tests | The risk level is the first step of allocation; the full planner is future work |
| Heat | CKDu evidence is mixed and heat has no measured effect size | "Heat matters for people doing heavy outdoor work; it is in the advisory and the outdoor-work item, not in the area-wide score" |
| Validating on our own simulation | Numbers can look circular | Show results next to the Thai benchmark score and the prevalence sensitivity check |
| Prevalence | No Philippine population study exists | "Derived from a Vietnamese study with the same definition; results shown at 8–18%" |
| High read as "probably sick" | In simulation most High results are not abnormal | "A higher chance, not a diagnosis" |
| Mocked explanations | Judges may ask how reasons are computed | Label as illustrative; Phase 2 computes them |
| Real facility names | Could look like a partnership | "Not verified, call ahead"; no logos |
| "The SMS is free" | Billing not confirmed with Globe/Smart | Don't claim it |
| "Analyst figures show real Laguna risk" | Demo data is simulated, and only people who checked are counted | "Simulated data, among people checked" |
| "Runs on a Raspberry Pi" | Not tested | "Lightweight enough to run offline on a laptop or tablet" |
| Risk level read as a diagnosis | Can cause false comfort or panic | The not-a-diagnosis line on every result, plus the worried-reader note |

## Open questions

- [ ] Who owns each task tonight: citizen flow, SMS flow, field tablet, analyst view, retraining, facility list?
- [ ] Which real facilities to list, and who checks their names and municipalities?
- [ ] Is the app a web app? If not, the field tool falls back to KoBoToolbox ([ADR 0003](ADR/0003-one-offline-web-app-for-all-channels.md)).
- [ ] Can the simulator generate urine ACR, which the outcome now needs?
- [ ] Get the Thai score's item points from Thakkinstian 2011 (BMC Nephrol 12:45).
- [ ] **Floor with "I don't know":** this PRD applies the guideline floor only to an explicit Yes or a "High" BP reading. "I don't know" enters the model as Yes and triggers the BP/sugar prompt, but does not trigger the floor. Confirm.
- [ ] **Kidney status is asked last** (for SMS partial answers). In the app, someone already diagnosed answers 12 questions before being routed to care. Consider moving it first in the app only.
- [ ] Can app users opt in to SMS reminders (giving a phone number), or do they only get the next date?
- [ ] Still to verify: PSH/PHA hypertension guidelines, ESH 2023, ADA recommendation grades, Clark 2018 (JAMA, CKD WIT water trial), Hill 2016 global prevalence, and whether the NTC SMS circulars are current.

## References

Checked by literature search on Oct 23, 2026, except where noted.

- Bang H, et al. SCORED. *Arch Intern Med* 2007;167(4):374–381. PMID 17325299.
- Kshirsagar AV, et al. *Arch Intern Med* 2008;168(22):2466–2473. PMID 19064831.
- Thakkinstian A, et al. Thai simplified CKD risk score. *BMC Nephrol* 2011;12:45. PMID 21943205.
- Satjamuk W, et al. SCORED in Thailand. *Isan J Pharm Sci* 2012;8(3).
- Tran HTB, et al. CKD in Long An, Vietnam. *BMC Res Notes* 2017;10:523. PMID 29084580.
- Hippisley-Cox J, Coupland C. QKidney. *BMC Fam Pract* 2010;11:49.
- Hsu CY, et al. BMI and ESRD. *Ann Intern Med* 2006;144(1):21–28. PMID 16389251.
- Garofalo C, et al. Obesity and CKD meta-analysis. *Kidney Int* 2017;91(5):1224–1235. PMID 28187985.
- WHO Expert Consultation. BMI in Asian populations. *Lancet* 2004;363:157–163. PMID 14726171.
- Freedman BI, Soucie JM, McClellan WM. Family history of ESRD. *J Am Soc Nephrol* 1997;8(12):1942–1945. PMID 9402097.
- Roy L, et al. Antihypertensive adherence and ESRD. *Kidney Int* 2013;84(3):570–577. PMID 23698228.
- Chang PY, et al. Oral antidiabetic adherence and ESRD. *Medicine* 2015;94(47):e2051. PMID 26632708.
- Molenaar EA, et al. Validity of self-reported diabetes and hypertension. *Eur J Public Health* 2007;17(2):199–205. PMID 16887835.
- Abalos JB, et al. Hypertension awareness among older Filipinos. *J Gerontol A* 2024;79(2):glad155. PMID 37379565.
- Du S, et al. Ultra-processed food and incident CKD. *Am J Kidney Dis* 2022;80(5):589–598. PMID 35679994.
- Johnson RJ, Wesseling C, Newman LS. CKD of unknown cause. *N Engl J Med* 2019;380:1843–1852. PMID 31067373.
- Flouris AD, et al. Occupational heat strain. *Lancet Planet Health* 2018;2(12):e521–e531.
- Inker LA, et al. CKD-EPI 2021. *N Engl J Med* 2021;385:1737–1749. PMID 34554658.
- KDIGO 2024 CKD guideline. *Kidney Int* 2024;105(4S):S117–S314. PMID 38490803.
- Paz-Pacheco E, et al. 2026 Philippine Periodic Health Examination guideline. *Acta Med Philipp* 2026;60(10):196–209. doi:10.47895/amp.v60i10.11674.
- USPSTF. Hypertension in adults: screening. 2021, Grade A.
- USPSTF. Prediabetes and type 2 diabetes: screening. 2021, Grade B.
- American Diabetes Association. Standards of Care in Diabetes 2026, Sections 2 and 11 (grades not verified).
- Gurol-Urganci I, et al. Mobile phone messaging reminders for appointments. Cochrane CD007458, 2013.
- Gibson DG, et al. Airtime incentives in mobile phone surveys. *BMJ Glob Health* 2019;4:e001604.
