# AGENTS.md: arbitrage_monitor

## 结论

本项目是 `finance/arbitrage_monitor` 的 Python + Streamlit + SQLite 监控子系统。修改时遵循最小改动原则，优先保持现有框架、配置分工、快照优先和测试口径稳定。

## 开始前必读

1. `docs/requirements_codex_v1.md`：当前需求边界、数据契约和验收标准。
2. `docs/CONTRIBUTING.md`：协作规则、核心文件、文档同步要求。
3. `docs/api_registry.md`：真实数据源、fallback 和状态。
4. `docs/run_guide.md`：本机运行和验证入口。
5. `docs/error_journal.md`：已知事故、规则来源和待观察项。

`PLAN.md` 若存在，仅作为短期接力或治理计划参考，不得当作正式项目状态；正式状态以 `docs/progress.md` 和当前基线文档为准。

## 当前架构边界

- 主入口：`core_scheduler.py`、`app_dashboard.py`。
- 数据链路：`fetchers/*` -> `strategies/*` -> `utils/db_manager.py` -> `app_dashboard.py`。
- 共享配置：`config/runtime_settings.json`、`config/futures_thresholds.json`、`config/metals_thresholds.json`、`config/premium_thresholds.json`。
- 本机私密项：`.env`。
- 本机覆盖项：`config/*.local.json`，不得提交。
- Dashboard 默认走 SQLite 快照；“强制抓新”才允许联网并回写快照。

## 不变量

- 所有策略返回 `list[Signal]`。
- `fetch_live()` 与 `fetch_from_fixture()` 返回同一数据契约。
- 单个模块失败不能破坏其他 MVP 模块运行。
- 新增 snapshot 表必须纳入 `DATA_RETENTION_DAYS` 清理和测试。
- SQLite 查询“今日”必须使用本地时间语义，避免裸 `date('now')`。
- 通知状态不得把“已入队”写成“已送达”。
- 数据源、fallback 或限流结论变化必须同步 `docs/api_registry.md`。
- 需求边界、验收标准、通知语义或数据契约变化必须优先同步 `docs/requirements_codex_v1.md`。

## 禁止事项

- 不提交 `.env`、`config/*.local.json`、`*.db`、`*.db-wal`、`*.db-shm`。
- 不删除已通过的测试用例来让检查变绿。
- 不把规划中的模块写成当前已完成能力。
- 不在历史文档里埋新的当前架构决策。
- 不顺手重写 Streamlit 框架或拆大目录，除非当前任务明确要求。

## 验证

提交前优先运行：

```bash
python3 scripts/check_standard.py
python3 -m pytest -q
python3 -m pytest -q tests/*.py
```

如果只改文档，可运行 `python3 scripts/check_standard.py --skip-compileall` 并说明未跑 pytest。
