# 文档重复与冲突审查报告

> 生命周期状态: DOC_GOVERNANCE_REVIEW
> 原路径: `finance/doc_review_report.md`
> 归档时间: 2026-04-28
> 说明: 报告中的根目录路径描述反映审查时状态；当前文档生命周期以 `docs/DOC_STANDARDS.md` 为准。
>
> 审查日期：2026-04-27
> 审查范围：项目内全部 37 份 Markdown 文档
> 分支：codex/crypto-carry-research

---

## 一、重复文档

### 1. `PLAN.md`（根目录）与 `docs/refactor_plan_20260423.md` 实质重复

`PLAN.md` 自身第 9-10 行明确写了"默认文档落点建议：`arbitrage_monitor/docs/refactor_plan_20260423.md`"，而 `refactor_plan_20260423.md` 已经存在且内容几乎完全相同。两者同时存在会造成：
- 读者不确定哪个是权威版本
- 后续更新可能只改其中一份，导致分叉

**建议**：删除根目录的 `PLAN.md`，或在 `PLAN.md` 头部加一行"已落盘到 `docs/refactor_plan_20260423.md`，本文件仅保留为历史入口，不再维护正文"。

### 2. 三份代码审查报告 + 一份批注版

| 文件 | 审查时间 | 状态 |
|------|----------|------|
| `arbitrage_monitor/docs/code_review_report.md` | 2026-03-13 | 已标注为历史文档 |
| `code_review_report.md`（根目录） | 2026-04-23 | 最新 Claude 审查 |
| `code_review_report_codex_reply.md`（根目录） | 2026-04-23 | 对上一份的逐条批注 |
| `arbitrage_monitor/docs/code_review_report_20260425.md` | 2026-04-25 | 又一次审查 |

四份审查报告存在大量交叉覆盖，且各报告对同一问题的结论不同（见下节冲突分析）。

**建议**：
- `docs/code_review_report.md` 已被 `DOC_STANDARDS.md` 标为 C 类历史文档，可以保留但不改
- 根目录的两份（`code_review_report.md` + `code_review_report_codex_reply.md`）应移入 `docs/` 或标注为已过时
- `code_review_report_20260425.md` 是最新最准确的，应作为当前有效审查结论

### 3. `requirements.md` 作为跳转页

`requirements.md` 已主动降级为兼容入口，只指向 `requirements_codex_v1.md`。这不算问题，但可以进一步精简——既然已有 `READ_ORDER.md` 和 `DOC_STANDARDS.md` 做导航，这个 35 行的跳转页可以合并。

---

## 二、冲突与矛盾

### 冲突 1：三份审查报告对同一问题结论互相矛盾

| 问题编号 | 问题描述 | `code_review_report.md`（根） | `codex_reply.md` | `code_review_report_20260425.md` |
|----------|----------|------|------|------|
| #4 | `.env` 不在顶层 `.gitignore` | P1 问题 | **驳回**：子目录规则已覆盖 | 未提及 |
| #8 | `DBManager` 单例模式脆弱 | 中等问题 | **驳回**：偏风格，不是缺陷 | 未提及 |
| #11 | Dashboard 缓存刷新期间仍联网抓取 | 中等问题 | **驳回**：当前已走快照优先 | 未提及 |
| #15 | Dockerfile 只启动 scheduler | 轻微问题 | **驳回**：compose 已含 dashboard | 未提及 |
| D3 | 子进度文档严重过时 | P1 问题 | **驳回**：已更新 | 未提及 |
| D5 | `api_registry.md` 未补充加密数据源 | 中等问题 | **驳回**：已记录 | 未提及 |
| D9 | compose 未提供看板服务 | 低优先级 | **驳回**：已有 | 未提及 |

**影响**：如果有人按最早的审查报告执行，会把已解决或不存在的问题重新排进待办。

**建议**：以 `code_review_report_20260425.md` 为当前有效审查结论；在根目录两份旧审查报告头部加 `> ⚠️ 本报告部分结论已被后续复核驳回，请以 docs/code_review_report_20260425.md 为准。`

### 冲突 2：`alert_history` 保留规则语义冲突

这是被多份文档反复指出但**至今未统一**的核心矛盾：

