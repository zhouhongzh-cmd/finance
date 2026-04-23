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

