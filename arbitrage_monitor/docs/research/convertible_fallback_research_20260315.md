# Convertible Fallback Research

> 日期: 2026-03-15
> 目标: 为可转债模块寻找东方财富降级源之外的字段补全方案
> 背景: 当前 `ak.bond_zh_cov()` 只能提供基础行情、转股价值和溢价率，无法直接提供 `YTM`、双低等完整策略字段

---

## 1. 结论摘要

经过实际联网调研，当前最可落地的补全方案不是简单再换一个 `akshare` 接口，而是：

1. **主方案**
   使用 **东方财富 `datacenter` 结构化接口** 作为降级主源，补齐：
   - 当前债券价格
   - 转股价
   - 转股价值
   - 转股溢价率
   - 回售触发价
   - 强赎触发价
   - 起息日
   - 到期日
   - 票息说明
   - 到期赎回条款

   在此基础上，**本地计算 `YTM`**。

2. **辅方案**
   使用 **同花顺可转债/F10 页面** 补静态债券条款：
   - 到期日期
   - 信用评级
   - 票面利率说明
   - 部分转股相关静态信息

3. **不推荐作为主要补源**
   - 继续依赖 `ak.bond_zh_cov()` 单源
   - 未认证雪球
   - 只靠列表页 JSON 的同花顺申购页

---

## 2. 已验证的数据源

### 2.1 东方财富 detail.js 背后的 datacenter 接口

#### 页面入口

- `https://data.eastmoney.com/kzz/detail/127113.html`
- 页面脚本: `https://data.eastmoney.com/newstatic/js/kzz/detail.js`

#### 已确认的结构化接口

- `https://datacenter-web.eastmoney.com/api/data/v1/get`

#### 已确认的关键参数

- `reportName=RPT_BOND_CB_LIST`
- `columns=ALL`
- `quoteColumns=...`
- `source=WEB`
- `client=WEB`
- `filter=(SECURITY_CODE="127113")`

#### 已实测可拿到的字段

以 `127113` 为例，实测可取到：

- `CURRENT_BOND_PRICENEW`
- `TRANSFER_PRICE`
- `TRANSFER_VALUE`
- `TRANSFER_PREMIUM_RATIO`
- `REDEEM_TRIG_PRICE`
- `RESALE_TRIG_PRICE`
- `CONVERT_STOCK_PRICE`
- `COUPON_IR`
- `INTEREST_RATE_EXPLAIN`
- `BOND_START_DATE`
- `EXPIRE_DATE`
- `REDEEM_CLAUSE`
- `RESALE_CLAUSE`

#### 覆盖范围

实测结果：

- 总记录数约 `1008`
- 分 `3` 页返回
- `pageSize=500` 时，分页结果为 `500 + 500 + 8`

说明：

- 这个接口具备全市场分页抓取能力
- 可以替代当前只依赖 `ak.bond_zh_cov()` 的粗糙降级源

---

### 2.2 东方财富接口的关键限制

该接口**没有直接给出**以下字段：

- `YTM`
- 双低
- 纯债价值

但是它给出的静态条款已经足够支持：

- 本地计算 `YTM`
- 本地计算双低

其中：

- 双低可按 `price + premium_rate` 直接计算
- `YTM` 可按当前价格、票息序列、到期日、到期赎回价做现金流折现求解

---

### 2.3 同花顺可转债/F10 页面

#### 已验证入口

- `https://data.10jqka.com.cn/ipo/kzz/`
- `https://basic.10jqka.com.cn/123266/`
- `https://basic.10jqka.com.cn/123266/detail.html`
- `https://basic.10jqka.com.cn/123266/grade.html`

#### 已验证结果

1. `https://data.10jqka.com.cn/ipo/kzz/`
   返回 JSON，可拿到全市场约 `913` 条转债发行/上市基础清单。

2. `https://basic.10jqka.com.cn/{code}/`
   页面文本中可稳定提取：
   - 到期日期
   - 评级
   - 票面利率说明
   - 部分转股基础信息

#### 适合的用途

- 作为**静态债券条款补源**
- 对冲东方财富某些静态字段缺失或异常

#### 不足

- 没有直接给出 `YTM`
- 没有直接给出双低
- 个别页面对新券/未上市券的数据完整性一般

---

### 2.4 集思录直接接口

尝试直接请求：

- `https://www.jisilu.cn/data/cbnew/cb_list/`

在当前环境中，即使带现有 `.env` 里的 `JSL_COOKIE`，返回仍异常：

- HTTP `200`
- `Content-Type: text/html`
- 实际响应体为空

说明：

- 问题不一定出在 `akshare`
- 很可能是当前 Cookie 已经失效，或集思录对直连方式有额外校验

结论：

- 集思录依然是最强主源
- 但它不适合作为“永不失效”的备源设计

---

