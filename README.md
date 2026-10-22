# DSDE — Dynamic State-Contingent Decision Engine

**阶段：** Phase 0–5（+ 单步 ELG 决策）  
**规格：** `/workspace/dsde/DSDE-V0.1-spec.md` V0.1.1  
**模式：** 仅 `synthetic_test`；不下单、不发投资结论

## 这是什么

分层、概率化、可审计的动态投资决策引擎骨架：状态估计 / 条件收益 / 仓位三模块分离。  
Phase 0 **只**提供配置 schema、领域实体、协议空壳、CLI `doctor` 与单元测试；不实现 HMM、PIT、MPC、回测。

## 安装

```bash
cd /workspace/dsde-engine
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## 常用命令

```bash
dsde --help
dsde doctor                    # 加载 configs/ 并校验 schema
python -m pytest               # 单元测试
ruff check src tests           # 可选 lint
mypy src                       # 可选类型检查
```

## 目录要点

- `configs/` — YAML 占位 + Pydantic 校验
- `src/dsde/domain/` — 实体与理由码
- `src/dsde/states/`、`returns/` — Protocol 空壳
- `src/dsde/cli/` — `dsde doctor`
- `tests/unit/` — schema / 概率和 / 非法配置

## Phase 5 单步决策

`SingleStepDecisionEngine` / `evaluate_research_exit` (B2/B4)

## Phase 4 条件收益

`SyntheticReturnEngine` / `AdapterConditionalReturnEngine` / `StubFundamentalValuationAdapter`

## Phase 3 转移/情景

`TransitionEstimator` / `ScenarioGenerator`（estimated vs assumption 分离）

## Phase 2 特征/状态

`FeatureBuilder` / `RuleStatStateEstimator` / `FactorizedProbStateEstimator`

## Phase 1 PIT

```bash
python -c "from dsde.data.synthetic import write_synthetic_bundle; write_synthetic_bundle('data/synthetic')"
python -m pytest tests/unit/test_pit_phase1.py tests/leakage -q
```

关键 API：`PitStore`、`AsOfQuery`、`FileJsonProvider`、`write_synthetic_bundle`。

## 非目标（Phase 0–1）

不实现状态估计、收益 adapter、MPC、A 股回测投资结论；合成输出必须带 `synthetic` 标签。
