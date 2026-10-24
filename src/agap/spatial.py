"""GEO-04 spatial sensitivity: the same residents and outcomes at a coarser H3 resolution.

Nothing is re-simulated. Deployment residents keep their hidden outcomes, reporting, completion
draws and model scores; only their location moves from the H3 resolution-8 cell centre to its
resolution-7 parent centre. Every allocation policy is re-run with the same seeds, so differences
come from geographic resolution alone (the modifiable areal unit problem). Verified barangay
boundaries, the SRS's other sensitivity representation, are not available.
"""
from __future__ import annotations

import json

import h3
import numpy as np
import pandas as pd

from agap.experiment import allocate_policy, allocation_metrics, allocation_scores, atomic_text, distance_matrix, pipeline_policies

RESOLUTIONS = {8: "h3", 7: "h3_parent"}
RANK_METRIC = "positives_detected"


def located_at(frame, facilities, resolution):
    """The same residents placed at the centre of their cell at this resolution."""
    if resolution not in RESOLUTIONS:
        raise ValueError(f"Spatial sensitivity supports H3 resolutions {sorted(RESOLUTIONS)}")
    located = frame.copy()
    areas = located[RESOLUTIONS[resolution]]
    centres = {area: h3.cell_to_latlng(area) for area in areas.unique()}
    located["latitude"] = areas.map(lambda area: centres[area][0])
    located["longitude"] = areas.map(lambda area: centres[area][1])
    # Reference distance for the assignment penalty in allocate_policy; base completion stays as simulated.
    located["nearest_distance_km"] = distance_matrix(located, facilities).min(axis=1)
    located["area"] = areas
    return located


def sensitivity(cfg, frame, facilities, scores):
    rows = []
    for resolution in sorted(RESOLUTIONS, reverse=True):
        located = located_at(frame, facilities, resolution)
        for policy, share in pipeline_policies(cfg):
            records = allocate_policy(cfg, located, facilities, scores, policy, share, cfg["seed"] + 100)
            metric = allocation_metrics(records, cfg).query("subgroup == 'all'").iloc[0]
            reached = located.loc[records.invited.to_numpy(), "area"].nunique()
            rows.append(dict(resolution=resolution, policy=metric.policy, areas=located.area.nunique(), areas_reached=reached,
                             share_of_areas_reached=reached / located.area.nunique(),
                             access_feasible=int(records.access_feasible.sum()),
                             **{key: metric[key] for key in ("invitations", "completions", "positives_detected",
                                                              "positives_per_100_completed", "completion_coverage",
                                                              "access_excluded_positives")}))
    return pd.DataFrame(rows)


def ranking_summary(table):
    """Policy order by positives detected at each resolution, and whether it changes."""
    order = {int(resolution): group.sort_values([RANK_METRIC, "policy"], ascending=[False, True]).policy.tolist()
             for resolution, group in table.groupby("resolution")}
    detected = table.pivot(index="policy", columns="resolution", values=RANK_METRIC)
    return dict(rank_metric=RANK_METRIC, policy_order=order, ranking_changed=len({tuple(v) for v in order.values()}) > 1,
                largest_change_in_positives_detected=int((detected[7] - detected[8]).abs().max()))


def spatial(cfg, directory):
    frame = pd.read_parquet(directory / "deployment_hidden.parquet")
    facilities = pd.read_parquet(directory / "facilities.parquet")
    predictions = pd.read_parquet(directory / "predictions.parquet")
    scores = allocation_scores(cfg, predictions, frame)
    table = sensitivity(cfg, frame, facilities, scores)
    table.to_csv(directory / "spatial_sensitivity.csv", index=False)
    summary = ranking_summary(table)
    atomic_text(directory / "spatial_sensitivity.json", json.dumps(dict(
        summary, residents=len(frame), resolutions=sorted(RESOLUTIONS, reverse=True),
        rule="Same deployment residents, outcomes, completion draws, scores and seeds; only location moves from the "
             "H3 resolution-8 centre to its resolution-7 parent centre (GEO-04).",
        limitation="Barangay-level sensitivity needs verified barangay boundaries, which are not collected."), indent=2))
    return table, summary
