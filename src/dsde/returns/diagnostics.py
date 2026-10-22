"""Return-engine diagnostics helpers."""

from __future__ import annotations

from dsde.domain.schemas import ReturnDistribution


def assert_synthetic_tagged(dist: ReturnDistribution) -> None:
    if not dist.is_synthetic:
        raise AssertionError("SyntheticReturnEngine output must set is_synthetic=True")
