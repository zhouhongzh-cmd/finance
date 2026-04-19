# 币圈期现套利公开数据源扩展研究

> 日期: `2026-04-18`
> 目标: 为“币圈期现套利 / cash-and-carry”建立公开数据源台账，覆盖更多交易所的现货、永续、交割合约市场数据能力，并补充稳定币存款费率数据可用性结论
> 当前基线: `docs/requirements_codex_v1.md`
> 说明: 本文档当前属于研究与台账，不代表仓库已正式启动 `crypto` 生产模块

---

## 1. 结论先行

### 1.1 核心判断

1. 期现套利研究的主数据源应优先来自交易所官方公开市场接口，而不是 `yfinance` 这类宽口径行情源。
2. 当前最适合做统一市场数据层的库仍是 `ccxt`，但稳定币存款费率不适合强行统一到 `ccxt`，应优先走各交易所官方 REST。
3. 交易所“官方文档可用”与“当前环境能直连”必须分开记录，不能混为一谈。
4. 稳定币存款费率不能简单写成“支持/不支持”，至少要区分三档：
   - `PUBLIC_NO_AUTH`
   - `PRIVATE_AUTH_REQUIRED`
   - `DOC_EXISTS_BUT_PUBLICITY_UNCONFIRMED`
5. 在当前环境中，`Bitget`、`Gate`、`KuCoin`、`Deribit`、`BitMEX` 的部分公开接口已能直接返回；`Bybit` 与 `Binance` 出现地域限制，`OKX` 直连未拿到有效返回。

### 1.2 本轮建议

1. 市场数据统一层:
   - 研究抽象层: `ccxt`
   - 当前仓库落地实现: `Gate` 官方公开 REST
2. 稳定币费率层:
   - 主候选: `Bybit` 公开 `Earn` 产品信息
   - 私有但结构清晰: `Binance`、`KuCoin`
   - 需继续确认公开性: `OKX`、`Gate`
3. 正式启动 `crypto` 模块前，仍应先更新：
   - `docs/requirements_codex_v1.md`
   - `docs/api_registry.md`

### 1.3 固定白名单资产池

当前 `v1` 固定白名单按“市值前列、排除稳定币与包装资产、且 Gate 上存在现货与至少一种合约腿”落地为：

- `BTC`
- `ETH`
- `XRP`
- `BNB`
- `SOL`
- `DOGE`
- `ADA`
- `TRX`
- `LINK`
- `AVAX`

其中：

- `BTC`、`ETH`、`DOGE` 目前可见 `永续 + 双月度 + 双季度`
- `XRP`、`SOL`、`ADA`、`LINK`、`AVAX` 当前至少可见 `永续 + 双月度`
- `BNB`、`TRX` 当前优先保留 `永续`

---

## 2. 研究范围与假设

### 2.1 研究范围

本轮只覆盖中心化交易所 `CEX`，不纳入：

- `Hyperliquid` 等链上 perp
- DeFi 存款池
- 自动下单与实盘交易接口

### 2.2 默认假设

1. 期货侧同时关注：
   - 永续合约
   - 交割合约
2. 稳定币“存款费率”默认指交易所内以下产品的收益率或利率字段：
   - `Earn`
   - `Savings`
   - `Flexible Saving`
   - `Lend & Earn`
3. 不把营销页上的“最高 `APY`”直接当作结构化研究数据。

### 2.3 本地验证环境说明

本轮除官方文档外，还补了最小直连验证。需要注意：

1. 当前 shell 中 `python3` 无法直接导入 `ccxt`，说明“仓库声明依赖存在”不等于“当前本机环境已安装”。
2. 当前网络环境对部分交易所存在访问限制，尤其是：
   - `Bybit`: 返回 CloudFront 按地区拦截
   - `Binance`: 返回 restricted location
   - `OKX`: 当前环境未拿到有效 API 返回

---

## 3. 交易所市场数据可用性矩阵

字段说明：

- `public_no_auth`: 官方公开接口是否无需鉴权
- `library_primary`: 推荐主接入方式
- `notes`: 只写影响期现套利研究的关键点

