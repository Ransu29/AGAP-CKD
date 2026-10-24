# Citizen UX Audit Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task by task. Steps use checkboxes for tracking. Execute one batch at a time; do not start parallel implementation.

**Goal:** Improve the citizen prototype's trustworthiness and usability through small, reviewable changes.

**Architecture:** Preserve the current React citizen view and existing API contract. Keep UI changes local; use clearly labeled fictional states where backend behavior is deferred. Do not restructure the application shell or introduce a new state-management system.

**Tech stack:** React, TypeScript, Tailwind CSS, Vite, existing Lucide icons.

**Spec:** [Decision and state tracker](citizen-ux-tracker.md); [original audit](citizen-ux-audit.md).

**Baseline:** 24 October 2026; branch `initial-frontend-setup`; HEAD `66813c7`. Includes the uncommitted audit/tracker documents. Static inspection only; this plan does not establish fresh browser or build results.

## Global constraints

- Citizen interface only. Backend/model work, town coverage work, and the shared mobile shell remain parked.
- Approved means authorized, not implemented. All 41 findings were **Not started** when this plan was created; current delivery evidence is in the tracker.
- No seeded health answers, invented facility facts, diagnosis claims, or promises of real persistence/offline evaluation.
- No new clinical thresholds or care-routing rules. Do not coerce inclusive/unknown responses into binary clinical inputs.
- Use natural Filipino, English or Taglish according to clarity. Preserve truthful prototype disclosure.
- No dependency installations, pipeline runs, broad refactors, or unrelated role changes.

## Prioritization and budget strategy

Prioritize harm from misleading information, impact on completing the citizen journey, decision readiness, and implementation size. Original P0–P3 severity remains intact: parking a severe issue does not make it safe for release.

Use the remaining budget for **one completed batch at a time**, beginning with B1. Read only that batch's code and tracker rows; preserve a short handoff after each batch. Do not aim to close all 41 findings in this session or spend the budget designing every screen upfront.

| Order | Cluster | Primary findings | Why this order |
|---|---|---|---|
| B1 | Neutral, deliberate answers | C-02, C-09, C-12, C-13 UI, C-14, C-31 | Stops the interface inventing answers or submitting unexpectedly; largely settled direction. |
| B2 | Readable, accessible controls | C-20, C-21, C-29, C-30, C-32, C-33 | Establishes a small reusable visual/accessibility baseline before reshaping screens. |
| B3 | Education-first entry and consent | C-01, C-23, C-25, C-35, C-39 | Delivers the agreed lightweight home without requiring an assessment first. |
| B4 | Clear, honest outcome presentation | C-05, C-07 UI, C-15, C-16, C-17, C-18, C-26, C-36, C-37, C-38 | Removes misleading hierarchy and unsupported claims; exact care language has a decision dependency. |
| B5 | Loading, recovery and return states | C-22 UI, C-24, C-28, C-34 | Makes interruptions understandable without pretending persistence or offline scoring exists. |
| B6 | Honest facility cards | C-04, C-27 | Replaces fabricated service promises with useful, qualified information. |
| D1 | Resolve questionnaire and care-flow design | C-06, C-08, C-10, C-40, C-41 | Approved concerns plus unresolved wording/branching; resolve before implementing new eligibility/care paths. |
| Parked | Backend and shared-shell work | C-03, C-11, C-19; backend portions of C-13/C-22 | Explicitly outside this sprint. Remain visible release limitations. |

Every finding has one primary owner above. Cross-cutting work can benefit later batches without closing their findings prematurely. C-18 owns result CTA and empty-state behavior; B6 supplies the facility details it uses.

## File boundaries

- `frontend/src/views/CitizenView.tsx`: local form state, navigation, citizen screens, feedback and facility presentation. Primary implementation file.
- `frontend/src/index.css`: only if necessary for citizen-scoped tokens/focus/readability; do not change global selectors that restyle other roles.
- `frontend/index.html`: C-30 only if a document-wide language is accurate for the whole app; otherwise apply language metadata inside the citizen view.
- `docs/audits/2026-10-24/citizen-ux-tracker.md`: status and evidence after each delivered batch.
- `frontend/src/App.tsx`, API/domain modules and data/configuration files: no planned changes. Shared-shell constraints may prevent complete mobile-overflow resolution.

