"""Distribution summaries and tail metrics."""

from __future__ import annotations

import math
from collections.abc import Iterable


def _sorted(xs: Iterable[float]) -> list[float]:
    return sorted(float(x) for x in xs)


def quantile(samples: list[float], q: float) -> float | None:
    if not samples:
        return None
    if q <= 0:
        return samples[0]
    if q >= 1:
        return samples[-1]
    xs = _sorted(samples)
    pos = q * (len(xs) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1 - w) + xs[hi] * w


def mean(samples: list[float]) -> float | None:
    if not samples:
        return None
    return sum(samples) / len(samples)


def expected_log_growth(samples: list[float]) -> float | None:
    """E[log(1+R)] with floor to avoid log<=0 crash on catastrophic samples."""
    if not samples:
        return None
    vals = []
    for r in samples:
        w = 1.0 + r
        if w <= 1e-12:
            vals.append(math.log(1e-12))
        else:
            vals.append(math.log(w))
    return sum(vals) / len(vals)


def cvar(samples: list[float], alpha: float = 0.05) -> float | None:
    """Average of the worst alpha fraction (left tail)."""
    if not samples:
        return None
    xs = _sorted(samples)
    k = max(1, int(math.ceil(alpha * len(xs))))
    return sum(xs[:k]) / k


def summarize(samples: list[float]) -> dict[str, float | None]:
    return {
        "mean": mean(samples),
        "expected_log_growth": expected_log_growth(samples),
        "q01": quantile(samples, 0.01),
        "q05": quantile(samples, 0.05),
        "q50": quantile(samples, 0.50),
        "q95": quantile(samples, 0.95),
        "q99": quantile(samples, 0.99),
        "cvar_05": cvar(samples, 0.05),
    }
