"""Pluggable fundamental / valuation adapters."""

from __future__ import annotations

from datetime import datetime

from dsde.domain.enums import FundamentalState, MarketState
from dsde.domain.schemas import StateBelief


class StubFundamentalValuationAdapter:
    """Deterministic stub: fair value from fundamental + market beliefs.

    Fair value is an absolute model value, not a function that auto-improves
    when market price alone drops. Price enters only as a separate input to
    the return engine (price / fair_value), not here as a cheapness booster.
    """

    model_version = "stub_valuation_v1"

    def __init__(self, *, base_value: float = 10.0) -> None:
        self.base_value = base_value

    def fair_value(
        self,
        *,
        instrument_id: str,
        as_of: datetime,
        belief: StateBelief,
        current_price: float,
    ) -> float:
        _ = (instrument_id, as_of, current_price)  # price intentionally unused
        # Fundamental multipliers
        f = belief.fundamental
        fund_mult = (
            1.15 * f.get(FundamentalState.GROWTH.value, 0.0)
            + 1.00 * f.get(FundamentalState.STABLE.value, 0.0)
            + 0.70 * f.get(FundamentalState.DETERIORATING.value, 0.0)
            + 0.90 * f.get(FundamentalState.RECOVERING.value, 0.0)
        )
        m = belief.market
        mkt_mult = (
            1.05 * m.get(MarketState.RISK_ON.value, 0.0)
            + 1.00 * m.get(MarketState.NEUTRAL.value, 0.0)
            + 0.90 * m.get(MarketState.RISK_OFF.value, 0.0)
            + 1.00 * m.get(MarketState.UNAVAILABLE.value, 0.0)
        )
        # If market unavailable mass is zero, renormalize-ish by using 1.0 default
        if abs(sum(m.values()) - 1.0) > 1e-6:
            mkt_mult = 1.0
        return self.base_value * fund_mult * mkt_mult

    def dividend_yield(
        self,
        *,
        instrument_id: str,
        as_of: datetime,
        belief: StateBelief,
        horizon_days: int,
    ) -> float:
        _ = (instrument_id, as_of, horizon_days)
        # Slightly higher yield in stable; lower when deteriorating
        f = belief.fundamental
        annual = (
            0.02 * f.get(FundamentalState.STABLE.value, 0.0)
            + 0.01 * f.get(FundamentalState.GROWTH.value, 0.0)
            + 0.005 * f.get(FundamentalState.RECOVERING.value, 0.0)
            + 0.0 * f.get(FundamentalState.DETERIORATING.value, 0.0)
        )
        return annual * (horizon_days / 252.0)
