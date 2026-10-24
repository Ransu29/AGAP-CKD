# App

Run `make prepare-climate` once if needed, then `make all CONFIG=config/climate.yaml`
and `make demo CONFIG=config/climate.yaml`. Open the URL printed by Streamlit.

Destinations follow the user's job. **Worklist** (staff, the default once a round
is approved) and **Plan** (draft scenarios) are operational; **Resident report** and
**Resident weather** are detail pages for the selected resident and return to the
page that opened them. **Evaluate** holds everything that uses hidden simulated
outcomes (plan vs random, climate vs questionnaire, surveillance, safeguards) under
one dashed "simulation truth" frame. **Data** holds clinic verification, data sources
and the research-interest demo. New sessions start with Questionnaire only.
On screens at 1100 pixels and below, a visible **Page** selector replaces the
horizontal destination tabs. Both controls use the same destination state.

1. In Plan, select a community on the large map, then a resident row. Decision
   shows the draft invitation, actual selection reason, known inputs and modeled
   access. **Why this score?** is an optional fitted-intercept waterfall.
2. Open **Plan settings** in the side panel, select the whole-cohort panel budget and strategy,
   and click **Compare screening plans**. Draft control edits do not apply until
   submission. Filters never change the allocation denominator or whole-plan CSV.
3. **Review / correct questionnaire** validates fictional form/SMS inputs and
   previews scores. **Apply report & return to workspace** updates only explicit
   applications, retaining the resident and other applied reports.
4. Below the map, review the plan summary and the assignments under **Approve a
   demo screening round**, tick the confirmation and click **Create demo screening round**. The active model, policy, operational inputs,
   assignments, capacity and replacement orders are frozen. Worklist opens.
5. Work the five queues: **Needs contact**, **Awaiting screening**, **Needs review /
   follow-up**, **Tasks complete**, and **Declined / withdrawn**. Record contact,
   specimen collection, fictional results, ownership, due dates and review actions.
   No activity is inferred from hidden simulation outcomes.
   Queue counts remain visible; **Browse worklist** provides search, staff due-date
   filters and a selectable ten-case page with next action, owner and due date.
   Saves keep the current case open and acknowledge its resulting queue. Use
   **Open next case** to advance explicitly. Short aliases retain full IDs in
   selectors, case details and exports.
6. A partial panel remains incomplete. Observed abnormal components open a review
   task, not a diagnosis. Results use creatinine mg/dL and uACR mg/g. Revisions
   preserve previous values and do not silently erase open review tasks.
7. An explicit decline before testing releases a slot. Review and confirm its
   replacement from the frozen ordering, same municipality/service point and
   saved access limit. An unanswered contact, overdue date or started panel does
   not release capacity. No eligible replacement leaves the slot open.
   Compare the two cases, eligibility checks and before/after occupied capacity.
   After saving, **Open replacement case** follows that resident explicitly.

The approved worklist and activity history survive reloads. Report applications
within a round are persisted as amendments, while draft model/budget changes
leave approved invitations unchanged. **Reset draft workspace** retains the
round. **Archive demo round** preserves read-only history and exports, including
past-run rounds, without attaching them to a different cohort.

Planning retains one 640-pixel map at about 72% of desktop width. At 1100 pixels
and below, **Tasks / Map** defaults to Tasks. Worklist forms use full width on all
screens within a centered content column capped at 960 pixels; Resident report
uses the same column. Shared spacing tokens in `workspace.css` keep 12-pixel
section gaps, 16-pixel form gaps, and 24-pixel card padding (16 pixels on smaller
screens). Longer forms scroll vertically so labels and actions have room.
The shell uses native HTML rendering to keep the brand and subtitle separated.
The planning queue's **Report / draft** distinguishes questionnaire
completeness from invitation selection; the reason stays in Decision.

**Evaluate → Climate vs questionnaire** and **Resident weather** show actual paired
added/removed/unchanged decisions at the same cohort, settings and draws. Enable
**Show climate invitation changes on the map** to reveal those markers. Draft
counterfactuals never rewrite the approved worklist. Statistical outcomes and
calibration remain labeled simulation evaluation, including negative findings.
**How this plan was formed** explains the applied model, budget, outreach,
capacity, access and municipal requirements. **Evaluate → Plan vs random**
compares with random invitations under the same budget and constraints; its
synthetic outcomes never populate recorded staff tasks.

Local coordination storage is separate from immutable experiment outputs. Its data contract and
transaction guarantees are in `src/agap/workflow.py` and `src/agap/workflow_store.py`. Exports
prepare local worklists; they do not send invitations or book appointments.

The recommended climate profile uses a 1991–2020 reference, 2021–2023 training,
2024 validation and January 2025–September 2026 deployment. Complete saved-date
windows and the original/reassigned ERA5 cells are kept in run-local artifacts.
Other-date exploration changes scores only; missing inputs produce an explanation.
To see the daily plots, select a resident and open **Resident weather** (or click
**View resident weather** in Decision). A decision comparison leads the page:
both saved-date model scores, whole-cohort priority ranks and actual paired
invitation statuses. It explicitly distinguishes unchanged, added, removed,
unplanned and unavailable decisions; rank alone never implies an invitation.
The **Active planning model** control synchronizes with the main planner while
preserving the resident, reports, budget and strategy.

