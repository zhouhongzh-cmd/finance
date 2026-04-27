# 文档功能重复分析报告

> 生命周期状态: DOC_GOVERNANCE_ANALYSIS
> 原路径: `finance/doc_duplication_analysis.md`
> 归档时间: 2026-04-28
> 说明: 报告中的根目录路径描述反映分析时状态；当前文档生命周期以 `docs/DOC_STANDARDS.md` 为准。
>
> 分析时间: 2026-04-26
> 分析范围: `arbitrage_monitor` 全部文档 + `finance/` 根目录文档

---

## 一、发现的重复与重叠

### 🔴 高度重复：[PLAN.md](file:///c:/Users/hikiwa/OneDrive/coding/finance/PLAN.md) 与 [docs/refactor_plan_20260423.md](file:///c:/Users/hikiwa/OneDrive/coding/finance/arbitrage_monitor/docs/refactor_plan_20260423.md)

| 维度 | [finance/PLAN.md](file:///c:/Users/hikiwa/OneDrive/coding/finance/PLAN.md) | [docs/refactor_plan_20260423.md](file:///c:/Users/hikiwa/OneDrive/coding/finance/arbitrage_monitor/docs/refactor_plan_20260423.md) |
|------|-------------------|----------------------------------|
| 行数 | 215 行 | 231 行 |
| 内容 | 结构治理执行计划 | 结构治理执行计划 |
| 定位 | 短期接力/治理计划参考 | 正式执行基线 |

**重叠程度: ~95%**

两份文档的 Phase 0/1/2/3、Test Plan、Assumptions 基本完全一致。区别仅在于：
- [PLAN.md](file:///c:/Users/hikiwa/OneDrive/coding/finance/PLAN.md) 位于 `finance/` 根目录
- [refactor_plan_20260423.md](file:///c:/Users/hikiwa/OneDrive/coding/finance/arbitrage_monitor/docs/refactor_plan_20260423.md) 位于 `arbitrage_monitor/docs/`，是正式落盘后的版本

> [!WARNING]
> `AGENTS.md` 已明确说明："`PLAN.md` 若存在，仅作为短期接力或治理计划参考，不得当作正式项目状态"。
> 
> **建议**: 删除 `finance/PLAN.md`，或在其中只保留一句指向 `docs/refactor_plan_20260423.md` 的跳转链接。

---

### 🔴 高度重复：`finance/code_review_report.md` 与 `docs/code_review_report.md`

| 维度 | `finance/code_review_report.md` (根目录) | `docs/code_review_report.md` (docs) |
|------|------------------------------------------|--------------------------------------|
| 行数 | 331 行 | 357 行 |
| 日期 | 2026-04-23 | 2026-03-13 |
| 内容 | 全量代码+文档审查 | 全量代码审查 |

**关系**: 这是两份不同日期的审查报告，但文件名几乎相同。`docs/code_review_report.md` 是 2026-03-13 的老报告，而 `finance/code_review_report.md` 是 2026-04-23 的新报告。

另外还存在：
- `finance/code_review_report_codex_reply.md`（对 2026-04-23 报告的批注回复）
- `docs/code_review_report_20260425.md`（2026-04-25 的第三份审查报告）

**四份审查相关文档分散在两个目录层级，容易混淆。**

> [!WARNING]
> **建议**: 
> 1. 将 `finance/code_review_report.md` 和 `finance/code_review_report_codex_reply.md` 移入 `docs/` 并加日期后缀
> 2. 或者在 `DOC_STANDARDS.md` 中增加"审查报告"分类，统一收口到 `docs/`

---

### 🟡 中度重复：`AGENTS.md` 与 `CLAUDE.md` 与 `READ_ORDER.md`

这三份文档的**核心功能高度重叠**——都在告诉 AI/开发者"先读什么、遵守什么规则"。

| 功能点 | `AGENTS.md` | `CLAUDE.md` | `READ_ORDER.md` |
|--------|------------|-------------|-----------------|
| 必读文档列表 | ✅ 5 条 | ✅ 5 条 | ✅ 8 条 |
| 架构边界 | ✅ 详细 | ✅ 简略 | ❌ |
| 不变量 | ✅ 7 条 | ❌ | ❌ |
| 禁止事项 | ✅ 5 条 | ❌ | ❌ |
| 优先规则 | ✅ 含在不变量 | ✅ 6 条 | ❌ |
| 验证命令 | ✅ | ✅ 提及 | ❌ |
| 历史文档说明 | ❌ | ❌ | ✅ |
| 任务后规则 | ❌ | ❌ | ✅ |

**重叠内容**:
- 三者都指向 `requirements_codex_v1.md` 为首要阅读
- `AGENTS.md` 和 `CLAUDE.md` 都列出了主入口文件、数据链路、配置分工
- `AGENTS.md` 和 `CLAUDE.md` 都要求提交前运行 `check_standard.py`
- `AGENTS.md` 和 `CLAUDE.md` 都要求同步 `api_registry.md` 和 `requirements_codex_v1.md`

> [!IMPORTANT]
> `CLAUDE.md` 第 1 行已声明"先读 `AGENTS.md`，本文件只补充 Claude Code 使用时的项目记忆入口"，这个分工声明是好的。但实际内容与 `AGENTS.md` 有超过 50% 的语义重复。
>
> **建议**: 
> - `CLAUDE.md` 只保留"指向 `AGENTS.md`"的一句话 + Claude Code 特有的项目事实（如果有的话）
> - `READ_ORDER.md` 可合并进 `AGENTS.md` 的"开始前必读"节，或保留为独立导航但去掉重复

---

### 🟡 中度重复：`CONTRIBUTING.md` 与 `AGENTS.md` 与 `DOC_STANDARDS.md`

| 功能点 | `CONTRIBUTING.md` | `AGENTS.md` | `DOC_STANDARDS.md` |
|--------|-------------------|-------------|---------------------|
| MVP 当前能力 | ✅ 10 条 | ❌ | ❌ |
| 不在 MVP 范围 | ✅ 4 条 | ❌ | ❌ |
| 核心文件列表 | ✅ 详细 | ✅ 简略 | ❌ |
| 不变量/约束 | ✅ 6 条 | ✅ 7 条 | ❌ |
| 文档修改规则 | ✅ 详细 | ✅ 简略 | ✅ 详细 |
| 变更分类 | ✅ 3 类 | ❌ | ✅ 3 类（完全一致） |
| 收尾检查 | ✅ 4 条 | ❌ | ✅ 5 条 |
| 测试要求 | ✅ | ✅ 简略 | ❌ |
| 验证命令 | ❌ | ✅ | ❌ |

**具体重复点**:

1. **变更分类（Contract/Design/Status Change）** 在 `CONTRIBUTING.md` §3 和 `DOC_STANDARDS.md` §4.1 完全重复
2. **收尾检查** 在 `CONTRIBUTING.md` §3.5 和 `DOC_STANDARDS.md` §4.3 高度重复
3. **开发约束** 在 `CONTRIBUTING.md` §4 和 `AGENTS.md` "不变量"节有大量重叠：
   - 策略返回 `list[Signal]`
   - `fetch_live()` 和 `fetch_from_fixture()` 返回类型一致
   - 单模块失败不破坏其他模块
   - 不把规划写成已完成

> [!TIP]
> **建议**: 
> - `CONTRIBUTING.md` 保留详细版的文档修改规则和测试要求
> - `DOC_STANDARDS.md` 只保留文档分层和事实来源优先级，去掉与 `CONTRIBUTING.md` 重复的变更分类和收尾检查（或改为"详见 `CONTRIBUTING.md`"）
> - `AGENTS.md` 的不变量保持为精简版，指向 `CONTRIBUTING.md` 获取完整约束

---

### 🟡 中度重复：`README.md` 与其他文档

`README.md` 的以下内容与其他文档重复：

| README 节 | 重复来源 |
|-----------|---------|
| 当前能力列表 | `CONTRIBUTING.md` §1、`progress.md` §1 |
| 运行入口 | `run_guide.md` §2 |
| 配置说明 | `run_guide.md` §5、`CONTRIBUTING.md` §2 |
| 文档入口 | `DOC_STANDARDS.md`、`READ_ORDER.md` |

> [!NOTE]
> README 作为项目门面，适度重复是合理的。但当前能力列表如果发生变化，需要同步更新三处（README、CONTRIBUTING、progress），容易遗漏。
>
> **建议**: README 的当前能力部分改为"详见 `progress.md`"的链接，减少同步负担。

---

### 🟡 中度重复：`requirements.md` 已退化为空壳

`requirements.md` 当前只有 35 行，全部内容就是"请看 `requirements_codex_v1.md`"。

> [!NOTE]
> 按 `DOC_STANDARDS.md` 的分类，它属于 C 类历史文档。保留作为旧链接兼容入口是合理的，但 35 行的跳转文件有些冗余。
>
> **建议**: 可保留不变，无需处理。

---

### 🟢 低度重复：`requirements_codex_v1.md` 与专题设计文档

| 主题 | `requirements_codex_v1.md` | 专题文档 |
|------|---------------------------|---------|
| 金属策略输入 | §8.5 列了 10 个字段 | `metals_arbitrage_design.md` §4 列了 8 个字段 |
| 金属触发条件 | §8.5 有 3 条规则 | `metals_arbitrage_design.md` §5 有 3 条规则 |
| 期现溢价输入 | §8.6 列了 10 个字段 | `premium_arbitrage_design.md` §4 列了 12 个字段 |
| 期现溢价触发 | §8.6 有 6 条规则 | `premium_arbitrage_design.md` §5 有 6 条规则 |

> [!NOTE]
> 这种重复是**设计上应有的**。`DOC_STANDARDS.md` 明确规定专题文档"承接主基线的展开细节，不得与主基线冲突"。主基线定义边界，专题文档展开实现细节——这是合理的层次化设计。
>
> **建议**: 保持不变，但需注意两者修改时同步。

---

### 🟢 低度重复：`progress.md` 与 `DEV_PROCESS.md`

- `progress.md` 记录**当前交付状态**（113 行）
- `DEV_PROCESS.md` 记录**开发历史变更**（167 行）

两者功能不同，但都包含"测试结果"和"已完成能力"的信息。这种重复是进度文档和变更日志之间的天然重叠，属于**正常范畴**。

---

## 二、重复程度汇总

| 优先级 | 重复对 | 重叠程度 | 建议操作 |
|--------|--------|---------|---------|
| 🔴 P0 | `PLAN.md` ↔ `refactor_plan_20260423.md` | ~95% | 删除 `PLAN.md` 或改为跳转 |
| 🔴 P0 | `finance/code_review_*.md` 散落 | 归属混乱 | 统一移入 `docs/` |
| 🟡 P1 | `AGENTS.md` ↔ `CLAUDE.md` ↔ `READ_ORDER.md` | ~50% | 精简 `CLAUDE.md`，合并阅读顺序 |
| 🟡 P1 | `CONTRIBUTING.md` ↔ `DOC_STANDARDS.md` | ~40% | 变更分类和收尾检查只写一处 |
| 🟡 P2 | `README.md` 能力列表与多文档重复 | ~30% | README 改为链接引用 |
| 🟢 低 | `requirements_codex_v1.md` ↔ 专题设计文档 | 设计性重复 | 保持不变 |
| 🟢 低 | `requirements.md` 空壳 | — | 保留兼容 |

---

## 三、文档总数统计

当前 `arbitrage_monitor` 下共有 **27 份 Markdown 文档**（含根目录文档），其中：

| 分类 | 数量 | 文件 |
|------|------|------|
| AI 入口/导航 | 3 | `AGENTS.md`, `CLAUDE.md`, `READ_ORDER.md` |
| 主规范 | 4 | `README.md`, `requirements_codex_v1.md`, `CONTRIBUTING.md`, `api_registry.md` |
| 文档规范 | 1 | `DOC_STANDARDS.md` |
| 专题设计 | 3 | `dashboard_phase2.md`, `metals_arbitrage_design.md`, `premium_arbitrage_design.md` |
| 操作指南 | 3 | `run_guide.md`, `multi_device_sync_guide.md`, `new_module_integration_guide.md` |
| 进度/历史 | 6 | `progress.md`, `DEV_PROCESS.md`, `progress_ai_*.md` × 4 |
| 审查报告 | 4 | `code_review_report.md` × 2, `code_review_report_20260425.md`, `code_review_report_codex_reply.md` |
| 研究文档 | 3 | `convertible_*.md`, `crypto_*.md`, `convertible_metric_*.md` |
| 治理计划 | 2 | `refactor_plan_20260423.md`, `PLAN.md` (重复) |
| 其他 | 3 | `requirements.md` (空壳), `requirements_gap_checklist.md` (历史), `文档改进建议.md`, `error_journal.md` |

> [!IMPORTANT]
> 如果按建议清理 P0 重复项（删掉 `PLAN.md`、归拢审查报告），可减少 2-3 份文件，同时减少跨位置扫描的认知负担。
