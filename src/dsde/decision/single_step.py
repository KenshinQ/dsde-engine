"""Single-step ELG decision engine (Phase 5)."""

from __future__ import annotations

import uuid
from datetime import datetime

from dsde.config import (
    AppConfig,
    DecisionConfig,
    ExecutionAShareConfig,
    RiskConfig,
    ValidationConfig,
    load_configs,
)
from dsde.decision.actions import resolve_action_grid, trade_notional_fraction
from dsde.decision.constraints import ConstraintContext, check_constraints
from dsde.decision.objective import expected_log_growth, roundtrip_cost_fraction
from dsde.domain.enums import ReasonCode, RunMode
from dsde.domain.schemas import (
    CandidateActionScore,
    DecisionRecord,
    ReturnDistribution,
)


class SingleStepDecisionEngine:
    """Compare discrete target weights under constraints; emit DecisionRecord."""

    model_version = "single_step_elg_v1"

    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        decision: DecisionConfig | None = None,
        risk: RiskConfig | None = None,
        validation: ValidationConfig | None = None,
        execution: ExecutionAShareConfig | None = None,
    ) -> None:
        if config is not None:
            self.decision = config.decision
            self.risk = config.risk
            self.validation = config.validation
            self.execution = config.execution_a_share
        else:
            self.decision = decision or DecisionConfig()
            self.risk = risk or RiskConfig()
            self.validation = validation or ValidationConfig()
            self.execution = execution or ExecutionAShareConfig()

    @classmethod
    def from_config_dir(cls, config_dir: str | None = None) -> SingleStepDecisionEngine:
        return cls(load_configs(config_dir))

    def decide(
        self,
        *,
        as_of: datetime,
        instrument_id: str,
        current_weight: float,
        returns: ReturnDistribution | list[float],
        run_mode: RunMode = RunMode.SYNTHETIC_TEST,
        tradable: bool = True,
        market_regime_gate_passed: bool | None = None,
        proposed_geo_annual: float | None = None,
        is_synthetic: bool | None = None,
        decision_id: str | None = None,
    ) -> DecisionRecord:
        samples = (
            list(returns.samples)
            if isinstance(returns, ReturnDistribution)
            else list(returns)
        )
        if not samples:
            raise ValueError("return samples must be non-empty")

        if market_regime_gate_passed is None:
            market_regime_gate_passed = (
                self.validation.market_regime_gate.gate_passed
            )

        cost_bps = (
            self.execution.commission_bps
            + self.execution.slippage_bps
            + 0.5 * self.execution.stamp_duty_sell_bps
        )

        grid = resolve_action_grid(self.decision)
        # Always evaluate HOLD at current weight (may not be on grid)
        hold_cost = 0.0
        hold_elg = expected_log_growth(
            samples, weight=current_weight, trade_cost_fraction=hold_cost
        )

        candidates: list[CandidateActionScore] = []
        feasible_scores: list[tuple[float, float, float, list[ReasonCode]]] = []
        # tuple: (elg, target, cost, reasons_empty)

        for w in grid:
            turnover = trade_notional_fraction(current_weight, w)
            cost = roundtrip_cost_fraction(turnover, cost_bps_one_way=cost_bps)
            elg = expected_log_growth(
                samples, weight=w, trade_cost_fraction=cost
            )
            improvement = elg - hold_elg

            ctx = ConstraintContext(
                current_weight=current_weight,
                target_weight=w,
                tradable=tradable,
                market_regime_gate_passed=bool(market_regime_gate_passed),
                proposed_geo_annual=proposed_geo_annual,
                decision=self.decision,
                risk=self.risk,
                validation=self.validation,
            )
            cres = check_constraints(ctx)
            reject = list(cres.reasons)

            # Cost / ELG improvement threshold (Spec §6.6) — only for changes
            if abs(w - current_weight) > 1e-15:
                if improvement < self.decision.min_elg_improvement:
                    if ReasonCode.TRANSACTION_COST_EXCEEDS_BENEFIT not in reject:
                        reject.append(ReasonCode.TRANSACTION_COST_EXCEEDS_BENEFIT)
                    cres.feasible = False

            # Same weight as current on grid → treat as hold candidate (feasible)
            if abs(w - current_weight) <= 1e-15:
                reject = [
                    r
                    for r in reject
                    if r
                    not in (
                        ReasonCode.POSITION_DEADBAND,
                        ReasonCode.TRANSACTION_COST_EXCEEDS_BENEFIT,
                        ReasonCode.MARKET_REGIME_GATE_BLOCKED,
                    )
                ]
                cres.feasible = len(reject) == 0

            cand = CandidateActionScore(
                target_weight=w,
                expected_log_growth=elg,
                elg_improvement_vs_hold=improvement,
                trade_cost_fraction=cost,
                feasible=cres.feasible and len(reject) == 0,
                reject_reasons=reject,
            )
            candidates.append(cand)
            if cand.feasible:
                feasible_scores.append((elg, w, cost, []))

        # Also consider pure HOLD if current not on grid
        if all(abs(w - current_weight) > 1e-15 for w in grid):
            candidates.append(
                CandidateActionScore(
                    target_weight=current_weight,
                    expected_log_growth=hold_elg,
                    elg_improvement_vs_hold=0.0,
                    trade_cost_fraction=0.0,
                    feasible=tradable,
                    reject_reasons=[] if tradable else [ReasonCode.NOT_TRADABLE],
                )
            )
            if tradable:
                feasible_scores.append((hold_elg, current_weight, 0.0, []))

        synth = (
            is_synthetic
            if is_synthetic is not None
            else (run_mode == RunMode.SYNTHETIC_TEST)
        )

        if not feasible_scores:
            # Safe degrade: HOLD current (even if not "optimal")
            return DecisionRecord(
                decision_id=decision_id or str(uuid.uuid4()),
                as_of=as_of,
                instrument_id=instrument_id,
                run_mode=run_mode,
                current_weight=current_weight,
                target_weight=current_weight,
                reason_codes=[ReasonCode.NO_FEASIBLE_ACTION],
                is_synthetic=synth,
                notes="safe_degrade_hold_current",
                expected_log_growth=hold_elg,
                hold_elg=hold_elg,
                elg_improvement=0.0,
                trade_cost_fraction=0.0,
                candidate_actions=candidates,
                binding_constraints=[ReasonCode.NO_FEASIBLE_ACTION],
                safe_degraded=True,
                model_versions={"decision": self.model_version},
                diagnostics={"n_feasible": 0, "hold_elg": hold_elg},
            )

        # Pick max ELG among feasible; tie-break toward smaller trade / lower weight
        feasible_scores.sort(key=lambda t: (-t[0], abs(t[1] - current_weight), t[1]))
        best_elg, best_w, best_cost, _ = feasible_scores[0]
        improvement = best_elg - hold_elg

        reasons: list[ReasonCode] = []
        if abs(best_w - current_weight) <= 1e-15:
            # Staying put — annotate why we didn't move if useful
            # Check if any higher weight was blocked by gate/deadband/cost
            blocked = [
                c
                for c in candidates
                if c.target_weight > current_weight and not c.feasible
            ]
            if any(
                ReasonCode.MARKET_REGIME_GATE_BLOCKED in c.reject_reasons
                for c in blocked
            ):
                reasons.append(ReasonCode.MARKET_REGIME_GATE_BLOCKED)
            if any(
                ReasonCode.TRANSACTION_COST_EXCEEDS_BENEFIT in c.reject_reasons
                for c in blocked
            ):
                reasons.append(ReasonCode.TRANSACTION_COST_EXCEEDS_BENEFIT)
            if any(
                ReasonCode.POSITION_DEADBAND in c.reject_reasons for c in blocked
            ):
                reasons.append(ReasonCode.POSITION_DEADBAND)
            if not reasons:
                reasons.append(ReasonCode.POSITIVE_ROBUST_ELG)
        else:
            reasons.append(ReasonCode.POSITIVE_ROBUST_ELG)

        return DecisionRecord(
            decision_id=decision_id or str(uuid.uuid4()),
            as_of=as_of,
            instrument_id=instrument_id,
            run_mode=run_mode,
            current_weight=current_weight,
            target_weight=best_w,
            reason_codes=reasons,
            is_synthetic=synth,
            expected_log_growth=best_elg,
            hold_elg=hold_elg,
            elg_improvement=improvement,
            trade_cost_fraction=best_cost,
            candidate_actions=candidates,
            binding_constraints=[],
            safe_degraded=False,
            model_versions={"decision": self.model_version},
            diagnostics={
                "n_feasible": len(feasible_scores),
                "cost_bps_one_way": cost_bps,
                "action_grid": grid,
                "min_elg_improvement": self.decision.min_elg_improvement,
                "position_deadband": self.decision.position_deadband,
            },
        )