## B1 — Neutral, deliberate answers: start here

**Deliverable:** Existing questions begin unanswered, preserve deliberate choices and require an explicit advance/submit action. No new medical questions or branch rules.

- [ ] Read the form type, initialization, choice handlers, age input, `handleNext`, `handleBack` and `handleEvaluate` in `CitizenView.tsx`.
- [ ] Represent unanswered UI values explicitly. Keep any API payload conversion at submission; never send a placeholder/default as the citizen's answer. If the current contract cannot represent an answer, show an unavailable demo outcome rather than substituting a medical fact.
- [ ] Remove false question-count/time promises. Show selection marks only for chosen options; choosing an answer must not immediately evaluate the form.
- [ ] Add the approved Intersex and Prefer not to say choices. Preserve raw age editing with a label and inline errors; blank/zero must not become 18. Do not introduce clinical age rules beyond the current established scope.
- [ ] Keep BP interpretation unchanged; prepare an unanswered/unknown presentation only where the existing contract can handle it honestly. Dynamic thresholds remain deferred.
- [ ] Use an explicit final submit action on the existing last step. Do not add a new review page or extra fields before D1 resolves the flow.
- [ ] Check fresh entry, each choice, back/edit, blank age, unsupported response, and final submission. Confirm no hidden default or final-option auto-submit remains.

**Completion boundary:** C-12 is only partially addressed until its BP/uncertainty details are checked; C-13 backend remains parked. Mark partial delivery in tracker notes rather than closing the entire finding.

## B2 — Readability and accessible controls

**Deliverable:** Citizen controls share readable styling and predictable keyboard behavior.

- [ ] In `CitizenView.tsx`, consolidate only repeated action, choice, status and focus styling needed by this view. Avoid a separate design-system project.
- [ ] Correct action contrast, consequential small text, named Back controls, semantic selection, heading order, and focus/announcement after step changes.
- [ ] Set accurate citizen language metadata; avoid changing other roles' document language inadvertently.
- [ ] Check keyboard-only navigation, focus visibility, text zoom and narrow-width rendering. Record any remaining shared-shell overflow under parked C-19.

## B3 — Education-first home and consent

**Deliverable:** A first-time visitor can learn without completing a questionnaire and can deliberately start a check-in.

- [ ] Replace the citizen landing composition with a concise educational home, an explicitly unassessed state, and a visible check-in CTA. No Low/Medium/High placeholder result.
- [ ] Put consent before health-answer collection; declining returns to educational content. State only confirmed data-handling facts; flag unresolved privacy copy for review.
- [ ] Remove citizen-owned faux status/decorative competition metadata while retaining a clear prototype label. Do not edit the shared role navigation or phone shell.
- [ ] Check first visit, start, decline, back and return-to-home. Confirm education remains available and no result is implied before assessment.

## B4 — Outcome hierarchy and terminology

**Deliverable:** Distinct unassessed, unavailable and fictional scored states with one clear primary action per state.

- [ ] Replace floating “Resulta mo / Medium” pills with a coherent heading and readable icon/text status treatment. Fix the Medium icon contrast without relying on emoji rendering.
- [ ] Put the principal message/action first; progressively disclose reasons and applicable supporting content. Show unavailable explanations honestly.
- [ ] Remove universal hard-coded dates and unsupported recommendations; label fictional variants. Explain blood/urine terminology without presenting eGFR as automatically a separate blood test.
- [ ] Separate clinician-care presentation from scored risk badges. **Dependency:** D1 must resolve C-41 before final care wording/actions; presentation scaffolding may proceed without inventing urgency or a formal referral.
- [ ] Check unassessed, unavailable, each fictional result, absent reasons, empty facilities and clinician-care presentation. Backend correctness C-03 remains open.

## B5 — Interruptions and returning users

**Deliverable:** Understandable pending, failed, offline and return states within the citizen prototype.

- [ ] Prepare visible loading, duplicate-activation prevention, failure/retry and slow/offline presentations using existing UI state. Distinguish demonstrated visuals from connected API recovery.
- [ ] Prepare back/reset/leave confirmations and an explicit “still correct?” review for any available prior answers. Do not promise cross-session storage or add it here.
- [ ] Check that errors retain in-memory answers and do not silently turn into an empty or Low result. Record which behaviors are mock-only.

