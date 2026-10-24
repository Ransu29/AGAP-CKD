#!/usr/bin/env python3
"""Parameter Register Validator for AGAP-CKD (SIM-04 audit).

Audits config/params.yaml against config/parameter_register.yaml to ensure:
  1. Every simulator/outcome parameter is explicitly registered.
  2. Every parameter has a valid classification ('source-supported', 'derived', or 'assumed').
  3. Every classified parameter carries its supporting evidence (source, derivation, or note).
  4. No deprecated or orphaned parameters remain in the register.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = REPO_ROOT / "config" / "params.yaml"
DEFAULT_REGISTER = REPO_ROOT / "config" / "parameter_register.yaml"
SECTIONS = ("outcome", "simulator", "prototype", "longitudinal", "reporting", "research")
LEAF_MAPPINGS = {"research.interest_shares"}


def leaves(node: dict, prefix: str = ""):
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict) and path not in LEAF_MAPPINGS:
            yield from leaves(value, path + ".")
        else:
            yield path


def audit_register(config_path: Path, register_path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not config_path.is_file():
        return False, [f"Config file not found: {config_path}"]
    if not register_path.is_file():
        return False, [f"Register file not found: {register_path}"]

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    with open(register_path, "r", encoding="utf-8") as f:
        register = yaml.safe_load(f)

    configured_nodes = {s: config[s] for s in SECTIONS if s in config}
    configured = set(leaves(configured_nodes))

    parameters = set(register.get("parameters", {}).keys())
    settings = set(register.get("settings", {}).keys())

    # Check collisions between parameters and settings
    overlap = parameters & settings
    if overlap:
        errors.append(f"Parameters also listed in settings: {sorted(overlap)}")

    # Check unclassified parameters
    unclassified = configured - parameters - settings
    if unclassified:
        errors.append(f"Unclassified parameters found in config: {sorted(unclassified)}")

    # Check orphaned entries in register
    orphaned = (parameters | settings) - configured
    if orphaned:
        errors.append(f"Register lists parameters that do not exist in config: {sorted(orphaned)}")

    # Check evidence keys
    evidence = {"source-supported": "source", "derived": "derivation", "assumed": "note"}
    valid_classes = set(register.get("classes", []))
    for name, entry in register.get("parameters", {}).items():
        p_class = entry.get("class")
        if p_class not in valid_classes:
            errors.append(f"Invalid class '{p_class}' for parameter: {name}")
        needed_field = evidence.get(p_class)
        if needed_field and not entry.get(needed_field):
            errors.append(f"Parameter '{name}' (class: {p_class}) is missing required field '{needed_field}'")

    return len(errors) == 0, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit AGAP-CKD parameter provenance and classification.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to config/params.yaml")
    parser.add_argument("--register", type=Path, default=DEFAULT_REGISTER, help="Path to config/parameter_register.yaml")
    args = parser.parse_args()

    ok, errors = audit_register(args.config, args.register)
    if not ok:
        print("[FAIL] Parameter Register Audit Failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("[PASS] Parameter Register Audit Successful: All parameters classified with evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
