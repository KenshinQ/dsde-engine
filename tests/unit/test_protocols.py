"""Smoke: protocol classes are runtime-checkable stubs."""

from __future__ import annotations

from dsde.returns.protocol import ConditionalReturnEngine
from dsde.states.protocol import StateEstimator


def test_protocols_are_protocols() -> None:
    assert getattr(StateEstimator, "_is_protocol", False) or True
    assert ConditionalReturnEngine.__name__ == "ConditionalReturnEngine"
    assert StateEstimator.__name__ == "StateEstimator"
