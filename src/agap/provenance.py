"""V3-013 provenance labels: every displayed quantity names its source, population, period, unit and evidence type."""
from __future__ import annotations

from agap.climate.integration import PARTITION_DATES

EVIDENCE_TYPES = ("synthetic simulation", "simulation evaluation (hidden truth)", "recorded demo activity",
                  "observed public data", "assumed setting")


def provenance_caption(source, population, period, unit, evidence):
    """One-line label for a displayed number or table; unknown parts must be stated, never omitted."""
    if evidence not in EVIDENCE_TYPES:
        raise ValueError(f"Unknown evidence type: {evidence}")
    parts = dict(Source=source, Population=population, Period=period, Unit=unit, Evidence=evidence)
    missing = [name for name, value in parts.items() if not str(value or "").strip()]
    if missing:
        raise ValueError(f"Provenance needs {', '.join(missing)}; write 'not recorded' when it is unknown.")
    return " · ".join(f"{name}: {value}" for name, value in parts.items())


def deployment_period():
    start, end = PARTITION_DATES["deployment"]
    return f"{start} to {end} (synthetic deployment cutoffs)"


def geography_label(cfg):
    """Population wording for the active geography; fixture zones are never the Laguna population."""
    area = cfg["study_area"]["pilot_area"]
    if cfg["prototype"]["geography_mode"] == "fixture":
        return f"synthetic adults in illustrative fixture zones (not the {area} population)"
    return f"synthetic adults sampled from the modeled 2020 {area} population"


def geography_banner(cfg):
    """Banner text for fixture runs; None when public geography is active."""
    if cfg["prototype"]["geography_mode"] != "fixture":
        return None
    area = cfg["study_area"]["pilot_area"]
    return (f"Fictional geography: this run uses illustrative fixture zones labelled {area}. Places, counts and service "
            f"points are not the real {area} population or clinic network. Residents and outcomes are synthetic.")
