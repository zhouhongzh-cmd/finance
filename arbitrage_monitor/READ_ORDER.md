# AI Read Order

> 当前项目的主需求基线已切换到 `docs/requirements_codex_v1.md`。
> `docs/requirements.md` 仅保留为历史兼容入口，不再作为首选事实来源。

---

## Required Reading Order

在生成代码、计划或修改任何文件之前，必须按以下顺序阅读：

1. `docs/requirements_codex_v1.md`
作用：理解当前版本的 `MVP`、数据契约、失败处理、通知语义和验收标准。

2. `docs/CONTRIBUTING.md`
作用：理解当前协作边界、可修改文件范围和文档更新规则。

3. `docs/api_registry.md`
作用：确认当前 `MVP` 实际使用的数据源、限制和降级路径。

4. `docs/DOC_STANDARDS.md`
作用：确认哪份文档是当前基线，哪些文档属于历史记录。

5. `docs/progress.md`
作用：查看当前交付状态、待补能力和历史子进度链接。

6. `docs/multi_device_sync_guide.md`
作用：当需要在多台电脑之间同步代码、配置 GitHub SSH 或切换工作机器时，按此文档执行。

---

## Historical Notes

以下文档仍可参考，但不应优先用作当前实现依据：

- `docs/requirements.md`
- `docs/code_review_report.md`
- `docs/progress_ai_*.md`

这些文档主要反映旧阶段设计、审查结果或历史过程。

---

## Post-Task Rules

完成任务后应遵守：

1. 在合适的 `progress` 文档中记录结果或状态变化。
2. 若外部接口限制或降级策略发生变化，更新 `docs/api_registry.md`。
3. 若需求边界发生变化，优先修改 `docs/requirements_codex_v1.md`，再改代码。
