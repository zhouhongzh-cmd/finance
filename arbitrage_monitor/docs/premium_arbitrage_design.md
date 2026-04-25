# A50 / Crypto 期现溢价专题设计

> 状态: ACTIVE
> 最后更新: 2026-04-26
> 关联基线: `docs/requirements_codex_v1.md`

---

## 1. 范围

本文档定义当前 A50 / crypto 期现溢价模块的专题设计。主需求边界仍以 `requirements_codex_v1.md` 为准，本文只展开 A50 与 Top10 crypto / 加密资产池的数据契约、阈值、快照和看板展示细节。

当前链路覆盖：

- 数据入口: `fetchers/premium_fetcher.py`
- 策略判断: `strategies/premium_strategy.py`
- 阈值配置: `config/premium_thresholds.json`
- 合约桶与资产池配置: `config/premium_thresholds.py`
- 调度入口: `core_scheduler.py`
- 快照存储: `utils/db_manager.py`
- 看板展示: `app_dashboard.py`

---

## 2. A50 与 Crypto 资产范围

当前资产组：

| 类型 | 资产组 |
|------|--------|
| 非加密 | `A50` |
| crypto / 加密 Top10 白名单 | `BTC`、`ETH`、`XRP`、`BNB`、`SOL`、`DOGE`、`ADA`、`TRX`、`LINK`、`AVAX` |

crypto / 加密资产以 `asset_group × contract_bucket` 展示。当前合约桶固定为：

| 合约桶 | 展示名 | 年化阈值 |
|--------|--------|----------|
| `PERP` | 永续 | 不参与 |
| `MONTHLY_CURRENT` | 当月 | 参与 |
| `MONTHLY_NEXT` | 次月 | 参与 |
| `QUARTERLY_CURRENT` | 近季 | 参与 |
| `QUARTERLY_NEXT` | 次季 | 参与 |

阈值配置中，crypto / 加密资产把交割合约桶统一映射到 `DELIVERY` 阈值组；`A50` 继续使用单组 `A50` 阈值。

---

## 3. 数据源与降级

| 链路 | 数据源 | 降级口径 |
|------|--------|----------|
| A50 现货 | `yf.Ticker("XIN9.FGI")` | 依次尝试 `fast_info`、`info`、`history(period="1d")`，仍失败则跳过 A50 |
| A50 期货 | `ak.futures_global_spot_em()` | 单个合约缺失时跳过该合约；整表失败则跳过 A50 |
| crypto / 加密现货 | Gate `GET /spot/tickers` | 单个币种现货缺失则跳过该资产 |
| crypto / 加密永续 | Gate `GET /futures/usdt/contracts` | 单个资产永续缺失只跳过 `PERP` 桶 |
| crypto / 加密交割 | Gate `GET /delivery/usdt/contracts` | 单个资产只保留可识别的交割桶 |

模块级 `fetch_live()` 使用 `tenacity`，当前为最多 3 次、指数退避 `2s -> 4s -> 8s`。

---

## 4. 数据契约

`PremiumArbitrageData` 的核心字段：

| 字段 | 语义 |
|------|------|
| `asset_group` | 资产组，如 `A50`、`BTC` |
| `contract_bucket` | 合约桶，如 `PERP`、`MONTHLY_CURRENT` |
| `contract_type` | 原生合约类型，如 `spot`、`swap`、`future` |
| `expiry_ts` | 到期时间，永续允许为空 |
| `bucket_rank` | 看板排序字段 |
| `source_exchange` | 期货腿交易所或来源 |
| `spot_price` | 现货价格 |
| `future_price` | 期货或永续价格 |
| `premium` | `future_price - spot_price` |
| `premium_rate` | `premium / spot_price * 100` |
| `state` | `contango` 或 `backwardation` |
| `days_to_maturity` | 剩余天数，永续允许为空 |

唯一标识口径：

- A50: `symbol = "A50:{future_symbol}"`
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
5. 永续或缺少到期日时不参与年化阈值判定。
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
- 最新快照读取会过滤非 A50 且 `contract_bucket` 为空的旧结构数据。

---

## 8. 看板展示

看板分为两个入口：

- `A50`: 维持原有多合约展示。
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
- `tests/test_retention_and_ops.py` 覆盖期现溢价快照保留期清理。
- dashboard 期现溢价页默认走快照读取，强制抓新成功后回写快照。
