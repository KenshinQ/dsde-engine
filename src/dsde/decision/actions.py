"""Configurable discrete target-weight grid."""

from __future__ import annotations

from dsde.config import DecisionConfig


def resolve_action_grid(config: DecisionConfig | None = None) -> list[float]:
    """Return sorted unique weights in [0, 1]; never hardcode in callers."""
    cfg = config or DecisionConfig()
    grid = sorted({float(w) for w in cfg.action_grid})
    for w in grid:
        if w < 0 or w > 1:
            raise ValueError(f"action_grid weight out of [0,1]: {w}")
    if not grid:
        raise ValueError("action_grid must be non-empty")
    return grid


def trade_notional_fraction(current_weight: float, target_weight: float) -> float:
    """Absolute portfolio-weight turnover (one-way)."""
    return abs(target_weight - current_weight)
