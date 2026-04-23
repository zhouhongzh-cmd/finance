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
                contract_bucket="PERP",
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
                contract_bucket="PERP",
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

