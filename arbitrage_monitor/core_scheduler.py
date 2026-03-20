"""
套利监控系统核心调度器
L2: 调度与并发层 + L6: 运维与监控层
"""

import signal
import sys
from datetime import datetime, time
from typing import Dict, Optional

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler

from config.settings import settings
from fetchers.ak_convertible import convertible_fetcher
from fetchers.ak_futures import futures_fetcher
from fetchers.ak_metals import metals_fetcher
from fetchers.futures_margin import futures_margin_fetcher
from fetchers.sentiment_spider import sentiment_fetcher
from strategies.cb_strategy import ConvertibleStrategy
from strategies.futures_strategy import FuturesDiscountStrategy
from strategies.metals_strategy import MetalsArbitrageStrategy
from strategies.sentiment_strategy import SentimentStrategy
from utils.db_manager import DBManager
from utils.logger import configure_logger, logger
from utils.notifier import notifier


configure_logger()

scheduler = BlockingScheduler(
    executors={"default": ThreadPoolExecutor(max_workers=settings.THREAD_POOL_SIZE)},
    job_defaults={"misfire_grace_time": 30, "coalesce": True},
)

cooldown_cache: Dict[str, datetime] = {}
db_manager = DBManager()

MODULE_RUNTIME_CONFIG = {
    "futures": {
        "enabled_field": "ENABLE_FUTURES_MONITOR",
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
        "cruise_field": "SENTIMENT_CRUISE_INTERVAL_MINUTES",
        "watch_field": None,
        "job_ids": {
            "cruise": "sentiment_low_freq_mode",
        },
        "prefix": "SENTIMENT",
    },
    "metals": {
        "enabled_field": "ENABLE_METALS_MONITOR",
        "cruise_field": "METALS_CRUISE_INTERVAL_MINUTES",
        "watch_field": "METALS_WATCH_INTERVAL_SECONDS",
        "job_ids": {
            "cruise": "metals_cruise_mode",
            "watch": "metals_watch_mode",
        },
        "prefix": "METALS",
    },
}