## B6 — Facilities and service information

**Deliverable:** Facility cards communicate what is known, unknown and actionable.

- [ ] Remove fabricated RHU names and free-test guarantees. Present offered/not offered/not verified when supported; no stock/capacity fields.
- [ ] Show town/address, contact number and Google Maps link only when supplied by a trustworthy source. Render absent details honestly; never derive a fake phone/map destination.
- [ ] Check populated, partially populated, empty and unverified lists. If the current payload lacks fields, use explicitly fictional preview data or withhold them; do not expand the API in this batch.

## D1 — Small design decision packet, not a redesign project

Resolve only the questions that block specific implementation:

1. Map each existing question to its purpose, required/optional status, uncertainty response, applicability and effect on the output. Do not restore old PRD fields automatically (C-10).
2. Distinguish age eligibility, pregnancy, symptoms and known diagnosis. Define proposed screen transitions separately from clinical rules; obtain appropriate content review before asserting medical routing (C-06/08/40).
3. Define what the clinician-care screen actually asks a citizen to do and how it differs from Medium/High guidance. Do not imply a formal referral was issued or universal hospital urgency (C-41).

Record decisions beside the affected tracker rows. Unresolved items do not block B1/B2 or the education-only portion of B3.

## Review focus and batch exit

For every batch, check unanswered versus negative answers, edits/back navigation, unknown/unsupported inputs, narrow-screen/keyboard access, and missing/failed data. Inspect only the affected variants; retain before/after screenshots for visible changes.

- [ ] Review the diff for citizen-only scope and truthful clinical/data wording.
- [ ] Run `npm run build` from `frontend/` when implementing, if installed dependencies are available; do not install packages just to satisfy this plan. Record the actual result or limitation.
- [ ] Add/run focused tests when behavior changes require them under repository instructions; do not run Python/model pipelines for cosmetic changes. Reuse relevant existing frontend tests where available.
- [ ] Update each affected finding's delivery status and evidence/date. A mock-only state, partial fix or unreviewed clinical copy is not a verified end-to-end feature.
- [ ] Summarize completed IDs, remaining limitations and the next single batch. Stop expanding scope when the batch is reviewable.

No UI changes, builds, tests, pipelines or fresh browser checks were performed to create this plan.

## B1 delivery update — 24 October 2026

Implementation and automated checks completed; visual checks blocked by local-server permission (`listen EPERM`). See the tracker’s B1 evidence for partial findings, contract limitations and exact checks. No subsequent batch has started.

## B2 delivery update — 24 October 2026

Citizen accessibility/readability baseline implemented; 11 frontend tests and production build pass. Browser interaction, rendered contrast and zoom checks remain outstanding. See tracker evidence; B3 has not started.

## B3 delivery update — 24 October 2026

Education-first home and explicit prototype notice gate implemented. All 13 frontend tests and production build pass. Privacy readiness and returning-user home remain partial; browser verification outstanding. See tracker evidence. B4 has not started.

## B3 refinement brief — 24 October 2026, proposed

**Product-lead direction:** simplify the text-heavy home into a dashboard. Put the check-in summary first, followed by one relevant next action and three destination modules: Learn, Care, Track. Supplied screenshots inform visual hierarchy, not wholesale feature adoption. This brief supersedes the earlier two-topic learning-strip proposal; dashboard redesign is not yet implemented.

### Dashboard content and hierarchy

1. **Compact header:** AGAP-CKD and a quiet Prototype label. No invented profile/avatar, long welcome paragraph, or decorative metrics.
2. **Primary check-in summary:** the dominant surface at the top.
   - Unassessed: “Wala pang check-in,” one brief explanation, and “Simulan ang check-in.” No score, empty chart or Low implication. Questionnaire is not labeled a laboratory test.
   - Available result: prominent Low/Medium/High text with supporting icon, actual assessment date when available, one short explanation, and the main next action. Secondary “Tingnan ang detalye” opens existing detailed results. Do not expose raw model probability or invent a refresh interval.
   - Loading, failed and unsupported states remain distinct; never substitute Low. Clinician-care routing is separate from risk classification and subject to D1/C-41.
   - Home may reuse the current in-memory result; cross-session history remains parked. Displaying an API result does not establish clinical validation; backend correctness remains C-03.
