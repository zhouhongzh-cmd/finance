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
    """测试 GUI 配置回写本机 local JSON 的行为。"""
    logger.info("test_runtime_config_writer_start")

    from pathlib import Path
    from utils.runtime_config import write_env_updates

    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "runtime_settings.local.json"
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


def test_runtime_config_local_override():
    """测试本机 runtime local 配置优先于仓库共享基线。"""
    logger.info("test_runtime_config_local_override_start")

    from pathlib import Path
    import config.settings as settings_module

    original_shared_path = settings_module.SHARED_RUNTIME_CONFIG_PATH
    original_local_path = settings_module.LOCAL_RUNTIME_CONFIG_PATH

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        shared_path = temp_root / "config" / "runtime_settings.json"
        local_path = temp_root / "config" / "runtime_settings.local.json"
        shared_path.parent.mkdir(parents=True, exist_ok=True)

        shared_path.write_text(
            json.dumps(
                {
                    "ENABLE_CONVERTIBLE_MONITOR": True,
                    "ENABLE_SENTIMENT_MONITOR": True,
                    "METALS_CRUISE_INTERVAL_MINUTES": 15,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        local_path.write_text(
            json.dumps(
                {
                    "ENABLE_CONVERTIBLE_MONITOR": False,
                    "METALS_CRUISE_INTERVAL_MINUTES": 21,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        settings_module.SHARED_RUNTIME_CONFIG_PATH = shared_path
        settings_module.LOCAL_RUNTIME_CONFIG_PATH = local_path
        probe = settings_module.Settings()

        try:
            effective = settings_module.load_effective_runtime_config(probe, force_reload=True)
        finally:
            settings_module.SHARED_RUNTIME_CONFIG_PATH = original_shared_path
            settings_module.LOCAL_RUNTIME_CONFIG_PATH = original_local_path

    if effective["ENABLE_CONVERTIBLE_MONITOR"] is not False:
        print("❌ Runtime Local Override: local bool override not applied")
        return False
    if effective["ENABLE_SENTIMENT_MONITOR"] is not True:
        print("❌ Runtime Local Override: shared value should remain when local missing")
        return False
    if effective["METALS_CRUISE_INTERVAL_MINUTES"] != 21:
        print("❌ Runtime Local Override: local interval override not applied")
        return False

    logger.info("runtime_config_local_override_ok")
    print("✅ Runtime Config Local Override: OK")
    return True


def test_futures_dual_threshold_trigger():
    """测试期指贴水率阈值和年化贴水率阈值必须同时触发才报警。"""
    logger.info("test_futures_dual_threshold_trigger_start")

    from models.market_data import FuturesData
    from strategies.futures_strategy import FuturesDiscountStrategy
    import utils.futures_config as futures_config

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
                        "backwardation_enabled": True,
                        "backwardation_threshold": 1.0,
                        "annualized_backwardation_threshold": 20.0,
                        "contango_enabled": True,
                        "contango_threshold": 1.0,
                        "annualized_contango_threshold": 20.0,
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
            strategy = FuturesDiscountStrategy()
            percent_only = strategy.evaluate(
                [
                    FuturesData(
                        symbol="IF2604",
                        timestamp=datetime.now(),
                        price=3500,
                        spot_price=3540,
                        discount_rate=1.2,
                        product_code="IF",
                        days_to_maturity=40,
                    )
                ]
            )
            annualized_only = strategy.evaluate(
                [
                    FuturesData(
                        symbol="IC2606",
                        timestamp=datetime.now(),
                        price=5100,
                        spot_price=5120,
                        discount_rate=0.4,
                        product_code="IC",
                        days_to_maturity=5,
                    )
                ]
            )
            none_triggered = strategy.evaluate(
                [
                    FuturesData(
                        symbol="IH2604",
                        timestamp=datetime.now(),
                        price=2400,
                        spot_price=2410,
                        discount_rate=0.2,
                        product_code="IH",
                        days_to_maturity=20,
                    )
                ]
            )
            both_triggered = strategy.evaluate(
                [
                    FuturesData(
                        symbol="IM2604",
                        timestamp=datetime.now(),
                        price=5200,
                        spot_price=5300,
                        discount_rate=2.2,
                        product_code="IM",
                        days_to_maturity=20,
                    )
                ]
            )
        finally:
            futures_config.get_futures_thresholds_path = original_shared_path_fn
            futures_config.get_local_futures_thresholds_path = original_local_path_fn
            futures_config._threshold_cache = original_cache

    if percent_only:
        print(f"❌ Futures Dual Threshold: percent-only sample should not trigger, got {len(percent_only)}")
        return False
    if annualized_only:
        print(f"❌ Futures Dual Threshold: annualized-only sample should not trigger, got {len(annualized_only)}")
        return False
    if none_triggered:
        print("❌ Futures Dual Threshold: non-triggering sample should not alert")
        return False
    if len(both_triggered) != 1:
        print(f"❌ Futures Dual Threshold: expected dual trigger, got {len(both_triggered)}")
        return False
    if "同时满足" not in both_triggered[0].message:
        print("❌ Futures Dual Threshold: signal message missing dual-threshold wording")
        return False
    if "普通贴水阈值" not in both_triggered[0].message or "年化贴水阈值" not in both_triggered[0].message:
        print("❌ Futures Dual Threshold: signal message missing threshold detail")
        return False

    logger.info("futures_dual_threshold_trigger_ok")
    print("✅ Futures Dual Threshold: OK")
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
        "ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD": settings.ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD,
        "ENABLE_SENTIMENT_PULSE_THRESHOLD": settings.ENABLE_SENTIMENT_PULSE_THRESHOLD,
    }

    try:
        settings.apply_updates(
            {
                "ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD": True,
                "ENABLE_SENTIMENT_PULSE_THRESHOLD": True,
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
    import utils.futures_config as futures_config

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


def test_alert_history_latest_only():
    """测试同一 asset 只保留最新一条报警记录。"""
    logger.info("test_alert_history_latest_only_start")

    from models.signals import Signal

    db = DBManager()
    asset = "LATEST_ONLY_TEST"
    with db.get_connection() as conn:
        conn.execute("DELETE FROM alert_history WHERE asset = ?", (asset,))
        conn.commit()

    first_id = db.save_signal(
        Signal(
            asset=asset,
            strategy_name="Strategy_A",
            level="WARNING",
            message="first",
        )
    )
    second_id = db.save_signal(
        Signal(
            asset=asset,
            strategy_name="Strategy_B",
            level="CRITICAL",
            message="second",
        )
    )

    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT id, strategy, message FROM alert_history WHERE asset = ? ORDER BY id DESC",
            (asset,),
        ).fetchall()
        conn.execute("DELETE FROM alert_history WHERE asset = ?", (asset,))
        conn.commit()

    if len(rows) != 1:
        print(f"❌ Alert Latest Only: expected 1 row, got {len(rows)}")
        return False
    if rows[0][0] != second_id or rows[0][1] != "Strategy_B" or rows[0][2] != "second":
        print(f"❌ Alert Latest Only: latest row mismatch {rows}")
        return False
    if first_id == second_id:
        print("❌ Alert Latest Only: expected new insert id for replacement row")
        return False

    logger.info("alert_history_latest_only_ok", alert_id=second_id)
    print("✅ Alert History Latest Only: OK")
    return True


def test_snapshot_deduplication():
    """测试高频快照分钟去重与变化更新。"""
    logger.info("test_snapshot_deduplication_start")

    from models.market_data import (
        CBData,
        FuturesData,
        MetalArbitrageData,
        PremiumArbitrageData,
        SentimentData,
    )

    db = DBManager()
    base_ts = datetime.now().replace(second=5, microsecond=0)
    later_same_minute = base_ts.replace(second=35)

    futures_a = FuturesData(
        symbol="DEDUP_IF",
        timestamp=base_ts,
        price=3500,
        spot_price=3510,
        discount_rate=1.0,
        product_code="IF",
        margin_ratio=12.0,
        days_to_maturity=10,
    )
    futures_b = FuturesData(
        symbol="DEDUP_IF",
        timestamp=later_same_minute,
        price=3501,
        spot_price=3510,
        discount_rate=1.1,
        product_code="IF",
        margin_ratio=12.0,
        days_to_maturity=10,
    )
    db.save_futures_live_snapshots([futures_a])
    db.save_futures_live_snapshots([futures_b])

    metal_a = MetalArbitrageData(
        symbol="DEDUP_AU:GC",
        timestamp=base_ts,
        metal_symbol="AU0",
        metal_name="黄金",
        benchmark_symbol="GC",
        benchmark_name="COMEX黄金",
        benchmark_display_name="COMEX GC",
        domestic_symbol="au0",
        domestic_name="沪金主力",
        domestic_unit="元/克",
        category="precious",
        dom_price=700,
        for_price_usd=2400,
        for_price_cny=699,
        exchange_rate=7.2,
        implied_rate=7.18,
        spread=1,
        spread_pct=0.14,
    )
    metal_b = MetalArbitrageData(
        symbol="DEDUP_AU:GC",
        timestamp=later_same_minute,
        metal_symbol="AU0",
        metal_name="黄金",
        benchmark_symbol="GC",
        benchmark_name="COMEX黄金",
        benchmark_display_name="COMEX GC",
        domestic_symbol="au0",
        domestic_name="沪金主力",
        domestic_unit="元/克",
        category="precious",
        dom_price=701,
        for_price_usd=2400,
        for_price_cny=700,
        exchange_rate=7.2,
        implied_rate=7.18,
        spread=1,
        spread_pct=0.15,
    )
    db.save_metal_snapshots([metal_a])
    db.save_metal_snapshots([metal_b])

    premium_a = PremiumArbitrageData(
        symbol="DEDUP_BTC:BTC=F",
        timestamp=base_ts,
        asset_group="BTC",
        spot_symbol="BTC-USD",
        spot_name="BTC现货",
        spot_price=68000,
        future_symbol="BTC=F",
        future_name="BTC期货",
        future_price=68100,
        premium=100,
        premium_rate=0.147,
        state="contango",
        source_spot="fixture",
        source_future="fixture",
    )
    premium_b = PremiumArbitrageData(
        symbol="DEDUP_BTC:BTC=F",
        timestamp=later_same_minute,
        asset_group="BTC",
        spot_symbol="BTC-USD",
        spot_name="BTC现货",
        spot_price=68010,
        future_symbol="BTC=F",
        future_name="BTC期货",
        future_price=68120,
        premium=110,
        premium_rate=0.162,
        state="contango",
        source_spot="fixture",
        source_future="fixture",
    )
    db.save_premium_snapshots([premium_a])
    db.save_premium_snapshots([premium_b])

    cb_a = CBData(
        symbol="DEDUP_CB",
        timestamp=base_ts,
        premium_rate=12.3,
        double_low=110.3,
        price=98.0,
        ytm=1.23,
        bond_code="110000",
        bond_name="测试转债",
        listing_status="listed",
        is_listed=True,
        is_delisted=False,
    )
    cb_b = CBData(
        symbol="DEDUP_CB",
        timestamp=later_same_minute,
        premium_rate=12.1,
        double_low=109.9,
        price=98.5,
        ytm=1.25,
        bond_code="110000",
        bond_name="测试转债",
        listing_status="listed",
        is_listed=True,
        is_delisted=False,
    )
    db.save_convertible_snapshots([cb_a])
    db.save_convertible_snapshots([cb_b])

    sentiment_a = SentimentData(
        symbol="SZ000001",
        timestamp=base_ts,
        name="平安银行",
        hot_score=900,
        sentiment_pulse=5.0,
        rank=3,
    )
    sentiment_b = SentimentData(
        symbol="SZ000001",
        timestamp=later_same_minute,
        name="平安银行",
        hot_score=930,
        sentiment_pulse=6.0,
        rank=2,
    )
    db.save_sentiment_snapshots([sentiment_a])
    db.save_sentiment_snapshots([sentiment_b])

    with db.get_connection() as conn:
        futures_rows = conn.execute(
            "SELECT COUNT(*), MAX(price), MAX(discount_rate) FROM futures_live_snapshot WHERE symbol = 'DEDUP_IF'"
        ).fetchone()
        metal_rows = conn.execute(
            "SELECT COUNT(*), MAX(dom_price), MAX(spread_pct) FROM metal_arbitrage_snapshot WHERE symbol = 'DEDUP_AU:GC'"
        ).fetchone()
        premium_rows = conn.execute(
            "SELECT COUNT(*), MAX(future_price), MAX(premium_rate) FROM premium_arbitrage_snapshot WHERE symbol = 'DEDUP_BTC:BTC=F'"
        ).fetchone()
        cb_rows = conn.execute(
            "SELECT COUNT(*), MAX(price), MAX(double_low) FROM convertible_live_snapshot WHERE symbol = 'DEDUP_CB'"
        ).fetchone()
        sentiment_rows = conn.execute(
            "SELECT COUNT(*), MAX(hot_score), MIN(rank) FROM sentiment_live_snapshot WHERE symbol = 'SZ000001'"
        ).fetchone()
        conn.execute("DELETE FROM futures_live_snapshot WHERE symbol = 'DEDUP_IF'")
        conn.execute("DELETE FROM metal_arbitrage_snapshot WHERE symbol = 'DEDUP_AU:GC'")
        conn.execute("DELETE FROM premium_arbitrage_snapshot WHERE symbol = 'DEDUP_BTC:BTC=F'")
        conn.execute("DELETE FROM convertible_live_snapshot WHERE symbol = 'DEDUP_CB'")
        conn.execute("DELETE FROM sentiment_live_snapshot WHERE symbol = 'SZ000001'")
        conn.commit()

    if futures_rows[0] != 1 or float(futures_rows[1]) != 3501 or float(futures_rows[2]) != 1.1:
        print(f"❌ Snapshot Deduplication: futures rows mismatch {futures_rows}")
        return False
    if metal_rows[0] != 1 or float(metal_rows[1]) != 701 or float(metal_rows[2]) != 0.15:
        print(f"❌ Snapshot Deduplication: metal rows mismatch {metal_rows}")
        return False
    if premium_rows[0] != 1 or float(premium_rows[1]) != 68120 or float(premium_rows[2]) != 0.162:
        print(f"❌ Snapshot Deduplication: premium rows mismatch {premium_rows}")
        return False
    if cb_rows[0] != 1 or float(cb_rows[1]) != 98.5 or float(cb_rows[2]) != 109.9:
        print(f"❌ Snapshot Deduplication: convertible rows mismatch {cb_rows}")
        return False
    if sentiment_rows[0] != 1 or int(sentiment_rows[1]) != 930 or int(sentiment_rows[2]) != 2:
        print(f"❌ Snapshot Deduplication: sentiment rows mismatch {sentiment_rows}")
        return False

    logger.info("snapshot_deduplication_ok")
    print("✅ Snapshot Deduplication: OK")
    return True


def test_latest_snapshot_readers():
    """测试最新快照读取接口只返回每个标的最新一条。"""
    logger.info("test_latest_snapshot_readers_start")

    from models.market_data import (
        CBData,
        FuturesData,
        MetalArbitrageData,
        PremiumArbitrageData,
        SentimentData,
    )

    db = DBManager()
    ts_old = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=20)
    ts_new = ts_old + timedelta(minutes=16)

    db.save_futures_live_snapshots(
        [
            FuturesData(
                symbol="LATEST_IF",
                timestamp=ts_old,
                price=3500,
                spot_price=3510,
                discount_rate=1.0,
                product_code="IF",
                margin_ratio=12.0,
                days_to_maturity=10,
            ),
            FuturesData(
                symbol="LATEST_IF",
                timestamp=ts_new,
                price=3510,
                spot_price=3520,
                discount_rate=0.8,
                product_code="IF",
                margin_ratio=12.0,
                days_to_maturity=9,
            ),
        ]
    )
    db.save_metal_snapshots(
        [
            MetalArbitrageData(
                symbol="LATEST_AU:GC",
                timestamp=ts_old,
                metal_symbol="AU0",
                metal_name="黄金",
                benchmark_symbol="GC",
                benchmark_name="COMEX黄金",
                benchmark_display_name="COMEX GC",
                domestic_symbol="au0",
                domestic_name="沪金主力",
                domestic_unit="元/克",
                category="precious",
                dom_price=700,
                for_price_usd=2400,
                for_price_cny=699,
                exchange_rate=7.2,
                implied_rate=7.18,
                spread=1,
                spread_pct=0.14,
            ),
            MetalArbitrageData(
                symbol="LATEST_AU:GC",
                timestamp=ts_new,
                metal_symbol="AU0",
                metal_name="黄金",
                benchmark_symbol="GC",
                benchmark_name="COMEX黄金",
                benchmark_display_name="COMEX GC",
                domestic_symbol="au0",
                domestic_name="沪金主力",
                domestic_unit="元/克",
                category="precious",
                dom_price=702,
                for_price_usd=2405,
                for_price_cny=701,
                exchange_rate=7.2,
                implied_rate=7.18,
                spread=1,
                spread_pct=0.15,
            ),
        ]
    )
    db.save_premium_snapshots(
        [
            PremiumArbitrageData(
                symbol="LATEST_BTC",
                timestamp=ts_old,
                asset_group="BTC",
                spot_symbol="BTC-USD",
                spot_name="BTC现货",
                spot_price=68000,
                future_symbol="BTC=F",
                future_name="BTC期货",
                future_price=68100,
                premium=100,
                premium_rate=0.147,
                state="contango",
                source_spot="fixture",
                source_future="fixture",
            ),
            PremiumArbitrageData(
                symbol="LATEST_BTC",
                timestamp=ts_new,
                asset_group="BTC",
                spot_symbol="BTC-USD",
                spot_name="BTC现货",
                spot_price=68050,
                future_symbol="BTC=F",
                future_name="BTC期货",
                future_price=68160,
                premium=110,
                premium_rate=0.161,
                state="contango",
                source_spot="fixture",
                source_future="fixture",
            ),
        ]
    )
    db.save_convertible_snapshots(
        [
            CBData(
                symbol="LATEST_CB",
                timestamp=ts_old,
                premium_rate=13.0,
                double_low=111.0,
                price=99.0,
                ytm=1.1,
                bond_code="113000",
                bond_name="最新转债",
                listing_status="listed",
                is_listed=True,
                is_delisted=False,
            ),
            CBData(
                symbol="LATEST_CB",
                timestamp=ts_new,
                premium_rate=12.8,
                double_low=110.8,
                price=99.5,
                ytm=1.2,
                bond_code="113000",
                bond_name="最新转债",
                listing_status="listed",
                is_listed=True,
                is_delisted=False,
            ),
        ]
    )
    db.save_sentiment_snapshots(
        [
            SentimentData(
                symbol="SH600519",
                timestamp=ts_old,
                name="贵州茅台",
                hot_score=800,
                sentiment_pulse=2.0,
                rank=10,
            ),
            SentimentData(
                symbol="SH600519",
                timestamp=ts_new,
                name="贵州茅台",
                hot_score=850,
                sentiment_pulse=3.0,
                rank=6,
            ),
        ]
    )

    futures = db.get_latest_futures_live_snapshots()
    metals = db.get_latest_metal_snapshots()
    premiums = db.get_latest_premium_snapshots()
    convertibles = db.get_latest_convertible_snapshots()
    sentiments = db.get_latest_sentiment_snapshots()

    with db.get_connection() as conn:
        conn.execute("DELETE FROM futures_live_snapshot WHERE symbol = 'LATEST_IF'")
        conn.execute("DELETE FROM metal_arbitrage_snapshot WHERE symbol = 'LATEST_AU:GC'")
        conn.execute("DELETE FROM premium_arbitrage_snapshot WHERE symbol = 'LATEST_BTC'")
        conn.execute("DELETE FROM convertible_live_snapshot WHERE symbol = 'LATEST_CB'")
        conn.execute("DELETE FROM sentiment_live_snapshot WHERE symbol = 'SH600519'")
        conn.commit()

    futures_match = any(item.symbol == "LATEST_IF" and float(item.price) == 3510 for item in futures)
    metals_match = any(item.symbol == "LATEST_AU:GC" and float(item.dom_price) == 702 for item in metals)
    premium_match = any(item.symbol == "LATEST_BTC" and float(item.future_price) == 68160 for item in premiums)
    cb_match = any(item.symbol == "LATEST_CB" and float(item.price) == 99.5 for item in convertibles)
    sentiment_match = any(item.symbol == "SH600519" and int(item.rank) == 6 for item in sentiments)

    if not futures_match:
        print("❌ Latest Snapshot Readers: futures latest row mismatch")
        return False
    if not metals_match:
        print("❌ Latest Snapshot Readers: metals latest row mismatch")
        return False
    if not premium_match:
        print("❌ Latest Snapshot Readers: premium latest row mismatch")
        return False
    if not cb_match:
        print("❌ Latest Snapshot Readers: convertible latest row mismatch")
        return False
    if not sentiment_match:
        print("❌ Latest Snapshot Readers: sentiment latest row mismatch")
        return False

    logger.info("latest_snapshot_readers_ok")
    print("✅ Latest Snapshot Readers: OK")
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


def test_dashboard_table_ordering():
    """测试期指和金属主表的固定排序与前置列顺序。"""
    logger.info("test_dashboard_table_ordering_start")

    from models.market_data import FuturesData, MetalArbitrageData, PremiumArbitrageData
    from utils.dashboard_tables import (
        FUTURES_FRONT_COLUMNS,
        METALS_FRONT_COLUMNS,
        PREMIUM_FRONT_COLUMNS,
        build_futures_live_tables,
        build_metals_live_tables,
        build_premium_live_tables,
    )

    futures_data = [
        FuturesData(symbol="IC2606", timestamp=datetime.now(), price=1, spot_price=2, discount_rate=0.5, product_code="IC", days_to_maturity=20),
        FuturesData(symbol="IH2604", timestamp=datetime.now(), price=1, spot_price=2, discount_rate=0.5, product_code="IH", days_to_maturity=5),
        FuturesData(symbol="IF2605", timestamp=datetime.now(), price=1, spot_price=2, discount_rate=0.5, product_code="IF", days_to_maturity=10),
        FuturesData(symbol="IM2603", timestamp=datetime.now(), price=1, spot_price=2, discount_rate=0.5, product_code="IM", days_to_maturity=1),
        FuturesData(symbol="IH2606", timestamp=datetime.now(), price=1, spot_price=2, discount_rate=0.5, product_code="IH", days_to_maturity=30),
    ]
    futures_df, _ = build_futures_live_tables(futures_data, [])
    expected_futures_order = ["IH2604", "IH2606", "IF2605", "IC2606", "IM2603"]
    if futures_df["名称"].tolist() != expected_futures_order:
        print(f"❌ Dashboard Ordering: unexpected futures order {futures_df['名称'].tolist()}")
        return False
    if futures_df.columns[: len(FUTURES_FRONT_COLUMNS)].tolist() != FUTURES_FRONT_COLUMNS:
        print("❌ Dashboard Ordering: futures front columns mismatch")
        return False

    metals_data = [
        MetalArbitrageData(symbol="CU0:CAD", timestamp=datetime.now(), metal_symbol="CU0", metal_name="铜", benchmark_symbol="CAD", benchmark_name="LME铜3个月", benchmark_display_name="LME铜", domestic_symbol="cu0", domestic_name="沪铜主力", domestic_unit="元/吨", category="base", dom_price=1, for_price_usd=1, for_price_cny=1, exchange_rate=1, implied_rate=1, spread=1, spread_pct=1),
        MetalArbitrageData(symbol="AU0:GC", timestamp=datetime.now(), metal_symbol="AU0", metal_name="黄金", benchmark_symbol="GC", benchmark_name="COMEX黄金", benchmark_display_name="COMEX GC", domestic_symbol="au0", domestic_name="沪金主力", domestic_unit="元/克", category="precious", dom_price=1, for_price_usd=1, for_price_cny=1, exchange_rate=1, implied_rate=1, spread=1, spread_pct=1),
        MetalArbitrageData(symbol="AG0:SI", timestamp=datetime.now(), metal_symbol="AG0", metal_name="白银", benchmark_symbol="SI", benchmark_name="COMEX白银", benchmark_display_name="COMEX SI", domestic_symbol="ag0", domestic_name="沪银主力", domestic_unit="元/千克", category="precious", dom_price=1, for_price_usd=1, for_price_cny=1, exchange_rate=1, implied_rate=1, spread=1, spread_pct=1),
        MetalArbitrageData(symbol="PT0:XPT", timestamp=datetime.now(), metal_symbol="PT0", metal_name="铂金", benchmark_symbol="XPT", benchmark_name="伦敦铂", benchmark_display_name="LME铂", domestic_symbol="pt0", domestic_name="沪铂主力", domestic_unit="元/克", category="precious", dom_price=1, for_price_usd=1, for_price_cny=1, exchange_rate=1, implied_rate=1, spread=1, spread_pct=1),
    ]
    metals_df, _ = build_metals_live_tables(metals_data, [])
    expected_metals_order = ["黄金", "白银", "铂金", "铜"]
    if metals_df["品种名称"].tolist() != expected_metals_order:
        print(f"❌ Dashboard Ordering: unexpected metals order {metals_df['品种名称'].tolist()}")
        return False
    if metals_df.columns[: len(METALS_FRONT_COLUMNS)].tolist() != METALS_FRONT_COLUMNS:
        print("❌ Dashboard Ordering: metals front columns mismatch")
        return False

    premium_data = [
        PremiumArbitrageData(symbol="A50:CN00Y", timestamp=datetime.now(), asset_group="A50", spot_symbol="XIN9.FGI", spot_name="A50现货", spot_price=14529.54, future_symbol="CN00Y", future_name="A50期指当月连续", future_price=14422.0, premium=-107.54, premium_rate=-0.74, state="backwardation", contract_bucket="A50", contract_type="future", bucket_rank=10, source_exchange="A50", source_spot="fixture", source_future="fixture"),
        PremiumArbitrageData(symbol="BTC:BTC_USDT", timestamp=datetime.now(), asset_group="BTC", spot_symbol="BTC_USDT", spot_name="BTC现货", spot_price=68102.59, future_symbol="BTC_USDT", future_name="BTC永续", future_price=68025.0, premium=-77.59, premium_rate=-0.11, state="backwardation", contract_bucket="PERP", contract_type="swap", bucket_rank=0, source_exchange="Gate", source_spot="fixture", source_future="fixture"),
        PremiumArbitrageData(symbol="ETH:ETH_USDT_20260626", timestamp=datetime.now(), asset_group="ETH", spot_symbol="ETH_USDT", spot_name="ETH现货", spot_price=2332.72, future_symbol="ETH_USDT_20260626", future_name="ETH近季", future_price=2350.18, premium=17.46, premium_rate=0.75, state="contango", contract_bucket="QUARTERLY_CURRENT", contract_type="future", expiry_ts="2026-06-26T00:00:00", bucket_rank=3, source_exchange="Gate", days_to_maturity=68, source_spot="fixture", source_future="fixture"),
    ]
    premium_df, _ = build_premium_live_tables(premium_data, [])
    if premium_df["资产组"].tolist() != ["BTC", "ETH", "A50"]:
        print(f"❌ Dashboard Ordering: unexpected premium order {premium_df['资产组'].tolist()}")
        return False
    if premium_df.columns[: len(PREMIUM_FRONT_COLUMNS)].tolist() != PREMIUM_FRONT_COLUMNS:
        print("❌ Dashboard Ordering: premium front columns mismatch")
        return False

    logger.info("dashboard_table_ordering_ok")
    print("✅ Dashboard Table Ordering: OK")
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
        "LISTING_DATE": "2026-03-18 00:00:00",
        "DELIST_DATE": None,
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


def test_convertible_status_filter():
    """测试可转债只保留已上市且未退市的记录。"""
    logger.info("test_convertible_status_filter_start")

    from fetchers.ak_convertible import ConvertibleFetcher

    fetcher = ConvertibleFetcher()
    listed = fetcher._build_cbdata_from_eastmoney_row(
        {
            "SECURITY_CODE": "123001",
            "SECURITY_NAME_ABBR": "测试转债A",
            "CURRENT_BOND_PRICENEW": 100,
            "TRANSFER_VALUE": 101,
            "TRANSFER_PREMIUM_RATIO": -1.0,
            "LISTING_DATE": "2025-01-01 00:00:00",
            "DELIST_DATE": None,
            "BOND_START_DATE": "2024-01-01 00:00:00",
            "INTEREST_RATE_EXPLAIN": "第一年为0.2%、第二年为0.4%。",
            "REDEEM_CLAUSE": "到期按债券面值的110%赎回。",
        }
    )
    unlisted = fetcher._build_cbdata_from_eastmoney_row(
        {
            "SECURITY_CODE": "123002",
            "SECURITY_NAME_ABBR": "测试转债B",
            "CURRENT_BOND_PRICENEW": 100,
            "TRANSFER_VALUE": 101,
            "TRANSFER_PREMIUM_RATIO": -1.0,
            "LISTING_DATE": "2099-01-01 00:00:00",
            "DELIST_DATE": None,
            "BOND_START_DATE": "2024-01-01 00:00:00",
            "INTEREST_RATE_EXPLAIN": "第一年为0.2%、第二年为0.4%。",
            "REDEEM_CLAUSE": "到期按债券面值的110%赎回。",
        }
    )
    delisted = fetcher._build_cbdata_from_eastmoney_row(
        {
            "SECURITY_CODE": "123003",
            "SECURITY_NAME_ABBR": "测试转债C",
            "CURRENT_BOND_PRICENEW": 100,
            "TRANSFER_VALUE": 101,
            "TRANSFER_PREMIUM_RATIO": -1.0,
            "LISTING_DATE": "2020-01-01 00:00:00",
            "DELIST_DATE": "2025-01-01 00:00:00",
            "BOND_START_DATE": "2024-01-01 00:00:00",
            "INTEREST_RATE_EXPLAIN": "第一年为0.2%、第二年为0.4%。",
            "REDEEM_CLAUSE": "到期按债券面值的110%赎回。",
        }
    )

    if listed is None or not listed.is_listed or listed.is_delisted:
        print("❌ Convertible Status Filter: listed bond should be kept")
        return False
    if unlisted is not None:
        print("❌ Convertible Status Filter: unlisted bond should be filtered")
        return False
    if delisted is not None:
        print("❌ Convertible Status Filter: delisted bond should be filtered")
        return False

    logger.info("convertible_status_filter_ok")
    print("✅ Convertible Status Filter: OK")
    return True


def test_sentiment_name_lookup():
    """测试舆情抓取结果会补股票名称。"""
    logger.info("test_sentiment_name_lookup_start")

    from fetchers.sentiment_spider import SentimentFetcher

    fetcher = SentimentFetcher()

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"sc": "SZ002361", "rk": 1, "rc": 2, "hisRc": 1}]}

    original_post = fetcher.client.post
    original_name_lookup = fetcher._fetch_stock_name_map
    try:
        fetcher.client.post = lambda *args, **kwargs: DummyResponse()
        fetcher._fetch_stock_name_map = lambda codes: {"SZ002361": "神剑股份"}
        data = fetcher.fetch_live()
    finally:
        fetcher.client.post = original_post
        fetcher._fetch_stock_name_map = original_name_lookup

    if not data or data[0].name != "神剑股份":
        print(f"❌ Sentiment Name Lookup: unexpected data {data}")
        return False

    logger.info("sentiment_name_lookup_ok", name=data[0].name)
    print("✅ Sentiment Name Lookup: OK")
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
    original_local_path_fn = metals_config.get_local_metals_thresholds_path
    original_legacy_path_fn = metals_config.get_legacy_metals_thresholds_path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        new_path = temp_root / "config" / "metals_thresholds.json"
        local_path = temp_root / "config" / "metals_thresholds.local.json"
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
        metals_config.get_local_metals_thresholds_path = lambda: local_path
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

            migrated = json.loads(local_path.read_text(encoding="utf-8"))
            if migrated["AG0"]["upper"] != 8.0 or migrated["AG0"]["lower"] != -8.0:
                print(f"❌ Metals Migration: AG0 not migrated correctly {migrated['AG0']}")
                return False
            if "REMOVED_SYMBOL" in migrated:
                print("❌ Metals Migration: removed symbol should not be kept")
                return False
            effective = metals_config.load_metals_thresholds(force_reload=True)
            if "PT0" not in effective:
                print("❌ Metals Migration: effective thresholds should still include new symbols")
                return False
        finally:
            metals_config.get_metals_thresholds_path = original_new_path_fn
            metals_config.get_local_metals_thresholds_path = original_local_path_fn
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
    original_local_path_fn = metals_config.get_local_metals_thresholds_path
    original_legacy_path_fn = metals_config.get_legacy_metals_thresholds_path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        new_path = temp_root / "config" / "metals_thresholds.json"
        local_path = temp_root / "config" / "metals_thresholds.local.json"
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
        metals_config.get_local_metals_thresholds_path = lambda: local_path
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
            metals_config.get_local_metals_thresholds_path = original_local_path_fn
            metals_config.get_legacy_metals_thresholds_path = original_legacy_path_fn
            metals_config._threshold_cache = None

    logger.info("current_metals_threshold_file_compatibility_ok")
    print("✅ Current Metals Threshold File Compatibility: OK")
    return True


def test_metals_threshold_local_override():
    """测试本机金属阈值 local 文件优先于仓库共享基线。"""
    logger.info("test_metals_threshold_local_override_start")

    from pathlib import Path
    import utils.metals_config as metals_config

    original_new_path_fn = metals_config.get_metals_thresholds_path
    original_local_path_fn = metals_config.get_local_metals_thresholds_path
    original_legacy_path_fn = metals_config.get_legacy_metals_thresholds_path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        shared_path = temp_root / "config" / "metals_thresholds.json"
        local_path = temp_root / "config" / "metals_thresholds.local.json"
        legacy_path = temp_root / "data" / "metals_thresholds.json"
        shared_path.parent.mkdir(parents=True, exist_ok=True)

        shared_path.write_text(
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
        local_path.write_text(
            json.dumps(
                {
                    "AG0": {"upper": 20.0, "lower": -20.0},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        metals_config.get_metals_thresholds_path = lambda: shared_path
        metals_config.get_local_metals_thresholds_path = lambda: local_path
        metals_config.get_legacy_metals_thresholds_path = lambda: legacy_path
        metals_config._threshold_cache = None

        try:
            effective = metals_config.load_metals_thresholds(force_reload=True)
        finally:
            metals_config.get_metals_thresholds_path = original_new_path_fn
            metals_config.get_local_metals_thresholds_path = original_local_path_fn
            metals_config.get_legacy_metals_thresholds_path = original_legacy_path_fn
            metals_config._threshold_cache = None

    if effective["AG0"]["upper"] != 20.0 or effective["AG0"]["lower"] != -20.0:
        print(f"❌ Metals Local Override: local AG0 override missing {effective['AG0']}")
        return False
    if effective["AU0"]["upper"] != 1.0 or effective["AU0"]["lower"] != -1.0:
        print(f"❌ Metals Local Override: shared AU0 baseline missing {effective['AU0']}")
        return False

    logger.info("metals_threshold_local_override_ok")
    print("✅ Metals Threshold Local Override: OK")
    return True


def test_futures_threshold_local_override():
    """测试期指分品种阈值支持共享基线叠加本机 local 覆盖。"""
    logger.info("test_futures_threshold_local_override_start")

    import utils.futures_config as futures_config

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
                    "IH": {
                        "backwardation_enabled": False,
                        "backwardation_threshold": 1.0,
                        "annualized_backwardation_threshold": 8.0,
                        "contango_enabled": False,
                        "contango_threshold": 1.0,
                        "annualized_contango_threshold": 8.0,
                    },
                    "IF": {
                        "backwardation_enabled": True,
                        "backwardation_threshold": 1.2,
                        "annualized_backwardation_threshold": 8.5,
                        "contango_enabled": True,
                        "contango_threshold": 1.2,
                        "annualized_contango_threshold": 8.5,
                    },
                    "IC": {
                        "backwardation_enabled": True,
                        "backwardation_threshold": 1.3,
                        "annualized_backwardation_threshold": 9.0,
                        "contango_enabled": True,
                        "contango_threshold": 1.3,
                        "annualized_contango_threshold": 9.0,
                    },
                    "IM": {
                        "backwardation_enabled": True,
                        "backwardation_threshold": 1.4,
                        "annualized_backwardation_threshold": 9.5,
                        "contango_enabled": True,
                        "contango_threshold": 1.4,
                        "annualized_contango_threshold": 9.5,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        local_path.write_text(
            json.dumps(
                {
                    "IF": {
                        "backwardation_enabled": False,
                        "backwardation_threshold": 2.2,
                        "annualized_backwardation_threshold": 12.5,
                        "contango_enabled": False,
                        "contango_threshold": 2.2,
                        "annualized_contango_threshold": 12.5,
                    }
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
            effective = futures_config.load_futures_thresholds(force_reload=True)
        finally:
            futures_config.get_futures_thresholds_path = original_shared_path_fn
            futures_config.get_local_futures_thresholds_path = original_local_path_fn
            futures_config._threshold_cache = original_cache

    if effective["IF"]["backwardation_enabled"] is not False:
        print("❌ Futures Threshold Local Override: local enabled override not applied")
        return False
    if float(effective["IF"]["backwardation_threshold"]) != 2.2:
        print("❌ Futures Threshold Local Override: local percent threshold not applied")
        return False
    if float(effective["IH"]["annualized_backwardation_threshold"]) != 8.0:
        print("❌ Futures Threshold Local Override: shared value should remain when local missing")
        return False

    logger.info("futures_threshold_local_override_ok")
    print("✅ Futures Threshold Local Override: OK")
    return True


def test_source_health_tracking():
    """测试数据源健康度记录。"""
    logger.info("test_source_health_tracking_start")

    from utils.source_health import record_source_health

    db = DBManager()
    source_name = f"test_source_health_{datetime.now().timestamp()}"
    try:
        record_source_health(source_name, success=False, duration_ms=120, error_summary="boom")
        record_source_health(
            source_name,
            success=True,
            duration_ms=80,
            active_source="fallback",
            is_fallback=True,
        )
        rows = [row for row in db.get_source_health_statuses() if row[0] == source_name]
        if len(rows) != 1:
            print("❌ Source Health: missing recorded row")
            return False
        row = rows[0]
        if row[3] != 0 or row[7] <= 0 or row[10] != "fallback" or row[11] != 1:
            print(f"❌ Source Health: unexpected row state {row}")
            return False
    finally:
        with db.get_connection() as conn:
            conn.execute("DELETE FROM source_health_status WHERE source_name = ?", (source_name,))
            conn.commit()

    logger.info("source_health_tracking_ok")
    print("✅ Source Health Tracking: OK")
    return True


def test_config_audit_history():
    """测试配置审计记录。"""
    logger.info("test_config_audit_history_start")

    from utils.config_audit import record_config_changes

    db = DBManager()
    key = f"TEST_CONFIG_{datetime.now().timestamp()}"
    try:
        changed = record_config_changes(
            {key: "old"},
            {key: "new"},
            source="dashboard_gui",
            destination="local_override",
        )
        if changed != 1:
            print(f"❌ Config Audit: expected 1 changed row, got {changed}")
            return False
        rows = [row for row in db.get_recent_config_changes(limit=20) if row[1] == key]
        if not rows:
            print("❌ Config Audit: missing persisted audit row")
            return False
        if rows[0][4] != "dashboard_gui" or rows[0][5] != "local_override":
            print(f"❌ Config Audit: unexpected source/destination {rows[0]}")
            return False
    finally:
        with db.get_connection() as conn:
            conn.execute("DELETE FROM config_change_history WHERE config_key = ?", (key,))
            conn.commit()

    logger.info("config_audit_history_ok")
    print("✅ Config Audit History: OK")
    return True


def test_job_run_status_tracking():
    """测试任务运行状态记录。"""
    logger.info("test_job_run_status_tracking_start")

    db = DBManager()
    job_name = f"test_job_status_{datetime.now().timestamp()}"
    started_at = datetime.now().isoformat()
    try:
        db.mark_job_started(job_name, started_at)
        db.mark_job_skipped(job_name)
        db.mark_job_finished(
            job_name,
            finished_at=datetime.now().isoformat(),
            status="SUCCESS",
            duration_ms=123.0,
        )
        rows = [row for row in db.get_job_run_statuses() if row[0] == job_name]
        if not rows:
            print("❌ Job Status: missing job row")
            return False
        row = rows[0]
        if row[1] != 0 or row[5] != "SUCCESS" or row[7] < 1:
            print(f"❌ Job Status: unexpected row {row}")
            return False
    finally:
        with db.get_connection() as conn:
            conn.execute("DELETE FROM job_run_status WHERE job_name = ?", (job_name,))
            conn.commit()

    logger.info("job_run_status_tracking_ok")
    print("✅ Job Run Status Tracking: OK")
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
    import utils.futures_config as futures_config

    db = DBManager()
    deliveries: list[tuple[str, dict[str, Any]]] = []
    original_post_json = notifier._post_json
    original_feishu = settings.FEISHU_WEBHOOK_URL
    original_wecom = settings.WECOM_WEBHOOK_URL
    original_shared_path_fn = futures_config.get_futures_thresholds_path
    original_local_path_fn = futures_config.get_local_futures_thresholds_path
    original_cache = futures_config._threshold_cache

    def fake_post_json(url: str, payload: dict[str, Any]):
        deliveries.append((url, payload))

        class DummyResponse:
            def raise_for_status(self):
                return None

        return DummyResponse()

    settings.FEISHU_WEBHOOK_URL = "https://example.com/feishu"
    settings.WECOM_WEBHOOK_URL = "https://example.com/wecom"
    notifier._post_json = fake_post_json

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        shared_path = temp_root / "config" / "futures_thresholds.json"
        local_path = temp_root / "config" / "futures_thresholds.local.json"
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        shared_path.write_text(
            json.dumps(
                {
                    product: {
                        "backwardation_enabled": True,
                        "backwardation_threshold": 0.2,
                        "annualized_backwardation_threshold": 3.0,
                        "contango_enabled": True,
                        "contango_threshold": 0.2,
                        "annualized_contango_threshold": 3.0,
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
            data = futures_fetcher.fetch_from_fixture("tests/fixtures/futures_sample.json")
            strategy = FuturesDiscountStrategy()
            signals = strategy.evaluate(data)
            if not signals:
                print("❌ Full Pipeline: expected at least one signal")
                return False
            alert_ids: list[int] = []
            for signal in signals:
                signal.alert_id = db.save_signal(signal)
                alert_ids.append(signal.alert_id)
                notifier.send(signal)

            notifier.flush()
        finally:
            futures_config.get_futures_thresholds_path = original_shared_path_fn
            futures_config.get_local_futures_thresholds_path = original_local_path_fn
            futures_config._threshold_cache = original_cache
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

    from models.market_data import (
        CBData,
        FuturesData,
        FuturesMarginData,
        MetalArbitrageData,
        PremiumArbitrageData,
        SentimentData,
    )

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
    db.save_premium_snapshots(
        [
            PremiumArbitrageData(
                symbol="RETENTION_BTC_OLD",
                timestamp=old_ts,
                asset_group="BTC",
                spot_symbol="BTC-USD",
                spot_name="BTC现货",
                spot_price=68000,
                future_symbol="BTC=F",
                future_name="BTC期货",
                future_price=68100,
                premium=100,
                premium_rate=0.147,
                state="contango",
                source_spot="retention_old",
                source_future="retention_old",
            ),
            PremiumArbitrageData(
                symbol="RETENTION_A50_NEW",
                timestamp=new_ts,
                asset_group="A50",
                spot_symbol="XIN9.FGI",
                spot_name="A50现货",
                spot_price=14529.54,
                future_symbol="CN00Y",
                future_name="A50期指当月连续",
                future_price=14422.0,
                premium=-107.54,
                premium_rate=-0.74,
                state="backwardation",
                source_spot="retention_new",
                source_future="retention_new",
            ),
        ]
    )
    db.save_convertible_snapshots(
        [
            CBData(
                symbol="RETENTION_CB_OLD",
                timestamp=old_ts,
                premium_rate=15.0,
                double_low=115.0,
                price=100.0,
                ytm=1.0,
                bond_code="110001",
                bond_name="旧转债",
                listing_status="listed",
                is_listed=True,
                is_delisted=False,
            ),
            CBData(
                symbol="RETENTION_CB_NEW",
                timestamp=new_ts,
                premium_rate=10.0,
                double_low=108.0,
                price=101.0,
                ytm=1.2,
                bond_code="110002",
                bond_name="新转债",
                listing_status="listed",
                is_listed=True,
                is_delisted=False,
            ),
        ]
    )
    db.save_sentiment_snapshots(
        [
            SentimentData(
                symbol="RETENTION_SENTIMENT_OLD",
                timestamp=old_ts,
                name="旧情绪",
                hot_score=500,
                sentiment_pulse=1.0,
                rank=50,
            ),
            SentimentData(
                symbol="RETENTION_SENTIMENT_NEW",
                timestamp=new_ts,
                name="新情绪",
                hot_score=700,
                sentiment_pulse=5.0,
                rank=8,
            ),
        ]
    )

    deleted_alerts = db.purge_alert_history_older_than(30)
    deleted_margins = db.purge_futures_margin_snapshots_older_than(30)
    deleted_futures = db.purge_futures_live_snapshots_older_than(30)
    deleted_convertibles = db.purge_convertible_snapshots_older_than(30)
    deleted_sentiments = db.purge_sentiment_snapshots_older_than(30)
    deleted_metals = db.purge_metal_snapshots_older_than(30)
    deleted_premium = db.purge_premium_snapshots_older_than(30)

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
        old_premium_count = conn.execute(
            "SELECT COUNT(*) FROM premium_arbitrage_snapshot WHERE symbol = 'RETENTION_BTC_OLD'"
        ).fetchone()[0]
        new_premium_count = conn.execute(
            "SELECT COUNT(*) FROM premium_arbitrage_snapshot WHERE symbol = 'RETENTION_A50_NEW'"
        ).fetchone()[0]
        old_convertible_count = conn.execute(
            "SELECT COUNT(*) FROM convertible_live_snapshot WHERE symbol = 'RETENTION_CB_OLD'"
        ).fetchone()[0]
        new_convertible_count = conn.execute(
            "SELECT COUNT(*) FROM convertible_live_snapshot WHERE symbol = 'RETENTION_CB_NEW'"
        ).fetchone()[0]
        old_sentiment_count = conn.execute(
            "SELECT COUNT(*) FROM sentiment_live_snapshot WHERE symbol = 'RETENTION_SENTIMENT_OLD'"
        ).fetchone()[0]
        new_sentiment_count = conn.execute(
            "SELECT COUNT(*) FROM sentiment_live_snapshot WHERE symbol = 'RETENTION_SENTIMENT_NEW'"
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
        conn.execute("DELETE FROM premium_arbitrage_snapshot WHERE symbol = 'RETENTION_A50_NEW'")
        conn.execute("DELETE FROM convertible_live_snapshot WHERE symbol = 'RETENTION_CB_NEW'")
        conn.execute(
            "DELETE FROM sentiment_live_snapshot WHERE symbol = 'RETENTION_SENTIMENT_NEW'"
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
    if deleted_premium < 1 or old_premium_count != 0 or new_premium_count != 1:
        print(
            "❌ Retention Cleanup: premium snapshot cleanup mismatch "
            f"(deleted={deleted_premium}, old={old_premium_count}, new={new_premium_count})"
        )
        return False
    if (
        deleted_convertibles < 1
        or old_convertible_count != 0
        or new_convertible_count != 1
    ):
        print(
            "❌ Retention Cleanup: convertible snapshot cleanup mismatch "
            f"(deleted={deleted_convertibles}, old={old_convertible_count}, new={new_convertible_count})"
        )
        return False
    if deleted_sentiments < 1 or old_sentiment_count != 0 or new_sentiment_count != 1:
        print(
            "❌ Retention Cleanup: sentiment snapshot cleanup mismatch "
            f"(deleted={deleted_sentiments}, old={old_sentiment_count}, new={new_sentiment_count})"
        )
        return False

    logger.info(
        "retention_cleanup_ok",
        deleted_alerts=deleted_alerts,
        deleted_margins=deleted_margins,
        deleted_futures=deleted_futures,
        deleted_convertibles=deleted_convertibles,
        deleted_sentiments=deleted_sentiments,
        deleted_metals=deleted_metals,
        deleted_premium=deleted_premium,
    )
    print("✅ Retention Cleanup: OK")
    return True


def test_premium_threshold_local_override():
    """测试 premium 阈值 local override 优先级。"""
    logger.info("test_premium_threshold_local_override_start")

    import utils.premium_config as premium_config

    original_shared_path_fn = premium_config.get_premium_thresholds_path
    original_local_path_fn = premium_config.get_local_premium_thresholds_path
    original_cache = premium_config._threshold_cache

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        shared_path = temp_root / "config" / "premium_thresholds.json"
        local_path = temp_root / "config" / "premium_thresholds.local.json"
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        shared_path.write_text(
            json.dumps(
                {
                    "BTC_PERP": {
                        "contango_threshold": 0.5,
                        "backwardation_threshold": 0.5,
                        "contango_enabled": True,
                        "backwardation_enabled": True,
                    },
                    "A50": {
                        "contango_threshold": 0.5,
                        "backwardation_threshold": 0.5,
                        "contango_enabled": True,
                        "backwardation_enabled": True,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        local_path.write_text(
            json.dumps(
                {
                    "BTC_PERP": {
                        "contango_threshold": 1.2,
                        "backwardation_threshold": 1.0,
                        "contango_enabled": True,
                        "backwardation_enabled": False,
                    }
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        premium_config.get_premium_thresholds_path = lambda: shared_path
        premium_config.get_local_premium_thresholds_path = lambda: local_path
        premium_config._threshold_cache = None

        try:
            btc = premium_config.get_effective_premium_threshold("BTC", "PERP")
            a50 = premium_config.get_effective_premium_threshold("A50")
        finally:
            premium_config.get_premium_thresholds_path = original_shared_path_fn
            premium_config.get_local_premium_thresholds_path = original_local_path_fn
            premium_config._threshold_cache = original_cache

    if float(btc["contango_threshold"]) != 1.2 or bool(btc["backwardation_enabled"]) is not False:
        print(f"❌ Premium Threshold Override: BTC override mismatch {btc}")
        return False
    if float(a50["contango_threshold"]) != 0.5 or float(a50["backwardation_threshold"]) != 0.5:
        print(f"❌ Premium Threshold Override: A50 shared fallback mismatch {a50}")
        return False

    logger.info("premium_threshold_local_override_ok")
    print("✅ Premium Threshold Local Override: OK")
    return True


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


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🧪 套利监控系统 - 端到端集成测试")
    print("=" * 60 + "\n")

    tests = [
        ("Database Manager", test_db_manager),
        ("Notifier", test_notifier),
        ("Runtime Config Writer", test_runtime_config_writer),
        ("Runtime Config Local Override", test_runtime_config_local_override),
        ("Futures Dual Threshold", test_futures_dual_threshold_trigger),
        ("Strategy Hot Reload", test_strategy_threshold_hot_reload),
        ("Strategy Enable Switches", test_strategy_enable_switches),
        ("Mode Enable Switches", test_mode_enable_switches),
        ("Threshold Enable Switches", test_threshold_enable_switches),
        ("Alert History Latest Only", test_alert_history_latest_only),
        ("Snapshot Deduplication", test_snapshot_deduplication),
        ("Latest Snapshot Readers", test_latest_snapshot_readers),
        ("Scheduler Runtime Sync", test_scheduler_runtime_settings_sync),
        ("Cooldown Restore", test_cooldown_restore_roundtrip),
        ("Retention Cleanup", test_retention_cleanup),
        ("Fetchers (Mock)", test_fetchers_mock),
        ("Strategies", test_strategies),
        ("Metals Conversion", test_metals_conversion_and_thresholds),
        ("Dashboard Table Ordering", test_dashboard_table_ordering),
        ("Legacy Metals Migration", test_legacy_metals_threshold_migration),
        ("Current Metals Config Compatibility", test_current_metals_threshold_file_compatibility),
        ("Metals Threshold Local Override", test_metals_threshold_local_override),
        ("Futures Threshold Local Override", test_futures_threshold_local_override),
        ("Premium Threshold Local Override", test_premium_threshold_local_override),
        ("Source Health Tracking", test_source_health_tracking),
        ("Config Audit History", test_config_audit_history),
        ("Job Run Status Tracking", test_job_run_status_tracking),
        ("Convertible Fallback", test_convertible_fallback_estimation),
        ("Convertible Status Filter", test_convertible_status_filter),
        ("Sentiment Name Lookup", test_sentiment_name_lookup),
        ("Futures Margin", test_futures_margin_enrichment),
        ("Active Contracts", test_active_futures_contract_generation),
        ("Spot Index Fallback", test_spot_index_fallback_parser),
        ("Module Schedule Windows", test_module_schedule_windows),
        ("Premium Module Integration", test_premium_module_integration),
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
