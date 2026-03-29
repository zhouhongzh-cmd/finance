import json
import os
import re
from datetime import datetime, date
from typing import List, Optional, Tuple
import akshare as ak
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from models.market_data import FuturesData
from fetchers.futures_margin import futures_margin_fetcher
from utils.logger import logger
from utils.source_health import source_health_context


def get_third_friday(year: int, month: int) -> date:
    """计算指定年月的第三个周五（A股股指期货法定交割日）"""
    first_day = date(year, month, 1)
    # weekday(): 周一=0 ... 周五=4
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday_day = 1 + days_until_friday
    third_friday_day = first_friday_day + 14
    return date(year, month, third_friday_day)


INDEX_NAME_MAP = {
    "000300": "沪深300",
    "000016": "上证50",
    "000905": "中证500",
    "000852": "中证1000",
}

SINA_INDEX_CODE_MAP = {
    "000300": "sh000300",
    "000016": "sh000016",
    "000905": "sh000905",
    "000852": "sz399852",
}


def get_active_contracts(today: Optional[date] = None) -> List[Tuple[str, str, int]]:
    """
    动态生成当前所有正在交易的期指合约列表。
    A股股指期货同时交易 4 个合约：当月、下月、当季、下季。
    返回: [(合约符号, 对应现货指数代码, 剩余交割天数), ...]
    """
    today = today or date.today()

    # 四大期指及对应现货指数代码
    index_pairs = [
        ("IF", "000300"),   # 沪深300
        ("IH", "000016"),   # 上证50
        ("IC", "000905"),   # 中证500
        ("IM", "000852"),   # 中证1000
    ]

    # 生成未来 9 个月内的候选合约月份
    candidate_months: List[Tuple[int, int]] = []
    y, m = today.year, today.month
    for _ in range(9):
        candidate_months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    # 中金所股指期货实际挂牌规则：
    # 当月、下月，以及之后最近的两个季月。
    # 如果当前月本身就是季月，不能因为去重而少掉“下下个季月”。
    front_months = candidate_months[:2]
    quarterly = [
        cm for cm in candidate_months
        if cm[1] in (3, 6, 9, 12) and cm not in front_months
    ]
    active_months = front_months + quarterly[:2]

    results = []
    for idx_sym, spot_sym in index_pairs:
        for cy, cm in active_months:
            delivery = get_third_friday(cy, cm)
            days_to_maturity = (delivery - today).days

            # 若该合约已经过了交割日则跳过
            if days_to_maturity < 0:
                continue

            # 合约符号格式：IF2503, IC2506, ...
            contract_sym = f"{idx_sym}{str(cy)[2:]}{cm:02d}"
            results.append((contract_sym, spot_sym, days_to_maturity))

    return results


