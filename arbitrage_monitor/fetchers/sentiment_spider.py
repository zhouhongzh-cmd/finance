import json
import os
import httpx
from typing import List
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential
from models.market_data import SentimentData  # 已迁移至 models 层，统一架构
from config.settings import settings
from utils.logger import logger
from utils.source_health import source_health_context


class SentimentFetcher:
    """舆情/人气数据获取器（主：东方财富人气榜，备：雪球热股）"""

    def __init__(self):
        self.client = httpx.Client(timeout=15.0)

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=8)
    )
    def fetch_live(self) -> List[SentimentData]:
        """
        从东方财富人气榜 API 获取热门股票排名数据。
        该接口免费、无需认证，稳定性远高于雪球。
        """
        logger.info("fetch_sentiment_live_start", source="eastmoney")

        url = "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
        payload = {
            "appId": "appId01",
            "globalId": "786e4c21-70dc-435a-93bb-38",
            "marketType": "",
            "pageNo": 1,
            "pageSize": 30,
        }
        with source_health_context("sentiment_eastmoney"):
            resp = self.client.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        items = data.get("data", [])

        if not items:
            logger.warning("eastmoney_empty_response")
            return []

        results = []
        for item in items:
            stock_code = item.get("sc", "UNKNOWN")
            rank = item.get("rk", 0)
            rank_change = item.get("rc", 0)  # 排名变化（正=上升，负=下降）
            his_rank_change = item.get("hisRc", 0)

            results.append(
                SentimentData(
                    symbol=stock_code,
                    timestamp=datetime.now(),
                    name=stock_code,  # 东财 API 不返回名称，用代码代替
                    hot_score=max(0, 1000 - rank * 30),  # 根据排名推算热度分
                    sentiment_pulse=float(rank_change),  # 用排名变化量作为情绪脉冲
                    rank=rank,
                )
            )

        logger.info("fetch_sentiment_live_success", count=len(results), source="eastmoney")
        return results

    def fetch_from_fixture(self, path: str) -> List[SentimentData]:
        """从本地 fixture 读取数据进行开发与测试"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(base_dir, path) if not os.path.isabs(path) else path

        with open(full_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        results = []
        for item in raw_data:
            dt = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
            dt = dt.replace(tzinfo=None)
            results.append(
                SentimentData(
                    symbol=item["symbol"],
                    timestamp=dt,
                    name=item["name"],
                    hot_score=item["hot_score"],
                    sentiment_pulse=item["sentiment_pulse"],
                    rank=item["rank"],
                )
            )
        return results


sentiment_fetcher = SentimentFetcher()
