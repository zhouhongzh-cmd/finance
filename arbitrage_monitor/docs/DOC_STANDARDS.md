# 文档规范与基线说明

> 当前生效的需求基线: `docs/requirements_codex_v1.md`
> 本文档只定义文档分层、生命周期和优先级；开发变更分类详见 `docs/CONTRIBUTING.md`。

---

## 1. 文档分层

### A. 主规范文档

这些文档定义当前版本真实规则：

- `README.md`：人类入口，负责项目定位、运行入口和关键文档链接。
- `docs/requirements_codex_v1.md`：当前需求边界、数据契约、通知语义和验收标准。
- `docs/CONTRIBUTING.md`：协作边界、变更分类、文档同步规则和测试要求。
- `docs/api_registry.md`：真实数据源、限流结论、fallback 和状态。
- `docs/DOC_STANDARDS.md`：文档分类、生命周期和事实来源优先级。

### A1. 专题设计文档

这些文档承接某一专题的细节设计，但不得与主基线冲突：

- `docs/dashboard_phase2.md`
- `docs/metals_arbitrage_design.md`
- `docs/premium_arbitrage_design.md`

### B. 状态与事故文档

这些文档记录当前状态、历史执行过程和已知事故：

- `docs/progress.md`
- `docs/progress_ai_*.md`
- `docs/DEV_PROCESS.md`
- `docs/error_journal.md`

### C. 历史与兼容文档

这些文档保留旧版本设计、旧清单或已过期治理建议，不再作为首选基线：

- `docs/requirements.md`
- `docs/requirements_gap_checklist.md`
- `docs/文档改进建议.md`

### D. 入口、导航与指南文档

- `AGENTS.md`：唯一 AI 主入口，负责开始前必读、架构边界、不变量和验证口径。
- `CLAUDE.md`：Claude Code 兼容入口，只保留指向 `AGENTS.md` 的项目记忆说明。
- `READ_ORDER.md`：旧链接兼容入口，不再维护独立阅读规则。
- `docs/run_guide.md`：本机直跑、Docker、配置分工和验证步骤。
- `docs/multi_device_sync_guide.md`：多设备同步、GitHub SSH 和工作机器切换。
- `docs/new_module_integration_guide.md`：新增品种或独立模块的落地接入清单。
- `docs/refactor_plan_20260423.md`：当前结构治理执行基线。

### E. 研究文档

研究文档用于记录数据源调研、接口可行性和候选实现，不直接升级为当前能力：

- `docs/research/convertible_and_futures_research_20260315.md`
- `docs/research/convertible_fallback_research_20260315.md`
- `docs/research/convertible_metric_definitions_20260315.md`
- `docs/research/crypto_cash_and_carry_research_20260418.md`

研究结论若被采纳，必须同步到 `requirements_codex_v1.md`、`api_registry.md` 或对应专题设计文档；未同步前只按 `RESEARCH_ONLY` 处理。

### F. 审查与治理报告

审查报告用于记录某次审查发现和复核过程，不直接覆盖当前事实来源：

- `docs/reviews/code_review_report.md`：2026-03-13 历史审查。
- `docs/reviews/code_review_report_20260423.md`：2026-04-23 审查报告。
- `docs/reviews/code_review_report_20260423_codex_reply.md`：2026-04-23 逐条复核批注。
- `docs/reviews/code_review_report_20260425.md`：2026-04-25 审查报告与修正状态。
- `docs/reviews/doc_duplication_analysis_20260426.md`：文档功能重复分析。
- `docs/reviews/doc_review_report_20260427.md`：文档重复与冲突审查。

审查发现进入执行队列时，应闭环到 `docs/error_journal.md`、`docs/progress.md` 或 `docs/DEV_PROCESS.md`；旧报告本身不作为当前待办清单。

### G. 排障总结

- `排障总结/*.md`：运行环境或现场故障的复盘材料。

排障总结形成稳定规则后，应同步到 `docs/error_journal.md`、`AGENTS.md` 或 `scripts/check_standard.py`。

---

## 2. 当前事实来源

若多个文档出现冲突，以以下顺序为准：

1. `docs/requirements_codex_v1.md`
2. `docs/CONTRIBUTING.md`
3. `docs/api_registry.md`
4. 对应专题设计文档
5. `docs/progress.md` 与 `docs/error_journal.md`
6. `docs/run_guide.md`

`README.md`、`AGENTS.md`、`CLAUDE.md`、`READ_ORDER.md` 只负责入口和导航，不覆盖主规范。研究文档、审查报告、历史文档和排障总结只用于回看；其中的结论必须被同步到上方事实来源后，才能作为当前实现依据。

---

## 3. 文档职责

### `docs/requirements_codex_v1.md`

负责定义 `MVP` 范围、`Phase 2` 范围、数据契约、失败与降级规则、调度与时间口径、通知语义和验收标准。

### `docs/CONTRIBUTING.md`

负责定义协作边界、当前可修改模块、变更分类、文档更新规则和测试要求。

### `docs/api_registry.md`

负责定义当前 `MVP` 使用的数据源、限流结论、稳定性评估和 fallback 路径。

### 专题设计文档

`dashboard_phase2.md`、`metals_arbitrage_design.md`、`premium_arbitrage_design.md` 负责展开对应专题的数据契约、阈值语义、快照表和看板口径。

### `docs/progress.md`

负责定义当前交付状态、已知未闭环项和子进度入口。

### `docs/error_journal.md`

负责记录审查发现、开发事故、规则来源和闭环状态。

---

## 4. 生命周期规则

1. 新增长期文档默认放入 `arbitrage_monitor/docs/`，不要写到 `finance/` 根目录。
2. `arbitrage_monitor/` 根目录只保留 `README.md`、`AGENTS.md`、`CLAUDE.md`、`READ_ORDER.md` 这类入口文档。
3. 审查与治理报告放入 `docs/reviews/`，命名使用 `code_review_report_YYYYMMDD.md` 或更明确的 `*_YYYYMMDD.md`。
4. 研究文档放入 `docs/research/`，命名使用主题加日期后缀，并在头部说明 `RESEARCH_ONLY`、`PARTIALLY_ADOPTED` 或 `ARCHIVED`。
5. 发现、修复、驳回、延期等状态必须写入 `error_journal`、`progress` 或报告头部说明，避免旧报告继续冒充当前待办。

---

## 5. 修改规则

1. 需求变化先改 `requirements_codex_v1.md`，再改代码。
2. 接口变化先改 `api_registry.md`，再改抓取逻辑。
3. 实施结果写入 `progress`、`DEV_PROCESS` 或 `error_journal`，不要倒灌到需求文档。
4. 历史文档允许补充说明性注释，但不再继续扩写为当前基线。
5. `Contract Change`、`Design Change`、`Status Change` 的定义、门槛和收尾检查以 `docs/CONTRIBUTING.md` 为准，本文档不重复维护第二份规则。

---

## 6. 文档版本号机制

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

## 7. AI 使用要求

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
