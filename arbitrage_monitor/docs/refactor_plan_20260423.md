# 结构治理执行计划（2026-04-23）

> 适用范围: `arbitrage_monitor`
> 目标: 逐步收敛 `scheduler / tests / db_manager / 参数页 / 目录结构` 的重复与膨胀
> 约束: 不改变业务规则、表结构、调度口径、配置优先级和告警语义

---

## Summary

本轮治理分两步连续完成：

1. 先把已确认的重构路线落盘为仓库正式文档，作为后续执行基线
2. 再按 `P1 -> P2 -> P3` 三阶段实施，始终保持对外行为和现有测试语义稳定

默认执行顺序：

1. `core_scheduler.py` 数据驱动化
2. `tests/test_integration.py` 拆分
3. `db_manager.py` 内部模板化
4. `pages/1_参数设置.py` 声明式收敛
5. 最后再做 `utils/ / config/ / dashboard/` 的目录重组

---

## Phase 0

### 计划文档落盘

- 新建本文件，作为本轮结构治理的执行说明
- 在 `README.md`、`DOC_STANDARDS.md` 中增加导航入口
- 在 `CONTRIBUTING.md` 补一句：当前结构治理以本计划为执行基线
- 在 `progress.md` 增加“结构治理计划已建立”的状态说明，但不提前写成已完成

---

## Phase 1

### 1. `core_scheduler.py` 数据驱动改造

目标：

- 去掉重复的 `run_*_mode()` 包装函数
- 保留当前 job 注册、状态码、日志和模块语义

实施约束：

- 提取交易时段判断到 `utils/trading_session.py`
- 在 `core_scheduler.py` 中新增统一任务注册表
- 新增 `run_module_task(task_key)` 统一执行入口
- 保留现有 `run_futures_cruise_mode()` 等函数名，但压缩为薄 wrapper
- `schedule_jobs()` 继续显式注册各个 job，不做自动 closure 生成
- `persist_runtime_data()` 暂不抽象

验收：

- 所有现有 `run_*_mode()` 对外仍存在
- 所有现有 `job id / job name / status` 不变
- `premium / sentiment / metals / futures / convertible` 的巡航/盯盘逻辑保持一致

### 2. `tests/test_integration.py` 拆分

目标：

- 把单文件大测试拆成按能力分组的 pytest 文件
- 保持原有断言和覆盖语义

实施约束：

- 新增 `tests/conftest.py`
- 拆为：
  - `test_scheduler.py`
  - `test_notification.py`
  - `test_runtime_config.py`
  - `test_dashboard.py`
  - `test_snapshot_storage.py`
  - `test_retention_and_ops.py`
  - `test_futures.py`
  - `test_convertible.py`
  - `test_metals.py`
  - `test_premium.py`
- 原 `main()` 聚合器移出测试文件，必要时单独保留为脚本
- 优先机械迁移，不顺手重写测试框架

验收：

- pytest 可按文件单独执行
- 原有覆盖场景都能找到对应归属
- `scheduler / premium / notification` 可单独快速运行

---

## Phase 2

### 3. `db_manager.py` 内部模板化

目标：

- 消除 5 类 snapshot 保存流程的重复
- 保持 `DBManager` 对外接口完全稳定

实施约束：

- 在 `db_manager.py` 内新增私有模板 helper
- 统一：
  - 获取 latest rows
  - 计算 state
  - classify skip/update/insert
  - 执行 SQL
  - 更新 latest_rows cache
- 各 snapshot 继续保留各自的 latest query / build state / build row / update sql / insert sql
- `save_futures_margin_snapshots()` 暂不并入统一模板
- `alert_history / cooldown_state / source_health_status / job_run_status / config_change_history` 暂不拆子 store

明确不做：

- 不拆 `utils/db/`
- 不引入新的 public `SnapshotStore`
- 不改 SQL schema
- 不改快照去重逻辑
- 不改 `alert_history` 现有语义

验收：

- `save_*_snapshots` 行为一致
- snapshot dedup / latest reader / retention 测试保持通过
- `db_manager.py` 明显减少重复，同时仍保持单一入口

### 4. `pages/1_参数设置.py` 声明式收敛

目标：

- 减少页面重复
- 不把所有面板一口气黑盒化

实施约束：

- 先抽公共片段函数：
  - runtime 开关区
  - 频率区
  - 时间窗口区
  - 阈值表格渲染区
  - 保存后配置审计回写区
- 再引入轻量 panel config
- `A50` 与 `加密货币` 保持两块独立 UI，但共享底层 premium 表单片段
- `金属 / 期指` 的 reset 按钮保留专门逻辑
- `系统运行` 面板单独保留

明确不做：

- 不改页面顺序
- 不改 widget key 语义
- 不改配置写入路径
- 不改 `record_config_changes()` 目的地判定方式

验收：

- 每个面板保存逻辑与当前一致
- `premium` 两块面板继续共享同一套 runtime 字段
- 不出现 session state / form key 冲突

---

## Phase 3

### 5. 目录重组

目标：

- 在前面逻辑去重完成后，再做认知层整理
- 该阶段单独提交，不混逻辑改动

实施约束：

- 将业务配置助手迁入 `config/`
  - `futures_thresholds.py`
  - `metals_thresholds.py`
  - `premium_thresholds.py`
  - `runtime.py`
  - `audit.py`
- 将 dashboard 辅助迁入 `dashboard/`
  - `tables.py`
- 暂不迁移 `app_dashboard.py` 与 `pages/1_参数设置.py`
- `utils/` 仅保留：
  - `logger.py`
  - `notifier.py`
  - `source_health.py`
  - `db_manager.py`
- `db_manager.py` 是否继续拆为 `utils/db/`，留待本阶段结束后再评估

同步文档：

- 更新 `CONTRIBUTING.md`
- 更新 `DOC_STANDARDS.md`
- 更新 `new_module_integration_guide.md`
- 更新本计划文档中的路径引用

---

## Test Plan

- `scheduler`
  - 巡航/盯盘状态切换
  - session 内外判断
  - watch 优先跳过
  - `premium` 独立模块运行
- `db`
  - snapshot dedup
  - latest snapshot readers
  - retention cleanup
  - premium threshold override / delivery mapping
- `pages`
  - 每个面板保存
  - 阈值 reset
  - 配置审计记录
  - premium A50 / crypto 共用 runtime 正常
- `tests`
  - 拆分后支持按文件运行
  - 聚合运行结果与拆分前等价

---

## Assumptions

- 默认这次是一次连续治理，不只停在 P1
- 默认先落文档，再按阶段实施
- 默认所有阶段都不改变业务规则、表结构、调度口径、配置优先级和告警语义
- 默认 `core_scheduler.py` 第一阶段保留显式 job 注册
- 默认 `db_manager.py` 第一阶段不拆成多个 store 文件
- 默认目录重组最后做，并作为单独提交批次
