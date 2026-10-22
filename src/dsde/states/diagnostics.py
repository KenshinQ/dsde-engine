"""State path diagnostics: shares, durations, transition counts."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from dsde.domain.schemas import StateBelief


def argmax_state(probs: dict[str, float]) -> str:
    return max(probs.items(), key=lambda kv: kv[1])[0]


def belief_path_diagnostics(beliefs: list[StateBelief]) -> dict[str, Any]:
    """Compute state share, spell durations, and transition counts on MAP labels."""
    if not beliefs:
        return {
            "n": 0,
            "fundamental_share": {},
            "market_share": {},
            "fundamental_transitions": {},
            "market_transitions": {},
            "fundamental_durations": {},
            "market_durations": {},
        }

    f_labels = [argmax_state(b.fundamental) for b in beliefs]
    m_labels = [argmax_state(b.market) for b in beliefs]

    def shares(labels: list[str]) -> dict[str, float]:
        c = Counter(labels)
        n = len(labels)
        return {k: v / n for k, v in sorted(c.items())}

    def transitions(labels: list[str]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for a, b in zip(labels, labels[1:], strict=False):
            counts[f"{a}->{b}"] += 1
        return dict(sorted(counts.items()))

    def durations(labels: list[str]) -> dict[str, float]:
        if not labels:
            return {}
        spells: dict[str, list[int]] = defaultdict(list)
        cur = labels[0]
        length = 1
        for lab in labels[1:]:
            if lab == cur:
                length += 1
            else:
                spells[cur].append(length)
                cur = lab
                length = 1
        spells[cur].append(length)
        return {k: sum(v) / len(v) for k, v in sorted(spells.items())}

    return {
        "n": len(beliefs),
        "fundamental_share": shares(f_labels),
        "market_share": shares(m_labels),
        "fundamental_transitions": transitions(f_labels),
        "market_transitions": transitions(m_labels),
        "fundamental_durations": durations(f_labels),
        "market_durations": durations(m_labels),
    }
