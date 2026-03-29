import re
from datetime import datetime
from io import StringIO
from typing import Dict, List, Optional

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from models.market_data import FuturesMarginData
from utils.db_manager import DBManager
from utils.logger import logger
from utils.source_health import source_health_context


PRODUCT_SPECS: Dict[str, Dict[str, object]] = {
    "IF": {
        "name": "沪深300股指期货",
        "urls": [
            "https://www.cffex.com.cn/hs300/",
            "https://www.cffex.com.cn/en_new/CSI300.html",
        ],
        "fallback_margin_ratio": 8.0,
        "contract_multiplier": 300,
    },
    "IH": {
        "name": "上证50股指期货",
        "urls": [
            "https://www.cffex.com.cn/sz50/",
            "https://www.cffex.com.cn/en_new/SSE50.html",
        ],
        "fallback_margin_ratio": 8.0,
        "contract_multiplier": 300,
    },
    "IC": {
        "name": "中证500股指期货",
        "urls": [
            "https://www.cffex.com.cn/zz500/",
            "https://www.cffex.com.cn/en_new/CSI500.html",
        ],
        "fallback_margin_ratio": 8.0,
        "contract_multiplier": 200,
    },
    "IM": {
        "name": "中证1000股指期货",
        "urls": [
            "https://www.cffex.com.cn/zz1000/",
            "https://www.cffex.com.cn/en_new/CSI1000IndexFutures.html",
        ],
        "fallback_margin_ratio": 8.0,
        "contract_multiplier": 200,
    },
}

CICC_MARGIN_LIST_URL = "https://www.ciccwmf.cn/bzjjzdtb.jhtml"
CICC_MARGIN_URL_PREFIX = "https://www.ciccwmf.cn"
CICC_PRODUCT_NAME_MAP = {
    "IF": "沪深300期货IF",
    "IH": "上证50期货IH",
    "IC": "中证500期货IC",
    "IM": "中证1000期货IM",
}


