# 集成组 (AI-Integration) 开发进度报告

> 说明: 本文档为历史执行记录。当前项目主基线已切换到 `docs/requirements_codex_v1.md`。

> **更新时间**: 2026-04-25
> **最后同步**: `progress.md` 更新至 2026-04-25，默认 pytest 39 通过，兼容套件 77 通过
> **负责人**: AI-Integration (集成组)
> **状态**: ✅ 已完成（持续维护中）
> **模块职责**: L2 调度器 + L5 看板 + L6 运维部署

---

## 1. 负责文件清单

| 文件 | 层级 | 状态 |
|------|------|------|
| `core_scheduler.py` | L2 调度层 | ✅ 完成 |
| `app_dashboard.py` | L5 展现层 | ✅ 完成 |
| `Dockerfile` | L6 运维层 | ✅ 完成 |
| `.dockerignore` | L6 运维层 | ✅ 完成 |
| `docker-compose.yml` | L6 运维层 | ✅ 完成 |
| `tests/test_integration.py` | 测试 | ✅ 完成 |

---

## 2. 核心功能实现

### 2.1 调度器 (`core_scheduler.py`)

**功能**:
- ✅ APScheduler 定时任务管理
- ✅ 交易时段动态频率切换 (巡航 5 分钟/盯盘 30 秒)
- ✅ 线程池并发执行 (20 workers)
- ✅ 信号冷却期去重 (30 分钟)
- ✅ SQLite 持久化存储
- ✅ 飞书/微信通知队列框架
- ✅ 每日心跳报告 (9:25)
- ✅ 优雅关闭信号处理

**注册策略**:
- `Futures_Discount_Arbitrage` (期指贴水)
- `Convertible_Arbitrage` (转债负溢价 + 双低)
- `Sentiment_Heat_and_Risk` (舆情热度)
- `Metals_Arbitrage` (金属套利 - 黄金、白银)
- `Premium_Arbitrage` (期现溢价 - A50、加密资产)

**调度器演进**:
- ✅ 模块独立时钟（各策略可独立配置频率）
- ✅ GUI 可调（通过 config/runtime_settings.json）
- ✅ 交易时段动态频率切换 (巡航 5 分钟/盯盘 30 秒)

---

### 2.2 Streamlit 看板 (`app_dashboard.py`)

**功能**:
- ✅ 今日报警汇总统计
- ✅ 报警详情列表 (支持筛选)
- ✅ 最新信号快照
- ✅ 数据库状态监控
- ✅ 缓存优化 (@st.cache_data)

**页面布局**:
```
┌─────────────────────────────────────────┐
│  🎯 套利监控看板                         │
├──────────────┬──────────────────────────┤
│  侧边栏       │  主内容区                  │
│  - 系统状态   │  - 今日报警汇总            │
│  - 筛选条件   │  - 报警详情列表            │
│               │  - 最新信号快照            │
└──────────────┴──────────────────────────┘
```

---

### 2.3 容器化部署

**Dockerfile**:
- 基于 `python:3.11-slim`
- 健康检查 (SQLite 连接测试)
- 数据卷挂载 (`./data:/app/data`)
- 环境变量注入 (`.env`)

**docker-compose.yml**:
- 双服务架构 (监控器 + 看板)
- 网络隔离 (`monitor_net`)
- 自动重启策略 (`restart: always`)
- 端口映射 (`8501:8501`)

---

## 3. 端到端测试结果

> **当前状态**: 默认 pytest 39 通过；兼容套件 77 通过（2026-04-25）
> 当前测试文件已拆分到 `tests/test_*.py`，兼容套件显式包含 `tests/run_legacy_suite.py`

**历史测试时间**: 2026-03-12 13:39:56

```
============================================================
🧪 套利监控系统 - 端到端集成测试
============================================================

✅ DB Manager: OK
✅ Notifier: OK
✅ Futures Fetcher (Mock): 2 records
✅ Convertible Fetcher (Mock): 4 records
✅ Futures Strategy: 2 signals
✅ Convertible Strategy: 2 signals
✅ Scheduler Imports: OK
✅ Full Pipeline: 2 signals processed

============================================================
📊 测试结果：6 通过，0 失败 (历史记录)
============================================================
```

