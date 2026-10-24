# AGAP-CKD Product Research

Language for the proposed analytical direction and its intended beneficiaries. These definitions describe the domain; they do not establish implemented features or validated model performance.

## Language

**Public-health analyst**:
The intended primary user of the proposed analytical system, examining population evidence and its implications for further investigation.
_Avoid_: Citizen user, treating clinician (as interchangeable roles)

**Population analysis**:
Analysis of defined groups and areas using appropriately scoped health, demographic and service information. A group-level pattern is not an individual patient finding.
_Avoid_: Individual diagnosis, individual risk score

**No known CKD diagnosis**:
A person's state when a CKD diagnosis is not known from the available information; it does not establish the absence of disease.
_Avoid_: Healthy, CKD-free

**Pre-dialysis CKD**:
Diagnosed CKD before dialysis treatment; distinct from both no known diagnosis and receiving dialysis.
_Avoid_: Undiagnosed CKD

**Dialysis research demonstration**:
A supporting investigation of dialysis-related observations and predictions within a specified research dataset, without implying live clinical use.
_Avoid_: Deployed warning system, treatment recommendation

**Research question**:
A question motivated by a population finding and examined using a separately identified research dataset. Motivating a question does not establish that the same relationship holds for individual patients.
_Avoid_: Confirmed relationship, validated clinical rule

**Supporting prediction study**:
An empirical investigation of a defined patient outcome and horizon that supports the main analytical experience. Its source population and evaluation limits remain distinct from the population analysis.
_Avoid_: Population-derived patient score

**Optional simulation**:
An additional exploration of explicitly defined hypothetical conditions, separate from observed findings and evaluated predictions.
_Avoid_: Demonstrated intervention benefit, observed future outcome

**Public-data-anchored population scenario**:
A fictional population constrained by specified published statistics, with unresolved relationships varied explicitly. Its outputs describe plausible conditions under those assumptions, not observed local people or disease counts.
_Avoid_: Observed population, validated digital twin

**Synthetic training augmentation**:
Adding artificially generated records to a model's training data. Its predictive benefit is established only through comparison with appropriate baselines on separate observed evaluation data.
_Avoid_: New independent observations, guaranteed accuracy improvement

**Risk-factor overlap**:
The proportion of a defined population with two or more specified risk factors together. Separate percentages for each factor do not determine this joint proportion.
_Avoid_: Sum of prevalences, CKD prevalence