class FuturesMarginFetcher:
    """抓取并缓存股指期货保证金比例。"""

    def __init__(self, db_manager: Optional[DBManager] = None):
        self.db_manager = db_manager or DBManager()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=8))
    def fetch_live(self) -> List[FuturesMarginData]:
        fetched_at = datetime.now()
        snapshots: List[FuturesMarginData] = []
        secondary_ratios = self._load_cicc_secondary_ratios(fetched_at)

        logger.info("fetch_futures_margin_start")
        for product_code, spec in PRODUCT_SPECS.items():
            snapshot = self._fetch_single_product(
                product_code, spec, fetched_at, secondary_ratios
            )
            snapshots.append(snapshot)

        self.db_manager.save_futures_margin_snapshots(snapshots)
        logger.info("fetch_futures_margin_success", count=len(snapshots))
        return snapshots

    def get_latest_margin_ratio(self, product_code: str) -> float:
        latest = self.db_manager.get_latest_futures_margin(product_code)
        if latest is not None:
            return latest.margin_ratio
        return self.get_default_margin_ratio(product_code)

    def get_default_margin_ratio(self, product_code: str) -> float:
        spec = PRODUCT_SPECS.get(product_code, {})
        return float(spec.get("fallback_margin_ratio", 0.0))

    def get_contract_multiplier(self, product_code: str) -> int:
        spec = PRODUCT_SPECS.get(product_code, {})
        return int(spec.get("contract_multiplier", 0))

    def _fetch_single_product(
        self,
        product_code: str,
        spec: Dict[str, object],
        fetched_at: datetime,
        secondary_ratios: Dict[str, tuple[float, str]],
    ) -> FuturesMarginData:
        notes: List[str] = []
        for url in spec["urls"]:
            try:
                source_key = "futures_margin_cffex_product_page"
                with source_health_context(source_key):
                    html = self._fetch_text(str(url))
                ratio = self._extract_margin_ratio(html)
                if ratio is not None:
                    logger.info(
                        "futures_margin_parsed",
                        product_code=product_code,
                        margin_ratio=ratio,
                        source_url=url,
                    )
                    return FuturesMarginData(
                        symbol=product_code,
                        timestamp=fetched_at,
                        margin_ratio=ratio,
                        source="cffex_product_page",
                        source_url=str(url),
                    )
                notes.append(f"parse_failed:{url}")
            except Exception as exc:
                logger.warning(
                    "futures_margin_fetch_failed",
                    product_code=product_code,
                    source_url=url,
                    error=str(exc),
                )
                notes.append(f"fetch_failed:{url}:{exc}")

        if product_code in secondary_ratios:
            ratio, source_url = secondary_ratios[product_code]
            return FuturesMarginData(
                symbol=product_code,
                timestamp=fetched_at,
                margin_ratio=ratio,
                source="ciccwmf_daily_margin_bulletin",
                source_url=source_url,
                notes="; ".join(notes)[:500],
            )

        fallback = float(spec["fallback_margin_ratio"])
        return FuturesMarginData(
            symbol=product_code,
            timestamp=fetched_at,
            margin_ratio=fallback,
            source="fallback_default",
            source_url=str(spec["urls"][0]),
            notes="; ".join(notes)[:500],
        )

    def _fetch_text(self, url: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
            )
        }
        with httpx.Client(
            headers=headers, follow_redirects=True, timeout=3.0, trust_env=False
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text

    def _extract_margin_ratio(self, raw_text: str) -> Optional[float]:
        text = re.sub(r"(?is)<script.*?</script>", " ", raw_text)
        text = re.sub(r"(?is)<style.*?</style>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)

        patterns = [
            r"交易保证金标准[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*%",
            r"保证金标准[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*%",
            r"Minimum Trading Margin[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*%",
            r"Trading Margin[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*%",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    def _load_cicc_secondary_ratios(self, fetched_at: datetime) -> Dict[str, tuple[float, str]]:
        try:
            with source_health_context(
                "futures_margin_cicc_bulletin", active_source="fallback", is_fallback=True
            ):
                list_html = self._fetch_text(CICC_MARGIN_LIST_URL)
            detail_url = self._extract_latest_cicc_detail_url(list_html)
            if detail_url is None:
                return {}

            with source_health_context(
                "futures_margin_cicc_detail", active_source="fallback", is_fallback=True
            ):
                detail_html = self._fetch_text(detail_url)
            ratios = self._extract_cicc_margin_ratios(detail_html)
            for product_code, ratio in ratios.items():
                logger.info(
                    "futures_margin_parsed_secondary",
                    product_code=product_code,
                    margin_ratio=ratio,
                    source_url=detail_url,
                    fetched_at=fetched_at.isoformat(),
                )
            return {product_code: (ratio, detail_url) for product_code, ratio in ratios.items()}
        except Exception as exc:
            logger.warning("futures_margin_secondary_failed", error=str(exc))
            return {}

    def _extract_latest_cicc_detail_url(self, html: str) -> Optional[str]:
        matches = re.findall(r'href="(/bzjjzdtb/\d+\.jhtml)"', html)
        if not matches:
            return None
        return f"{CICC_MARGIN_URL_PREFIX}{matches[0]}"

    def _extract_cicc_margin_ratios(self, html: str) -> Dict[str, float]:
        tables = pd.read_html(StringIO(html))
        ratios: Dict[str, float] = {}

        for table in tables:
            for row in table.itertuples(index=False):
                cells = [str(cell).strip() for cell in row]
                for product_code, target_name in CICC_PRODUCT_NAME_MAP.items():
                    if target_name not in cells or product_code in ratios:
                        continue
                    for cell in cells:
                        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)%", cell)
                        if match:
                            ratios[product_code] = float(match.group(1))
                            break
        return ratios


futures_margin_fetcher = FuturesMarginFetcher()
