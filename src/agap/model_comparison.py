"""Paired model comparisons on one immutable, fully climate-supported cohort.

Operational invitation changes are separate from simulator-only diagnostics.
Neither model is refitted here; both use the same allocation settings and draws.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from agap.demo import compare_plans, outreach_share

MODEL_LABELS = {"clinical": "Questionnaire only", "climate": "Questionnaire + climate"}


def comparison_export(decisions, run_id, active_model, settings):
    """Keep exported model changes tied to their actual synthetic planning context."""
    columns = ["resident_id", "municipality", "clinical_score", "climate_score", "clinical_invited", "climate_invited", "change"]
    output = decisions[columns].copy()
    output["run_id"], output["active_model"] = run_id, active_model
    output["budget_panels"], output["strategy"] = settings["budget"], settings["strategy"]
    output["outreach_share"] = outreach_share(settings)
    output["data_status"] = "Synthetic residents and outcomes; hypothetical service points; model comparison"
    return output


def invitation_changes(scored, clinical, climate):
    """Join by ID and project only operational fields, never medical truth."""
    ids = set(scored.resident_id)
    if scored.resident_id.duplicated().any():
        raise ValueError("Model comparison requires unique resident IDs.")
    for plan in (clinical, climate):
        if plan.resident_id.duplicated().any() or set(plan.resident_id) != ids:
            raise ValueError("Both model plans must cover exactly the same residents.")
    output = scored[["resident_id", "municipality", "clinical_score", "climate_score"]].copy()
    for variant, plan in (("clinical", clinical), ("climate", climate)):
        decisions = plan.set_index("resident_id")
        output[f"{variant}_invited"] = output.resident_id.map(decisions.invited).astype(bool)
    output["change"] = np.select(
        [~output.clinical_invited & output.climate_invited,
         output.clinical_invited & ~output.climate_invited,
         output.clinical_invited & output.climate_invited],
        ["Added with climate", "Removed with climate", "Invited by both"], default="Not invited by either")
    return output


def model_diagnostics(scored, bins=10):
    """Simulation-truth evaluation of current scores; never recalibrate on test data.

Fixed-width calibration bins are visual summaries, not clinical risk tiers.
Empty bins are omitted and every occupied bin carries its sample size.
"""
    labels = scored.y_true.to_numpy()
    if not len(labels) or not np.isin(labels, [0, 1]).all():
        raise ValueError("Simulation evaluation requires nonmissing binary truth.")
    metrics, calibration = [], []
    for variant, label in MODEL_LABELS.items():
        scores = scored[f"{variant}_score"].to_numpy(dtype=float)
        if not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1)):
            raise ValueError("Every compared resident requires a finite probability from both models.")
        classes = len(np.unique(labels)) == 2
        metrics.append(dict(model=variant, label=label, residents=len(labels),
                            auroc=roc_auc_score(labels, scores) if classes else np.nan,
                            auprc=average_precision_score(labels, scores) if classes else np.nan,
                            brier=brier_score_loss(labels, scores)))
        grouped = pd.DataFrame(dict(bin=np.minimum((scores * bins).astype(int), bins-1),
                                    predicted=scores, abnormal=labels.astype(float))).groupby("bin")
        points = grouped.agg(mean_score=("predicted", "mean"), abnormal_fraction=("abnormal", "mean"),
                             residents=("predicted", "size")).reset_index()
        points["model"], points["label"] = variant, label
        calibration.append(points)
    return pd.DataFrame(metrics), pd.concat(calibration, ignore_index=True)


def compare_models(scored, facilities, cfg, budget, strategy, outreach=.2):
    """Change only the model scores; cohort, constraints and random draws stay paired."""
    if "hot_dry_score" not in scored or not np.isfinite(scored.hot_dry_score).all():
        raise ValueError("Model comparison requires complete saved climate exposure for every resident.")
    diagnostics, calibration = model_diagnostics(scored)
    plans = {variant: compare_plans(scored, facilities, scored[f"{variant}_score"].to_numpy(),
                                    cfg, budget, strategy, outreach) for variant in MODEL_LABELS}
    decisions = invitation_changes(scored, plans["clinical"]["proposed"], plans["climate"]["proposed"])
    evaluation = pd.DataFrame([dict(model=variant, label=MODEL_LABELS[variant],
                                   **{key: plan["proposed_summary"][key] for key in (
                                       "invitations", "completions", "positives_detected", "positives_not_detected",
                                       "eligible_positives")}) for variant, plan in plans.items()])
    return dict(plans=plans, decisions=decisions, evaluation=evaluation,
                diagnostics=diagnostics, calibration=calibration)
