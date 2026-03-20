# 项目代码审查报告

> 说明: 本报告反映 2026-03-13 的审查结论，属于历史审查记录。
> 当前项目主需求基线已切换到 `docs/requirements_codex_v1.md`，阅读本报告时请以新基线为准。

> **审查日期**: 2026-03-13  
> **审查范围**: arbitrage_monitor 项目全部代码与文档  
> **审查人**: AI Assistant

---

## 一、项目概览

本项目是一个**个人金融套利监控系统**，采用纯 Python 技术栈，实现对 A 股多品种（可转债、股指期货、舆情）的实时套利机会监控。

**项目结构**:
```
arbitrage_monitor/
├── config/          # 配置管理
├── models/          # 数据模型
├── fetchers/        # 数据接入层
├── strategies/      # 策略引擎层
├── utils/           # 工具层
├── tests/           # 测试
├── docs/            # 文档
├── core_scheduler.py    # 调度器主入口
└── app_dashboard.py     # Streamlit 看板
```

**已完成模块**:
- ✅ 期指吃贴水策略
- ✅ 可转债负溢价+双低策略
- ✅ 舆情热度监控策略
- ✅ SQLite 数据存储 (WAL 模式)
- ✅ Streamlit Web 看板
- ✅ Docker 部署配置

---

## 二、发现的问题

### 🔴 严重问题 (P0)

#### 1. 飞书/微信通知功能未实现

**位置**: `utils/notifier.py:32-39`

**问题描述**:  
`_send_feishu` 方法只有日志记录，**没有实际发送 HTTP 请求**。用户配置了 Webhook URL 也不会收到任何通知。

**当前代码**:
```python
def _send_feishu(self, signal: Signal):
    if not settings.FEISHU_WEBHOOK_URL:
        logger.info("skip_notification", msg="Webhook url not found", data=signal.message)
        return
        
    color_map = {"INFO": "blue", "WARNING": "yellow", "CRITICAL": "red"}
    # 此处省略具体组装 Feishu Post Card 的网络请求动作代码  ← 问题所在
    logger.info("sent_notification", strategy=signal.strategy_name, level=signal.level, asset=signal.asset)
```

**影响**: 核心功能缺失，报警无法触达用户。

**建议修复**:
```python
def _send_feishu(self, signal: Signal):
    if not settings.FEISHU_WEBHOOK_URL:
        logger.info("skip_notification", msg="Webhook url not found")
        return
    
    color_map = {"INFO": "blue", "WARNING": "yellow", "CRITICAL": "red"}
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"[{signal.level}] {signal.strategy_name}"},
                "template": color_map.get(signal.level, "blue")
            },
            "elements": [
                {"tag": "div", "text": {"tag": "plain_text", "content": signal.message}},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"标的: {signal.asset}"}]}
            ]
        }
    }
    resp = httpx.post(settings.FEISHU_WEBHOOK_URL, json=payload, timeout=10)
    resp.raise_for_status()
    logger.info("sent_notification", strategy=signal.strategy_name, level=signal.level)
```

---

#### 2. 雪球舆情爬虫无法正常工作

**位置**: `fetchers/sentiment_spider.py:30-32`

**问题描述**:  
雪球 API 需要先访问主页获取 Cookie 才能请求 API，当前代码直接请求会返回 403 或空数据。

**当前代码**:
```python
url = "https://stock.xueqiu.com/v5/stock/hot_stock/list.json"
resp = self.client.get(url, headers=headers)  # 缺少必需的 Cookie
resp.raise_for_status()
```

**影响**: 舆情策略无法获取数据。

**建议修复**:
1. 方案一：先请求主页获取 Cookie
2. 方案二：要求用户在 `.env` 中配置 `XUEQIU_COOKIE`
3. 方案三：改用其他数据源（如东方财富热度榜）

---

#### 3. 冷却期状态重启后丢失

**位置**: `core_scheduler.py:44`

**问题描述**:  
`cooldown_cache` 是内存字典，服务重启后状态丢失，可能导致短时间内重复推送报警。

**当前代码**:
```python
cooldown_cache: Dict[str, datetime] = {}  # 重启后为空
```

**影响**: 服务重启后可能触发消息轰炸。

**建议修复**:
```python
def restore_cooldown_from_db():
    """启动时从数据库恢复冷却期状态"""
    with db_manager.get_connection() as conn:
        cursor = conn.execute("SELECT strategy_key, last_alert FROM cooldown_state")
        for row in cursor.fetchall():
            key, last_alert = row
            cooldown_cache[key] = datetime.fromisoformat(last_alert)
    logger.info("cooldown_restored", count=len(cooldown_cache))

# 在 main() 中调度器启动前调用
restore_cooldown_from_db()
```

---

### 🟡 中等问题 (P1)

#### 4. 缺少 `__init__.py` 文件

**位置**: `config/`, `models/`, `fetchers/`, `strategies/`, `utils/`, `tests/`

**问题描述**:  
所有包目录都没有 `__init__.py` 文件。虽然 Python 3.3+ 支持隐式命名空间包，但作为完整项目应显式创建。

**影响**: 
- 导入路径可能不稳定
- 无法在 `__init__.py` 中控制导出符号
- 不符合 Python 包规范

