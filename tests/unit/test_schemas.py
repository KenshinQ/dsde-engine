"""Unit tests: domain schemas and belief probability sums."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from dsde.domain.enums import ReasonCode, RunMode
from dsde.domain.errors import DomainValidationError
from dsde.domain.schemas import DecisionRecord, ObservationRecord, StateBelief


def test_observation_record_schema_ok() -> None:
    t0 = datetime(2020, 1, 1, tzinfo=UTC)
    t1 = datetime(2020, 1, 15, tzinfo=UTC)
    rec = ObservationRecord(
        instrument_id="600000.SH",
        feature_name="payload",
        value={"rev": 1},
        event_time=t0,
        available_at=t1,
        source="synthetic",
        is_synthetic=True,
    )
    assert rec.entity_id == "600000.SH"
    assert rec.instrument_id == "600000.SH"
    assert rec.is_synthetic is True


def test_state_belief_probs_sum_to_one() -> None:
    belief = StateBelief(
        as_of=datetime(2020, 1, 1, tzinfo=UTC),
        fundamental={
            "growth": 0.25,
            "stable": 0.25,
            "deteriorating": 0.25,
            "recovering": 0.25,
        },
        market={"risk_on": 0.2, "neutral": 0.5, "risk_off": 0.3},
        is_synthetic=True,
    )
    assert abs(sum(belief.fundamental.values()) - 1.0) < 1e-9
    assert abs(sum(belief.market.values()) - 1.0) < 1e-9


def test_state_belief_bad_sum_raises() -> None:
    with pytest.raises((DomainValidationError, ValidationError)):
        StateBelief(
            as_of=datetime(2020, 1, 1, tzinfo=UTC),
            fundamental={"growth": 0.9, "stable": 0.9},
            market={"neutral": 1.0},
            is_synthetic=True,
        )


def test_reason_codes_include_phase011() -> None:
    required = {
        ReasonCode.POSITION_DEADBAND,
        ReasonCode.MARKET_REGIME_GATE_BLOCKED,
        ReasonCode.PRESERVATION_FLOOR_BINDING,
        ReasonCode.TRANSACTION_COST_EXCEEDS_BENEFIT,
        ReasonCode.NO_FEASIBLE_ACTION,
    }
    assert required.issubset(set(ReasonCode))


def test_synthetic_mode_requires_tag() -> None:
    with pytest.raises((DomainValidationError, ValidationError)):
        DecisionRecord(
            decision_id="d1",
            as_of=datetime(2020, 1, 1, tzinfo=UTC),
            instrument_id="600000.SH",
            run_mode=RunMode.SYNTHETIC_TEST,
            current_weight=0.0,
            target_weight=0.0,
            is_synthetic=False,
        )
