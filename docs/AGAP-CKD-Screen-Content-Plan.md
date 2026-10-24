# AGAP-CKD Screen Content Plan

Oct 23, 2026 · companion to [AGAP-CKD-PRD-v3.md](AGAP-CKD-PRD-v3.md)

This plan lists what each screen shows and in what order of importance. Terms in **bold** are defined in [GLOSSARY.md](GLOSSARY.md).

**How to read each screen**

- **P1** is the one thing the user must see first: the largest element, at the top.
- **P2** is supporting information, visible without scrolling.
- **P3** is detail: below the fold, collapsed, or smaller.
- **Actions** are listed primary first.
- **Rules** are behaviours or wording that must not change.

**Copy rules for every screen**

- Never say "screening", "test" (for the risk check), "positive", "you have CKD" or "likely CKD".
- Every result says: "This is not a diagnosis. Only a blood and urine test can check your kidneys."
- Tagalog/Taglish copy is checked by a native speaker before the demo.

---

## 1. Citizen app

Flow: C1 Onboarding → C2 Invitation → C3 Consent → C4 Safety pre-check → C5 Questions → C6 Result → C7 Facilities.
Off-path screens: C4a See a doctor; C8 Education only (consent declined); C9 Already diagnosed.

### C1 Onboarding (3 cards)

- **P1:** one sentence per card, with a simple illustration.
  1. "Your kidneys clean your blood every day."
  2. "Early kidney problems have no symptoms."
  3. "Only a simple blood and urine test can check your kidneys."
- **P2:** card position dots (1 of 3).
- **Actions:** Next · Skip.
- **Rules:** no medical terms on these cards. "CKD" first appears with its meaning: "chronic kidney disease (CKD)".

### C2 Invitation

- **P1:** "Would you like to know if you may be at risk for kidney problems?"
- **P2:** "About 2 minutes · 12 short questions · Free".
- **Actions:** Start · Not now.
- **Rules:** never call it screening or a test.

### C3 Consent

- **P1:** "Before we start", with three short lines:
  - what we ask (health history, height and weight, town);
  - who sees it (only totals for your town, never your name);
  - how long it is kept.
- **P2:** "We do not ask your name. You can stop anytime."
- **P3:** link to the full privacy notice (RA 10173).
- **Actions:** I agree · Not now → C8.

### C4 Safety pre-check

- **P1:** "First, a quick safety question." Then: "Are you under 18, pregnant, or do you have any of these: swelling of the legs or face, foamy or bloody urine, or passing very little urine?"
- **P2:** short icons for each symptom.
- **Actions:** Yes → C4a · No → C5 · I don't know → C5. On C5, the app shows a gentle line: "If you notice these, see a doctor."

### C4a See a doctor

- **P1:** "Please see a doctor soon."
- **P2:** "These signs need a check by a doctor, not this questionnaire." Then the nearest facility from their municipality: name, town, "Not yet verified, call ahead".
- **P3:** "What these signs can mean" (2 lines).
- **Actions:** See facilities → C7 · Back to home.
- **Rules:** no risk level is shown.

### C5 Questions (one per screen)

- **P1:** the question, in large type.
- **P2:** answer buttons, full width; "I don't know" is always the last button.
- **P3:** a progress bar ("5 of 12") and a "Why we ask" link (one line, e.g. "Diabetes is the leading cause of kidney disease").
- **Actions:** answer advances automatically · Back.
- **Order and branching:** follows the PRD v3 questionnaire table.
  - Medication: only if diabetes or high BP = Yes.
  - BP reading: only if high BP = No or I don't know.
  - Total progress is recalculated after those answers.
- **Variants:**
  - Height and weight is a number screen with a cm/ft and kg/lb toggle and an "I don't know" button.
  - On a re-check, unchanging answers are pre-filled with "Still correct? Yes / Change".

### C6 Result

One scrolling screen. The sections appear in this order, which is the hierarchy.

