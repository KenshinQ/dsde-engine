"""Market feature helpers — all require market regime gate."""

from __future__ import annotations

from dsde.features.registry import default_registry


def gated_market_feature_names() -> list[str]:
    return default_registry().market_gated_names()
