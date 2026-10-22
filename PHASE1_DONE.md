# DSDE Phase 1 — 完成清单

- 日期：2026-10-18 Asia/Shanghai
- 仓库：`/workspace/dsde-engine/`（本机，无远端 / 无 push）
- Spec：V0.1.1 §Phase 1 — PIT 数据层与时间回放

## 验收勾选

- [x] ObservationRecord 对齐 PIT 字段；扩展 PriceBar / FundamentalSnapshot / CorporateAction / TradingCalendar / InstrumentMeta
- [x] period_end 与 announcement_time 分离保存
- [x] Provider-agnostic 接口 `DataProvider` + 文件适配器 `FileJsonProvider`
- [x] `PitStore` + `AsOfQuery`：永不返回 `available_at > as_of`
- [x] 修订历史：较早 as-of 看到旧 revision
- [x] 导入质量报告 `QualityReport`（来源、记录数、缺失/重复率、质量标记）
- [x] 合成数据集 `data/synthetic/` + `write_synthetic_bundle`
- [x] 泄漏测试：未来数据注入不改变较早 PIT 查询
- [x] 信号时间 vs 执行时间 schema（`SignalExecutionTiming` / DecisionRecord 字段）
- [x] 测试覆盖停牌、退市、公司行动、缺失、重复
- [x] **未**实现 HMM / returns adapter / MPC / backtest
- [x] `pytest` 全绿

## 关键 API

| API | 作用 |
|---|---|
| `dsde.data.PitStore` | 内存 PIT 存储与 ingest |
| `dsde.data.AsOfQuery` | as-of / replay 查询 |
| `dsde.data.DataProvider` | 来源无关 Protocol |
| `dsde.data.FileJsonProvider` | JSON/JSONL 文件适配器示例 |
| `dsde.data.write_synthetic_bundle` | 写出合成夹具 |
| `dsde.data.build_quality_report` | 导入质量报告 |

## 命令

```bash
cd /workspace/dsde-engine
source .venv/bin/activate
python -m pytest          # 22 passed (Phase0+1)
dsde doctor
```

## Gate → Phase 2

PIT 泄漏测试通过后，才开特征 / 状态估计器。
