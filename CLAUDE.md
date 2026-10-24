# CLAUDE.md

@AGENTS.md

## Claude Code Execution Guidance

Claude Code discovers project skills via `.claude/skills/` (symlink to `.agents/skills/`). Edit skills only in `.agents/skills/`.

### Core Commands & Fast Verifications
- Run fast unit tests: `pytest tests/test_<area>.py`
- Run full test suite: `make test`
- Audit feature leakage: `python .agents/skills/ckd-health-data-scientist/scripts/leakage_scanner.py --features <f1,f2,...>`
- Audit parameter register: `python .agents/skills/ckd-health-researcher/scripts/parameter_register_validator.py`
- Compute clinical net benefit: `python .agents/skills/ckd-health-data-scientist/scripts/decision_curve.py --file <preds.csv>`
- Estimate sample size (Riley criteria): `python .agents/skills/ckd-health-researcher/scripts/pmsampsize_estimator.py --c-statistic <auc> --prevalence <prev> --parameters <p>`

### Operational Rules
1. **Never declare victory without running tests.** Always execute the relevant pytest file before concluding a task.
2. **Parameters live in config.** Read/modify `config/params.yaml`, never hardcode numbers. Keep `config/parameter_register.yaml` in sync.
3. **Screening flag $\neq$ diagnosis.** All patient data are synthetic; outputs are prioritization flags. Never refer to model flags as medical advice or diagnoses.
4. **Zero-leakage enforcement.** Outcome-defining variables (`creatinine`, `egfr`, `uacr`, `y_true`, or 90/180d follow-ups) must never enter a feature matrix.
