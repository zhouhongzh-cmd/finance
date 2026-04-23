# 新增品种 / 模块接入指南

> 适用范围: `arbitrage_monitor` 当前仓库
> 目的: 让“新增一个品种”时能快速判断改动类型、定位代码落点、按顺序完成融合

---

## 1. 先判断是哪一类新增

新增需求先分成两类，不要混着做：

### A. 现有模块扩资产

特征：

- 复用现有 `fetcher + strategy + snapshot + dashboard` 主链路
- 只是给现有模块增加标的、阈值、白名单、合约桶或展示字段

常见例子：

- 给 `premium` 模块新增一个现货/合约资产
- 给 `metals` 模块新增一个品种
- 给 `futures` 模块新增一个合约组或配置项

### B. 新增独立模块

特征：

- 需要新增独立 `fetcher`
- 需要新增独立 `strategy`
- 需要新增调度 job、快照表或 dashboard 页面

常见例子：

- 新增 `macro`
- 新增 `ib`
- 新增一个完全独立于现有五大模块的新监控策略

---

## 2. 推荐阅读顺序

开始前按这个顺序看文档：

1. `docs/requirements_codex_v1.md`
2. `docs/CONTRIBUTING.md`
3. `docs/api_registry.md`
4. 本文档
5. 对应模块的 `progress_ai_*.md` 或专题 research 文档

用途说明：

- `requirements_codex_v1.md`：看边界、契约、调度和验收标准
- `CONTRIBUTING.md`：看当前允许怎么改、哪些文档必须同步
- `api_registry.md`：看真实数据源、fallback 和限流结论
- 本文档：看接入步骤和代码位点
- `progress_ai_*.md`：看现有模块已经怎么落地

---

## 3. 现有模块扩资产的最小接入清单

如果只是给现有模块增加品种，默认按这个顺序处理：

1. 先确认是否属于当前 `MVP` 范围
2. 明确该资产复用哪条现有链路
3. 补配置
4. 补抓取与策略逻辑
5. 补快照和展示
6. 补测试
7. 回写文档

### 3.1 需要看的代码落点

- 数据入口：`fetchers/*.py`
- 策略判断：`strategies/*.py`
- 配置解析：`config/*.json`、`config/*.py`
- 调度复用：`core_scheduler.py`
- 落库与读取：`utils/db_manager.py`
- 看板展示：`app_dashboard.py`
- 集成测试：`tests/test_scheduler.py`、`tests/test_snapshot_storage.py`、`tests/test_premium.py`

### 3.2 典型改动判断

如果新增资产只影响现有白名单或阈值：

- 优先改配置文件和对应配置解析器
- 尽量不要新开独立 job
- 尽量复用现有 snapshot 表和 dashboard 页面

如果新增资产需要额外字段：

- 先看现有数据模型能否承载
- 不能承载时，先补数据契约，再改 fetcher / strategy

### 3.3 完成标准

至少应满足：

- `fetch_live()` 能返回该资产的数据
- 现有策略能对该资产正常计算
- snapshot 能落库并被 dashboard 读到
- GUI 或配置文件能调到该资产相关参数
- 集成测试至少覆盖一条正向链路

---

## 4. 新增独立模块的完整接入清单

如果是新增一个独立模块，默认按下面顺序做，不要跳步：

1. 先改 `requirements_codex_v1.md`
2. 再改 `api_registry.md`
3. 再定义数据契约
4. 再新增代码文件
5. 再接入调度器
6. 再接入数据库和 dashboard
7. 最后补测试和进度文档

### 4.1 必改文档

- `docs/requirements_codex_v1.md`
- `docs/api_registry.md`
- `docs/progress.md`
- 必要时补 `docs/progress_ai_*.md` 或专题设计文档

### 4.2 必看代码位点

- `models/market_data.py`
- `models/signals.py`
- `fetchers/`
- `strategies/`
- `core_scheduler.py`
- `utils/db_manager.py`
- `app_dashboard.py`
- `tests/test_scheduler.py`
- `tests/test_snapshot_storage.py`

### 4.3 最小代码清单

通常至少包含：

- 一个 `fetcher`
- 一个 `strategy`
- 一个调度入口
- 一组 runtime 配置项
- 一组 snapshot 存储 / 读取接口
- 一个 dashboard 展示入口
- 一组 fixture / strategy / integration 测试

---

## 5. 文件级改动地图

下面这张表回答“新增一个品种时通常改哪些文件”。

| 目标 | 常见文件 | 说明 |
|------|----------|------|
| 定义是否进入正式范围 | `docs/requirements_codex_v1.md` | 先定边界，再写代码 |
| 记录数据源与 fallback | `docs/api_registry.md` | 写清主源、备源、限流、最后验证时间 |
| 定义或复用数据模型 | `models/market_data.py` | 新字段先在这里收口 |
| 数据抓取 | `fetchers/*.py` | 保持 `fetch_live()` / `fetch_from_fixture()` 返回类型一致 |
| 策略计算 | `strategies/*.py` | 所有策略统一返回 `list[Signal]` |
| 调度注册 | `core_scheduler.py` | 当前版本新增策略默认要改这里 |
| 持久化 | `utils/db_manager.py` | 新快照表、读取接口、清理逻辑都在这里汇总 |
| 参数配置 | `config/*.json`、`config/*.py` | 阈值、白名单、模块时钟统一收口 |
| 看板展示 | `app_dashboard.py` | 新增页面、表格或读取逻辑 |
| 验证 | `tests/test_scheduler.py`、`tests/test_snapshot_storage.py`、`tests/test_premium.py` | 至少补最小闭环用例 |

