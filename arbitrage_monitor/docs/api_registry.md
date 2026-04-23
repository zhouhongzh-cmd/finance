# API Registry

> 当前基线: `docs/requirements_codex_v1.md`
> 版本: V1.1
> 最后更新: 2026-04-23
> 说明: 本文档只记录当前 `MVP` 已使用或已规划但明确标注状态的数据源。

---

## 版本变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| V1.0 | 2026-03-15 | 初始版本 |
| V1.1 | 2026-04-23 | 1. 补充期现溢价模块调度频率<br>2. 添加各条目"最后验证时间"字段 |

---

---

## 1. MVP Data Sources

### 1.1 现货指数行情

- `status`: `ACTIVE`
- `module`: `fetchers/ak_futures.py`
- `name`: `akshare.stock_zh_index_spot_em`
- `call`: `ak.stock_zh_index_spot_em()`
- `rate_limit`: 极宽松
- `latency`: 约 `200ms`
- `quality`: 高
- `fallback`: 直连新浪指数接口 `https://hq.sinajs.cn/list=...`
- `notes`: 当前环境中东方财富指数接口偶发代理/连接失败，新浪指数备源当前可用

### 1.2 股指期货行情

- `status`: `ACTIVE`
- `module`: `fetchers/ak_futures.py`
- `name`: `akshare.futures_zh_spot`
- `call`: `ak.futures_zh_spot(symbol=..., market="FF", adjust="0")`
- `rate_limit`: 建议低于 `5` 次/秒
- `latency`: 约 `400ms`
- `quality`: 较高
- `fallback`: 记录日志后跳过本轮
- `notes`: 当前活跃合约按“当月 + 下月 + 之后最近两个季月”生成，季月场景下四个品种共 `16` 个有效合约

### 1.3 股指期货保证金比例

- `status`: `ACTIVE`
- `module`: `fetchers/futures_margin.py`
- `name`: `cffex.product_page_margin_rule`
- `call`: `httpx.get("https://www.cffex.com.cn/...")`
- `rate_limit`: 极低频，每日 `09:00` 与 `00:00` 各一次
- `latency`: 中等，实测可能出现握手超时
- `quality`: 官方规则口径高，但运行时可用性一般
- `fallback`: 优先回退到中金财富期货的每日结算保证金公告，再回退到品种默认最低保证金比例
- `notes`: 当前环境中中金所官网常见 `Connection refused`，因此运行时经常由备源补齐 IF/IH/IC/IM 的保证金比例

### 1.4 股指期货保证金比例备源

- `status`: `ACTIVE_FALLBACK`
- `module`: `fetchers/futures_margin.py`
- `name`: `ciccwmf.daily_margin_bulletin`
- `call`: `httpx.get("https://www.ciccwmf.cn/bzjjzdtb.jhtml")` -> latest detail page
- `rate_limit`: 极低频，每日 `09:00` 与 `00:00` 各一次
- `latency`: 中等
- `quality`: 中高，属于期货公司日度结算保证金公告
- `fallback`: 若列表或详情页失败，再回退到静态默认值
- `notes`: 当前实测可稳定提取 `IF=14%`、`IH=14%`、`IC=15%`、`IM=15%`

### 1.5 可转债主数据源

- `status`: `ACTIVE`
- `module`: `fetchers/ak_convertible.py`
- `name`: `akshare.bond_cb_jsl`
- `call`: `ak.bond_cb_jsl(cookie=settings.JSL_COOKIE)`
- `rate_limit`: 极严，未登录或 Cookie 失效时常截断为 `<=30` 条
- `latency`: 约 `400ms`
- `quality`: 高
- `fallback`: 若结果疑似截断，自动切换到东方财富 `datacenter` 结构化接口；仅在该接口失败时再退到 `ak.bond_zh_cov()`
- `notes`: 主数据源可提供 `premium_rate`、`double_low`、`ytm` 等核心字段

### 1.6 可转债降级数据源

- `status`: `ACTIVE_FALLBACK`
- `module`: `fetchers/ak_convertible.py`
- `name`: `eastmoney.datacenter.RPT_BOND_CB_LIST`
- `call`: `https://datacenter-web.eastmoney.com/api/data/v1/get`
- `rate_limit`: 宽松
- `latency`: 中等
- `quality`: 中高
- `fallback`: 若该接口失败，再回退到 `ak.bond_zh_cov()`
- `notes`: 可提供 `CURRENT_BOND_PRICENEW`、`TRANSFER_VALUE`、`TRANSFER_PREMIUM_RATIO`、`REDEEM_TRIG_PRICE`、`RESALE_TRIG_PRICE`、`BOND_START_DATE`、`EXPIRE_DATE`、`INTEREST_RATE_EXPLAIN`、`REDEEM_CLAUSE` 等字段。系统在该源上本地计算 `double_low` 和 `ytm`。

