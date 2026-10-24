"""Load the project configuration (config/params.yaml)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "params.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Return the parsed YAML config as a dict."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    with open(cfg_path, encoding="utf-8") as f:
        values = yaml.safe_load(f)
    if "extends" in values:
        base = load_config(cfg_path.parent / values.pop("extends"))
        def merge(target, update):
            for key, value in update.items():
                if isinstance(value, dict) and isinstance(target.get(key), dict):
                    merge(target[key], value)
                else:
                    target[key] = value
        merge(base, values)
        return base
    return values