| Order | Section | Content | Shown when |
| --- | --- | --- | --- |
| 1 (P1) | Risk level | A level badge (Low / Medium / High) in words and colour, and one line: "Your answers show a lower chance…" / "Some of your answers raise…" / "Several of your answers raise…" | Always |
| 2 (P1) | Not-a-diagnosis line | "This is not a diagnosis. Only a blood and urine test can check your kidneys." | Always, directly under the badge |
| 3 (P1) | Next step | One action sentence with the **next check date**, picked by state (table below) | Always |
| 4 (P2) | Why | "Main reasons": 2–3 reasons in plain words, e.g. "You have high blood pressure". Labelled "illustrative" in the demo | Always |
| 5 (P2) | Heat advisory card | "On hot days, drink water regularly and rest in the shade. If your doctor told you to limit fluids, follow your doctor." | The municipality had recent hot days, or heavy outdoor work = Yes |
| 6 (P2) | What you can do now | 2–4 tips picked from the answers (tip rules below) | Always |
| 7 (P2) | If you feel worried | "This is a chance, not a diagnosis. Early kidney problems can be managed. Getting tested is the next step." | Medium and High |
| 8 (P2) | Where to get checked | The top 3 facilities in the municipality, each showing "Kidney tests: Unknown, call ahead", and a "See all" link → C7 | Medium and High; Low shows a link only |
| 9 (P3) | Answer again sooner if… | "…you're diagnosed with diabetes or high BP, start or stop medicine, turn 50, 60 or 70, gain or lose a lot of weight, or after pregnancy." | Always |
| 10 (P3) | Partner booking | "Book through a partner facility: coming soon" (disabled) | Medium and High |

**Next-step sentence by state**

