from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta
from typing import Any, Optional

import akshare as ak
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from config.metals import DEFAULT_EXCHANGE_RATE, METALS_CONFIG
from config.settings import settings
from models.market_data import MetalArbitrageData
from utils.logger import logger
from utils.source_health import source_health_context


class MetalsFetcher:
    """金属套利行情抓取器。每条输出对应一个国内品种与一个外盘基准。"""

    def get_exchange_rate(self) -> float:
        try:
            with source_health_context("metals_fx_spot_quote"):
                df = ak.fx_spot_quote()
            usd_cny = df[df["货币对"] == "USD/CNY"]["买报价"].values[0]
            rate = float(usd_cny)
            if not math.isnan(rate) and rate > 0:
                return rate
            raise ValueError(f"invalid_rate={rate}")
        except Exception as exc:
            logger.warning("metals_fx_primary_failed", error=str(exc))

        try:
            end_date = date.today().strftime("%Y%m%d")
            start_date = (date.today() - timedelta(days=7)).strftime("%Y%m%d")
            with source_health_context(
                "metals_fx_boc", active_source="fallback", is_fallback=True
            ):
                df_boc = ak.currency_boc_sina(
                    symbol="美元", start_date=start_date, end_date=end_date
                )
            if df_boc is not None and not df_boc.empty:
                last_row = df_boc.iloc[-1]
                for col_idx in [1, 2, 3, 5]:
                    val = float(last_row.iloc[col_idx])
                    if not math.isnan(val) and val > 0:
                        return val / 100.0
            raise ValueError("empty_boc_rate")
        except Exception as exc:
            logger.warning("metals_fx_boc_failed", error=str(exc))

        try:
            from forex_python.converter import CurrencyRates

            with source_health_context(
                "metals_fx_forex_python", active_source="fallback", is_fallback=True
            ):
                rate = float(CurrencyRates().get_rate("USD", "CNY"))
            if rate > 0:
                return rate
            raise ValueError(f"invalid_forex_python_rate={rate}")
        except Exception as exc:
            logger.warning("metals_fx_forex_python_failed", error=str(exc))

        logger.warning("metals_fx_default_used", default_rate=DEFAULT_EXCHANGE_RATE)
        return DEFAULT_EXCHANGE_RATE

    def fetch_foreign_commodity(self, symbol: str) -> dict[str, Any]:
        with source_health_context("metals_foreign_realtime"):
            df = ak.futures_foreign_commodity_realtime(symbol=symbol)
        if df is None or df.empty:
            raise ValueError(f"empty_foreign_response:{symbol}")

        row = df.iloc[0]
        price_cny: Optional[float] = None
        if "人民币报价" in row.index:
            raw_cny = row.get("人民币报价")
            if raw_cny not in ("", None) and pd.notna(raw_cny):
                price_cny = float(raw_cny)

        return {
            "symbol": symbol,
            "price_usd": float(row.get("最新价", 0) or 0),
            "price_cny": price_cny,
            "time": str(row.get("行情时间", "") or ""),
            "date": str(row.get("日期", "") or ""),
            "name": str(row.get("名称", symbol) or symbol),
        }

    def fetch_domestic_minute(self, symbol: str) -> dict[str, Any]:
        with source_health_context("metals_domestic_minute"):
            df = ak.futures_zh_minute_sina(symbol=symbol, period="1")
        if df is None or df.empty:
            raise ValueError(f"empty_domestic_minute_response:{symbol}")

        latest = df.iloc[-1]
        return {
            "symbol": symbol,
            "price": float(latest["close"]),
            "time": str(latest["datetime"]),
            "source": "SHFE_MINUTE",
        }

    def fetch_domestic_spot(self, symbol: str) -> dict[str, Any]:
        with source_health_context(
            "metals_domestic_spot", active_source="fallback", is_fallback=True
        ):
            df = ak.futures_zh_spot(symbol=symbol, market="CF", adjust="0")
        if df is None or df.empty:
            raise ValueError(f"empty_domestic_spot_response:{symbol}")

        row = df.iloc[0]
        price_val = row.get("current_price", row.iloc[0] if len(row) > 0 else 0)
        time_str = str(row.get("time", "") or "")
        if len(time_str) == 6 and time_str.isdigit():
            time_str = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
        if time_str and len(time_str) <= 8:
            time_str = f"{datetime.now().strftime('%Y-%m-%d')} {time_str}"

        return {
            "symbol": symbol,
            "price": float(price_val) if pd.notna(price_val) else 0.0,
            "time": time_str,
            "source": "SHFE_SPOT",
        }

    def fetch_domestic_price(self, metal_symbol: str) -> dict[str, Any]:
        config = METALS_CONFIG[metal_symbol]
        domestic_symbol = config["domestic_symbol"]

        try:
            data = self.fetch_domestic_minute(domestic_symbol)
            data["source"] = "SHFE_MINUTE"
            return data
        except Exception as primary_exc:
            logger.warning(
                "metals_domestic_minute_failed",
                metal_symbol=metal_symbol,
                domestic_symbol=domestic_symbol,
                error=str(primary_exc),
            )

        data = self.fetch_domestic_spot(domestic_symbol)
        data["source"] = "SHFE_SPOT"
        return data

    def convert_foreign_price(
        self,
        usd_price: float,
        rate: float,
        unit_factor: float,
        foreign_cny: Optional[float] = None,
        benchmark_name: str = "",
    ) -> tuple[float, bool]:
        if foreign_cny and foreign_cny > 0:
            if "COMEX" in benchmark_name and "银" in benchmark_name:
                return foreign_cny * unit_factor, True
            if "伦敦银" in benchmark_name or "LME银" in benchmark_name:
                return foreign_cny * 1000, True
            return foreign_cny, True

        if unit_factor in (0, 1):
            return usd_price * rate, False

        cny_price = usd_price * rate / unit_factor
        if unit_factor > 10:
            cny_price *= 1000
        return cny_price, False

    def calculate_implied_rate(
        self,
        for_price_cny: float,
        foreign_usd: float,
        unit_factor: float,
        rate_direction: str = "base",
    ) -> float:
        if not foreign_usd or foreign_usd <= 0:
            return 0.0
        if rate_direction == "div":
            return for_price_cny * unit_factor / foreign_usd
        if rate_direction == "div_kg":
            return for_price_cny / (foreign_usd * unit_factor)
        if rate_direction == "mul":
            return for_price_cny / (foreign_usd * unit_factor)
        return for_price_cny / foreign_usd

    def build_snapshot(
        self,
        metal_symbol: str,
        benchmark_config: dict[str, Any],
        domestic_data: dict[str, Any],
        foreign_data: dict[str, Any],
        exchange_rate: float,
    ) -> MetalArbitrageData:
        metal_config = METALS_CONFIG[metal_symbol]
        benchmark_name = benchmark_config["name"]
        unit_factor = float(benchmark_config["unit_factor"])
        rate_direction = benchmark_config.get("rate_direction", "base")

        for_price_cny, used_api_cny_quote = self.convert_foreign_price(
            usd_price=float(foreign_data["price_usd"]),
            rate=exchange_rate,
            unit_factor=unit_factor,
            foreign_cny=foreign_data.get("price_cny"),
            benchmark_name=benchmark_name,
        )
        dom_price = float(domestic_data["price"])
        spread = dom_price - for_price_cny
        spread_pct = (spread / for_price_cny * 100) if for_price_cny else 0.0
        implied_rate = self.calculate_implied_rate(
            for_price_cny=for_price_cny,
            foreign_usd=float(foreign_data["price_usd"]),
            unit_factor=unit_factor,
            rate_direction=rate_direction,
        )

        symbol = f"{metal_symbol}:{benchmark_config['symbol']}"
        return MetalArbitrageData(
            symbol=symbol,
            timestamp=datetime.now(),
            metal_symbol=metal_symbol,
            metal_name=metal_config["name"],
            benchmark_symbol=benchmark_config["symbol"],
            benchmark_name=benchmark_name,
            benchmark_display_name=benchmark_config["display_name"],
            domestic_symbol=metal_config["domestic_symbol"],
            domestic_name=metal_config["domestic_name"],
            domestic_unit=metal_config["domestic_unit"],
            category=metal_config["category"],
            dom_price=dom_price,
            for_price_usd=float(foreign_data["price_usd"]),
            for_price_cny=for_price_cny,
            exchange_rate=exchange_rate,
            implied_rate=implied_rate or exchange_rate,
            spread=spread,
            spread_pct=spread_pct,
            dom_time=str(domestic_data.get("time", "")),
            for_time=str(foreign_data.get("time", "")),
            for_date=str(foreign_data.get("date", "")),
            used_api_cny_quote=used_api_cny_quote,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=8),
    )
    def fetch_live(self) -> list[MetalArbitrageData]:
        logger.info("fetch_metals_live_start")
        exchange_rate = self.get_exchange_rate()
        results: list[MetalArbitrageData] = []

        for metal_symbol, metal_config in METALS_CONFIG.items():
            try:
                domestic_data = self.fetch_domestic_price(metal_symbol)
            except Exception as exc:
                logger.warning(
                    "metals_domestic_fetch_failed",
                    metal_symbol=metal_symbol,
                    error=str(exc),
                )
                continue

            for benchmark_config in metal_config["foreign_benchmarks"]:
                try:
                    foreign_data = self.fetch_foreign_commodity(benchmark_config["symbol"])
                    results.append(
                        self.build_snapshot(
                            metal_symbol=metal_symbol,
                            benchmark_config=benchmark_config,
                            domestic_data=domestic_data,
                            foreign_data=foreign_data,
                            exchange_rate=exchange_rate,
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "metals_pair_fetch_failed",
                        metal_symbol=metal_symbol,
                        benchmark_symbol=benchmark_config["symbol"],
                        error=str(exc),
                    )

        logger.info("fetch_metals_live_success", count=len(results))
        return results

    def fetch_from_fixture(
        self, path: str = "tests/fixtures/metals_sample.json"
    ) -> list[MetalArbitrageData]:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(base_dir, path)
        with open(full_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        results: list[MetalArbitrageData] = []
        for item in raw_data:
            results.append(
                MetalArbitrageData(
                    symbol=item["symbol"],
                    timestamp=datetime.now(),
                    metal_symbol=item["metal_symbol"],
                    metal_name=item["metal_name"],
                    benchmark_symbol=item["benchmark_symbol"],
                    benchmark_name=item["benchmark_name"],
                    benchmark_display_name=item["benchmark_display_name"],
                    domestic_symbol=item["domestic_symbol"],
                    domestic_name=item["domestic_name"],
                    domestic_unit=item["domestic_unit"],
                    category=item["category"],
                    dom_price=float(item["dom_price"]),
                    for_price_usd=float(item["for_price_usd"]),
                    for_price_cny=float(item["for_price_cny"]),
                    exchange_rate=float(item["exchange_rate"]),
                    implied_rate=float(item["implied_rate"]),
                    spread=float(item["spread"]),
                    spread_pct=float(item["spread_pct"]),
                    dom_time=str(item.get("dom_time", "")),
                    for_time=str(item.get("for_time", "")),
                    for_date=str(item.get("for_date", "")),
                    used_api_cny_quote=bool(item.get("used_api_cny_quote", False)),
                )
            )
        logger.debug("fetch_metals_from_fixture", path=path, count=len(results))
        return results


metals_fetcher = MetalsFetcher()
