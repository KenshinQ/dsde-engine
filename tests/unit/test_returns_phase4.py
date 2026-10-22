"""Phase 4 conditional return engine tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from dsde.domain.enums import FundamentalState, MarketState, RunMode
from dsde.domain.errors import MissingValuationModelError
from dsde.domain.schemas import ReturnDefinition, ScenarioPath, StateBelief
from dsde.returns.adapters import StubFundamentalValuationAdapter
from dsde.returns.distribution import mean, quantile, summarize
from dsde.returns.engine import AdapterConditionalReturnEngine
from dsde.returns.synthetic import SyntheticReturnEngine


def _belief(
    *,
    fund: dict[str, float] | None = None,
    market: dict[str, float] | None = None,
) -> StateBelief:
    return StateBelief(
        as_of=datetime(2020, 3, 1),
        instrument_id="SYN001.SH",
        fundamental=fund
        or {
            FundamentalState.GROWTH.value: 0.1,
            FundamentalState.STABLE.value: 0.7,
            FundamentalState.DETERIORATING.value: 0.1,
            FundamentalState.RECOVERING.value: 0.1,
        },
        market=market
        or {
            MarketState.RISK_ON.value: 0.2,
            MarketState.NEUTRAL.value: 0.6,
            MarketState.RISK_OFF.value: 0.2,
        },
        is_synthetic=True,
    )


def _deteriorating_belief() -> StateBelief:
    return _belief(
        fund={
            FundamentalState.GROWTH.value: 0.05,
            FundamentalState.STABLE.value: 0.1,
            FundamentalState.DETERIORATING.value: 0.8,
            FundamentalState.RECOVERING.value: 0.05,
        }
    )


def _paths() -> list[ScenarioPath]:
    return [
        ScenarioPath(
            scenario_id="est-0-0",
            seed=0,
            path_steps=3,
            fundamental_path=["stable", "stable", "deteriorating"],
            market_path=["neutral", "neutral", "risk_off"],
            start_fundamental_probs=_belief().fundamental,
            start_market_probs=_belief().market,
            parameter_draw_id="param-0",
            probability_kind="estimated_probability",
            process_rng_seed=1,
            parameter_rng_seed=2,
            provenance={"test": True},
            is_synthetic=True,
        )
    ]


def test_synthetic_tagged_and_known_stats() -> None:
    eng = SyntheticReturnEngine(noise_scale=0.0)
    b = _belief()
    # With zero noise, all samples equal fair/price - 1
    fair_proxy = SyntheticReturnEngine._synthetic_fair_value(b)
    price = fair_proxy  # => mean ~ 0
    dist = eng.sample_returns(
        instrument_id="SYN001.SH",
        as_of=b.as_of,
        current_price=price,
        belief=b,
        n_samples=64,
        seed=1,
        run_mode=RunMode.SYNTHETIC_TEST,
    )
    assert dist.is_synthetic is True
    assert dist.provenance.get("note") == "synthetic_test_only"
    assert dist.mean == pytest.approx(0.0, abs=1e-9)
    assert dist.q50 == pytest.approx(0.0, abs=1e-9)


def test_synthetic_refuses_nonsynthetic_mode() -> None:
    eng = SyntheticReturnEngine()
    b = _belief()
    with pytest.raises(MissingValuationModelError):
        eng.sample_returns(
            instrument_id="X",
            as_of=b.as_of,
            current_price=10.0,
            belief=b,
            run_mode=RunMode.HISTORICAL_RESEARCH,
        )


def test_missing_adapter_no_silent_synthetic() -> None:
    eng = AdapterConditionalReturnEngine(adapter=None, require_adapter=True)
    b = _belief()
    with pytest.raises(MissingValuationModelError):
        eng.sample_returns(
            instrument_id="X",
            as_of=b.as_of,
            current_price=10.0,
            belief=b,
            run_mode=RunMode.HISTORICAL_RESEARCH,
        )


def test_depends_on_price_and_beliefs() -> None:
    eng = SyntheticReturnEngine(noise_scale=0.0)
    b = _belief()
    d1 = eng.sample_returns(
        instrument_id="X",
        as_of=b.as_of,
        current_price=10.0,
        belief=b,
        n_samples=32,
        seed=0,
    )
    d2 = eng.sample_returns(
        instrument_id="X",
        as_of=b.as_of,
        current_price=12.0,
        belief=b,
        n_samples=32,
        seed=0,
    )
    # Higher price → lower expected return for same fair value
    assert d1.mean is not None and d2.mean is not None
    assert d1.mean > d2.mean

    d3 = eng.sample_returns(
        instrument_id="X",
        as_of=b.as_of,
        current_price=10.0,
        belief=_deteriorating_belief(),
        n_samples=32,
        seed=0,
    )
    assert d3.mean is not None
    assert d3.mean < d1.mean


def test_price_drop_does_not_auto_raise_edge_when_fundamentals_worse() -> None:
    """Deteriorating fundamentals + lower price can worsen odds (not 'cheaper=better')."""
    eng = AdapterConditionalReturnEngine(adapter=StubFundamentalValuationAdapter(base_value=10.0))
    good = _belief()
    bad = _deteriorating_belief()

    # Fair values
    adapter = StubFundamentalValuationAdapter(base_value=10.0)
    fv_good = adapter.fair_value(
        instrument_id="X", as_of=good.as_of, belief=good, current_price=10.0
    )
    fv_bad = adapter.fair_value(
        instrument_id="X", as_of=bad.as_of, belief=bad, current_price=10.0
    )
    assert fv_bad < fv_good

    # Price drops proportionally less than fair value drop → edge worsens
    price_good = fv_good
    price_bad = fv_good * 0.95  # small drop, but fair dropped more
    assert price_bad < price_good
    assert fv_bad / price_bad < fv_good / price_good

    d_good = eng.sample_returns(
        instrument_id="X",
        as_of=good.as_of,
        current_price=price_good,
        belief=good,
        n_samples=200,
        seed=5,
        return_definition=ReturnDefinition(
            include_dividends=False, include_costs=False, description="gross"
        ),
        run_mode=RunMode.HISTORICAL_RESEARCH,
    )
    d_bad = eng.sample_returns(
        instrument_id="X",
        as_of=bad.as_of,
        current_price=price_bad,
        belief=bad,
        n_samples=200,
        seed=5,
        return_definition=ReturnDefinition(
            include_dividends=False, include_costs=False, description="gross"
        ),
        run_mode=RunMode.HISTORICAL_RESEARCH,
    )
    assert d_good.edge_score is not None and d_bad.edge_score is not None
    assert d_bad.edge_score < d_good.edge_score
    # Cheapness alone would have raised edge; we assert it did not
    assert d_bad.current_price < d_good.current_price


def test_gross_net_dividend_cost_definitions() -> None:
    eng = AdapterConditionalReturnEngine(adapter=StubFundamentalValuationAdapter())
    b = _belief()
    rd = ReturnDefinition(
        include_dividends=True,
        include_costs=True,
        cost_bps_roundtrip=50.0,
        dividend_yield_horizon=0.01,
        description="net_with_div",
    )
    dist = eng.sample_returns(
        instrument_id="X",
        as_of=b.as_of,
        current_price=10.0,
        belief=b,
        n_samples=50,
        seed=2,
        return_definition=rd,
        run_mode=RunMode.HISTORICAL_RESEARCH,
    )
    assert dist.includes_costs is True
    assert dist.includes_dividends is True
    assert dist.gross_samples and dist.net_samples
    # Net = gross - 50bps
    for g, n in zip(dist.gross_samples, dist.net_samples, strict=True):
        assert n == pytest.approx(g - 0.005, abs=1e-12)


def test_tail_metrics_and_summaries() -> None:
    xs = [-0.2, -0.1, 0.0, 0.05, 0.1]
    s = summarize(xs)
    assert s["mean"] == pytest.approx(sum(xs) / len(xs))
    assert s["q05"] == pytest.approx(quantile(xs, 0.05))
    assert s["cvar_05"] is not None
    assert mean(xs) == s["mean"]


def test_provenance_includes_scenarios() -> None:
    eng = SyntheticReturnEngine(noise_scale=0.01)
    b = _belief()
    paths = _paths()
    dist = eng.sample_returns(
        instrument_id="X",
        as_of=b.as_of,
        current_price=10.0,
        belief=b,
        scenario_paths=paths,
        n_samples=30,
        seed=9,
    )
    assert dist.scenario_ids == ["est-0-0"]
    assert dist.provenance.get("n_paths") == 1
    assert "return_engine" in dist.model_versions


def test_adapter_provenance_parameter_draws() -> None:
    eng = AdapterConditionalReturnEngine(adapter=StubFundamentalValuationAdapter())
    b = _belief()
    paths = _paths()
    dist = eng.sample_returns(
        instrument_id="X",
        as_of=b.as_of,
        current_price=10.0,
        belief=b,
        scenario_paths=paths,
        n_samples=20,
        seed=1,
        run_mode=RunMode.HISTORICAL_RESEARCH,
    )
    assert "param-0" in dist.provenance.get("parameter_draw_ids", [])
    assert dist.model_versions.get("valuation_adapter") == "stub_valuation_v1"


def test_distribute_wrapper() -> None:
    eng = SyntheticReturnEngine(noise_scale=0.0)
    b = _belief()
    d = eng.distribute(
        as_of=b.as_of, instrument_id="X", belief=b, price=10.0, horizon_days=20
    )
    assert d.is_synthetic is True
    assert d.horizon_days == 20
