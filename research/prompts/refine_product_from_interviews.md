# Prompt: Refine AGAP-CKD After Stakeholder Interviews

Use this prompt in an agent session with access to the repository. It produces a proposed product direction and specifications; it does not implement changes.

---

Act as a senior product strategist, public-health product manager, data-science lead, and software architect. Refine AGAP-CKD's existing product direction using its current implementation, submitted proposal, recent nurse interviews, personal concept notes, and competition primer.

Produce a coherent longer-term proposition and a smaller, credible competition version. Connect the citizen experience, health-worker workflow, and aggregated community analysis through a clear early-detection purpose. Make reasoned decisions and explicitly note uncertainty; do not stop to seek further clarification or approval.

## Product-lead decisions already established

Treat these as confirmed preferences, not questions to reopen:

- **Primary problem:** helping people at risk get checked earlier for kidney-health concerns.
- **Primary audience:** the general public, especially people with relevant risk factors. Citizens must be informed and supported, not diagnosed by the product.
- **Professional audience:** appropriately authorized health workers and LGU personnel, using aggregated population information to identify patterns, explore groups and simulate or plan interventions.
- **Secondary journey:** supporting people already diagnosed, as a connected longer-term capability. Keep early detection as the leading proposition.
- **Change boundary:** refine the existing AGAP-CKD direction. Preserve useful work where it serves the proposition; existing features are not automatically mandatory.
- **Climate:** a supporting element, definitely not the primary driver. Determine its appropriate role rather than assuming it must remain a clinical predictor.
- **Data:** synthetic citizen-level data is acceptable for the demonstration. Real citizen data and institutional partnerships are unconfirmed. Design explicitly for a real-world cold start.
- **Planning horizon:** a longer-term product direction with a smaller competition version.
- **Open citizen action:** the product lead has not yet chosen the concrete next step after a citizen uses the product. Recommend one based on the evidence and explain its dependencies; label it as your recommendation.
- **Decision authority for this task:** proceed without approval checkpoints. State what is uncertain and what you assumed. Do not invent commitments, resources, access agreements, or stakeholder endorsements.

## Read these sources before proposing changes

Locate the Git root and follow applicable `AGENTS.md` instructions. Read:

1. `research/validation/interviews/Minutes (1).pdf`.
2. `research/validation/interviews/Dialysis-Nurse-Interview-Notes.pdf`.
3. `research/decisions/concepts/PersonalNotes.md`.
4. `research/decisions/baseline/[00] Project Proposal-1.pdf`.
5. `research/evidence/competition/[00] Primer.pdf`, especially PDF pages 10–14.
6. `research/ssot/PRD.md` and `research/ssot/ARCHITECTURE.md`.
7. Relevant current code, configuration and product documents to check what is actually available for reuse.

Record the date, branch and commit used. Treat existing SSOT documents as a current-version baseline and confirm consequential implementation details against code. Read the personal notes as supplied; do not invent missing earlier sections or assume every listed idea is a requirement.

## Interpret the interviews carefully

The two PDFs describe **one joint interview with two nurses**, not independent corroborating interviews. The minutes contain paraphrased responses; the companion document adds the team's interpretation and proposed implications. Distinguish these from each other and from the product lead's ideas.

- Attribute interview insights by role. The notes say permission to name the participants or quote them publicly has not been confirmed. Do not turn paraphrases into verbatim quotes.
- Their direct work concerns dialysis patients at a Batangas center. Their observations can inform the proposition, but do not establish population-level screening needs, RHU practice, nationwide policy, or prevalence.
- Do not infer that community screening is absent because it was not described, that urine testing is unnecessary because uACR was not discussed, or that screening access is adequate because dialysis centers were described as accessible.
- Do not convert unconfirmed creatinine units or reported dialysis thresholds into product decision rules. Interview descriptions of eGFR, testing, financing, heat and treatment are participant accounts requiring appropriate external confirmation before becoming clinical or policy facts.
- The nurses' views neither establish nor refute a causal climate–kidney relationship. Assess whether climate belongs in contextual education, population analysis, a labeled simulation, or another supporting role.
- Recognize both practical observations and stated wishes, including patient awareness/education, late presentation, treatment refusal, follow-up calls, monthly laboratory work and fragmented information. Explain their relevance without assuming the interview validated AGAP-CKD itself.