| exchange | spot_supported | perpetual_supported | dated_futures_supported | tickers_supported | klines_supported | funding_supported | open_interest_supported | mark_price_supported | index_price_supported | public_no_auth | library_primary | 来源类别 | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OKX | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | `ccxt` + 官方 REST | 官方公开文档 | 官方文档声明 public market data 覆盖 `tickers/candles/funding/index/mark/OI`；当前环境未完成直连验证 |
| Bybit | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | `ccxt` + 官方 REST / `pybit` | 官方公开文档 + 环境实测 | `V5` 统一 `spot/linear/inverse/option`；当前环境直连 `api.bybit.com` 被 CloudFront 按地区拦截 |
| Binance | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | `ccxt` + 官方 REST / Binance Python Connectors | 官方公开文档 + 环境实测 | 文档完整区分 `Spot/UM Futures/CM Futures`；当前环境直连返回 restricted location |
| Deribit | 有限 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 官方 REST | 官方公开文档 + 环境实测 | 衍生品能力强；现货腿覆盖相对有限，适合做 `BTC/ETH` 衍生品研究补充，不适合作为全市场现货主源 |
| Gate | 是 | 是 | 待确认 | 是 | 是 | 是 | 间接可得 | 是 | 是 | 是 | `ccxt` + 官方 REST | 官方公开文档 + 环境实测 | 文档明确 spot/perpetual public endpoints；实测现货 ticker 与合约详情可返回，交割合约覆盖需继续核验 |
| KuCoin | 是 | 是 | 待确认 | 是 | 是 | 是 | 待确认 | 待确认 | 待确认 | 是 | `ccxt` + 官方 REST | 官方公开文档 + 环境实测 | Spot 与 Futures 域名分离；实测现货 `level1` 与 futures current funding 均可返回 |
| Bitget | 是 | 是 | 待确认 | 是 | 是 | 待确认 | 是 | 待确认 | 待确认 | 是 | `ccxt` + 官方 REST | 官方公开文档 + 环境实测 | 已实测 `open-interest` 返回；需继续补 funding、mark、index 和现货联动验证 |
| BitMEX | 有限 | 是 | 是 | 是 | 是 | 有 | 是 | 是 | 是 | 是 | 官方 REST | 官方公开文档 + 环境实测 | 衍生品公开数据强；现货腿存在但不适合作为主现货数据源，适合衍生品结构研究 |

### 3.1 重点交易所补充判断

#### OKX

- 官方文档明确公开市场数据涵盖：
  - `tickers`
  - `candles`
  - `funding rate`
  - `index prices`
  - `mark prices`
  - `open interest`
- 当前环境没有拿到稳定有效返回，因此此处结论主要依赖官方文档，而不是本地直连。

#### Bybit

- `V5` 统一 `spot/linear/inverse/option`，对期现套利研究非常友好。
- `instrument info`、`tickers`、`funding history`、`open interest` 均有公开文档。
- 当前环境直连被区域策略拦截，因此部署前必须单独做网络可达性检查。

#### Binance

- 公共文档最完整，且现货、`UM Futures`、`CM Futures` 分层清晰。
- 但当前环境直连公开接口时已返回地域限制文案。
- 这意味着：
  - 文档层面是强候选
  - 当前环境落地时有现实可达性风险

#### Deribit

- 非常适合做 `BTC/ETH` 的 perp/futures 研究。
- 实测 `BTC-PERPETUAL` 公开 ticker 可直接返回 `index_price`、`mark_price`、`open_interest`、`current_funding` 等字段。
- 现货覆盖不够广，应视为衍生品侧补充源，而不是主现货源。

#### Gate

- 实测现货 ticker:
  - `GET /api/v4/spot/tickers?currency_pair=BTC_USDT`
- 实测 USDT 合约详情:
  - `GET /api/v4/futures/usdt/contracts/BTC_USDT`
- 返回里可直接看到：
  - `funding_rate`
  - `mark_price`
  - `index_price`
  - `funding_interval`
- 交割合约能力本轮未做完整枚举，先标记为待确认。

#### KuCoin

- 实测现货：
  - `GET /api/v1/market/orderbook/level1?symbol=BTC-USDT`
- 实测期货当前资金费率：
  - `GET https://api-futures.kucoin.com/api/v1/funding-rate/XBTUSDTM/current`
- Spot 与 Futures 需要分域名和分接口处理，不适合只靠单一手写 URL 猜测。

#### Bitget

- 实测：
  - `GET /api/v3/market/open-interest?category=USDT-FUTURES&symbol=BTCUSDT`
- 已确认公开 `open_interest` 能力。
- 仍需继续核验：
  - funding
  - mark/index
  - spot 现货腿字段映射

#### BitMEX

- 实测 `instrument` 可直接返回：
  - `listing`
  - `referenceSymbol`
  - `initMargin`
  - 合约结构字段