Temperature and rainfall are stacked on one shared local-day axis with a shared
hover and a screening-date marker. Only the preceding 30 complete local days
are plotted. Summary differences use the saved seasonal reference for the
30-day mean daily maximum temperature and total rainfall, not a daily normal or
a heat-index warning. A resident decision card stays beside the timeline with
reporting, access, active invitation reason and **Show in Plan**.
Source/grid/reference definitions and model explanations remain available below;
the displayed public weather and synthetic health decisions stay clearly labeled.
The separate `config/weather_preview.yaml` profile remains available after
`make prepare-weather`: its 2021–2024 weather is context only and its Planning
model selector is fixed to Questionnaire only. Its weather view distinguishes
saved-date coverage, an automatic fallback and a deliberate historical date.
Use `CONFIG=config/public.yaml` for both commands for public geography without the
weather preview.


The simulation-evaluation expander includes a four-part missed-case chart with
policy/category resident inspection and an empirical pure-risk versus outreach
swap table. All use the current model, reports, budget and seeds. Evaluation
categories never filter the operational export.

Resident details show an evaluation-only timeline that separates follow-up
climate coverage from simulated attendance. The report tab shows valid revisions,
rejected attempts and cross-channel duplicate status. The evidence header reads
saved-run safeguards; missing artifacts are unavailable, never assumed passes.

Under **Data → Clinic verification**, the 111
PhilHealth register identities start unverified. Record checked coordinates,
creatinine/uACR availability, complete-panel capacity per round, evidence/source
and date. Unknown values stay blank or Not checked. Partial verification is
supported; pilot-review readiness requires every item. Download the queue as a
worksheet. Idempotent, append-only SQLite revisions live in
`data/reports/clinic_verifications.sqlite3`, with atomic concurrent saves and
history per clinic. These confirmations do not replace a run's hypothetical
service points or alter saved experiments.

**Evaluate → Surveillance** starts with the simulation visibility-gap count chart.
For its selected area/month, observed plus undetected flags equal all hidden
abnormal flags in that fresh monthly synthetic sample. Planner edits do not alter
these saved counts; this comparison is not independent model validation.

## Offline browser verification

The public Laguna profile defaults to **Street map**, using OpenFreeMap's
OSM-derived Liberty style: roads, place names, water and land cover, with native
zoom/pan controls. The same basemap sits under the optional 3D overlay. The
checked-in local pack includes 379 vector tiles (zooms 7–12), fonts, icons and
license notices, about 15 MB total. It covers Laguna and nearby context, not the
whole world; zooming further enlarges that saved detail. `.streamlit/config.toml`
enables local static serving. No API key is required. `make collect-map` regenerates
the bounded pack under the provider's area-download terms. Its source snapshot,
retrieval time and file checksums are in `app/static/maps/laguna/manifest.json`.
If the pack is absent, Street map uses the online service and says internet is
required. **Outline map** retains the tile-free Cartesian fallback; fixture
profiles default to that fallback. Streets are display context only: distances
remain straight-line, and basemap POIs do not verify laboratory capability.

The optional
**3D H3 hex map** replaces it in the same panel; it aggregates actual cohort
members per cell. Height is cohort count (90 display metres/adult), not terrain.
No-cohort cells are omitted. Both views synchronize the municipality and resident
queue. Hypothetical service points are context markers, not selection targets.

Runtime versions are pinned in `requirements.txt`; browser tooling is separate:

```bash
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/verify_offline_browser.py
```

The script starts a temporary local server, blocks and counts attempted internet
requests in a fresh Chromium context, checks local tile/font responses and
attribution, clicks real community markers/H3 columns
and resident rows, and checks resident retention and supporting tabs. In the
climate profile it also switches the two models, verifies scores and downloaded
invitation exports at the same budget, and checks the comparison/calibration
views and unverified clinic form. Pass
`--url http://localhost:8501` to test an existing server. It writes its report and
1440×900 / 1280×800 screenshots for both views to `outputs/browser-verification/`.
It rejects desktop maps smaller than 600 pixels tall / 70% of workspace width,
maps pushed down the page, and 2D geography smaller than 420 pixels tall inside
the outline canvas. It checks the outline fallback too, and fails on missing
map assets or browser console errors. These checks cover actual map size and
interactions, not just chart presence.
The weather check verifies the shared 30-day axis, actual cross-panel hover,
model switching and resident handoff, with initial and scrolled screenshots at
both desktop sizes. Worklist checks also verify header/subtitle separation and
an unobstructed primary action reachable within one viewport of scrolling.
This requires local browser-process and loopback permissions. A JSON unit test
alone does not establish offline rendering. Use **2D community map → Outline
map** for a browser without WebGL support.