## 3. 可落地的字段补全方案

### 方案 A: 东方财富 datacenter + 本地估值计算

这是当前最推荐方案。

#### 可直接拿的字段

- `price`
- `premium_rate`
- `transfer_value`
- `transfer_price`
- `redeem_trig_price`
- `resale_trig_price`
- `bond_start_date`
- `expire_date`
- `interest_rate_explain`
- `redeem_clause`

#### 可本地推导的字段

- `double_low = price + premium_rate`
- `ytm = solve(cashflow_discount_rate)`

#### `YTM` 计算思路

1. 从 `INTEREST_RATE_EXPLAIN` 解析每年票息
2. 从 `BOND_START_DATE` 和 `EXPIRE_DATE` 构造剩余现金流时间点
3. 从 `REDEEM_CLAUSE` 解析“到期按面值的 `110%` / `112%` / `114%` 赎回”等信息
4. 以当前债券价格为现值，使用二分法或牛顿法求解折现率

#### 已完成的可行性验证

对样本券进行了本地计算，得到合理结果，例如：

- `113701 祥和转债` 在价格 `100` 条件下，估算 `YTM ≈ 3.3476%`
- `118066 统联转债` 在价格 `100` 条件下，估算 `YTM ≈ 2.5017%`
- `127113 长高转债` 在价格 `100` 条件下，估算 `YTM ≈ 2.4935%`

结论：

- 该路线技术上可落地
- 比当前 `ak.bond_zh_cov()` 纯降级强很多

---

### 方案 B: 东方财富 datacenter 为主，同花顺补静态字段

适合做双源兜底。

#### 使用方式

- 东方财富负责实时价格、转股价值、溢价率
- 同花顺负责票息说明、评级、到期日期等静态债券信息校验

#### 优点

- 两个源都不依赖 `akshare`
- 一个偏实时，一个偏静态，互补性强

#### 风险

- 需要维护两个解析器
- 同花顺页面是 HTML 文本，结构变动风险高于 JSON 接口

---

### 方案 C: 继续以集思录为主，补做 Cookie 健康检查

这是主源稳定性增强方案，不是备源方案。

建议增加：

- 启动前 Cookie 健康检查
- 当返回 `<=30` 条时明确判定主源降级
- 定时提醒用户更新 Cookie

适合作为主链路治理，但不能替代备用源设计。

---

## 4. 不推荐的方向

### 4.1 只靠 `ak.bond_zh_cov()`

原因：

- 没有 `YTM`
- 没有双低
- 没有完整债性条款
- 只能做基础监控

### 4.2 只靠同花顺申购列表 JSON

原因：

- 字段偏发行/申购视角
- 缺估值字段
- 不足以支撑策略判断

### 4.3 继续寻找匿名雪球补源

原因：

- 当前重点是转债，不是舆情
- 雪球匿名接口限制强，稳定性差

---

## 5. 推荐接入顺序

### 优先级 1

新增一个 **非 `akshare` 的东方财富 datacenter fetcher**，替代当前 `_fetch_live_fallback()`。

目标：

- 保留当前基础行情字段
- 新增静态债券条款字段
- 支持本地 `YTM` 计算

### 优先级 2

在 `models/market_data.py` 中为 `CBData` 增加可选字段，例如：

- `transfer_value`
- `redeem_trig_price`
- `resale_trig_price`
- `expire_date`
- `coupon_schedule`
- `data_quality`

### 优先级 3

实现一个本地 `YTM` 计算模块，单独测试。

### 优先级 4

引入同花顺静态条款页作为校验源，而不是第一时间接主流程。

---

## 6. 最终建议

如果目标是“集思录失效时还能尽量保住双低策略”，最佳路线是：

1. 保留集思录为主源
2. 用东方财富 `datacenter` 取代 `ak.bond_zh_cov()` 作为真正的降级源
3. 在降级源里本地计算 `double_low` 和 `YTM`
4. 同花顺仅作为静态字段校验和补充

这条路线的优势是：

- 不依赖 `akshare` 封装层
- 可直接调用站点真实接口
- 能显著缩小“集思录主源”和“东方财富备源”之间的字段鸿沟
- 后续可逐步演进成双源校验架构

---

## 7. 参考入口

- 东方财富可转债详情页: `https://data.eastmoney.com/kzz/detail/127113.html`
- 东方财富详情脚本: `https://data.eastmoney.com/newstatic/js/kzz/detail.js`
- 东方财富 datacenter 接口: `https://datacenter-web.eastmoney.com/api/data/v1/get`
- 同花顺可转债发行列表: `https://data.10jqka.com.cn/ipo/kzz/`
- 同花顺 F10 详情页: `https://basic.10jqka.com.cn/123266/`
- 集思录转债列表入口: `https://www.jisilu.cn/data/cbnew/cb_list/`
