"""
端到端集成测试脚本
验证调度器、策略、通知、数据库的完整链路
"""

import json
import sys
import os
import io
import tempfile
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from utils.logger import configure_logger
from utils.db_manager import DBManager
from utils.notifier import notifier

configure_logger()

from utils.logger import logger

def test_premium_module_integration():
    """测试 premium 模块调度独立运行。"""
    logger.info("test_premium_module_integration_start")

    import core_scheduler as cs
    from config.settings import settings

    original_run_strategy_task = cs.run_strategy_task
    original_sync_runtime_settings = cs.sync_runtime_settings
    original_is_module_watch_hours = cs.is_module_watch_hours
    original = {
        "ENABLE_PREMIUM_MONITOR": settings.ENABLE_PREMIUM_MONITOR,
        "ENABLE_PREMIUM_CRUISE": settings.ENABLE_PREMIUM_CRUISE,
        "ENABLE_PREMIUM_WATCH": settings.ENABLE_PREMIUM_WATCH,
    }
    executed: list[str] = []

    def fake_run_strategy_task(fetcher, strategy, strategy_name: str):
        executed.append(strategy_name)
        return {"status": "SUCCESS"}

    try:
        cs.run_strategy_task = fake_run_strategy_task
        cs.sync_runtime_settings = lambda: None
        cs.is_module_watch_hours = lambda prefix, now=None: prefix == "PREMIUM"
        settings.apply_updates(
            {
                "ENABLE_PREMIUM_MONITOR": True,
                "ENABLE_PREMIUM_CRUISE": True,
                "ENABLE_PREMIUM_WATCH": False,
            }
        )
        cs.run_premium_cruise_mode()
        cs.run_premium_watch_mode()
    finally:
        settings.apply_updates(original)
        cs.run_strategy_task = original_run_strategy_task
        cs.sync_runtime_settings = original_sync_runtime_settings
        cs.is_module_watch_hours = original_is_module_watch_hours

    if executed != ["Premium_Arbitrage"]:
        print(f"❌ Premium Module Integration: unexpected executed strategies {executed}")
        return False

    logger.info("premium_module_integration_ok", executed=executed)
    print("✅ Premium Module Integration: OK")
    return True

