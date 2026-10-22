"""StateEstimator protocol (Phase 2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from dsde.domain.schemas import ObservationRecord, StateBelief
from dsde.features.builder import FeatureSnapshot


@runtime_checkable
class StateEstimator(Protocol):
    """Estimate posterior belief b_t. Implementations must be seed-reproducible."""

    model_version: str

    def fit(self, history: list[FeatureSnapshot], *, seed: int = 0) -> StateEstimator:
        """Fit any scaler / params on history only (no future)."""
        ...

    def initialize(self, *, as_of: datetime, instrument_id: str | None = None) -> StateBelief:
        ...

    def update(
        self,
        *,
        as_of: datetime,
        features: FeatureSnapshot,
        prior: StateBelief | None = None,
        observations: list[ObservationRecord] | None = None,
    ) -> StateBelief:
        """Return a valid StateBelief; must not invent future fundamentals."""
        ...

    def diagnostics(self) -> dict[str, Any]:
        ...
