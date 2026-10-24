# Channel consistency: PRD v3 cross-reference

24 Oct 2026 · checks that the citizen app, the field tablet and the analyst view follow [PRD v3](AGAP-CKD-PRD-v3.md), the [screen content plan](AGAP-CKD-Screen-Content-Plan.md) and [ADR 0003](ADR/0003-one-offline-web-app-for-all-channels.md). Each row cites the requirement, where it is built and the test that holds it. SMS is not built yet; when it is, it calls the same endpoint.

## The rule

> "Every channel (app, SMS, field tablet) uses the same questions, the same model and the same guideline floor, so a risk level means the same thing however it was collected." (PRD v3, line 34; ADR 0003)

| Part | One implementation | Used by |
|---|---|---|
| Questions, order, branching | `frontend/src/riskCheck/content.ts`: `QUESTIONS` (l. 49), `questionsFor` (l. 165), `pruneBranches` (l. 173) | Citizen app, field tablet |
| Model, cut-offs, floor | `src/agap/risk_check_service.py`: `score_frame` (l. 57) | `/api/risk-check/evaluate` (`api/main.py` l. 210), analyst simulated checks (`src/agap/analyst.py` l. 75) |
| Endpoint | `POST /api/risk-check/evaluate`; `/api/citizen/evaluate` is the same function (`api/main.py` l. 229) | Citizen app (`CitizenView.tsx` l. 101, payload built by `citizenForm.ts` `evaluationPayload`, l. 81), field tablet (`FieldWorkerView.tsx` l. 183) |
| Counting | Scored app checks are logged when scored (`api/main.py` l. 222); field checks when the tablet syncs; both are added to the analyst map (`analyst.py` `overview_with_recorded`, l. 124) | Analyst view |

**Removed:** the citizen endpoint's old 6-question model with fixed cut-offs 0.06 / 0.15 and its silent 5% fallback. No channel can reach it.

## Inconsistencies found and fixed

