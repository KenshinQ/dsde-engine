"""Multi-frequency update helpers: no forged fundamental observations."""

from __future__ import annotations

from dsde.features.builder import FeatureSnapshot
from dsde.features.fundamental import announcement_fingerprint


def fundamental_observation_changed(
    prev_fp: str | None, features: FeatureSnapshot
) -> bool:
    """True only when a new announcement/revision is visible in the feature snapshot."""
    cur = None
    if features.fundamental_announcement_time is not None:
        cur = (
            f"{features.fundamental_period_end}|"
            f"{features.fundamental_revision_id}|"
            f"{features.fundamental_announcement_time.isoformat()}"
        )
    if prev_fp is None and cur is None:
        return False
    return cur != prev_fp


def fingerprint_from_features(features: FeatureSnapshot) -> str | None:
    if features.fundamental_announcement_time is None:
        return None
    return (
        f"{features.fundamental_period_end}|"
        f"{features.fundamental_revision_id}|"
        f"{features.fundamental_announcement_time.isoformat()}"
    )


# re-export for clarity
__all__ = [
    "announcement_fingerprint",
    "fingerprint_from_features",
    "fundamental_observation_changed",
]
