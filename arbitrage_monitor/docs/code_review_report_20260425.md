# 代码审查报告 2026-04-25

> 修正状态: 本报告记录审查时发现的问题。2026-04-25 后续修正已处理期指交割日后漏合约、默认 pytest 阻断、测试数据库隔离、README 断链/绝对路径、运行指南缺失、测试基准过期和文档建议台账过期等问题。

## 结论

本次审查范围覆盖 `arbitrage_monitor` 的调度器、Dashboard、SQLite 持久化、配置页、数据源抓取器、通知队列、测试与部署文件。

总体判断：当前主流程已经有较完整的测试覆盖，显式运行 `tests/*.py` 通过；但存在 1 个会影响期指监控完整性的业务缺陷，以及 2 个会影响日常验证和运维可信度的问题，建议优先处理。

审查基准：

- 分支：`codex/crypto-carry-research`
- HEAD：`aadf0b0 Refactor arbitrage monitor and fix dashboard snapshot refresh`
- 审查入口：`arbitrage_monitor/`

## 发现的问题

### P1: 期指合约生成在交割日后少抓一组合约

位置：`fetchers/ak_futures.py:41-89`

`get_active_contracts()` 先固定取 `candidate_months[:2]` 作为当月/下月，再追加两个季月，最后才在循环里跳过已过交割日的月份。交割日之后，当月合约会被跳过，但不会补充新的下月或更远季月，导致每个品种只剩 3 个合约。

本地复现结果：

```text
2026-04-16 -> 16 条，月份 ['2604', '2605', '2606', '2609']
2026-04-25 -> 12 条，月份 ['2605', '2606', '2609']
2026-06-20 -> 12 条，月份 ['2607', '2609', '2612']
```

影响：

- 中金所股指期货理论上应持续覆盖当月、下月、当季、下季。
- 交割日后至月底这段时间，Dashboard、快照、策略报警都会缺少远季合约。
- 当前测试没有覆盖“交割日之后”的日期边界。

建议：

- 先过滤掉已过交割日的候选月份，再从有效月份中选当月/下月和后续两个季月。
- 为 `get_active_contracts(date(...))` 增加交割日前、交割日后、季月交割日后的单元测试，断言每个品种仍为 4 个合约。

### P1: 默认 pytest 命令会被已提交的 `test_result.txt` 阻断

位置：`tests/test_result.txt`

在临时副本中执行默认测试命令：

```bash
python3 -m pytest -q
```

结果在收集阶段失败：

```text
ERROR collecting tests/test_result.txt
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xbc in position 647
```

继续显式只跑 Python 测试文件时：

```bash
python3 -m pytest -q tests/*.py
```

结果为：

```text
76 passed, 86 warnings in 1.22s
```

影响：

- 新开发者或 CI 直接运行 `pytest` 会失败，无法得到真实测试结果。
- 失败发生在 collection 阶段，会掩盖业务测试是否通过。

建议：

- 删除或移出 `tests/test_result.txt`，或改名到不被测试发现的归档目录。
- 如果必须保留，增加 pytest 配置明确只收集 `test_*.py` / `*_test.py`。
- 把 CI 或文档中的测试命令固定为 `python3 -m pytest -q tests/*.py`，直到清理完成。

### P1: 测试直接写默认生产数据库，隔离性不足

位置：

- `utils/db_manager.py:21-36`
- `tests/test_notification.py:35-50`
- `tests/test_notification.py:120-183`

`DBManager()` 默认使用 `arbitrage_monitor/data/monitor_history.db`，且是进程级单例。测试中多处直接 `DBManager()` 并插入 `alert_history`，只有部分用例做了清理。

影响：

- 在真实仓库目录直接跑测试会写入本地运行数据库。
- 通知、流水线、保留期测试可能污染 Dashboard 的报警统计与历史记录。
- 单例设计让测试后续再传自定义 `db_path` 也不会生效，隔离 fixture 很难可靠实现。