| Found (audit, 24 Oct) | Requirement | Fix | Test |
|---|---|---|---|
| Citizen app scored with the old 6-question model and cut-offs 0.06 / 0.15; tablet and map used the frozen model with 0.0711 / 0.1208 | PRD l. 34, l. 78–84 (model, cut-offs "saved with the run", floor) | Citizen app posts to `/api/risk-check/evaluate`; old model path deleted | `test_citizen_path_is_the_shared_risk_check` (`tests/test_api.py` l. 104); `test_app_and_analyst_score_identically` (`tests/test_risk_check_service.py` l. 48) |
| Citizen app asked exact age, and lacked heart disease/stroke, kidney stones, medicine and kidney status | PRD questionnaire items 1, 6, 8, 9, 13 (l. 53, 58, 60, 61, 65); fixed order on every channel (l. 48) | Citizen check-in (refreshed design, PR #48) asks every PRD item in PRD order, one per screen, with the PRD branching (`citizenForm.ts` `stepsFor`, l. 50); exact age is sent as the PRD age group, and under 18 goes to the see-a-doctor route | `frontend/src/__tests__/citizenForm.test.ts` (order, branching, payload) |
| Citizen app had no consent screen | PRD citizen flow step 3 (l. 40); content plan C3 (l. 45) | C1 onboarding → C2 invitation → C3 consent (Agree / Not now → C8) | Walk-through: declined consent shows C8 |
| Citizen form started pre-filled as a high-risk person (age 52, diabetes, high BP, family history = yes) | Fixed order, one item per screen, answer advances (PRD l. 42; content plan l. 69–77) | Form starts empty (`emptyCitizenForm`) | `citizenForm.test.ts` "starts without assumed answers" |
| Field checks did not reach the analyst map | Analyst map counts checks from the channels (PRD l. 175, 192) | Synced field checks and scored app checks are added to the simulated checks when the map is served; the page shows "incl. N recorded (app/field)" | `test_recorded_checks_reach_the_analyst_map` (l. 128); `test_app_checks_are_recorded_without_identities_and_field_checks_wait_for_sync` (l. 113) |

## Rules every channel now shares

| Requirement | Source | Where | Test |
|---|---|---|---|
| "I don't know" to diabetes or high BP enters the model as Yes and never triggers the floor | PRD l. 77; PRD open question (floor with "I don't know") | `triage.encode_features`, `triage.guideline_floor` | `test_dont_know_raises_the_model_but_never_triggers_the_floor` (l. 67) |
| Guideline floor after the model | PRD l. 82–84; ADR 0002 | `score_frame` | `test_risk_check_guideline_floor_applied` (`test_api.py` l. 72) |
| Score never shown to citizens | PRD l. 73 | `/api/risk-check/evaluate` returns no probability | `test_results_carry_no_probability_and_routes_skip_the_level` (l. 127) |
| Safety pre-check "Yes" → see a doctor, no level; "Told something was wrong" → go to care, no level | PRD l. 41, item 13 (l. 65); content plan C4a, C9 (l. 137) | `risk_check_service.evaluate` (l. 251, 253) | `test_risk_check_safety_and_diagnosed_routes_get_no_level` (`test_api.py` l. 79) |
| Next step and date by state | PRD next steps table; "Next date shown everywhere" (l. 115) | `risk_check_service.next_step` (l. 129) | `test_next_step_follows_the_prd_interval_table` (l. 95), 9 cases |
| "This is not a diagnosis…" on every result | PRD l. 95 | Citizen C6, field F3 | Walk-through |
| No names or ID numbers | PRD l. 164, 197 | Check log entries hold channel, time, town, level and answers only | `test_app_checks_are_recorded_…` asserts the exact fields |

## Re-check (24 Oct, 6:05 PM)

- **Same answers, three paths:** `/api/risk-check/evaluate` (app), `/api/citizen/evaluate` and `/api/risk-check/evaluate` (field) gave identical levels and next steps for a diabetes Yes (High, kidney test), an all-"I don't know" (High, kidney test) and a young person with no risk factors (Low, re-check).
- **Citizen walk-through** (headless browser, no console errors):
  - young, no risk factors → Low, "Next check: Okt 2029";
  - diabetes Yes, stopped medicine → High, kidney test soon;
  - "I don't know" answers → High, with the blood-sugar prompt;
  - symptoms → see a doctor, no level;
  - already diagnosed → facilities, no level;
  - declined consent → education cards.
- **Field walk-through:** full check → referral note, safety "Oo" → see a doctor, declined → education cards, Today list and Sync.
- **Analyst map:** the province total went from 4,300 to 4,306 after recorded checks were added, and back after the demo logs were cleared.

## Refreshed citizen design (PR #48)

The refreshed citizen screens (dashboard, Learn, Care, Track) were connected to the shared risk check:

| Design choice | PRD rule | Resolution |
|---|---|---|
| Dashboard showed a "Demo model score /100" | The score is never shown to citizens (PRD l. 73) | The dashboard shows the level and "Antas: …"; the API never returns the probability. Test: `citizenEntry.test.tsx` "no numeric score" |
| Result showed a fixed "Nob 2026 – Ene 2027" testing window | Next date by state (PRD l. 115) | Next step and date come from `next_step` |
| Facility rows said "Libreng blood/urine check" | No unverified claims; facilities "Not yet verified, call ahead" (PRD facility list) | PhilHealth YAKAP list, "Kidney tests: hindi pa alam · tumawag muna" |
| Intersex / Prefer not to say | The model needs Female or Male | No level ("Hindi available"), as designed; team decision pending |

## Still open

- **SMS (S1–S7)** is not built; it must call `/api/risk-check/evaluate` with `channel: "sms"`.
- **Recorded checks and the simulated base:** the map is still mostly simulated, so recorded checks change it only slightly. The banner keeps "Simulated data".
- **Clearing demo checks before the freeze:** recorded checks live in `data/reports/field_sync_log.jsonl` and `data/reports/risk_check_log.jsonl` (git-ignored).
- **Taglish copy** needs native-speaker review (PRD l. 69).