---

## 6. 调度器接入规则

当前版本不是“插件式自动注册”架构，所以新增独立策略时默认要改 `core_scheduler.py`。

通常要补的点包括：

- 模块开关
- 巡航 / 盯盘频率字段
- 交易时段字段
- `persist_runtime_data()` 分发
- `run_*_cruise_mode()` / `run_*_watch_mode()` 入口
- `schedule_jobs()` 注册
- 热更新所需的 runtime state

如果只是现有模块扩资产：

- 原则上不应该新开一组调度 job
- 优先复用原模块时钟

---

## 7. 数据库与快照接入规则

如果新增资产仍属于现有模块：

- 优先复用当前 snapshot 表
- 优先复用当前 dashboard 读取函数

如果新增独立模块：

- 需要在 `utils/db_manager.py` 明确新增表
- 需要补对应保存、查询、保留期清理接口
- 需要决定是否进入 dashboard 的 snapshot-first 路径

完成前至少确认：

- 表结构清楚
- 去重规则清楚
- 保留期清理是否纳入
- dashboard 读的是 live 还是 snapshot

---

## 8. 配置接入规则

先判断新增内容属于哪一类配置：

- 共享运行参数：`config/runtime_settings.json`
- 模块阈值：各模块自己的 `thresholds.json`
- 本机私密项：`.env`
- 本机覆盖项：`*.local.json`

规则：

- 时钟、模块开关、共享运行参数优先放 `runtime_settings.json`
- 阈值、白名单、品种映射优先放对应模块配置文件
- Cookie、Webhook 等私密信息放 `.env`
- 不要把本机临时覆盖写回共享配置，除非这是明确要求

---

## 9. 测试最低要求

无论是扩资产还是新模块，至少补下面这些验证中的一部分：

- fixture 加载测试
- strategy 计算测试
- scheduler 导入或注册测试
- snapshot 落库 / 读取测试
- dashboard 读取链路测试
- fallback 场景测试

建议最低闭环：

1. 构造 fixture
2. `fetcher` 返回数据
3. `strategy` 输出信号或快照
4. `db_manager` 落库成功
5. dashboard 能读到结果

---

## 10. 文档回写清单

做完后至少回写这些地方：

- `docs/requirements_codex_v1.md`
- `docs/api_registry.md`
- `docs/progress.md`

必要时再补：

- `docs/progress_ai_*.md`
- 专题 research 文档
- `docs/DEV_PROCESS.md`

不要只改代码不改文档，否则后续很难判断新增品种是“正式接入”还是“临时实验”。

---

## 11. 两类新增的决策建议

### 什么时候只算“扩资产”

- 现有模型字段够用
- 现有 snapshot 表够用
- 现有 dashboard 页够用
- 只需要改白名单、阈值或映射逻辑

### 什么时候必须升级为“新模块”

- 需要独立 fetcher
- 需要独立策略名
- 需要独立调度频率
- 需要独立 snapshot 表
- 需要独立 dashboard 页面或读模型

如果你已经需要独立 job + 独立表 + 独立页面，就不要再把它当成“只是多一个品种”。

---

## 12. 实战样例：接入“恒生指数折价 / 溢价计算”

这个例子最接近当前仓库里的 `A50` 期现溢价链路。

### 12.1 应归类为哪一种

如果你的目标是：

- 现货腿：恒生指数现货
- 期货腿：恒指期货不同月份合约
- 产出：和 `A50` 一样的 `premium / premium_rate / annualized premium rate`

那么它更适合作为：

- `premium` 模块下的**现有模块扩资产**

而不是新开一个完全独立模块。

原因：

- 数据结构可以直接复用 `PremiumArbitrageData`
- 调度可以复用 `premium` 模块现有巡航 / 盯盘 job
- 快照表可以复用 `premium_arbitrage_snapshot`

### 12.2 先说明一个当前边界

仓库当前**没有已验证的恒生指数现货 / 恒指期货数据源实现**。

因此：

- 下面给的是“如何融入当前代码框架”的接入模板
- 不是已经在当前仓库验证通过的接口清单
- 真正开做前，仍要先把数据源验证结果写进 `docs/api_registry.md`

### 12.3 计算口径应沿用现有 premium 模块

建议直接复用当前 `PremiumFetcher._build_snapshot()` 的口径：

- `premium = future_price - spot_price`
- `premium_rate = premium / spot_price * 100`
- `premium > 0` 记为 `contango`
- `premium < 0` 记为 `backwardation`

如果有交割日，再复用 `PremiumArbitrageStrategy` 的年化逻辑：