建议：

- 给测试加统一 fixture：每个测试进程重置 `DBManager._instance`，并传入临时 SQLite 路径。
- 让 `DBManager` 支持显式 `db_path` 或环境变量覆盖，生产入口仍默认使用当前路径。
- 对会写库的测试补充 `finally` 清理，避免失败时残留测试数据。

### P2: README 链接的运行指南文件不存在

位置：`README.md:18-20`

README 指向 `docs/run_guide.md`，但当前分支没有该文件。

影响：

- 运行入口虽然在 README 中有简写，但详细运行说明链接不可用。
- 和项目文档入口的“当前能力/运行入口”不一致，容易让后续启动或部署排障走错文档。

建议：

- 恢复或新增 `docs/run_guide.md`。
- 如果运行说明已经迁到其他文档，则更新 README 链接。

### P2: README 使用本机绝对路径链接，仓库文档不可移植

位置：`README.md:3`、`README.md:20`、`README.md:32-36`

README 中多处 Markdown 链接写成 `/Users/hikiwa/.../arbitrage_monitor/docs/...` 的本机绝对路径。该路径在当前机器可打开，但换到其他电脑、Docker、GitHub Web 或其他 clone 路径后不可用。

影响：

- 项目入口文档对多机同步和远端阅读不友好。
- 和 `docs/multi_device_sync_guide.md` 中“不把当前电脑目录当成唯一入口”的管理目标冲突。

建议：

- 改为相对路径，例如 `docs/requirements_codex_v1.md`、`docs/DOC_STANDARDS.md`。
- 用一次本地 Markdown 链接检查脚本校验所有相对链接。

### P2: 文档测试基准停留在 36 通过，已与当前测试结果不一致

位置：

- `docs/progress.md:25-27`
- `docs/progress_ai_a_futures.md:6-28`
- `docs/dashboard_phase2.md:120-128`
- `docs/CONTRIBUTING.md:175`
- `docs/requirements_codex_v1.md:17`

多份当前状态文档仍记录“集成测试 36 通过”。本次在临时副本中显式执行 `python3 -m pytest -q tests/*.py` 的结果为 `76 passed, 86 warnings`，同时默认 `python3 -m pytest -q` 仍被 `tests/test_result.txt` 阻断。

影响：

- 文档无法准确反映当前自动化验证状态。
- 新增测试后没有同步 `progress.md`，违反 `DOC_STANDARDS.md` 中 Status Change 必须更新进度文档的规则。
- 容易让后续审查误以为当前测试集仍只有旧规模。

建议：

- 在修复默认 pytest 收集问题后，统一更新 `progress.md`、`CONTRIBUTING.md`、`requirements_codex_v1.md` 和相关专题文档中的测试基准。
- 记录两类命令口径：默认 `pytest` 是否通过，以及显式 `tests/*.py` 是否通过。

### P2: 文档把“16 合约覆盖”写成已完成事实，但代码存在日期边界反例

位置：

- `docs/progress.md:25`
- `docs/progress.md:67`
- `docs/progress_ai_a_futures.md:18-28`
- `docs/dashboard_phase2.md:124-127`
- `docs/api_registry.md:45`

这些文档都把期指 `IF/IH/IC/IM` 各 4 档、合计 16 合约写成当前能力。但本次代码审查复现出交割日后 `get_active_contracts()` 只返回 12 条的情况。也就是说，文档中的“当前能力”没有覆盖日期边界限制。

影响：

- 文档与代码实际行为不一致，且该不一致直接影响监控范围。
- 后续如果只读文档，会误判期指合约覆盖已完全闭环。

建议：

- 优先修代码并补交割日后测试。
- 修复前，在 `progress.md` 的“当前仍未闭环”中增加该边界问题，避免继续把 16 合约覆盖写成无条件完成。

### P3: 文档治理建议本身已经过期，容易制造二次噪音

