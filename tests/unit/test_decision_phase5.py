"""Phase 5 single-step decision / ELG tests."""

from __future__ import annotations

import math
from datetime import datetime

import pytest

from dsde.config import (
    DecisionConfig,
    ExecutionAShareConfig,
    MarketRegimeGateConfig,
    RiskConfig,
    ValidationConfig,
)
from dsde.decision.constraints import ConstraintContext, check_constraints
from dsde.decision.objective import binary_bet_elg, expected_log_growth, wealth_multipliers
from dsde.decision.research_exit import B2, B4, evaluate_research_exit
from dsde.decision.single_step import SingleStepDecisionEngine
from dsde.domain.enums import ReasonCode, RunMode
from dsde.domain.schemas import ReturnDistribution


def _engine(**kwargs) -> SingleStepDecisionEngine:
    gate = MarketRegimeGateConfig(enabled=True, gate_passed=True)
    validation = ValidationConfig(market_regime_gate=gate)
    return SingleStepDecisionEngine(
        decision=kwargs.get("decision")
        or DecisionConfig(position_deadband=0.02, min_elg_improvement=0.0001),
        risk=kwargs.get("risk") or RiskConfig(single_name_cap=0.25, no_leverage=True),
        validation=kwargs.get("validation") or validation,
        execution=kwargs.get("execution")
        or ExecutionAShareConfig(commission_bps=0.0, slippage_bps=0.0, stamp_duty_sell_bps=0.0),
    )


def test_binary_bet_elg_matches_closed_form() -> None:
    # Classic: p=0.6, win=+1, lose=-0.5, w=0.2, no cost
    p, win, lose, w = 0.6, 1.0, -0.5, 0.2
    analytic = binary_bet_elg(p_win=p, win_return=win, lose_return=lose, weight=w)
    # Discrete sample equivalent: 3 wins, 2 losses
    samples = [win, win, win, lose, lose]
    # But ELG with equal weights on samples is not same as p=0.6 unless we weight —
    # Use exact two-point with repetition matching p via formula path:
    assert analytic == pytest.approx(
        p * math.log(1 + w * win) + (1 - p) * math.log(1 + w * lose)
    )
    # Sample estimator with probabilities encoded by frequency 3:2
    est = expected_log_growth(samples, weight=w, trade_cost_fraction=0.0)
    assert est == pytest.approx(
        0.6 * math.log(1 + w * win) + 0.4 * math.log(1 + w * lose)
    )


def test_zero_weight_no_cost_wealth_is_one() -> None:
    samples = [0.5, -0.2, 0.1]
    mults = wealth_multipliers(samples, weight=0.0, trade_cost_fraction=0.0)
    assert mults == [1.0, 1.0, 1.0]
    assert expected_log_growth(samples, weight=0.0) == pytest.approx(0.0)


def test_position_cap_and_no_leverage() -> None:
    eng = _engine(
        decision=DecisionConfig(
            action_grid=[0.0, 0.1, 0.25, 0.5],
            position_deadband=0.02,
            min_elg_improvement=0.0001,
            single_name_cap=0.25,
        ),
        risk=RiskConfig(single_name_cap=0.25, no_leverage=True),
    )
    # Strong positive edge
    samples = [0.5] * 10 + [-0.1] * 2
    d = eng.decide(
        as_of=datetime(2020, 1, 1),
        instrument_id="X",
        current_weight=0.0,
        returns=samples,
        run_mode=RunMode.SYNTHETIC_TEST,
        market_regime_gate_passed=True,
    )
    assert d.target_weight <= 0.25 + 1e-12
    # Cap binding visible on overweight candidates
    assert any(
        ReasonCode.POSITION_CAP_BINDING in c.reject_reasons
        for c in d.candidate_actions
        if c.target_weight > 0.25
    )


def test_hold_when_cost_exceeds_benefit() -> None:
    # Tiny edge, large costs
    decision = DecisionConfig(
        action_grid=[0.0, 0.1, 0.2],
        position_deadband=0.01,
        min_elg_improvement=0.01,  # high bar
    )
    execution = ExecutionAShareConfig(
        commission_bps=50.0, slippage_bps=50.0, stamp_duty_sell_bps=0.0
    )
    eng = _engine(decision=decision, execution=execution)
    samples = [0.02, 0.01, -0.005, 0.015]  # mild positive
    d = eng.decide(
        as_of=datetime(2020, 1, 1),
        instrument_id="X",
        current_weight=0.0,
        returns=samples,
        run_mode=RunMode.SYNTHETIC_TEST,
        market_regime_gate_passed=True,
    )
    # Should stay at 0 or not improve enough to trade
    assert d.target_weight == pytest.approx(0.0)
    assert (
        ReasonCode.TRANSACTION_COST_EXCEEDS_BENEFIT in d.reason_codes
        or any(
            ReasonCode.TRANSACTION_COST_EXCEEDS_BENEFIT in c.reject_reasons
            for c in d.candidate_actions
            if c.target_weight > 0
        )
    )


