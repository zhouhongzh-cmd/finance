# Requirements Gap Checklist

> 状态: 已完成
> 说明: 本清单中的补强项已用于产出 `docs/requirements_codex_v1.md`，现作为历史准备材料保留。

> 日期: 2026-03-15
> 范围: `docs/requirements.md` 的补强建议清单

## 1. MVP Scope

明确当前必须交付的模块列表。

- `futures`
- `convertible`
- `sentiment`
- `core_scheduler`
- `sqlite`
- `dashboard`
- `notifier` 当前是框架还是完整可发送

## 2. Phase 2 Scope

规划中但不属于当前验收范围的模块。

- `macro`
- `crypto`
- `ib`

## 3. Acceptance Criteria

为每个核心模块补充可执行的验收标准。

- `fetchers`
- `strategies`
- `scheduler`
- `cooldown`
- `dashboard`
- `notification`

## 4. Data Contract

统一定义模型字段语义。

- `timestamp` 用本地时间还是 `UTC`
- `symbol` / `asset` / `name` 的区别
- `source` 是否必填
- 缺失字段允许的默认值
- fallback 数据是否允许降级字段

## 5. Failure And Fallback Rules

统一写明失败处理规则。

- 请求失败时是否抛异常
- 何时重试
- 何时降级
- 何时跳过本轮
- 缺关键字段时哪些策略禁止触发

## 6. Notification Semantics

把通知链路定义清楚。

- 支持哪些渠道
- 发送失败是否重试
- `notified` 字段何时更新
- 冷却期按“信号生成”还是“通知成功”计算
- 心跳是否走同一通知通道

## 7. Scheduler Execution Model

说明并发和执行边界。

- 是多个 `job` 并发，还是单 `job` 内并发
- `fetch`、`evaluate`、`save`、`notify` 的顺序
- 单策略失败是否影响其他策略

## 8. State And Persistence

把运行状态和数据库职责写完整。

- `cooldown_state` 的恢复时机
- 最近一次成功抓取时间存哪里
- 通知结果是否落库
- 失败记录是否持久化

## 9. Observability

定义系统可观测项。

- 每个策略最近成功时间
- 最近失败原因
- 单轮耗时
- 数据源成功率
- 通知队列长度
- 今日报警数统计口径

## 10. Time And Calendar Rules

单独定义时间相关规则。

- 使用哪个时区
- 交易日如何判断
- 午休是否算交易时段
- 节假日是否依赖交易日历还是只按周一到周五

## 11. Testing Strategy

把测试目标写进需求书。

- fixture 测试
- 策略单元测试
- 调度集成测试
- fallback 场景测试
- 重启恢复测试

## 12. Out Of Scope

明确当前不做的内容，防止范围膨胀。

- 不做自动下单
- 不做实时撮合
- 不做高频低延迟交易系统
- 不做分布式部署

## Priority

最值得优先补的 5 项：

1. `MVP Scope`
2. `Acceptance Criteria`
3. `Data Contract`
4. `Failure And Fallback Rules`
5. `Notification Semantics`
