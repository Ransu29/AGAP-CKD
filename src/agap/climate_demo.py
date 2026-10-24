"""Date-specific model previews using saved public climate inputs.

The preview changes only model-visible climate inputs. It never generates new
outcomes or reinterprets the historical outcome attached to a synthetic resident.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


CLINICAL_FEATURES = ["age", "female", "dm_report", "htn_report", "family_report", "outdoor_report"]
FEATURE_LABELS = {
    "age": "Age", "female": "Sex recorded as female", "dm_report": "Reported diabetes",
    "htn_report": "Reported hypertension", "family_report": "Reported family history",
    "outdoor_report": "Reported outdoor work", "hot_dry_score": "Community hot–dry conditions",
}
SNAPSHOTS = ("climate_daily.parquet", "climate_exposure.parquet", "climate_metadata.json", "model_climate.joblib")


def load_climate_preview(directory: Path):
    """Load only this project's run-local snapshots and locally trained model."""
    if not all((directory / filename).exists() for filename in SNAPSHOTS):
        return None
    metadata = json.loads((directory / "climate_metadata.json").read_text())
    daily = pd.read_parquet(directory / "climate_daily.parquet")
    exposure = pd.read_parquet(directory / "climate_exposure.parquet")
    exposure["cutoff"] = pd.to_datetime(exposure.cutoff).dt.normalize()
    if exposure.duplicated(["era5_cell", "cutoff"]).any():
        raise ValueError("Saved climate exposure contains duplicate cell/date records.")
    model = joblib.load(directory / "model_climate.joblib")
    return dict(daily=daily, exposure=exposure, metadata=metadata, model=model)


def complete_exposure(exposure):
    """A partial weather window cannot silently become an imputed climate score."""
    return exposure.complete.fillna(False).astype(bool) & np.isfinite(exposure.hot_dry_score)


def score_cohort(frame, clinical_model, climate_model=None):
    """Score saved resident inputs without changing the caller's data.

    Both models use the same residents and their own saved feature names. Rank 1
    is the highest score; stored tie draws resolve equal scores in ascending
    order. Existing derived scores/ranks are replaced so changing the available
    models cannot leave stale climate results. Without a climate model only the
    clinical score/rank columns are returned. Empty inputs have the same typed
    output columns and never call either model's prediction method.
    """
    score_columns = [f"{variant}_{measure}" for variant in ("clinical", "climate")
                     for measure in ("score", "rank")]
    scored = frame.drop(columns=score_columns, errors="ignore").copy(deep=True)
    models = {"clinical": clinical_model}
    if climate_model is not None:
        models["climate"] = climate_model
    for variant, model in models.items():
        if scored.empty:
            scored[f"{variant}_score"] = pd.Series(index=scored.index, dtype="float64")
            scored[f"{variant}_rank"] = pd.Series(index=scored.index, dtype="int64")
            continue
        scored[f"{variant}_score"] = model.predict_proba(scored[list(model.feature_names_in_)])[:, 1]
        order = np.lexsort((scored.tie_uniform.to_numpy(), -scored[f"{variant}_score"].to_numpy()))
        ranks = np.empty(len(scored), dtype=np.int64)
        ranks[order] = np.arange(1, len(scored) + 1)
        scored[f"{variant}_rank"] = ranks
    return scored


def preview_at_date(frame, exposure, cutoff, clinical_model, climate_model):
    """Score both models on the same residents, at one date, without mutation.

    Rank 1 is the highest probability. Stable stored tie draws resolve equal
    probabilities. Residents lacking a complete climate window are excluded from
    both ranking denominators rather than receiving imputed exposure. If no
    residents match, the return is an empty frame with typed score/rank columns.
    """
    cutoff = pd.Timestamp(cutoff).normalize()
    selected = exposure[pd.to_datetime(exposure.cutoff).dt.normalize().eq(cutoff)]
    if selected.duplicated("era5_cell").any():
        raise ValueError("A cell must have exactly one exposure record for the selected date.")
    selected = selected.loc[complete_exposure(selected)].set_index("era5_cell")
    preview = frame.loc[frame.era5_cell.isin(selected.index)].copy(deep=True)
    # Deliberately do not change the saved cutoff or any hidden outcome columns.
    preview["hot_dry_score"] = preview.era5_cell.map(selected.hot_dry_score)
    return score_cohort(preview, clinical_model, climate_model)


def model_contributions(model, person):
    """Exact additive log-odds contributions of value and missingness terms.

    This explains the fitted model relative to its standardized reference. It is
    not a causal effect, a medical interpretation, or a percent probability shift.
    """
    features = list(model.feature_names_in_)
    row = person.to_frame().T if isinstance(person, pd.Series) else person
    row = row[features].astype(float)
    transformer = model.named_steps["features"]
    transformed = np.asarray(transformer.transform(row))[0]
    terms = transformed * model.named_steps["model"].coef_[0]
    values = terms[transformer.output_indices_["values"]]
    missing = terms[transformer.output_indices_["missing"]]
    if len(values) != len(features) or len(missing) != len(features):
        raise ValueError("This explanation requires the saved numeric and missingness pipeline.")
    result = pd.DataFrame({
        "feature": features,
        "input": [FEATURE_LABELS[name] for name in features],
        "contribution": values + missing,
        "missing": row.iloc[0].isna().to_numpy(),
    })
    result.attrs["intercept"] = float(model.named_steps["model"].intercept_[0])
    return result
