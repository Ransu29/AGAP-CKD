# Repository Guidelines

## Project Structure & Module Organization

The Python package is in `src/agap/`, organized by domain (`climate/`, `data/`, `models/`, `allocation/`, and `simulate/`). Keep reusable logic there and command-line entry points in `scripts/`; the Makefile invokes those scripts. The Streamlit app is in `app/`, tests in `tests/`, configuration in `config/`, documentation in `docs/`, and generated reports in `outputs/`. Treat `notebooks/` as exploratory. Read `data/README.md` before changing data workflows; do not commit generated or private data.

## Build, Test, and Development Commands

Use Python 3.10+ in a virtual environment and install dependencies with `pip install -r requirements.txt`.

- `make test` runs pytest.
- `make all` runs the small synthetic-data pipeline using `config/params.yaml`.
- `make demo` starts Streamlit at `http://localhost:8501`.
- `make data`, `make simulate`, and `make train` run individual pipeline stages.
- `make experiments CONFIG=config/fast.yaml` runs a smaller experiment profile; `config/full.yaml` is for longer runs.

Downloads are separate from the default pipeline. Review data-source documentation before running collection targets.

## Coding Style & Naming Conventions

Follow existing Python style: four-space indentation, `snake_case` for modules, functions, and variables, and `PascalCase` for classes. Keep domain code in its corresponding package module and scenario settings in YAML rather than hard-coding them. Add type hints and focused docstrings where they clarify interfaces or assumptions. No formatter or linter is configured; match nearby code.

## Testing Guidelines

Tests use pytest, are collected from `tests/`, and follow `test_<area>.py`. Add focused tests for behavior changes and run `make test` from the repository root. Keep tests deterministic with explicit seeds and synthetic fixtures; ordinary unit tests should not download data.

## Commit & Pull Request Guidelines

Recent history uses short imperative subjects with prefixes such as `feat:`, `test:`, and `docs:`. Keep commits focused (for example, `fix: preserve saved screening dates`). Pull requests should explain the change and rationale, link related issues or decisions, note configuration/data implications, and include screenshots for visible app changes. Report `make test` results and request at least one teammate review before merging.

## Data, Safety, and Configuration

Patient-level records are synthetic, and model outputs are screening flags rather than diagnoses. Preserve these limits in code, reports, and UI. Keep seeds, thresholds, and scenario choices in configuration. Never commit credentials or private data; document provenance and licensing for external sources.

## Agent Skills

Project skills live in `.agents/skills/` (mirrored to `.claude/skills/` for Claude Code). Load the matching `SKILL.md` before starting related work:

- `ckd-health-data-scientist` — clinical ML framing, features, risk models, calibration, thresholds, fairness, leakage and selection-bias checks for CKD screening. Includes executable tools:
  - `.agents/skills/ckd-health-data-scientist/scripts/leakage_scanner.py` (zero-leakage validator).
  - `.agents/skills/ckd-health-data-scientist/scripts/decision_curve.py` (clinical net benefit / DCA).
  - References: `model_card_template.md`, `ckd_clinical_reference.md`.
- `ckd-health-researcher` — research questions, study/simulation design, evidence appraisal, causal and missing-data methods, and reporting guidelines (TRIPOD+AI, STROBE, PROBAST). Includes executable tools:
  - `.agents/skills/ckd-health-researcher/scripts/pmsampsize_estimator.py` (Riley sample size criteria).
  - `.agents/skills/ckd-health-researcher/scripts/parameter_register_validator.py` (SIM-04 audit).
  - References: `ademp_simulation_template.md`, `audit_review_protocol.md`, `reporting_guidelines.md`.

## Agent Verification Protocol (The "Done" Checklist)

Before claiming a task, model, or research modification is complete, agents MUST complete this verification cycle:

1. **Safety & Framing:** Verify no synthetic screening result is described as a "diagnosis" or "CKD".
2. **Leakage Audit:** Run `leakage_scanner.py` on any modified feature sets or model scripts.
3. **Parameter Provenance:** Run `parameter_register_validator.py` if any numeric parameters or simulator generators were touched.
4. **Automated Testing:** Run `pytest tests/test_<area>.py` (or `make test`). Explain any test failure root cause before attempting a fix.
5. **Calibrated Utility:** For modeling tasks, report discrimination (AUROC/AUPRC), calibration slope, and decision-curve net benefit against baseline.
