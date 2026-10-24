# AGAP-CKD Frontend Application

React + TypeScript + Vite frontend for the **AGAP-CKD** kidney risk check (PRD v3).

Built for the **Philippine Junior Data Science Challenge (PJDSC) 2026**.

---

## Design System: 1a Mint Calm

Follows the canonical design system in `docs/reference/AGAP-Design-System.dc.html`:
- **Canvas:** `#F3F8F4` (soft sage background)
- **Primary Ink:** `#1B2A22` (deep forest charcoal)
- **Primary Green:** `#22A75A` (action green)
- **Surface / Mint:** `#DDF1E4` (soft badge/pill tint)
- **Header Ink:** `#17573A` (dark emerald)
- **Border Radius:** `28px` for cards, `16px` for inner panels, full-pill for badges and status chips.

---

## Views (PRD v3)

Every channel asks the same PRD v3 questions and is scored by `POST /api/risk-check/evaluate`: the frozen
risk-level model, its saved cut-offs and the guideline floor (ADR 0002, ADR 0003). The model's probability is
never returned or shown. The shared questions and wording are in `src/riskCheck/content.ts`.

1. **Citizen app (`CitizenView.tsx`, `CitizenEntry.tsx`, `CitizenResources.tsx`):** dashboard (level only),
   Learn, Care (PhilHealth YAKAP facilities) and Track (coming soon); consent, safety pre-check, the PRD v3
   questionnaire and the result (next step and date, reasons, tips, facilities).
2. **SMS (`SmsView.tsx`, `src/riskCheck/smsFlow.ts`):** a simulated basic phone running the PRD v3 SMS
   flow (CHECK, consent, numbered replies, STOP/HELP/BACK/TULOY, multi-part result). No real messages are sent.
3. **Field health worker tablet (`FieldWorkerView.tsx`):** Today list (no names or IDs), consent script,
   the same check in a large layout, referral note, and Sync (`POST /api/field/batch-sync`).
4. **Analyst (`AnalystView.tsx`):** province map (A1), municipality detail (A2), climate context (A3) and
   model quality (A4), from `GET /api/analyst/*`.

App checks are recorded when scored and field checks when synced (`data/reports/*.jsonl`, git-ignored); the
analyst map adds them to its simulated checks.

---

## Quick Start

### 0. Build the data once (fresh clone)
```bash
make prepare-climate   # ERA5-Land daily table from the committed extract
make triage            # frozen risk-level model and cut-offs
make analyst           # analyst map, climate and model-quality data
```

### 1. Start the Backend API
```bash
make api
# Runs FastAPI on http://127.0.0.1:8000
```

### 2. Start the Frontend
```bash
make web
# Runs Vite on http://localhost:5173
```

### 3. Production Build
```bash
make web-build
# Compiles TypeScript and creates optimized bundles in frontend/dist/
```

---

## Architecture & Data Flow

- The frontend communicates directly with the FastAPI REST API (`api/main.py`).
- Scoring runs in the local API, so a check needs no internet; only field Sync does. In-browser offline scoring is Phase 2.
- SVG boundaries for Laguna are loaded from `frontend/src/data/laguna-municipalities.json` with spherical winding correction (RFC 7946).