class FuturesFetcher:
    """期指行情获取器"""

    def _fetch_spot_index_prices(self) -> dict[str, float]:
        """优先使用 AKShare，失败时直连新浪指数接口。"""
        try:
            with source_health_context("futures_spot_index_eastmoney"):
                spot_df = ak.stock_zh_index_spot_em()
            return {
                str(code): float(price)
                for code, price in spot_df[["代码", "最新价"]].itertuples(index=False)
                if str(code) in INDEX_NAME_MAP and price not in ("-", None)
            }
        except Exception as exc:
            logger.warning("spot_index_primary_failed", error=str(exc))
            fallback = self._fetch_spot_index_prices_from_sina()
            if fallback:
                logger.info("spot_index_fallback_used", source="sina_hq", count=len(fallback))
                return fallback
            raise

    def _fetch_spot_index_prices_from_sina(self) -> dict[str, float]:
        codes = ",".join(SINA_INDEX_CODE_MAP.values())
        url = f"https://hq.sinajs.cn/list={codes}"
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
            ),
        }
        with source_health_context(
            "futures_spot_index_sina", active_source="fallback", is_fallback=True
        ):
            with httpx.Client(headers=headers, timeout=10.0, trust_env=False) as client:
                response = client.get(url)
                response.raise_for_status()
                return self._parse_sina_index_response(response.text)

    def _parse_sina_index_response(self, text: str) -> dict[str, float]:
        prices: dict[str, float] = {}
        reverse_map = {value: key for key, value in SINA_INDEX_CODE_MAP.items()}
        pattern = re.compile(r'var hq_str_(\w+)="([^"]*)";')

        for market_code, payload in pattern.findall(text):
            if market_code not in reverse_map:
                continue
            parts = payload.split(",")
            if len(parts) < 4:
                continue
            latest_raw = parts[3].strip()
            if not latest_raw or latest_raw == "0":
                continue
            try:
                prices[reverse_map[market_code]] = float(latest_raw)
            except ValueError:
                continue

        return prices

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=8))
    def fetch_live(self) -> List[FuturesData]:
        """
        生产模式：获取所有正在交易的期指合约行情（当月、下月、当季、下季）。
        每个合约依据其真实交割日动态计算 days_to_maturity，用于准确年化贴水率。
        """
        logger.info("fetch_futures_live_start")
        results = []

        # 一次性拉取现货指数数据（失败时让异常抛出以触发 tenacity 重试）
        spot_dict = self._fetch_spot_index_prices()

        contracts = get_active_contracts()
        logger.info("futures_contracts_to_fetch", count=len(contracts))

        for contract_sym, spot_sym, days_to_maturity in contracts:
            try:
                with source_health_context("futures_quote_ff_spot"):
                    future_df = ak.futures_zh_spot(symbol=contract_sym, market="FF", adjust="0")
                if future_df.empty:
                    logger.warning("futures_empty_response", symbol=contract_sym)
                    continue

                future_price = float(future_df["current_price"].iloc[0])
                spot_price = float(spot_dict.get(spot_sym, 0.0))

                if spot_price == 0.0 or future_price == 0.0:
                    continue

                discount_rate = (spot_price - future_price) / spot_price * 100
                product_code = contract_sym[:2]
                multiplier = futures_margin_fetcher.get_contract_multiplier(product_code)
                margin_ratio = futures_margin_fetcher.get_latest_margin_ratio(product_code)
                notional_per_lot = future_price * multiplier
                margin_required_per_lot = notional_per_lot * margin_ratio / 100

                results.append(FuturesData(
                    symbol=contract_sym,
                    timestamp=datetime.now(),
                    price=future_price,
                    spot_price=spot_price,
                    discount_rate=discount_rate,
                    product_code=product_code,
                    contract_multiplier=multiplier,
                    margin_ratio=margin_ratio,
                    notional_per_lot=notional_per_lot,
                    margin_required_per_lot=margin_required_per_lot,
                    days_to_maturity=days_to_maturity,
                ))

            except Exception as e:
                logger.warning("fetch_single_future_failed", symbol=contract_sym, error=str(e))

        logger.info("fetch_futures_live_success", count=len(results))
        return results

    def fetch_from_fixture(self, path: str = "tests/fixtures/futures_sample.json") -> List[FuturesData]:
        """
        开发模式：读取本地样本数据，零网络请求，防反爬。
        Fixture JSON 字段: symbol, last_price, spot_price, days_to_maturity(可选,默认15)
        """
        logger.debug("fetch_futures_from_fixture", path=path)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(base_dir, path)

        with open(full_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        results = []
        for item in raw_data:
            future_price = item["last_price"]
            spot_price = item["spot_price"]
            discount_rate = (spot_price - future_price) / spot_price * 100
            days_to_maturity = item.get("days_to_maturity", 15)  # fixture 支持自定义，兜底15天
            product_code = item["symbol"][:2]
            multiplier = futures_margin_fetcher.get_contract_multiplier(product_code)
            margin_ratio = item.get(
                "margin_ratio", futures_margin_fetcher.get_latest_margin_ratio(product_code)
            )
            notional_per_lot = future_price * multiplier
            margin_required_per_lot = notional_per_lot * margin_ratio / 100

            results.append(FuturesData(
                symbol=item["symbol"],
                timestamp=datetime.now(),
                price=future_price,
                spot_price=spot_price,
                discount_rate=discount_rate,
                product_code=product_code,
                contract_multiplier=multiplier,
                margin_ratio=margin_ratio,
                notional_per_lot=notional_per_lot,
                margin_required_per_lot=margin_required_per_lot,
                days_to_maturity=days_to_maturity,
            ))

        return results


# 单例供调度器调用
futures_fetcher = FuturesFetcher()
