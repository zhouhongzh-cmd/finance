# 舆情组 (AI-D) 开发进度报告

> 说明: 本文档为历史执行记录。当前项目主基线已切换到 `docs/requirements_codex_v1.md`。

> **更新时间**: 2026-04-23
> **最后同步**: `progress.md` 更新至 2026-04-22，集成测试 36 通过
> **负责人**: AI-D (舆情组)
> **状态**: ✅ 已完成
> **模块职责**: 监控雪球热度等舆情脉冲，进行预警和排雷分析。

---

## Current State Summary

> 更新时间: 2026-04-23

- 舆情模块已实现雪球/东方财富热度监控
- 数据源: 东方财富人气榜 API（主源）、雪球（备源，已失效）
- 核心指标: sentiment_pulse（舆情脉冲）
- **当前集成测试**: 36 通过（与 progress.md 同步）

---

## 1. 负责文件清单
- ✅ `fetchers/sentiment_spider.py` (雪球舆情数据拉取器)
- ✅ `strategies/sentiment_strategy.py` (舆情脉冲与风险排查策略)
- ✅ `tests/fixtures/sentiment_mock.json` (用于防反爬开发测试的数据快照)

## 2. 研发与实盘跑通日志 (RUNTIME_OUTPUT)
于 2026-03-11 完成了防反爬 (Mock json) 验证。

**实盘更新 (2026-03-14)**：
鉴于雪球 API 升级反爬（即使访问主页也无法通过匿名获取有效 Cookie，返回 40016 错误），已将主数据源切换为 **东方财富人气榜 API**。
- **验证结果**：✅ 成功获取全市场 Top 30 热门股票。
- **运行日志**：
```bash
INFO  fetch_sentiment_live_start source='eastmoney'
INFO  fetch_sentiment_live_success count=30 source='eastmoney'
INFO  signal_triggered asset='SH601669' strategy='Sentiment_Heat_and_Risk'
INFO  sent_notification asset='SH601669' strategy='Sentiment_Heat_and_Risk'
```

注：以上日志仅表示通知模块记录了发送事件，不代表远端 webhook 已被严格验证送达。

## 3. 排障避雷录 (TROUBLESHOOTING)
- 🚨 **问题 (2026-03-14)**: 雪球 API 即使配置了自动获取 Cookie，仍返回 `{"error_code":"400016", "error_description":"请刷新页面登录帐号"}`。
- 💡 **方案**: 此问题属于接口方策略整体上调，匿名访问已不可用。系统已完成数据源平替：
  1. 将主数据源改为 **东方财富人气榜 API** (无需认证，高频稳定)。
  2. 保持 `SentimentData` 模型不变，策略计算逻辑无缝衔接。
  3. 雪球保留为备选方案，仅在配置了有效 `XUEQIU_COOKIE` 后激活。
