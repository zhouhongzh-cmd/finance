# 开发过程文档 (DEV_PROCESS)

> 本文件记录项目开发过程中的关键变更与决策。
> 自 2026-03-15 起，项目主需求基线切换为 `docs/requirements_codex_v1.md`。
> 自 2026-04-26 起，观察项统一补充 `RESOLVED / DEFERRED` 状态；`DEFERRED` 表示已进入后续触发条件或 Phase 2，不阻断当前 MVP。

---
## [2026-03-16 18:20] - 数据保留清理落地与 cooldown 恢复测试补齐
- **📊 进度状态**: 100% - 把文档里提到的保留期治理真正落到了代码和测试里
- **🛠️ 实现方式**:
  - `config/settings.py` 新增 `DATA_RETENTION_DAYS`，默认 `30`
  - `core_scheduler.py` 新增 `retention_cleanup` 日度任务，默认每日 `00:10` 清理超期数据
  - `utils/db_manager.py` 增加按保留期清理 `alert_history` 与 `futures_margin_snapshot` 的接口
  - GUI 参数页同步新增“数据保留天数”，支持 `.env` 持久化与运行时热更新
  - `tests/test_integration.py` 补充了保留期清理测试和 cooldown 重启恢复 round-trip 测试
- **✅ 验证结果**:
  - 集成测试通过 `16/16`
  - `.env` 回写已覆盖 `DATA_RETENTION_DAYS`
  - cooldown 状态已验证“写入数据库 -> 恢复到内存缓存”链路
