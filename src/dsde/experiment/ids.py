"""Experiment identity helpers: run_id, seed, config hash."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dsde.config import AppConfig


def make_run_id(*, prefix: str = "dsde", when: datetime | None = None) -> str:
    """Stable-looking opaque run id (timestamp + short uuid)."""
    ts = (when or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{ts}-{uuid.uuid4().hex[:8]}"


def resolve_seed(seed: int | None) -> int:
    """Return explicit seed or a deterministic default for Phase 0 placeholders."""
    if seed is None:
        return 0
    if seed < 0:
        raise ValueError("seed must be non-negative")
    return seed


def config_hash(config: AppConfig | dict[str, Any] | Path) -> str:
    """SHA256 of canonical JSON for an AppConfig, dict, or config directory path."""
    if isinstance(config, Path):
        from dsde.config import load_configs

        payload = load_configs(config).model_dump(mode="json")
    elif isinstance(config, AppConfig):
        payload = config.model_dump(mode="json")
    else:
        payload = config
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def experiment_meta(
    *,
    config: AppConfig,
    seed: int | None = None,
    run_mode: str = "synthetic_test",
) -> dict[str, Any]:
    """Bundle run metadata for ledger / research reports."""
    s = resolve_seed(seed)
    return {
        "run_id": make_run_id(),
        "seed": s,
        "config_hash": config_hash(config),
        "run_mode": run_mode,
        "phase": "0",
        "is_synthetic": run_mode == "synthetic_test",
    }
