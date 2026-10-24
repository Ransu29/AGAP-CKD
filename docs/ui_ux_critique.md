# Design critique: AGAP-CKD Streamlit app

Prepared 23 October 2026, against commit `3a8a054`. Inputs:
- the product modules in `docs/product_overview.md`;
- the page structure in `app/main.py`, `src/agap/walkthrough.py`, `src/agap/workflow_ui.py` and `app/workspace.css`;
- the inventory of 63 items from 21 October in `docs/ux_audit.md`.

I did not render screenshots for this critique. Findings on layout and hierarchy come from the code's structure, together with the earlier audit's full-height screenshots. Run `make verify-browser` to get fresh ones before acting on the visual points.

---

## Overall impression

The individual parts are good: the resident decision card, the model-shift card, the worklist queues and the safety wording. The app reads as "all over the place" because **the product's modules don't map onto the app's pages**.
- One screen mixes **operational work** (planning, approving, working cases) with **simulation evaluation** (hidden outcomes, calibration, missed-case analysis).
- One page called "Evidence & readiness" holds six unrelated tools.

Most of the clutter is an information-architecture problem, not a styling one. Fix the structure first; the visual polish matters less.

---

## 1. Module-to-page mapping: where the separation broke

The product overview defines separate modules. Here is where each one actually lives in the UI today.

| Module (product overview) | Who it serves | Where it lives now | Problem |
|---|---|---|---|
| Plan (§4.1) | LGU planner | Screening workspace → Plan: map (left) + a 3-tab side panel (Residents / Decision / Plan) | Plan controls, CSV export **and round approval** are squeezed into one tab of a fixed-height (678 px) side panel |
| Simulation evaluation (§4.5) | Analyst | **Below the map on the same Plan screen** (`_plan_results`): missed-case chart, swap table, municipal summaries, 180-day persistence | Hidden simulator truth sits on the planner's own screen. This is the biggest source of mixing; the 21 Oct audit measured the page at ~4,500 px tall |
| Climate model comparison (§4.4) | Analyst / judge | Twice: below the map on the Plan screen (`_model_comparison`), **and** on the Climate comparison page | Two places, and two "Active planning model" controls (map toolbar and the Climate page) for one setting |
| Resident report (§4.2) | Barangay health worker | A top-level page, but it is empty until a resident is selected on another page | A step in a task presented as a destination. Users land on "Select a resident in the screening planner" |
| Worklist (§4.3) | RHU coordinator | Inside Screening workspace, behind a Plan / Worklist radio. Plan is hidden with a CSS `display:none` hack | The coordinator's daily tool is a sub-mode of the planner. When a round exists, its default is right, but the coordinator's job never gets its own top-level place |
| Community surveillance (§4.5) | Analyst / LGU | An expander **inside** Evidence & readiness, but rendered from `main.py` as a separate "tab" handle | A full analytics module (4 charts, 3 tables) hidden in a collapsed section |
| Clinic verification (§4.5) | Data steward | An expander inside Evidence & readiness | An **operational data-entry tool** filed under "evidence" |
| Research gateway (§4.5) | Researcher | An expander inside Evidence & readiness | A separate engine (E4-05 requires it to be separate), yet nested beside safeguards |
| Run safeguards and provenance (§4.6) | Analyst / judge | Evidence & readiness: metrics, honesty text, raw manifest JSON, data sources | Fine as content, but mixed with the three tools above |
| Team-only content | Team | Evidence & readiness: "A short presentation script", "Why is there a January 2021 temperature file?" | The 21 Oct audit marked both **CUT**. Both are still in `app/main.py` |
| Help and instructions | Everyone | Sidebar (collapsed by default) plus a header caption plus 102 `st.caption` calls | Instructions sit where nobody looks, and captions are everywhere else |

**Root cause.** Pages are grouped by *engine or implementation* (walkthrough, climate, evidence), not by *user and job*. The 21 Oct audit proposed a Story tab and an Analyst view to fix this. Neither is implemented: a grep finds no "Analyst" or "Story" in `app/` or `src/`. In the meantime the Worklist was added, which made the Plan screen denser still.

---

## 2. Usability