- 很适合做衍生品结构、到期属性、保证金规则研究。
- 现货腿不适合做主研究源。

### 3.2 本轮已执行的最小直连验证

| exchange | endpoint | 结果 |
| --- | --- | --- |
| Bybit | `https://api.bybit.com/v5/earn/product?category=FlexibleSaving&coin=USDT` | CloudFront `403`，提示按国家/地区拦截 |
| Binance | `https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT` | 返回 restricted location |
| Gate | `https://api.gateio.ws/api/v4/spot/tickers?currency_pair=BTC_USDT` | 正常返回现货 ticker |
| Gate | `https://api.gateio.ws/api/v4/futures/usdt/contracts/BTC_USDT` | 正常返回 `funding_rate/mark_price/index_price` |
| KuCoin | `https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=BTC-USDT` | 正常返回现货盘口 |
| KuCoin | `https://api-futures.kucoin.com/api/v1/funding-rate/XBTUSDTM/current` | 正常返回当前 funding |
| Bitget | `https://api.bitget.com/api/v3/market/open-interest?...` | 正常返回 OI |
| Deribit | `https://www.deribit.com/api/v2/public/ticker?instrument_name=BTC-PERPETUAL` | 正常返回 `mark/index/OI/funding` |
| BitMEX | `https://www.bitmex.com/api/v1/instrument?symbol=XBTUSD...` | 正常返回合约元数据 |

---

## 4. 稳定币存款费率可用性矩阵

字段说明：

- `rate_field`: 上游文档或返回中最关键的收益字段名
- `rate_semantics`: 收益口径解释
- `publicity_level`: `PUBLIC_NO_AUTH` / `PRIVATE_AUTH_REQUIRED` / `DOC_EXISTS_BUT_PUBLICITY_UNCONFIRMED`
- `history_supported`: 是否明确存在历史费率或历史记录查询能力

| exchange | product_type | asset | rate_field | rate_semantics | publicity_level | auth_required | history_supported | library_or_access_path | 来源类别 | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Bybit | `FlexibleSaving` | `USDT/USDC` 等 | `estimateApr` | 预估活期收益率 | `PUBLIC_NO_AUTH` | 否 | 文档未明确费率历史 | 官方 REST / `pybit` | 官方公开文档 | `GET /v5/earn/product` 文档明确无需鉴权，是当前最强公开候选 |
| Binance | `Simple Earn Flexible` | `USDT/USDC` 等 | `APR` / 费率历史接口 | 活期收益率 / 费率历史 | `PRIVATE_AUTH_REQUIRED` | 是 | 是 | 官方 REST / Binance Python Connectors | 官方文档 / 官方示例 | 当前主要接口为 `USER_DATA`，不能归类为公开数据源 |
| KuCoin | `Savings` | 稳定币可筛选 | `returnRate` | 储蓄产品收益率 | `PRIVATE_AUTH_REQUIRED` | 是 | 文档未明确单独费率历史 | 官方 REST | 官方公开文档 | `Get Savings Products` 文档明确为 `Private` |
| Gate | `Earn / Lend & Earn / uni` | 稳定币待筛选 | 待确认 | 待确认 | `DOC_EXISTS_BUT_PUBLICITY_UNCONFIRMED` | 待确认 | 待确认 | 官方 REST | 官方文档 / 官方公告 | 已确认 Earn API 存在且近期有迁移公告，但公开收益字段是否可无鉴权查询，本轮证据不足 |
| OKX | `Earn / Savings` | 稳定币待筛选 | 待确认 | 待确认 | `DOC_EXISTS_BUT_PUBLICITY_UNCONFIRMED` | 待确认 | 待确认 | 官方 REST | 官方文档 | 当前已确认 OKX 市场数据公开，不等于 Earn 收益率公开 |

### 4.1 关于“存款费率”的口径约束

后续若接入真实费率表，必须明确区分三类值：

1. 浮动活期收益
   - 例如 `Flexible Saving`
   - 适合作为“持币空仓资金占用收益”的粗略补充
2. 锁仓收益
   - 不应直接与现金套利的短期滚动收益横向比较
3. 活动补贴收益
   - 不能直接当作长期可复用真实费率

---

## 5. 库选型与接入建议

### 5.1 市场数据层

#### 主方案: `ccxt`

适用场景：

- 快速比较多个交易所是否有相同市场
- 统一拉取：
  - `fetch_markets`
  - `fetch_ticker`
  - `fetch_ohlcv`
  - 部分交易所的 funding / OI 扩展能力

