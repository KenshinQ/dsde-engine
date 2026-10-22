"""Phase 5 research-exit helpers: B2 / B4 comparison hooks (stubs OK)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BaselineSpec:
    """Pre-registered baselines for research exit (Spec Phase 5)."""

    name: str
    description: str


B2 = BaselineSpec(
    name="B2",
    description="Fundamental/valuation strategy without dynamic state updates",
)
B4 = BaselineSpec(
    name="B4",
    description="Same return model, single-step ELG, no MPC",
)


@dataclass
class ResearchExitReport:
    """Document whether to proceed past Phase 5 (no MPC required if FAIL)."""

    primary_metric: str = "net_geometric_growth_vs_B2_B4"
    baselines: list[str] = field(default_factory=lambda: ["B2", "B4"])
    dsde_metric: float | None = None
    b2_metric: float | None = None
    b4_metric: float | None = None
    min_improvement: float | None = None
    passed: bool | None = None
    recommendation: str = "insufficient_evidence"
    notes: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


def evaluate_research_exit(
    *,
    dsde_net_geo: float | None = None,
    b2_net_geo: float | None = None,
    b4_net_geo: float | None = None,
    min_improvement: float = 0.0,
    secondary: dict[str, float] | None = None,
) -> ResearchExitReport:
    """Compare DSDE single-step to B2/B4 on pre-registered primary metric.

    If metrics are missing, returns insufficient_evidence (do not proceed to MPC
    on narrative alone). Does not run a full backtest — callers supply metrics.
    """
    notes: list[str] = [
        "Phase 5 research exit: do not enter Phase 6–7 without pre-registered OOS pass",
        "Primary metric must be net geometric wealth growth vs B2 and B4",
    ]
    if dsde_net_geo is None or b2_net_geo is None or b4_net_geo is None:
        return ResearchExitReport(
            dsde_metric=dsde_net_geo,
            b2_metric=b2_net_geo,
            b4_metric=b4_net_geo,
            min_improvement=min_improvement,
            passed=None,
            recommendation="insufficient_evidence",
            notes=notes + ["metrics_incomplete_stub"],
            extras={"secondary": secondary or {}},
        )

    delta_b2 = dsde_net_geo - b2_net_geo
    delta_b4 = dsde_net_geo - b4_net_geo
    passed = delta_b2 >= min_improvement and delta_b4 >= min_improvement
    rec = "proceed_optional_phase6" if passed else "stop_or_simplify_stay_phase5"
    return ResearchExitReport(
        dsde_metric=dsde_net_geo,
        b2_metric=b2_net_geo,
        b4_metric=b4_net_geo,
        min_improvement=min_improvement,
        passed=passed,
        recommendation=rec,
        notes=notes
        + [
            f"delta_vs_B2={delta_b2}",
            f"delta_vs_B4={delta_b4}",
        ],
        extras={"secondary": secondary or {}, "delta_b2": delta_b2, "delta_b4": delta_b4},
    )