| Finding | Severity | Recommendation |
|---|---|---|
| Simulation evaluation (hidden outcomes) renders on the operational Plan screen, below the map | 🔴 Critical | Move all of `_plan_results` and the evaluation half of `_model_comparison` to an **Evaluate** destination. Keep one result card under the map ("500 tests → 346 completed → 53 of 166 found; random: 17"), as audit change #2 recommended |
| Round approval (a commit that can't be undone) is the last block inside the Plan side-panel tab, under the controls and export | 🔴 Critical | Make approval a deliberate step: a primary **Approve round…** button that opens an `st.dialog` with a summary (budget, model, strategy, counts by municipality) and a confirmation. Approval is the hand-off between the two main jobs; it should not be scrolled past |
| The coordinator's Worklist is a radio sub-mode of the planner | 🟡 Moderate | Make **Worklist** (or "Today") its own top-level destination, first when a round exists. That matches the revised plan's "Today / Residents / Screening plans / Community" navigation |
| Resident report is a page that is unusable without a selection made elsewhere | 🟡 Moderate | Open it as an `st.dialog` (or a side sheet) from the Decision card's **Review / correct questionnaire**. Previews and applying stay as they are; only the container changes |
| Two "Active planning model" controls (map toolbar and Climate page) | 🟡 Moderate | One control, in the Plan toolbar. The Climate page shows the active model read-only, with a link back |
| "Compare screening plans" sits in the side panel, but its results appear below the map, outside the viewport | 🟡 Moderate | Show the result card directly under the button (or pinned above the map), with the full comparison in Evaluate |
| The Worklist case view has about 12 expanders (contact, visit, review, owner, recover, case details, history, downloads, archive…) | 🟡 Moderate | Show **only the next action's form** open. Put the rest behind one "Case record" tab group: Details / History / Downloads. Expander titles that are tasks ("Record contact") should be buttons that set the stage |
| Help lives in a collapsed sidebar; the sidebar also holds **Reset draft workspace** and the run info | 🟢 Minor | Remove the sidebar. Put Reset in a "⋯" menu in the header, run info in Evaluate → Provenance, and give each page one short line of instruction under its title |
| The Plan / Worklist switch hides Plan with injected CSS, so Plan still computes on every rerun | 🟢 Minor | Once Worklist is its own page this goes away. Render only the active page |
| On mobile, a "Tasks / Map" radio replaces the side-by-side layout | 🟢 Minor | Keep it. The overview already says "desktop coordinator prototype"; don't invest more until the page structure changes |

---

## 3. Visual hierarchy

- **What draws the eye first:** the dark green brand bar, then the 640 px map. On the Plan screen that's right. On every other page the brand bar competes with the page's own title, because there *is* no page-level title (tabs only).
- **Reading flow:** the map sits on the left (72%) and a tabbed panel on the right (Residents → Decision → Plan). The task order is *set budget → plan → inspect residents → approve*, but the tab order is Residents first and Plan last. Below the fold the eye falls into evaluation charts that belong to a different job.
- **Emphasis:**
  - Too many things are emphasised: metrics, model-shift cards, coloured chips, map overlays and badges all at once.
  - Too many things are de-emphasised: 102 captions in muted 11–13 px text carry real instructions.
  - Headings are nearly flat: h1 1.5 rem, h2 1.4 rem, h3 1.25 rem, and the side panel's h3 1.15 rem. Section and sub-section look the same.

**Fixes:**
1. Each page gets one H1-level title, plus one line on *the question this page answers*.
2. Use a clear type scale: 1.5 / 1.125 / 0.875 rem, a ratio of about 1.33. Keep weight, not only size, for sub-headings.
3. Order the Plan panel tabs as **Plan → Residents → Decision**, or better, put the plan controls in a toolbar above the map. Then the panel is about residents only.
4. Fold captions:
   - definitional text (H3 resolution, ERA5 grid, attribution) → a single ⓘ popover per widget, using `help=`;
   - safety text → the global disclaimer banner;
   - only captions that change what the user does stay inline.

   Target: under 30 visible captions app-wide, down from 102.

---

## 4. Consistency

| Element | Issue | Recommendation |
|---|---|---|
| Naming | The browser title says "Screening coordinator"; the header "Community screening workspace"; the page "Screening workspace"; captions say "screening planner", and the alias map lists "Screening planner", "Weather & score" and "Evidence & data readiness" | One glossary: **Today / Plan / Residents / Evaluate / Data**. Apply it to tab names, buttons ("Show in screening workspace"), captions and tests together |
| Terms | "panels", "tests", "invitations", "slots" and "positives" / "abnormal flags" / "abnormal results" are used interchangeably | Pick one term for each: *test (panel)*, *invitation*, *slot*, *abnormal screen*. The audit's plain-language table (21 Oct) already lists them |
| Colour | Plotly charts hard-code hexes (`#285a46`, `#b36c30`, `#507c9a`…) in `main.py`, outside the `--agap-*` tokens. Map added/removed colours live in CSS only | Add chart tokens (a categorical palette plus `--agap-eval` for simulation-truth views) and use them in one Plotly template (`pio.templates["agap"]`) |
| "Evaluation" labelling | Hidden-outcome views are marked by a text suffix only: "(eval)", "simulation evaluation only", "simulator truth" | Use one visual treatment for every simulator-truth surface: a dashed border, a tinted header and a "SIMULATION TRUTH: not visible in practice" badge. Users then learn the separation by sight, not by reading captions |
| Cards | Three card styles: `stForm` white cards, `workspace_tools` bordered, and custom HTML cards (`agap-model-shift`, `agap-current-decision`) with their own radii (8 / 10 / 12 px) | One card component (radius 12, border token, padding `--agap-space-5`). The decision and model-shift cards keep their content but use it |
| Spacing | Tokens exist (`--agap-space-1..6`), but custom HTML blocks use raw px (`gap:10px`, `margin:4px 0`, `padding:6px 10px`) | Replace raw px with tokens in `workspace.css` |

---

## 5. Accessibility

- **Colour contrast:** text colours pass WCAG AA. Calculated: muted caption `#536c64` on the page background is 5.1:1; the decision eyebrow is 4.7:1; the added and removed map markers are 5.0 and 5.1:1 on white.
- **Text size:**
  - **Fails the guideline.** Several custom labels are 9–11 px: `.agap-current-decision > span` is 9 px; the resident-facts `dt`, the model-label badges and the scope badge are 10 px; captions on the map overlay are 10–11 px.
  - These carry meaning (what the number is, the selection reason).
  - Fix: minimum 12 px, and 13–14 px for anything a user must read to decide.
- **Colour alone:** map coverage and added/removed markers use colour plus a fill or outline difference. That's good; keep the shape coding when tokens change.
- **Targets:** Streamlit's defaults are fine. Expander summaries are 48 px high, which is good.
- **Screen readers:**
  - The pydeck maps carry an `alt`. The Plotly map does not.
  - Custom HTML cards rely on `<b>` and `<span>` with no headings or landmarks.
  - Fix: give the decision and model-shift cards a heading element and an `aria-label` that states the verdict.

---

## 6. What works well

- **The decision card answers "why this person?"**: the invitation, the actual selection reason, the assigned service point and fact chips. It is the best element in the app.
- **The model-shift card** (score → rank → verdict) makes the climate question concrete for one resident.
- **The Plan and Worklist split is the right concept.** Frozen approval, slot recovery, and "no activity inferred from hidden outcomes" are exactly the separation the product needs. It is only placed wrongly.
- **The safety wording is consistent and careful** throughout ("review task, not a diagnosis").
- **Offline, accessible map engineering**: bundled tiles, an outline fallback, `alt` text, and a browser check that the map size is right.

---

## 7. Proposed information architecture

Organise by **user and job**, as the revised implementation plan already suggests. Every current item has a home and nothing is deleted except the two team-only notes.

```
Header: AGAP-CKD · [SYNTHETIC DEMO] · disclaimer banner (always visible) · ⋯ (reset, run info)

1. Today            (RHU coordinator; default when a round exists)
   Queue counts strip → case list (filters) → selected case: next-action form open,
   Case record [Details | History | Downloads] in tabs. Round details + archive in ⋯.

2. Plan             (LGU planner; default when no round exists)
   Toolbar: budget · strategy · outreach · model (single control) · [Compare]
   Map (left) │ Residents panel: queue → selected resident's decision card
   Result card under map (one line, live) · [Approve round…] → confirmation dialog
   Resident report = dialog launched from the decision card.

3. Evaluate         (analyst / judge; everything here carries the SIMULATION TRUTH treatment)
   Tabs: Plan vs random │ Climate vs questionnaire │ Follow-up (180 d) │ Surveillance │ Safeguards & provenance
   (absorbs _plan_results, the model-comparison evaluation, the per-resident weather timeline,
    surveillance, evidence scorecard, model metrics, manifest)

4. Data             (data steward)
   Clinic verification workspace │ Data sources & licences │ Weather provenance

5. Research (demo)  (separate by design, E4-05; could sit under Data if five destinations is too many)
```

The per-resident **climate timeline** has two halves. The *weather context* is observable, so a compact version stays reachable from the decision card on Plan. The *model comparison and its outcomes* are evaluation, so they go to Evaluate.

---

## 8. Priority recommendations

1. **Separate operations from evaluation.** Move everything below the map, and the outcome half of the climate comparison, into **Evaluate**, and give that destination one visual treatment. This removes most of the "information heavy" feeling at once. The work is mostly moving existing render calls (`_plan_results`, `_model_comparison`, the surveillance and evidence blocks) under a new tab. Audit changes #3–4 estimated about 5 hours, and listed the tab-name assertions in tests that must change in the same commit.
2. **Give each job its own destination and make approval explicit.** Today (Worklist), Plan, Evaluate, Data. Approval becomes a confirmation dialog and Resident report becomes a dialog. This is the separation of modules the product overview describes, and it lines up with the revised plan's navigation, so care Release A can extend it rather than redo it.
3. **Cut the noise.**
   - Delete the presentation script and the January 2021 file section.
   - Fold the 102 captions into a global banner plus `help=` popovers.
   - Set a 12 px minimum font size.
   - Use one type scale, one card style and one Plotly template.

   This is low-risk CSS and wording work, and it should come after #1 and #2 so the copy is written once for its final place.

**Not recommended now:** a Story landing tab (from the 21 Oct audit). It made sense for a judging video. Once Evaluate exists, a short "headline" strip at the top of Evaluate does the same job without adding a sixth destination.
