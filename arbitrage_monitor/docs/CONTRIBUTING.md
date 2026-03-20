# 开发协作指南

> 当前协作基线: `docs/requirements_codex_v1.md`
> 适用范围: `arbitrage_monitor` 当前 `MVP`

---

## 1. 当前目标

当前版本的开发目标是稳定交付以下 `MVP` 能力：

- 期指贴水监控
- 可转债负溢价和双低监控
- 舆情/热度监控
- 调度器
- SQLite 存储
- 冷却期恢复
- Streamlit 看板
- 通知队列框架

以下内容不属于当前协作主线：

- 宏观策略
- 加密货币策略
- 盈透策略
- 自动下单

---

## 2. 当前核心文件

### 只读契约文件

- `docs/requirements_codex_v1.md`
- `config/settings.py`
- `models/market_data.py`
- `models/signals.py`
- `strategies/base.py`

### 当前实现文件

- `fetchers/ak_futures.py`
- `fetchers/ak_convertible.py`
- `fetchers/sentiment_spider.py`
- `strategies/futures_strategy.py`
- `strategies/cb_strategy.py`
- `strategies/sentiment_strategy.py`
- `core_scheduler.py`
- `app_dashboard.py`
- `utils/db_manager.py`
- `utils/logger.py`
- `utils/notifier.py`
- `tests/test_integration.py`

---

## 3. 文档修改规则

### 变更先分类

较大修改开始前，先判断属于哪一类：

- `Contract Change`: 改需求边界、数据契约、调度规则、通知语义、验收标准
- `Design Change`: 改数据源链路、fallback、GUI 结构或专题架构细节
- `Status Change`: 改测试结果、当前完成度、已知限制、阶段状态

### 需求相关

若修改影响范围、验收标准、失败处理、通知语义或数据契约，必须优先更新：

- `docs/requirements_codex_v1.md`

### 接口相关

若修改数据源、限流结论、降级路径或备选接口，必须更新：

- `docs/api_registry.md`

### 进度相关

若完成修复、增加限制说明或补充测试记录，更新：

- `docs/progress.md`
- 对应的 `docs/progress_ai_*.md`
- `docs/DEV_PROCESS.md`

### 收尾检查

较大变更提交前，至少确认：

1. `requirements_codex_v1.md` 与当前代码行为一致
2. `api_registry.md` 与真实数据源 / fallback 顺序一致
3. `progress.md` 中的测试数字已刷新
4. 历史文档没有继续冒充当前事实来源

---

## 4. 开发约束

1. 不要把规划中的模块写成当前已完成能力。
2. 不要在 `progress` 文档里埋新的架构决策。
3. 涉及外部请求时优先使用 fixture 进行开发和验证。
4. 所有策略必须返回 `list[Signal]`。
5. 所有 fetcher 的 `fetch_live()` 和 `fetch_from_fixture()` 必须保持返回类型一致。
6. 单个模块失败不能破坏其他 `MVP` 模块运行。

---

## 5. 测试要求

当前版本至少应覆盖：

- fixture 加载测试
- 策略计算测试
- 调度器基础导入测试
- fallback 场景测试
- cooldown 恢复测试

通知模块当前至少需要明确区分：

- 入队成功
- 远端实际发送成功

不得把“已入队”记成“已送达”。

---

## 6. 后续扩展规则

如果未来启动 `macro`、`crypto` 或 `ib` 模块，必须先做以下动作：

1. 在 `docs/requirements_codex_v1.md` 中把该模块升级为正式范围。
2. 在 `docs/api_registry.md` 中补数据源台账。
3. 再新增代码文件和测试。

未经上述步骤，不得把规划内容写入当前主交付状态。
