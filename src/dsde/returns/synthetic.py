"""SyntheticReturnEngine — tests / synthetic_test mode ONLY."""

from __future__ import annotations

import random
from datetime import datetime

from dsde.domain.enums import FundamentalState, MarketState, RunMode
from dsde.domain.errors import MissingValuationModelError
from dsde.domain.schemas import (
    ReturnDefinition,
    ReturnDistribution,
    ScenarioPath,
    StateBelief,
)
from dsde.returns.distribution import summarize


class SyntheticReturnEngine:
    """Known synthetic generative model for unit tests.

    MUST tag is_synthetic=True. Refuses non-synthetic run modes.
    Conditioning: price, fundamental belief, market belief, optional paths.
    Price drop alone does NOT raise edge_score; edge = E[R] under the model.
    """

    model_version = "synthetic_return_v1"

    def __init__(self, *, noise_scale: float = 0.02) -> None:
        self.noise_scale = noise_scale

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
        run_mode: RunMode = RunMode.SYNTHETIC_TEST,
    ) -> ReturnDistribution:
        if run_mode != RunMode.SYNTHETIC_TEST:
            raise MissingValuationModelError(
                "SyntheticReturnEngine cannot be used outside synthetic_test; "
                "refusing silent fallback in research/shadow modes"
            )
        if current_price <= 0:
            raise ValueError("current_price must be positive")

        rd = return_definition or ReturnDefinition(
            include_dividends=False,
            include_costs=False,
            description="price_return_gross",
        )
        rng = random.Random(seed)

        # Synthetic fair value from beliefs (independent of current_price level
        # except as a ratio input for returns).
        fair = self._synthetic_fair_value(belief)
        # Path-conditioned expected terminal multiple
        path_ids: list[str] = []
        if scenario_paths:
            path_ids = [p.scenario_id for p in scenario_paths]
            path_mult = self._path_multiplier(scenario_paths, rng)
        else:
            path_mult = 1.0

        scale = (horizon_days / 20.0) ** 0.5
        gross: list[float] = []
        for _ in range(n_samples):
            # Terminal value ~ fair * path_mult * (1+noise); return vs current price
            shock = rng.gauss(0.0, self.noise_scale * scale)
            terminal = fair * path_mult * (1.0 + shock)
            r_price = terminal / current_price - 1.0
            r = r_price
            if rd.include_dividends:
                r += rd.dividend_yield_horizon + self._div_from_belief(
                    belief, horizon_days
                )
            gross.append(r)

        net = list(gross)
        if rd.include_costs:
            cost = rd.cost_bps_roundtrip / 10_000.0
            net = [g - cost for g in gross]

        primary = net if rd.include_costs else gross
        stats = summarize(primary)
        edge = stats["mean"]  # E[R]; NOT (fair/price - 1) alone as "cheapness boost"

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
            },
            includes_costs=rd.include_costs,
            includes_dividends=rd.include_dividends,
            current_price=current_price,
            model_fair_value=fair,
            edge_score=edge,
            scenario_ids=path_ids,
            model_versions={"return_engine": self.model_version},
            is_synthetic=True,
            provenance={
                "engine": self.model_version,
                "run_mode": run_mode.value,
                "seed": seed,
                "n_samples": n_samples,
                "path_mult": path_mult,
                "n_paths": len(scenario_paths or []),
                "fair_value": fair,
                "note": "synthetic_test_only",
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
            run_mode=RunMode.SYNTHETIC_TEST,
        )

    @staticmethod
    def _synthetic_fair_value(belief: StateBelief) -> float:
        base = 10.0
        f = belief.fundamental
        fund = (
            1.20 * f.get(FundamentalState.GROWTH.value, 0.0)
            + 1.00 * f.get(FundamentalState.STABLE.value, 0.0)
            + 0.60 * f.get(FundamentalState.DETERIORATING.value, 0.0)
            + 0.85 * f.get(FundamentalState.RECOVERING.value, 0.0)
        )
        m = belief.market
        mkt = (
            1.05 * m.get(MarketState.RISK_ON.value, 0.0)
            + 1.00 * m.get(MarketState.NEUTRAL.value, 0.0)
            + 0.90 * m.get(MarketState.RISK_OFF.value, 0.0)
        )
        return base * fund * (mkt if mkt > 0 else 1.0)

    @staticmethod
    def _div_from_belief(belief: StateBelief, horizon_days: int) -> float:
        f = belief.fundamental
        annual = 0.02 * f.get(FundamentalState.STABLE.value, 0.0)
        return annual * (horizon_days / 252.0)

    @staticmethod
    def _path_multiplier(paths: list[ScenarioPath], rng: random.Random) -> float:
        # Sample one path's terminal states as a multiplier shock
        p = paths[rng.randrange(len(paths))]
        f = p.fundamental_path[-1]
        m = p.market_path[-1]
        f_map = {
            "growth": 1.05,
            "stable": 1.0,
            "deteriorating": 0.85,
            "recovering": 0.95,
        }
        m_map = {"risk_on": 1.02, "neutral": 1.0, "risk_off": 0.95, "unavailable": 1.0}
        return f_map.get(f, 1.0) * m_map.get(m, 1.0)
