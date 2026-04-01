import json
import os
import httpx
import akshare as ak
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
        self._name_cache: dict[str, str] = {}

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

        stock_codes = [item.get("sc", "UNKNOWN") for item in items]
        name_map = self._fetch_stock_name_map(stock_codes)

        results = []
        for item in items:
            stock_code = item.get("sc", "UNKNOWN")
            rank = item.get("rk", 0)
            rank_change = item.get("rc", 0)  # 排名变化（正=上升，负=下降）
            his_rank_change = item.get("hisRc", 0)
            stock_name = name_map.get(stock_code, stock_code)

            results.append(
                SentimentData(
                    symbol=stock_code,
                    timestamp=datetime.now(),
                    name=stock_name,
                    hot_score=max(0, 1000 - rank * 30),  # 根据排名推算热度分
                    sentiment_pulse=float(rank_change),  # 用排名变化量作为情绪脉冲
                    rank=rank,
                )
            )

        logger.info("fetch_sentiment_live_success", count=len(results), source="eastmoney")
        return results

    def _fetch_stock_name_map(self, codes: List[str]) -> dict[str, str]:
        normalized_codes = [str(code or "").strip() for code in codes if str(code or "").strip()]
        missing_codes = [code for code in normalized_codes if code not in self._name_cache]
        if missing_codes:
            try:
                self._fetch_stock_name_map_primary(missing_codes)
            except Exception as exc:
                logger.warning("sentiment_name_lookup_failed", error=str(exc))
                self._fetch_stock_name_map_fallback(missing_codes)
        return {code: self._name_cache.get(code, code) for code in normalized_codes}

    def _fetch_stock_name_map_primary(self, missing_codes: List[str]) -> None:
        secids = []
        for code in missing_codes:
            pure_code = code[2:] if code.startswith(("SZ", "SH", "BJ")) else code
            market = "1" if pure_code.startswith(("6", "9")) else "0"
            secid = f"{market}.{pure_code}"
            secids.append(secid)
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
        params = {
            "fltt": "2",
            "invt": "2",
            "fields": "f12,f14",
            "secids": ",".join(secids),
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        }
        with source_health_context("sentiment_eastmoney_names"):
            resp = self.client.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
        rows = ((payload.get("data") or {}).get("diff") or [])
        for row in rows:
            code = str(row.get("f12") or "").strip()
            name = str(row.get("f14") or "").strip()
            if code and name:
                self._store_name_mapping(code, name)

    def _fetch_stock_name_map_fallback(self, missing_codes: List[str]) -> None:
        if self._fetch_stock_name_map_from_sina(missing_codes):
            return
        self._fetch_stock_name_map_from_akshare(missing_codes)

    def _fetch_stock_name_map_from_sina(self, missing_codes: List[str]) -> bool:
        symbols = []
        for code in missing_codes:
            pure_code = code[2:] if code.startswith(("SZ", "SH", "BJ")) else code
            if pure_code.startswith(("6", "9")):
                symbols.append(f"sh{pure_code}")
            elif pure_code.startswith(("0", "3")):
                symbols.append(f"sz{pure_code}")
            elif pure_code.startswith(("4", "8")):
                symbols.append(f"bj{pure_code}")
        if not symbols:
            return False

        url = "https://hq.sinajs.cn/list=" + ",".join(symbols)
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0",
        }
        try:
            with source_health_context("sentiment_name_fallback_sina"):
                resp = self.client.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
            lines = [line.strip() for line in resp.text.splitlines() if line.strip()]
        except Exception as exc:
            logger.warning("sentiment_name_lookup_sina_failed", error=str(exc))
            return False

        success = False
        for line in lines:
            if "=\"" not in line:
                continue
            prefix, payload = line.split("=\"", 1)
            payload = payload.rstrip('";')
            symbol = prefix.replace("var hq_str_", "").strip()
            if not payload:
                continue
            parts = payload.split(",")
            if not parts:
                continue
            name = parts[0].strip()
            if not name:
                continue
            code = symbol[2:].upper()
            self._store_name_mapping(code, name)
            success = True
        return success

    def _fetch_stock_name_map_from_akshare(self, missing_codes: List[str]) -> None:
        try:
            with source_health_context("sentiment_name_fallback_akshare"):
                df = ak.stock_zh_a_spot_em()
        except Exception as exc:
            logger.warning("sentiment_name_lookup_fallback_failed", error=str(exc))
            return

        if df.empty or "代码" not in df.columns or "名称" not in df.columns:
            return

        wanted = {code[2:] if code.startswith(("SZ", "SH", "BJ")) else code: code for code in missing_codes}
        matched = df[df["代码"].astype(str).isin(wanted.keys())][["代码", "名称"]]
        for _, row in matched.iterrows():
            code = str(row["代码"]).strip()
            name = str(row["名称"]).strip()
            if code and name:
                self._store_name_mapping(code, name)

    def _store_name_mapping(self, code: str, name: str) -> None:
        if code.startswith(("0", "3")):
            prefixed = f"SZ{code}"
        elif code.startswith(("6", "9")):
            prefixed = f"SH{code}"
        elif code.startswith(("4", "8")):
            prefixed = f"BJ{code}"
        else:
            prefixed = code
        self._name_cache[prefixed] = name
        self._name_cache[code] = name

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
