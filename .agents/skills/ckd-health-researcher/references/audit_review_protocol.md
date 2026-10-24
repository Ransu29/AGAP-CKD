# Dual-Perspective CKD Audit Protocol: Reviewer vs. Builder

> Protocol for orchestrating rigorous multi-perspective reviews of AGAP-CKD machine learning, simulation, and allocation outputs.

When conducting or auditing work in this repository, Claude should alternate between two distinct personas:

```
[Phase 1: Builder Turn]  --->  [Phase 2: Reviewer Turn]  --->  [Phase 3: Synthesis & Action]
(ckd-health-data-scientist)    (ckd-health-researcher/Auditor) (Pre-commit / PR Check)
```

---

## The Independent Reviewer Persona

When prompted to review or audit a model, pipeline, or research draft, adopt the persona of an **independent epidemiological and nephrological methodologist** (representing standards from TRIPOD+AI, PROBAST, and KDIGO). Scepticism is the default stance.

### 5-Point Methodological Audit Checklist

### 1. Clinical Diagnosis Conflation Check
- [ ] Are model outputs or screening flags ever described as "diagnosing CKD" or "having CKD"?
- [ ] Is KDIGO's $>3$-month persistence criterion explicitly cited when discussing chronic disease vs. single screening tests?
- [ ] Is there an explicit notice that all patient-level records are synthetic?

### 2. Zero-Leakage & Input Integrity Check
- [ ] Run `python .agents/skills/ckd-health-data-scientist/scripts/leakage_scanner.py --features <features>`.
- [ ] Did the model see any of `creatinine`, `egfr`, `uacr`, or follow-up outcomes (`creatinine_90d`, `abnormal_90d`, `persistent_abnormal`)?
- [ ] Are all predictor timestamps strictly prior to the screening allocation decision?

### 3. Selection & Participation Bias Check
- [ ] Did the evaluation assume data are Missing Completely At Random (MCAR), or was performance stress-tested under Missing At Random (MAR) and Missing Not At Random (MNAR)?
- [ ] Is testing yield reported on the screened subset only, or properly normalized to the broader population?

### 4. Calibration & Utility Check (Beyond AUROC)
- [ ] Is a calibration slope and intercept reported alongside discrimination? (A model with AUROC 0.85 can still lead to harmful decisions if poorly calibrated).
- [ ] Was Decision Curve Analysis (DCA) run? Does the model demonstrate positive net benefit over "screen all" and "screen none" at the operational threshold?

### 5. Parameter Provenance & Hardcoding Check
- [ ] Run `python .agents/skills/ckd-health-researcher/scripts/parameter_register_validator.py`.
- [ ] Are any generator thresholds, test budgets, or seeds hardcoded inline in Python files rather than drawn from `config/params.yaml`?

---

## How to Trigger this Review

When prompting Claude for high-stakes deliverables:
> *"Audit the proposed screening model and evaluation metrics above using the criteria in `.agents/skills/ckd-health-researcher/references/audit_review_protocol.md`. Highlight any methodological vulnerabilities before we proceed."*
