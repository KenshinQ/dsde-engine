# DSDE Phase 3 — 完成清单

- 日期：2026-10-18 Asia/Shanghai
- 仓库：`/workspace/dsde-engine/`（本机，无远端 / 无 push）
- Spec：V0.1.1 §Phase 3 — 状态转移、参数不确定性与情景生成

## 验收勾选

- [x] 转移估计器 + Dirichlet 收缩（`TransitionEstimator`）
- [x] 行随机（row-stochastic）矩阵校验
- [x] 参数不确定性：bootstrap 抽样（与过程噪声 RNG 分离）
- [x] `ScenarioGenerator`：可配置 N、步数；资源上限 `max_paths` / `max_steps`
- [x] `estimated_probability` vs `assumption_scenario` 分离（假设情景权重 0，不混入统计概率）
- [x] 路径 provenance（参数 draw id、双 RNG seed、观测数、降级警告）
- [x] 路径起始抽样来自输入 belief；belief probs 写入路径
- [x] 稀有状态 / 少样本：收缩、警告、sticky fallback
- [x] 固定 seed 可复现；换 seed 改变样本
- [x] 因子化基本面/市场链；**无**重联合 HMM / returns / MPC / backtest
- [x] `pytest` 全绿

## 关键 API

| API | 作用 |
|---|---|
| `dsde.transitions.TransitionEstimator` | 收缩转移估计 / assumption 身份矩阵 |
| `dsde.transitions.bootstrap_transition_samples` | 参数 bootstrap |
| `dsde.scenarios.ScenarioGenerator` | 情景路径批量生成 |
| `dsde.domain.schemas.TransitionMatrix` | 行随机转移矩阵 |
| `dsde.domain.schemas.ScenarioPath` / `ScenarioBatch` | 路径与批次 |

## 命令

```bash
cd /workspace/dsde-engine && source .venv/bin/activate
python -m pytest
```

## Gate → Phase 4

路径可复现、概率守恒、低样本不虚报精度后，才开条件收益引擎。
