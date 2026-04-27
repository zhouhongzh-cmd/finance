# 套利监控系统代码审查与文档改进报告

> 生命周期状态: HISTORICAL_REVIEW
> 原路径: `finance/code_review_report.md`
> 归档时间: 2026-04-28
> 说明: 部分结论已由 `docs/reviews/code_review_report_20260423_codex_reply.md` 和 `docs/reviews/code_review_report_20260425.md` 复核或修正；不得直接当作当前待办清单。
>
> 审查时间: 2026-04-23
> 审查范围: `arbitrage_monitor` 全量代码与文档

---

## 一、代码问题（按严重程度排列）

### 🔴 严重问题（影响正确性或数据安全）

#### 1. [_get_job_lock](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#294-298) 存在竞态条件
[core_scheduler.py:L294-297](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#L294-L297)

```python
def _get_job_lock(job_name: str) -> threading.Lock:
    if job_name not in job_locks:
        job_locks[job_name] = threading.Lock()
    return job_locks[job_name]
```

**问题**：`job_locks` 字典的读写不是原子操作。在多线程环境中，两个线程可能同时检测到 `job_name not in job_locks`，各自创建一个新 Lock 实例，导致锁失效。

**建议**：使用 `defaultdict(threading.Lock)` 或在外层加锁：

```python
_job_locks_meta = threading.Lock()

def _get_job_lock(job_name: str) -> threading.Lock:
    with _job_locks_meta:
        if job_name not in job_locks:
            job_locks[job_name] = threading.Lock()
        return job_locks[job_name]
```

#### 2. [save_signal](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/db_manager.py#594-618) 每次保存前删除同一 asset 的全部历史
[db_manager.py:L594-617](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/db_manager.py#L594-L617)

```python
conn.execute(
    "DELETE FROM alert_history WHERE asset = ?",
    (signal.asset,),
)
```

**问题**：这会删除同一标的的**所有**策略的报警记录，而非"同一策略+标的"。例如 `IF2503` 同时触发贴水策略和升水策略时，后写入的会删掉先写入的。虽然 [requirements_codex_v1.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/requirements_codex_v1.md) 第 11.3 节说"只保留同一 asset 的最新一条"，但这导致不同策略之间互相覆盖，与冷却期按 `strategy_name:asset` 区分的设计不一致。

**建议**：改为按 `strategy + asset` 去重，或至少在文档中明确这是预期行为。

#### 3. 巡航模式函数中存在冗余/不可达代码
[core_scheduler.py](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py)

以 [run_futures_cruise_mode](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#451-469) 为例 (L451-468)：

```python
if not settings.ENABLE_FUTURES_MONITOR:          # L454
    ...
    return {"status": "DISABLED"}
...
if settings.ENABLE_FUTURES_MONITOR:               # L462 ← 冗余！
    return run_strategy_task(...)
return {"status": "DISABLED"}                     # L466 ← 不可达
```

L454 已检查 `not ENABLE_FUTURES_MONITOR` 且返回，所以 L462 的 [if](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/notifier.py#11-156) 永远为 True，L466 永远不可达。同样的问题出现在：
- [run_convertible_cruise_mode](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#471-489) (L471-488)
- [run_sentiment_low_freq_mode](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#491-509) (L491-508)
- [run_metals_cruise_mode](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#511-529) (L511-528)
- [run_futures_watch_mode](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#531-549) (L531-548)
- [run_convertible_watch_mode](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#551-569) (L551-568)
- [run_metals_watch_mode](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#571-589) (L571-588)

**建议**：将冗余的 `if settings.ENABLE_*_MONITOR:` 判断去掉，直接 `return run_strategy_task(...)`。

#### 4. [.env](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/.env) 文件不在 [.gitignore](file:///c:/Users/hikiwa/Desktop/coding/finance/.gitignore) 顶层
[.gitignore](file:///c:/Users/hikiwa/Desktop/coding/finance/.gitignore)

根文件 [.gitignore](file:///c:/Users/hikiwa/Desktop/coding/finance/.gitignore) 只有 55 字节，很可能不包含 [.env](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/.env)。而 [arbitrage_monitor/.gitignore](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/.gitignore) 中有 [.env](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/.env)。如果有人在根目录执行 `git add -A`，可能会意外提交 [.env](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/.env)。

**建议**：确保顶层 [.gitignore](file:///c:/Users/hikiwa/Desktop/coding/finance/.gitignore) 也包含 [.env](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/.env) 规则。

#### 5. `Notifier.__init__` 在模块导入时立即创建 httpx 客户端和工作线程
[notifier.py:L157](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/notifier.py#L157)

```python
notifier = Notifier()
```

这意味着即使只是 `import notifier`（如在测试、dashboard 中），也会创建 httpx 连接池和 daemon 线程。这在测试时会产生意外副作用。

**建议**：使用延迟初始化（lazy init），或在测试中使用 mock。

---

### 🟡 中等问题（影响健壮性或可维护性）

#### 6. 浮点数精确比较导致快照写入判断不准
[db_manager.py](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/db_manager.py) 中多处使用 `!=` 比较浮点数：

```python
float(snapshot.price) != latest["price"],
float(snapshot.discount_rate) != latest["discount_rate"],
```

浮点数在 Python ↔ SQLite 之间来回转换时容易丢失精度（如 `0.1 + 0.2 != 0.3`），导致本应跳过的快照被误判为"值变化"而重复写入。

**建议**：改为容差比较，如 `abs(a - b) > 1e-8`，或在存取时统一精度 (`round`)。

#### 7. [send_heartbeat](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#627-666) 在函数体内做延迟 import
[core_scheduler.py:L638, L649](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#L638)

```python
import os
...
from models.signals import Signal
```

这两个 import 应该放在文件顶部,不应在函数体内延迟导入，除非有明确的循环依赖需要规避。

#### 8. [DBManager](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/db_manager.py#19-1578) 单例模式但 [__init__](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/notifier.py#13-18) 每次都执行
[db_manager.py:L25-31](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/db_manager.py#L25-L31)

[__new__](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/db_manager.py#25-32) 实现了单例，但 [__init__](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/notifier.py#13-18) 不存在——目前靠 [_init_db](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/db_manager.py#33-232) 在 [__new__](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/db_manager.py#25-32) 中手动调用。这种模式可行但脆弱（如果有人添加 [__init__](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/notifier.py#13-18)，每次创建实例都会执行）。

**建议**：使用显式的 `get_instance()` 工厂方法或 `borg` 模式。

#### 9. `config/premium_thresholds.local.json` 未加入 [.gitignore](file:///c:/Users/hikiwa/Desktop/coding/finance/.gitignore)
[.gitignore](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/.gitignore#L11-L13)

```
config/runtime_settings.local.json
config/metals_thresholds.local.json
config/futures_thresholds.local.json
```

缺少 `config/premium_thresholds.local.json`，可能导致意外提交敏感的本地覆盖配置。

#### 10. [requirements.txt](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/requirements.txt) 包含未使用的依赖
[requirements.txt](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/requirements.txt)

```
ib_insync>=0.9.8
```

`ib_insync` 属于 Phase 2 的盈透策略依赖，当前 MVP 未使用。它会增加 Docker 镜像体积和构建时间。`forex-python` 也应验证是否仍在使用。

**建议**：移除未使用的依赖，或拆分为 [requirements.txt](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/requirements.txt) 和 `requirements-dev.txt`。

#### 11. Dashboard 在缓存刷新期间仍网络抓取
[app_dashboard.py:L202-206](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/app_dashboard.py#L202-L206)

```python
@st.cache_data(ttl=30)
def fetch_futures_live_view() -> tuple[pd.DataFrame, pd.DataFrame]:
    data = futures_fetcher.fetch_live()   # ← 每次缓存过期就联网
    db_manager.save_futures_live_snapshots(data)
    ...
```

这些 `fetch_*_live_view` 函数在缓存过期后直接联网抓取，但它们的唯一调用场景是"强制抓新"按钮。缓存过期后如果 Streamlit 重新渲染页面（如用户切换控件），也会意外触发联网。

#### 12. [CryptoFundingData](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/models/market_data.py#47-52) 已定义但未使用
[models/market_data.py:L47-51](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/models/market_data.py#L47-L51)

```python
@dataclass
class CryptoFundingData(BaseMarketData):
    """资金费率快照"""
    funding_rate: float
    predicted_rate: Optional[float] = None
```

这个模型在整个项目中没有被引用。

---

### 🟢 轻微问题（代码风格与最佳实践）

#### 13. `SYNCABLE_RUNTIME_FIELDS` 与模块级配置字段列表过长且手动维护
[config/settings.py:L22-104](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/config/settings.py#L22-L104)

80+ 个手写字段名极易在新增模块时遗漏。

**建议**：从 [Settings](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/config/settings.py#107-239) 模型字段自动生成，排除 `LOCAL_ONLY_FIELDS` 即可。

#### 14. `any()` 传入了元组而非可迭代的条件表达式
[core_scheduler.py:L170-188](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#L170-L188)

```python
return any(
    (
        _is_day_session_active(...),
        _is_day_session_active(...),
        _is_night_session_active(...),
    )
)
```

`any()` 会收到一个预先计算的元组，意味着所有三个函数都会被调用（无短路求值）。虽然功能正确，但不符合 `any()` 的惯用写法。

**建议**：去掉内层括号，改为生成器表达式，实现短路求值。

#### 15. [Dockerfile](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/Dockerfile) 只启动 [core_scheduler.py](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py)，看板需额外配置
[Dockerfile:L28](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/Dockerfile#L28)

```dockerfile
CMD ["python", "core_scheduler.py"]
```

看板 [app_dashboard.py](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/app_dashboard.py) 需要通过 `streamlit run` 启动，但 Docker 中没有配置。[docker-compose.yml](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docker-compose.yml) 应提供看板服务的独立容器定义。

---

## 二、文档问题与改进建议

### 🔴 高优先级

#### D1. [requirements_codex_v1.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/requirements_codex_v1.md) 需要同步更新已落地功能

以下能力在代码中已落地，但文档中缺少或不完整：

| 维度 | 代码现状 | 文档缺失 |
|------|----------|----------|
| 期现溢价调度频率 | 巡航 5min / 盯盘 30s | ✅ 已补（V1.1） |
| 必要表列表 | 含 `convertible_live_snapshot`、`sentiment_live_snapshot`、[source_health_status](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/db_manager.py#1341-1439)、[job_run_status](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/db_manager.py#1567-1578)、`config_change_history` | ❌ §11.2 仅列 6 张表 |
| [premium_thresholds.json](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/config/premium_thresholds.json) | 代码和 GUI 已使用 | ❌ §15.4 未列出 |
| 可转债快照表 | `convertible_live_snapshot` 已实装 | ❌ §11.5 清理规则未提及 |
| 舆情快照表 | `sentiment_live_snapshot` 已实装 | ❌ 同上 |
| 数据源健康度 / 任务状态 / 配置审计 | 三张表已实装并上看板 | ❌ §11.2 未列出 |

**建议**：将 [requirements_codex_v1.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/requirements_codex_v1.md) 升级至 V1.2，补全所有已实装表和配置文件引用。

#### D2. [alert_history](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/app_dashboard.py#85-101) 保留规则仍有歧义

§11.3 说"只保留同一 asset 的最新一条"，但代码中的实现是 **`DELETE WHERE asset = ?`** 后再 INSERT。这意味着：
  - 同一标的不同策略的报警互相覆盖
  - 与 §11.3 补充说的"在内存层面去重"不一致——代码是在数据库层面物理删除

**建议**：要么修改代码改为 `DELETE WHERE asset = ? AND strategy = ?`，要么在文档中明确"同一标的无论哪个策略只保留一条"。

#### D3. 子进度文档严重过时

| 文档 | 最后更新 | 问题 |
|------|----------|------|
| [progress_ai_a_futures.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/progress_ai_a_futures.md) | 2026-03-15 | 写着 10 通过，实际已 36 通过 |
| [progress_ai_integration.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/progress_ai_integration.md) | 2026-03-12 | 停在 6 通过时代 |
| [progress_ai_b_convertible.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/progress_ai_b_convertible.md) | 待查 | 缺少 Current State Summary |
| [progress_ai_d_sentiment.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/progress_ai_d_sentiment.md) | 待查 | 缺少 Current State Summary |

**建议**：
- 若不再作为活跃文档，在文件头部添加 `> ⚠️ 本文档已归档，最新状态见 progress.md`
- 或做一次批量更新，同步至 36 通过

### 🟡 中优先级

#### D4. [CONTRIBUTING.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/CONTRIBUTING.md) 应与当前模块结构对齐

需确认是否仍反映当前的可修改文件范围（包括新增的 [premium_fetcher.py](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/fetchers/premium_fetcher.py)、[premium_strategy.py](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/strategies/premium_strategy.py)、[premium_config.py](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/premium_config.py) 等）。

#### D5. [api_registry.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/api_registry.md) 应补充加密资产数据源

当前 [premium_fetcher.py](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/fetchers/premium_fetcher.py) 使用了 ccxt 连接交易所 API，[api_registry.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/api_registry.md) 应记录：
- 使用了哪些交易所
- 限流策略
- fallback 路径

#### D6. [.env.example](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/.env.example) 缺少 `XUEQIU_COOKIE`

[settings.py](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/config/settings.py) L134 定义了 `XUEQIU_COOKIE: str = ""`，但 [.env.example](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/.env.example) 中没有这个字段的说明。

#### D7. `文档改进建议.md` 中列出的 P0/P1 项部分已完成

该文档提到的一些问题在最近的 V1.1 更新中已部分修复（如期现溢价调度频率、集成测试基准）。应对已修复项做标记。

### 🟢 低优先级

#### D8. 缺少 `README.md`

项目没有根级别的 README，新开发者无法快速了解：
- 项目用途
- 如何安装依赖
- 如何启动调度器和看板
- 如何运行测试

#### D9. [docker-compose.yml](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docker-compose.yml) 应提供看板服务定义

当前只有调度器服务，看板的 Streamlit 服务需要额外的 docker-compose service。

#### D10. 研究文档未与主流程关联

docs 中有多份研究文档（[convertible_and_futures_research_20260315.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/convertible_and_futures_research_20260315.md)、[crypto_cash_and_carry_research_20260418.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/crypto_cash_and_carry_research_20260418.md) 等），但 [DOC_STANDARDS.md](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/docs/DOC_STANDARDS.md) 中没有给研究文档定义分类。

---

## 三、改进优先级汇总

| 优先级 | 编号 | 问题 | 类型 | 预估工作量 |
|--------|------|------|------|------------|
| **P0** | #1 | [_get_job_lock](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#294-298) 竞态条件 | 代码 | 5min |
| **P0** | #2 | [save_signal](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/db_manager.py#594-618) 删除逻辑跨策略覆盖 | 代码 | 15min |
| **P0** | #3 | 巡航模式冗余/不可达代码 | 代码 | 15min |
| **P0** | D1 | 需求文档 V1.2 同步已落地功能 | 文档 | 1h |
| **P0** | D2 | [alert_history](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/app_dashboard.py#85-101) 保留规则歧义 | 代码+文档 | 30min |
| **P1** | #4 | [.gitignore](file:///c:/Users/hikiwa/Desktop/coding/finance/.gitignore) 顶层缺 [.env](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/.env) | 配置 | 2min |
| **P1** | #9 | [.gitignore](file:///c:/Users/hikiwa/Desktop/coding/finance/.gitignore) 缺 premium local | 配置 | 2min |
| **P1** | #10 | 移除未使用依赖 | 配置 | 5min |
| **P1** | D3 | 子进度文档严重过时 | 文档 | 30min |
| **P2** | #5 | Notifier 模块导入副作用 | 代码 | 30min |
| **P2** | #6 | 浮点数精确比较 | 代码 | 1h |
| **P2** | #7 | 函数内延迟 import | 代码 | 5min |
| **P2** | D4-D7 | 文档对齐与补充 | 文档 | 2h |
| **P3** | #8, #12-15 | 代码风格与最佳实践 | 代码 | 1h |
| **P3** | D8-D10 | README / docker-compose / 研究文档分类 | 文档 | 2h |

---

## 四、总体评价

### 优点
- **架构清晰**：6 层分离（数据→调度→策略→存储→展现→运维）落地良好
- **文档体系完善**：有基线文档、进度文档、标准文档、导航文档的分层
- **降级能力强**：可转债三级降级、期指现货双源、金属汇率四级兜底设计合理
- **快照去重机制**：分钟级去重 + 值变化检测 + 保底定时写入，有效控制数据库增长
- **模块独立性好**：每个模块有独立的时钟、开关、阈值、巡航/盯盘模式

### 需改进
- **线程安全**：[_get_job_lock](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/core_scheduler.py#294-298) 竞态问题需立即修复
- **数据一致性**：[save_signal](file:///c:/Users/hikiwa/Desktop/coding/finance/arbitrage_monitor/utils/db_manager.py#594-618) 的跨策略删除逻辑需要确认是否为预期行为
- **代码冗余**：7 个调度函数中的冗余条件判断应清理
- **文档同步**：代码演进快于文档，需做一次全面的文档追赶
