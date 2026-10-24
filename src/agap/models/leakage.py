"""Guard against label leakage: outcome-defining variables must not be model inputs."""
from __future__ import annotations

from collections.abc import Iterable


class LeakageError(ValueError):
    """Raised when a forbidden feature is passed to a model."""


def check_allowed_features(features, allowed, forbidden=()):
    unexpected = sorted(set(features) - set(allowed))
    if unexpected:
        raise LeakageError(f"Features not in declared allowlist: {unexpected}")
    check_no_leakage(features, forbidden)


def check_no_leakage(features: Iterable[str], forbidden: Iterable[str]) -> None:
    leaked = sorted({f.lower() for f in features} & {f.lower() for f in forbidden})
    if leaked:
        raise LeakageError(f"Forbidden features used as model inputs: {leaked}")
