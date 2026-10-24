# Product Research

Use this folder to investigate the AGAP-CKD concept, evaluate evidence, and record product direction. Start with [the product discovery workflow](product_workflow.md). Record the question, method, date, sources, findings, limitations, and resulting decision. Distinguish observed findings from reported, inferred, and assumed claims.

## Directory guide

```text
research/
  README.md
  product_workflow.md
  validation/
    interviews/              # supplied interview minutes and team synthesis
  evidence/
    competition/             # competition brief and requirements
  decisions/
    baseline/                # submitted proposal, preserved as historical context
    concepts/                # personal ideas, not validated requirements
    proposed/                # proposed PRD and architecture, not implementation truth
  ssot/                      # current-version PRD and architecture
  prompts/                   # reusable research/specification instructions
```

- **`validation/`** — stakeholder/user research, workflow checks, and assumptions being examined. The two interview PDFs describe one joint conversation, not independent corroboration. Keep participant accounts separate from the team's interpretations.
- **`evidence/`** — clinical, climate, policy, competition, and data-source evidence. Create topical subfolders as material accumulates. An accessible source page does not establish that its underlying dataset has been obtained.
- **`decisions/`** — historical baseline, product concepts, proposed scope and future decision records. A proposal or personal note is not evidence of user demand or implemented functionality.
- **`ssot/`** — the documented current implementation baseline. Keep it separate from proposed changes.
- **`prompts/`** — instructions for repeatable research and specification work; maintain their repository paths when files move.

Create `market/` for alternatives/ecosystem research and `templates/` for reusable research templates when there is material to store. Neither currently contains research, so no empty placeholder folders are required.

## Start here

| Material | Location |
|---|---|
| Submitted proposal | Not included in the public repository; its reference list is in [`references.txt`](../references.txt) |
| Competition primer | `[00] Primer.pdf` — kept out of Git (29.6 MB); held locally by the team |
| Interview minutes | `Minutes (1).pdf` — kept out of Git: names the participants, whose consent to be named is pending |
| Interview synthesis | `Dialysis-Nurse-Interview-Notes.pdf` — kept out of Git for the same reason |
| Personal concepts | [PersonalNotes.md](decisions/concepts/PersonalNotes.md) |
| Current product baseline | [PRD](ssot/PRD.md) · [Architecture](ssot/ARCHITECTURE.md) |
| Proposed specifications | [PRD](decisions/proposed/PRD.md) · [Architecture](decisions/proposed/ARCHITECTURE.md) |
| Optional simulation research | [23 October shortlist](evidence/2026-10-23-simulation-options.md) |
| Proposed data inventory | [Public, citizen, synthetic and derived data](evidence/2026-10-23-proposed-data-inventory.md) |
| SMART data specification | [Field contracts, citizen inputs and acceptance gates](decisions/proposed/DATA_SPEC.md) |
| Data feasibility findings | [Secured inputs and resulting feature candidates](evidence/2026-10-23-data-feasibility.md) |

## Evidence and document handling

Preserve supplied reference documents and their filenames; organize by moving them rather than rewriting their contents. Cite PDFs by filename and page. Keep source links, dates, definitions, geography, and access limitations with research findings.

The proposed specifications are **Version 3 (23 October 2026)**: a data-led direction covering population risk-factor analysis, geographic coverage, and separate pre-dialysis/dialysis research branches. The citizen-facing interface remains in product scope; only detailed design discussion is paused. Dataset feasibility, D’s time-based target, and real-world usefulness remain unresolved; these are proposed specifications, not implemented capabilities.

Interview originals contain participant names; public naming/quotation permission has not been confirmed. Preserve the supplied originals locally and use role-attributed paraphrases in public-facing material. Review identifiable material before publishing or committing; keep private health records, contact details, recordings, and consent forms out of Git.
