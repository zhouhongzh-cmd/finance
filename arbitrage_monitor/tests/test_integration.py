"""
端到端集成测试脚本
验证调度器、策略、通知、数据库的完整链路
"""

import json
import sys
import os
import io
import tempfile
from typing import Any

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from utils.logger import configure_logger
from utils.db_manager import DBManager
from utils.notifier import notifier

configure_logger()

from utils.logger import logger


def test_db_manager():
    """测试数据库管理器"""
    logger.info("test_db_manager_start")

    db = DBManager()

    with db.get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM alert_history")
        count = cursor.fetchone()[0]
        logger.info("db_check_success", alert_count=count)

    print("✅ DB Manager: OK")
    return True


def test_notifier():
    """测试通知模块"""
    logger.info("test_notifier_start")

    from models.signals import Signal
    from config.settings import settings

    db = DBManager()
    with db.get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO alert_history (timestamp, asset, strategy, level, message, notified)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                "TEST",
                "Integration_Test",
                "INFO",
                "🧪 集成测试通知",
                0,
            ),
        )
        conn.commit()
        alert_id = int(cursor.lastrowid)

    test_signal = Signal(
        asset="TEST",
        strategy_name="Integration_Test",
        level="INFO",
        message="🧪 集成测试通知",
        alert_id=alert_id,
    )

    deliveries: list[tuple[str, dict[str, Any]]] = []
    original_post_json = notifier._post_json
    original_feishu = settings.FEISHU_WEBHOOK_URL
    original_wecom = settings.WECOM_WEBHOOK_URL

    def fake_post_json(url: str, payload: dict[str, Any]):
        deliveries.append((url, payload))

        class DummyResponse:
            def raise_for_status(self):
                return None

        return DummyResponse()

    try:
        settings.FEISHU_WEBHOOK_URL = "https://example.com/feishu"
        settings.WECOM_WEBHOOK_URL = "https://example.com/wecom"
        notifier._post_json = fake_post_json

        notifier.send(test_signal)
        notifier.flush()
    finally:
        notifier._post_json = original_post_json
        settings.FEISHU_WEBHOOK_URL = original_feishu
        settings.WECOM_WEBHOOK_URL = original_wecom

    if len(deliveries) != 2:
        print(f"❌ Notifier: expected 2 deliveries, got {len(deliveries)}")
        return False

    urls = {url for url, _ in deliveries}
    if "https://example.com/feishu" not in urls or "https://example.com/wecom" not in urls:
        print("❌ Notifier: missing expected channel deliveries")
        return False

    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT notified FROM alert_history WHERE id = ?",
            (alert_id,),
        )
        row = cursor.fetchone()

    if row is None or row[0] != 1:
        print(f"❌ Notifier: expected alert {alert_id} notified=1, got {row}")
        return False

    logger.info("notification_sent", asset=test_signal.asset, deliveries=len(deliveries))

    print("✅ Notifier: OK")
    return True