- **⚠️ 当前观察状态**:
  - `RESOLVED` ([2026-04-25](progress.md#1-mvp-status)): 保留期清理已覆盖报警历史、保证金快照、期指快照、转债快照、舆情快照、金属快照和期现溢价快照。
  - `DEFERRED` ([后续新增模块规则](new_module_integration_guide.md#4-新增独立模块的完整接入清单)): 若未来新增独立模块，仍需同步补对应 snapshot 清理接口和测试。

---
## [2026-03-16 17:40] - 调度拆分、舆情低频独立化与 SQLite 写锁加固
- **📊 进度状态**: 100% - 已把“统一总包扫描”进一步拆向策略级调度，并加固关键写路径
- **🛠️ 实现方式**:
  - `core_scheduler.py` 不再只依赖单个总包巡航/盯盘函数，改为按策略注册独立 job：
    - 期指巡航
    - 转债巡航
    - 期指盯盘
    - 转债盯盘
    - 舆情低频扫描
  - 新增 `SENTIMENT_INTERVAL_MINUTES`，默认 `3` 分钟，用于舆情的独立低频执行
  - 舆情策略不再被 A 股交易时段严格限制，允许在非交易时段继续低频运行
  - `DBManager` 为关键写路径补充显式写锁，串行化信号写入、通知状态回写、冷却期保存和保证金快照写入
  - GUI 参数页同步新增舆情频率可调项，并保持 `.env` 持久化 + 热更新
- **✅ 验证结果**:
  - 集成测试通过 `14/14`
  - 调度频率重载测试已覆盖新的独立 job 结构
  - 策略开关、阈值热更新和 `.env` 回写均已通过自动化测试
- **⚠️ 当前观察状态**:
  - `RESOLVED` ([2026-04-25](progress.md#1-mvp-status)): 调度层已按策略拆分独立 job，并支持模块级时钟配置。
  - `DEFERRED` ([2026-04-25](progress.md#1-mvp-status)): SQLite 单写队列仍保留为 P3 触发项，触发条件为写入频率持续超过 `100` 次/分钟。

---
## [2026-03-16 15:50] - 看板交互提速与通知状态回写闭环
- **📊 进度状态**: 100% - 当前看板交互模式与通知本地状态闭环已对齐代码事实
- **🛠️ 实现方式**:
  - `utils/notifier.py` 在至少一个通知渠道发送成功后，回写 `alert_history.notified = 1`
  - `models/signals.py` 增加 `alert_id`，用于把异步通知结果与入库记录关联
  - `utils/db_manager.py` 新增信号保存和通知状态回写接口，并为 SQLite 连接补充显式 `timeout`
  - `tests/test_integration.py` 补充断言，验证通知成功后数据库中的 `notified` 字段会被正确更新
  - `app_dashboard.py` 从“多标签整页重跑”调整为“单页切换 + 当前页手动刷新 + session_state 缓存”
  - 看板视觉风格向旧版 Tkinter GUI 靠拢：按模块分页、整表优先、每页独立刷新
- **✅ 验证结果**:
  - 集成测试通过 `10/10`
  - `Notifier` 集成测试已验证 `notified=1` 回写
  - 当前 Streamlit 看板切换页面时，不再同时触发期指、转债、舆情三条 live 链路重抓
- **⚠️ 当前观察状态**:
  - `RESOLVED` ([2026-04-25](progress.md#1-mvp-status)): 看板主读取路径已切到数据库快照，期指、金属、期现溢价、转债和舆情均支持最新快照读取。
  - `DEFERRED` ([Phase 2](progress.md#4-phase-2)): 更完整的监控面板和性能趋势分析仍属于后续规划。

---
## [2026-03-15 00:40] - 文档基线切换与全量归档
- **📊 进度状态**: 100% - 旧版项目已完成归档，文档主基线切换完成
- **🛠️ 实现方式**:
  - 对整个 `arbitrage_monitor` 目录进行了归档，文件位于 `finance/archives/arbitrage_monitor_20260315_002654.tar.gz`
  - 新建 `docs/requirements_codex_v1.md` 作为当前工程主需求书
  - 更新 `READ_ORDER.md`、`CONTRIBUTING.md`、`DOC_STANDARDS.md`、`api_registry.md`、`progress.md`，统一以新需求书为当前事实来源
  - 将 `requirements.md`、`code_review_report.md`、`progress_ai_*.md` 等文档定位为历史记录或兼容入口
- **⚠️ 当前仍未闭环状态**:
  - `RESOLVED` ([2026-04-25](progress.md#1-mvp-status)): 基础通知传输、异步入队和 `alert_history.notified` 本地回写已接入。
  - `DEFERRED` ([2026-04-25](progress.md#1-mvp-status)): 多渠道细粒度回执、失败重试和崩溃补发仍属于 Phase 2 通知链路增强。
- **⏭️ 下一步状态**:
  - `RESOLVED` ([requirements_codex_v1.md](requirements_codex_v1.md#10-通知语义)): 通知能力的当前边界已写入主需求基线。

---
## [2026-03-15 21:55] - 期指真实链路打通与文档刷新
- **📊 进度状态**: 100% - 期指现货备源、16 合约覆盖与真实链路验证完成
- **🛠️ 实现方式**:
  - `fetchers/ak_futures.py` 新增现货指数备源，主源 `ak.stock_zh_index_spot_em()` 失败时切换到直连新浪指数接口
  - 修复季月场景活跃合约生成逻辑，从 `12` 个合约补全为 `16` 个有效合约
  - 新增季月合约生成测试与现货指数备源解析测试
  - 同步刷新期指相关文档，明确主源、备源、真实环境行为和最新测试结果
- **✅ 验证结果**:
  - 本地集成测试通过 `10/10`
  - 当前活跃合约为 `IF/IH/IC/IM` 各 `4` 档，共 `16` 个
  - 真实环境下期指全链路可产出 `16` 条 live 数据
  - 当前 live 结果触发 `9` 个期指信号
- **⚠️ 当前观察状态**:
  - `DEFERRED` ([2026-04-25](progress.md#1-mvp-status)): 期指现货与保证金链路仍依赖外部站点，但已有备源，当前作为 P3 可接受风险持续监控。
  - `RESOLVED` ([api_registry.md](api_registry.md#1-数据源清单)): 期指数据源、备源和 fallback 口径已纳入数据源台账。

---
## [2026-03-15 21:30] - 期指保证金比例任务接入
- **📊 进度状态**: 100% - 期指模块已接入保证金比例快照与调度
- **🛠️ 实现方式**:
  - 新增 `fetchers/futures_margin.py`，维护 IF/IH/IC/IM 的官方保证金比例抓取逻辑
  - 新增 `futures_margin_snapshot` 表，持久化保证金比例历史快照
  - `fetchers/ak_futures.py` 在生成 `FuturesData` 时补充 `product_code`、`contract_multiplier`、`margin_ratio`、`notional_per_lot`、`margin_required_per_lot`
  - `core_scheduler.py` 新增保证金比例刷新任务，固定在每日 `09:00` 与 `00:00` 执行
  - 启动时若历史快照为空，系统会主动建立一份保证金基线
  - `strategies/futures_strategy.py` 的报警文案已补充保证金比例和单手占用信息
- **✅ 验证结果**:
  - 集成测试新增 `Futures Margin` 用例
  - 本地集成测试通过 `10/10`
  - 真实环境下中金所页面连接失败较多，但已能自动切换到中金财富期货的日度保证金公告
  - 当前实测可恢复 `IF=14%`、`IH=14%`、`IC=15%`、`IM=15%`
- **⚠️ 当前观察状态**:
  - `DEFERRED` ([2026-04-25](progress.md#1-mvp-status)): 官方规则页程序化访问可用性仍需持续监控，当前已有期货公司公告和默认最低保证金比例兜底。
  - `RESOLVED` ([api_registry.md](api_registry.md#1-数据源清单)): 保证金比例主备源已纳入数据源台账。

---
## [2026-03-15 20:45] - 可转债降级源升级研发落地
- **📊 进度状态**: 100% - 转债 fallback 从单纯 `ak.bond_zh_cov()` 升级为多层降级
- **🛠️ 实现方式**:
  - 主源仍为集思录 `bond_cb_jsl`
  - 当集思录返回 `<=30` 条时，优先切换到东方财富 `datacenter` 结构化接口
  - 在东方财富结构化字段基础上，本地恢复 `double_low` 并估算 `ytm`
  - 若东方财富 `datacenter` 失败，再回退到 `ak.bond_zh_cov()` 作为最后兜底
  - 补充了自动化测试，断言 fallback 可生成合理的 `double_low` 与 `ytm`
- **✅ 验证结果**:
  - 本地集成测试通过 `7/7`
  - 真实环境中，转债在线抓取可返回 `364` 条数据
  - 样本 `127113(长高转债)` 可恢复出 `price=100.0`、`premium_rate=-11.28`、`double_low=88.72`、`ytm=2.19`
- **⚠️ 研发结论状态**:
  - `RESOLVED` ([requirements_codex_v1.md](requirements_codex_v1.md#7-数据契约)): 可转债降级源字段恢复口径已写入当前数据契约和实现约束。
  - `DEFERRED` ([api_registry.md](api_registry.md#1-数据源清单)): 个别收益率字段与集思录逐值一致性仍按数据源差异处理，不阻断当前 MVP。

---
## [2026-03-13 23:28] - Code Review 问题批量修复
- **📊 进度状态**: 100% - 两份审查报告中 12 个问题已全部修复（排除通知相关 2 项）
- **🛠️ 实现方式**:
  - **Cooldown 重启恢复** (`core_scheduler.py`): 新增 `restore_cooldown_from_db()` 函数，在 `main()` 启动调度器之前从 `cooldown_state` 表恢复内存缓存，防止重启后报警轰炸
  - **UTC 时区修复** (`core_scheduler.py` + `app_dashboard.py`): 所有 SQLite 查询中的 `date('now')` 改为 `date('now','localtime')`，解决本地时间存储与 UTC 查询的日期边界偏移
  - **Retry 绕过修复** (`fetchers/ak_futures.py`): 移除现货指数获取的 `try-except return []`，让异常自然抛出以触发 tenacity `@retry` 重试
  - **JSL Cookie 检测修复** (`fetchers/ak_convertible.py`): 降级判断去掉 `not settings.JSL_COOKIE` 条件，仅凭返回数据量 ≤30 触发降级，覆盖 Cookie 失效场景
  - **雪球爬虫 Cookie** (`fetchers/sentiment_spider.py`): 新增 `_ensure_cookie()` 方法，支持 `.env` 配置 `XUEQIU_COOKIE` 或自动访问主页获取 Cookie
  - **Logger 重复初始化** (`utils/logger.py`): 移除模块级 `configure_logger()` 调用，仅由入口文件调用一次
  - **包规范** (`__init__.py`): 为 config、models、fetchers、strategies、utils、tests 6 个包目录创建空 `__init__.py`
  - **依赖补全** (`requirements.txt`): 显式添加 `pandas>=2.0.0`
  - **测试 fixture 补全**: `cb_mock.json` 添加 `price`/`ytm` 字段；`futures_sample.json` 添加 `days_to_maturity` 字段
  - **测试覆盖** (`tests/test_integration.py`): 补充 SentimentFetcher 和 SentimentStrategy 的 Mock 测试
  - **文档对齐** (`READ_ORDER.md`): 阅读顺序与 `DOC_STANDARDS.md` 统一为 requirements → CONTRIBUTING → api_registry → DOC_STANDARDS/progress
  - **`.gitignore`**: 新建文件，排除 `.env`、`*.db`、`__pycache__/` 等敏感/编译产物
- **⚠️ 遇到的问题与解决**:
  - PowerShell 不支持 `&&` 连接符 → 改用 `Cwd` 参数指定工作目录
  - 环境缺少 structlog/apscheduler 等依赖 → `pip install` 安装后测试通过
- **⏭️ 下一步状态**:
  - `RESOLVED` ([requirements_codex_v1.md](requirements_codex_v1.md#10-通知语义)): 飞书和企业微信 webhook 已接入实际 HTTP POST 发送。
  - `DEFERRED` ([2026-04-25](progress.md#1-mvp-status)): DB 连接池优化仍非当前瓶颈，长期高压写入优先评估单写队列。

---
## [2026-03-14 14:15] - 舆情数据源紧急切换与文档同步
- **📊 进度状态**: 100% - 舆情监控模块稳定性大幅提升
- **🛠️ 实现方式**:
  - **数据源切换** (`fetchers/sentiment_spider.py`): 鉴于雪球 API 近期反爬大幅升级（强制要求登录 `xq_a_token` 否则返回 40016），将主数据源切换为**东方财富人气榜 API**（POST 请求，无需认证，稳定性极高）。
  - **架构对齐**: 保留雪球作为备选/手动模式，但默认由东财提供全量 30 只热股数据。
  - **文档补全**: 当时同步更新了旧版 `docs/requirements.md` 与 `docs/api_registry.md`；当前已由 `docs/requirements_codex_v1.md` 接管主基线。
- **⚠️ 遇到的问题与解决**:
  - 发现雪球匿名访问返回 `{"error_code":"400016", "error_description":"请刷新页面登录帐号"}` -> 调研并切换至无需认证的东财 API。
  - `api_registry.md` 与实际代码逻辑（如 JSL 降级）不一致 -> 进行了闭环同步。
- **⏭️ 下一步状态**:
  - `DEFERRED` ([api_registry.md](api_registry.md#1-数据源清单)): 东方财富人气榜仍为舆情主源，更多舆情维度暂不进入当前 MVP。

