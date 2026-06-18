# Error Journal

> 目的：记录开发事故、审查发现和规则来源。这里不替代 `排障总结/`；运行环境或现场故障仍写入 `排障总结/`。

## 规则

- 只记录已经发生或已在审查中复现的问题，不写假想风险。
- 每条记录要能追溯到来源文档、代码位置或验证命令。
- 形成稳定规则后，同步到 `AGENTS.md` 或 `scripts/check_standard.py`。
- 状态使用 `OPEN / RESOLVED / DEFERRED / WATCH`。

## 记录

| 日期 | 来源 | 问题 | 根因 | 当前状态 | 后续规则 |
| --- | --- | --- | --- | --- | --- |
| 2026-03-13 | `docs/DEV_PROCESS.md` | SQLite 今日查询出现 UTC 日期边界偏移 | 使用裸 `date('now')`，与本地时间存储不一致 | RESOLVED | `check_standard.py` 拦截裸 `date('now')` |
| 2026-03-14 | `docs/DEV_PROCESS.md` | 雪球匿名访问返回登录错误 | 外部接口反爬升级，强制 token | RESOLVED | 数据源变化必须同步 `api_registry.md` |
| 2026-04-23 | `排障总结/2026-04-23_dashboard_refresh_db_path.md` | Dashboard 刷新显示后表格不更新 | 残留调度器进程写入旧 DB，且刷新显示只读快照不联网 | RESOLVED | 区分“刷新显示”和“强制抓新” |
| 2026-04-25 | `docs/reviews/code_review_report_20260425.md` | 默认 pytest 曾被非 Python 测试产物阻断 | 测试收集范围被历史输出文件污染 | RESOLVED | 保留默认 pytest 与 `tests/*.py` 两类验证口径 |
| 2026-04-25 | `docs/reviews/code_review_report_20260425.md` | 测试曾直接写默认运行数据库 | `DBManager()` 默认生产路径且有单例状态 | RESOLVED | 会写库测试必须隔离临时 DB |
| 2026-04-25 | `docs/reviews/code_review_report_20260425.md` | Docker healthcheck 只能证明 SQLite 可打开 | 健康检查未覆盖调度器心跳或 Dashboard HTTP | DEFERRED | 进入部署增强时处理 |
| 2026-04-26 | 当前检查 | `alert_history` 当前按 `asset` 去重 | 当前实现语义如此，是否改为 `strategy+asset` 需要先定设计 | WATCH | 不直接脚本阻断，先人工确认语义 |
| 2026-06-18 | linux 主机部署 | `docker build` 卡死，新代码无法部署 | 主机外网受限，Docker Hub / `deb.debian.org` / `pypi.org` 均不可达 | RESOLVED | 基础镜像从 `docker.m.daocloud.io` 拉取后 `docker tag` 成 `python:3.11-slim`；删除多余的 apt 装 curl；pip 用 `--build-arg PIP_INDEX_URL` 指国内源 |
| 2026-06-18 | linux 主机部署 | 容器内 yfinance 代理失效，A50/外盘指数取价失败 | bridge 网络下 `127.0.0.1` 指向容器自身，连不到仅监听 loopback 的宿主 Clash | RESOLVED | 容器改用 `--network host`；代理地址抽成环境变量 `YFINANCE_PROXY`（见 `premium_arbitrage_design.md` §3.1） |
| 2026-06-18 | linux 主机部署 | yfinance 取价频繁 `YFRateLimitError`（HTTP 429） | Yahoo 对默认 UA / crumb 端点限流 | RESOLVED | `_fetch_yfinance_price` 会话带浏览器 `User-Agent` 并退避重试（2s/4s） |