def test_runtime_config_writer():
    """测试 GUI 配置回写共享 JSON 的行为。"""
    logger.info("test_runtime_config_writer_start")

    from pathlib import Path
    from utils.runtime_config import write_env_updates

    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "runtime_settings.json"
        config_path.write_text(
            json.dumps(
                {
                    "ENABLE_FUTURES_MONITOR": True,
                    "CB_YTM_THRESHOLD": 2.0,
                    "METALS_MORNING_START": "09:00",
                    "DATA_RETENTION_DAYS": 30,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        write_env_updates(
            {
                "ENABLE_FUTURES_MONITOR": False,
                "CB_YTM_THRESHOLD": 3.5,
                "FUTURES_WATCH_INTERVAL_SECONDS": 45,
                "METALS_MORNING_START": "08:30",
                "DATA_RETENTION_DAYS": 21,
            },
            env_path=config_path,
        )
        content = json.loads(config_path.read_text(encoding="utf-8"))

    if content["ENABLE_FUTURES_MONITOR"] is not False:
        print("❌ Runtime Config: bool value not updated")
        return False
    if content["CB_YTM_THRESHOLD"] != 3.5:
        print("❌ Runtime Config: existing numeric value not updated")
        return False
    if content["FUTURES_WATCH_INTERVAL_SECONDS"] != 45:
        print("❌ Runtime Config: missing appended key")
        return False
    if content["METALS_MORNING_START"] != "08:30":
        print("❌ Runtime Config: schedule window not updated")
        return False
    if content["DATA_RETENTION_DAYS"] != 21:
        print("❌ Runtime Config: retention days not persisted")
        return False

    logger.info("runtime_config_writer_ok")
    print("✅ Runtime Config Writer: OK")
    return True


def test_strategy_threshold_hot_reload():
    """测试策略阈值热更新后立即影响判定。"""
    logger.info("test_strategy_threshold_hot_reload_start")

    from datetime import datetime
    from config.settings import settings
    from models.market_data import SentimentData
    from strategies.sentiment_strategy import SentimentStrategy

    original = {
        "SENTIMENT_HOT_SCORE_THRESHOLD": settings.SENTIMENT_HOT_SCORE_THRESHOLD,
        "SENTIMENT_PULSE_THRESHOLD": settings.SENTIMENT_PULSE_THRESHOLD,
    }

    try:
        settings.apply_updates(
            {
                "SENTIMENT_HOT_SCORE_THRESHOLD": 500,
                "SENTIMENT_PULSE_THRESHOLD": -0.5,
            }
        )
        data = [
            SentimentData(
                symbol="TEST001",
                timestamp=datetime.now(),
                name="TEST001",
                hot_score=600,
                sentiment_pulse=-0.6,
                rank=1,
            )
        ]
        signals = SentimentStrategy().evaluate(data)
    finally:
        settings.apply_updates(original)

    if len(signals) != 2:
        print(f"❌ Strategy Hot Reload: expected 2 signals, got {len(signals)}")
        return False

    logger.info("strategy_threshold_hot_reload_ok", signals=len(signals))
    print("✅ Strategy Hot Reload: OK")
    return True


def test_strategy_enable_switches():
    """测试策略开关关闭后调度器会跳过对应任务。"""
    logger.info("test_strategy_enable_switches_start")

    import core_scheduler as cs
    from config.settings import settings

    original_run_strategy_task = cs.run_strategy_task
    original_sync_runtime_settings = cs.sync_runtime_settings
    original_is_module_watch_hours = cs.is_module_watch_hours
    original = {
        "ENABLE_FUTURES_MONITOR": settings.ENABLE_FUTURES_MONITOR,
        "ENABLE_CONVERTIBLE_MONITOR": settings.ENABLE_CONVERTIBLE_MONITOR,
        "ENABLE_SENTIMENT_MONITOR": settings.ENABLE_SENTIMENT_MONITOR,
        "ENABLE_METALS_MONITOR": settings.ENABLE_METALS_MONITOR,
    }
    executed: list[str] = []

    def fake_run_strategy_task(fetcher, strategy, strategy_name: str):
        executed.append(strategy_name)

    try:
        cs.run_strategy_task = fake_run_strategy_task
        cs.sync_runtime_settings = lambda: None
        cs.is_module_watch_hours = (
            lambda prefix, now=None: True if prefix == "SENTIMENT" else False
        )
        settings.apply_updates(
            {
                "ENABLE_FUTURES_MONITOR": False,
                "ENABLE_CONVERTIBLE_MONITOR": True,
                "ENABLE_SENTIMENT_MONITOR": False,
                "ENABLE_METALS_MONITOR": False,
            }
        )
        cs.run_futures_cruise_mode()
        cs.run_convertible_cruise_mode()
        cs.run_sentiment_low_freq_mode()
        cs.run_metals_cruise_mode()
    finally:
        settings.apply_updates(original)
        cs.run_strategy_task = original_run_strategy_task
        cs.sync_runtime_settings = original_sync_runtime_settings
        cs.is_module_watch_hours = original_is_module_watch_hours

    if executed != ["Convertible_Arbitrage"]:
        print(f"❌ Strategy Enable Switches: unexpected executed strategies {executed}")
        return False

    logger.info("strategy_enable_switches_ok", executed=executed)
    print("✅ Strategy Enable Switches: OK")
    return True


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

    with tempfile.TemporaryDirectory() as temp_dir:
        shared_path = Path(temp_dir) / "runtime_settings.json"
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
            settings.reload_from_env()
            settings.apply_updates(original)

    logger.info("scheduler_runtime_settings_sync_ok")
    print("✅ Scheduler Runtime Sync: OK")
    return True


def test_fetchers_mock():
    """测试 Fetcher 的 Mock 模式"""
    logger.info("test_fetchers_mock_start")

    from fetchers.ak_futures import futures_fetcher
    from fetchers.ak_convertible import convertible_fetcher
    from fetchers.ak_metals import metals_fetcher
    from fetchers.sentiment_spider import sentiment_fetcher

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    futures_path = os.path.join(base_dir, "tests/fixtures/futures_sample.json")
    futures_data = futures_fetcher.fetch_from_fixture(futures_path)
    logger.info("futures_mock_loaded", count=len(futures_data))
    print(f"✅ Futures Fetcher (Mock): {len(futures_data)} records")

    cb_path = os.path.join(base_dir, "tests/fixtures/cb_mock.json")
    cb_data = convertible_fetcher.fetch_from_fixture(cb_path)
    logger.info("cb_mock_loaded", count=len(cb_data))
    print(f"✅ Convertible Fetcher (Mock): {len(cb_data)} records")

    sentiment_path = os.path.join(base_dir, "tests/fixtures/sentiment_mock.json")
    sentiment_data = sentiment_fetcher.fetch_from_fixture(sentiment_path)
    logger.info("sentiment_mock_loaded", count=len(sentiment_data))
    print(f"✅ Sentiment Fetcher (Mock): {len(sentiment_data)} records")

    metals_path = os.path.join(base_dir, "tests/fixtures/metals_sample.json")
    metals_data = metals_fetcher.fetch_from_fixture(metals_path)
    logger.info("metals_mock_loaded", count=len(metals_data))
    print(f"✅ Metals Fetcher (Mock): {len(metals_data)} records")

    return True


def test_strategies():
    """测试策略计算"""
    logger.info("test_strategies_start")

    from fetchers.ak_futures import futures_fetcher
    from fetchers.ak_convertible import convertible_fetcher
    from fetchers.ak_metals import metals_fetcher
    from fetchers.sentiment_spider import sentiment_fetcher
    from strategies.futures_strategy import FuturesDiscountStrategy
    from strategies.cb_strategy import ConvertibleStrategy
    from strategies.metals_strategy import MetalsArbitrageStrategy
    from strategies.sentiment_strategy import SentimentStrategy

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    futures_path = os.path.join(base_dir, "tests/fixtures/futures_sample.json")
    futures_data = futures_fetcher.fetch_from_fixture(futures_path)
    futures_strategy = FuturesDiscountStrategy()
    futures_signals = futures_strategy.evaluate(futures_data)
    logger.info("futures_strategy_evaluated", signals=len(futures_signals))
    print(f"✅ Futures Strategy: {len(futures_signals)} signals")

    cb_path = os.path.join(base_dir, "tests/fixtures/cb_mock.json")
    cb_data = convertible_fetcher.fetch_from_fixture(cb_path)
    cb_strategy = ConvertibleStrategy()
    cb_signals = cb_strategy.evaluate(cb_data)
    logger.info("cb_strategy_evaluated", signals=len(cb_signals))
    print(f"✅ Convertible Strategy: {len(cb_signals)} signals")

    sentiment_path = os.path.join(base_dir, "tests/fixtures/sentiment_mock.json")
    sentiment_data = sentiment_fetcher.fetch_from_fixture(sentiment_path)
    sentiment_strategy = SentimentStrategy()
    sentiment_signals = sentiment_strategy.evaluate(sentiment_data)
    logger.info("sentiment_strategy_evaluated", signals=len(sentiment_signals))
    print(f"✅ Sentiment Strategy: {len(sentiment_signals)} signals")

    metals_path = os.path.join(base_dir, "tests/fixtures/metals_sample.json")
    metals_data = metals_fetcher.fetch_from_fixture(metals_path)
    metals_strategy = MetalsArbitrageStrategy()
    metals_signals = metals_strategy.evaluate(metals_data)
    logger.info("metals_strategy_evaluated", signals=len(metals_signals))
    print(f"✅ Metals Strategy: {len(metals_signals)} signals")

    return True


def test_convertible_fallback_estimation():
    """测试东方财富备用源字段转换与本地 YTM 估算。"""
    logger.info("test_convertible_fallback_estimation_start")

    from fetchers.ak_convertible import ConvertibleFetcher

    fetcher = ConvertibleFetcher()
    row = {
        "SECURITY_CODE": "127113",
        "SECURITY_NAME_ABBR": "长高转债",
        "CURRENT_BOND_PRICENEW": 100,
        "TRANSFER_PRICE": 11.01,
        "TRANSFER_VALUE": 112.7157,
        "TRANSFER_PREMIUM_RATIO": -11.28,
        "REDEEM_TRIG_PRICE": 14.31,
        "RESALE_TRIG_PRICE": 7.71,
        "CONVERT_STOCK_PRICE": 12.41,
        "COUPON_IR": 0.2,
        "INTEREST_RATE_EXPLAIN": "第一年为0.2%、第二年为0.4%、第三年为0.6%、第四年为1.0%、第五年为1.5%、第六年为2.0%。",
        "BOND_START_DATE": "2026-03-11 00:00:00",
        "REDEEM_CLAUSE": "到期赎回条款在本次发行的可转债期满后五个交易日内,发行人将按债券面值的110%(含最后一期利息)的价格赎回全部未转股的可转换公司债券。",
    }

    item = fetcher._build_cbdata_from_eastmoney_row(row)
    if item is None:
        print("❌ Convertible Fallback: build result is None")
        return False

    if item.symbol != "127113(长高转债)":
        print(f"❌ Convertible Fallback: unexpected symbol {item.symbol}")
        return False

    if round(item.premium_rate, 2) != -11.28:
        print(f"❌ Convertible Fallback: unexpected premium {item.premium_rate}")
        return False

    if round(item.double_low, 2) != 88.72:
        print(f"❌ Convertible Fallback: unexpected double_low {item.double_low}")
        return False

    if not (2.0 <= item.ytm <= 3.0):
        print(f"❌ Convertible Fallback: unexpected ytm {item.ytm}")
        return False

    logger.info("convertible_fallback_estimated", ytm=item.ytm, double_low=item.double_low)
    print(f"✅ Convertible Fallback: YTM={item.ytm}, double_low={item.double_low:.2f}")
    return True


def test_metals_conversion_and_thresholds():
    """测试金属换算逻辑与阈值配置热更新。"""
    logger.info("test_metals_conversion_and_thresholds_start")

    from fetchers.ak_metals import MetalsFetcher
    from strategies.metals_strategy import MetalsArbitrageStrategy
    from utils.metals_config import (
        get_effective_metal_threshold,
        load_metals_thresholds,
        reset_metals_thresholds,
        save_metals_thresholds,
    )

    fetcher = MetalsFetcher()
    xau_cny, xau_used_api = fetcher.convert_foreign_price(
        usd_price=3130.0,
        rate=6.9,
        unit_factor=31.1034768,
        foreign_cny=695.2,
        benchmark_name="COMEX黄金",
    )
    if round(xau_cny, 2) != 695.2 or not xau_used_api:
        print(f"❌ Metals Conversion: unexpected XAU conversion {(xau_cny, xau_used_api)}")
        return False

    xag_cny, xag_used_api = fetcher.convert_foreign_price(
        usd_price=31.5,
        rate=7.2,
        unit_factor=32.1507,
        foreign_cny=255.0,
        benchmark_name="COMEX白银",
    )
    if round(xag_cny, 2) != round(255.0 * 32.1507, 2) or not xag_used_api:
        print(f"❌ Metals Conversion: unexpected XAG conversion {(xag_cny, xag_used_api)}")
        return False

    hg_rate = fetcher.calculate_implied_rate(
        for_price_cny=67400.0,
        foreign_usd=460.0,
        unit_factor=22.0462,
        rate_direction="mul",
    )
    if not (6.5 <= hg_rate <= 6.8):
        print(f"❌ Metals Conversion: unexpected HG implied rate {hg_rate}")
        return False

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    metals_path = os.path.join(base_dir, "tests/fixtures/metals_sample.json")
    metals_data = fetcher.fetch_from_fixture(metals_path)
    strategy = MetalsArbitrageStrategy()
    original_thresholds = load_metals_thresholds()

    try:
        save_metals_thresholds(
            {
                **original_thresholds,
                "AU0": {"upper": 10.0, "lower": -10.0},
                "AG0": {"upper": 10.0, "lower": -10.0},
            }
        )
        if get_effective_metal_threshold("AU0")["upper"] != 10.0:
            print("❌ Metals Thresholds: hot reload not applied")
            return False
        muted_signals = strategy.evaluate(metals_data)
        if muted_signals:
            print(f"❌ Metals Thresholds: expected 0 muted signals, got {len(muted_signals)}")
            return False

        save_metals_thresholds(
            {
                **original_thresholds,
                "AU0": {"upper": 1.0, "lower": -1.0},
                "AG0": {"upper": 2.0, "lower": -2.0},
            }
        )
        active_signals = strategy.evaluate(metals_data)
    finally:
        save_metals_thresholds(original_thresholds)

    if len(active_signals) != 2:
        print(f"❌ Metals Thresholds: expected 2 active signals, got {len(active_signals)}")
        return False

    reset_metals_thresholds()
    logger.info("metals_conversion_and_thresholds_ok", signals=len(active_signals))
    print("✅ Metals Conversion & Thresholds: OK")
    return True


def test_legacy_metals_threshold_migration():
    """测试旧版金属阈值文件的显式迁移和字段兼容性。"""
    logger.info("test_legacy_metals_threshold_migration_start")

    from pathlib import Path
    import utils.metals_config as metals_config

    original_new_path_fn = metals_config.get_metals_thresholds_path
    original_legacy_path_fn = metals_config.get_legacy_metals_thresholds_path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        new_path = temp_root / "config" / "metals_thresholds.json"
        legacy_path = temp_root / "data" / "metals_thresholds.json"
        new_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.parent.mkdir(parents=True, exist_ok=True)

        new_path.write_text(
            json.dumps(
                {
                    "AU0": {"upper": 1.0, "lower": -1.0},
                    "AG0": {"upper": 2.0, "lower": -2.0},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        legacy_path.write_text(
            json.dumps(
                {
                    "AU0": {"upper": 1.0, "lower": -1.0},
                    "AG0": {"upper": 8.0, "lower": -8.0},
                    "REMOVED_SYMBOL": {"upper": 99.0, "lower": -99.0},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        metals_config.get_metals_thresholds_path = lambda: new_path
        metals_config.get_legacy_metals_thresholds_path = lambda: legacy_path
        metals_config._threshold_cache = None

        try:
            preview = metals_config.get_legacy_metals_thresholds_preview()
            if preview is None:
                print("❌ Metals Migration: expected migration preview")
                return False
            if len(preview["differences"]) != 1 or preview["differences"][0]["symbol"] != "AG0":
                print(f"❌ Metals Migration: unexpected diff preview {preview['differences']}")
                return False

            result = metals_config.migrate_legacy_metals_thresholds()
            if not result["migrated"] or result["count"] != 1:
                print(f"❌ Metals Migration: unexpected migrate result {result}")
                return False
            if legacy_path.exists():
                print("❌ Metals Migration: legacy file should be removed after migration")
                return False

            migrated = json.loads(new_path.read_text(encoding="utf-8"))
            if migrated["AG0"]["upper"] != 8.0 or migrated["AG0"]["lower"] != -8.0:
                print(f"❌ Metals Migration: AG0 not migrated correctly {migrated['AG0']}")
                return False
            if "REMOVED_SYMBOL" in migrated:
                print("❌ Metals Migration: removed symbol should not be kept")
                return False
            if "PT0" not in migrated:
                print("❌ Metals Migration: new symbols should be filled from defaults")
                return False
        finally:
            metals_config.get_metals_thresholds_path = original_new_path_fn
            metals_config.get_legacy_metals_thresholds_path = original_legacy_path_fn
            metals_config._threshold_cache = None

    logger.info("legacy_metals_threshold_migration_ok")
    print("✅ Legacy Metals Threshold Migration: OK")
    return True


def test_current_metals_threshold_file_compatibility():
    """测试当前 config/metals_thresholds.json 的旧结构兼容性。"""
    logger.info("test_current_metals_threshold_file_compatibility_start")

    from pathlib import Path
    import utils.metals_config as metals_config

    original_new_path_fn = metals_config.get_metals_thresholds_path
    original_legacy_path_fn = metals_config.get_legacy_metals_thresholds_path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        new_path = temp_root / "config" / "metals_thresholds.json"
        legacy_path = temp_root / "data" / "metals_thresholds.json"
        new_path.parent.mkdir(parents=True, exist_ok=True)

        # 模拟同路径老版本: 缺少新金属、包含已删除金属、部分字段缺失
        new_path.write_text(
            json.dumps(
                {
                    "AU0": {"upper": 1.2},
                    "AG0": {"lower": -9.0},
                    "REMOVED_SYMBOL": {"upper": 99.0, "lower": -99.0},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        metals_config.get_metals_thresholds_path = lambda: new_path
        metals_config.get_legacy_metals_thresholds_path = lambda: legacy_path
        metals_config._threshold_cache = None

        try:
            normalized = metals_config.load_metals_thresholds(force_reload=True)
            if normalized["AU0"]["upper"] != 1.2 or normalized["AU0"]["lower"] != -1.0:
                print(f"❌ Metals Current Config: AU0 normalization mismatch {normalized['AU0']}")
                return False
            if normalized["AG0"]["upper"] != 2.0 or normalized["AG0"]["lower"] != -9.0:
                print(f"❌ Metals Current Config: AG0 normalization mismatch {normalized['AG0']}")
                return False
            if "REMOVED_SYMBOL" in normalized:
                print("❌ Metals Current Config: removed symbol should be discarded")
                return False
            if "PT0" not in normalized:
                print("❌ Metals Current Config: missing new symbol defaults")
                return False

            rewritten = json.loads(new_path.read_text(encoding="utf-8"))
            if "REMOVED_SYMBOL" in rewritten:
                print("❌ Metals Current Config: stale symbol should not remain after rewrite")
                return False
            if rewritten["PT0"]["upper"] != 2.0 or rewritten["PT0"]["lower"] != -2.0:
                print(f"❌ Metals Current Config: new symbol defaults missing {rewritten['PT0']}")
                return False
        finally:
            metals_config.get_metals_thresholds_path = original_new_path_fn
            metals_config.get_legacy_metals_thresholds_path = original_legacy_path_fn
            metals_config._threshold_cache = None

    logger.info("current_metals_threshold_file_compatibility_ok")
    print("✅ Current Metals Threshold File Compatibility: OK")
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


def test_futures_margin_enrichment():
    """测试期指保证金比例解析、落库和行情补全。"""
    logger.info("test_futures_margin_enrichment_start")

    from fetchers.futures_margin import FuturesMarginFetcher, futures_margin_fetcher
    from fetchers.ak_futures import futures_fetcher
    from models.market_data import FuturesMarginData

    fetcher = FuturesMarginFetcher()
    list_html = '<a href="/bzjjzdtb/92035.jhtml">2026年3月13日结算保证金及涨跌停板</a>'
    detail_url = fetcher._extract_latest_cicc_detail_url(list_html)
    if detail_url != "https://www.ciccwmf.cn/bzjjzdtb/92035.jhtml":
        print(f"❌ Futures Margin: unexpected detail url {detail_url}")
        return False

    detail_html = """
    <table>
      <tr><th>交易所</th><th>品种</th><th>保证金标准</th></tr>
      <tr><td>中金所</td><td>沪深300期货IF</td><td>14%</td></tr>
      <tr><td>中金所</td><td>上证50期货IH</td><td>14%</td></tr>
      <tr><td>中金所</td><td>中证500期货IC</td><td>15%</td></tr>
      <tr><td>中金所</td><td>中证1000期货IM</td><td>15%</td></tr>
    </table>
    """
    ratios = fetcher._extract_cicc_margin_ratios(detail_html)
    if ratios != {"IF": 14.0, "IH": 14.0, "IC": 15.0, "IM": 15.0}:
        print(f"❌ Futures Margin: unexpected parsed ratios {ratios}")
        return False

    sample_html = "<table><tr><td>交易保证金标准</td><td>8%</td></tr></table>"
    ratio = fetcher._extract_margin_ratio(sample_html)
    if ratio != 8.0:
        print(f"❌ Futures Margin: unexpected parsed ratio {ratio}")
        return False

    now = datetime.now()
    db = DBManager()
    db.save_futures_margin_snapshots(
        [
            FuturesMarginData(
                symbol="IF",
                timestamp=now,
                margin_ratio=12.0,
                source="test",
                source_url="https://example.com/if",
            ),
            FuturesMarginData(
                symbol="IC",
                timestamp=now,
                margin_ratio=14.0,
                source="test",
                source_url="https://example.com/ic",
            ),
        ]
    )

    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM futures_margin_snapshot
            WHERE product_code IN ('IF', 'IC') AND fetched_at = ?
            """,
            (now.isoformat(),),
        )
        snapshot_count = cursor.fetchone()[0]
    if snapshot_count != 2:
        print(
            "❌ Futures Margin: expected 2 inserted snapshots for current test run, "
            f"got {snapshot_count}"
        )
        return False

    original_get_latest_margin_ratio = futures_margin_fetcher.get_latest_margin_ratio
    futures_margin_fetcher.get_latest_margin_ratio = lambda product_code: {
        "IF": 12.0,
        "IC": 14.0,
    }.get(product_code, original_get_latest_margin_ratio(product_code))
    try:
        data = futures_fetcher.fetch_from_fixture("tests/fixtures/futures_sample.json")
    finally:
        futures_margin_fetcher.get_latest_margin_ratio = original_get_latest_margin_ratio

    if not data:
        print("❌ Futures Margin: no futures data loaded")
        return False

    first = data[0]
    second = data[1]
    if first.product_code != "IF" or round(first.margin_ratio, 2) != 12.0:
        print(f"❌ Futures Margin: unexpected IF margin {first.margin_ratio}")
        return False
    if round(first.notional_per_lot, 2) != round(first.price * 300, 2):
        print(f"❌ Futures Margin: unexpected IF notional {first.notional_per_lot}")
        return False
    if round(first.margin_required_per_lot, 2) != round(first.notional_per_lot * 0.12, 2):
        print(
            "❌ Futures Margin: unexpected IF margin required "
            f"{first.margin_required_per_lot}"
        )
        return False

    if second.product_code != "IC" or round(second.margin_ratio, 2) != 14.0:
        print(f"❌ Futures Margin: unexpected IC margin {second.margin_ratio}")
        return False

    logger.info(
        "futures_margin_enriched",
        if_margin=first.margin_ratio,
        ic_margin=second.margin_ratio,
    )
    print(
        "✅ Futures Margin: "
        f"IF={first.margin_ratio:.2f}% margin={first.margin_required_per_lot:.0f}, "
        f"IC={second.margin_ratio:.2f}%"
    )
    return True


def test_active_futures_contract_generation():
    """测试季月场景下仍能生成 4 档有效合约。"""
    logger.info("test_active_futures_contract_generation_start")

    from datetime import date
    from fetchers.ak_futures import get_active_contracts

    contracts = get_active_contracts(today=date(2026, 3, 15))
    by_product: dict[str, list[str]] = {}
    for symbol, _, _ in contracts:
        by_product.setdefault(symbol[:2], []).append(symbol)

    expected = {
        "IF": ["IF2603", "IF2604", "IF2606", "IF2609"],
        "IH": ["IH2603", "IH2604", "IH2606", "IH2609"],
        "IC": ["IC2603", "IC2604", "IC2606", "IC2609"],
        "IM": ["IM2603", "IM2604", "IM2606", "IM2609"],
    }

    for product_code, expected_symbols in expected.items():
        actual = by_product.get(product_code)
        if actual != expected_symbols:
            print(
                f"❌ Active Contracts: {product_code} expected {expected_symbols}, got {actual}"
            )
            return False

    logger.info("active_futures_contract_generation_ok", contracts=len(contracts))
    print("✅ Active Contracts: quarter-month generation OK")
    return True


def test_spot_index_fallback_parser():
    """测试新浪指数备源解析。"""
    logger.info("test_spot_index_fallback_parser_start")

    from fetchers.ak_futures import FuturesFetcher

    fetcher = FuturesFetcher()
    sample = (
        'var hq_str_sh000300="沪深300,4669.0619,4687.5601,4669.1400,4707.4194,4659.4979,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-03-13,15:35:29,00,";\n'
        'var hq_str_sh000016="上证50,2961.7335,2971.5612,2956.8468,2977.8417,2951.7012,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-03-13,15:35:41,00,";\n'
        'var hq_str_sh000905="中证500,8317.7799,8359.4721,8239.7980,8371.7157,8217.9686,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-03-13,15:35:35,00,";\n'
        'var hq_str_sz399852="中证1000,8297.913,8335.908,8214.293,8350.917,8196.374,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-03-13,15:00:42,00,";'
    )
    parsed = fetcher._parse_sina_index_response(sample)
    expected = {
        "000300": 4669.14,
        "000016": 2956.8468,
        "000905": 8239.798,
        "000852": 8214.293,
    }
    if parsed != expected:
        print(f"❌ Spot Index Fallback: expected {expected}, got {parsed}")
        return False

    logger.info("spot_index_fallback_parser_ok", count=len(parsed))
    print("✅ Spot Index Fallback: parser OK")
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


def test_full_pipeline():
    """测试完整链路"""
    logger.info("test_full_pipeline_start")

    from fetchers.ak_futures import futures_fetcher
    from strategies.futures_strategy import FuturesDiscountStrategy
    from config.settings import settings

    data = futures_fetcher.fetch_from_fixture("tests/fixtures/futures_sample.json")
    strategy = FuturesDiscountStrategy()
    signals = strategy.evaluate(data)

    db = DBManager()
    deliveries: list[tuple[str, dict[str, Any]]] = []
    original_post_json = notifier._post_json
    original_feishu = settings.FEISHU_WEBHOOK_URL
    original_wecom = settings.WECOM_WEBHOOK_URL

    def fake_post_json(url: str, payload: dict[str, Any]):
        deliveries.append((url, payload))

        class DummyResponse:
            def raise_for_status(self):
                return None

        return DummyResponse()

    settings.FEISHU_WEBHOOK_URL = "https://example.com/feishu"
    settings.WECOM_WEBHOOK_URL = "https://example.com/wecom"
    notifier._post_json = fake_post_json

    try:
        alert_ids: list[int] = []
        for signal in signals:
            signal.alert_id = db.save_signal(signal)
            alert_ids.append(signal.alert_id)
            notifier.send(signal)

        notifier.flush()
    finally:
        notifier._post_json = original_post_json
        settings.FEISHU_WEBHOOK_URL = original_feishu
        settings.WECOM_WEBHOOK_URL = original_wecom

    with db.get_connection() as conn:
        cursor = conn.execute(
            f"SELECT COUNT(*) FROM alert_history WHERE id IN ({','.join(['?'] * len(alert_ids))}) AND notified = 1",
            alert_ids,
        )
        notified_count = cursor.fetchone()[0]

    if notified_count != len(alert_ids):
        print(
            "❌ Full Pipeline: expected all alerts notified, "
            f"got {notified_count}/{len(alert_ids)}"
        )
        return False

    logger.info("full_pipeline_completed", signals_processed=len(signals))
    print(f"✅ Full Pipeline: {len(signals)} signals processed")

    return True


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


def test_retention_cleanup():
    """测试历史报警与各类快照的保留期清理。"""
    logger.info("test_retention_cleanup_start")

    from models.market_data import FuturesData, FuturesMarginData, MetalArbitrageData

    db = DBManager()
    old_ts = datetime.now().replace(microsecond=0) - timedelta(days=365)
    new_ts = datetime.now().replace(microsecond=0)

    with db.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO alert_history (timestamp, asset, strategy, level, message, notified)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                old_ts.isoformat(),
                "RETENTION_OLD",
                "Retention_Test",
                "INFO",
                "old row",
            ),
        )
        conn.execute(
            """
            INSERT INTO alert_history (timestamp, asset, strategy, level, message, notified)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                new_ts.isoformat(),
                "RETENTION_NEW",
                "Retention_Test",
                "INFO",
                "new row",
            ),
        )
        conn.commit()

    db.save_futures_margin_snapshots(
        [
            FuturesMarginData(
                symbol="IF",
                timestamp=old_ts,
                margin_ratio=12.0,
                source="retention_old",
                source_url="https://example.com/old",
            ),
            FuturesMarginData(
                symbol="IH",
                timestamp=new_ts,
                margin_ratio=13.0,
                source="retention_new",
                source_url="https://example.com/new",
            ),
        ]
    )
    db.save_futures_live_snapshots(
        [
            FuturesData(
                symbol="RETENTION_IF_OLD",
                timestamp=old_ts,
                price=3500.0,
                spot_price=3600.0,
                discount_rate=2.77,
                product_code="IF",
                contract_multiplier=300,
                margin_ratio=12.0,
                notional_per_lot=1_050_000.0,
                margin_required_per_lot=126_000.0,
                days_to_maturity=20,
            ),
            FuturesData(
                symbol="RETENTION_IF_NEW",
                timestamp=new_ts,
                price=3550.0,
                spot_price=3600.0,
                discount_rate=1.38,
                product_code="IF",
                contract_multiplier=300,
                margin_ratio=12.0,
                notional_per_lot=1_065_000.0,
                margin_required_per_lot=127_800.0,
                days_to_maturity=50,
            ),
        ]
    )
    db.save_metal_snapshots(
        [
            MetalArbitrageData(
                symbol="AU0:GC",
                timestamp=old_ts,
                metal_symbol="AU0",
                metal_name="黄金",
                benchmark_symbol="GC",
                benchmark_name="COMEX黄金",
                benchmark_display_name="COMEX GC",
                domestic_symbol="au0",
                domestic_name="沪金主力",
                domestic_unit="元/克",
                category="precious",
                dom_price=700.0,
                for_price_usd=3000.0,
                for_price_cny=690.0,
                exchange_rate=6.9,
                implied_rate=6.9,
                spread=10.0,
                spread_pct=1.45,
            ),
            MetalArbitrageData(
                symbol="AG0:SI",
                timestamp=new_ts,
                metal_symbol="AG0",
                metal_name="白银",
                benchmark_symbol="SI",
                benchmark_name="COMEX白银",
                benchmark_display_name="COMEX SI",
                domestic_symbol="ag0",
                domestic_name="沪银主力",
                domestic_unit="元/千克",
                category="precious",
                dom_price=7800.0,
                for_price_usd=31.0,
                for_price_cny=7700.0,
                exchange_rate=7.2,
                implied_rate=7.2,
                spread=100.0,
                spread_pct=1.3,
            ),
        ]
    )

    deleted_alerts = db.purge_alert_history_older_than(30)
    deleted_margins = db.purge_futures_margin_snapshots_older_than(30)
    deleted_futures = db.purge_futures_live_snapshots_older_than(30)
    deleted_metals = db.purge_metal_snapshots_older_than(30)

    with db.get_connection() as conn:
        old_alert_count = conn.execute(
            "SELECT COUNT(*) FROM alert_history WHERE asset = 'RETENTION_OLD'"
        ).fetchone()[0]
        new_alert_count = conn.execute(
            "SELECT COUNT(*) FROM alert_history WHERE asset = 'RETENTION_NEW'"
        ).fetchone()[0]
        old_margin_count = conn.execute(
            "SELECT COUNT(*) FROM futures_margin_snapshot WHERE source = 'retention_old'"
        ).fetchone()[0]
        new_margin_count = conn.execute(
            "SELECT COUNT(*) FROM futures_margin_snapshot WHERE source = 'retention_new'"
        ).fetchone()[0]
        old_futures_count = conn.execute(
            "SELECT COUNT(*) FROM futures_live_snapshot WHERE symbol = 'RETENTION_IF_OLD'"
        ).fetchone()[0]
        new_futures_count = conn.execute(
            "SELECT COUNT(*) FROM futures_live_snapshot WHERE symbol = 'RETENTION_IF_NEW'"
        ).fetchone()[0]
        old_metals_count = conn.execute(
            "SELECT COUNT(*) FROM metal_arbitrage_snapshot WHERE symbol = 'AU0:GC' AND fetched_at = ?",
            (old_ts.isoformat(),),
        ).fetchone()[0]
        new_metals_count = conn.execute(
            "SELECT COUNT(*) FROM metal_arbitrage_snapshot WHERE symbol = 'AG0:SI' AND fetched_at = ?",
            (new_ts.isoformat(),),
        ).fetchone()[0]
        conn.execute("DELETE FROM alert_history WHERE asset = 'RETENTION_NEW'")
        conn.execute(
            "DELETE FROM futures_margin_snapshot WHERE source = 'retention_new'"
        )
        conn.execute("DELETE FROM futures_live_snapshot WHERE symbol = 'RETENTION_IF_NEW'")
        conn.execute(
            "DELETE FROM metal_arbitrage_snapshot WHERE symbol = 'AG0:SI' AND fetched_at = ?",
            (new_ts.isoformat(),),
        )
        conn.commit()

    if deleted_alerts < 1 or old_alert_count != 0 or new_alert_count != 1:
        print(
            "❌ Retention Cleanup: alert_history cleanup mismatch "
            f"(deleted={deleted_alerts}, old={old_alert_count}, new={new_alert_count})"
        )
        return False
    if deleted_margins < 1 or old_margin_count != 0 or new_margin_count != 1:
        print(
            "❌ Retention Cleanup: margin cleanup mismatch "
            f"(deleted={deleted_margins}, old={old_margin_count}, new={new_margin_count})"
        )
        return False
    if deleted_futures < 1 or old_futures_count != 0 or new_futures_count != 1:
        print(
            "❌ Retention Cleanup: futures snapshot cleanup mismatch "
            f"(deleted={deleted_futures}, old={old_futures_count}, new={new_futures_count})"
        )
        return False
    if deleted_metals < 1 or old_metals_count != 0 or new_metals_count != 1:
        print(
            "❌ Retention Cleanup: metals snapshot cleanup mismatch "
            f"(deleted={deleted_metals}, old={old_metals_count}, new={new_metals_count})"
        )
        return False

    logger.info(
        "retention_cleanup_ok",
        deleted_alerts=deleted_alerts,
        deleted_margins=deleted_margins,
        deleted_futures=deleted_futures,
        deleted_metals=deleted_metals,
    )
    print("✅ Retention Cleanup: OK")
    return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🧪 套利监控系统 - 端到端集成测试")
    print("=" * 60 + "\n")

    tests = [
        ("Database Manager", test_db_manager),
        ("Notifier", test_notifier),
        ("Runtime Config Writer", test_runtime_config_writer),
        ("Strategy Hot Reload", test_strategy_threshold_hot_reload),
        ("Strategy Enable Switches", test_strategy_enable_switches),
        ("Scheduler Runtime Sync", test_scheduler_runtime_settings_sync),
        ("Cooldown Restore", test_cooldown_restore_roundtrip),
        ("Retention Cleanup", test_retention_cleanup),
        ("Fetchers (Mock)", test_fetchers_mock),
        ("Strategies", test_strategies),
        ("Metals Conversion", test_metals_conversion_and_thresholds),
        ("Legacy Metals Migration", test_legacy_metals_threshold_migration),
        ("Current Metals Config Compatibility", test_current_metals_threshold_file_compatibility),
        ("Convertible Fallback", test_convertible_fallback_estimation),
        ("Futures Margin", test_futures_margin_enrichment),
        ("Active Contracts", test_active_futures_contract_generation),
        ("Spot Index Fallback", test_spot_index_fallback_parser),
        ("Module Schedule Windows", test_module_schedule_windows),
        ("Scheduler Imports", test_scheduler_imports),
        ("Full Pipeline", test_full_pipeline),
    ]

    passed = 0
    failed = 0
    skipped = 0

    for name, test_func in tests:
        try:
            result = test_func()
            if result is True:
                passed += 1
            elif result == "SKIP":
                skipped += 1
            else:
                failed += 1
        except Exception as e:
            logger.error("test_failed", test=name, error=str(e), exc_info=True)
            print(f"❌ {name}: EXCEPTION - {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"📊 测试结果：{passed} 通过，{failed} 失败，{skipped} 跳过")
    print("=" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
