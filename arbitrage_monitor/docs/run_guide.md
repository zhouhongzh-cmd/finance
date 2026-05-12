# 运行指南

> 适用目录: `arbitrage_monitor/`
> 当前主入口:
> - 调度器: `core_scheduler.py`
> - 看板: `app_dashboard.py`
> - 容器编排: `docker-compose.yml`

## 1. 结论

本项目推荐两种运行方式:

- 本机开发调试: 直接用 Python 环境启动调度器和 Streamlit 看板。
- 持续运行: 用 Docker Compose 同时拉起调度器和看板。

最少需要准备:

- `.env`: 本机项，例如 Webhook、Cookie 和 `IB_*` 连接参数。
- `config/runtime_settings.json`: 共享运行参数。
- `config/futures_thresholds.json`: 期指阈值。
- `config/metals_thresholds.json`: 金属阈值。
- `config/premium_thresholds.json`: A50 和加密期现溢价阈值。

本机覆盖文件 `config/*.local.json` 由参数页写入，不建议提交。

## 2. 本机直跑

从本目录执行:

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

按需编辑 `.env`:

- `FEISHU_WEBHOOK_URL`
- `WECOM_WEBHOOK_URL`
- `JSL_COOKIE`
- `XUEQIU_COOKIE`
- `IB_DEFAULT_PROFILE`
- `IB_REMOTE_HOST` / `IB_REMOTE_PORT` / `IB_REMOTE_CLIENT_ID`
- `IB_LOCAL_HOST` / `IB_LOCAL_PORT` / `IB_LOCAL_CLIENT_ID`
- `IB_GATEWAY_TIMEOUT_SECONDS`

启动调度器:

```bash
source .venv/bin/activate
python core_scheduler.py
```

新开终端启动看板:

```bash
source .venv/bin/activate
streamlit run app_dashboard.py
```

默认访问:

- `http://localhost:8501`

## 3. Docker Compose 运行

```bash
cp .env.example .env
docker compose up -d --build
```

服务:

- `arbitrage_monitor`: 运行 `python core_scheduler.py`
- `streamlit_dashboard`: 运行 `streamlit run app_dashboard.py --server.address 0.0.0.0 --server.port 8501`

查看状态:

```bash
docker compose ps
docker compose logs -f arbitrage_monitor
docker compose logs -f streamlit_dashboard
```

停止:

```bash
docker compose down
```

## 4. 验证步骤

先看数据库是否生成:

```bash
ls -lh data/monitor_history.db
```

再检查核心表:

```bash
sqlite3 data/monitor_history.db ".tables"
sqlite3 data/monitor_history.db "SELECT COUNT(*) FROM alert_history;"
sqlite3 data/monitor_history.db "SELECT COUNT(*) FROM job_run_status;"
```

最后打开看板:

- `http://localhost:8501`

如果只验证代码和测试:

```bash
python3 scripts/check_standard.py
python3 -m pytest -q
python3 -m compileall -q .
```

如果希望提交前一次跑完标准检查和两类 pytest 口径:

```bash
python3 scripts/check_standard.py --pytest --legacy-pytest
```

如果需要单独验证 IB Gateway 连通与 `HSI` 行情:

```bash
python3 scripts/test_ib_gateway_api.py --profile remote --with-hsi
python3 scripts/test_ib_gateway_api.py --profile local --with-hsi
```

## 5. 配置分工

`.env` 只放本机环境相关配置。缺少 Webhook 时程序仍可运行，但不会实际发送到对应渠道；缺少有效 `JSL_COOKIE` 时，可转债数据可能降级；缺少可用 `IB_*` 配置时，外盘指数会回退到非 IB 源，`HSI` 则可能直接跳过。

`config/runtime_settings.json` 放共享运行参数，包括模块开关、巡航/盯盘频率、时间窗口和通用阈值。调度器运行中会定期同步。

`config/futures_thresholds.json`、`config/metals_thresholds.json`、`config/premium_thresholds.json` 分别放期指、金属和期现溢价阈值。参数设置页会把本机覆盖写入对应 `.local.json`。

## 6. 常见问题

看板能打开但没有数据:

- 确认调度器正在运行。
- 确认 `data/monitor_history.db` 已生成。
- 确认数据源 Cookie 或网络访问可用。

Docker 启动后页面打不开:

- 检查 `docker compose ps`。
- 检查 `streamlit_dashboard` 日志。
- 确认本机 `8501` 端口未被占用。

修改参数后没生效:

- 改 `.env` 通常需要重启进程或容器。
- 改 `config/runtime_settings.json` 通常会被调度器定期同步。
- 改阈值 JSON 后，策略下一轮运行或页面刷新时才会使用新值。
