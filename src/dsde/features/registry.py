"""Feature registry with market-regime gate tagging."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FeatureFamily(str, Enum):
    FUNDAMENTAL = "fundamental"
    MARKET = "market"


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    family: FeatureFamily
    window: int | None = None
    units: str | None = None
    missing_policy: str = "skip"
    version: str = "v1"
    requires_market_regime_gate: bool = False
    description: str = ""


@dataclass
class FeatureRegistry:
    specs: dict[str, FeatureSpec] = field(default_factory=dict)

    def register(self, spec: FeatureSpec) -> None:
        if spec.name in self.specs:
            raise ValueError(f"duplicate feature: {spec.name}")
        self.specs[spec.name] = spec

    def get(self, name: str) -> FeatureSpec:
        return self.specs[name]

    def by_family(self, family: FeatureFamily) -> list[FeatureSpec]:
        return [s for s in self.specs.values() if s.family == family]

    def market_gated_names(self) -> list[str]:
        return [
            s.name
            for s in self.specs.values()
            if s.requires_market_regime_gate
        ]


def default_registry() -> FeatureRegistry:
    """Default Phase 2 feature set: fundamental vs market, gate-tagged."""
    reg = FeatureRegistry()
    # Fundamental (no market gate)
    for name, desc in [
        ("revenue_yoy", "YoY revenue growth from last two periods"),
        ("net_income_margin", "net_income / revenue"),
        ("cfo_to_ni", "operating cash flow / net income"),
        ("leverage_proxy", "placeholder leverage from total_assets change"),
    ]:
        reg.register(
            FeatureSpec(
                name=name,
                family=FeatureFamily.FUNDAMENTAL,
                units="ratio",
                description=desc,
                requires_market_regime_gate=False,
            )
        )
    # Market price/vol/breadth — ALL require gate
    for name, window, desc in [
        ("mkt_ret_20d", 20, "20d close-to-close return"),
        ("mkt_vol_20d", 20, "20d realized vol of daily returns"),
        ("mkt_drawdown_60d", 60, "drawdown from 60d peak"),
        ("mkt_trend_ma_gap", 20, "close / MA20 - 1"),
        ("mkt_breadth_proxy", 20, "share of up-days in window (breadth proxy)"),
    ]:
        reg.register(
            FeatureSpec(
                name=name,
                family=FeatureFamily.MARKET,
                window=window,
                units="ratio",
                description=desc,
                requires_market_regime_gate=True,
            )
        )
    return reg
