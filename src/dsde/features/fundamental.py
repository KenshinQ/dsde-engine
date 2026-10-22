"""Fundamental feature helpers."""

from __future__ import annotations

from dsde.domain.schemas import FundamentalSnapshot


def announcement_fingerprint(snap: FundamentalSnapshot | None) -> str | None:
    """Identity of the latest fundamental announcement — used to avoid forged updates."""
    if snap is None:
        return None
    return f"{snap.period_end.isoformat()}|{snap.revision_id}|{snap.announcement_time.isoformat()}"
