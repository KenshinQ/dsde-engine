# DSDE Phase 0 — 完成清单

- 日期：2026-10-18 Asia/Shanghai
- 仓库：`/workspace/dsde-engine/`（本机 workspace，无远端）
- Spec：V0.1.1 Phase 0 / 开工单 `/workspace/dsde/phase0-kickoff.md`

## 验收勾选

- [x] Python 包 `dsde` + `pyproject.toml`（pytest / ruff / mypy 可选依赖）
- [x] 中文短 README；安装与 `doctor` / `pytest` 说明
- [x] `configs/*.yaml` 占位：data / states / decision / risk / validation / execution_a_share
- [x] Pydantic schema 校验（`position_deadband`、`min_elg_improvement`、`preservation_floor_annual=0.04`、主指标 vs B2/B4、`market_regime_gate`）
- [x] `domain/`：ObservationRecord / StateBelief（概率和≈1）/ ReturnDistribution / DecisionRecord
- [x] ReasonCode 含 POSITION_DEADBAND / MARKET_REGIME_GATE_BLOCKED / PRESERVATION_FLOOR_BINDING / TRANSACTION_COST_EXCEEDS_BENEFIT / NO_FEASIBLE_ACTION 等
- [x] Protocol 空壳：StateEstimator、ConditionalReturnEngine
- [x] 运行模式：synthetic_test / historical_research / asof_replay / shadow；synthetic 强制标签
- [x] CLI：`dsde --help`、`dsde doctor`、`dsde version`
- [x] 单元测试 ≥3；`python -m pytest` → **10 passed**
- [x] 实验助手：run_id / seed / config_hash
- [x] **未**实现 HMM / PIT / returns adapter / MPC / backtest

## 命令

```bash
cd /workspace/dsde-engine
source .venv/bin/activate   # 或: python3 -m venv .venv && pip install -e ".[dev]"
python -m pytest            # exit 0, 10 passed
dsde doctor
```

`dsde doctor`：configs schema-valid；deadband=0.03；preservation_floor_annual=0.04；market_regime_gate.gate_passed=False。

## 文件树（不含 .venv / caches）

```
./.gitignore
./PHASE0_DONE.md
./README.md
./configs/data.yaml
./configs/decision.yaml
./configs/execution_a_share.yaml
./configs/risk.yaml
./configs/states.yaml
./configs/validation.yaml
./pyproject.toml
./src/dsde/__init__.py
./src/dsde/cli/__init__.py
./src/dsde/cli/main.py
./src/dsde/config.py
./src/dsde/domain/__init__.py
./src/dsde/domain/enums.py
./src/dsde/domain/errors.py
./src/dsde/domain/schemas.py
./src/dsde/experiment/__init__.py
./src/dsde/experiment/ids.py
./src/dsde/returns/__init__.py
./src/dsde/returns/protocol.py
./src/dsde/states/__init__.py
./src/dsde/states/protocol.py
./tests/__init__.py
./tests/unit/__init__.py
./tests/unit/test_config.py
./tests/unit/test_protocols.py
./tests/unit/test_schemas.py
```

## Gate → Phase 1

接口稳定、测试通过后，才开 PIT 数据层。
