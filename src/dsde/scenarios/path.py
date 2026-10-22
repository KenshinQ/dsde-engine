"""Path utilities."""

from __future__ import annotations

from dsde.domain.schemas import ScenarioPath


def path_state_at(path: ScenarioPath, step: int) -> tuple[str, str]:
    """Return (fundamental, market) at step index (0 = start)."""
    if step < 0 or step >= path.path_steps:
        raise IndexError(step)
    return path.fundamental_path[step], path.market_path[step]
