---
status: proposed (confirm the citizen app is a web app)
---

# One offline-capable web app serves every channel

The field health worker's tablet runs the citizen web app as an offline progressive web app (PWA). Checks are stored on the device and synced when online. The SMS backend calls the same scoring code. The PRD requires that a risk level mean the same thing on every channel. Ready-made field tools (ODK, KoBoToolbox) would mean re-writing the scoring and the guideline floor in form formulas, giving two copies of the rules that would drift apart.

## Considered options

- **KoBoToolbox / ODK Collect.** Mature offline sync, fast to set up, and used in Philippine community surveys. Rejected because the scoring would be duplicated. It remains the fallback if the citizen app turns out not to be a web app.
- **CommCare / DHIS2 Android.** Strong case tracking, but too heavy to configure for the prototype.

## Consequences

We build sync ourselves: a waiting-to-sync counter and a sync button now; conflict handling, retries and encryption at rest in Phase 2.
