"""Portfolio wealth paths and expected log growth."""

from __future__ import annotations

import math


def roundtrip_cost_fraction(
    turnover: float,
    *,
    cost_bps_one_way: float,
) -> float:
    """Cost as fraction of wealth for a one-way turnover at given bps.

    For simplicity Phase 5 treats cost_bps_one_way as applied to |Δw|.
    Round-trip intuition: callers may pass half of round-trip bps as one-way
    or pass full round-trip / 2 externally.
    """
    return turnover * (cost_bps_one_way / 10_000.0)


def wealth_multipliers(
    asset_returns: list[float],
    *,
    weight: float,
    trade_cost_fraction: float = 0.0,
) -> list[float]:
    """Wealth growth factors W_{t+1}/W_t for each asset-return sample.

    Cash earns 0 in Phase 5 single-step toy (explicit; no silent rf).
    Cost is paid up front: net_mult = (1 - cost) * (1 + w*R).
    """
    if weight < 0:
        raise ValueError("weight must be >= 0 (no short in V0.1)")
    out: list[float] = []
    scale = max(0.0, 1.0 - trade_cost_fraction)
    for r in asset_returns:
        port_r = weight * r  # cash fraction earns 0
        out.append(scale * (1.0 + port_r))
    return out


def expected_log_growth(
    asset_returns: list[float],
    *,
    weight: float,
    trade_cost_fraction: float = 0.0,
) -> float:
    """E[log(W_{t+1}/W_t)] under discrete return samples."""
    if not asset_returns:
        raise ValueError("asset_returns must be non-empty")
    mults = wealth_multipliers(
        asset_returns, weight=weight, trade_cost_fraction=trade_cost_fraction
    )
    logs = []
    for m in mults:
        if m <= 1e-15:
            logs.append(math.log(1e-15))
        else:
            logs.append(math.log(m))
    return sum(logs) / len(logs)


def binary_bet_elg(
    *,
    p_win: float,
    win_return: float,
    lose_return: float,
    weight: float,
    trade_cost_fraction: float = 0.0,
) -> float:
    """Closed-form ELG for a binary bet (hand-computable tests).

    With probability p: asset return = win_return; else lose_return.
    Portfolio: W' / W = (1 - c) * (1 + w * R).
    """
    if not 0 <= p_win <= 1:
        raise ValueError("p_win must be in [0,1]")
    scale = max(0.0, 1.0 - trade_cost_fraction)
    m_win = scale * (1.0 + weight * win_return)
    m_lose = scale * (1.0 + weight * lose_return)
    m_win = max(m_win, 1e-15)
    m_lose = max(m_lose, 1e-15)
    return p_win * math.log(m_win) + (1.0 - p_win) * math.log(m_lose)
