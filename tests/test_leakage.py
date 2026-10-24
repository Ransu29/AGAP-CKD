import pytest

from agap.config import load_config
from agap.models.leakage import LeakageError, check_no_leakage


def test_clean_features_pass():
    forbidden = load_config()["models"]["forbidden_features"]
    check_no_leakage(["age", "sex", "hypertension"], forbidden)


def test_leaked_feature_raises():
    forbidden = load_config()["models"]["forbidden_features"]
    with pytest.raises(LeakageError):
        check_no_leakage(["age", "eGFR"], forbidden)