Cite interview claims by filename and PDF page; personal notes by heading. Cite current behavior with repository paths and symbols. For new clinical, policy or institutional claims needed to justify the proposition, verify current primary sources where browsing is available. If verification is unavailable, mark the claim unverified and do not build a firm requirement on it. Format external references in APA 7, with working source links and relevant dates.

## Validation layer and methodology

Use **evidence-informed product discovery with requirements traceability**: synthesize the interview, identify opportunities, compare candidate refinements, check consequential claims against appropriate evidence, and translate the selected direction into testable requirements. This is the working method for this task, not a claim that the product or its clinical models are validated.

Apply this sequence before finalizing the proposed specifications:

1. **Extract claims without endorsing them.** Distinguish participant observations, interviewer interpretations, personal ideas, current implementation, clinical assertions, institutional assertions, and proposed product benefits. Cite the originating page, heading or symbol. Treat the two interview documents as one evidence source.
2. **Check evidence against the type of claim.** Use the source hierarchy below. Look for evidence that narrows or challenges the proposition, not only evidence that supports it. Check population, setting, date, definitions and outcome before transferring a finding to this product.
3. **Reconcile the claim.** Mark it supported within a stated scope, supported only with qualification, contradicted by cited evidence, unverified, or a proposed hypothesis. Silence in an interview is not contradiction. Do not assign numerical confidence without a defensible basis.
4. **Trace the design decision.** For every consequential requirement, analytical method and institutional integration, identify the user problem, supporting evidence, existing implementation if any, and proposed observable acceptance criterion. A feature recommendation remains a recommendation even when its motivating problem has evidence.
5. **Check the competing explanations.** Could late presentation reflect barriers other than lack of awareness? Would an education interface actually change screening behavior? Is a resource constraint demonstrated for the intended setting? Does an analytical result depend on an assumption built into the simulator? State what the available evidence can and cannot distinguish.
6. **Proceed with explicit limits.** Unsupported clinical rules must not become firm product instructions. Unconfirmed integrations remain conditional proposals. Recommend an alternative or qualified requirement and continue; do not request approval or invent validation results. Put concise evidence-status notes next to the affected requirements in the two documents.

### Match sources to the validation question