### 1.7 可转债最后兜底数据源

- `status`: `ACTIVE_FALLBACK`
- `module`: `fetchers/ak_convertible.py`
- `name`: `akshare.bond_zh_cov`
- `call`: `ak.bond_zh_cov()`
- `rate_limit`: 宽松
- `latency`: 约 `600ms`
- `quality`: 中低
- `fallback`: 无进一步 fallback
- `notes`: 仅用于东方财富 datacenter 不可用时的最后兜底。字段不完整，`ytm` 无法可靠恢复。

### 1.8 舆情主数据源

- `status`: `ACTIVE`
- `module`: `fetchers/sentiment_spider.py`
- `name`: `eastmoney.stock_rank_list`
- `call`: `httpx.post("https://emappdata.eastmoney.com/stockrank/getAllCurrentList", json=...)`
- `rate_limit`: 宽松
- `latency`: 约 `200ms`
- `quality`: 高
- `fallback`: 可切换至雪球，但当前默认不启用
- `notes`: 当前 `MVP` 舆情能力以东方财富人气榜为主

### 1.9 舆情备选数据源

- `status`: `OPTIONAL`
- `module`: `fetchers/sentiment_spider.py`
- `name`: `xueqiu.hot_stock_list`
- `call`: `httpx.get("https://stock.xueqiu.com/v5/stock/hot_stock/list.json")`
- `rate_limit`: 极严
- `latency`: 约 `500ms`
- `quality`: 低到中
- `fallback`: 默认仍回到东方财富
- `notes`: 2026 年实测匿名访问经常返回登录错误，不应作为默认主源

### 1.10 金属国内行情主数据源

- `status`: `ACTIVE`
- `module`: `fetchers/ak_metals.py`
- `name`: `akshare.futures_zh_minute_sina`
- `call`: `ak.futures_zh_minute_sina(symbol=..., period="1")`
- `rate_limit`: 建议低于 `5` 次/秒
- `latency`: 约 `400ms`
- `quality`: 中高
- `fallback`: 回退到 `ak.futures_zh_spot(symbol=..., market="CF", adjust="0")`
- `notes`: 默认用于沪金、沪银及基础金属主力分钟线

### 1.11 金属国内行情备源

- `status`: `ACTIVE_FALLBACK`
- `module`: `fetchers/ak_metals.py`
- `name`: `akshare.futures_zh_spot`
- `call`: `ak.futures_zh_spot(symbol=..., market="CF", adjust="0")`
- `rate_limit`: 建议低于 `5` 次/秒
- `latency`: 中等
- `quality`: 中
- `fallback`: 无进一步 fallback
- `notes`: 当分钟线接口失败时兜底，时间字段会做本地日期补齐

### 1.12 金属外盘主数据源

- `status`: `ACTIVE`
- `module`: `fetchers/ak_metals.py`
- `name`: `akshare.futures_foreign_commodity_realtime`
- `call`: `ak.futures_foreign_commodity_realtime(symbol=...)`
- `rate_limit`: 中等
- `latency`: 中等
- `quality`: 中高
- `fallback`: 单个 benchmark 失败则记录日志并跳过本轮
- `notes`: 提供外盘美元报价，部分品种同时提供 `人民币报价`

### 1.13 金属汇率主数据源

- `status`: `ACTIVE`
- `module`: `fetchers/ak_metals.py`
- `name`: `akshare.fx_spot_quote`
- `call`: `ak.fx_spot_quote()`
- `rate_limit`: 宽松
- `latency`: 约 `300ms`
- `quality`: 中高
- `fallback`: 依次回退到 `ak.currency_boc_sina()`、`forex_python.converter.CurrencyRates()`、默认汇率
- `notes`: 当前系统使用 `USD/CNY` 买报价，失败时自动兜底

### 1.14 加密资产现货主数据源

- `status`: `ACTIVE`
- `module`: `fetchers/premium_fetcher.py`
- `name`: `gate.spot.tickers`
- `call`: `GET /spot/tickers`
- `rate_limit`: 宽松
- `latency`: 中等
- `quality`: 中高
- `fallback`: 若单个币种现货缺失则跳过该资产；整表失败则跳过本轮加密资产现货腿
- `调度频率`: 巡航 5 分钟 / 盯盘 30 秒
- `最后验证时间`: 2026-04-22
- `notes`: 当前用于固定白名单 `Top10` 合约加密资产池的现货腿，默认读取 `*_USDT`