3. **One next action, when useful:** normally inside the summary to avoid duplicating its CTA. A separate short row is justified only for additional applicable context. Before a check-in, omit personalized advice. Heat content is conditional on supported input/applicability, not a permanent risk tile.
4. **Three destination modules:** previews of pages, rather than full page content on the dashboard.

| Module | Destination content | Baseline behavior | Boundary |
|---|---|---|---|
| Learn / Alamin | Basic kidney information, kidney-friendly recipes, lifestyle resources | Active destination with three categories; simple image placeholders for recipe/resource previews | Category structure is agreed; actual recipes/health claims require reviewed content. Do not imply every recipe fits every kidney condition. No personalized diet or nutrient prescription. |
| Care / Magpa-check | List of facilities, town/address, offered services, contact and Google Maps link where supported | Active destination; useful even before assessment. Honest empty/unverified/missing-data states; no town preselection | B6 governs facility facts. No fabricated facility names/free-test claims, live stock, bookings or institutional partnership claims. Extensible later without displaying unfinished functionality now. |
| Track / Subaybayan | Lab test results, food log, nutrient targets; possible BP recordings/trends | Visible “Coming soon / Paparating” preview, clearly non-interactive | Phase two: no working inputs, fake graphs, progress rings, numeric targets, reminders or saved history. |

### Recommended UI: summary first, stacked destination rows

Use one generous mint summary surface, then a section label such as “Tuklasin” and three compact horizontal destination rows. Each row has a Lucide icon, title, one-line purpose and a clear trailing affordance. Image placeholders belong only to Recipes/Lifestyle previews within Learn. Learn and Care have chevrons; Track has a readable Coming soon label and no chevron. Keep its label legible rather than fading the whole row.

This composition preserves the top summary as the focal point and accommodates Filipino/Taglish labels at narrow widths better than three equal-width tiles. Avoid a carousel hiding one destination, a busy bento grid, or three large competing cards. Let content height expand under text zoom. Do not add a bottom navigation bar for three modules during this refinement; citizen-local page views with a named Back control are sufficient. Shared-shell redesign remains parked C-19.

Use neutral, static placeholders labeled “Larawan” only for upcoming recipe/lifestyle image content inside Learn; they are intentional placeholders, not animated loading skeletons. Decorative placeholders should be hidden from assistive technology when the adjacent title already supplies meaning. Real photographs are not required for baseline implementation.

### Destination layout

- **Learn:** page heading, a short category selector (Basics / Recipes / Lifestyle with clear localized labels), and a short list of content previews. Opening an item reveals its content and sources. Do not fabricate complete articles or recipes to fill the layout; show a clear content-preparation state where material is not yet reviewed. All learning remains accessible without questionnaire consent.
- **Care:** page heading, deliberate town selection if needed, facility rows, expandable service/contact information, and missing-data states. Do not require a completed check-in to browse. No new API work is silently included.
- **Track:** a static dashboard preview only; no destination until there is useful content. Announce Coming soon in accessible text, without a dead focusable button.

### Visual and interaction constraints

- Existing green/mint palette, clear dark text, restrained surface grouping and generous separation. Place most explanatory copy on destination/detail screens.
- One primary action in the summary. Short non-diagnosis wording next to an available result; fuller prototype/data notice stays before health answers.
- Native links/buttons for active destinations, stable heading focus and visible keyboard focus on interactive elements. No heading outline box.
- First viewport should prioritize summary and CTA. Confirm rendered widths/zoom and shared-shell constraints before claiming this achieved.
- State previews must be explicitly fictional when not backed by current inputs. Do not invent dates, readings, facility records or health outcomes.

### Parked phase-two work

Recurring BP check-ins, manual readings with source/time/context, trends and reminders; longitudinal lab/check-in history; food logs and nutrient targets. Cadence, persistence, consent, measurement quality, interpretation and clinical escalation need explicit decisions. No assumption of daily reminders or universal fluid/nutrient targets. Medications, appointments and care-team features remain possible extensions, not committed requirements.

### Implementation order and acceptance