| Question | Primary sources to consult | What they can establish |
|---|---|---|
| What constitutes appropriate kidney-health assessment and understandable screening information? | Final published [KDIGO CKD guidance](https://kdigo.org/guidelines/ckd-evaluation--and-management/), including the [2024 guideline](https://kdigo.org/wp-content/uploads/2024/03/KDIGO-2024-CKD-Guideline.pdf); [NIDDK's UACR/GFR reference](https://www.niddk.nih.gov/health-information/professionals/advanced-search/quick-reference-uacr-gfr). Check for applicable final updates; do not treat a public-review draft as adopted guidance. | Clinical definitions, test roles and interpretation boundaries. They do not validate AGAP's predictions, wording comprehension, or local service availability. |
| How could the product fit Philippine primary care? | Current DOH administrative orders and implementing guidance, including CKD prevention/control and PhilPEN where relevant; official [PhilHealth YAKAP issuances](https://www.philhealth.gov.ph/yakap/issuances/) and applicable circulars/annexes. | Published responsibilities, benefits, eligibility and program conditions. A policy or register does not establish that a particular facility currently supplies a test or agrees to integrate. |
| How common are relevant conditions and who is represented? | Definition-matched DOH/FNRI survey reports and PSA population/statistical releases; WorldPop documentation for the modeled population actually used. Prefer original tables and methods to news summaries. | Population estimates and their denominators, dates and limitations. Aggregate prevalence cannot establish individual correlations or representative coverage of registered users. |
| What can the interviews establish about workflow and needs? | The supplied minutes, clearly attributed paraphrases and contextual notes; any separately supplied direct confirmation from intended users/service providers. | Experiences and reported needs in the participants' setting. Citizen desirability, RHU workflow, and institution-wide practice remain unconfirmed unless directly studied. |
| Are geographic/climate inputs and methods appropriate? | Dataset publishers' metadata and methods: geoBoundaries, WorldPop, Copernicus/ECMWF; original peer-reviewed studies for any proposed climate-health association. | Source meaning, coverage, processing and study-specific associations. Weather-source validity does not establish clinical predictive value or causation. |
| Is the proposed analytical approach justified? | Original method papers, applicable model-reporting/evaluation guidance, dataset documentation, and current code/artifacts. Assess real-data external validation separately from simulator evaluation. | Method suitability and reproducible implementation evidence within the available data. Synthetic discrimination/calibration cannot establish performance in real citizens. |
| Does the competition slice satisfy the brief? | `research/evidence/competition/[00] Primer.pdf` and any verified official organizer amendments. | Submission requirements and judging criteria, not product effectiveness or a guaranteed competition outcome. |

Use official NPC guidance and applicable Philippine law if proposing specific personal-data sharing or consent requirements. Distinguish those published requirements from proposed technical controls; do not invent institutional permission.

### Keep different kinds of validation separate

- **Clinical-content checking:** compare proposed educational statements and screening terminology with current guidance; identify content requiring qualified clinical review before real deployment.
- **Problem/workflow evidence:** describe what was learned from the interview and what remains a product hypothesis. An interview is not a usability or outcome trial.
- **Technical verification:** inspect whether current code implements the claimed behavior. Existing test definitions and saved results are not fresh test execution; do not run tests for this specification task.
- **Analytical evaluation:** specify baselines, leakage controls, held-out evaluation, missingness handling, calibration/uncertainty and subgroup checks appropriate to each proposed method. Distinguish implemented checks from proposed evaluation, and avoid unjustified thresholds.
- **Real-world product validation:** specify how screening follow-through, comprehension and professional decision usefulness could later be assessed with intended users; describe these as future evaluation, not completed validation.

Do not create a separate validation report or claim registry. Integrate the evidence-to-requirement links and material uncertainties into the proposed PRD/architecture. If browsing or a needed source is unavailable, name the specific unverified claim and bound the design accordingly.

## Reason through the refined proposition

### 1. Define the problem, audience and action

Briefly compare a small number of plausible refinements, then select and develop one. Explain what evidence and product-lead preferences favor it. Avoid combining every idea into an all-purpose health platform.

Define the primary citizen segment, the recurring situation that brings them to the product, what they learn, and the concrete action the product helps them take. Distinguish awareness, screening eligibility, screening priority, completed screening, and diagnosis. Do not equate a questionnaire score with disease detection.

Explain the corresponding health-worker/LGU task and decision. Specify who would act on an aggregate pattern and how the citizen journey connects to that action. Treat any proposed institutional responsibility or partnership as a dependency unless confirmed. Distinguish current Laguna implementation from the Batangas interview setting; recommend a geographic scope without silently assuming transferability or a committed pilot partner.

Place the diagnosed-patient journey in an explicit secondary scope. Define its relationship to early detection without making comprehensive disease management part of the immediate competition promise.

### 2. Make the data science purposeful and rigorous

The primer judges data acquisition, methodology, technical validity, analytical depth, findings, real-world application, reproducibility and communication. It does not mandate climate prediction, clustering, or a specific machine-learning algorithm. Assess candidate techniques by the decision they support and the data actually available.

For each retained or proposed analytical component, specify:

- The decision/question, unit of analysis and intended user.
- Available versus hypothetical inputs and their provenance, timing and missingness.
- Method, comparison baseline, expected output, evaluation design and relevant metric.
- What the analysis can establish, and what synthetic outcomes cannot establish.
- How the output informs a citizen action, worker task or population-level decision.

Use clustering only if its inputs, interpretation and actionability justify it; do not force it into the design. Keep aggregate patterns distinct from individual clinical risk. Separate simulated allocation/coverage results from demonstrated health outcomes. Avoid selecting evaluation metrics merely because they make the project look successful.

Reconsider existing scores, allocation policies, climate analysis and surveillance in this context. A simulation with an assumed climate effect cannot validate that effect. A real-weather input does not make synthetic-label performance clinical validation.

### 3. Design for cold start and Philippine service context

Describe what can function with zero real registered citizens and no confirmed institutional data feed. Explain what public information and carefully scoped voluntary inputs could support initially, what remains unavailable, and how behavior changes as data accumulates. Never silently use demonstration records in real population counts or treat absent citizen reports as negative health findings.

Distinguish public-data community context from registered-user aggregates; define denominators, data period, completeness and represented population. Specify whether sparse groups suppress, aggregate or withhold a display rather than implying representative patterns from a few users.

Separate citizen-entered information, staff-verified results, derived estimates and synthetic records. Describe suitable permission boundaries for proposed professional interfaces and limited aggregate access. Current demo staff labels are not an authorization system. Institutional record sharing and integration must remain proposed unless actually available.

Explain how the product could fit existing Philippine services, using verified evidence for specific program responsibilities or coverage claims. Do not assume the LGU is entitled to identifiable center records or that a facility register confirms test capability, available capacity or a referral partnership.

### 4. Fit the competition version to the existing build

Use the primer's actual requirements. It lists an October 24, 2026, 11:59 PM submission, a complete repository, a deck of at most 20 slides including references/appendices, and a video of at most three minutes. Note any verified organizer update that changes these constraints; otherwise identify the primer as the date source.

Choose a small, coherent demonstration with a visible citizen action, a connected professional decision, and reproducible data-science results. Map its requirements to existing PRD feature IDs F-001–F-026 and code. Classify each proposed change as reuse, revise, add, or leave out of this version. Do not confuse existing functionality with proposed work or promise completion by an unverified engineering estimate.

Keep longer-term integrations and patient-support capabilities visible as later scope, with dependencies. Explain how the competition slice demonstrates the direction without pretending those capabilities already operate. State how its artifacts address the submission rubric and support a clear three-minute narrative; do not write the deck or video script.

## Produce exactly two proposed specifications

Write to `research/decisions/proposed/PRD.md` and `research/decisions/proposed/ARCHITECTURE.md`. Preserve the current-version SSOT, interview files, submitted proposal, and existing implementation. Do not install dependencies, run tests/pipelines, download datasets, or implement product changes. Source browsing is permitted for the verification described above.

**Proposed PRD:** include the recommended proposition and rationale; primary/secondary users; value and intended outcomes; citizen and professional journeys; information architecture; functional requirements; purposeful analytical components; cold-start behavior; longer-term direction; a clearly bounded competition scope; a current-feature-to-proposed-feature mapping; success measures; and concise unresolved questions/assumptions beside the affected decisions.

**Proposed architecture:** describe the architecture supporting those requirements, reusing the present code where appropriate. Include component and data-flow diagrams, data/source lineage, entities and consent/permission boundaries, aggregate versus individual/synthetic data handling, analytical execution paths, cold-start modes, proposed external interfaces/dependencies, and the difference between competition implementation and longer-term architecture. Cross-reference PRD requirement IDs and current code. Mark every component as existing, revised, or proposed.

Both documents must be labeled **proposed**, include source references, and distinguish product-lead decisions, interview accounts, verified external facts and your recommendations. Keep uncertainties concise and actionable rather than creating a separate audit report. Recommend the best direction you can support; do not halt at a list of options.

Before finishing, check that early detection leads, climate supports rather than dominates, the citizen is informed rather than diagnosed, professional outputs serve a specified decision, cold start requires no imaginary data/partnership, and the competition scope retains meaningful data science. Finish with links to the two files, the recommended proposition, the competition slice, and the most consequential uncertainties.
