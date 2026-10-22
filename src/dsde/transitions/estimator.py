"""Factorized transition estimator with Dirichlet shrinkage."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from dsde.domain.enums import FundamentalState, MarketState
from dsde.domain.schemas import TransitionMatrix
from dsde.transitions.uncertainty import bootstrap_transition_samples

ROW_TOL = 1e-9


def count_transitions(labels: Sequence[str], states: list[str]) -> list[list[float]]:
    idx = {s: i for i, s in enumerate(states)}
    n = len(states)
    counts = [[0.0] * n for _ in range(n)]
    for a, b in zip(labels, labels[1:], strict=False):
        if a not in idx or b not in idx:
            continue
        counts[idx[a]][idx[b]] += 1.0
    return counts


def _normalize_rows(counts: list[list[float]], alpha: float) -> list[list[float]]:
    n = len(counts)
    out: list[list[float]] = []
    for i in range(n):
        row = [counts[i][j] + alpha for j in range(n)]
        s = sum(row)
        if s <= 0:
            out.append([1.0 / n] * n)
        else:
            out.append([x / s for x in row])
    return out


def _identity(n: int) -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


class TransitionEstimator:
    """Estimate row-stochastic P with Dirichlet(alpha) shrinkage; factorized chains only."""

    model_version = "transition_shrink_v1"

    def __init__(
        self,
        *,
        states: list[str] | None = None,
        shrinkage_alpha: float = 0.5,
        rare_state_min_count: int = 3,
        min_transitions: int = 5,
        kind: str = "estimated_probability",
    ) -> None:
        if kind not in ("estimated_probability", "assumption_scenario"):
            raise ValueError("kind must be estimated_probability or assumption_scenario")
        self.states = states or [s.value for s in FundamentalState]
        self.shrinkage_alpha = shrinkage_alpha
        self.rare_state_min_count = rare_state_min_count
        self.min_transitions = min_transitions
        self.kind = kind
        self._last_counts: list[list[float]] | None = None
        self._last_labels: list[str] = []

    def estimate(self, labels: list[str], *, seed: int = 0) -> TransitionMatrix:
        _ = seed  # point estimate deterministic given labels/alpha
        if self.kind == "assumption_scenario":
            # Explicit assumption: sticky identity (not from data frequencies)
            mat = _identity(len(self.states))
            return TransitionMatrix(
                states=list(self.states),
                matrix=mat,
                kind="assumption_scenario",
                n_obs=0,
                shrinkage_alpha=0.0,
                rare_state_warnings=["assumption_scenario_not_from_data"],
                degraded=False,
                model_version=self.model_version,
            )

        counts = count_transitions(labels, self.states)
        self._last_counts = counts
        self._last_labels = list(labels)
        n_trans = sum(sum(r) for r in counts)
        warnings: list[str] = []
        degraded = False

        state_counts = Counter(labels)
        for s in self.states:
            c = state_counts.get(s, 0)
            if c < self.rare_state_min_count:
                warnings.append(f"rare_state:{s}:count={c}")

        if n_trans < self.min_transitions:
            degraded = True
            warnings.append(
                f"fallback_sticky_identity:n_transitions={int(n_trans)}<{self.min_transitions}"
            )
            # Stronger shrink toward identity for under-identified samples
            alpha = max(self.shrinkage_alpha, 2.0)
            # Blend counts with identity pseudo-counts
            n = len(self.states)
            for i in range(n):
                counts[i][i] += alpha * 2
            mat = _normalize_rows(counts, alpha=self.shrinkage_alpha)
        else:
            mat = _normalize_rows(counts, alpha=self.shrinkage_alpha)

        # Force exact row-stochastic within float noise
        mat = [self._renorm(row) for row in mat]

        return TransitionMatrix(
            states=list(self.states),
            matrix=mat,
            kind="estimated_probability",
            n_obs=int(n_trans),
            shrinkage_alpha=self.shrinkage_alpha,
            rare_state_warnings=warnings,
            degraded=degraded,
            model_version=self.model_version,
        )

    @staticmethod
    def _renorm(row: list[float]) -> list[float]:
        s = sum(row)
        if s <= 0:
            n = len(row)
            return [1.0 / n] * n
        out = [x / s for x in row]
        # Fix residual on last element
        out[-1] = 1.0 - sum(out[:-1])
        return out

    def sample_parameters(
        self, *, n: int, seed: int, labels: list[str] | None = None
    ) -> list[TransitionMatrix]:
        """Bootstrap parameter draws (parameter uncertainty ≠ process noise)."""
        if self.kind == "assumption_scenario":
            # Assumption scenarios do not pretend to be bootstrap posteriors
            base = self.estimate([], seed=seed)
            return [
                base.model_copy(
                    update={
                        "rare_state_warnings": list(base.rare_state_warnings)
                        + [f"assumption_draw:{i}"]
                    }
                )
                for i in range(n)
            ]
        labs = labels if labels is not None else self._last_labels
        return bootstrap_transition_samples(
            labs,
            states=self.states,
            n_samples=n,
            seed=seed,
            shrinkage_alpha=self.shrinkage_alpha,
            rare_state_min_count=self.rare_state_min_count,
            min_transitions=self.min_transitions,
            model_version=self.model_version,
        )


def default_fundamental_estimator(**kwargs: object) -> TransitionEstimator:
    return TransitionEstimator(
        states=[s.value for s in FundamentalState],
        **kwargs,  # type: ignore[arg-type]
    )


def default_market_estimator(**kwargs: object) -> TransitionEstimator:
    return TransitionEstimator(
        states=[
            MarketState.RISK_ON.value,
            MarketState.NEUTRAL.value,
            MarketState.RISK_OFF.value,
        ],
        **kwargs,  # type: ignore[arg-type]
    )
