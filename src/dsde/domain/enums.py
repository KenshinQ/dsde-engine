"""DSDE enums: run modes, reason codes, data-layer enums."""

from __future__ import annotations

from enum import Enum


class RunMode(str, Enum):
    """Allowed runtime modes. synthetic_test outputs must carry synthetic tags."""

    SYNTHETIC_TEST = "synthetic_test"
    HISTORICAL_RESEARCH = "historical_research"
    ASOF_REPLAY = "asof_replay"
    SHADOW = "shadow"


class ReasonCode(str, Enum):
    """Machine-readable decision reason codes (Spec §6.9)."""

    POSITIVE_ROBUST_ELG = "POSITIVE_ROBUST_ELG"
    INSUFFICIENT_MODEL_CONFIDENCE = "INSUFFICIENT_MODEL_CONFIDENCE"
    STATE_PROBABILITY_SHIFT = "STATE_PROBABILITY_SHIFT"
    RETURN_DISTRIBUTION_DETERIORATION = "RETURN_DISTRIBUTION_DETERIORATION"
    PRICE_VALUATION_CONTEXT_CHANGED = "PRICE_VALUATION_CONTEXT_CHANGED"
    RISK_BUDGET_BINDING = "RISK_BUDGET_BINDING"
    POSITION_CAP_BINDING = "POSITION_CAP_BINDING"
    TRANSACTION_COST_EXCEEDS_BENEFIT = "TRANSACTION_COST_EXCEEDS_BENEFIT"
    POSITION_DEADBAND = "POSITION_DEADBAND"
    MARKET_REGIME_GATE_BLOCKED = "MARKET_REGIME_GATE_BLOCKED"
    PRESERVATION_FLOOR_BINDING = "PRESERVATION_FLOOR_BINDING"
    NOT_TRADABLE = "NOT_TRADABLE"
    MODEL_DRIFT_DETECTED = "MODEL_DRIFT_DETECTED"
    FALLBACK_TO_BASELINE = "FALLBACK_TO_BASELINE"
    NO_FEASIBLE_ACTION = "NO_FEASIBLE_ACTION"


class FundamentalState(str, Enum):
    GROWTH = "growth"
    STABLE = "stable"
    DETERIORATING = "deteriorating"
    RECOVERING = "recovering"


class MarketState(str, Enum):
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"
    UNAVAILABLE = "unavailable"


class CorporateActionType(str, Enum):
    DIVIDEND = "dividend"
    STOCK_SPLIT = "stock_split"
    STOCK_DIVIDEND = "stock_dividend"
    RIGHTS_ISSUE = "rights_issue"
    OTHER = "other"


class QualityFlag(str, Enum):
    OK = "ok"
    MISSING = "missing"
    DUPLICATE = "duplicate"
    SUSPENDED = "suspended"
    DELISTED = "delisted"
    REVISED = "revised"
    OUTLIER = "outlier"
    STALE = "stale"
