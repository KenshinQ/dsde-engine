# DSDE Phase 5 — 完成清单

- 日期：2026-10-18 Asia/Shanghai
- 仓库：`/workspace/dsde-engine/`（本机，无远端 / 无 push）
- Spec：V0.1.1 §Phase 5 — 单步决策、ELG 与约束仓位基线

## 验收勾选

- [x] 可配置目标仓位网格（`configs/decision.yaml` / `DecisionConfig.action_grid`）
- [x] 组合财富乘数 + 交易成本（bps × turnover）
- [x] 单步 expected log growth（样本与二元赌局闭式）
- [x] 约束优先级：可交易、无杠杆/仓位上限、保全尺 hook、deadband、成本门槛、市场 Regime 门禁
- [x] `DecisionRecord` + `CandidateActionScore` + 理由码
- [x] 手算二元赌局 ELG 测试
- [x] 成本覆盖优势 → HOLD / `TRANSACTION_COST_EXCEEDS_BENEFIT`
- [x] 无可行动作 → `NO_FEASIBLE_ACTION` 安全退化持有现仓
- [x] 研究出口 stubs：`evaluate_research_exit` vs B2/B4
- [x] **未**实现 MPC / 完整 backtest
- [x] `pytest` 全绿

## 关键 API

| API | 作用 |
|---|---|
| `dsde.decision.SingleStepDecisionEngine` | 单步网格决策 |
| `dsde.decision.expected_log_growth` / `binary_bet_elg` | ELG 目标 |
| `dsde.decision.evaluate_research_exit` | B2/B4 研究出口 |
| `dsde.decision.constraints.check_constraints` | 可行性检查 |
| `CandidateActionScore`（扩展 DecisionRecord） | 候选审计 |

## 命令

```bash
cd /workspace/dsde-engine && source .venv/bin/activate
python -m pytest
```

## Gate / 研究出口

单步手算与硬约束通过后，可用 `evaluate_research_exit` 对照 B2/B4；未过预先登记门槛则**可不进 Phase 6–7**。
