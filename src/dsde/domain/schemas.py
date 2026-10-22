"""Core domain entities (Phase 0 + Phase 1 PIT schemas)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dsde.domain.enums import (
    CorporateActionType,
    FundamentalState,
    MarketState,
    QualityFlag,
    ReasonCode,
    RunMode,
)
from dsde.domain.errors import DomainValidationError

PROB_SUM_TOL = 1e-6


class ObservationRecord(BaseModel):
    """Generic PIT observation (Spec §5.2)."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    feature_name: str
    value: Any = None
    event_time: datetime
    available_at: datetime
    ingested_at: datetime | None = None
    source: str = "unknown"
    revision_id: str | None = None
    quality_flags: list[QualityFlag] = Field(default_factory=lambda: [QualityFlag.OK])
    units: str | None = None
    is_synthetic: bool = False
    # Backward-compatible alias used in Phase 0 tests / callers
    instrument_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _alias_instrument(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "entity_id" not in data and data.get("instrument_id"):
                data = {**data, "entity_id": data["instrument_id"]}
            if "feature_name" not in data:
                data = {**data, "feature_name": data.get("feature_name") or "payload"}
            if "value" not in data and "payload" in data:
                data = {**data, "value": data.pop("payload")}
        return data

    @model_validator(mode="after")
    def _available_not_before_event(self) -> ObservationRecord:
        if self.available_at < self.event_time:
            raise DomainValidationError(
                "available_at must be >= event_time for ObservationRecord"
            )
        if self.instrument_id is None:
            object.__setattr__(self, "instrument_id", self.entity_id)
        return self


class InstrumentMeta(BaseModel):
    """Listing / delisting metadata."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    exchange: str = "XSHG"
    list_date: date | None = None
    delist_date: date | None = None
    is_synthetic: bool = False

    @model_validator(mode="after")
    def _delist_after_list(self) -> InstrumentMeta:
        if (
            self.list_date is not None
            and self.delist_date is not None
            and self.delist_date < self.list_date
        ):
            raise DomainValidationError("delist_date must be >= list_date")
        return self

    def is_listed_on(self, d: date) -> bool:
        if self.list_date is not None and d < self.list_date:
            return False
        if self.delist_date is not None and d >= self.delist_date:
            return False
        return True


class PriceBar(BaseModel):
    """Daily (or bar) price / volume with tradability flags."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    trade_date: date
    available_at: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    amount: float | None = None
    adj_factor: float | None = 1.0
    is_suspended: bool = False
    limit_up: float | None = None
    limit_down: float | None = None
    quality_flags: list[QualityFlag] = Field(default_factory=lambda: [QualityFlag.OK])
    source: str = "unknown"
    revision_id: str | None = None
    is_synthetic: bool = False

    @property
    def event_time(self) -> date:
        return self.trade_date


class FundamentalSnapshot(BaseModel):
    """Fiscal-period fundamentals with separate period vs announcement times."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    period_start: date
    period_end: date
    announcement_time: datetime
    available_at: datetime | None = None
    financial_features: dict[str, float | None] = Field(default_factory=dict)
    cash_flow_features: dict[str, float | None] = Field(default_factory=dict)
    balance_sheet_features: dict[str, float | None] = Field(default_factory=dict)
    quality_flags: list[QualityFlag] = Field(default_factory=lambda: [QualityFlag.OK])
    source_version: str = "v1"
    revision_id: str | None = None
    is_synthetic: bool = False

    @model_validator(mode="after")
    def _period_and_announce(self) -> FundamentalSnapshot:
        if self.period_end < self.period_start:
            raise DomainValidationError("period_end must be >= period_start")
        # Announcement is after (or at) period end in calendar terms — allow same-day
        # but forbid announcement before period_start.
        if self.announcement_time.date() < self.period_start:
            raise DomainValidationError(
                "announcement_time must not precede period_start"
            )
        if self.available_at is None:
            object.__setattr__(self, "available_at", self.announcement_time)
        return self


class CorporateAction(BaseModel):
    """Dividend / split / rights etc."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    action_type: CorporateActionType
    ex_date: date
    available_at: datetime
    record_date: date | None = None
    pay_date: date | None = None
    cash_amount: float | None = None
    ratio: float | None = None
    source: str = "unknown"
    revision_id: str | None = None
    is_synthetic: bool = False


class CalendarDay(BaseModel):
    """One trading-calendar row."""

    model_config = ConfigDict(extra="forbid")

    calendar_id: str = "XSHG"
    day: date
    is_trading_day: bool = True


class TradingCalendar(BaseModel):
    """Trading calendar container."""

    model_config = ConfigDict(extra="forbid")

    calendar_id: str = "XSHG"
    days: list[CalendarDay] = Field(default_factory=list)

    def is_trading_day(self, d: date) -> bool:
        for row in self.days:
            if row.day == d:
                return row.is_trading_day
        return False

    def next_trading_day(self, d: date) -> date | None:
        after = sorted(x.day for x in self.days if x.is_trading_day and x.day > d)
        return after[0] if after else None


class SignalExecutionTiming(BaseModel):
    """Signal time vs execution time must be explicit and separated (Spec Phase 1)."""

    model_config = ConfigDict(extra="forbid")

    signal_time: datetime
    execution_time: datetime
    signal_rule: str = "close"
    execution_rule: str = "next_open"

    @model_validator(mode="after")
    def _exec_after_signal(self) -> SignalExecutionTiming:
        if self.execution_time <= self.signal_time:
            raise DomainValidationError(
                "execution_time must be strictly after signal_time"
            )
        return self


class QualityReport(BaseModel):
    """Import quality summary (Spec Phase 1 acceptance #7)."""

    model_config = ConfigDict(extra="forbid")

    source: str
    record_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    duplicate_count: int = 0
    missing_field_count: int = 0
    missing_rate: float = 0.0
    duplicate_rate: float = 0.0
    quality_flags: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    is_synthetic: bool = False


class StateBelief(BaseModel):
    """Posterior belief over factorized fundamental × market states."""

    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    instrument_id: str | None = None
    fundamental: dict[str, float]
    market: dict[str, float]
    market_regime_gate_passed: bool | None = None
    is_synthetic: bool = False
    model_version: str = "phase0-stub"
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    feature_contributions: dict[str, float] = Field(default_factory=dict)
    input_snapshot_hash: str | None = None

    @field_validator("fundamental", "market")
    @classmethod
    def _nonempty_probs(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise DomainValidationError("probability map must be non-empty")
        for k, p in v.items():
            if p < 0 or p > 1:
                raise DomainValidationError(f"probability out of [0,1] for {k}: {p}")
        return v

    @model_validator(mode="after")
    def _probs_sum_to_one(self) -> StateBelief:
        for name, probs in (("fundamental", self.fundamental), ("market", self.market)):
            s = sum(probs.values())
            if abs(s - 1.0) > PROB_SUM_TOL:
                raise DomainValidationError(
                    f"{name} probabilities must sum to 1±{PROB_SUM_TOL}, got {s}"
                )
        return self

    @classmethod
    def uniform_placeholder(
        cls,
        *,
        as_of: datetime,
        instrument_id: str | None = None,
        is_synthetic: bool = True,
    ) -> StateBelief:
        fund = {s.value: 1.0 / len(FundamentalState) for s in FundamentalState}
        mkt = {
            s.value: 1.0 / (len(MarketState) - 1)
            for s in MarketState
            if s != MarketState.UNAVAILABLE
        }
        return cls(
            as_of=as_of,
            instrument_id=instrument_id,
            fundamental=fund,
            market=mkt,
            is_synthetic=is_synthetic,
        )


class ReturnDefinition(BaseModel):
    """Explicit return / cost口径 (Spec Phase 4)."""

    model_config = ConfigDict(extra="forbid")

    price_return: bool = True
    include_dividends: bool = False
    include_costs: bool = False
    cost_bps_roundtrip: float = 0.0
    dividend_yield_horizon: float = 0.0
    description: str = "price_return_gross"


class ReturnDistribution(BaseModel):
    """Conditional return distribution with summaries, tails, provenance."""

    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    instrument_id: str
    horizon_days: int = Field(ge=1)
    return_definition: str = "price_return_gross"
    samples: list[float] = Field(default_factory=list)  # primary (net if costs on)
    gross_samples: list[float] = Field(default_factory=list)
    net_samples: list[float] = Field(default_factory=list)
    mean: float | None = None
    expected_log_growth: float | None = None
    q01: float | None = None
    q05: float | None = None
    q50: float | None = None
    q95: float | None = None
    q99: float | None = None
    cvar_05: float | None = None
    tail_metrics: dict[str, float] = Field(default_factory=dict)
    includes_costs: bool = False
    includes_dividends: bool = False
    current_price: float | None = None
    model_fair_value: float | None = None
    # Advantage vs cash: E[R] — NOT "cheapness". Lower price alone must not raise this
    # unless fair value / cashflows justify it.
    edge_score: float | None = None
    scenario_ids: list[str] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)
    is_synthetic: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)


