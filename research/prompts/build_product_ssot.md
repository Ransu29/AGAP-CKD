# Prompt: Document the Current AGAP-CKD Product and Architecture

Copy the prompt below into an agent session with access to this repository.

---

Act as a senior product manager and software architect. Inspect the AGAP-CKD repository and produce a Product Requirements Document (PRD) and an architecture document that accurately describe the current version.

The goal is to establish a clear reference for what the product currently does, how its features work, what data they use, and how the system is organized. Document the existing product rather than proposing a future version.

## Working instructions

- Follow applicable `AGENTS.md` instructions and locate the Git repository root.
- Document the current working tree. Record the documentation date, branch, commit, and whether relevant uncommitted changes are included.
- Inspect implementation, configuration, and supporting documentation before writing. Use current code and active configuration to establish implemented behavior; use the proposal and historical specifications as background.
- Create only the two requested documents. Preserve existing code, configuration, data, proposals, and historical documentation. Do not install dependencies, download data, execute tests, or run pipelines for this documentation task.
- Cite important descriptions with repository paths and function/class names or line references. Cite PDFs by filename and page when using them.
- Describe only behavior supported by inspected material. When a detail cannot be established, say it is unspecified rather than inventing it.
- Preserve distinctions between public data, synthetic data, simulated operations, and real integrations. Describe screening outputs using the terminology actually supported by the product.
- Keep the writing readable for product leads and developers. Define domain terms and explain technical details in relation to product behavior.
- Do not produce an assumption register, contradiction report, evidence-gap analysis, audit-coverage report, interview objectives, validation plan, roadmap, or feature recommendations.

## Material to inspect

Start with these sources, then follow their references into the implementation:

- `README.md`, `Makefile`, `pyproject.toml`, dependency files, and `app/README.md`.
- `research/decisions/baseline/[00] Project Proposal-1.pdf` and the software requirements PDF in the repository root.
- `feature_decisions.md`, `final_prototype_scope.md`, and relevant requirements errata and traceability documents.
- Current implementation and workflow documentation under `docs/`, including `prototype_plan.md`, `prototype_upgrade_spec_v2.0.md`, `screening_coordination.md`, `engine1_reporting_design.md`, `surveillance_design.md`, `data_contracts.md`, `data_sources.md`, and `synthesis_disclosure.md`.
- Application entry points and assets in `app/`, all relevant modules in `src/agap/`, pipeline scripts in `scripts/`, and configuration profiles in `config/`.
- Data manifests, `config/parameter_register.yaml`, accessible data schemas, and existing tests where they clarify implemented behavior. Do not claim tests pass merely because test files exist.

Avoid treating an old repository snapshot or a historical specification as a substitute for reading current files. Do not copy historical features into the PRD unless they exist in the current version.

## Deliverable 1: Current-version PRD

Write `research/ssot/PRD.md`, titled **AGAP-CKD — Current Product Requirements Document**. Include:

1. **Version and product overview:** documentation baseline, purpose, problem addressed, intended users and beneficiaries, product value, and current scope.
2. **User roles and use cases:** distinguish intended users from roles and permissions actually enforced by the application.
3. **Information architecture:** screens, tabs, navigation, shared context, primary actions, and where each capability is accessed. Include a Mermaid navigation diagram when useful.
4. **End-to-end user journeys:** document the actual sequence of actions, inputs, decisions, and outputs for each implemented workflow.
5. **Functional requirements and feature catalog:** assign stable identifiers such as `F-001`. For each meaningful feature, state the user purpose, entry point, preconditions, inputs, behavior/rules, outputs, persistence, configurable settings, and relevant error or missing-data behavior. Include implementation references and existing SRS identifiers where applicable.
6. **Data supporting the features:** explain each feature's data dependencies and where those data originate. Distinguish data used in decisions from data displayed for context. Link to the architecture document for detailed transformations.
7. **Models and decision behavior:** explain the implemented scoring, allocation, forecasting, comparison, and eligibility behavior in product terms, including how configuration profiles change behavior.
8. **Records, reports, and exports:** describe important entities, generated artifacts, export fields, saved records, revisions, and user-visible state transitions.
9. **Current operating requirements:** document implemented performance, offline behavior, privacy, reproducibility, accessibility, and reliability characteristics only where supported. Identify specified targets as targets rather than measured results.
10. **Scope boundaries and glossary:** briefly describe the current prototype's operational boundaries and define the terminology needed to understand it.

Discover features from the application and backend, rather than relying solely on a README list. Cover meaningful user-facing and background capabilities; avoid turning every helper function into a separate feature.

## Deliverable 2: Current-version architecture document

Write `research/ssot/ARCHITECTURE.md`, titled **AGAP-CKD — Current System Architecture**. Include:

1. **System context:** users, application boundary, external data providers, actual integrations, and local operating environment.
2. **Component architecture:** UI, domain modules, CLI/scripts, pipeline stages, configuration, storage, and reporting. Explain responsibilities and dependencies with repository paths.
3. **Execution paths:** how a local setup starts the app and runs the pipeline; key Make targets and entry points; how UI interactions reach domain logic.
4. **Data architecture:** entities, identifiers, relationships, schemas/contracts, storage formats and locations, lifecycle, revisions, and run provenance.
5. **Data-source and lineage catalog:** for each consumed source family, document publisher/source, URL or local artifact, represented time/geography, units/resolution where relevant, collection code, transformations, derived fields, and consuming features/models. Describe simulator-generated data and parameter sources explicitly. Mention reference documents separately from datasets actually consumed.
6. **Models and algorithms:** implemented model inputs/targets, preprocessing, training and evaluation partitions, scoring/threshold logic, allocation policies, forecasts, and parameter/configuration dependencies. Reference formulas or algorithms in their implementation.
7. **State and persistence:** session state, draft versus saved/approved plans, record transitions, persistence mechanisms, corrections, idempotency, and recovery behavior where implemented.
8. **Configuration and runtime modes:** compare the fixture, public, weather-preview, climate, fast, and full profiles where present. Explain which distinctions affect data, model behavior, output, or runtime.
9. **Cross-cutting behavior:** error handling, integrity checks, missingness, date/cutoff handling, reproducibility, offline assets, credentials handling, and concurrency constraints supported by the code.
10. **Diagrams and module map:** provide Mermaid system/component and end-to-end data-flow diagrams, plus a concise directory/module reference.

Keep one canonical explanation of each technical mechanism in this document and cross-link it from the PRD. Use the PRD's feature IDs when connecting components and data to product behavior.

## Final quality check and response

Check the documents against current code and configuration, make terminology consistent, and ensure that the main application workflows and pipeline capabilities are represented. Keep historical or future-only functionality out of the current-version specification. Explain profile-specific behavior wherever a general statement would be misleading.

Finish with links to the two documents and a short description of their scope. State that they were created through static repository inspection. Do not add separate audit or validation deliverables.
