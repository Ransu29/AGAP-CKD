"""The pipeline's allocation model is a config setting and matches the app's default planning model."""
import pandas as pd
import pytest

from agap.config import load_config
from agap.experiment import allocation_scores


def predictions():
    rows = [("SYN-2", "clinical", .9, .2), ("SYN-1", "clinical", .9, .1), ("SYN-1", "climate", .9, .7),
            ("SYN-2", "climate", .9, .8), ("SYN-1", "clinical", .8, .5), ("SYN-2", "clinical", .8, .6)]
    return pd.DataFrame(rows, columns=["resident_id", "model", "target_sensitivity", "score"])


def test_allocation_scores_follow_the_configured_model_in_frame_order():
    frame = pd.DataFrame({"resident_id": ["SYN-1", "SYN-2"]})
    for model, expected in (("clinical", [.1, .2]), ("climate", [.7, .8])):
        cfg = {"prototype": {"allocation_model": model}}
        assert allocation_scores(cfg, predictions(), frame).tolist() == expected


def test_unknown_allocation_model_is_rejected():
    with pytest.raises(ValueError, match="Unknown allocation model"):
        allocation_scores({"prototype": {"allocation_model": "heat"}}, predictions(), pd.DataFrame({"resident_id": ["SYN-1"]}))


@pytest.mark.parametrize("profile", ["config/params.yaml", "config/climate.yaml", "config/fast.yaml"])
def test_profiles_allocate_with_the_app_default_questionnaire_model(profile):
    assert load_config(profile)["prototype"]["allocation_model"] == "clinical"
