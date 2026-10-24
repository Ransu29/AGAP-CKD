"""PRD v3 risk check for one person: answers -> risk level, next step, reasons, tips and facilities.

Every channel (app, field tablet, SMS) scores with :func:`score_frame`, the same function the analyst
view uses for its simulated checks, so a risk level means the same thing however it was collected
(ADR 0003). Scoring uses the frozen risk-level model and the cut-offs saved with its run, then the
guideline floor (ADR 0002). Heat never enters the level (ADR 0001); it only triggers an advisory card.

The service returns codes and dates, not sentences: each channel words them in its own copy. The
model's probability is never returned, because the score is never shown to citizens.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from agap.simulate.risk_check import DONT_KNOW
from agap.triage import LEVELS, encode_features, floored, guideline_floor, model_levels

AGE_GROUPS = ("18-39", "40-49", "50-59", "60-69", "70+")
YES_NO = ("Yes", "No", DONT_KNOW)
MEDICINE = ("Regularly", "Sometimes miss", "Stopped", "No medicine given", DONT_KNOW)
BP_READINGS = ("Normal", "High", "Not measured", DONT_KNOW)
KIDNEY_STATUS = ("Never tested", "Tested normal in the past 12 months", "Told something was wrong", DONT_KNOW)
TOLD_SOMETHING_WRONG = "Told something was wrong"


class ArtifactsMissing(RuntimeError):
    """The frozen risk-level run has not been built (make triage)."""


@dataclass
class FrozenModel:
    model: object
    cutoffs: dict

    @property
    def run(self):
        return dict(config_fingerprint=self.cutoffs.get("config_fingerprint"), git_commit=self.cutoffs.get("git_commit"))


def load_frozen_model(outputs: Path) -> FrozenModel:
    model_path, cutoffs_path = outputs / "model_clinical.joblib", outputs / "triage_cutoffs.json"
    if not (model_path.exists() and cutoffs_path.exists()):
        raise ArtifactsMissing("Risk-level model not built: run `make triage`.")
    bundle = joblib.load(model_path)
    if not isinstance(bundle, dict) or "model" not in bundle:
        raise ArtifactsMissing("outputs/model_clinical.joblib is not the PRD v3 risk-level model: run `make triage`.")
    return FrozenModel(bundle["model"], json.loads(cutoffs_path.read_text()))


def score_frame(frame, model, cutoffs, cfg):
    """Risk levels (0 Low, 1 Medium, 2 High) and the guideline floor for answer rows in the simulator's vocabulary."""
    p = model.predict_proba(encode_features(frame, cfg).to_numpy(float))[:, 1]
    floor = guideline_floor(frame)
    return floored(model_levels(p, cutoffs), floor), model_levels(p, cutoffs), floor


@dataclass
class Answers:
    """One person's PRD v3 questionnaire answers. Items not shown by the branching are None."""
    age_group: str
    sex: str
    municipality: str
    diabetes: str
    high_blood_pressure: str
    heart_disease_stroke: str
    kidney_stones: str
    family_history: str
    heavy_outdoor_work: str
    kidney_status: str
    medicine: str | None = None
    bp_reading: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None

    @property
    def bmi(self):
        if self.height_cm and self.weight_kg and 100 <= self.height_cm <= 230 and 25 <= self.weight_kg <= 300:
            return self.weight_kg / (self.height_cm / 100) ** 2
        return None

    def to_frame(self):
        """One row in the simulator's answer vocabulary, applying the questionnaire branching."""
        diabetes_yes, htn_yes = self.diabetes == "Yes", self.high_blood_pressure == "Yes"
        medicine = (self.medicine or DONT_KNOW) if (diabetes_yes or htn_yes) else ""
        bp_reading = "" if htn_yes else (self.bp_reading or DONT_KNOW)
        return pd.DataFrame([dict(age_group=self.age_group, sex=self.sex, diabetes=self.diabetes,
                                  high_blood_pressure=self.high_blood_pressure, bp_reading=bp_reading, medicine=medicine,
                                  heart_disease_stroke=self.heart_disease_stroke, kidney_stones=self.kidney_stones,
                                  family_history=self.family_history, heavy_outdoor_work=self.heavy_outdoor_work,
                                  bmi_reported=np.nan if self.bmi is None else self.bmi, kidney_status=self.kidney_status)])


def add_months(day: date, months: int) -> str:
    """The month ``months`` after ``day``, as YYYY-MM."""
    index = day.year * 12 + day.month - 1 + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def explicit_dm_or_htn(row):
    """Diabetes or high BP for the wording and the floor: an explicit Yes or a High reading, never "I don't know"."""
    return row.diabetes == "Yes" or row.high_blood_pressure == "Yes" or row.bp_reading == "High"


