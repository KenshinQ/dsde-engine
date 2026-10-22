"""Position / Kelly budget helpers."""

from __future__ import annotations


def half_kelly_cap(*, full_kelly_fraction: float, kelly_fraction: float = 0.5) -> float:
    """Apply fractional Kelly; never use Full Kelly to breach hard caps elsewhere."""
    if full_kelly_fraction < 0:
        return 0.0
    return full_kelly_fraction * kelly_fraction
