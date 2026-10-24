# Optional simulation and replay extensions

**Research date:** October 23, 2026. **Status:** candidates for discussion; not approved features. Primary-source listings and study documentation were inspected. Dataset files were not downloaded or inspected; no models, tests or pipelines were run.

## Purpose and boundaries

AGAP's leading user is a public-health analyst. Population findings can motivate research questions and subgroup comparisons in separate patient datasets; they cannot automatically modify individual predictions. The extensions below investigate model behavior and uncertainty. They do not presume staffing shortages, estimate treatment effects, or attach Philippine weather to unrelated foreign patient records.

## Candidate extensions

### 1. Historical replay with prediction-horizon comparison

**Question:** How does predictive performance change as more information becomes available, or as the forecast reaches farther ahead?

Progressively reveal a held-out dialysis session, display a prediction using only information available at that moment, and subsequently reveal the recorded outcome. Compare a simple last-observation baseline with a fitted model. Report error by horizon for blood-pressure prediction; for event prediction, report discrimination, calibration and advance notice under an explicitly defined event and horizon.

**Published foundation:** the HEMOBP descriptor documents linked patient, session and timestamped measurement tables, including blood pressure and dialysis settings. It makes temporal replay plausible, but irregular measurements and interventions complicate interpretation. Dataset access remains unconfirmed. [Lin et al., 2019](https://www.nature.com/articles/s41597-019-0319-8.pdf)

**Our proposal:** a replay interface is an AGAP experiment, not a published validation result. Patient identifiers, ordered timestamps and pre-outcome inputs must survive in the release. Separate patients between development and evaluation for new-patient claims; distinguish that from forecasting later sessions in known patients. No post-event measurements may enter an advance forecast.

### 2. Missing or delayed measurement stress test

**Question:** How fragile is a research model when selected inputs are missing or arrive late?

Apply reproducible masking or delays to held-out predictors, then compare performance, prediction changes and the proportion of cases where the system withholds an estimate. Include a simple baseline and explicit missingness handling; fit preprocessing only on development data. Random masking and block/dropout scenarios should be labeled imposed experimental conditions, not measured local missingness rates.

**Data prerequisite:** temporal delay needs real timestamps. Baseline-only CKD data can support feature-removal stress tests, not genuine monitoring-delay simulation. Mendeley's dialysis release explicitly retains valid complete sessions; artificial masking tests robustness within that selected cohort, not performance among all originally incomplete sessions. [Gomez-Pulido, 2021](https://data.mendeley.com/datasets/7kmtsmsgfw/1)

**Interpretation:** removing an input demonstrates information dependence, not that measuring it improves clinical outcomes.

### 3. Threshold and research-flag trade-offs

**Question:** What happens to false flags, missed events and total flagged cases when the research threshold changes?

Using held-out predictions, display counts per 100 eligible cases alongside sensitivity, specificity, positive predictive value and calibration. For longitudinal sessions, define whether flags are per measurement or per session and avoid counting repeated flags as independent events. Thresholds remain exploratory; no slider should prescribe patient care.

**Methodological foundation:** decision-curve methods evaluate explicit benefit–harm trade-offs; they require a specified action and justified threshold range. Until those exist, AGAP should show descriptive flag trade-offs, not claim clinical utility or a clinically optimal threshold. [Vickers et al., 2016](https://www.bmj.com/content/352/bmj.i6)

### 4. Population-composition sensitivity

**Question:** Do aggregate model results change when the evaluation sample contains different supported proportions of age or other observed groups?

Compare subgroup performance and explicitly reweighted source-cohort scenarios, reporting group counts, uncertainty, weight concentration and unsupported combinations. This creates a link from population findings to a research question without merging unrelated people.

**Boundary:** a hypothetical age mix is not a representative Filipino cohort. Matching a few marginal distributions cannot fix unmeasured differences, missing groups or incompatible clinical practice. Reweighting cannot create Philippine external validation. Prediction-model guidance distinguishes subgroup/context evaluation from performance in genuinely new populations. [TRIPOD-Cluster explanation, 2023](https://www.bmj.com/content/380/bmj-2022-071058)

### 5. Pre-dialysis horizon explorer

**Question:** How do observed progression patterns and estimated probabilities differ across supported follow-up horizons?

CKD-ROUTE's repository identifies progression as over 50% eGFR loss or dialysis initiation and reports follow-up and outcomes. Inspect the workbook for event times, censoring and repeated observations before deciding between survival analysis and dynamic replay. [Iimori et al., 2018, dataset](https://datadryad.org/dataset/doi:10.5061/dryad.kq23s)

A horizon selector can compare appropriately evaluated time-to-event estimates. It cannot extrapolate arbitrarily far beyond follow-up, invent serial laboratory trajectories, or treat censored participants as event-free forever. Competing death requires appropriate consideration. This is risk-over-time research, not a treatment-effect simulator.

## Shortlist for discussion

**First:** missing-input stress tests plus descriptive threshold trade-offs; these can work without rich temporal data. **Conditional visual demonstration:** historical dialysis replay, only after confirming timestamps, identifiers and input timing. **Secondary:** pre-dialysis horizons and composition sensitivity if the released fields support them. No option currently supports heat-driven disease forecasts or causal treatment sliders. Begin with one model and one extension rather than promising all five.