def risk_factors(row, cfg):
    """Answers that count as a risk factor for the re-check interval and the "never tell a person with no
    risk factors to get a kidney test" rule. "I don't know" to diabetes or high BP counts (it enters the model
    as Yes); heavy outdoor work does not (no guideline lists it)."""
    traits = cfg["simulator"]["risk_check"]["traits"]
    factors = []
    if row.diabetes in ("Yes", DONT_KNOW):
        factors.append("diabetes")
    if row.high_blood_pressure in ("Yes", DONT_KNOW) or row.bp_reading == "High":
        factors.append("high_bp")
    for item in ("heart_disease_stroke", "kidney_stones", "family_history"):
        if getattr(row, item) == "Yes":
            factors.append(item)
    if pd.notna(row.bmi_reported) and row.bmi_reported >= traits["bmi_overweight_cut"]:
        factors.append("bmi")
    return factors


def next_step(level, row, cfg, today: date):
    """PRD v3 next step and re-check interval.

    - Low, aged 40+ or any risk factor: re-check in 12 months.
    - Low, aged 18-39, no risk factors and a BP reading measured Normal in the past 12 months: re-check in 3 years.
      (Any other Low aged 18-39 without risk factors gets 12 months: the PRD's 3-year rule needs the normal reading.)
    - Medium without diabetes or high BP: get BP and blood sugar checked first, then answer again (no date).
    - Medium or High with diabetes or high BP: kidney test (soon, for High), then yearly.
    - High without diabetes or high BP (age, kidney stones, or "I don't know"): kidney test soon, then yearly.
      The PRD's level table says "kidney test soon" for High; its interval table has no separate row.
    """
    young = row.age_group == "18-39"
    factors = risk_factors(row, cfg)
    if level == "Low":
        three_years = young and not factors and row.bp_reading == "Normal"
        return dict(code="recheck", soon=False, next_check=add_months(today, 36 if three_years else 12), next_kidney_test=None)
    if level == "Medium" and not explicit_dm_or_htn(row):
        return dict(code="bp_sugar_first", soon=False, next_check=None, next_kidney_test=None)
    return dict(code="kidney_test", soon=level == "High", next_check=None, next_kidney_test=add_months(today, 12))


def blood_sugar_prompt(row, cfg):
    """PHEX 2026: aged 40+ or BMI >= 23, and diabetes No or I don't know."""
    overweight = pd.notna(row.bmi_reported) and row.bmi_reported >= cfg["simulator"]["risk_check"]["traits"]["bmi_overweight_cut"]
    return row.diabetes in ("No", DONT_KNOW) and (row.age_group != "18-39" or overweight)


def reasons(row, cfg, limit=3):
    """Main reasons in plain-word codes (illustrative in the demo; Phase 2 computes them from the model)."""
    traits = cfg["simulator"]["risk_check"]["traits"]
    bmi = row.bmi_reported
    ordered = [
        ("diabetes", row.diabetes == "Yes"),
        ("high_bp", row.high_blood_pressure == "Yes" or row.bp_reading == "High"),
        ("age_group", row.age_group in ("50-59", "60-69", "70+")),
        ("kidney_stones", row.kidney_stones == "Yes"),
        ("heart_disease_stroke", row.heart_disease_stroke == "Yes"),
        ("family_history", row.family_history == "Yes"),
        ("unknown_bp_sugar", row.diabetes == DONT_KNOW or row.high_blood_pressure == DONT_KNOW),
        ("obese", pd.notna(bmi) and bmi >= traits["bmi_obese_cut"]),
        ("overweight", pd.notna(bmi) and traits["bmi_overweight_cut"] <= bmi < traits["bmi_obese_cut"]),
        ("stopped_medicine", row.medicine in ("Stopped", "Sometimes miss")),
        ("age_group", row.age_group == "40-49"),
        ("heavy_outdoor_work", row.heavy_outdoor_work == "Yes"),
    ]
    codes = []
    for code, applies in ordered:
        if applies and code not in codes:
            codes.append(code)
    return (codes or ["age_group"])[:limit]


def tips(row, cfg, heat_card, limit=4):
    """Content-plan tip rules, in priority order, at most ``limit``."""
    overweight = pd.notna(row.bmi_reported) and row.bmi_reported >= cfg["simulator"]["risk_check"]["traits"]["bmi_overweight_cut"]
    ordered = [
        ("keep_medicine", row.medicine in ("Stopped", "Sometimes miss")),
        ("check_bp_sugar", row.diabetes == DONT_KNOW or row.high_blood_pressure == DONT_KNOW),
        ("diabetes_care", row.diabetes == "Yes"),
        ("bp_care", row.high_blood_pressure == "Yes" or row.bp_reading == "High"),
        ("weight_activity", overweight),
        ("water_shade", row.heavy_outdoor_work == "Yes" and not heat_card),
        ("avoid_painkillers", True),
    ]
    return [code for code, applies in ordered if applies][:limit]


