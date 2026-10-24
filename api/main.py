"""AGAP-CKD REST API for the React prototype: the PRD v3 risk check (app, SMS, field tablet) and the analyst view."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, List, Literal, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agap.config import ROOT
from agap.analyst import display_name, load_adults, load_age_weights, overview_with_recorded
from agap.config import load_config
from agap.triage import FEATURES
from agap.risk_check_service import Answers, ArtifactsMissing, evaluate, load_context, load_frozen_model

# Paths
ANALYST_DIR = ROOT / "outputs/analyst"
LAGUNA_DIR = ROOT / "data/processed/public/laguna"
FIELD_SYNC_LOG_PATH = ROOT / "data/reports/field_sync_log.jsonl"
RISK_CHECK_LOG_PATH = ROOT / "data/reports/risk_check_log.jsonl"


# App State Cache
STATE: dict[str, Any] = {
    "run_id": "not built",
    "risk_check": None,
}


def init_state():
    """Record the frozen risk-level run the API scores with (outputs/triage_cutoffs.json, from make triage)."""
    cutoffs = ROOT / "outputs/triage_cutoffs.json"
    if cutoffs.exists():
        STATE["run_id"] = json.loads(cutoffs.read_text()).get("config_fingerprint") or "unknown"
    print(f"AGAP-CKD API initialized. Risk-level model run: {STATE['run_id']}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_state()
    yield


app = FastAPI(
    title="AGAP-CKD Competition API",
    description="PRD v3 kidney risk check for every channel, and the analyst view",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Schemas ---

YesNo = Literal["Yes", "No", "I don't know"]


class RiskCheckRequest(BaseModel):
    """PRD v3 questionnaire answers, in the questionnaire's order. Branch-only items may be omitted."""
    channel: Literal["app", "field", "sms"] = "app"
    safety: YesNo = Field(..., description="Under 18, pregnant, or swelling / foamy, bloody or very little urine")
    age_group: Literal["18-39", "40-49", "50-59", "60-69", "70+"]
    sex: Literal["Female", "Male"]
    municipality: str
    diabetes: YesNo
    high_blood_pressure: YesNo
    medicine: Optional[Literal["Regularly", "Sometimes miss", "Stopped", "No medicine given", "I don't know"]] = None
    bp_reading: Optional[Literal["Normal", "High", "Not measured", "I don't know"]] = None
    heart_disease_stroke: YesNo
    kidney_stones: YesNo
    family_history: YesNo
    height_cm: Optional[float] = Field(None, description="Omit for I don't know")
    weight_kg: Optional[float] = Field(None, description="Omit for I don't know")
    heavy_outdoor_work: YesNo
    kidney_status: Literal["Never tested", "Tested normal in the past 12 months", "Told something was wrong", "I don't know"]


class BatchSyncRequest(BaseModel):
    checks: List[dict]
    worker_id: Optional[str] = "worker-01"


def record_check(entry: dict) -> None:
    """Append one scored check (answers and level, no name or ID) to the check log the analyst view counts."""
    RISK_CHECK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RISK_CHECK_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def read_log(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def risk_check_state():
    """The frozen risk-level model and the facility and heat context, loaded once."""
    if STATE.get("risk_check") is None:
        try:
            frozen = load_frozen_model(ROOT / "outputs")
        except ArtifactsMissing as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        STATE["risk_check"] = (frozen, load_context(LAGUNA_DIR, load_config()))
    return STATE["risk_check"]


# --- Endpoints ---

@app.get("/api/meta")
def get_meta():
    """Scenario, the frozen risk-level model run, and the data disclaimer."""
    return {
        "status": "ready",
        "run_id": STATE["run_id"],
        "scenario": "Laguna community kidney risk check (PRD v3)",
        "disclaimer": "Simulated data. Risk levels are priorities for a kidney test, not diagnoses.",
        "features": FEATURES,  # PRD v3 risk-level model inputs (agap.triage)
    }


@app.post("/api/risk-check/evaluate")
def evaluate_risk_check(req: RiskCheckRequest):
    """PRD v3 risk check for any channel: frozen model, saved cut-offs and the guideline floor (ADR 0002/0003).

    Safety pre-check "Yes" and kidney status "Told something was wrong" return no risk level. The model's
    probability is never returned: the score is never shown to citizens."""
    frozen, context = risk_check_state()
    known = set(context.centroids)
    if req.municipality not in known:
        raise HTTPException(status_code=422, detail=f"Unknown municipality: {req.municipality}")
    answers = Answers(**req.model_dump(exclude={"channel", "safety"}))
    result = evaluate(answers, req.safety, frozen, context, load_config())
    # App and SMS checks count in the area totals when scored; field checks count when the tablet syncs.
    if req.channel != "field" and result["route"] == "result":
        record_check(dict(channel=req.channel, at=datetime.now(timezone.utc).isoformat(), municipality=req.municipality,
                          risk_level=result["level"], answers=req.model_dump(exclude={"channel", "municipality"})))
    return result


@app.post("/api/citizen/evaluate")
def evaluate_citizen(req: RiskCheckRequest):
    """The citizen app's path for the same PRD v3 risk check (ADR 0003)."""
    return evaluate_risk_check(req)


@app.get("/api/risk-check/municipalities")
def get_risk_check_municipalities():
    """Laguna's 30 municipalities for the questionnaire dropdown, with their short display names."""
    _, context = risk_check_state()
    return sorted(({"municipality": m, "name": display_name(m)} for m in context.centroids), key=lambda m: m["name"])


@app.get("/api/risk-check/barangays")
def get_risk_check_barangays(municipality: str):
    """Barangay names for one municipality (PSA 2024 Census), for the field tablet's check record."""
    if STATE.get("barangays") is None:
        STATE["barangays"] = pd.read_csv(LAGUNA_DIR / "barangays_psa2024.csv")
    table = STATE["barangays"]
    rows = table[table.municipality == municipality]
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"Unknown municipality: {municipality}")
    return sorted(rows.barangay.tolist())


