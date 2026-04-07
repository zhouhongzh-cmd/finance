from __future__ import annotations

import json
import os
from datetime import datetime
from calendar import monthrange
from typing import Any

import akshare as ak
import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from models.market_data import PremiumArbitrageData
from utils.logger import logger
from utils.source_health import source_health_context


class PremiumFetcher:
    """BTC 与 A50 期现溢价抓取器。"""

    A50_MONTH_CODES = {
        "F": 1,
        "G": 2,
        "H": 3,
        "J": 4,
        "K": 5,
        "M": 6,
        "N": 7,
        "Q": 8,
        "U": 9,
        "V": 10,
        "X": 11,
        "Z": 12,
        "Y": None,
    }

    def _fetch_yfinance_price(self, symbol: str, source_name: str) -> tuple[float | None, str]:
        price = None
        source = ""
        try:
            with source_health_context(source_name):
                ticker = yf.Ticker(symbol)

                fast_info = getattr(ticker, "fast_info", None)
                if fast_info is not None:
                    price = fast_info.get("lastPrice") or fast_info.get("regularMarketPrice")
                    if price is not None:
                        return float(price), "yfinance.fast_info"

                info = ticker.info
                price = (
                    info.get("regularMarketPrice")
                    or info.get("currentPrice")
                    or info.get("lastPrice")
                )
                if price is not None:
                    return float(price), "yfinance.info"

                hist = ticker.history(period="1d")
                if hist is not None and not hist.empty:
                    close_price = hist["Close"].iloc[-1]
                    if pd.notna(close_price):
                        return float(close_price), "yfinance.history_1d"
        except Exception as exc:
            logger.warning("premium_yfinance_fetch_failed", symbol=symbol, error=str(exc))
        return None, source

    def _fetch_btc_future_price(self) -> tuple[float | None, str, str, str]:
        try:
            with source_health_context("premium_btc_future_akshare"):
                df = ak.futures_foreign_commodity_realtime(symbol="BTC")
            if df is not None and not df.empty:
                row = df.iloc[0]
                raw_price = row.get("最新价")
                if raw_price is not None and not pd.isna(raw_price):
                    future_name = str(row.get("名称") or "CME比特币期货").strip()
                    return (
                        float(raw_price),
                        "akshare.futures_foreign_commodity_realtime",
                        "BTC",
                        future_name or "CME比特币期货",
                    )
        except Exception as exc:
            logger.warning("premium_btc_future_akshare_failed", error=str(exc))

        fallback_price, fallback_source = self._fetch_yfinance_price(
            "BTC=F", "premium_btc_future_yfinance"
        )
        if fallback_price is not None:
            return fallback_price, fallback_source, "BTC=F", "BTC期货"
        return None, "", "", ""

    def _build_snapshot(
        self,
        *,
        asset_group: str,
        spot_symbol: str,
        spot_name: str,
        spot_price: float,
        future_symbol: str,
        future_name: str,
        future_price: float,
        days_to_maturity: int | None,
        source_spot: str,
        source_future: str,
    ) -> PremiumArbitrageData:
        premium = future_price - spot_price
        premium_rate = (premium / spot_price * 100) if spot_price else 0.0
        state = "contango" if premium > 0 else "backwardation"
        return PremiumArbitrageData(
            symbol=f"{asset_group}:{future_symbol}",
            timestamp=datetime.now(),
            asset_group=asset_group,
            spot_symbol=spot_symbol,
            spot_name=spot_name,
            spot_price=spot_price,
            future_symbol=future_symbol,
            future_name=future_name,
            future_price=future_price,
            premium=premium,
            premium_rate=premium_rate,
            state=state,
            days_to_maturity=days_to_maturity,
            source_spot=source_spot,
            source_future=source_future,
        )

    def _estimate_days_to_maturity(self, future_symbol: str) -> int | None:
        code = (future_symbol or "").strip().upper()
        if not code.startswith("CN") or len(code) < 4:
            return None

        suffix = code[-1]
        month = self.A50_MONTH_CODES.get(suffix)
        now = datetime.now()
        if suffix == "Y":
            month = now.month
            year = now.year
        else:
            year_fragment = code[-3:-1]
            if not year_fragment.isdigit() or month is None:
                return None
            year = 2000 + int(year_fragment)

        last_day = monthrange(year, month)[1]
        expiry_date = datetime(year, month, last_day)
        delta = (expiry_date.date() - now.date()).days
        return max(delta, 0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=8))
    def fetch_live(self) -> list[PremiumArbitrageData]:
        results: list[PremiumArbitrageData] = []
        logger.info("fetch_premium_live_start")

        btc_spot, btc_spot_source = self._fetch_yfinance_price(
            "BTC-USD", "premium_btc_spot_yfinance"
        )
        btc_future, btc_future_source, btc_future_symbol, btc_future_name = self._fetch_btc_future_price()
        if btc_spot is not None and btc_future is not None:
            results.append(
                self._build_snapshot(
                    asset_group="BTC",
                    spot_symbol="BTC-USD",
                    spot_name="BTC现货",
                    spot_price=btc_spot,
                    future_symbol=btc_future_symbol or "BTC=F",
                    future_name=btc_future_name or "BTC期货",
                    future_price=btc_future,
                    days_to_maturity=None,
                    source_spot=btc_spot_source,
                    source_future=btc_future_source,
                )
            )
        else:
            logger.warning(
                "premium_btc_incomplete",
                has_spot=btc_spot is not None,
                has_future=btc_future is not None,
            )

        a50_spot, a50_spot_source = self._fetch_yfinance_price(
            "XIN9.FGI", "premium_a50_spot_yfinance"
        )
        if a50_spot is None:
            logger.warning("premium_a50_spot_missing")
            logger.info("fetch_premium_live_success", count=len(results))
            return results

        try:
            with source_health_context("premium_a50_futures_akshare"):
                df = ak.futures_global_spot_em()
            mask = df["名称"].astype(str).str.contains("A50", case=False, na=False)
            a50_futures = df[mask].copy()
            for _, row in a50_futures.iterrows():
                try:
                    raw_price = row.get("最新价") or row.get("last_price")
                    if raw_price in ("", None) or pd.isna(raw_price):
                        continue
                    future_price = float(raw_price)
                    future_symbol = str(row.get("代码") or row.get("symbol") or "").strip()
                    future_name = str(row.get("名称") or row.get("name") or future_symbol).strip()
                    if not future_symbol:
                        future_symbol = future_name
                    days_to_maturity = self._estimate_days_to_maturity(future_symbol)
                    results.append(
                        self._build_snapshot(
                            asset_group="A50",
                            spot_symbol="XIN9.FGI",
                            spot_name="A50现货",
                            spot_price=float(a50_spot),
                            future_symbol=future_symbol,
                            future_name=future_name,
                            future_price=future_price,
                            days_to_maturity=days_to_maturity,
                            source_spot=a50_spot_source,
                            source_future="akshare.futures_global_spot_em",
                        )
                    )
                except Exception as exc:
                    logger.warning("premium_a50_future_parse_failed", error=str(exc))
        except Exception as exc:
            logger.warning("premium_a50_futures_fetch_failed", error=str(exc))

        logger.info("fetch_premium_live_success", count=len(results))
        return results

    def fetch_from_fixture(
        self, path: str = "tests/fixtures/premium_sample.json"
    ) -> list[PremiumArbitrageData]:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(base_dir, path)
        with open(full_path, "r", encoding="utf-8") as file:
            raw_data = json.load(file)

        results: list[PremiumArbitrageData] = []
        for item in raw_data:
            spot_price = item.get("spot_price")
            future_price = item.get("future_price")
            if spot_price in ("", None) or future_price in ("", None):
                continue
            results.append(
                self._build_snapshot(
                    asset_group=str(item["asset_group"]).upper(),
                    spot_symbol=item["spot_symbol"],
                    spot_name=item.get("spot_name", item["spot_symbol"]),
                    spot_price=float(spot_price),
                    future_symbol=item["future_symbol"],
                    future_name=item.get("future_name", item["future_symbol"]),
                    future_price=float(future_price),
                    days_to_maturity=item.get("days_to_maturity"),
                    source_spot=item.get("source_spot", "fixture"),
                    source_future=item.get("source_future", "fixture"),
                )
            )
        return results


premium_fetcher = PremiumFetcher()
