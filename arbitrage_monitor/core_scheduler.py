"""
套利监控系统核心调度器
L2: 调度与并发层 + L6: 运维与监控层
"""

import os
import signal
import sys
import threading
import time as time_module
from datetime import datetime
from typing import Callable, Dict, Optional

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler

from config.settings import settings
from fetchers.ak_convertible import convertible_fetcher
from fetchers.ak_futures import futures_fetcher
from fetchers.ak_metals import metals_fetcher
from fetchers.futures_margin import futures_margin_fetcher
from fetchers.premium_fetcher import premium_fetcher
from fetchers.sentiment_spider import sentiment_fetcher
from models.signals import Signal
from strategies.cb_strategy import ConvertibleStrategy
from strategies.futures_strategy import FuturesDiscountStrategy
from strategies.metals_strategy import MetalsArbitrageStrategy
from strategies.premium_strategy import PremiumArbitrageStrategy
from strategies.sentiment_strategy import SentimentStrategy
from utils.db_manager import DBManager
from utils.logger import configure_logger, logger
from utils.notifier import notifier
from utils.trading_session import is_day_session_active, is_night_session_active


configure_logger()

scheduler = BlockingScheduler(
    executors={"default": ThreadPoolExecutor(max_workers=settings.THREAD_POOL_SIZE)},
    job_defaults={"misfire_grace_time": 30, "coalesce": True},
)

cooldown_cache: Dict[str, datetime] = {}
db_manager = DBManager()
job_locks: Dict[str, threading.Lock] = {}

MODULE_RUNTIME_CONFIG = {
    "futures": {
        "enabled_field": "ENABLE_FUTURES_MONITOR",
        "cruise_enabled_field": "ENABLE_FUTURES_CRUISE",
        "watch_enabled_field": "ENABLE_FUTURES_WATCH",
        "cruise_field": "FUTURES_CRUISE_INTERVAL_MINUTES",
        "watch_field": "FUTURES_WATCH_INTERVAL_SECONDS",
        "job_ids": {
            "cruise": "futures_cruise_mode",
            "watch": "futures_watch_mode",
        },
        "prefix": "FUTURES",
    },
    "convertible": {
        "enabled_field": "ENABLE_CONVERTIBLE_MONITOR",
        "cruise_enabled_field": "ENABLE_CONVERTIBLE_CRUISE",
        "watch_enabled_field": "ENABLE_CONVERTIBLE_WATCH",
        "cruise_field": "CONVERTIBLE_CRUISE_INTERVAL_MINUTES",
        "watch_field": "CONVERTIBLE_WATCH_INTERVAL_SECONDS",
        "job_ids": {
            "cruise": "convertible_cruise_mode",
            "watch": "convertible_watch_mode",
        },
        "prefix": "CONVERTIBLE",
    },
    "sentiment": {
        "enabled_field": "ENABLE_SENTIMENT_MONITOR",
        "cruise_enabled_field": "ENABLE_SENTIMENT_CRUISE",
        "watch_enabled_field": None,
        "cruise_field": "SENTIMENT_CRUISE_INTERVAL_MINUTES",
        "watch_field": None,
        "job_ids": {
            "cruise": "sentiment_low_freq_mode",
        },
        "prefix": "SENTIMENT",
    },
    "metals": {
        "enabled_field": "ENABLE_METALS_MONITOR",
        "cruise_enabled_field": "ENABLE_METALS_CRUISE",
        "watch_enabled_field": "ENABLE_METALS_WATCH",
        "cruise_field": "METALS_CRUISE_INTERVAL_MINUTES",
        "watch_field": "METALS_WATCH_INTERVAL_SECONDS",
        "job_ids": {
            "cruise": "metals_cruise_mode",
            "watch": "metals_watch_mode",
        },
        "prefix": "METALS",
    },
    "premium": {
        "enabled_field": "ENABLE_PREMIUM_MONITOR",
        "cruise_enabled_field": "ENABLE_PREMIUM_CRUISE",
        "watch_enabled_field": "ENABLE_PREMIUM_WATCH",
        "cruise_field": "PREMIUM_CRUISE_INTERVAL_MINUTES",
        "watch_field": "PREMIUM_WATCH_INTERVAL_SECONDS",
        "job_ids": {
            "cruise": "premium_cruise_mode",
            "watch": "premium_watch_mode",
        },
        "prefix": "PREMIUM",
    },
}