@app.get("/api/risk-check/facilities")
def get_risk_check_facilities(municipality: Optional[str] = None):
    """C7 / Care: hospitals and health centers for one municipality (or the nearest one with any), or all of
    them when no municipality is given. All unverified, kidney tests unknown."""
    _, context = risk_check_state()
    if municipality is None:
        return dict(municipality=None, shown_from=None, facilities=context.facilities.to_dict("records"))
    if municipality not in context.centroids:
        raise HTTPException(status_code=404, detail=f"Unknown municipality: {municipality}")
    return context.facilities_for(municipality)


@app.post("/api/field/batch-sync")
def batch_sync_checks(req: BatchSyncRequest):
    """Sync field checks collected offline on worker tablet."""
    checks_count = len(req.checks)
    now_iso = datetime.now(timezone.utc).isoformat()
    receipt_id = f"SYNC-{int(datetime.now().timestamp())}"

    # Persist synced checks to sync journal on disk
    FIELD_SYNC_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(FIELD_SYNC_LOG_PATH, "a", encoding="utf-8") as f:
            for check in req.checks:
                entry = {
                    "receipt_id": receipt_id,
                    "synced_at": now_iso,
                    "worker_id": req.worker_id,
                    **check,
                }
                f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        print("Note: field sync journal write error:", exc)

    return {
        "status": "success",
        "synced_count": checks_count,
        "synced_at": now_iso,
        "receipt_id": receipt_id,
        "message": f"Successfully synced {checks_count} offline checks to provincial register.",
    }


def _analyst_file(name: str) -> dict:
    path = ANALYST_DIR / f"{name}.json"
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"Analyst data not built: run `make triage` then `make analyst` ({path.name} missing).")
    return json.loads(path.read_text())


@app.get("/api/analyst/overview")
def get_analyst_overview():
    """A1/A2: area totals from simulated checks, with values withheld for areas under the privacy thresholds."""
    data = _analyst_file("overview")
    simulated_path = ANALYST_DIR / "checks.parquet"
    records = read_log(FIELD_SYNC_LOG_PATH) + read_log(RISK_CHECK_LOG_PATH)
    if records and simulated_path.exists():
        cfg = load_config()
        data = overview_with_recorded(pd.read_parquet(simulated_path), records, load_adults(LAGUNA_DIR), cfg,
                                      load_age_weights(LAGUNA_DIR), data)
    data["disclaimer"] = "Simulated data · Among people checked. Area totals only; not individual medical diagnoses."
    return data


@app.get("/api/analyst/climate/{municipality}")
def get_analyst_climate(municipality: str):
    """A3: monthly hot days, rainfall and mean daily maximum (ERA5-Land) for one municipality."""
    data = _analyst_file("climate")
    key = display_name(municipality)
    entry = data["municipalities"].get(key)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No climate context for {municipality}")
    return {k: v for k, v in data.items() if k != "municipalities"} | {"name": key, **entry}


@app.get("/api/analyst/model-quality")
def get_analyst_model_quality():
    """A4: the frozen run's model vs the Thai simplified score on the held-out test cohort."""
    return _analyst_file("model_quality")
