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

def test_full_pipeline():
    """测试完整链路"""
    logger.info("test_full_pipeline_start")

    from fetchers.ak_futures import futures_fetcher
    from strategies.futures_strategy import FuturesDiscountStrategy
    from config.settings import settings
    import config.futures_thresholds as futures_config

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