_scheduler_runtime_state = {
    name: {
        "cruise_interval": getattr(settings, cfg["cruise_field"]),
        "watch_interval": (
            getattr(settings, cfg["watch_field"]) if cfg["watch_field"] else None
        ),
        "cruise_enabled": getattr(settings, cfg["cruise_enabled_field"]),
        "watch_enabled": (
            getattr(settings, cfg["watch_enabled_field"])
            if cfg["watch_enabled_field"]
            else None
        ),
    }
    for name, cfg in MODULE_RUNTIME_CONFIG.items()
}

MODULE_TASK_CONFIG = {
    "futures_cruise": {
        "job_name": "futures_cruise_mode",
        "prefix": "FUTURES",
        "strategy_name": "Futures_Discount_Arbitrage",
        "mode": "cruise",
        "session_required": False,
        "watch_preferred": True,
        "watch_skip_log": "futures_cruise_skipped_watch_preferred",
        "fetcher": futures_fetcher,
        "strategy_factory": FuturesDiscountStrategy,
    },
    "convertible_cruise": {
        "job_name": "convertible_cruise_mode",
        "prefix": "CONVERTIBLE",
        "strategy_name": "Convertible_Arbitrage",
        "mode": "cruise",
        "session_required": False,
        "watch_preferred": True,
        "watch_skip_log": "convertible_cruise_skipped_watch_preferred",
        "fetcher": convertible_fetcher,
        "strategy_factory": ConvertibleStrategy,
    },
    "sentiment_cruise": {
        "job_name": "sentiment_low_freq_mode",
        "prefix": "SENTIMENT",
        "strategy_name": "Sentiment_Heat_and_Risk",
        "mode": "cruise",
        "session_required": True,
        "watch_preferred": False,
        "session_skip_log": "sentiment_low_freq_skipped_outside_window",
        "fetcher": sentiment_fetcher,
        "strategy_factory": SentimentStrategy,
    },
    "metals_cruise": {
        "job_name": "metals_cruise_mode",
        "prefix": "METALS",
        "strategy_name": "Metals_Arbitrage",
        "mode": "cruise",
        "session_required": False,
        "watch_preferred": True,
        "watch_skip_log": "metals_cruise_skipped_watch_preferred",
        "fetcher": metals_fetcher,
        "strategy_factory": MetalsArbitrageStrategy,
    },
    "futures_watch": {
        "job_name": "futures_watch_mode",
        "prefix": "FUTURES",
        "strategy_name": "Futures_Discount_Arbitrage",
        "mode": "watch",
        "session_required": True,
        "watch_preferred": False,
        "session_skip_log": "futures_watch_skipped_non_trading_hours",
        "fetcher": futures_fetcher,
        "strategy_factory": FuturesDiscountStrategy,
    },
    "convertible_watch": {
        "job_name": "convertible_watch_mode",
        "prefix": "CONVERTIBLE",
        "strategy_name": "Convertible_Arbitrage",
        "mode": "watch",
        "session_required": True,
        "watch_preferred": False,
        "session_skip_log": "convertible_watch_skipped_non_trading_hours",
        "fetcher": convertible_fetcher,
        "strategy_factory": ConvertibleStrategy,
    },
    "metals_watch": {
        "job_name": "metals_watch_mode",
        "prefix": "METALS",
        "strategy_name": "Metals_Arbitrage",
        "mode": "watch",
        "session_required": True,
        "watch_preferred": False,
        "session_skip_log": "metals_watch_skipped_non_trading_hours",
        "fetcher": metals_fetcher,
        "strategy_factory": MetalsArbitrageStrategy,
    },
    "premium_cruise": {
        "job_name": "premium_cruise_mode",
        "prefix": "PREMIUM",
        "strategy_name": "Premium_Arbitrage",
        "mode": "cruise",
        "session_required": False,
        "watch_preferred": True,
        "watch_skip_log": "premium_cruise_skipped_watch_preferred",
        "fetcher": premium_fetcher,
        "strategy_factory": PremiumArbitrageStrategy,
    },
    "premium_watch": {
        "job_name": "premium_watch_mode",
        "prefix": "PREMIUM",
        "strategy_name": "Premium_Arbitrage",
        "mode": "watch",
        "session_required": True,
        "watch_preferred": False,
        "session_skip_log": "premium_watch_skipped_non_trading_hours",
        "fetcher": premium_fetcher,
        "strategy_factory": PremiumArbitrageStrategy,
    },
}


