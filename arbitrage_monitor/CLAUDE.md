# CLAUDE.md: arbitrage_monitor

先读 `AGENTS.md`。本文件只补充 Claude Code 使用时的项目记忆入口，避免与 Codex 规则分叉。

## 项目事实

- 项目类型：个人金融套利监控系统。
- 技术栈：Python、APScheduler、Streamlit、SQLite、akshare、ccxt。
- 主入口：`core_scheduler.py`、`app_dashboard.py`。
- 当前需求基线：`docs/requirements_codex_v1.md`。
- 当前运行指南：`docs/run_guide.md`。
- 开发事故与规则来源：`docs/error_journal.md`。

## 优先规则

- 最小改动，保留现有 `fetcher + strategy + snapshot + dashboard` 链路。
- Dashboard 默认快照优先；页面刷新不应隐式联网抓新。
- `.env` 和 `config/*.local.json` 是本机项，不提交。
- 修改数据源或 fallback 时同步 `docs/api_registry.md`。
- 修改数据契约、验收标准或通知语义时同步 `docs/requirements_codex_v1.md`。
- 提交前运行 `python3 scripts/check_standard.py`。
