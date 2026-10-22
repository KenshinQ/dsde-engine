# DSDE Phase 2 — 完成清单

- 日期：2026-10-18 Asia/Shanghai
- 仓库：`/workspace/dsde-engine/`（本机，无远端 / 无 push）
- Spec：V0.1.1 §Phase 2 — 特征构建与状态估计器基线

## 验收勾选

- [x] 特征注册表 `FeatureRegistry` / `FeatureSpec`；滚动计算 + `RollingScaler`
- [x] 基本面 vs 市场特征分离（`FeatureSnapshot.fundamental` / `.market`）
- [x] 市场价量/广度特征全部 `requires_market_regime_gate=true`
- [x] Baseline A：`RuleStatStateEstimator`（规则/统计 → soft belief）
- [x] Baseline B：`FactorizedProbStateEstimator`（因子化概率，非重 HMM）
- [x] 多频率：无新公告时不伪造基本面更新（`filtering.fundamental_observation_changed`）
- [x] 诊断：状态占比、持续时间、转移计数（`belief_path_diagnostics`）
- [x] 欠识别时降级（`degraded` + warnings）
- [x] 固定 seed 可复现；特征 / scaler 无未来泄漏
- [x] 测试覆盖；**未**实现 HMM 全量、returns、MPC、backtest
- [x] `pytest` 全绿

## 关键 API

| API | 作用 |
|---|---|
| `dsde.features.FeatureBuilder` | PIT 安全特征快照 |
| `dsde.features.default_registry` | 默认特征注册（含 gate 标记） |
| `dsde.features.RollingScaler` | 仅训练集拟合的标准化 |
| `dsde.states.RuleStatStateEstimator` | 规则/统计基线 |
| `dsde.states.FactorizedProbStateEstimator` | 因子化概率估计器 |
| `dsde.states.belief_path_diagnostics` | 路径诊断 |

## 命令

```bash
cd /workspace/dsde-engine && source .venv/bin/activate
python -m pytest   # 31 passed
```

## Gate → Phase 3

概率合法、时间语义正确、降级可解释后，才开转移 / 情景。
