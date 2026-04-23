# 文档规范与基线说明

> 当前生效的需求基线: `docs/requirements_codex_v1.md`
> 本文档用于定义哪些文档是当前事实来源，哪些只是历史记录。

---

## 1. 文档分层

当前项目文档分为四类：

### A. 主规范文档

这些文档定义当前版本真实规则：

- `README.md`
- `requirements_codex_v1.md`
- `CONTRIBUTING.md`
- `api_registry.md`

### A1. 专题设计文档

这些文档承接某一专题的细节设计，但不得与主基线冲突：

- `dashboard_phase2.md`

### B. 进度文档

这些文档记录当前状态和历史执行过程：

- `progress.md`
- `progress_ai_*.md`
- `DEV_PROCESS.md`

### C. 历史文档

这些文档保留旧版本设计或旧审查信息，不再作为首选基线：

- `requirements.md`
- `code_review_report.md`
- `requirements_gap_checklist.md`

### D. 导航文档

- `READ_ORDER.md`
- `README.md` 作为项目入口说明，负责把运行入口、配置入口和主基线链接起来
- `new_module_integration_guide.md` 作为新增品种 / 模块的落地接入清单
- `refactor_plan_20260423.md` 作为当前结构治理执行基线

---

## 2. 当前事实来源

若多个文档出现冲突，以以下顺序为准：

1. `requirements_codex_v1.md`
2. `CONTRIBUTING.md`
3. `api_registry.md`
4. 对应专题设计文档（如 `dashboard_phase2.md`）
5. `progress.md`

历史文档只用于回看，不用于决定当前实现。

---

## 3. 文档职责

### `requirements_codex_v1.md`

负责定义：

- `MVP` 范围
- `Phase 2` 范围
- 数据契约
- 失败与降级规则
- 调度与时间口径
- 通知语义
- 验收标准

### `CONTRIBUTING.md`

负责定义：

- 协作边界
- 当前可修改模块
- 文档更新规则
- 测试要求

### `api_registry.md`

负责定义：

- 当前 `MVP` 使用的数据源
- 限流结论
- 稳定性评估
- fallback 路径

### `dashboard_phase2.md`

负责定义：

- Phase 2 看板专题设计
- 看板视图结构
- 看板快照数据层需求
- 看板交互约束

### `progress.md`

负责定义：

- 当前交付状态
- 已知未闭环项
- 子进度入口

---

## 4. 修改规则

1. 需求变化先改 `requirements_codex_v1.md`，再改代码。
2. 接口变化先改 `api_registry.md`，再改抓取逻辑。
3. 实施结果写入 `progress` 或 `DEV_PROCESS`，不要倒灌到需求文档。
4. 历史文档允许补充“说明性注释”，但不再继续扩写为当前基线。

### 4.1 变更类型

后续所有较大变更，默认先归类，再决定改哪些文件：

- `Contract Change`
  - 影响范围：`MVP` 范围、数据契约、调度规则、失败语义、通知语义、验收标准
  - 必改文件：`requirements_codex_v1.md`
- `Design Change`
  - 影响范围：数据源链路、fallback 顺序、GUI 结构、专题架构方案
  - 必改文件：`api_registry.md`
  - 需要时补充专题设计文档
- `Status Change`
  - 影响范围：测试结果、当前完成度、已知限制、近期决策落地情况
  - 必改文件：`progress.md`、`DEV_PROCESS.md`

**"较大变更"定义门槛**：

| 变更类型 | 门槛标准 |
|----------|----------|
| Contract Change | 任何影响数据契约、调度频率、阈值定义、新增/删除模块的改动 |
| Design Change | 任何数据源替换、GUI 结构变化、fallback 链路调整 |
| Status Change | 任何测试结果更新、完成度变化、新增已知问题 |

> 注：修改配置文件（如 thresholds.json）属于 Design Change，因为影响数据源链路。

### 4.2 推荐更新顺序

涉及代码和文档同时变化时，按以下顺序处理：

1. 先判断本次属于 `Contract Change`、`Design Change`、还是 `Status Change`
2. 修改对应文档基线
3. 再修改代码
4. 运行测试或最小验证
5. 回写 `progress.md` 或 `DEV_PROCESS.md`

### 4.3 交叉一致性检查

每次较大变更完成后，至少检查以下 5 项：

1. `requirements_codex_v1.md` 与当前代码行为是否一致
2. `api_registry.md` 与真实 fetcher / fallback 链路是否一致
3. `progress.md` 中的测试数字是否为最新结果
4. 历史文档是否仍在描述已经失效的“当前能力”
5. 是否把“已入队”“本地成功”“远端送达”混写成同一种状态

---

## 5. 文档版本号机制

### 版本号格式
主基线文档使用 `Vx.y` 格式：
- `x`: 主版本号，当有重大架构变化（新增模块、数据契约变更）时递增
- `y`: 副版本号，当有功能补充、配置扩展时递增

### 版本升级触发条件

| 条件 | 升级类型 |
|------|----------|
| 新增/删除策略模块 | x+1 (主版本) |
| 数据契约字段变化 | x+1 (主版本) |
| 调度规则重大调整 | x+1 (主版本) |
| 新增配置文件 | y+1 (副版本) |
| 阈值定义扩展 | y+1 (副版本) |
| 修复文档内部矛盾 | y+1 (副版本) |

### 版本变更记录
每个主基线文档应在头部添加变更记录：
```markdown
| 版本 | 日期 | 变更内容 |
|------|------|----------|
| V1.0 | 2026-03-15 | 初始版本 |
| V1.1 | 2026-04-23 | 补充xxx |
```

---

## 5. AI 使用要求

### 禁止性规则
1. 进入项目后优先读取 `requirements_codex_v1.md`。
2. 不要把 `requirements.md` 当作当前唯一事实来源。
3. 不要根据历史日志推断当前能力已完整实现。
4. 对”通知已入队”和”通知已送达”必须严格区分。

### 正向指引（AI 应该主动做什么）
1. **主动检查文档时效性**：在修改代码前，先检查对应的需求文档版本号和更新时间
2. **主动检查一致性**：修改后检查 `requirements_codex_v1.md`、`api_registry.md`、`progress.md` 三者是否对齐
3. **主动提示文档过期**：如果发现文档描述与代码实现不一致，应主动指出
4. **主动更新测试数字**：修改测试或新增测试后，应提示更新 `progress.md` 中的测试结果
5. **主动识别未闭环项**：在实现过程中发现的新问题，应主动记录到 `progress.md` 的”当前仍未闭环”部分