### 1.15 加密资产永续主数据源

- `status`: `ACTIVE`
- `module`: `fetchers/premium_fetcher.py`
- `name`: `gate.futures.usdt.contracts`
- `call`: `GET /futures/usdt/contracts`
- `rate_limit`: 宽松
- `latency`: 中等
- `quality`: 中高
- `fallback`: 某个资产永续缺失时只跳过 `PERP` 桶；整表失败则跳过本轮加密永续腿
- `调度频率`: 巡航 5 分钟 / 盯盘 30 秒
- `最后验证时间`: 2026-04-22
- `notes`: 当前用于固定白名单 `Top10` 合约加密资产池的永续腿，默认合约名为 `*_USDT`

### 1.16 加密资产交割合约主数据源

- `status`: `ACTIVE`
- `module`: `fetchers/premium_fetcher.py`
- `name`: `gate.delivery.usdt.contracts`
- `call`: `GET /delivery/usdt/contracts`
- `rate_limit`: 宽松
- `latency`: 中等
- `quality`: 中高
- `fallback`: 某个资产仅缺失部分交割合约桶时允许局部跳过；整表失败则只保留现货与永续
- `调度频率`: 巡航 5 分钟 / 盯盘 30 秒
- `最后验证时间`: 2026-04-22
- `notes`: 当前按 `expire_time + cycle` 归类为 `MONTHLY_CURRENT`、`MONTHLY_NEXT`、`QUARTERLY_CURRENT`、`QUARTERLY_NEXT`；当前固定白名单里 `BTC/ETH/DOGE` 已验证可落到双月度 + 双季度桶，`XRP/SOL/ADA/LINK/AVAX` 至少可落到双月度桶

### 1.17 A50 现货主数据源

- `status`: `ACTIVE`
- `module`: `fetchers/premium_fetcher.py`
- `name`: `yfinance.XIN9.FGI`
- `call`: `yf.Ticker("XIN9.FGI")`
- `rate_limit`: 中等
- `latency`: 中等
- `quality`: 中
- `fallback`: 依次尝试 `fast_info`、`info`、`history(period="1d")`；仍失败则跳过 A50 全组
- `调度频率`: 巡航 5 分钟 / 盯盘 30 秒
- `最后验证时间`: 2026-04-22
- `notes`: 用于 A50 期现溢价监控的现货腿

### 1.18 A50 期货主数据源

- `status`: `ACTIVE`
- `module`: `fetchers/premium_fetcher.py`
- `name`: `akshare.futures_global_spot_em`
- `call`: `ak.futures_global_spot_em()`
- `rate_limit`: 建议低于 `5` 次/秒
- `latency`: 中等
- `quality`: 中高
- `fallback`: 单个 A50 合约缺失时跳过该合约；整表失败则跳过 A50 本轮
- `调度频率`: 巡航 5 分钟 / 盯盘 30 秒
- `最后验证时间`: 2026-04-22
- `notes`: 通过筛选 `名称` 含 `A50` 的全部合约构造 A50 多合约溢价对

### 1.19 加密资产稳定币收益率研究台账

- `status`: `RESEARCH_ONLY`
- `module`: `docs/crypto_cash_and_carry_research_20260418.md`
- `name`: `exchange earn/savings flexible rate endpoints`
- `call`: `官方 REST 文档与最小直连验证`
- `rate_limit`: 依交易所而定
- `latency`: 不适用
- `quality`: 研究中
- `fallback`: 暂不接入生产代码
- `调度频率`: 研究阶段，尚未接入调度
- `最后验证时间`: 2026-04-18
- `notes`: 当前仅形成研究台账，公开候选优先 `Bybit`，`Binance/KuCoin` 明确需要鉴权，`OKX/Gate` 公开性仍待确认

---

## 2. Planned Data Sources

以下接口属于后续规划，不属于当前 `MVP` 验收范围。

### 2.1 IB

- `status`: `PLANNED`
- `module`: `fetchers/ib_margin.py`
- `name`: `ib_insync.IB.reqMktData`
- `call`: `ib.reqMktData()`
- `notes`: 等 `ib` 模块进入正式范围后再补完整约束

### 2.2 Macro

- `status`: `PLANNED`
- `module`: `fetchers/ak_macro.py`
- `name`: `TBD`
- `call`: `TBD`
- `notes`: 宏观模块尚未进入当前基线

---

## 3. Update Rules

出现以下情况时，必须更新本文件：

1. 主数据源切换
2. 限流结论变化
3. fallback 规则变化
4. 某数据源从 `PLANNED` 升级为 `ACTIVE`

若变化同时影响需求边界，也要同步更新 `requirements_codex_v1.md`。
