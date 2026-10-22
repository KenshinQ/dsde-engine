"""Feasibility checks with Spec §6.8 constraint priority."""

from __future__ import annotations

from dataclasses import dataclass, field

from dsde.config import DecisionConfig, RiskConfig, ValidationConfig
from dsde.domain.enums import ReasonCode


@dataclass
class ConstraintContext:
    current_weight: float
    target_weight: float
    tradable: bool = True
    market_regime_gate_passed: bool = False
    # Optional annualized geometric growth estimate for preservation floor hook
    proposed_geo_annual: float | None = None
    decision: DecisionConfig = field(default_factory=DecisionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)


@dataclass
class ConstraintResult:
    feasible: bool
    reasons: list[ReasonCode] = field(default_factory=list)


def check_constraints(ctx: ConstraintContext) -> ConstraintResult:
    """Apply hard constraints in Spec priority order; collect reject reasons."""
    reasons: list[ReasonCode] = []

    # 1. Execution / tradability
    if not ctx.tradable:
        reasons.append(ReasonCode.NOT_TRADABLE)

    # 2. No leverage, cash floor, single-name cap
    if ctx.risk.no_leverage and ctx.target_weight > 1.0 + 1e-12:
        reasons.append(ReasonCode.POSITION_CAP_BINDING)
    if ctx.target_weight < 0:
        reasons.append(ReasonCode.POSITION_CAP_BINDING)
    cap = min(ctx.decision.single_name_cap, ctx.risk.single_name_cap)
    if ctx.target_weight > cap + 1e-12:
        reasons.append(ReasonCode.POSITION_CAP_BINDING)
    cash = 1.0 - ctx.target_weight
    if cash < ctx.risk.cash_floor - 1e-12:
        reasons.append(ReasonCode.RISK_BUDGET_BINDING)

    # 3. Preservation floor hook (annual geo below floor → bind when provided)
    floor = ctx.risk.preservation_floor_annual
    if (
        ctx.proposed_geo_annual is not None
        and ctx.target_weight > ctx.current_weight + 1e-12
        and ctx.proposed_geo_annual < floor
    ):
        reasons.append(ReasonCode.PRESERVATION_FLOOR_BINDING)

    # 4. Deadband — only when proposing a change
    deadband = ctx.decision.position_deadband
    delta = abs(ctx.target_weight - ctx.current_weight)
    if delta > 0 and delta < deadband - 1e-15:
        reasons.append(ReasonCode.POSITION_DEADBAND)

    # 6. Market regime gate: block increases that rely on gated market regime
    gate = ctx.validation.market_regime_gate
    if (
        gate.enabled
        and not ctx.market_regime_gate_passed
        and ctx.target_weight > ctx.current_weight + 1e-12
    ):
        # Allow decreases / exits; block add-ons when gate not passed
        reasons.append(ReasonCode.MARKET_REGIME_GATE_BLOCKED)

    # Deduplicate while preserving order
    seen: set[ReasonCode] = set()
    uniq: list[ReasonCode] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)

    return ConstraintResult(feasible=len(uniq) == 0, reasons=uniq)
