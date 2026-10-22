"""Rolling calculators and train-only scalers (no future leakage)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def rolling_mean(xs: list[float], window: int) -> float | None:
    if window <= 0 or len(xs) < window:
        return None
    chunk = xs[-window:]
    return sum(chunk) / window


def rolling_std(xs: list[float], window: int) -> float | None:
    if window <= 1 or len(xs) < window:
        return None
    chunk = xs[-window:]
    mu = sum(chunk) / window
    var = sum((x - mu) ** 2 for x in chunk) / (window - 1)
    return math.sqrt(var)


def simple_returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev == 0:
            continue
        out.append(closes[i] / prev - 1.0)
    return out


def max_drawdown_from_peak(closes: list[float]) -> float | None:
    if not closes:
        return None
    peak = closes[0]
    mdd = 0.0
    for c in closes:
        peak = max(peak, c)
        if peak > 0:
            mdd = min(mdd, c / peak - 1.0)
    return mdd


@dataclass
class RollingScaler:
    """Fit mean/std on a training slice only; transform later windows with frozen params."""

    means: dict[str, float] = field(default_factory=dict)
    stds: dict[str, float] = field(default_factory=dict)
    fitted: bool = False

    def fit(self, rows: list[dict[str, float | None]]) -> RollingScaler:
        cols: dict[str, list[float]] = {}
        for row in rows:
            for k, v in row.items():
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    continue
                cols.setdefault(k, []).append(float(v))
        self.means.clear()
        self.stds.clear()
        for k, vals in cols.items():
            if not vals:
                continue
            mu = sum(vals) / len(vals)
            if len(vals) == 1:
                sd = 1.0
            else:
                sd = math.sqrt(sum((x - mu) ** 2 for x in vals) / (len(vals) - 1))
                if sd < 1e-12:
                    sd = 1.0
            self.means[k] = mu
            self.stds[k] = sd
        self.fitted = True
        return self

    def transform(self, row: dict[str, float | None]) -> dict[str, float | None]:
        if not self.fitted:
            raise RuntimeError("RollingScaler.transform called before fit")
        out: dict[str, float | None] = {}
        for k, v in row.items():
            if v is None or k not in self.means:
                out[k] = None
                continue
            out[k] = (float(v) - self.means[k]) / self.stds[k]
        return out
