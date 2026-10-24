# PRD v3 → current frontend: requirements coverage

**Reviewed:** 24 October 2026
**Code:** local `initial-frontend-setup` at `66813c7`
**Baseline:** [PRD v3](../../AGAP-CKD-PRD-v3.md), [screen content plan](../../AGAP-CKD-Screen-Content-Plan.md), and [ADRs](../../ADR/).
**Surfaces checked:** React frontend in `frontend/src/`, FastAPI in `api/main.py`, and the running app at `http://localhost:5173` with its API at port 8000.

This is a **requirements and behavior audit**, not a visual-quality, accessibility, or responsive-design audit. “Present” means the requirement is implemented and connected enough to perform its stated job. “Partial” means a screen or some logic exists, but an essential rule or connection is missing. “Demo only” means the interface displays fixed or synthetic values without the stated computation or workflow. “Absent” means no implementation was found in the reviewed branch. These are source and limited browser observations, not a clinical validation. The older Streamlit app and other unmerged branches are outside this matrix.

## Executive findings

The React shell, four navigation tabs, Laguna map, citizen result panel, field-worker screens, coordinator worklist, and analyst panels all render. The API responds and the production frontend builds. The current experience nevertheless covers only part of the PRD's three-channel product. The PRD calls for one consistent check across citizen, field tablet, and SMS; the field tablet has a manually chosen level, SMS has no flow, and the citizen app omits several questionnaire items. The analyst interface is substantial as a demonstration but its headline indicators and model-quality numbers come from hard-coded API fixtures, not the active run.

The largest release risks are (1) collecting health answers before citizen consent, (2) an incomplete citizen form feeding a model with fixed thresholds instead of PRD v3 cut-offs, (3) a field flow that can report any manually selected level and lose pending checks on reload, and (4) analyst metrics presented with a “Live Backend” indicator even though the API supplies fixed demonstration numbers. These are differences between the PRD and this branch; the report does not endorse clinical use of either.

## Browser evidence

Playwright visited the live local app with the FastAPI backend running. The following screenshots record the current content and available routes. They are evidence of rendered states, not a UI critique.

| State | Capture |
|---|---|
| Citizen start | [citizen-start.png](screenshots/citizen-start.png) |
| Citizen High result after the available questions | [citizen-result.png](screenshots/citizen-result.png) |
| Citizen safety route | [citizen-doctor-referral.png](screenshots/citizen-doctor-referral.png) |
| Field-worker Today | [field-today.png](screenshots/field-today.png) |
| Field-worker “form” with manual level selection | [field-manual-level.png](screenshots/field-manual-level.png) |
| Coordinator worklist | [coordinator-worklist.png](screenshots/coordinator-worklist.png) |
| Analyst province map | [analyst-map.png](screenshots/analyst-map.png) |
| Analyst climate | [analyst-climate.png](screenshots/analyst-climate.png) |
| Analyst model quality | [analyst-model.png](screenshots/analyst-model.png) |

The browser showed a real active run ID in the shared footer and 500 coordinator cases. This does not make the analyst's displayed measures run-derived: [`api/main.py`](../../../api/main.py#L477) defines those measures separately as constants and formulas.

## Citizen channel

