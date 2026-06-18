# 外盘指数 / Crypto 期现溢价专题设计

> 状态: ACTIVE
> 最后更新: 2026-06-18
> 关联基线: `docs/requirements_codex_v1.md`

---

## 1. 范围

本文档定义当前外盘指数 / crypto 期现溢价模块的专题设计。主需求边界仍以 `requirements_codex_v1.md` 为准，本文只展开外盘指数与 Top10 crypto / 加密资产池的数据契约、阈值、快照和看板展示细节。

当前链路覆盖：

- 数据入口: `fetchers/premium_fetcher.py`
- 策略判断: `strategies/premium_strategy.py`
- 阈值配置: `config/premium_thresholds.json`
- 资产池配置: `config/premium_assets.py`
- 合约桶与阈值加载: `config/premium_thresholds.py`
- 调度入口: `core_scheduler.py`
- 快照存储: `utils/db_manager.py`
- 看板展示: `app_dashboard.py`

---

## 2. 外盘指数与 Crypto 资产范围

当前资产组：

| 类型 | 资产组 |
|------|--------|
| 外盘指数 | `A50`、`HSI`、`HSTECH`、`NDX`、`SPX`、`DJI`、`NIKKEI225` |
| crypto / 加密 Top10 白名单 | `BTC`、`ETH`、`XRP`、`BNB`、`SOL`、`DOGE`、`ADA`、`TRX`、`LINK`、`AVAX` |

外盘指数按 `asset_group` 展示。指数阈值按资产组维护，例如 `A50`、`NDX`、`SPX`。

crypto / 加密资产以 `asset_group × contract_bucket` 展示。当前合约桶固定为：

| 合约桶 | 展示名 | 年化阈值 |
|--------|--------|----------|
| `PERP` | 永续 | 不参与 |
| `MONTHLY_CURRENT` | 当月 | 参与 |
| `MONTHLY_NEXT` | 次月 | 参与 |
| `QUARTERLY_CURRENT` | 近季 | 参与 |
| `QUARTERLY_NEXT` | 次季 | 参与 |

阈值配置中，crypto / 加密资产把交割合约桶统一映射到 `DELIVERY` 阈值组；外盘指数继续使用单资产组阈值。

---

## 3. 数据源与降级

| 链路 | 数据源 | 降级口径 |
|------|--------|----------|
| 外盘指数现货 | `ak.index_global_spot_em()`、`ak.stock_hk_index_spot_em()`、`IB reqMktData(按资产启用)` | `IB` 资产优先尝试 provider；失败后再回退到东财 / `yf.Ticker(...)` |
| A50 / 美股指数期货 | `ak.futures_global_spot_em()` 名称筛选 `A50`、`小型纳指当月连续`、`小型标普当月连续`、`小型道指` | 单个合约缺失时跳过该合约；整表失败或单指数缺失时尝试可用备源 |
| 恒生指数期货 | `IB reqMktData("HSI" / "CONTFUT" / "HKFE")` | `IB` 不可用或无价格时跳过 `HSI` 本轮折溢价计算 |
| 恒生科技指数期货 | `IB reqMktData("HSTECH" / "CONTFUT" / "HKFE")` | `IB` 不可用或无价格时跳过 `HSTECH` 本轮折溢价计算 |
| 美股/日经指数期货备源 | `yf.Ticker("NQ=F"/"ES=F"/"YM=F"/"NKD=F")` | 期货价格缺失时跳过该指数本轮折溢价计算 |
| crypto / 加密现货 | Gate `GET /spot/tickers` | 单个币种现货缺失则跳过该资产 |
| crypto / 加密永续 | Gate `GET /futures/usdt/contracts` | 单个资产永续缺失只跳过 `PERP` 桶 |
| crypto / 加密交割 | Gate `GET /delivery/usdt/contracts` | 单个资产只保留可识别的交割桶 |

第一版采用“可用源优先”：没有稳定期货源的指数不会阻塞整个 premium 抓取；系统记录 warning 后继续处理其他指数和 crypto 资产。

当前已可生成并写入数据库的外盘指数折溢价快照：

- `HSI`: `IB` 可用时按 `IND + CONTFUT` 形成恒指折溢价快照。
- `HSTECH`: `IB` 可用时按 `IND + CONTFUT` 形成恒生科技指数折溢价快照。
- `A50`: 东财全球期货表中有 `CN00Y` 及部分可用月份合约。
- `NDX`: 东财全球期货表中当前可用 `NQ00Y` 主连。
- `SPX`: 东财全球期货表中当前可用 `ES00Y` 主连。
- `DJI`: 东财全球期货表中当前可用 `YM00Y` 及部分月份合约，按有有效 `最新价` 的行入库；只有昨结、无最新价的远月合约跳过。
- `NIKKEI225`: 当前期货腿使用 yfinance `NKD=F`。

待探索数据源，不进入当前数据库写入范围：

- 纳斯达克 100、标普 500 远月实时期货行情。
- 恒生国企指数连续期货（当前仅验证到现货 `IND` 可解析）。
- DAX、FTSE 等其他外盘指数期货腿。

模块级 `fetch_live()` 使用 `tenacity`，当前为最多 3 次、指数退避 `2s -> 4s -> 8s`。

### 3.1 yfinance 访问（代理与限流）

所有经 `yf.Ticker(...)` 的取价（外盘指数现货回退、A50 现货 `XIN9.FGI`、美股 / 日经期货备源 `NQ=F`/`ES=F`/`YM=F`/`NKD=F` 等）统一走 `_fetch_yfinance_price`，由 `_build_yfinance_session()` 构造会话：

