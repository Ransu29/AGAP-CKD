# A guideline floor overrides the model

After the logistic regression sets a risk level, a fixed rule raises it:
- diabetes or high blood pressure (an explicit Yes or a "High" BP reading) → at least Medium;
- both, or either one with age 60 or older → High.

KDIGO 2024 and ADA call for kidney testing in people with diabetes and hypertension, and the 2026 Philippine Periodic Health Exam guideline targets testing at these groups. A model trained on simulated data could still put a young person with diabetes in Low. That would be false reassurance the app cannot defend. A reader of the code will see the model's output being overridden and may think it is a bug. It is deliberate.

## Consequences

- Model-quality numbers are reported for the model alone and for the model plus the floor, so the floor's effect is visible.
- On the analyst map, the share at Medium or High partly reflects how common diabetes and hypertension are in an area.
- "I don't know" enters the model as Yes but does not trigger the floor (still to be confirmed; see PRD v3 open questions).
