"""Transition estimator protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from dsde.domain.schemas import TransitionMatrix


@runtime_checkable
class TransitionModel(Protocol):
    def estimate(self, labels: list[str], *, seed: int = 0) -> TransitionMatrix: ...

    def sample_parameters(self, *, n: int, seed: int) -> list[TransitionMatrix]: ...
