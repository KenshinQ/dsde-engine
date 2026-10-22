"""Unit tests: config loading and bad-config errors."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dsde.config import load_configs
from dsde.domain.errors import ConfigValidationError
from dsde.experiment.ids import config_hash, make_run_id, resolve_seed


def test_load_default_configs_ok() -> None:
    cfg = load_configs()
    assert cfg.decision.position_deadband == 0.03
    assert cfg.decision.min_elg_improvement == 0.0005
    assert cfg.risk.preservation_floor_annual == 0.04
    assert "half_kelly" in cfg.risk.kelly_note
    assert cfg.validation.primary_metric == "net_geometric_growth_vs_B2_B4"
    assert set(cfg.validation.baselines) == {"B2", "B4"}
    assert cfg.validation.market_regime_gate.enabled is True
    assert cfg.validation.market_regime_gate.gate_passed is False


def test_bad_config_raises(tmp_path: Path) -> None:
    # Copy minimal valid set then break decision.yaml
    src = Path(__file__).resolve().parents[2] / "configs"
    for name in (
        "data.yaml",
        "states.yaml",
        "decision.yaml",
        "risk.yaml",
        "validation.yaml",
        "execution_a_share.yaml",
    ):
        (tmp_path / name).write_text((src / name).read_text(encoding="utf-8"), encoding="utf-8")

    bad = {"position_deadband": -1.0, "min_elg_improvement": 0.0005}
    (tmp_path / "decision.yaml").write_text(yaml.dump(bad), encoding="utf-8")

    with pytest.raises(ConfigValidationError):
        load_configs(tmp_path)


def test_missing_config_dir_raises(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(ConfigValidationError):
        load_configs(missing)


def test_experiment_helpers() -> None:
    cfg = load_configs()
    rid = make_run_id(prefix="test")
    assert rid.startswith("test-")
    assert resolve_seed(None) == 0
    assert resolve_seed(42) == 42
    h1 = config_hash(cfg)
    h2 = config_hash(cfg)
    assert h1 == h2
    assert len(h1) == 64