- **代理**：用 `requests.Session` 走代理访问 Yahoo，地址由环境变量 `YFINANCE_PROXY` 配置（默认 `http://127.0.0.1:7897`，即本机 Clash；置空字符串则直连）。在容器内运行时需以 `--network host` 启动，`127.0.0.1` 才能命中宿主的代理端口（bridge 网络下 `127.0.0.1` 指向容器自身，连不到宿主 Clash）。
- **反限流**：会话带浏览器 `User-Agent`，显著降低 Yahoo `YFRateLimitError`（HTTP 429）。
- **重试**：取价失败时退避重试最多 3 次（`2s -> 4s`）；若已连上但未取到价格则不重试，直接返回空。

> 该重试与上文模块级 `fetch_live()` 的 `tenacity` 重试相互独立，分别作用于单标的取价和整轮抓取。

---

## 4. 数据契约

`PremiumArbitrageData` 的核心字段：

| 字段 | 语义 |
|------|------|
| `asset_group` | 资产组，如 `A50`、`NDX`、`BTC` |
| `contract_bucket` | 合约桶，如 `INDEX`、`PERP`、`MONTHLY_CURRENT` |
| `contract_type` | 原生合约类型，如 `swap`、`future` |
| `expiry_ts` | 到期时间，永续或连续指数期货允许为空 |
| `bucket_rank` | 看板排序字段 |
| `source_exchange` | 期货腿交易所或来源 |
| `spot_price` | 现货价格 |
| `future_price` | 期货或永续价格 |
| `premium` | `future_price - spot_price` |
| `premium_rate` | `premium / spot_price * 100` |
| `state` | `contango` 或 `backwardation` |
| `days_to_maturity` | 剩余天数，永续或连续指数期货允许为空 |

唯一标识口径：

- 外盘指数: `symbol = "{asset_group}:{future_symbol}"`
- crypto / 加密资产: `symbol = "{asset_group}:{future_symbol}"`

---

## 5. 阈值与信号

阈值来源为 `config/premium_thresholds.json`，正式字段为：

- `upper_enabled`
- `upper`
- `annualized_upper_enabled`
- `annualized_upper`
- `lower_enabled`
- `lower`
- `annualized_lower_enabled`
- `annualized_lower`

兼容字段仍保留 `contango_*` 和 `backwardation_*` 别名。

判断规则：

1. 先按 `asset_group` 和 `contract_bucket` 取有效阈值。
2. 当 `premium_rate >= upper` 时进入升水候选。
3. 当 `premium_rate <= lower` 时进入贴水候选。
4. 非永续合约若启用年化阈值，还必须同时满足对应年化阈值。
5. 永续、连续指数期货或缺少到期日时不参与年化阈值判定。
6. 触发倍率 `>= 1.5` 时信号级别为 `CRITICAL`，否则为 `WARNING`。

年化口径：

```text
annualized_premium_rate = premium_rate * (365 / max(days_to_maturity, 1))
```

---

## 6. 调度与时间窗

运行时字段：

| 字段 | 默认值 |
|------|--------|
| `ENABLE_PREMIUM_MONITOR` | `False` |
| `ENABLE_PREMIUM_CRUISE` | `True` |
| `ENABLE_PREMIUM_WATCH` | `False` |
| `PREMIUM_CRUISE_INTERVAL_MINUTES` | `5` |
| `PREMIUM_WATCH_INTERVAL_SECONDS` | `30` |
| `PREMIUM_MORNING_START` / `PREMIUM_MORNING_END` | `09:00` / `11:30` |
| `PREMIUM_AFTERNOON_START` / `PREMIUM_AFTERNOON_END` | `13:00` / `16:00` |
| `PREMIUM_NIGHT_START` / `PREMIUM_NIGHT_END` | `20:00` / `06:00` |

调度 job：

- `premium_cruise_mode`
- `premium_watch_mode`

外盘指数和 crypto / 加密资产第一版继续共享同一套 premium 模块时钟。

---

## 7. 快照表

表名: `premium_arbitrage_snapshot`

关键字段：

- 标识: `symbol`、`asset_group`、`contract_bucket`
- 合约: `contract_type`、`expiry_ts`、`bucket_rank`、`source_exchange`
- 现货腿: `spot_symbol`、`spot_name`、`spot_price`
- 期货腿: `future_symbol`、`future_name`、`future_price`
- 计算: `premium`、`premium_rate`、`state`、`days_to_maturity`
- 来源: `source_spot`、`source_future`、`fetched_at`

写入规则：

- 按 `symbol` 读取最新快照。
- 若合约桶、价格、溢价、状态或剩余天数变化则写入或更新。
- 最新快照读取会过滤非外盘指数且 `contract_bucket` 为空的旧结构数据，并只展示最近一次 premium 抓取批次窗口内的数据，避免历史旧 symbol 混入当前行情页。

---

## 8. 看板展示

看板分为两个入口：

- `外盘指数`: 展示 A50、恒生、恒生科技、纳斯达克、标普、道指、日经等指数中当前可生成的折溢价快照。
- `加密货币`: 按 Top10 crypto / 加密资产和合约桶展示。

展示内容：

- 溢价对主表
- 资产组筛选
- 当前触发信号
- 最近快照历史
- 阈值和模块时钟跳转入口

crypto / 加密资产表格必须保留 `资产组` 与 `合约桶`，避免把 Top10 快照回读压缩成单资产。

---

## 9. 验收口径

最小验收：

- `tests/test_premium.py` 覆盖 fixture、阈值、年化阈值和策略触发。
- `tests/test_snapshot_storage.py` 覆盖期现溢价快照写入和最新快照读取。
- `tests/test_dashboard.py` 覆盖外盘指数与 crypto 的看板过滤/排序口径。
- `tests/test_retention_and_ops.py` 覆盖期现溢价快照保留期清理。
- dashboard 期现溢价页默认走快照读取，强制抓新成功后回写快照。