**建议修复**: 为各目录创建空的 `__init__.py` 文件。

---

#### 5. `requirements.txt` 缺少 `pandas` 依赖

**位置**: `requirements.txt`

**问题描述**:  
`app_dashboard.py:12` 使用了 `pandas`，但依赖文件未列出。

**影响**: Docker 构建或新环境部署会失败。

**建议修复**:
```txt
akshare>=1.10.0
httpx>=0.27.0
tenacity>=8.2.0
apscheduler>=3.10.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
streamlit>=1.30.0
structlog>=24.1.0
pandas>=2.0.0          # 新增
ccxt>=4.0.0
ib_insync>=0.9.8
```

---

#### 6. 测试 fixture 数据不完整

**位置**: `tests/fixtures/cb_mock.json`, `tests/fixtures/futures_sample.json`

**问题描述**:  
- `cb_mock.json` 缺少 `price` 和 `ytm` 字段
- `futures_sample.json` 缺少 `days_to_maturity` 字段

**当前 `cb_mock.json`**:
```json
{
    "symbol": "113058(安22转债)",
    "timestamp": "2026-03-11T14:00:00Z",
    "premium_rate": -2.5,
    "double_low": 115.2
    // 缺少 price 和 ytm
}
```

**影响**: 测试数据不够真实，无法覆盖完整逻辑。

**建议修复**: 补充完整字段。

---

#### 7. logger 初始化重复调用

**位置**: `utils/logger.py:21`, `core_scheduler.py:37`

**问题描述**:  
`configure_logger()` 被调用两次，可能导致日志配置冲突。

**建议修复**: 移除 `logger.py` 模块级的 `configure_logger()` 调用，仅在入口文件调用。

---

#### 8. 数据库连接频繁创建/关闭

**位置**: `utils/db_manager.py:43-50`

**问题描述**:  
每次操作都创建新连接，虽然可用但效率不高。

**建议修复**: 考虑使用连接池或线程局部存储的持久连接。

---

### 🟢 轻微问题 (P2)

#### 9. 舆情策略测试缺失

**位置**: `tests/test_integration.py`

**问题描述**:  
没有测试 `SentimentStrategy`，尽管 `sentiment_mock.json` fixture 存在。

---

#### 10. 缺少单元测试

**问题描述**:  
只有集成测试，缺少各模块的单元测试（如策略计算、数据解析等）。

---

#### 11. 缺少 `.gitignore` 文件

**问题描述**:  
项目中没有 `.gitignore`，敏感文件和编译产物可能被误提交。

**建议添加**:
```gitignore
# Python
__pycache__/
*.py[cod]
*.pyo
.env
*.db
*.db-wal
*.db-shm

# IDE
.idea/
.vscode/
*.swp

# Distribution
dist/
build/
*.egg-info/
```

---

#### 12. `.env` 文件存在于工作区

**问题描述**:  
敏感配置文件可能被误提交，需确保在 `.gitignore` 中排除。

---

## 三、问题统计

| 级别 | 数量 | 说明 |
|------|------|------|
| 🔴 P0 严重 | 3 | 核心功能缺失或无法工作 |
| 🟡 P1 中等 | 5 | 影响稳定性或规范性 |
| 🟢 P2 轻微 | 4 | 代码质量改进项 |
| **总计** | **12** | |

---

## 四、修复优先级建议

### 立即修复 (P0)

| 序号 | 问题 | 预计工作量 |
|------|------|-----------|
| 1 | 实现飞书/微信通知发送逻辑 | 30分钟 |
| 2 | 修复雪球爬虫或更换数据源 | 1小时 |
| 3 | 启动时恢复冷却期状态 | 15分钟 |

### 短期修复 (P1)

| 序号 | 问题 | 预计工作量 |
|------|------|-----------|
| 4 | 添加 `__init__.py` 文件 | 10分钟 |
| 5 | 更新 `requirements.txt` | 5分钟 |
| 6 | 补充 fixture 数据字段 | 10分钟 |
| 7 | 修复 logger 初始化 | 5分钟 |

### 后续优化 (P2)

| 序号 | 问题 | 预计工作量 |
|------|------|-----------|
| 8-12 | 添加测试、`.gitignore` 等 | 2小时 |

---

## 五、架构评价

### 优点

1. **分层清晰**: 6层架构设计合理，职责分明
2. **策略可插拔**: 策略模块零耦合，易于扩展
3. **防御式设计**: 重试机制、冷却期、降级方案完备
4. **轻量级**: 无重型中间件依赖，适合个人服务器部署
5. **文档完善**: 需求文档、API注册表、进度追踪齐全

### 待改进

1. **测试覆盖**: 需要补充单元测试
2. **错误处理**: 部分异常处理不够细致
3. **监控告警**: 缺少数据源异常的主动告警机制

---

## 六、总结

本项目整体架构设计良好，代码规范清晰，但存在 **3个严重问题需要立即修复**（通知功能未实现、舆情爬虫无法工作、冷却期状态丢失）。修复这些问题后，系统即可正常运行。

建议按照优先级顺序进行修复，预计完成所有 P0 和 P1 问题修复仅需 **约 2 小时**。

---

*报告生成时间: 2026-03-13*