| PRD / screen requirement | Status | Evidence and gap |
|---|---|---|
| C1: three education cards with Next / Skip | **Absent** | [`CitizenView.tsx`](../../../frontend/src/views/CitizenView.tsx#L132) has a single introductory screen; the three card sequence is not present. |
| C2: separate invitation with Start / Not now | **Partial** | Intro has “Simulan ang Check” [`L158`](../../../frontend/src/views/CitizenView.tsx#L158), but no Not now route. |
| C3: explicit consent before health questions, retention statement, decline → education | **Absent** | Start goes directly to the safety question [`L158`](../../../frontend/src/views/CitizenView.tsx#L158); no consent decision or retention notice. |
| C4: under-18 / pregnancy / acute-symptom pre-check | **Partial** | A combined yes/no screen routes yes to `Doctor Referral` [`L172`](../../../frontend/src/views/CitizenView.tsx#L172); “very little urine” and “I don't know” are missing, and pregnancy is not collected separately. |
| C4a: doctor route without a risk level | **Partial** | API bypasses probability scoring [`api/main.py:L208`](../../../api/main.py#L208), but the shared result panel still shows a `Doctor Referral` level badge, reasons, and a fixed testing period [`CitizenView.tsx:L611`](../../../frontend/src/views/CitizenView.tsx#L611). See browser capture. |
| C5: one question per screen with progress | **Partial** | Question steps and progress exist [`L228`](../../../frontend/src/views/CitizenView.tsx#L228), but progress is fixed at seven and does not follow PRD question order or branching. |
| Age, sex, municipality | **Partial** | Age and sex share a screen; only **six** towns are rendered from a 16-town list [`L38`](../../../frontend/src/views/CitizenView.tsx#L38), [`L259`](../../../frontend/src/views/CitizenView.tsx#L259), versus 30 required. |
| Diabetes, high BP, BP reading, family history, outdoor work | **Present as questions** | Screens exist [`L320`](../../../frontend/src/views/CitizenView.tsx#L320) onward; BP reading is asked even after high BP = Yes, contrary to the PRD branch. |
| Medicine-taking, heart disease/stroke, kidney stones, kidney status | **Absent** | None appear in the frontend form type [`L4`](../../../frontend/src/views/CitizenView.tsx#L4) or API request schema [`api/main.py:L115`](../../../api/main.py#L115). No already-diagnosed route. |
| Height and weight with units / unknown | **Absent as questions** | Values are preset in component state [`L61`](../../../frontend/src/views/CitizenView.tsx#L61); the user never enters or confirms them. |
| C6: level, explanation, not-a-diagnosis line, next step | **Partial** | API returns these and the result displays them [`L611`](../../../frontend/src/views/CitizenView.tsx#L611). Reasons are labeled illustrative. The response also contains `tips`, but the frontend does not render them. |
| C6: state-specific next date and re-check rules | **Absent** | Result displays “Nob 2026 – Ene 2027” for every level, including doctor referral [`L645`](../../../frontend/src/views/CitizenView.tsx#L645). API Low uses next calendar year; Medium/High use broad prose [`api/main.py:L301`](../../../api/main.py#L301). |
| C6: heat advisory, worried-reader note, answer-sooner line | **Absent** | No such result sections; an outdoor-work hydration tip exists in API but is not rendered [`api/main.py:L295`](../../../api/main.py#L295). |
| C7: facility list and municipality switcher | **Partial** | Toggle reveals up to three API facilities [`L669`](../../../frontend/src/views/CitizenView.tsx#L669). It labels each as an RHU and “free blood/urine check” rather than showing real name/type, test capability Unknown, and “Not yet verified, call ahead.” No standalone C7 or town switcher. |
| C8 education-only route, C9 already-diagnosed route | **Absent** | No consent-decline path or kidney-status input in the component. |
| App answer prefill and “Still correct?” | **Absent** | State resets to default demo answers on remount [`L61`](../../../frontend/src/views/CitizenView.tsx#L61); no local persistence. |
| Partner booking “coming soon” | **Absent** | No disabled booking item on result. This is explicitly a Phase 2 capability, although the screen plan calls for its placeholder. |

## Shared scoring and next-step rules

| PRD rule | Status | Evidence and gap |
|---|---|---|
| “I don't know” for diabetes / high BP enters model as Yes | **Present** | API maps both to true for model input [`api/main.py:L224`](../../../api/main.py#L224). |
| Guideline floor after model | **Present in API** | Explicit diabetes/high BP and age rules are coded [`api/main.py:L257`](../../../api/main.py#L257). |
| PRD v3 logistic model using all defined questionnaire features | **Absent on this branch** | API uses six input fields and loads `model_clinical.joblib` [`api/main.py:L80`](../../../api/main.py#L80), [`L230`](../../../api/main.py#L230). PRD v3 retraining is on a separate remote branch; the frontend cannot collect the full input set. |
| Explicit handling when the model artifact is unavailable | **Absent** | API begins at probability `0.05` and only sets `model_degraded` after a prediction exception [`api/main.py:L239`](../../../api/main.py#L239). If no model was loaded, a result is still returned without a degraded flag. |
| Validation-selected cut-offs saved with run | **Absent** | API uses literal `0.06` / `0.15` [`api/main.py:L249`](../../../api/main.py#L249); it does not read a run cut-off artifact. |
| No kidney test recommendation to a healthy Low-risk user | **Partial** | API Low offers yearly “check” [`api/main.py:L305`](../../../api/main.py#L305), but the same UI adds a fixed “testing” period and facility action [`CitizenView.tsx:L645`](../../../frontend/src/views/CitizenView.tsx#L645). |
| Medium without diabetes/high BP → BP and sugar check first | **Absent** | API's single Medium next step recommends blood and urine kidney screening regardless of that distinction [`api/main.py:L303`](../../../api/main.py#L303). |
| 12-month vs 3-year re-check, day-30 and annual reminders, blood-sugar prompt | **Absent** | No state-specific scheduling or reminder implementation in the citizen API/UI. |
| Heavy outdoor work but no municipal heat in personal score | **Partial** | API's six-feature input includes outdoor work and no municipal heat [`api/main.py:L230`](../../../api/main.py#L230), but the PRD's separate advisory is not displayed. |

## Field-worker channel and SMS

| PRD / screen requirement | Status | Evidence and gap |
|---|---|---|
| F1 Today list, sync count, action | **Partial / demo** | UI shows checks, counts and sync control [`FieldWorkerView.tsx:L95`](../../../frontend/src/views/FieldWorkerView.tsx#L95). API Today returns fixed sample records and counts [`api/main.py:L353`](../../../api/main.py#L353); UI also hard-codes “12” re-checks due [`FieldWorkerView.tsx:L213`](../../../frontend/src/views/FieldWorkerView.tsx#L213). |
| F2 read-aloud consent | **Partial** | Tagalog script and Agree / Decline buttons exist [`L246`](../../../frontend/src/views/FieldWorkerView.tsx#L246). English is decorative text, there is no recorded checkbox, and Decline returns to Today instead of education. |
| F2b same safety pre-check, questionnaire, model and floor as citizen | **Absent** | The field “form” has barangay and manually selected Low/Medium/High only [`L306`](../../../frontend/src/views/FieldWorkerView.tsx#L306). It sends no answers for scoring. |
| F3 referral note for Medium/High with reason, verified facility status and next date; Low gets re-check date | **Partial / demo** | Note screen exists [`L371`](../../../frontend/src/views/FieldWorkerView.tsx#L371) but uses the manually chosen level, fixed Calamba RHU, and no reason or next date. It is shown for Low too. |
| Durable offline checks and later sync | **Partial** | New checks live in React state [`L15`](../../../frontend/src/views/FieldWorkerView.tsx#L15), so reload loses pending data. API appends a journal on sync [`api/main.py:L322`](../../../api/main.py#L322), but a write error still returns success; frontend also marks all pending checks synced without checking HTTP success [`FieldWorkerView.tsx:L61`](../../../frontend/src/views/FieldWorkerView.tsx#L61). |
| Optional family-number reminder consent | **Absent** | No input or consent workflow. |
| SMS: CHECK → consent → questions → result → reminder opt-in | **Absent** | No SMS handler, messaging route, or channel UI in this branch; the analyst's SMS share is a fixture [`api/main.py:L540`](../../../api/main.py#L540). |
| SMS: STOP / HELP / BACK / TULOY, GSM-7, retention, deletion | **Absent** | No matching implementation in `frontend/src/` or `api/`. |
| One scoring path for citizen / field / SMS (ADR 0003) | **Absent** | Citizen calls `/api/citizen/evaluate`; field selects a level manually; SMS has no flow. [`ADR 0003`](../../ADR/0003-one-offline-web-app-for-all-channels.md). |

## Analyst and operational views

| PRD / screen requirement | Status | Evidence and gap |
|---|---|---|
| A1 Laguna municipality map and selectable towns | **Present as demo** | All 30 shapes render, selection updates details [`LagunaMap.tsx:L67`](../../../frontend/src/components/LagunaMap.tsx#L67). Values are fixed in frontend fallback and API fixtures. |
| A1 under-10 suppression and 10–49 fading | **Partial** | Map coloring and opacity reflect both thresholds [`LagunaMap.tsx:L132`](../../../frontend/src/components/LagunaMap.tsx#L132); the side panel can still show a selected area's numbers. |
| A1 metric switch: share / coverage / awareness | **Partial** | Controls exist [`AnalystView.tsx:L250`](../../../frontend/src/views/AnalystView.tsx#L250), but map coverage color is derived from check count (`n / 1000`) and awareness color from Medium/High share, not the selected metric [`LagunaMap.tsx:L134`](../../../frontend/src/components/LagunaMap.tsx#L134). Tooltip remains share. |
| A1 age-standardised share and confidence range | **Demo only** | API supplies fixed shares and `share ± 4` as the range; no age-standardisation calculation [`api/main.py:L519`](../../../api/main.py#L519). |
| A2 checks, coverage, awareness, channel split, factors, DONE replies | **Demo only** | Panel and labels render [`AnalystView.tsx:L327`](../../../frontend/src/views/AnalystView.tsx#L327); API derives these from constants, not observed check data [`api/main.py:L519`](../../../api/main.py#L519). Sync timestamp is also fixed [`AnalystView.tsx:L431`](../../../frontend/src/views/AnalystView.tsx#L431). |
| A2 top reasons hidden below 30 checks | **Absent** | Factors render for every selected town [`AnalystView.tsx:L437`](../../../frontend/src/views/AnalystView.tsx#L437). |
| A3 separate climate context panel and caution label | **Partial** | Separate tab and caution copy exist [`AnalystView.tsx:L530`](../../../frontend/src/views/AnalystView.tsx#L530); API's 12-month series is fixed, and 30-day values are randomly generated rather than read from the loaded weather data [`api/main.py:L576`](../../../api/main.py#L576). |
| A4 model vs Thai benchmark, cut-offs, sensitivity, run ID | **Demo only** | Panel exists [`AnalystView.tsx:L590`](../../../frontend/src/views/AnalystView.tsx#L590); numbers and run ID are hard-coded in API [`api/main.py:L558`](../../../api/main.py#L558), separate from the actual footer run ID. |
| “Simulated data · Among people checked” banner | **Present** | Analyst banner is rendered [`AnalystView.tsx:L180`](../../../frontend/src/views/AnalystView.tsx#L180). |
| Coordinator worklist, queues, case events | **Present outside PRD v3 three-view IA** | React tab and API-backed worklist render; event endpoint records to SQLite when an active round exists [`CoordinatorView.tsx:L18`](../../../frontend/src/views/CoordinatorView.tsx#L18), [`api/main.py:L445`](../../../api/main.py#L445). Treat this as a parallel operations feature, not evidence that the PRD's field or analyst jobs are complete. |

## Privacy, facility, and claim integrity

| Requirement | Status | Evidence and gap |
|---|---|---|
| Consent before questions on every channel | **Absent overall** | Citizen has no consent; field has a consent-script screen; SMS is absent. |
| No names or ID numbers collected for PRD check | **Partial** | Citizen questionnaire collects no name. Field view creates `resident_alias` strings and shows check IDs; coordinator uses synthetic resident IDs by design. The PRD's privacy model needs clarification across operations. |
| Small-area suppression | **Partial** | Map hides share under 10 checks, but side panel and analyst details do not consistently suppress values. |
| Real facilities with test capability Unknown and call-ahead label | **Absent as specified** | API reads run facilities and returns first municipality matches [`api/main.py:L174`](../../../api/main.py#L174); citizen view invents an “RHU” label and claims free tests [`CitizenView.tsx:L673`](../../../frontend/src/views/CitizenView.tsx#L673). Test capability is not verified. |
| App / field / SMS share one answer and model contract | **Absent** | Inputs and scoring paths differ; see channel findings. |

## Prioritized completion work

1. **P0 — Consent and routing:** add citizen consent/decline and the specified C4a/C8/C9 branches before collecting questionnaire data. Make doctor referral an independent path with no risk-level result or generic testing date.
2. **P0 — Shared risk check:** complete the PRD question set, branching, age/weight inputs, 30 municipalities, and one scoring contract for citizen and field. Integrate the PRD v3 model and saved cut-offs only after compatibility checks and the repository's model verification protocol. Return a clear unavailable state if the model cannot be loaded.
3. **P0 — Honest next steps and facilities:** distinguish re-check from kidney test, compute dates from actual state, stop recommending a kidney test to low-risk users without a risk factor, and label facility verification and capability accurately.
4. **P1 — Offline and sync integrity:** persist unsynced checks locally; treat API failures as failures; provide reliable sync receipts. Remove “saved to local database” until storage exists.
5. **P1 — Analyst data contract:** either derive metrics, climate, and model quality from the active run or mark the panels explicitly as fixed illustrative examples, including the map metric switch and run ID.
6. **P1 — SMS channel:** implement or explicitly mark it unbuilt. The current analyst SMS percentages cannot be treated as activity.

## Verification performed and limits

- `npm --prefix frontend run build` passed (`tsc && vite build`).
- Playwright opened each of the four channels, captured nine states, and walked the citizen safety and High-result paths plus the field form. The live API returned `status: ready`, 30 analyst municipalities, and the current run ID.
- This review did not run the full Python suite, mutate coordinator events, deliver SMS, validate clinical evidence, or assess visual/UI quality. The browser captures use the local sample run and show only sampled states.
- The Impeccable launcher returned `permission denied`, so its context loader and bundled detector did not run. Its audit playbook was read, but the user's scope limits this report to requirements coverage rather than the playbook's UI score.
