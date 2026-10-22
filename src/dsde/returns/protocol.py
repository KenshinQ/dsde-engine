"""ConditionalReturnEngine protocol (Phase 4)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from dsde.domain.enums import RunMode
from dsde.domain.schemas import (
    ReturnDefinition,
    ReturnDistribution,
    ScenarioPath,
    StateBelief,
)


@runtime_checkable
class ValuationAdapter(Protocol):
    """Pluggable fundamental / valuation model."""

    model_version: str

    def fair_value(
        self,
        *,
        instrument_id: str,
        as_of: datetime,
        belief: StateBelief,
        current_price: float,
    ) -> float:
        """Model fair value in price units. Must depend on belief, not only price."""
        ...

    def dividend_yield(
        self,
        *,
        instrument_id: str,
        as_of: datetime,
        belief: StateBelief,
        horizon_days: int,
    ) -> float:
        ...


@runtime_checkable
class ConditionalReturnEngine(Protocol):
    """Map price × belief × paths → conditional return distribution.

    Decision layer must not bypass this interface.
    """

    model_version: str

    def sample_returns(
        self,
        *,
        instrument_id: str,
        as_of: datetime,
        current_price: float,
        belief: StateBelief,
        scenario_paths: list[ScenarioPath] | None = None,
        horizon_days: int = 20,
        n_samples: int = 256,
        seed: int = 0,
        return_definition: ReturnDefinition | None = None,
        run_mode: RunMode = RunMode.SYNTHETIC_TEST,
    ) -> ReturnDistribution:
        ...

    def distribute(
        self,
        *,
        as_of: datetime,
        instrument_id: str,
        belief: StateBelief,
        price: float,
        horizon_days: int,
    ) -> ReturnDistribution:
        """Convenience wrapper around sample_returns."""
        ...
