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

def test_scheduler_runtime_settings_sync():
    """测试调度频率调整后 job trigger 会重建。"""
    logger.info("test_scheduler_runtime_settings_sync_start")

    from pathlib import Path
    import core_scheduler as cs
    import config.settings as settings_module
    from config.settings import settings

    original = {
        "FUTURES_CRUISE_INTERVAL_MINUTES": settings.FUTURES_CRUISE_INTERVAL_MINUTES,
        "FUTURES_WATCH_INTERVAL_SECONDS": settings.FUTURES_WATCH_INTERVAL_SECONDS,
        "CONVERTIBLE_CRUISE_INTERVAL_MINUTES": settings.CONVERTIBLE_CRUISE_INTERVAL_MINUTES,
        "CONVERTIBLE_WATCH_INTERVAL_SECONDS": settings.CONVERTIBLE_WATCH_INTERVAL_SECONDS,
        "SENTIMENT_CRUISE_INTERVAL_MINUTES": settings.SENTIMENT_CRUISE_INTERVAL_MINUTES,
        "METALS_CRUISE_INTERVAL_MINUTES": settings.METALS_CRUISE_INTERVAL_MINUTES,
        "METALS_WATCH_INTERVAL_SECONDS": settings.METALS_WATCH_INTERVAL_SECONDS,
        "DATA_RETENTION_DAYS": settings.DATA_RETENTION_DAYS,
    }
    original_path = settings_module.SHARED_RUNTIME_CONFIG_PATH
    original_local_path = settings_module.LOCAL_RUNTIME_CONFIG_PATH

    with tempfile.TemporaryDirectory() as temp_dir:
        shared_path = Path(temp_dir) / "runtime_settings.json"
        local_path = Path(temp_dir) / "runtime_settings.local.json"
        shared_path.write_text(
            json.dumps(
                {
                    "CRUISE_INTERVAL_MINUTES": 5,
                    "WATCH_INTERVAL_SECONDS": 30,
                    "SENTIMENT_INTERVAL_MINUTES": 3,
                    "THREAD_POOL_SIZE": 20,
                    "REQUEST_TIMEOUT": 15,
                    "RETRY_MAX_ATTEMPTS": 3,
                    "COOLDOWN_MINUTES": 30,
                    "DATA_RETENTION_DAYS": 20,
                    "ENABLE_FUTURES_MONITOR": True,
                    "ENABLE_CONVERTIBLE_MONITOR": True,
                    "ENABLE_SENTIMENT_MONITOR": True,
                    "ENABLE_METALS_MONITOR": True,
                    "MORNING_START": "09:30",
                    "MORNING_END": "11:30",
                    "AFTERNOON_START": "13:00",
                    "AFTERNOON_END": "15:00",
                    "FUTURES_CRUISE_INTERVAL_MINUTES": 7,
                    "FUTURES_WATCH_INTERVAL_SECONDS": 45,
                    "FUTURES_MORNING_START": "09:30",
                    "FUTURES_MORNING_END": "11:30",
                    "FUTURES_AFTERNOON_START": "13:00",
                    "FUTURES_AFTERNOON_END": "15:00",
                    "FUTURES_NIGHT_START": "",
                    "FUTURES_NIGHT_END": "",
                    "CONVERTIBLE_CRUISE_INTERVAL_MINUTES": 8,
                    "CONVERTIBLE_WATCH_INTERVAL_SECONDS": 50,
                    "CONVERTIBLE_MORNING_START": "09:30",
                    "CONVERTIBLE_MORNING_END": "11:30",
                    "CONVERTIBLE_AFTERNOON_START": "13:00",
                    "CONVERTIBLE_AFTERNOON_END": "15:00",
                    "CONVERTIBLE_NIGHT_START": "",
                    "CONVERTIBLE_NIGHT_END": "",
                    "SENTIMENT_CRUISE_INTERVAL_MINUTES": 4,
                    "SENTIMENT_MORNING_START": "09:00",
                    "SENTIMENT_MORNING_END": "11:30",
                    "SENTIMENT_AFTERNOON_START": "13:00",
                    "SENTIMENT_AFTERNOON_END": "15:30",
                    "SENTIMENT_NIGHT_START": "",
                    "SENTIMENT_NIGHT_END": "",
                    "METALS_CRUISE_INTERVAL_MINUTES": 11,
                    "METALS_WATCH_INTERVAL_SECONDS": 75,
                    "METALS_MORNING_START": "09:00",
                    "METALS_MORNING_END": "11:30",
                    "METALS_AFTERNOON_START": "13:30",
                    "METALS_AFTERNOON_END": "15:00",
                    "METALS_NIGHT_START": "21:00",
                    "METALS_NIGHT_END": "02:30",
                    "CB_NEGATIVE_PREMIUM_THRESHOLD": 0.0,
                    "CB_DOUBLE_LOW_THRESHOLD": 130.0,
                    "CB_YTM_THRESHOLD": 2.0,
                    "CB_SAFE_PRICE_THRESHOLD": 130.0,
                    "FUTURES_DISCOUNT_PERCENT_THRESHOLD": 1.0,
                    "FUTURES_DISCOUNT_RATE_THRESHOLD": 8.0,
                    "SENTIMENT_HOT_SCORE_THRESHOLD": 5000000,
                    "SENTIMENT_PULSE_THRESHOLD": -0.8,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        try:
            settings_module.SHARED_RUNTIME_CONFIG_PATH = shared_path
            settings_module.LOCAL_RUNTIME_CONFIG_PATH = local_path
            settings.reload_from_env()
            cs.scheduler.remove_all_jobs()
            cs.schedule_jobs()

            futures_cruise_job = cs.scheduler.get_job("futures_cruise_mode")
            convertible_cruise_job = cs.scheduler.get_job("convertible_cruise_mode")
            futures_watch_job = cs.scheduler.get_job("futures_watch_mode")
            convertible_watch_job = cs.scheduler.get_job("convertible_watch_mode")
            sentiment_job = cs.scheduler.get_job("sentiment_low_freq_mode")
            metals_cruise_job = cs.scheduler.get_job("metals_cruise_mode")
            metals_watch_job = cs.scheduler.get_job("metals_watch_mode")
            if int(futures_cruise_job.trigger.interval.total_seconds()) != 420:
                print("❌ Scheduler Sync: initial cruise interval mismatch")
                return False
            if int(convertible_cruise_job.trigger.interval.total_seconds()) != 480:
                print("❌ Scheduler Sync: initial convertible cruise interval mismatch")
                return False
            if int(futures_watch_job.trigger.interval.total_seconds()) != 45:
                print("❌ Scheduler Sync: initial watch interval mismatch")
                return False
            if int(convertible_watch_job.trigger.interval.total_seconds()) != 50:
                print("❌ Scheduler Sync: initial convertible watch interval mismatch")
                return False
            if int(sentiment_job.trigger.interval.total_seconds()) != 240:
                print("❌ Scheduler Sync: initial sentiment interval mismatch")
                return False
            if int(metals_cruise_job.trigger.interval.total_seconds()) != 660:
                print("❌ Scheduler Sync: initial metals cruise interval mismatch")
                return False
            if int(metals_watch_job.trigger.interval.total_seconds()) != 75:
                print("❌ Scheduler Sync: initial metals watch interval mismatch")
                return False

            shared_path.write_text(
                json.dumps(
                    {
                        "CRUISE_INTERVAL_MINUTES": 5,
                        "WATCH_INTERVAL_SECONDS": 30,
                        "SENTIMENT_INTERVAL_MINUTES": 3,
                        "THREAD_POOL_SIZE": 20,
                        "REQUEST_TIMEOUT": 15,
                        "RETRY_MAX_ATTEMPTS": 3,
                        "COOLDOWN_MINUTES": 30,
                        "DATA_RETENTION_DAYS": 15,
                        "ENABLE_FUTURES_MONITOR": True,
                        "ENABLE_CONVERTIBLE_MONITOR": True,
                        "ENABLE_SENTIMENT_MONITOR": True,
                        "ENABLE_METALS_MONITOR": True,
                        "MORNING_START": "09:30",
                        "MORNING_END": "11:30",
                        "AFTERNOON_START": "13:00",
                        "AFTERNOON_END": "15:00",
                        "FUTURES_CRUISE_INTERVAL_MINUTES": 9,
                        "FUTURES_WATCH_INTERVAL_SECONDS": 60,
                        "FUTURES_MORNING_START": "09:30",
                        "FUTURES_MORNING_END": "11:30",
                        "FUTURES_AFTERNOON_START": "13:00",
                        "FUTURES_AFTERNOON_END": "15:00",
                        "FUTURES_NIGHT_START": "",
                        "FUTURES_NIGHT_END": "",
                        "CONVERTIBLE_CRUISE_INTERVAL_MINUTES": 10,
                        "CONVERTIBLE_WATCH_INTERVAL_SECONDS": 65,
                        "CONVERTIBLE_MORNING_START": "09:30",
                        "CONVERTIBLE_MORNING_END": "11:30",
                        "CONVERTIBLE_AFTERNOON_START": "13:00",
                        "CONVERTIBLE_AFTERNOON_END": "15:00",
                        "CONVERTIBLE_NIGHT_START": "",
                        "CONVERTIBLE_NIGHT_END": "",
                        "SENTIMENT_CRUISE_INTERVAL_MINUTES": 6,
                        "SENTIMENT_MORNING_START": "09:00",
                        "SENTIMENT_MORNING_END": "11:30",
                        "SENTIMENT_AFTERNOON_START": "13:00",
                        "SENTIMENT_AFTERNOON_END": "15:30",
                        "SENTIMENT_NIGHT_START": "",
                        "SENTIMENT_NIGHT_END": "",
                        "METALS_CRUISE_INTERVAL_MINUTES": 13,
                        "METALS_WATCH_INTERVAL_SECONDS": 90,
                        "METALS_MORNING_START": "09:00",
                        "METALS_MORNING_END": "11:30",
                        "METALS_AFTERNOON_START": "13:30",
                        "METALS_AFTERNOON_END": "15:00",
                        "METALS_NIGHT_START": "21:00",
                        "METALS_NIGHT_END": "02:30",
                        "CB_NEGATIVE_PREMIUM_THRESHOLD": 0.0,
                        "CB_DOUBLE_LOW_THRESHOLD": 130.0,
                        "CB_YTM_THRESHOLD": 2.0,
                        "CB_SAFE_PRICE_THRESHOLD": 130.0,
                        "FUTURES_DISCOUNT_PERCENT_THRESHOLD": 1.0,
                        "FUTURES_DISCOUNT_RATE_THRESHOLD": 8.0,
                        "SENTIMENT_HOT_SCORE_THRESHOLD": 5000000,
                        "SENTIMENT_PULSE_THRESHOLD": -0.8,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            cs.sync_runtime_settings()

            futures_cruise_job = cs.scheduler.get_job("futures_cruise_mode")
            convertible_cruise_job = cs.scheduler.get_job("convertible_cruise_mode")
            futures_watch_job = cs.scheduler.get_job("futures_watch_mode")
            convertible_watch_job = cs.scheduler.get_job("convertible_watch_mode")
            sentiment_job = cs.scheduler.get_job("sentiment_low_freq_mode")
            metals_cruise_job = cs.scheduler.get_job("metals_cruise_mode")
            metals_watch_job = cs.scheduler.get_job("metals_watch_mode")
            if int(futures_cruise_job.trigger.interval.total_seconds()) != 540:
                print("❌ Scheduler Sync: updated cruise interval mismatch")
                return False
            if int(convertible_cruise_job.trigger.interval.total_seconds()) != 600:
                print("❌ Scheduler Sync: updated convertible cruise interval mismatch")
                return False
            if int(futures_watch_job.trigger.interval.total_seconds()) != 60:
                print("❌ Scheduler Sync: updated watch interval mismatch")
                return False
            if int(convertible_watch_job.trigger.interval.total_seconds()) != 65:
                print("❌ Scheduler Sync: updated convertible watch interval mismatch")
                return False
            if int(sentiment_job.trigger.interval.total_seconds()) != 360:
                print("❌ Scheduler Sync: updated sentiment interval mismatch")
                return False
            if int(metals_cruise_job.trigger.interval.total_seconds()) != 780:
                print("❌ Scheduler Sync: updated metals cruise interval mismatch")
                return False
            if int(metals_watch_job.trigger.interval.total_seconds()) != 90:
                print("❌ Scheduler Sync: updated metals watch interval mismatch")
                return False
            if settings.DATA_RETENTION_DAYS != 15:
                print("❌ Scheduler Sync: retention days not hot reloaded")
                return False
        finally:
            cs.scheduler.remove_all_jobs()
            settings_module.SHARED_RUNTIME_CONFIG_PATH = original_path
            settings_module.LOCAL_RUNTIME_CONFIG_PATH = original_local_path
            settings.reload_from_env()
            settings.apply_updates(original)

    logger.info("scheduler_runtime_settings_sync_ok")
    print("✅ Scheduler Runtime Sync: OK")
    return True

def test_module_schedule_windows():
    """测试模块独立时钟和跨日窗口判断。"""
    logger.info("test_module_schedule_windows_start")

    import core_scheduler as cs

    weekday_day = datetime(2026, 3, 16, 10, 0, 0)
    saturday_night_tail = datetime(2026, 3, 21, 1, 30, 0)
    monday_early = datetime(2026, 3, 16, 1, 30, 0)

    if not cs.is_module_watch_hours("FUTURES", weekday_day):
        print("❌ Module Schedule: futures day session should be active")
        return False
    if not cs.is_module_watch_hours("METALS", saturday_night_tail):
        print("❌ Module Schedule: metals Friday-night tail should be active on Saturday early morning")
        return False
    if cs.is_module_watch_hours("METALS", monday_early):
        print("❌ Module Schedule: metals should be inactive on Monday early morning without Sunday night session")
        return False

    logger.info("module_schedule_windows_ok")
    print("✅ Module Schedule Windows: OK")
    return True

def test_scheduler_imports():
    """测试调度器导入"""
    logger.info("test_scheduler_imports_start")

    try:
        from core_scheduler import (
            ensure_futures_margin_baseline,
            refresh_futures_margin_snapshot,
            cleanup_old_runtime_data,
            is_trading_hours,
            is_module_watch_hours,
            run_futures_cruise_mode,
            run_convertible_cruise_mode,
            run_sentiment_low_freq_mode,
            run_metals_cruise_mode,
            run_futures_watch_mode,
            run_convertible_watch_mode,
            run_metals_watch_mode,
            send_heartbeat,
        )

        logger.info("scheduler_imports_success")
        print("✅ Scheduler Imports: OK")
        return True
    except ImportError as e:
        logger.warning("scheduler_imports_skipped", error=str(e))
        print(f"⚠️ Scheduler Imports: SKIPPED - {e}")
        return "SKIP"

def test_cooldown_restore_roundtrip():
    """测试 cooldown_state 写入后可从数据库恢复到内存缓存。"""
    logger.info("test_cooldown_restore_roundtrip_start")

    import core_scheduler as cs

    db = DBManager()
    strategy_key = f"Cooldown_Test:{datetime.now().isoformat()}"
    last_alert = datetime.now().replace(microsecond=0)

    original_cache = dict(cs.cooldown_cache)
    try:
        db.save_cooldown_state(strategy_key, last_alert.isoformat())
        cs.cooldown_cache.clear()
        cs.restore_cooldown_from_db()
        restored = cs.cooldown_cache.get(strategy_key)
    finally:
        cs.cooldown_cache.clear()
        cs.cooldown_cache.update(original_cache)
        with db.get_connection() as conn:
            conn.execute(
                "DELETE FROM cooldown_state WHERE strategy_key = ?",
                (strategy_key,),
            )
            conn.commit()

    if restored != last_alert:
        print(f"❌ Cooldown Restore: expected {last_alert}, got {restored}")
        return False

    logger.info("cooldown_restore_roundtrip_ok", strategy_key=strategy_key)
    print("✅ Cooldown Restore: OK")
    return True
