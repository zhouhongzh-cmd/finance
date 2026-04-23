# Dashboard 刷新显示不更新排障总结

检索标签：#Streamlit #APScheduler #SQLite #相对路径 #本地快照

**环境上下文**：
- macOS 本机
- 项目路径：`/Users/hikiwa/Library/CloudStorage/OneDrive-个人/coding/finance/arbitrage_monitor`
- 前端：`Streamlit`
- 后台调度：`APScheduler`
- 存储：`SQLite`
- 涉及模块：`premium`（A50 / 加密货币）

**业务需求**：
- dashboard 页面点击“刷新显示”后，应读取最新本地快照
- `premium_watch` 盯盘模式按 `20s` 周期持续更新本地快照
- 页面展示和后台调度应基于同一份数据库

**异常现象**：
- 点击“刷新显示”后，页面显示“最近操作”时间变了，但表格和“最新快照时间”不变
- 用户已确认 `premium` 使用盯盘模式 `20s` 更新，但页面看不到新数据
- 数据库排查时发现不同模块/页面看到的快照时间不一致
- 机器上残留多个 `core_scheduler.py` 进程

**核心判断点**：
- 第一优先先查 `DBManager().db_path`，确认 dashboard 和 scheduler 是否指向同一份 SQLite 文件
- 再查 `job_run_status` 里的 `premium_watch_mode` 最近状态和完成时间
- 最后查 `premium_arbitrage_snapshot` 的最新 `fetched_at` 是否真的推进

**本质原因**：
- `DBManager` 使用相对路径 `data/monitor_history.db`
- 从不同工作目录启动时，会落到两份不同数据库：
  - `finance/data/monitor_history.db`
  - `arbitrage_monitor/data/monitor_history.db`
- 导致 scheduler 在一份库里写新快照，dashboard 在另一份库里读旧快照
- 同时旧的 scheduler 进程未清理，进一步干扰状态判断

**解决步骤**：
- 将 `DBManager` 默认数据库路径改为项目根目录下的绝对路径
- 清理残留的旧 `core_scheduler.py` 进程
- 重新启动 scheduler 和 dashboard，确保两者都指向同一份项目数据库
- 验证 `premium_watch_mode` 恢复为 `SUCCESS`
- 验证 `premium_arbitrage_snapshot` 的最新时间推进到当前时刻
- 再次点击“刷新显示”，确认页面能读到新快照

**实现原理**：
- “刷新显示”本身只会重读本地 SQLite 快照，不会联网抓新
- 只要 dashboard 和 scheduler 读写的是同一份数据库，页面刷新就能反映后台最新落库结果
- 将数据库路径固定为项目绝对路径后，不再受启动目录影响，避免双库分叉
- 清理重复调度进程后，任务状态、快照写入和页面展示恢复一致