优点：

1. 统一抽象层，研究期起步最快
2. 对现货与衍生品都能做基础行情拉取
3. 更适合先做“交易所能力矩阵”而不是立即写很多专有 client

限制：

1. 交易所特有字段不一定统一暴露
2. `funding history`、`open interest history`、`mark/index price` 等衍生品特有能力，仍要逐交易所核验
3. 当前本地 shell 未装好 `ccxt` 运行环境，不能把“计划可用”误写成“已本地跑通”

#### 备方案: 官方 SDK / 官方 REST

- `Bybit`: `pybit`
- `Binance`: Binance Python Connectors
- `OKX`: 优先官方 REST 文档
- `Deribit`: 官方 REST / WebSocket

适用场景：

- 需要交易所特有字段
- 需要更完整的 funding / OI / instrument metadata
- 需要避开 `ccxt` 抽象层屏蔽掉的能力差异

### 5.2 稳定币收益率层

不建议把稳定币收益率强行统一到 `ccxt`。

建议顺序：

1. 先走官方 REST
2. 每家交易所单独定义字段映射
3. 明确收益口径
4. 再决定是否抽象成统一模型

推荐最小字段：

- `exchange`
- `asset`
- `product_type`
- `rate_field`
- `rate_value`
- `rate_semantics`
- `is_promotional`
- `auth_required`
- `timestamp`

---

## 6. 最小可落地原型建议

### 6.1 阶段一: 研究原型

目标：

- 不写交易逻辑
- 只做市场数据与费率台账

建议步骤：

1. 用 `ccxt` 验证至少 `3` 家交易所的：
   - `BTC/USDT` 现货
   - `BTC` perp 或 futures
2. 用官方 REST 补齐至少 `2` 家交易所的：
   - funding
   - OI
3. 用官方 REST 补齐至少 `1` 家交易所的：
   - 稳定币活期收益率

### 6.2 阶段二: 若正式启动 `crypto` 模块

应先做文档基线升级，再写代码：

1. 更新 `docs/requirements_codex_v1.md`
2. 更新 `docs/api_registry.md`
3. 再新增：
   - `fetchers/crypto_*`
   - `strategies/crypto_*`
   - 对应 tests / fixtures

---

## 7. 建议的后续验证命令

以下命令适合作为下一轮最小 smoke check。

### 7.1 公开 REST

```bash
curl -s 'https://api.gateio.ws/api/v4/spot/tickers?currency_pair=BTC_USDT'
curl -s 'https://api.gateio.ws/api/v4/futures/usdt/contracts/BTC_USDT'
curl -s 'https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=BTC-USDT'
curl -s 'https://api-futures.kucoin.com/api/v1/funding-rate/XBTUSDTM/current'
curl -s 'https://api.bitget.com/api/v3/market/open-interest?category=USDT-FUTURES&symbol=BTCUSDT'
curl -s 'https://www.deribit.com/api/v2/public/ticker?instrument_name=BTC-PERPETUAL'
curl -s 'https://www.bitmex.com/api/v1/instrument?symbol=XBTUSD&count=1&reverse=true'
```

### 7.2 `ccxt` 原型

```python
import ccxt

for ex_id in ["okx", "bybit", "gateio"]:
    ex = getattr(ccxt, ex_id)({"enableRateLimit": True})
    ex.load_markets()
    print(ex_id, ex.fetch_ticker("BTC/USDT")["last"])
```

注意：

- 本地需先确保 `ccxt` 已安装
- `Bybit` / `Binance` / `OKX` 还要先确认当前部署网络能直连

---

## 8. 本轮结论汇总

1. 若只看“公开市场数据能力”，第一梯队仍是：
   - `OKX`
   - `Bybit`
   - `Binance`
2. 若叠加“当前环境直连可用性”，本轮更容易先落地验证的是：
   - `Gate`
   - `KuCoin`
   - `Bitget`
   - `Deribit`
   - `BitMEX`
3. 若只看“公开稳定币活期收益率接口”，当前最有明确证据的是：
   - `Bybit`
4. 若只看“费率接口结构存在但需要鉴权”，当前最明确的是：
   - `Binance`
   - `KuCoin`
5. 若后续继续实现，建议优先顺序为：
   - 先做 `Gate + KuCoin + Deribit + Bitget` 的研究原型
   - 再处理 `OKX / Bybit / Binance` 的网络与区域限制