@dataclass
class Context:
    """Data the result needs besides the answers: facilities and recent heat per municipality."""
    facilities: pd.DataFrame
    centroids: dict
    recent_hot_days: dict = field(default_factory=dict)
    heat_month: str | None = None

    def facilities_for(self, municipality, limit=None):
        """Facilities in the municipality, or in the nearest municipality that has some (labelled with its town)."""
        rows = self.facilities[self.facilities.municipality == municipality]
        nearest = None
        if rows.empty and municipality in self.centroids:
            lat, lon = self.centroids[municipality]
            others = sorted((((la - lat) ** 2 + (lo - lon) ** 2), name) for name, (la, lo) in self.centroids.items()
                            if name != municipality and (self.facilities.municipality == name).any())
            if others:
                nearest = others[0][1]
                rows = self.facilities[self.facilities.municipality == nearest]
        records = rows.to_dict("records")
        return dict(municipality=municipality, shown_from=nearest, facilities=records[:limit] if limit else records)


def load_context(laguna: Path, cfg) -> Context:
    facilities = pd.read_csv(laguna / "facilities_yakap.csv")
    geography = json.loads((laguna / "municipalities.geojson").read_text())
    centroids = {}
    for feature in geography["features"]:
        coords = np.array([point for ring in _rings(feature["geometry"]) for point in ring])
        centroids[feature["properties"]["shapeName"]] = (float(coords[:, 1].mean()), float(coords[:, 0].mean()))
    hot, month = {}, None
    heat_path, cells_path = laguna / "heat_index_daily_era5land.csv", laguna / "municipal_era5_cells.csv"
    if heat_path.exists() and cells_path.exists():
        heat = pd.read_csv(heat_path, parse_dates=["local_date"])
        heat = heat[heat.complete]
        latest = heat.local_date.dt.to_period("M").max()
        recent = heat[heat.local_date.dt.to_period("M") == latest]
        threshold = cfg["analyst"]["heat_index_hot_c"]
        by_cell = recent.groupby("era5_cell").max_heat_index_c.apply(lambda s: int((s >= threshold).sum()))
        cells = pd.read_csv(cells_path)
        cells["hot_days"] = cells.era5_cell.map(by_cell).fillna(0)
        hot = (cells.weight * cells.hot_days).groupby(cells.municipality).sum().round(1).to_dict()
        month = str(latest)
    return Context(facilities, centroids, hot, month)


def _rings(geometry):
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]
    return [ring for polygon in geometry["coordinates"] for ring in polygon]


def evaluate(answers: Answers, safety: str, frozen: FrozenModel, context: Context, cfg, today: date | None = None):
    """The citizen result. Safety pre-check "Yes" and kidney status "Told something was wrong" get no risk level."""
    today = today or date.today()
    if safety == "Yes":
        return dict(route="see_doctor", where=context.facilities_for(answers.municipality, limit=1))
    if answers.kidney_status == TOLD_SOMETHING_WRONG:
        return dict(route="already_diagnosed", where=context.facilities_for(answers.municipality))
    frame = answers.to_frame()
    level_code, model_level, floor = score_frame(frame, frozen.model, frozen.cutoffs, cfg)
    level = LEVELS[int(level_code[0])]
    row = frame.iloc[0]
    hot_days = context.recent_hot_days.get(answers.municipality, 0.0)
    heat_card = row.heavy_outdoor_work == "Yes" or hot_days > 0
    referred = level != "Low"
    return dict(
        route="result",
        level=level,
        floor_applied=bool(level_code[0] > model_level[0]),
        explicit_dm_or_htn=bool(explicit_dm_or_htn(row)),
        next_step=next_step(level, row, cfg, today),
        blood_sugar_prompt=bool(blood_sugar_prompt(row, cfg)),
        reasons=reasons(row, cfg),
        age_group=answers.age_group,
        heat_advisory=dict(show=bool(heat_card), outdoor_work=row.heavy_outdoor_work == "Yes", recent_hot_days=hot_days,
                           month=context.heat_month),
        tips=tips(row, cfg, heat_card),
        worried_note=referred,
        partner_booking=referred,
        where=context.facilities_for(answers.municipality, limit=3 if referred else None),
        checked_on=today.isoformat(),
        model_run=frozen.run,
    )
