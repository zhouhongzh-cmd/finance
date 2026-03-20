# 文档规范与基线说明

> 当前生效的需求基线: `docs/requirements_codex_v1.md`
> 本文档用于定义哪些文档是当前事实来源，哪些只是历史记录。

---

## 1. 文档分层

当前项目文档分为四类：

### A. 主规范文档

这些文档定义当前版本真实规则：

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

## 5. AI 使用要求

1. 进入项目后优先读取 `requirements_codex_v1.md`。
2. 不要把 `requirements.md` 当作当前唯一事实来源。
3. 不要根据历史日志推断当前能力已完整实现。
4. 对“通知已入队”和“通知已送达”必须严格区分。
