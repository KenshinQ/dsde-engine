"""Adapter-backed ConditionalReturnEngine (non-synthetic research path)."""

from __future__ import annotations

import random
from datetime import datetime

from dsde.domain.enums import RunMode
from dsde.domain.errors import MissingValuationModelError
from dsde.domain.schemas import (
    ReturnDefinition,
    ReturnDistribution,
    ScenarioPath,
    StateBelief,
)
from dsde.returns.adapters import StubFundamentalValuationAdapter
from dsde.returns.distribution import summarize
from dsde.returns.protocol import ValuationAdapter


class AdapterConditionalReturnEngine:
    """Condition returns on price, belief, and valuation adapter.

    - Requires an explicit ValuationAdapter; never silently swaps in synthetic.
    - edge_score = E[net return], not a mechanical (1 - price/fair) cheapness score.
    - If fair value falls as much or more than price, edge does not improve.
    """

    model_version = "adapter_return_v1"

    def __init__(
        self,
        adapter: ValuationAdapter | None = None,
        *,
        require_adapter: bool = True,
        residual_vol: float = 0.03,
    ) -> None:
        self.adapter = adapter
        self.require_adapter = require_adapter
        self.residual_vol = residual_vol

    def sample_returns(
        self,
        *,
        instrument_id: str,
        as_of: datetime,
        current_price: float,
        belief: StateBelief,
        scenario_paths: list[ScenarioPath] | None = None,
        horizon_days: int = 20,
        n_samples: int = 256,
        seed: int = 0,
        return_definition: ReturnDefinition | None = None,
        run_mode: RunMode = RunMode.HISTORICAL_RESEARCH,
    ) -> ReturnDistribution:
        if self.adapter is None:
            if self.require_adapter or run_mode != RunMode.SYNTHETIC_TEST:
                raise MissingValuationModelError(
                    "ValuationAdapter missing; refusing silent SyntheticReturnEngine fallback "
                    f"(run_mode={run_mode.value})"
                )
            raise MissingValuationModelError("adapter required")

        if current_price <= 0:
            raise ValueError("current_price must be positive")

        rd = return_definition or ReturnDefinition(
            include_dividends=True,
            include_costs=True,
            cost_bps_roundtrip=20.0,
            description="total_return_net_of_costs",
        )

        fair = self.adapter.fair_value(
            instrument_id=instrument_id,
            as_of=as_of,
            belief=belief,
            current_price=current_price,
        )
        div = 0.0
        if rd.include_dividends:
            div = self.adapter.dividend_yield(
                instrument_id=instrument_id,
                as_of=as_of,
                belief=belief,
                horizon_days=horizon_days,
            )
            if rd.dividend_yield_horizon:
                div = rd.dividend_yield_horizon

        rng = random.Random(seed)
        scale = (horizon_days / 20.0) ** 0.5
        path_ids = [p.scenario_id for p in scenario_paths] if scenario_paths else []

        # Expected terminal = fair value * path state shock; return vs current price
        gross: list[float] = []
        for i in range(n_samples):
            path_mult = 1.0
            if scenario_paths:
                p = scenario_paths[i % len(scenario_paths)]
                path_mult = _terminal_mult(p)
            shock = rng.gauss(0.0, self.residual_vol * scale)
            terminal = fair * path_mult * (1.0 + shock)
            r = terminal / current_price - 1.0 + div
            gross.append(r)

        net = list(gross)
        if rd.include_costs:
            cost = rd.cost_bps_roundtrip / 10_000.0
            net = [g - cost for g in gross]

        primary = net if rd.include_costs else gross
        stats = summarize(primary)

        return ReturnDistribution(
            as_of=as_of,
            instrument_id=instrument_id,
            horizon_days=horizon_days,
            return_definition=rd.description,
            samples=primary,
            gross_samples=gross,
            net_samples=net,
            mean=stats["mean"],
            expected_log_growth=stats["expected_log_growth"],
            q01=stats["q01"],
            q05=stats["q05"],
            q50=stats["q50"],
            q95=stats["q95"],
            q99=stats["q99"],
            cvar_05=stats["cvar_05"],
            tail_metrics={
                "cvar_05": stats["cvar_05"] or 0.0,
                "q01": stats["q01"] or 0.0,
                "vol_proxy": self.residual_vol * scale,
            },
            includes_costs=rd.include_costs,
            includes_dividends=rd.include_dividends,
            current_price=current_price,
            model_fair_value=fair,
            edge_score=stats["mean"],
            scenario_ids=path_ids,
            model_versions={
                "return_engine": self.model_version,
                "valuation_adapter": self.adapter.model_version,
            },
            is_synthetic=belief.is_synthetic and run_mode == RunMode.SYNTHETIC_TEST,
            provenance={
                "engine": self.model_version,
                "adapter": self.adapter.model_version,
                "run_mode": run_mode.value,
                "seed": seed,
                "n_samples": n_samples,
                "fair_value": fair,
                "dividend_component": div,
                "cost_bps_roundtrip": rd.cost_bps_roundtrip if rd.include_costs else 0.0,
                "scenario_ids": path_ids,
                "parameter_draw_ids": [
                    p.parameter_draw_id for p in (scenario_paths or []) if p.parameter_draw_id
                ],
            },
        )

    def distribute(
        self,
        *,
        as_of: datetime,
        instrument_id: str,
        belief: StateBelief,
        price: float,
        horizon_days: int,
    ) -> ReturnDistribution:
        return self.sample_returns(
            instrument_id=instrument_id,
            as_of=as_of,
            current_price=price,
            belief=belief,
            horizon_days=horizon_days,
            run_mode=RunMode.HISTORICAL_RESEARCH,
        )


def _terminal_mult(path: ScenarioPath) -> float:
    f = path.fundamental_path[-1]
    m = path.market_path[-1]
    f_map = {
        "growth": 1.05,
        "stable": 1.0,
        "deteriorating": 0.85,
        "recovering": 0.95,
    }
    m_map = {"risk_on": 1.02, "neutral": 1.0, "risk_off": 0.95, "unavailable": 1.0}
    return f_map.get(f, 1.0) * m_map.get(m, 1.0)


def build_default_research_engine() -> AdapterConditionalReturnEngine:
    """Factory with stub adapter — explicit, not a silent synthetic swap."""
    return AdapterConditionalReturnEngine(adapter=StubFundamentalValuationAdapter())
