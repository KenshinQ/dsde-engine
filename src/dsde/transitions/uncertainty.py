"""Bootstrap / posterior-style parameter samples for transition matrices."""

from __future__ import annotations

import random
from collections import Counter

from dsde.domain.schemas import TransitionMatrix


def _normalize_rows(counts: list[list[float]], alpha: float) -> list[list[float]]:
    n = len(counts)
    out: list[list[float]] = []
    for i in range(n):
        row = [counts[i][j] + alpha for j in range(n)]
        s = sum(row)
        if s <= 0:
            out.append([1.0 / n] * n)
        else:
            r = [x / s for x in row]
            r[-1] = 1.0 - sum(r[:-1])
            out.append(r)
    return out


def bootstrap_transition_samples(
    labels: list[str],
    *,
    states: list[str],
    n_samples: int,
    seed: int,
    shrinkage_alpha: float = 0.5,
    rare_state_min_count: int = 3,
    min_transitions: int = 5,
    model_version: str = "transition_shrink_v1",
) -> list[TransitionMatrix]:
    """Resample consecutive pairs to get parameter uncertainty draws."""
    rng = random.Random(seed)
    pairs = list(zip(labels, labels[1:], strict=False))
    idx = {s: i for i, s in enumerate(states)}
    n = len(states)
    out: list[TransitionMatrix] = []

    if not pairs:
        # Empty → sticky identity draws with degrade flag
        ident = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
        for _i in range(n_samples):
            out.append(
                TransitionMatrix(
                    states=list(states),
                    matrix=ident,
                    kind="estimated_probability",
                    n_obs=0,
                    shrinkage_alpha=shrinkage_alpha,
                    rare_state_warnings=["bootstrap_empty_fallback_identity"],
                    degraded=True,
                    model_version=model_version,
                )
            )
        return out

    for i in range(n_samples):
        draw = [pairs[rng.randrange(len(pairs))] for _ in range(len(pairs))]
        counts = [[0.0] * n for _ in range(n)]
        for a, b in draw:
            if a in idx and b in idx:
                counts[idx[a]][idx[b]] += 1.0
        n_trans = sum(sum(r) for r in counts)
        warnings: list[str] = [f"bootstrap_draw:{i}"]
        degraded = n_trans < min_transitions
        # rare states in this draw
        labs_flat = [a for a, _ in draw] + ([draw[-1][1]] if draw else [])
        sc = Counter(labs_flat)
        for s in states:
            if sc.get(s, 0) < rare_state_min_count:
                warnings.append(f"rare_state:{s}:count={sc.get(s, 0)}")
        if degraded:
            warnings.append("bootstrap_underidentified")
            for r in range(n):
                counts[r][r] += shrinkage_alpha * 2
        mat = _normalize_rows(counts, alpha=shrinkage_alpha)
        out.append(
            TransitionMatrix(
                states=list(states),
                matrix=mat,
                kind="estimated_probability",
                n_obs=int(n_trans),
                shrinkage_alpha=shrinkage_alpha,
                rare_state_warnings=warnings,
                degraded=degraded,
                model_version=model_version,
            )
        )
    return out
