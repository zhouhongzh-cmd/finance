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

def test_fetchers_mock():
    """测试 Fetcher 的 Mock 模式"""
    logger.info("test_fetchers_mock_start")

    from fetchers.ak_futures import futures_fetcher
    from fetchers.ak_convertible import convertible_fetcher
    from fetchers.ak_metals import metals_fetcher
    from fetchers.premium_fetcher import premium_fetcher
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

    premium_path = os.path.join(base_dir, "tests/fixtures/premium_sample.json")
    premium_data = premium_fetcher.fetch_from_fixture(premium_path)
    logger.info("premium_mock_loaded", count=len(premium_data))
    print(f"✅ Premium Fetcher (Mock): {len(premium_data)} records")

    if len(premium_data) != 4:
        print(f"❌ Fetchers Mock: expected 4 valid premium rows, got {len(premium_data)}")
        return False

    return True

def test_strategies():
    """测试策略计算"""
    logger.info("test_strategies_start")

    from fetchers.ak_futures import futures_fetcher
    from fetchers.ak_convertible import convertible_fetcher
    from fetchers.ak_metals import metals_fetcher
    from fetchers.premium_fetcher import premium_fetcher
    from fetchers.sentiment_spider import sentiment_fetcher
    from strategies.futures_strategy import FuturesDiscountStrategy
    from strategies.cb_strategy import ConvertibleStrategy
    from strategies.metals_strategy import MetalsArbitrageStrategy
    from strategies.premium_strategy import PremiumArbitrageStrategy
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

    premium_path = os.path.join(base_dir, "tests/fixtures/premium_sample.json")
    premium_data = premium_fetcher.fetch_from_fixture(premium_path)
    premium_strategy = PremiumArbitrageStrategy()
    premium_signals = premium_strategy.evaluate(premium_data)
    logger.info("premium_strategy_evaluated", signals=len(premium_signals))
    print(f"✅ Premium Strategy: {len(premium_signals)} signals")

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

def test_mode_enable_switches():
    """测试模块巡航/盯盘开关对运行模式生效。"""
    logger.info("test_mode_enable_switches_start")

    import core_scheduler as cs
    from config.settings import settings

    original_run_strategy_task = cs.run_strategy_task
    original_sync_runtime_settings = cs.sync_runtime_settings
    original_is_module_watch_hours = cs.is_module_watch_hours
    original = {
        "ENABLE_FUTURES_MONITOR": settings.ENABLE_FUTURES_MONITOR,
        "ENABLE_FUTURES_CRUISE": settings.ENABLE_FUTURES_CRUISE,
        "ENABLE_FUTURES_WATCH": settings.ENABLE_FUTURES_WATCH,
    }
    executed: list[str] = []

    def fake_run_strategy_task(fetcher, strategy, strategy_name: str):
        executed.append(strategy_name)
        return {"status": "SUCCESS"}

    try:
        cs.run_strategy_task = fake_run_strategy_task
        cs.sync_runtime_settings = lambda: None
        cs.is_module_watch_hours = lambda prefix, now=None: prefix == "FUTURES"
        settings.apply_updates(
            {
                "ENABLE_FUTURES_MONITOR": True,
                "ENABLE_FUTURES_CRUISE": True,
                "ENABLE_FUTURES_WATCH": False,
            }
        )
        cs.run_futures_cruise_mode()
        cs.run_futures_watch_mode()
    finally:
        settings.apply_updates(original)
        cs.run_strategy_task = original_run_strategy_task
        cs.sync_runtime_settings = original_sync_runtime_settings
        cs.is_module_watch_hours = original_is_module_watch_hours

    if executed != ["Futures_Discount_Arbitrage"]:
        print(f"❌ Mode Enable Switches: unexpected executed strategies {executed}")
        return False

    logger.info("mode_enable_switches_ok", executed=executed)
    print("✅ Mode Enable Switches: OK")
    return True

def test_threshold_enable_switches():
    """测试阈值开关关闭后不再参与策略触发。"""
    logger.info("test_threshold_enable_switches_start")

    from models.market_data import FuturesData, SentimentData
    from strategies.futures_strategy import FuturesDiscountStrategy
    from strategies.sentiment_strategy import SentimentStrategy
    from config.settings import settings
    import config.futures_thresholds as futures_config

    original_sentiment = {
        "ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD": settings.ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD,
        "ENABLE_SENTIMENT_PULSE_THRESHOLD": settings.ENABLE_SENTIMENT_PULSE_THRESHOLD,
        "SENTIMENT_HOT_SCORE_THRESHOLD": settings.SENTIMENT_HOT_SCORE_THRESHOLD,
        "SENTIMENT_PULSE_THRESHOLD": settings.SENTIMENT_PULSE_THRESHOLD,
    }
    original_shared_path_fn = futures_config.get_futures_thresholds_path
    original_local_path_fn = futures_config.get_local_futures_thresholds_path
    original_cache = futures_config._threshold_cache

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        shared_path = temp_root / "config" / "futures_thresholds.json"
        local_path = temp_root / "config" / "futures_thresholds.local.json"
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        shared_path.write_text(
            json.dumps(
                {
                    product: {
                        "backwardation_enabled": False,
                        "backwardation_threshold": 1.0,
                        "annualized_backwardation_threshold": 8.0,
                        "contango_enabled": False,
                        "contango_threshold": 1.0,
                        "annualized_contango_threshold": 8.0,
                    }
                    for product in ("IH", "IF", "IC", "IM")
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        futures_config.get_futures_thresholds_path = lambda: shared_path
        futures_config.get_local_futures_thresholds_path = lambda: local_path
        futures_config._threshold_cache = None

        try:
            settings.apply_updates(
                {
                    "ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD": False,
                    "ENABLE_SENTIMENT_PULSE_THRESHOLD": False,
                    "SENTIMENT_HOT_SCORE_THRESHOLD": 500,
                    "SENTIMENT_PULSE_THRESHOLD": -0.5,
                }
            )
            futures_signals = FuturesDiscountStrategy().evaluate(
                [
                    FuturesData(
                        symbol="IF2604",
                        timestamp=datetime.now(),
                        price=3500,
                        spot_price=3540,
                        discount_rate=1.2,
                        product_code="IF",
                        days_to_maturity=5,
                    )
                ]
            )
            sentiment_signals = SentimentStrategy().evaluate(
                [
                    SentimentData(
                        symbol="TEST001",
                        timestamp=datetime.now(),
                        name="TEST001",
                        hot_score=600,
                        sentiment_pulse=-0.6,
                        rank=1,
                    )
                ]
            )
        finally:
            settings.apply_updates(original_sentiment)
            futures_config.get_futures_thresholds_path = original_shared_path_fn
            futures_config.get_local_futures_thresholds_path = original_local_path_fn
            futures_config._threshold_cache = original_cache

    if futures_signals:
        print("❌ Threshold Enable Switches: futures thresholds disabled but still triggered")
        return False
    if sentiment_signals:
        print("❌ Threshold Enable Switches: sentiment thresholds disabled but still triggered")
        return False

    logger.info("threshold_enable_switches_ok")
    print("✅ Threshold Enable Switches: OK")
    return True