def restore_cooldown_from_db():
    """启动时从数据库恢复冷却期状态，防止重启后报警轰炸。"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT strategy_key, last_alert FROM cooldown_state")
            for row in cursor.fetchall():
                key, last_alert_str = row
                cooldown_cache[key] = datetime.fromisoformat(last_alert_str)
        logger.info("cooldown_restored_from_db", count=len(cooldown_cache))
    except Exception as exc:
        logger.warning("cooldown_restore_failed", error=str(exc))


def is_module_watch_hours(prefix: str, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    return (
        is_day_session_active(
            getattr(settings, f"{prefix}_MORNING_START"),
            getattr(settings, f"{prefix}_MORNING_END"),
            now,
        )
        or is_day_session_active(
            getattr(settings, f"{prefix}_AFTERNOON_START"),
            getattr(settings, f"{prefix}_AFTERNOON_END"),
            now,
        )
        or is_night_session_active(
            getattr(settings, f"{prefix}_NIGHT_START"),
            getattr(settings, f"{prefix}_NIGHT_END"),
            now,
        )
    )


def is_trading_hours() -> bool:
    """兼容旧测试与旧调用，默认指代期指/A 股交易窗口。"""
    return is_module_watch_hours("FUTURES")


def is_module_mode_enabled(prefix: str, mode: str) -> bool:
    if mode not in {"cruise", "watch"}:
        raise ValueError(f"unsupported mode: {mode}")
    field = f"ENABLE_{prefix}_{mode.upper()}"
    return bool(getattr(settings, field, False))


def get_cooldown_key(signal) -> str:
    return f"{signal.strategy_name}:{signal.asset}"


def is_in_cooldown(signal) -> bool:
    key = get_cooldown_key(signal)
    if key not in cooldown_cache:
        return False

    last_alert = cooldown_cache[key]
    elapsed = (datetime.now() - last_alert).total_seconds() / 60
    if elapsed < settings.COOLDOWN_MINUTES:
        logger.debug("signal_in_cooldown", key=key, elapsed_minutes=elapsed)
        return True
    return False


def update_cooldown(signal):
    key = get_cooldown_key(signal)
    cooldown_cache[key] = datetime.now()
    db_manager.save_cooldown_state(key, signal.timestamp.isoformat())


def save_signal_to_db(signal):
    signal.alert_id = db_manager.save_signal(signal)


def persist_runtime_data(strategy_name: str, data) -> None:
    try:
        if strategy_name == "Futures_Discount_Arbitrage":
            db_manager.save_futures_live_snapshots(data)
        elif strategy_name == "Convertible_Arbitrage":
            db_manager.save_convertible_snapshots(data)
        elif strategy_name == "Sentiment_Heat_and_Risk":
            db_manager.save_sentiment_snapshots(data)
        elif strategy_name == "Metals_Arbitrage":
            db_manager.save_metal_snapshots(data)
        elif strategy_name == "Premium_Arbitrage":
            db_manager.save_premium_snapshots(data)
    except Exception as exc:
        logger.warning(
            "runtime_snapshot_persist_failed",
            strategy=strategy_name,
            error=str(exc),
        )


def _log_strategy_disabled(strategy_name: str) -> dict[str, str]:
    logger.info("strategy_disabled", strategy=strategy_name)
    return {"status": "DISABLED"}


def run_module_task(task_key: str):
    config = MODULE_TASK_CONFIG[task_key]
    prefix = config["prefix"]
    mode = str(config["mode"])
    strategy_name = str(config["strategy_name"])
    fetcher = config["fetcher"]
    strategy_factory: Callable[[], object] = config["strategy_factory"]

    def _runner():
        sync_runtime_settings()
        if not getattr(settings, f"ENABLE_{prefix}_MONITOR"):
            return _log_strategy_disabled(strategy_name)
        if mode == "cruise" and not getattr(settings, f"ENABLE_{prefix}_CRUISE"):
            return {"status": "DISABLED_MODE"}
        if mode == "watch" and not getattr(settings, f"ENABLE_{prefix}_WATCH"):
            return {"status": "DISABLED_MODE"}
        if config["session_required"] and not is_module_watch_hours(prefix):
            logger.debug(config.get("session_skip_log", f"{prefix.lower()}_{mode}_skipped_non_trading_hours"))
            return {"status": "SKIPPED_WINDOW"}
        if config["watch_preferred"] and is_module_watch_hours(prefix) and getattr(
            settings, f"ENABLE_{prefix}_WATCH", False
        ):
            logger.debug(config.get("watch_skip_log", f"{prefix.lower()}_{mode}_skipped_watch_preferred"))
            return {"status": "SKIPPED_WINDOW"}
        return run_strategy_task(fetcher, strategy_factory(), strategy_name)

    return execute_job(str(config["job_name"]), _runner)


def run_strategy_task(fetcher, strategy, strategy_name: str):
    """通用策略执行入口。"""
    try:
        logger.info("strategy_task_start", strategy=strategy_name)
        data = fetcher.fetch_live()
        if not data:
            logger.warning("strategy_no_data", strategy=strategy_name)
            return {"status": "NO_DATA", "signals_count": 0}

        persist_runtime_data(strategy_name, data)
        signals = strategy.evaluate(data)

        for signal in signals:
            if is_in_cooldown(signal):
                logger.debug(
                    "signal_skipped_cooldown",
                    strategy=signal.strategy_name,
                    asset=signal.asset,
                )
                continue

            logger.info(
                "signal_triggered",
                strategy=signal.strategy_name,
                level=signal.level,
                asset=signal.asset,
            )
            save_signal_to_db(signal)
            update_cooldown(signal)
            notifier.send(signal)

        logger.info(
            "strategy_task_completed",
            strategy=strategy_name,
            signals_count=len(signals),
        )
        return {"status": "SUCCESS", "signals_count": len(signals)}
    except Exception as exc:
        logger.error(
            "strategy_task_failed", strategy=strategy_name, error=str(exc), exc_info=True
        )
        return {"status": "FAILED", "signals_count": 0, "error": str(exc)}


def _get_job_lock(job_name: str) -> threading.Lock:
    if job_name not in job_locks:
        job_locks[job_name] = threading.Lock()
    return job_locks[job_name]


def execute_job(job_name: str, runner):
    lock = _get_job_lock(job_name)
    if not lock.acquire(blocking=False):
        db_manager.mark_job_skipped(job_name, reason="OVERLAP")
        logger.warning("job_skipped_overlap", job=job_name)
        return None

    started_at = datetime.now()
    started_perf = time_module.perf_counter()
    db_manager.mark_job_started(job_name, started_at.isoformat())

    status = "SUCCESS"
    error_summary = ""
    try:
        result = runner()
        if isinstance(result, dict):
            status = str(result.get("status", "SUCCESS"))
            error_summary = str(result.get("error", "") or "")
        return result
    except Exception as exc:
        status = "FAILED"
        error_summary = str(exc)
        logger.error("job_execution_failed", job=job_name, error=error_summary, exc_info=True)
        return {"status": status, "error": error_summary}
    finally:
        duration_ms = (time_module.perf_counter() - started_perf) * 1000
        db_manager.mark_job_finished(
            job_name,
            finished_at=datetime.now().isoformat(),
            status=status,
            duration_ms=duration_ms,
            error_summary=error_summary,
        )
        lock.release()


def _reschedule_runtime_jobs_if_needed():
    for module_name, config in MODULE_RUNTIME_CONFIG.items():
        cruise_interval = getattr(settings, config["cruise_field"])
        state = _scheduler_runtime_state[module_name]
        cruise_enabled = getattr(settings, config["cruise_enabled_field"])
        if state["cruise_interval"] != cruise_interval:
            scheduler.reschedule_job(
                config["job_ids"]["cruise"], trigger="interval", minutes=cruise_interval
            )
            state["cruise_interval"] = cruise_interval
            logger.info(
                "scheduler_cruise_interval_reloaded",
                module=module_name,
                cruise_interval=cruise_interval,
            )
        if state["cruise_enabled"] != cruise_enabled:
            state["cruise_enabled"] = cruise_enabled
            logger.info(
                "scheduler_cruise_mode_reloaded",
                module=module_name,
                cruise_enabled=cruise_enabled,
            )

        watch_field = config["watch_field"]
        watch_job_id = config["job_ids"].get("watch")
        if watch_field and watch_job_id:
            watch_interval = getattr(settings, watch_field)
            watch_enabled = getattr(settings, config["watch_enabled_field"])
            if state["watch_interval"] != watch_interval:
                scheduler.reschedule_job(
                    watch_job_id, trigger="interval", seconds=watch_interval
                )
                state["watch_interval"] = watch_interval
                logger.info(
                    "scheduler_watch_interval_reloaded",
                    module=module_name,
                    watch_interval=watch_interval,
                )
            if state["watch_enabled"] != watch_enabled:
                state["watch_enabled"] = watch_enabled
                logger.info(
                    "scheduler_watch_mode_reloaded",
                    module=module_name,
                    watch_enabled=watch_enabled,
                )


def sync_runtime_settings():
    previous = {
        module_name: {
            "enabled": getattr(settings, cfg["enabled_field"]),
            "cruise_enabled": getattr(settings, cfg["cruise_enabled_field"]),
            "watch_enabled": (
                getattr(settings, cfg["watch_enabled_field"])
                if cfg["watch_enabled_field"]
                else None
            ),
            "cruise_interval": getattr(settings, cfg["cruise_field"]),
            "watch_interval": (
                getattr(settings, cfg["watch_field"]) if cfg["watch_field"] else None
            ),
        }
        for module_name, cfg in MODULE_RUNTIME_CONFIG.items()
    }
    previous["cooldown_minutes"] = settings.COOLDOWN_MINUTES
    previous["data_retention_days"] = settings.DATA_RETENTION_DAYS

    settings.reload_from_env()
    _reschedule_runtime_jobs_if_needed()

    current = {
        module_name: {
            "enabled": getattr(settings, cfg["enabled_field"]),
            "cruise_enabled": getattr(settings, cfg["cruise_enabled_field"]),
            "watch_enabled": (
                getattr(settings, cfg["watch_enabled_field"])
                if cfg["watch_enabled_field"]
                else None
            ),
            "cruise_interval": getattr(settings, cfg["cruise_field"]),
            "watch_interval": (
                getattr(settings, cfg["watch_field"]) if cfg["watch_field"] else None
            ),
        }
        for module_name, cfg in MODULE_RUNTIME_CONFIG.items()
    }
    current["cooldown_minutes"] = settings.COOLDOWN_MINUTES
    current["data_retention_days"] = settings.DATA_RETENTION_DAYS

    if current != previous:
        logger.info("runtime_settings_reloaded", **current)


def refresh_futures_margin_snapshot():
    try:
        logger.info("futures_margin_refresh_start")
        snapshots = futures_margin_fetcher.fetch_live()
        logger.info("futures_margin_refresh_completed", count=len(snapshots))
        return {"status": "SUCCESS", "count": len(snapshots)}
    except Exception as exc:
        logger.error("futures_margin_refresh_failed", error=str(exc), exc_info=True)
        return {"status": "FAILED", "error": str(exc)}


def ensure_futures_margin_baseline():
    try:
        latest = db_manager.get_latest_futures_margins()
        if latest:
            logger.info("futures_margin_baseline_exists", count=len(latest))
            return
        refresh_futures_margin_snapshot()
    except Exception as exc:
        logger.warning("futures_margin_baseline_check_failed", error=str(exc))


def run_futures_cruise_mode():
    return run_module_task("futures_cruise")


def run_convertible_cruise_mode():
    return run_module_task("convertible_cruise")


def run_sentiment_low_freq_mode():
    return run_module_task("sentiment_cruise")


def run_metals_cruise_mode():
    return run_module_task("metals_cruise")


def run_futures_watch_mode():
    return run_module_task("futures_watch")


def run_convertible_watch_mode():
    return run_module_task("convertible_watch")


def run_metals_watch_mode():
    return run_module_task("metals_watch")


def run_premium_cruise_mode():
    return run_module_task("premium_cruise")


def run_premium_watch_mode():
    return run_module_task("premium_watch")


def send_heartbeat():
    try:
        logger.info("heartbeat_start")
        with db_manager.get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM alert_history WHERE date(timestamp) = date('now','localtime')"
            )
            today_alerts = cursor.fetchone()[0]
            cursor = conn.execute("SELECT COUNT(*) FROM alert_history")
            total_alerts = cursor.fetchone()[0]

        db_size = os.path.getsize(db_manager.db_path) if os.path.exists(db_manager.db_path) else 0
        heartbeat_msg = (
            f"🟢 套利监控引擎运行正常\n"
            f"📊 今日报警：{today_alerts} 次\n"
            f"📈 累计报警：{total_alerts} 次\n"
            f"💾 数据库大小：{db_size / 1024:.1f} KB\n"
            f"⏰ 报告时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        notifier.send(
            Signal(
                asset="SYSTEM",
                strategy_name="Heartbeat",
                level="INFO",
                message=heartbeat_msg,
            )
        )
        logger.info(
            "heartbeat_completed", today_alerts=today_alerts, total_alerts=total_alerts
        )
        return {"status": "SUCCESS"}
    except Exception as exc:
        logger.error("heartbeat_failed", error=str(exc), exc_info=True)
        return {"status": "FAILED", "error": str(exc)}


def cleanup_old_runtime_data():
    try:
        retention_days = settings.DATA_RETENTION_DAYS
        logger.info("retention_cleanup_start", retention_days=retention_days)
        alert_rows = db_manager.purge_alert_history_older_than(retention_days)
        margin_rows = db_manager.purge_futures_margin_snapshots_older_than(retention_days)
        futures_rows = db_manager.purge_futures_live_snapshots_older_than(retention_days)
        convertible_rows = db_manager.purge_convertible_snapshots_older_than(retention_days)
        sentiment_rows = db_manager.purge_sentiment_snapshots_older_than(retention_days)
        metals_rows = db_manager.purge_metal_snapshots_older_than(retention_days)
        premium_rows = db_manager.purge_premium_snapshots_older_than(retention_days)
        logger.info(
            "retention_cleanup_completed",
            retention_days=retention_days,
            deleted_alert_rows=alert_rows,
            deleted_margin_rows=margin_rows,
            deleted_futures_snapshot_rows=futures_rows,
            deleted_convertible_snapshot_rows=convertible_rows,
            deleted_sentiment_snapshot_rows=sentiment_rows,
            deleted_metal_snapshot_rows=metals_rows,
            deleted_premium_snapshot_rows=premium_rows,
        )
        return {"status": "SUCCESS"}
    except Exception as exc:
        logger.error("retention_cleanup_failed", error=str(exc), exc_info=True)
        return {"status": "FAILED", "error": str(exc)}


def run_futures_margin_refresh_job():
    return execute_job("futures_margin_refresh", refresh_futures_margin_snapshot)


def run_daily_heartbeat_job():
    return execute_job("daily_heartbeat", send_heartbeat)


def run_retention_cleanup_job():
    return execute_job("retention_cleanup", cleanup_old_runtime_data)


def run_runtime_settings_sync_job():
    return execute_job("runtime_settings_sync", lambda: (sync_runtime_settings() or {"status": "SUCCESS"}))


def setup_signal_handlers():
    def signal_handler(signum, frame):
        logger.info("shutdown_signal_received", signal=signum)
        logger.info("shutting_down_gracefully")
        scheduler.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def schedule_jobs():
    for module_name, config in MODULE_RUNTIME_CONFIG.items():
        _scheduler_runtime_state[module_name]["cruise_interval"] = getattr(
            settings, config["cruise_field"]
        )
        if config["watch_field"]:
            _scheduler_runtime_state[module_name]["watch_interval"] = getattr(
                settings, config["watch_field"]
            )

    scheduler.add_job(
        run_futures_cruise_mode,
        "interval",
        minutes=settings.FUTURES_CRUISE_INTERVAL_MINUTES,
        id="futures_cruise_mode",
        name="Futures Cruise Mode Scan",
    )
    scheduler.add_job(
        run_convertible_cruise_mode,
        "interval",
        minutes=settings.CONVERTIBLE_CRUISE_INTERVAL_MINUTES,
        id="convertible_cruise_mode",
        name="Convertible Cruise Mode Scan",
    )
    scheduler.add_job(
        run_futures_watch_mode,
        "interval",
        seconds=settings.FUTURES_WATCH_INTERVAL_SECONDS,
        id="futures_watch_mode",
        name="Futures Watch Mode Scan",
        misfire_grace_time=30,
    )
    scheduler.add_job(
        run_convertible_watch_mode,
        "interval",
        seconds=settings.CONVERTIBLE_WATCH_INTERVAL_SECONDS,
        id="convertible_watch_mode",
        name="Convertible Watch Mode Scan",
        misfire_grace_time=30,
    )
    scheduler.add_job(
        run_sentiment_low_freq_mode,
        "interval",
        minutes=settings.SENTIMENT_CRUISE_INTERVAL_MINUTES,
        id="sentiment_low_freq_mode",
        name="Sentiment Low Frequency Scan",
        misfire_grace_time=60,
    )
    scheduler.add_job(
        run_metals_cruise_mode,
        "interval",
        minutes=settings.METALS_CRUISE_INTERVAL_MINUTES,
        id="metals_cruise_mode",
        name="Metals Cruise Mode Scan",
    )
    scheduler.add_job(
        run_metals_watch_mode,
        "interval",
        seconds=settings.METALS_WATCH_INTERVAL_SECONDS,
        id="metals_watch_mode",
        name="Metals Watch Mode Scan",
        misfire_grace_time=30,
    )
    scheduler.add_job(
        run_premium_cruise_mode,
        "interval",
        minutes=settings.PREMIUM_CRUISE_INTERVAL_MINUTES,
        id="premium_cruise_mode",
        name="Premium Cruise Mode Scan",
    )
    scheduler.add_job(
        run_premium_watch_mode,
        "interval",
        seconds=settings.PREMIUM_WATCH_INTERVAL_SECONDS,
        id="premium_watch_mode",
        name="Premium Watch Mode Scan",
        misfire_grace_time=30,
    )
    scheduler.add_job(
        run_daily_heartbeat_job,
        "cron",
        hour=9,
        minute=25,
        id="daily_heartbeat",
        name="Daily Heartbeat Report",
    )
    scheduler.add_job(
        run_futures_margin_refresh_job,
        "cron",
        hour=9,
        minute=0,
        id="futures_margin_open_refresh",
        name="Futures Margin Refresh Before Open",
    )
    scheduler.add_job(
        run_futures_margin_refresh_job,
        "cron",
        hour=0,
        minute=0,
        id="futures_margin_midnight_refresh",
        name="Futures Margin Refresh At Midnight",
    )
    scheduler.add_job(
        run_retention_cleanup_job,
        "cron",
        hour=0,
        minute=10,
        id="retention_cleanup",
        name="Retention Cleanup",
    )
    scheduler.add_job(
        run_runtime_settings_sync_job,
        "interval",
        seconds=15,
        id="runtime_settings_sync",
        name="Runtime Settings Sync",
        coalesce=True,
        misfire_grace_time=15,
    )
    logger.info("scheduler_jobs_registered")


def main():
    logger.info("scheduler_starting")
    restore_cooldown_from_db()
    ensure_futures_margin_baseline()
    setup_signal_handlers()
    schedule_jobs()
    logger.info(
        "scheduler_started",
        futures_cruise_interval=settings.FUTURES_CRUISE_INTERVAL_MINUTES,
        futures_watch_interval=settings.FUTURES_WATCH_INTERVAL_SECONDS,
        convertible_cruise_interval=settings.CONVERTIBLE_CRUISE_INTERVAL_MINUTES,
        convertible_watch_interval=settings.CONVERTIBLE_WATCH_INTERVAL_SECONDS,
        sentiment_interval=settings.SENTIMENT_CRUISE_INTERVAL_MINUTES,
        metals_cruise_interval=settings.METALS_CRUISE_INTERVAL_MINUTES,
        metals_watch_interval=settings.METALS_WATCH_INTERVAL_SECONDS,
        premium_cruise_interval=settings.PREMIUM_CRUISE_INTERVAL_MINUTES,
        premium_watch_interval=settings.PREMIUM_WATCH_INTERVAL_SECONDS,
        thread_pool_size=settings.THREAD_POOL_SIZE,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler_stopped")


if __name__ == "__main__":
    main()
