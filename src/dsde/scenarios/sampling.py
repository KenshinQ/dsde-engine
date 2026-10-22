"""Process-noise sampling helpers (separate from parameter RNG)."""

from __future__ import annotations

import random


def sample_categorical(
    probs: dict[str, float], rng: random.Random
) -> str:
    items = list(probs.items())
    total = sum(p for _, p in items)
    if total <= 0:
        return items[0][0]
    u = rng.random() * total
    acc = 0.0
    for k, p in items:
        acc += p
        if u <= acc:
            return k
    return items[-1][0]


def sample_from_row(
    states: list[str], row: list[float], rng: random.Random
) -> str:
    u = rng.random()
    acc = 0.0
    for s, p in zip(states, row, strict=True):
        acc += p
        if u <= acc:
            return s
    return states[-1]