_scheduler_runtime_state = {
    name: {
        "cruise_interval": getattr(settings, cfg["cruise_field"]),
        "watch_interval": (
            getattr(settings, cfg["watch_field"]) if cfg["watch_field"] else None
        ),
    }
    for name, cfg in MODULE_RUNTIME_CONFIG.items()
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


def _parse_optional_time(value: str) -> Optional[time]:
    value = (value or "").strip()
    if not value:
        return None
    return time.fromisoformat(value)


def _is_day_session_active(start_value: str, end_value: str, now: datetime) -> bool:
    start = _parse_optional_time(start_value)
    end = _parse_optional_time(end_value)
    if not start or not end:
        return False
    return now.weekday() < 5 and start <= now.time() <= end


def _is_night_session_active(start_value: str, end_value: str, now: datetime) -> bool:
    start = _parse_optional_time(start_value)
    end = _parse_optional_time(end_value)
    if not start or not end:
        return False

    current_time = now.time()
    if start <= end:
        return now.weekday() < 5 and start <= current_time <= end

    if current_time >= start:
        return now.weekday() < 5
    if current_time <= end:
        return now.weekday() > 0
    return False


def is_module_watch_hours(prefix: str, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    return any(
        (
            _is_day_session_active(
                getattr(settings, f"{prefix}_MORNING_START"),
                getattr(settings, f"{prefix}_MORNING_END"),
                now,
            ),
            _is_day_session_active(
                getattr(settings, f"{prefix}_AFTERNOON_START"),
                getattr(settings, f"{prefix}_AFTERNOON_END"),
                now,
            ),
            _is_night_session_active(
                getattr(settings, f"{prefix}_NIGHT_START"),
                getattr(settings, f"{prefix}_NIGHT_END"),
                now,
            ),
        )
    )


def is_trading_hours() -> bool:
    """兼容旧测试与旧调用，默认指代期指/A 股交易窗口。"""
    return is_module_watch_hours("FUTURES")


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
        elif strategy_name == "Metals_Arbitrage":
            db_manager.save_metal_snapshots(data)
    except Exception as exc:
        logger.warning(
            "runtime_snapshot_persist_failed",
            strategy=strategy_name,
            error=str(exc),
        )


def run_strategy_task(fetcher, strategy, strategy_name: str):
    """通用策略执行入口。"""
    try:
        logger.info("strategy_task_start", strategy=strategy_name)
        data = fetcher.fetch_live()
        if not data:
            logger.warning("strategy_no_data", strategy=strategy_name)
            return

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
    except Exception as exc:
        logger.error(
            "strategy_task_failed", strategy=strategy_name, error=str(exc), exc_info=True
        )


def _reschedule_runtime_jobs_if_needed():
    for module_name, config in MODULE_RUNTIME_CONFIG.items():
        cruise_interval = getattr(settings, config["cruise_field"])
        state = _scheduler_runtime_state[module_name]
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

        watch_field = config["watch_field"]
        watch_job_id = config["job_ids"].get("watch")
        if watch_field and watch_job_id:
            watch_interval = getattr(settings, watch_field)
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


def sync_runtime_settings():
    previous = {
        module_name: {
            "enabled": getattr(settings, cfg["enabled_field"]),
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
    except Exception as exc:
        logger.error("futures_margin_refresh_failed", error=str(exc), exc_info=True)


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
    sync_runtime_settings()
    if is_module_watch_hours("FUTURES"):
        logger.debug("futures_cruise_skipped_trading_hours")
        return
    if settings.ENABLE_FUTURES_MONITOR:
        run_strategy_task(
            futures_fetcher, FuturesDiscountStrategy(), "Futures_Discount_Arbitrage"
        )
    else:
        logger.info("strategy_disabled", strategy="Futures_Discount_Arbitrage")


def run_convertible_cruise_mode():
    sync_runtime_settings()
    if is_module_watch_hours("CONVERTIBLE"):
        logger.debug("convertible_cruise_skipped_trading_hours")
        return
    if settings.ENABLE_CONVERTIBLE_MONITOR:
        run_strategy_task(
            convertible_fetcher, ConvertibleStrategy(), "Convertible_Arbitrage"
        )
    else:
        logger.info("strategy_disabled", strategy="Convertible_Arbitrage")


def run_sentiment_low_freq_mode():
    sync_runtime_settings()
    if not is_module_watch_hours("SENTIMENT"):
        logger.debug("sentiment_low_freq_skipped_outside_window")
        return
    if settings.ENABLE_SENTIMENT_MONITOR:
        run_strategy_task(
            sentiment_fetcher, SentimentStrategy(), "Sentiment_Heat_and_Risk"
        )
    else:
        logger.info("strategy_disabled", strategy="Sentiment_Heat_and_Risk")


def run_metals_cruise_mode():
    sync_runtime_settings()
    if is_module_watch_hours("METALS"):
        logger.debug("metals_cruise_skipped_watch_hours")
        return
    if settings.ENABLE_METALS_MONITOR:
        run_strategy_task(metals_fetcher, MetalsArbitrageStrategy(), "Metals_Arbitrage")
    else:
        logger.info("strategy_disabled", strategy="Metals_Arbitrage")


def run_futures_watch_mode():
    sync_runtime_settings()
    if not is_module_watch_hours("FUTURES"):
        logger.debug("futures_watch_skipped_non_trading_hours")
        return
    if settings.ENABLE_FUTURES_MONITOR:
        run_strategy_task(
            futures_fetcher, FuturesDiscountStrategy(), "Futures_Discount_Arbitrage"
        )
    else:
        logger.info("strategy_disabled", strategy="Futures_Discount_Arbitrage")


def run_convertible_watch_mode():
    sync_runtime_settings()
    if not is_module_watch_hours("CONVERTIBLE"):
        logger.debug("convertible_watch_skipped_non_trading_hours")
        return
    if settings.ENABLE_CONVERTIBLE_MONITOR:
        run_strategy_task(
            convertible_fetcher, ConvertibleStrategy(), "Convertible_Arbitrage"
        )
    else:
        logger.info("strategy_disabled", strategy="Convertible_Arbitrage")


def run_metals_watch_mode():
    sync_runtime_settings()
    if not is_module_watch_hours("METALS"):
        logger.debug("metals_watch_skipped_non_trading_hours")
        return
    if settings.ENABLE_METALS_MONITOR:
        run_strategy_task(metals_fetcher, MetalsArbitrageStrategy(), "Metals_Arbitrage")
    else:
        logger.info("strategy_disabled", strategy="Metals_Arbitrage")


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

        import os

        db_size = os.path.getsize(db_manager.db_path) if os.path.exists(db_manager.db_path) else 0
        heartbeat_msg = (
            f"🟢 套利监控引擎运行正常\n"
            f"📊 今日报警：{today_alerts} 次\n"
            f"📈 累计报警：{total_alerts} 次\n"
            f"💾 数据库大小：{db_size / 1024:.1f} KB\n"
            f"⏰ 报告时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        from models.signals import Signal

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
    except Exception as exc:
        logger.error("heartbeat_failed", error=str(exc), exc_info=True)


def cleanup_old_runtime_data():
    try:
        retention_days = settings.DATA_RETENTION_DAYS
        logger.info("retention_cleanup_start", retention_days=retention_days)
        alert_rows = db_manager.purge_alert_history_older_than(retention_days)
        margin_rows = db_manager.purge_futures_margin_snapshots_older_than(retention_days)
        futures_rows = db_manager.purge_futures_live_snapshots_older_than(retention_days)
        metals_rows = db_manager.purge_metal_snapshots_older_than(retention_days)
        logger.info(
            "retention_cleanup_completed",
            retention_days=retention_days,
            deleted_alert_rows=alert_rows,
            deleted_margin_rows=margin_rows,
            deleted_futures_snapshot_rows=futures_rows,
            deleted_metal_snapshot_rows=metals_rows,
        )
    except Exception as exc:
        logger.error("retention_cleanup_failed", error=str(exc), exc_info=True)


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
        send_heartbeat,
        "cron",
        hour=9,
        minute=25,
        id="daily_heartbeat",
        name="Daily Heartbeat Report",
    )
    scheduler.add_job(
        refresh_futures_margin_snapshot,
        "cron",
        hour=9,
        minute=0,
        id="futures_margin_open_refresh",
        name="Futures Margin Refresh Before Open",
    )
    scheduler.add_job(
        refresh_futures_margin_snapshot,
        "cron",
        hour=0,
        minute=0,
        id="futures_margin_midnight_refresh",
        name="Futures Margin Refresh At Midnight",
    )
    scheduler.add_job(
        cleanup_old_runtime_data,
        "cron",
        hour=0,
        minute=10,
        id="retention_cleanup",
        name="Retention Cleanup",
    )
    scheduler.add_job(
        sync_runtime_settings,
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
        thread_pool_size=settings.THREAD_POOL_SIZE,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler_stopped")


if __name__ == "__main__":
    main()
