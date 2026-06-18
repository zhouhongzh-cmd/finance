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

def test_storage_maintenance_reclaims_freelist():
    """测试低频数据库维护可回收 SQLite 空闲页。"""
    logger.info("test_storage_maintenance_reclaims_freelist_start")

    db = DBManager()
    with db.get_connection() as conn:
        conn.execute("CREATE TABLE storage_maintenance_test (payload TEXT NOT NULL)")
        conn.executemany(
            "INSERT INTO storage_maintenance_test (payload) VALUES (?)",
            [("x" * 2048,) for _ in range(200)],
        )
        conn.commit()
        conn.execute("DROP TABLE storage_maintenance_test")
        conn.commit()
        freelist_before = int(conn.execute("PRAGMA freelist_count").fetchone()[0])

    stats = db.maintain_storage()

    with db.get_connection() as conn:
        freelist_after = int(conn.execute("PRAGMA freelist_count").fetchone()[0])

    if freelist_before <= 0:
        print(f"❌ Storage Maintenance: expected freelist before maintenance, got {freelist_before}")
        return False
    if stats["freelist_count_before"] <= 0 or stats["freelist_count_after"] != 0:
        print(f"❌ Storage Maintenance: unexpected maintenance stats {stats}")
        return False
    if freelist_after != 0:
        print(f"❌ Storage Maintenance: expected freelist after 0, got {freelist_after}")
        return False

    logger.info("storage_maintenance_reclaims_freelist_ok", **stats)
    print("✅ Storage Maintenance: OK")
    return True
