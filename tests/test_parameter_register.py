"""SIM-03 / SIM-04: simulator numbers live in config and every one is classified."""
import yaml

from agap.config import ROOT

SECTIONS = ("outcome", "simulator", "prototype", "longitudinal", "reporting", "research")
LEAF_MAPPINGS = {"research.interest_shares"}  # one parameter whose value is a mapping


def leaves(node, prefix=""):
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict) and path not in LEAF_MAPPINGS:
            yield from leaves(value, path + ".")
        else:
            yield path


def test_every_simulator_parameter_is_classified_once():
    config = yaml.safe_load((ROOT / "config/params.yaml").read_text())
    register = yaml.safe_load((ROOT / "config/parameter_register.yaml").read_text())
    configured = set(leaves({section: config[section] for section in SECTIONS}))
    parameters, settings = set(register["parameters"]), set(register["settings"])
    assert not parameters & settings
    assert configured - parameters - settings == set(), "unclassified parameters"
    assert (parameters | settings) - configured == set(), "register lists parameters that no longer exist"


def test_classes_carry_their_evidence():
    register = yaml.safe_load((ROOT / "config/parameter_register.yaml").read_text())
    evidence = {"source-supported": "source", "derived": "derivation", "assumed": "note"}
    for name, entry in register["parameters"].items():
        assert entry["class"] in register["classes"], name
        assert entry.get(evidence[entry["class"]]), f"{name} needs a {evidence[entry['class']]}"


def test_simulator_code_has_no_inline_generator_numbers():
    source = (ROOT / "src/agap/experiment.py").read_text()
    for literal in (".035", ".015", ".025", "29.9", "59.9", "logit(.10)", "< .18", "< .30", "(subtype < .65)"):
        assert literal not in source, literal
