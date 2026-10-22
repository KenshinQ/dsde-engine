# DSDE Phase 4 — 完成清单

- 日期：2026-10-18 Asia/Shanghai
- 仓库：`/workspace/dsde-engine/`（本机，无远端 / 无 push）
- Spec：V0.1.1 §Phase 4 — 条件收益引擎与估值模型适配器

## 验收勾选

- [x] `ConditionalReturnEngine` / `ValuationAdapter` 协议
- [x] `SyntheticReturnEngine`（仅 `synthetic_test`，强制 `is_synthetic=True`）
- [x] 可替换估值适配器：`StubFundamentalValuationAdapter`
- [x] `AdapterConditionalReturnEngine`：研究路径；缺 adapter **不**静默切合成
- [x] 收益口径：`ReturnDefinition`（gross/net、股息、费用 bps）
- [x] 分布摘要 + 尾部：mean / ELG / quantiles / CVaR
- [x] 条件化于 price × fundamental belief × market belief（+ optional scenario paths）
- [x] 价格下跌不会机械抬升 edge；恶化基本面 + 小幅降价可恶化赔率
- [x] 样本 provenance → scenario_ids / parameter_draw_ids / model_versions
- [x] **未**实现 MPC / backtest
- [x] `pytest` 全绿

## 关键 API

| API | 作用 |
|---|---|
| `dsde.returns.SyntheticReturnEngine` | 测试专用合成收益引擎 |
| `dsde.returns.AdapterConditionalReturnEngine` | 适配器驱动条件收益 |
| `dsde.returns.StubFundamentalValuationAdapter` | 可插拔估值 stub |
| `dsde.returns.build_default_research_engine` | 显式挂 stub 的工厂 |
| `dsde.domain.schemas.ReturnDefinition` / 扩展 `ReturnDistribution` | 口径与摘要 |

## 命令

```bash
cd /workspace/dsde-engine && source .venv/bin/activate
python -m pytest
```

## Gate → Phase 5

收益分布数值与口径可审计后，才开单步 ELG / 约束仓位。
