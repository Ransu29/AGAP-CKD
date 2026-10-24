# Product Discovery Workflow for AGAP-CKD

## Is this how strong product teams work?

There is no single workflow used by every top product manager. Strong product teams tend to share a few practices: they start with an outcome and user need, keep learning from users during delivery, test assumptions before committing to expensive work, and use evidence to guide iteration. Teresa Torres describes continuous discovery as recurring customer interviews plus assumption testing around a clear outcome. GOV.UK's service guidance similarly recommends understanding user needs before settling on a solution, prototyping early, and continuing research through delivery. SVPG describes this as discovering a solution worth building before scaling delivery.

For AGAP-CKD, use these as principles, not a process ceremony. This is a health-adjacent prototype with simulation data. Product research can validate workflows, comprehension, feasibility, and stakeholder needs; it cannot validate clinical effectiveness or real-world health outcomes without appropriate clinical evidence and governance.

## The working loop

1. **Choose one outcome to improve.** Write a user-facing outcome, its beneficiary, and a measure. Keep the measure honest about what the prototype can observe. Candidate outcome to validate: *health coordinators can understand and review a transparent, capacity-limited screening plan*. This is a hypothesis, not a confirmed user need.
2. **Learn the current workflow.** Identify who does the job, what triggers it, what they do today, where delays or uncertainty occur, and what constraints matter. Include operational staff and people who support or receive the service; do not assume one persona represents everyone.
3. **Map opportunities before features.** Group observed needs, workarounds, and pain points under the chosen outcome. For each opportunity, retain a link to its evidence. Keep proposed solutions as options, not requirements.
4. **Rank assumptions by risk.** Record what must be true for an idea to work: user value, usability/comprehension, operational fit, data validity/coverage, feasibility, privacy, and safety. Prioritize assumptions that are both uncertain and consequential.
5. **Run the cheapest credible test.** Use interviews or workflow observation for problem understanding; paper/clickable prototypes for comprehension and usability; synthetic-data walkthroughs for workflow fit; and code experiments for technical/data feasibility. State the question, method, participants or test data, success/failure signal, limitations, and next decision before the test.
6. **Decide and update the product.** Record what was learned, what remains uncertain, and whether to proceed, revise, retest, or stop. Update the opportunity map and the relevant product/technical decision documents. Convert only validated next steps into issues or pull requests, each linked back to the evidence and outcome.
7. **Check whether the change helped.** After implementation, review the chosen measure and user feedback. Keep model or simulation metrics separate from evidence of user benefit.

## Repository integration

Keep `research/` as the source for discovery evidence and product decisions. Use this lightweight layout as work accumulates:

```text
research/
  README.md                    # directory guide and source index
  product_workflow.md          # this workflow
  validation/interviews/       # supplied stakeholder accounts and team synthesis
  evidence/competition/        # competition primer; add other evidence topics as needed
  decisions/baseline/          # submitted proposal; preserve original
  decisions/concepts/          # personal ideas, distinct from findings
  decisions/proposed/          # proposed product and architecture specifications
  ssot/                        # current implementation specifications
  prompts/                     # reusable research/specification instructions
```

Create `market/` and `templates/` when alternatives research or reusable templates are added. See [the research index](README.md) for current files.

Use dated, descriptive filenames, such as `2026-10-22-coordinator-workflow-interviews.md`. Every finding should distinguish **observed**, **reported**, **inferred**, and **assumed**; include source/date, method, sample or scope, limitations, and a link to the related decision or code issue. Keep identifiable health information, contact details, recordings, and consent forms out of Git. If research with people is planned, first follow the team's applicable ethics, consent, and data-handling process.

Connect discovery to existing project records rather than making parallel specifications:

- Treat the submitted proposal as the historical starting point.
- Update [`final_prototype_scope.md`](../final_prototype_scope.md) when prototype boundaries change.
- Update [`feature_decisions.md`](../feature_decisions.md) when a product or requirement choice is made.
- Update [`docs/prototype_plan.md`](../docs/prototype_plan.md) for implementation status, model/data limitations, and next technical work.
- Link relevant workflow findings to [`docs/screening_coordination.md`](../docs/screening_coordination.md) and the relevant `src/agap/`, `app/`, or `tests/` changes.

Each Git issue or pull request should state the user problem, evidence link, expected outcome, and acceptance check. A PR should also say how it changes (or preserves) synthetic-data labeling, clinical claims, privacy, and model/data assumptions when relevant.

## A sustainable cadence

For a small team, start with one short weekly review: revisit the outcome, discuss new evidence, select the riskiest assumption, and decide the next test or delivery slice. Talk with a user or operational stakeholder regularly when access permits; otherwise explicitly label desk research and internal opinions as weaker evidence. Share concise findings with the whole team. Adjust the cadence to access and workload; do not manufacture weekly research activity when there is no meaningful question to test.

## Useful source guidance

- Teresa Torres, [Discovering Solutions: Quickly Determine Which Ideas Will Work](https://www.producttalk.org/discovering-solutions/) — outcome-led opportunity mapping, generative interviews, and evaluative assumption tests.
- GOV.UK Service Manual, [Understand user needs](https://www.gov.uk/service-manual/service-standard/point-1-understand-user-needs) — research user problems, test assumptions early, and use prototypes.
- GOV.UK Service Manual, [Learning about user needs](https://www.gov.uk/service-manual/user-research/start-by-learning-user-needs) — research throughout development; treat non-user opinions as assumptions to validate.
- GOV.UK Service Manual, [Making prototypes](https://www.gov.uk/service-manual/design/making-prototypes) — choose prototypes that answer the question and discard weak concepts cheaply.
- Silicon Valley Product Group, [Build to Learn vs Build to Earn](https://www.svpg.com/build-to-learn-vs-build-to-earn/) — distinguish discovery of a solution worth building from delivery at scale.
