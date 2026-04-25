# 金属套利专题设计

> 状态: ACTIVE
> 最后更新: 2026-04-26
> 关联基线: `docs/requirements_codex_v1.md`

---

## 1. 范围

本文档定义当前金属跨市场套利模块的专题设计。主需求边界仍以 `requirements_codex_v1.md` 为准，本文只展开数据契约、阈值、快照和看板展示细节。

当前链路覆盖：

- 数据入口: `fetchers/ak_metals.py`
- 策略判断: `strategies/metals_strategy.py`
- 品种配置: `config/metals.py`
- 阈值配置: `config/metals_thresholds.json`
- 调度入口: `core_scheduler.py`
- 快照存储: `utils/db_manager.py`
- 看板展示: `app_dashboard.py`

---

## 2. 资产与基准

当前品种由 `config/metals.py` 的 `METALS_CONFIG` 定义。

| 品种代码 | 名称 | 国内合约 | 分类 | 外盘基准 |
|----------|------|----------|------|----------|
| `AU0` | 黄金 | `au0` | precious | 伦敦金、COMEX黄金 |
| `AG0` | 白银 | `ag0` | precious | 伦敦银、COMEX白银 |
| `PT0` | 铂金 | `pt0` | precious | 伦敦铂 |
| `PD0` | 钯金 | `pd0` | precious | 伦敦钯 |
| `CU0` | 铜 | `cu0` | base | LME铜3个月、COMEX铜 |
| `AL0` | 铝 | `al0` | base | LME铝3个月 |
| `ZN0` | 锌 | `zn0` | base | LME锌3个月 |
| `PB0` | 铅 | `pb0` | base | LME铅3个月 |
| `NI0` | 镍 | `ni0` | base | LME镍3个月 |
| `SN0` | 锡 | `sn0` | base | LME锡3个月 |

一条金属套利快照对应一个 `国内品种 × 外盘基准` 组合，内部唯一键为 `symbol = "{metal_symbol}:{benchmark_symbol}"`。

---

## 3. 数据源与降级

| 链路 | 主源 | 降级口径 |
|------|------|----------|
| 国内行情 | `ak.futures_zh_minute_sina(symbol=..., period="1")` | 失败后回退 `ak.futures_zh_spot(symbol=..., market="CF", adjust="0")` |
| 外盘行情 | `ak.futures_foreign_commodity_realtime(symbol=...)` | 单个 benchmark 失败时记录日志并跳过该组合 |
| 汇率 | `ak.fx_spot_quote()` | 依次回退 `ak.currency_boc_sina()`、`forex_python.converter.CurrencyRates()`、默认汇率 `7.20` |

模块级 `fetch_live()` 使用 `tenacity`，当前为最多 3 次、指数退避 `2s -> 4s -> 8s`。

---

## 4. 计算口径

`MetalArbitrageData` 的核心字段：

| 字段 | 语义 |
|------|------|
| `dom_price` | 国内主力价格 |
| `for_price_usd` | 外盘美元价格 |
| `for_price_cny` | 外盘折人民币后的价格 |
| `exchange_rate` | 本轮使用的 USD/CNY 汇率 |
| `implied_rate` | 由国内/外盘价格反推的隐含汇率 |
| `spread` | `dom_price - for_price_cny` |
| `spread_pct` | `spread / for_price_cny * 100` |
| `used_api_cny_quote` | 是否直接使用接口返回的人民币报价 |

方向口径：

- `spread_pct >= upper` 记为升水触发。
- `spread_pct <= lower` 记为贴水触发。
- `upper` 必须为正数，`lower` 必须为负数。

---

## 5. 阈值与信号

阈值来源为 `config/metals_thresholds.json`，正式字段为：

- `upper_enabled`
- `upper`
- `lower_enabled`
- `lower`

兼容字段仍保留：

- `contango_enabled`
- `contango_threshold`
- `backwardation_enabled`
- `backwardation_threshold`

策略判断：

1. 每条快照按 `metal_symbol` 读取有效阈值。
2. 升水或贴水触发后生成 `Metals_Arbitrage` 信号。
3. 当 `abs(spread_pct) >= 触发阈值 * 1.5` 时信号级别为 `CRITICAL`，否则为 `WARNING`。

---

## 6. 调度与时间窗

运行时字段：

| 字段 | 默认值 |
|------|--------|
| `ENABLE_METALS_MONITOR` | `True` |
| `ENABLE_METALS_CRUISE` | `True` |
| `ENABLE_METALS_WATCH` | `False` |
| `METALS_CRUISE_INTERVAL_MINUTES` | `15` |
| `METALS_WATCH_INTERVAL_SECONDS` | `60` |
| `METALS_MORNING_START` / `METALS_MORNING_END` | `09:00` / `11:30` |
| `METALS_AFTERNOON_START` / `METALS_AFTERNOON_END` | `13:30` / `15:00` |
| `METALS_NIGHT_START` / `METALS_NIGHT_END` | `21:00` / `02:30` |

调度 job：

- `metals_cruise_mode`
- `metals_watch_mode`

---

## 7. 快照表

表名: `metal_arbitrage_snapshot`

关键字段：

- 标识: `symbol`、`metal_symbol`、`benchmark_symbol`
- 名称: `metal_name`、`benchmark_name`、`benchmark_display_name`
- 行情: `dom_price`、`for_price_usd`、`for_price_cny`
- 计算: `exchange_rate`、`implied_rate`、`spread`、`spread_pct`
- 状态: `used_api_cny_quote`、`fetched_at`

写入规则：

- 按 `symbol` 读取最新快照。
- 若核心价格、价差或汇率发生变化则写入或更新。
- 高频快照遵循分钟级去重和保底写入策略。

---

## 8. 看板展示

金属页展示：

- 国内外套利对主表
- 分类筛选
- 当前触发信号
- 最近快照历史
- 阈值和模块时钟跳转入口

表格前置字段应优先展示：

1. 品种名称
2. 基准名称
3. 国内价格
4. 外盘人民币价
5. 价差
6. 价差百分比
7. 隐含汇率
8. 信号

---

## 9. 验收口径

最小验收：

- `tests/test_metals.py` 覆盖 fixture、阈值和策略触发。
- `tests/test_snapshot_storage.py` 覆盖金属快照写入和最新快照读取。
- `tests/test_retention_and_ops.py` 覆盖金属快照保留期清理。
- dashboard 金属页默认走快照读取，强制抓新成功后回写快照。