**测试覆盖**:
- ✅ 数据库读写
- ✅ 通知队列发送
- ✅ Mock 数据加载
- ✅ 策略信号生成
- ✅ 调度器导入
- ✅ 完整链路 (数据→策略→数据库→通知)
- ✅ 金属策略 (metals_strategy.py)
- ✅ 期现溢价策略 (premium_strategy.py)
- ✅ 配置文件解析 (futures_thresholds.json, metals_thresholds.json, premium_thresholds.json)

---

## 4. 排障避雷录 (TROUBLESHOOTING)

### 问题 1: 路径错误导致 Fixture 加载失败
**现象**: `FileNotFoundError: tests/fixtures/cb_mock.json`
**原因**: 测试脚本使用相对路径，但工作目录不确定
**解决**: 使用 `os.path.dirname(os.path.abspath(__file__))` 构建绝对路径

### 问题 2: sentiment_spider 缺少单例导出
**现象**: `ImportError: cannot import name 'sentiment_fetcher'`
**原因**: 其他 fetcher 都有单例导出，sentiment_spider 漏了
**解决**: 添加 `sentiment_fetcher = SentimentFetcher()`

### 问题 3: futures_strategy 循环变量名错误
**现象**: `AttributeError: 'list' object has no attribute 'discount_rate'`
**原因**: 参数名为 `data`，循环内也用 `data` 导致覆盖
**解决**: 循环变量改为 `item`

### 问题 4: Windows 控制台编码问题
**现象**: `UnicodeEncodeError: 'gbk' codec can't encode character`
**原因**: Windows 默认 GBK 编码无法显示 emoji
**解决**: 测试脚本添加 `sys.stdout = io.TextIOWrapper(..., encoding='utf-8')`

---

## 5. 部署指南

### 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填写 Webhook URL 和 JSL_COOKIE

# 运行调度器
python core_scheduler.py

# 运行看板 (新终端)
streamlit run app_dashboard.py
```

### Docker 部署

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f arbitrage_monitor

# 访问看板
# http://localhost:8501
```

---

## 6. 下一步行动

### Phase 2 待开发模块

> 注: 以下内容已根据 progress.md (2026-04-22) 更新

| 模块 | 文件 | 状态 |
|------|------|------|
| 加密期现链路增强 | 增加更多交易所切换预案 | ⏳ PENDING |
| 通知链路增强 | Phase 2 通知增强 | ⏳ PENDING |
| 宏观策略组 | `fetchers/ak_macro.py` + `strategies/macro_strategy.py` | ⏳ PENDING |
| 盈透套利组 | `fetchers/ib_margin.py` + `strategies/ib_strategy.py` | ⏳ PENDING |

**已完成的 Phase 2 项**:
- ✅ 金属套利 (ak_metals.py + metals_strategy.py)
- ✅ 期现溢价 (premium_fetcher.py + premium_strategy.py)
- ✅ 模块独立时钟 + GUI 可调

### 优化建议

1. **通知增强**: 实现完整的飞书富文本卡片组装
2. **监控增强**: 添加 Prometheus 指标导出
3. **回测功能**: 基于历史数据验证策略有效性
4. **配置热更新**: 支持不重启修改阈值

---

## 7. 系统就绪状态

| 层级 | 模块 | 状态 |
|------|------|------|
| L1 数据层 | 期指/转债/舆情/金属/期现 Fetcher | ✅ 6/6 完成 |
| L2 调度层 | 核心调度器（独立时钟+GUI可调） | ✅ 完成 |
| L3 策略层 | 期指/转债/舆情/金属/期现策略 | ✅ 5/6 完成 |
| L4 存储层 | SQLite WAL 管理器 | ✅ 完成 |
| L5 看板层 | Streamlit 看板 | ✅ 完成 |
| L6 运维层 | Docker 部署配置 | ✅ 完成 |

**系统已具备生产部署条件** ✅

**当前测试结果**: 默认 pytest 39 通过；兼容套件 77 通过