- `requirements_codex_v1.md` §11.3 既写"只保留同一 asset 的最新一条"，又写"保留 14 天历史用于审计和统计"
- 代码实现是 `DELETE FROM alert_history WHERE asset = ?`（不区分策略）
- `progress.md` 写"同一标的全系统只保留最新一条报警"
- `error_journal.md` 最后一条标记为 `WATCH`，说明仍未闭环

**建议**：这是一个需要先定设计再改代码的问题。应先在 `requirements_codex_v1.md` 中统一语义，然后再决定是改代码还是改文档。

### 冲突 3："16 合约覆盖"这一声称与代码实际行为不一致

- `progress.md`、`progress_ai_a_futures.md`、`dashboard_phase2.md`、`api_registry.md` 都写"16 合约覆盖"
- `code_review_report_20260425.md` 复现出交割日后只生成 12 条合约
- 代码修复后可能已解决，但文档中的"16 合约覆盖"没有附加日期边界说明

**建议**：在 `progress.md` 的"已完成"部分明确"16 合约覆盖（交割日后已补边界测试）"，或在"仍未闭环"中标注此边界条件。

### 冲突 4：测试基准数字多文档不一致

| 文档 | 记录的测试数字 |
|------|---------------|
| `progress_ai_integration.md` 历史日志 | "6 通过"、"10/10"、"14/14"、"16/16" |
| `CONTRIBUTING.md` | 默认 pytest 39 通过；兼容套件 77 通过 |
| `progress.md` | 同上 |
| `code_review_report_20260425.md` 初次验证 | 76 passed |
| `code_review_report_20260425.md` 修正后 | 39 passed / 77 passed |

历史子进度文档中的旧数字（如 `progress_ai_integration.md` 的"6 通过"）虽然已被 Current State Summary 覆盖，但历史正文仍可能误导读者。

**建议**：这是轻微问题，当前 Current State Summary 已统一口径。但子进度文档的历史正文可以加一行"以下为历史记录，不代表当前状态"。

### 冲突 5：`DOC_STANDARDS.md` 编号重复

`DOC_STANDARDS.md` 有两个 `## 5.` 小节：
- 第 190-216 行：`## 5. 文档版本号机制`
- 第 218-232 行：`## 5. AI 使用要求`

第二个应为 `## 6.`。

### 冲突 6：`progress_ai_b_convertible.md` 标题重复

第 24-27 行出现了两次 `## 1. 业务目标`。

---

## 三、冗余/可归档文档

| 文档 | 建议 |
|------|------|
| `requirements_gap_checklist.md` | 已标记"已完成"，纯历史准备材料，可移入 `docs/archives/` |
| `code_review_report.md`（docs/） | 已标记历史，建议在文件头更醒目地标注 |
| `convertible_and_futures_research_20260315.md` | 研究文档，已落地，可归档 |
| `convertible_fallback_research_20260315.md` | 同上 |
| `convertible_metric_definitions_20260315.md` | 同上 |
| `PLAN.md`（根目录） | 已落盘到 docs/，根目录可删或改为跳转 |
| `code_review_report.md`（根目录） | 应移入 docs/ 或标注已过时 |
| `code_review_report_codex_reply.md`（根目录） | 同上 |

---

## 四、总结

```
┌─────────────────────────────────────────────────────┐
│            文档重复与冲突分析总览                      │
├──────────────┬──────────────────────────────────────┤
│ 严重冲突 (2) │ 1. alert_history 语义未统一           │
│              │ 2. 审查报告结论互相矛盾                 │
├──────────────┼──────────────────────────────────────┤
│ 中等问题 (3) │ 3. PLAN.md 与 refactor_plan 重复      │
│              │ 4. "16 合约"声称缺边界说明              │
│              │ 5. 根目录两份审查报告应归档/标注         │
├──────────────┼──────────────────────────────────────┤
│ 轻微问题 (3) │ 6. DOC_STANDARDS.md 编号重复 (5→6)    │
│              │ 7. progress_ai_b 标题重复              │
│              │ 8. 子进度文档历史数字可能误导             │
└──────────────┴──────────────────────────────────────┘
```

**优先建议处理顺序**：
1. 统一 `alert_history` 的语义（需先做设计决策）
2. 在根目录两份旧审查报告头部加过时标注
3. 处理 `PLAN.md` 的重复（删除或改为跳转）
4. 修复 `DOC_STANDARDS.md` 和 `progress_ai_b_convertible.md` 的编号/标题错误
5. 归档已完成的 research 文档
