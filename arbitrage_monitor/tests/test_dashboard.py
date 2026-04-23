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

def test_dashboard_table_ordering():
    """测试期指和金属主表的固定排序与前置列顺序。"""
    logger.info("test_dashboard_table_ordering_start")

    from models.market_data import FuturesData, MetalArbitrageData, PremiumArbitrageData
    from dashboard.tables import (
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

