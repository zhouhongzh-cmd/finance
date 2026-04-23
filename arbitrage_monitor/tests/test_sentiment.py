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

