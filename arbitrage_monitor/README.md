# arbitrage_monitor

当前项目是 `finance/arbitrage_monitor` 的监控子系统，主交付范围以 [docs/requirements_codex_v1.md](docs/requirements_codex_v1.md) 为准。

## 当前能力

- 期指贴水监控
- 可转债负溢价和双低监控
- 舆情/热度监控
- 金属套利监控
- 期现溢价监控（外盘指数、crypto / 加密资产）
- SQLite 快照与冷却期恢复
- Streamlit 看板
- 飞书 / 企业微信通知队列

## 运行入口

- 调度器：`python core_scheduler.py`
- 看板：`streamlit run app_dashboard.py`
- 详细运行说明：见 [docs/run_guide.md](docs/run_guide.md)

## 配置说明

- 共享运行参数：`config/runtime_settings.json`
- 金属阈值：`config/metals_thresholds.json`
- 外盘指数 / crypto 期现溢价阈值：`config/premium_thresholds.json`
- 本机私密项：`.env`
- 本机覆盖项：`config/runtime_settings.local.json`、`config/metals_thresholds.local.json`、`config/futures_thresholds.local.json`、`config/premium_thresholds.local.json`

## 文档入口

- AI 协作入口： [AGENTS.md](AGENTS.md)
- 协作规则： [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)
- 文档基线： [docs/DOC_STANDARDS.md](docs/DOC_STANDARDS.md)
- 数据源台账： [docs/api_registry.md](docs/api_registry.md)
- 金属套利设计： [docs/metals_arbitrage_design.md](docs/metals_arbitrage_design.md)
- 外盘指数 / crypto 期现溢价设计： [docs/premium_arbitrage_design.md](docs/premium_arbitrage_design.md)
- 新增品种接入： [docs/new_module_integration_guide.md](docs/new_module_integration_guide.md)
- 结构治理计划： [docs/refactor_plan_20260423.md](docs/refactor_plan_20260423.md)
- 研究文档目录： [docs/research/](docs/research/)
- 审查与治理报告： [docs/reviews/](docs/reviews/)