def test_deadband_blocks_tiny_rebalance() -> None:
    eng = _engine(
        decision=DecisionConfig(
            action_grid=[0.0, 0.10, 0.12, 0.20],
            position_deadband=0.05,
            min_elg_improvement=0.0,
        )
    )
    samples = [0.3] * 8 + [-0.05] * 2
    d = eng.decide(
        as_of=datetime(2020, 1, 1),
        instrument_id="X",
        current_weight=0.10,
        returns=samples,
        run_mode=RunMode.SYNTHETIC_TEST,
        market_regime_gate_passed=True,
    )
    # 0.12 is within deadband of 0.10 → rejected
    c012 = next(c for c in d.candidate_actions if abs(c.target_weight - 0.12) < 1e-12)
    assert ReasonCode.POSITION_DEADBAND in c012.reject_reasons
    assert c012.feasible is False


def test_market_regime_gate_blocks_add() -> None:
    gate = MarketRegimeGateConfig(enabled=True, gate_passed=False)
    eng = _engine(validation=ValidationConfig(market_regime_gate=gate))
    samples = [0.4] * 10 + [-0.05] * 2
    d = eng.decide(
        as_of=datetime(2020, 1, 1),
        instrument_id="X",
        current_weight=0.0,
        returns=samples,
        run_mode=RunMode.SYNTHETIC_TEST,
        market_regime_gate_passed=False,
    )
    assert d.target_weight == pytest.approx(0.0)
    assert any(
        ReasonCode.MARKET_REGIME_GATE_BLOCKED in c.reject_reasons
        for c in d.candidate_actions
        if c.target_weight > 0
    )


def test_no_feasible_action_safe_degrade() -> None:
    eng = _engine()
    samples = [0.1, -0.05]
    d = eng.decide(
        as_of=datetime(2020, 1, 1),
        instrument_id="X",
        current_weight=0.1,
        returns=samples,
        run_mode=RunMode.SYNTHETIC_TEST,
        tradable=False,
        market_regime_gate_passed=True,
    )
    assert ReasonCode.NO_FEASIBLE_ACTION in d.reason_codes
    assert d.safe_degraded is True
    assert d.target_weight == pytest.approx(0.1)


def test_preservation_floor_hook() -> None:
    ctx = ConstraintContext(
        current_weight=0.0,
        target_weight=0.2,
        tradable=True,
        market_regime_gate_passed=True,
        proposed_geo_annual=0.01,  # below 4% floor
        risk=RiskConfig(preservation_floor_annual=0.04),
        decision=DecisionConfig(position_deadband=0.0),
        validation=ValidationConfig(
            market_regime_gate=MarketRegimeGateConfig(enabled=False)
        ),
    )
    res = check_constraints(ctx)
    assert ReasonCode.PRESERVATION_FLOOR_BINDING in res.reasons


def test_decision_record_audits_candidates() -> None:
    eng = _engine()
    samples = [0.25] * 6 + [-0.1] * 4
    dist = ReturnDistribution(
        as_of=datetime(2020, 1, 1),
        instrument_id="X",
        horizon_days=20,
        samples=samples,
        is_synthetic=True,
    )
    d = eng.decide(
        as_of=datetime(2020, 1, 1),
        instrument_id="X",
        current_weight=0.0,
        returns=dist,
        run_mode=RunMode.SYNTHETIC_TEST,
        market_regime_gate_passed=True,
    )
    assert d.candidate_actions
    assert d.expected_log_growth is not None
    assert d.hold_elg is not None
    assert d.is_synthetic is True


def test_research_exit_stubs_b2_b4() -> None:
    assert B2.name == "B2" and B4.name == "B4"
    incomplete = evaluate_research_exit()
    assert incomplete.passed is None
    assert incomplete.recommendation == "insufficient_evidence"

    fail = evaluate_research_exit(
        dsde_net_geo=0.05, b2_net_geo=0.08, b4_net_geo=0.07, min_improvement=0.0
    )
    assert fail.passed is False
    assert "stay_phase5" in fail.recommendation or "stop" in fail.recommendation

    ok = evaluate_research_exit(
        dsde_net_geo=0.12, b2_net_geo=0.08, b4_net_geo=0.09, min_improvement=0.01
    )
    assert ok.passed is True