| State | Next-step sentence |
| --- | --- |
| Low, aged 40+ or any risk factor | "Next check: ⟨month year + 12 months⟩" |
| Low, aged 18–39, no risk factors | "Next check: ⟨month year + 3 years⟩" |
| Medium without diabetes or high BP | "Get your BP and blood sugar checked at your health center first, then answer again." |
| Medium or High with diabetes or high BP | "Get a simple blood and urine test for your kidneys (soon, for High). Next kidney test: ⟨+12 months⟩ after that." |
| Blood-sugar prompt (age ≥ 40 or BMI ≥ 23, diabetes = No or I don't know) | Added line: "Get your blood sugar checked." |

**Tip rules** (pick at most 4, in this priority order)

1. Medicine stopped or sometimes missed → "Keep taking your BP or sugar medicine every day, even when you feel fine."
2. Diabetes or high BP = I don't know → "Get your BP and blood sugar checked. It's quick and usually free at your health center."
3. Diabetes = Yes → blood sugar and check-up tips.
4. High BP = Yes → BP and low-salt tips.
5. BMI ≥ 23 → weight and activity tip.
6. Heavy outdoor work = Yes → water and shade tip (unless the heat card already shows).
7. Always available → "Don't take pain relievers like ibuprofen often without a doctor's advice." (General kidney-safety advice; source to be confirmed.)

**Actions:** primary depends on level: Low → Done · Medium/High → See where to get checked. Secondary: Share result (text only, no data) · Start over.

### C7 Where to get checked

- **P1:** the facility list for the municipality. Each row shows:
  - name and type (hospital / health center);
  - "Kidney tests: Yes / No / Unknown";
  - "Not yet verified, call ahead".
- **P2:** a municipality switcher.
- **P3:** "What to bring: this result screen, your medicines, your next check date."
- **Rules:** no logos, no "partner" wording.

### C8 Education only (consent declined)

- **P1:** the three onboarding cards plus "Who should get a kidney test" (people with diabetes, high BP, or aged 60+).
- **Actions:** "Start the check" (returns to C3).

### C9 Already diagnosed (kidney status = Told something was wrong)

- **P1:** "Please keep seeing your doctor about your kidneys."
- **P2:** facility list.
- **Rules:** no risk level. Phase 2 education for diagnosed patients goes here.

---

## 2. SMS channel

Every message is ≤ 160 GSM-7 characters. The drafts below were length-checked, assuming a facility name of up to 30 characters. ⟨…⟩ are placeholders.

**Wording rules**

- Replies use **1=Oo 2=Hindi 0=Hindi ko alam** throughout.
- Progress uses "n/12", and the total is recalculated after the diabetes and high-BP answers.

| ID | When | Draft text | Hierarchy note |
| --- | --- | --- | --- |
| S1 | Resident texts CHECK | "AGAP Kidney Check: ~12 short questions, 2 min. Hindi ito diagnosis. Private: only area totals are shared. Reply 1=Agree 2=No. STOP anytime." | Consent before any question |
| S2 | After agreeing | "1/12 Under 18, pregnant, or have swelling, foamy or bloody urine, or very little urine? 1=Oo 2=Hindi 0=Hindi ko alam" | Safety pre-check first |
| S2a | S2 = Oo | "Please see a doctor soon. Nearest: ⟨facility⟩, ⟨town⟩. Not yet verified, call ahead. Reply HELP for info." | Ends the check, no level |
| S3 | Each item | "5/12 Has a doctor ever told you that you have diabetes? 1=Oo 2=Hindi 0=Hindi ko alam" | One question per message |
| S3-town | Municipality | "4/12 What town or city do you live in? Ex: Calamba", then the confirmation "⟨town⟩? 1=Oo 2=Mali" | 30 numbered towns don't fit in one SMS, so free text is matched to the closest name and confirmed |
| S3-hw | Height and weight | "11/12 Height and weight? Ex: 160cm 65kg or 5ft3 143lb. 0=Hindi ko alam", then the confirmation "165 cm, 70 kg? 1=Oo 2=Mali" | Echo back to confirm |
| S3-err | Unclear reply | "Sorry, di namin naintindihan. Reply with a number only, e.g. 1. BACK=previous HELP=info" | Re-asked once, then the answer is recorded as I don't know |
| S4-1 | Result | "Result: ⟨HIGH⟩ chance of kidney problems. This is not a diagnosis. Only a blood and urine test can check your kidneys." | Level first, as in the app |
| S4-2 | Result | "Main reason: ⟨diabetes⟩. Next: get a kidney blood and urine test by ⟨Nov 2026⟩." (Low: "Main reason: ⟨age⟩. Next check: ⟨Oct 2027⟩. Answer again sooner if your health changes. Reply HELP for tips.") | Reason, then next step and date |
| S4-3 | Result (Medium/High) | "Where: ⟨facility⟩, ⟨town⟩. Not yet verified, call ahead. Reply 1 for up to 3 reminders, 2 for none." | Facility and reminder opt-in |
| S5 | Day 7 and 30 reminder | "Paalala: kidney blood and urine test at ⟨facility⟩. Reply DONE if tested, STOP to end reminders." | Retention |
| S5-y | Re-check reminder | "Paalala: time for your yearly AGAP kidney check. Text CHECK to start. Reply 1 to get next year's reminder too." | Asks for consent again each year |
| S6 | Resume after a timeout | "You stopped at ⟨6/12⟩. Reply TULOY to continue or CHECK to start over." | — |
| S6-e | New result lower than a Medium/High from the last 30 days | "Your earlier result (⟨HIGH⟩) still stands until you get a kidney test. Reply HELP for where to go." | Stops people re-answering for a better result |
| S7 | HELP | "AGAP Kidney Check. Reply with the number of your answer. BACK=previous question, TULOY=continue, STOP=end. Not a diagnosis." | — |

**Rules**

- Messages are sent only between 7 AM and 9 PM.
- No emoji or curly quotes: either one switches the message to UCS-2 (70 characters).
- "ñ" is in the GSM-7 basic set, but test operator handling on real phones.
- "~" in S1 is a GSM-7 extension character and counts as 2. S1 still fits.

---

## 3. Field health worker (tablet, offline)

Flow: F1 Today → F2 Consent script → (same C4–C5 in a large layout) → F3 Result and referral note → F1. Sync happens from F1.

### F1 Today

- **P1:** "⟨n⟩ checks waiting to sync", with a **Sync** button. It is enabled when online and shows "Offline" when not.
- **P2:**
  - "Today's checks" list: check number, time, barangay, risk level badge.
  - "Re-checks due this month in your areas: ⟨n⟩".
- **P3:** last synced time; worker's barangay coverage list.
- **Actions:** **Start a new check** (primary, large) · Sync.
- **Rules:** no names or ID numbers anywhere.

### F2 Consent script

- **P1:** the consent script, in large text for reading aloud (Tagalog and English toggle).
- **P2:** checkbox "Resident agreed".
- **Actions:** Continue (enabled only when ticked) · Resident declined → show education cards (C8).

### F2b Check (same content as C4–C5)

- Larger buttons and type.
- The worker reads each question aloud.
- "I don't know" is always available.

### F3 Result and referral note

- **P1:** risk level badge and the not-a-diagnosis line, as on C6.
- **P2:** the **referral note** (Medium/High), in large, copy-friendly text:
  > AGAP Kidney Check · ⟨date⟩ · Check #⟨n⟩
  > Result: ⟨High⟩ chance of kidney problems. Not a diagnosis.
  > Main reason: ⟨diabetes⟩
  > Next: simple blood and urine test for your kidneys
  > Where: ⟨facility⟩, ⟨town⟩ (call ahead)
  > Next kidney test: ⟨month year⟩
- **P2 (Low):** "Next check: ⟨month year⟩" in large type, for the resident to note.
- **P3:**
  - tips (as on C6, at most 3);
  - "Optional: family member's number for reminders", with a consent tick for that person.
- **Actions:** Done, back to Today (saves locally) · Read note aloud.

---

## 4. Analyst

Every analyst screen shows a top banner: **"Simulated data · Among people checked, last 12 months"**.

### A1 Province map (default)

- **P1:** a map of Laguna by municipality, coloured by the **age-standardised share of people checked at Medium or High**. Areas display as follows:

| Checks in the area | Display |
| --- | --- |
| < 10 | Hidden (grey: "Too few checks") |
| 10–49 | Faded |
| 50 or more | Full colour |

- **P2:**
  - legend;
  - the number of checks beside each area name;
  - the note: "Includes people who don't know their BP or sugar status".
- **P3:** province totals: checks, **coverage**, **awareness gap**, field vs app split.
- **Actions:** click a municipality → A2 · switch the map metric: Medium/High share (default) / Coverage / Awareness gap.
- **Hover:** share, confidence range, and number of checks.

### A2 Municipality detail (side panel)

| Order | Content |
| --- | --- |
| P1 | Medium/High share (age-standardised) with its confidence range, and the number of checks |
| P1 | **Coverage**: checks ÷ adult population (PSA census) |
| P2 | **Awareness gap**: % "I don't know" to diabetes or high BP, with a link to "Suggest BP/sugar check-up drive" (text only) |
| P2 | Channel split: field health worker vs app vs SMS; "Last synced" for field data |
| P2 | Top modifiable factors over-represented vs the province (stopped medicine, obesity, unknown status, heavy outdoor work). Hidden if < 30 checks. Labelled "illustrative" in the demo |
| P3 | "Got tested" DONE replies, labelled "self-reported, SMS opt-ins only" |

- **Rules:** no cross-tabs by age or sex, and no individual records.

### A3 Climate context (separate tab)

- **P1:** heat and rainfall over time for the selected municipality.
- **P2:** label "Context only: not used in the risk level · community-level estimate".
- **Rules:** never shown as an overlay on the risk map.

### A4 Model quality (collapsed, for judges)

- **P1:** the model vs the **benchmark score** (Thai simplified score) on the same simulated people:
  - share of abnormal screens caught by Medium/High;
  - abnormal rate per level;
  - AUC.
- **P2:**
  - cut-off rules: Medium-or-High catches ≥ 85% of abnormal screens; High has ≥ 2× the overall abnormal rate;
  - the effect of the guideline floor;
  - the prevalence sensitivity table at 8%, 12.8% and 18%.
- **P3:**
  - run ID;
  - the outcome definition: eGFR < 60 or ACR ≥ 30;
  - the prevalence source: derived, Tran 2017;
  - the effect-size tags table.