位置：`docs/文档改进建议.md:7-15`、`docs/文档改进建议.md:81-91`、`docs/文档改进建议.md:108-133`

`文档改进建议.md` 仍写着 `requirements_codex_v1.md` 缺失、`DOC_STANDARDS.md` 缺少版本机制等问题，但当前仓库已经存在完整 `requirements_codex_v1.md`，`DOC_STANDARDS.md` 也已经包含版本号机制、变更门槛和 AI 使用要求。该文档没有标注哪些建议已完成、哪些仍有效。

影响：

- 新接手的人会被过期建议误导。
- 文档目录中“治理文档”没有自身状态，削弱了主基线规则的可信度。

建议：

- 给 `文档改进建议.md` 增加状态列：`OPEN / DONE / OBSOLETE`。
- 已被 `requirements_codex_v1.md`、`DOC_STANDARDS.md` 吸收的条目改为 `DONE` 或移入历史记录区。

### P2: Pydantic V2.11+ 已提示 `model_fields` 实例访问废弃

位置：`config/settings.py:234-268`

测试输出中重复出现：

```text
PydanticDeprecatedSince211: Accessing the 'model_fields' attribute on the instance is deprecated.
```

影响：

- 当前不阻断运行。
- 未来 Pydantic V3 可能变成兼容性问题。

建议：

- 将 `self.model_fields` / `source.model_fields` 改为 `type(self).model_fields` / `type(source).model_fields`。
- 修改后重新跑 `python3 -m pytest -q tests/*.py`，确认 warnings 明显下降。

### P3: Docker 健康检查只验证 SQLite 可打开，不能代表服务健康

位置：

- `Dockerfile:25-26`
- `docker-compose.yml:14-18`
- `docker-compose.yml:31-33`

当前 healthcheck 只执行 `sqlite3.connect(...); SELECT 1`。即使调度器主循环卡住、数据源全部失败、Streamlit 进程不可访问，只要数据库能打开就会被判定为健康。

影响：

- 容器编排层无法准确发现核心服务异常。
- `streamlit_dashboard` 只 `depends_on` 调度器服务创建，不等待真实健康状态。

建议：

- 调度器写入 `job_run_status` 或 heartbeat 后，healthcheck 检查最近更新时间是否在阈值内。
- Dashboard 服务增加 HTTP healthcheck，例如请求 `http://localhost:8501/_stcore/health`。

## 验证记录

### 审查时验证

在临时副本中执行，避免写当前仓库真实数据库：

```bash
python3 -m pytest -q
# 失败：tests/test_result.txt UTF-8 解码错误

python3 -m pytest -q tests/*.py
# 76 passed, 86 warnings in 1.22s

python3 -m compileall -q .
# 通过

python3 -m ruff check .
# 未执行：当前全局 Python 环境未安装 ruff
```

### 修正后验证

```bash
python3 -m pytest -q
# 39 passed, 46 warnings in 1.26s

python3 -m pytest -q tests/*.py
# 77 passed, 86 warnings in 1.14s
```

额外边界验证：

```bash
python3 - <<'PY'
from datetime import date
from fetchers.ak_futures import get_active_contracts
for d in [date(2026,4,16), date(2026,4,25), date(2026,6,20)]:
    rows = get_active_contracts(d)
    print(d, len(rows), sorted(set(sym[2:] for sym, _, _ in rows)))
PY
```

## 优先级建议

1. 先修 `get_active_contracts()` 的交割日后漏合约问题，并补边界测试。
2. 清理 `tests/test_result.txt` 或加 pytest 收集配置，让默认测试命令可用。
3. 给测试数据库做临时路径隔离，避免本地运行数据被测试污染。
4. 补齐 README 指向的运行指南，并把 README 绝对路径改成相对链接。
5. 统一更新文档中的测试基准和期指 16 合约覆盖口径。
6. 清理或标注 `文档改进建议.md` 中已经过期的治理建议。
7. 顺手处理 Pydantic deprecation warning 和 Docker healthcheck。