1. Build the summary plus three icon-led destination rows; use image placeholders only inside Learn; connect unassessed and current in-memory result/unavailable variants.
2. Add citizen-local Learn and Care navigation, reuse consent and detailed-result screens, and apply B6 data honesty to facilities. Track stays non-interactive.
3. Check first use, result return, unavailable result, no facility records, unreviewed learning content, Back, keyboard access and text zoom. No dead controls, fictitious personalization, or tracker implementation.

**Reference:** `docs/AGAP-CKD-PRD-v3.md`, Citizen flow and Risk level, plus current code and approved tracker decisions. New Learn categories and the module structure are product-lead additions, not existing PRD implementation claims. Kidnee article: https://blog.flutterflow.io/kidnee-a-new-way-to-manage-kidney-disease/ (June 1, 2023; consulted October 24, 2026). Its composition and destinations are inspiration, not evidence of AGAP feature effectiveness.

**Status:** proposed layout ready for review; this update changes documentation only. Earlier heading-focus box correction is implemented; browser verification remains outstanding.

## B3 dashboard implementation — 24 October 2026

Product-lead correction applied: image placeholders are for recipes/lifestyle inside Learn, not dashboard module rows. Existing Lucide assets supply BookOpen (Learn), MapPin (Care), ChartLine (Track), ClipboardList/status icons (summary), HeartPulse (brand), and navigation icons. No generated/downloaded imagery or new dependencies.

Implemented `CitizenEntry.tsx` summary/module composition and `CitizenResources.tsx` Learn/Care pages. Dashboard reuses the current in-memory result/unavailable state; detailed results can return home without clearing that state. A client timestamp is labeled as display time within this session, not laboratory history or a saved clinical record. Existing detailed-result shortcomings remain under B4.

Learn tabs use keyboard navigation; Basics reuses existing product explanations. Recipe/lifestyle previews have static image placeholders and explicit content-review status, not invented articles or personalized advice. Track is a static Coming soon row. Care reads the existing `/api/facilities` endpoint; unnamed rows are excluded from its citizen directory and missing usable records produce an honest empty state. No verified partnership, address, phone, map or service facts were invented. Full B6 facility enrichment remains open.

Verification evidence and outstanding states are recorded in the tracker. This implementation supersedes the earlier “not implemented” status for the dashboard composition; parked tracking/BP work remains unimplemented.

## Visual direction adjustment — 24 October 2026

Product lead requested a stronger modern dashboard finish and the supplied screenshot's outlined answer selection throughout. Use dark forest/pale lime for the first-use summary, restrained mint destination surfaces, and a quiet parked Track row. Preserve risk-status color meaning on completed summaries. All choice controls use white selected surfaces with a dark inset border/check; keyboard focus has a separate outer ring. Kasarian is a native dropdown with an empty default and all four approved options. Scope and parked items unchanged; current verification limits are in the tracker.

## Gradient dashboard and in-app select — 24 October 2026

Latest product-lead direction supersedes the stacked-row/dark-summary composition: an open subtle green gradient across the citizen dashboard, concise state text with a small adjacent action, score on the left and abstract indicator on the right, then simple Learn/Care cards and parked Track preview. Recipe/lifestyle image placeholders remain inside Learn only.

The explicit request for a numeric score supersedes the earlier hide-numeric-score design constraint for the prototype presentation only: display rounded `model_probability * 100` as “Demo model score” /100 only for a known scored level and a finite probability in [0,1]. Missing/invalid values, unassessed, unavailable and clinician-care states show no number. The score is not a validated clinical risk percentage; the text distinguishes it from diagnosis and explains that risk-factor rules can change the categorical level. No model or threshold changes. The abstract radial SVG is decorative geometry, not a time series or a calibrated gauge.

`components/CitizenSelect.tsx` is the shared in-app listbox/combobox for Kasarian and Care town filtering. Empty sex default preserved; keyboard open/arrows/Home/End/typeahead/Enter/Space/Escape/Tab, active option, selected check, outside dismissal and trigger focus are implemented. Real interactive assistive-technology verification remains outstanding.

Citizen view icons now use official Phosphor regular paths in `components/PhosphorIcons.tsx`, with license/provenance at `public/PHOSPHOR-LICENSE.txt` (included in the build). npm install failed with registry DNS ENOTFOUND; official source definitions were retrieved through browsing and bundled locally. No icon CDN, package changes or fabricated Phosphor aliases. Shared-shell and other-role icons remain unchanged under the citizen-only scope.
