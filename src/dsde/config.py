"""Load and validate configs/*.yaml with Pydantic schemas."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from dsde.domain.errors import ConfigValidationError

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"


class DataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calendar: str = "XSHG"
    timezone: str = "Asia/Shanghai"
    pit_required: bool = True
    price_adjust: str = "total_return"
    placeholder_note: str = "Phase 0 placeholder; no real providers"


class StatesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fundamental_states: list[str] = Field(
        default_factory=lambda: ["growth", "stable", "deteriorating", "recovering"]
    )
    market_states: list[str] = Field(
        default_factory=lambda: ["risk_on", "neutral", "risk_off"]
    )
    factorization: str = "factorized"
    max_joint_free_params: int = 0


class DecisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_grid: list[float] = Field(
        default_factory=lambda: [0.0, 0.05, 0.10, 0.15, 0.20, 0.25]
    )
    position_deadband: float = Field(default=0.03, ge=0.0, le=0.25)
    min_elg_improvement: float = Field(default=0.0005, ge=0.0)
    mpc_horizon_steps: int = Field(default=1, ge=1)
    single_name_cap: float = Field(default=0.25, ge=0.0, le=1.0)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    no_leverage: bool = True
    cash_floor: float = Field(default=0.0, ge=0.0, le=1.0)
    single_name_cap: float = Field(default=0.25, ge=0.0, le=1.0)
    kelly_fraction: float = Field(default=0.5, gt=0.0, le=1.0)
    kelly_note: str = "half_kelly default; Full Kelly point estimate forbidden"
    preservation_floor_annual: float = Field(default=0.04, ge=0.0, le=0.5)
    robust_elg_quantile: float = Field(default=0.25, gt=0.0, lt=1.0)


class MarketRegimeGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    requires_independent_oos: bool = True
    gate_passed: bool = False
    freeze_fields: list[str] = Field(
        default_factory=lambda: [
            "metric",
            "threshold",
            "universe",
            "window",
            "registered_at",
        ]
    )
    fallback_market_state: str = "neutral"
    tre_probe_ref: str = "/workspace/tre-factor-probe/summary.md"
    note: str = (
        "Price-volume market regime must pass frozen OOS gate before sizing; "
        "TRE F1/RMOM probes closed as weak/not robust."
    )


class ValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_metric: str = "net_geometric_growth_vs_B2_B4"
    baselines: list[str] = Field(default_factory=lambda: ["B2", "B4"])
    secondary_metrics: list[str] = Field(
        default_factory=lambda: [
            "max_drawdown",
            "left_tail_q05",
            "turnover",
            "net_costs",
        ]
    )
    market_regime_gate: MarketRegimeGateConfig = Field(
        default_factory=MarketRegimeGateConfig
    )
    allow_investment_claims_without_adapter: bool = False


class ExecutionAShareConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t_plus_one: bool = True
    respect_limit_up_down: bool = True
    commission_bps: float = Field(default=3.0, ge=0.0)
    stamp_duty_sell_bps: float = Field(default=5.0, ge=0.0)
    slippage_bps: float = Field(default=5.0, ge=0.0)
    signal_time: str = "close"
    execution_time: str = "next_open"
    position_deadband_enforced: bool = True


class AppConfig(BaseModel):
    """Aggregate validated config bundle."""

    model_config = ConfigDict(extra="forbid")

    data: DataConfig
    states: StatesConfig
    decision: DecisionConfig
    risk: RiskConfig
    validation: ValidationConfig
    execution_a_share: ExecutionAShareConfig


_FILE_TO_MODEL: dict[str, type[BaseModel]] = {
    "data.yaml": DataConfig,
    "states.yaml": StatesConfig,
    "decision.yaml": DecisionConfig,
    "risk.yaml": RiskConfig,
    "validation.yaml": ValidationConfig,
    "execution_a_share.yaml": ExecutionAShareConfig,
}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigValidationError(f"missing config file: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigValidationError(f"invalid YAML in {path}: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigValidationError(f"config root must be a mapping: {path}")
    return raw


def load_configs(config_dir: Path | str | None = None) -> AppConfig:
    """Load and validate the Phase 0 config bundle."""
    root = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    if not root.is_dir():
        raise ConfigValidationError(f"config directory not found: {root}")

    parts: dict[str, BaseModel] = {}
    for filename, model_cls in _FILE_TO_MODEL.items():
        path = root / filename
        data = _load_yaml(path)
        key = filename.removesuffix(".yaml")
        try:
            parts[key] = model_cls.model_validate(data)
        except Exception as exc:
            raise ConfigValidationError(f"{filename}: {exc}") from exc

    return AppConfig(
        data=parts["data"],  # type: ignore[arg-type]
        states=parts["states"],  # type: ignore[arg-type]
        decision=parts["decision"],  # type: ignore[arg-type]
        risk=parts["risk"],  # type: ignore[arg-type]
        validation=parts["validation"],  # type: ignore[arg-type]
        execution_a_share=parts["execution_a_share"],  # type: ignore[arg-type]
    )