class CandidateActionScore(BaseModel):
    """One evaluated target weight on the discrete grid."""

    model_config = ConfigDict(extra="forbid")

    target_weight: float
    expected_log_growth: float | None = None
    elg_improvement_vs_hold: float | None = None
    trade_cost_fraction: float = 0.0
    feasible: bool = True
    reject_reasons: list[ReasonCode] = Field(default_factory=list)


class DecisionRecord(BaseModel):
    """Auditable single-step decision (Phase 5)."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    as_of: datetime
    instrument_id: str
    run_mode: RunMode
    current_weight: float = Field(ge=0.0, le=1.0)
    target_weight: float = Field(ge=0.0, le=1.0)
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    is_synthetic: bool = False
    notes: str | None = None
    signal_time: datetime | None = None
    execution_time: datetime | None = None
    expected_log_growth: float | None = None
    hold_elg: float | None = None
    elg_improvement: float | None = None
    trade_cost_fraction: float = 0.0
    candidate_actions: list[CandidateActionScore] = Field(default_factory=list)
    binding_constraints: list[ReasonCode] = Field(default_factory=list)
    safe_degraded: bool = False
    model_versions: dict[str, str] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _synthetic_tag_consistency(self) -> DecisionRecord:
        if self.run_mode == RunMode.SYNTHETIC_TEST and not self.is_synthetic:
            raise DomainValidationError(
                "run_mode=synthetic_test requires is_synthetic=True"
            )
        if self.is_synthetic and self.run_mode != RunMode.SYNTHETIC_TEST:
            raise DomainValidationError(
                "is_synthetic=True is only allowed when run_mode=synthetic_test"
            )
        if (
            self.signal_time is not None
            and self.execution_time is not None
            and self.execution_time <= self.signal_time
        ):
            raise DomainValidationError(
                "execution_time must be strictly after signal_time"
            )
        return self


class TransitionMatrix(BaseModel):
    """Row-stochastic transition matrix for one factorized chain."""

    model_config = ConfigDict(extra="forbid")

    states: list[str]
    matrix: list[list[float]]
    kind: str = "estimated_probability"  # vs assumption_scenario
    n_obs: int = 0
    shrinkage_alpha: float = 0.0
    rare_state_warnings: list[str] = Field(default_factory=list)
    degraded: bool = False
    model_version: str = "transition_v1"
    is_synthetic: bool = False

    @model_validator(mode="after")
    def _row_stochastic(self) -> TransitionMatrix:
        n = len(self.states)
        if len(self.matrix) != n:
            raise DomainValidationError("matrix row count must match states")
        for i, row in enumerate(self.matrix):
            if len(row) != n:
                raise DomainValidationError(f"matrix row {i} length mismatch")
            if any(x < -1e-12 for x in row):
                raise DomainValidationError("negative transition probability")
            s = sum(row)
            if abs(s - 1.0) > 1e-6:
                raise DomainValidationError(
                    f"row {i} must sum to 1±1e-6, got {s}"
                )
        return self


class ScenarioPath(BaseModel):
    """One simulated future state path with provenance (Spec §5.2 / §6.4)."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    seed: int
    path_steps: int
    fundamental_path: list[str]
    market_path: list[str]
    start_fundamental_probs: dict[str, float]
    start_market_probs: dict[str, float]
    parameter_draw_id: str | None = None
    scenario_weight: float = 1.0
    assumption_tags: list[str] = Field(default_factory=list)
    # estimated_probability | assumption_scenario
    probability_kind: str = "estimated_probability"
    process_rng_seed: int | None = None
    parameter_rng_seed: int | None = None
    transition_model_version: str = "transition_v1"
    provenance: dict[str, Any] = Field(default_factory=dict)
    is_synthetic: bool = False


class ScenarioBatch(BaseModel):
    """Batch of paths with resource metadata."""

    model_config = ConfigDict(extra="forbid")

    paths: list[ScenarioPath]
    n_requested: int
    n_generated: int
    n_capped: bool = False
    max_paths_cap: int = 0
    max_steps_cap: int = 0
    seed: int = 0
    notes: list[str] = Field(default_factory=list)