- `annualized_premium_rate = premium_rate * (365 / days_to_maturity)`

### 12.4 需要改哪些文件

如果要把恒指正式接进当前 `premium` 模块，至少要动这些位置：

1. `docs/requirements_codex_v1.md`
2. `docs/api_registry.md`
3. `config/premium_thresholds.py`
4. `config/premium_thresholds.json`
5. `fetchers/premium_fetcher.py`
6. `app_dashboard.py`
7. `tests/test_premium.py`

通常**不需要**：

- 新建独立 snapshot 表
- 新建独立调度 job
- 新建独立 strategy 文件

### 12.5 配置层怎么接

当前 `premium` 配置把非加密资产收在 `NON_CRYPTO_PREMIUM_ASSETS`。

所以恒指接入通常要先补：

- `config/premium_thresholds.py`

示意方向：

```python
NON_CRYPTO_PREMIUM_ASSETS = {
    "A50": "富时中国A50",
    "HSI": "恒生指数",
}
```

然后在 `config/premium_thresholds.json` 增加一组共享阈值：

```json
{
  "A50": {
    "upper": 0.5,
    "annualized_upper": 8.0,
    "lower": -0.5,
    "annualized_lower": -8.0
  },
  "HSI": {
    "upper": 0.5,
    "annualized_upper": 8.0,
    "lower": -0.5,
    "annualized_lower": -8.0
  }
}
```

这里的阈值数值只是复用 `A50` 的默认模板，是否适合恒指要由你后续根据市场特征再调。

### 12.6 Fetcher 怎么接

在 `fetchers/premium_fetcher.py` 里，建议仿照 `_build_a50_snapshots()` 再做一条恒指链路，例如：

- 单独取恒生指数现货
- 单独取恒指期货多合约
- 每个期货合约都调用 `_build_snapshot()`
- `asset_group` 统一写成 `HSI`

建议新增一个形如：

- `_build_hsi_snapshots()`

然后在 `fetch_live()` 里把它并入当前 `premium` 返回列表。

注意点：

- `symbol` 必须保持唯一，建议形如 `HSI:<future_symbol>`
- `days_to_maturity` 如果能得到交割日就写入；拿不到就允许为空
- `contract_bucket` 需要给一个明确值，否则当前 premium 快照读取会把“非 A50 且 contract_bucket 为空”的行过滤掉

这点很重要：

- `utils/db_manager.py` 当前读取 premium 最新快照时，写了 `asset_group <> 'A50' 且 contract_bucket = ''` 的过滤条件
- 所以恒指如果按非 A50 资产组接入，不能把 `contract_bucket` 留空

### 12.7 Dashboard 需要补什么

这是当前文档里最容易漏掉的一步。

`app_dashboard.py` 现在把 premium 页面硬分成：

- `A50`
- `加密货币`

并且过滤逻辑也是按 `资产组 == "A50"` 来拆分。

所以恒指接入后，你至少要二选一：

#### 方案 A：并到现有“A50”页

适合你想把“股指期现”放在同一页看。

这时要改：

- premium 页面标题文案
- `filter_premium_table()`
- `filter_premium_signal_table()`
- 历史区筛选逻辑

把原来的 `A50` 单点判断改成“股指组白名单”，例如：

- `{"A50", "HSI"}`

#### 方案 B：单独开一个“恒生指数”页签

适合你要把 A50 和恒指完全分开看。

这时要改：

- sidebar 选项
- premium 页签分流逻辑
- 对应按钮文案和说明文案

如果只改 fetcher、不改 dashboard，恒指数据虽然可能落库，但页面归类会不符合预期。

### 12.8 测试最低要补哪些

以恒指为例，至少建议补：

1. `premium_config` 能识别 `HSI`
2. fixture 中加入一条 `HSI` 样例，验证 fetcher 输出结构
3. strategy 能对 `HSI` 触发升水 / 贴水判断
4. snapshot 落库后，`get_latest_premium_snapshots()` 能读到 `HSI`
5. dashboard 过滤后，`HSI` 出现在预期页面

### 12.9 一条实际可执行的落地顺序

如果你现在就要做恒指，建议按这个顺序：

1. 先确定恒指现货源和期货源，并写进 `docs/api_registry.md`
2. 在 `requirements_codex_v1.md` 补一句：`premium` 模块覆盖 `A50 + HSI + crypto`
3. 在 `config/premium_thresholds.py` 和 `config/premium_thresholds.json` 补 `HSI`
4. 在 `fetchers/premium_fetcher.py` 增加 `_build_hsi_snapshots()`
5. 在 `app_dashboard.py` 决定它是并到“A50”页还是单独成页
6. 在 `tests/test_premium.py` 补 fixture / strategy / dashboard 断言
7. 最后更新 `progress.md`

### 12.10 什么时候不该按这个方案做

如果你的“恒生指数折价溢价”并不是：

- 现货指数 vs 期货合约

而是：

- ETF vs 指数
- 不同交易所同名指数产品互比
- 期权隐含折溢价

那它就不一定属于当前 `premium` 模块的直接扩资产，可能要先重新定义数据契约。
