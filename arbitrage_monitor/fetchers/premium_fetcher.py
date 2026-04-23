from __future__ import annotations

import json
import os
from calendar import monthrange
from datetime import datetime
from typing import Any

import akshare as ak
import httpx
import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from models.market_data import PremiumArbitrageData
from utils.logger import logger
from config.premium_thresholds import (
    CONTRACT_BUCKET_LABELS,
    CONTRACT_BUCKET_ORDER,
    CRYPTO_PREMIUM_ASSETS,
)
from utils.source_health import source_health_context


class PremiumFetcher:
    """A50 与加密期现溢价抓取器。"""

    GATE_BASE_URL = "https://api.gateio.ws/api/v4"
    GATE_SOURCE = "gate.api.v4"
    GATE_EXCHANGE = "Gate"
    GATE_SETTLE = "usdt"
    GATE_TOP_CRYPTO_ASSETS: dict[str, str] = CRYPTO_PREMIUM_ASSETS
    GATE_PERP_BUCKET = "PERP"
    GATE_DELIVERY_MONTHLY_BUCKETS = ("MONTHLY_CURRENT", "MONTHLY_NEXT")
    GATE_DELIVERY_QUARTERLY_BUCKETS = ("QUARTERLY_CURRENT", "QUARTERLY_NEXT")
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
        return None, ""

    def _gate_get_json(self, path: str, *, source_name: str) -> Any:
        url = f"{self.GATE_BASE_URL}{path}"
        with source_health_context(source_name):
            response = httpx.get(url, timeout=15.0)
            response.raise_for_status()
            return response.json()

    def _estimate_a50_days_to_maturity(self, future_symbol: str) -> int | None:
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

        expiry_date = datetime(year, month, monthrange(year, month)[1])
        return max((expiry_date.date() - now.date()).days, 0)

    def _format_expiry_ts(self, raw_expiry: Any) -> str:
        try:
            expiry = int(raw_expiry)
        except Exception:
            return ""
        if expiry <= 0:
            return ""
        return datetime.fromtimestamp(expiry).isoformat()

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
        contract_bucket: str = "",
        contract_type: str = "",
        expiry_ts: str = "",
        bucket_rank: int = 0,
        source_exchange: str = "",
        days_to_maturity: int | None = None,
        source_spot: str = "",
        source_future: str = "",
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
            contract_bucket=contract_bucket,
            contract_type=contract_type,
            expiry_ts=expiry_ts,
            bucket_rank=bucket_rank,
            source_exchange=source_exchange,
            days_to_maturity=days_to_maturity,
            source_spot=source_spot,
            source_future=source_future,
        )

    def _build_a50_snapshots(self) -> list[PremiumArbitrageData]:
        results: list[PremiumArbitrageData] = []
        a50_spot, a50_spot_source = self._fetch_yfinance_price(
            "XIN9.FGI", "premium_a50_spot_yfinance"
        )
        if a50_spot is None:
            logger.warning("premium_a50_spot_missing")
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
                    results.append(
                        self._build_snapshot(
                            asset_group="A50",
                            spot_symbol="XIN9.FGI",
                            spot_name="A50现货",
                            spot_price=float(a50_spot),
                            future_symbol=future_symbol,
                            future_name=future_name,
                            future_price=future_price,
                            contract_bucket="A50",
                            contract_type="future",
                            expiry_ts="",
                            bucket_rank=0 if future_symbol == "CN00Y" else 10,
                            source_exchange="A50",
                            days_to_maturity=self._estimate_a50_days_to_maturity(future_symbol),
                            source_spot=a50_spot_source,
                            source_future="akshare.futures_global_spot_em",
                        )
                    )
                except Exception as exc:
                    logger.warning("premium_a50_future_parse_failed", error=str(exc))
        except Exception as exc:
            logger.warning("premium_a50_futures_fetch_failed", error=str(exc))
        return results

    def _fetch_gate_spot_pairs(self) -> set[str]:
        rows = self._gate_get_json("/spot/currency_pairs", source_name="premium_gate_spot_pairs")
        return {
            str(item.get("id") or item.get("currency_pair") or "").strip()
            for item in rows
            if isinstance(item, dict) and item.get("trade_status") == "tradable"
        }

    def _fetch_gate_spot_tickers(self) -> dict[str, dict[str, Any]]:
        rows = self._gate_get_json("/spot/tickers", source_name="premium_gate_spot_tickers")
        return {
            str(item.get("currency_pair") or "").strip(): item
            for item in rows
            if isinstance(item, dict) and item.get("currency_pair")
        }

    def _fetch_gate_perp_contracts(self) -> dict[str, dict[str, Any]]:
        rows = self._gate_get_json(
            f"/futures/{self.GATE_SETTLE}/contracts",
            source_name="premium_gate_perp_contracts",
        )
        return {
            str(item.get("name") or "").strip(): item
            for item in rows
            if isinstance(item, dict) and item.get("name") and not item.get("in_delisting", False)
        }

    def _fetch_gate_delivery_contracts(self) -> dict[str, list[dict[str, Any]]]:
        rows = self._gate_get_json(
            f"/delivery/{self.GATE_SETTLE}/contracts",
            source_name="premium_gate_delivery_contracts",
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in rows:
            if not isinstance(item, dict) or item.get("in_delisting", False):
                continue
            underlying = str(item.get("underlying") or "").strip()
            if not underlying:
                continue
            grouped.setdefault(underlying, []).append(item)
        for contracts in grouped.values():
            contracts.sort(key=lambda item: int(item.get("expire_time") or 0))
        return grouped

    def _build_gate_delivery_buckets(self, delivery_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        monthly_rows = [
            row
            for row in delivery_rows
            if str(row.get("cycle") or "").upper() not in {"QUARTERLY", "BI-QUARTERLY"}
        ]
        quarterly_rows = [
            row
            for row in delivery_rows
            if str(row.get("cycle") or "").upper() in {"QUARTERLY", "BI-QUARTERLY"}
        ]

        buckets: dict[str, dict[str, Any]] = {}
        for bucket_name, row in zip(self.GATE_DELIVERY_MONTHLY_BUCKETS, monthly_rows[:2]):
            buckets[bucket_name] = row
        for bucket_name, row in zip(self.GATE_DELIVERY_QUARTERLY_BUCKETS, quarterly_rows[:2]):
            buckets[bucket_name] = row
        return buckets

    def _build_gate_crypto_snapshots(self) -> list[PremiumArbitrageData]:
        results: list[PremiumArbitrageData] = []
        try:
            spot_pairs = self._fetch_gate_spot_pairs()
            spot_tickers = self._fetch_gate_spot_tickers()
            perp_contracts = self._fetch_gate_perp_contracts()
            delivery_contracts = self._fetch_gate_delivery_contracts()

            for asset_group in self.GATE_TOP_CRYPTO_ASSETS:
                underlying = f"{asset_group}_USDT"
                if underlying not in spot_pairs:
                    continue
                if underlying not in perp_contracts and not delivery_contracts.get(underlying):
                    continue

                spot_row = spot_tickers.get(underlying)
                if not spot_row:
                    logger.warning("premium_gate_spot_missing", asset_group=asset_group)
                    continue
                try:
                    spot_price = float(spot_row["last"])
                except Exception:
                    logger.warning("premium_gate_spot_price_invalid", asset_group=asset_group)
                    continue

                if underlying in perp_contracts:
                    perp_row = perp_contracts[underlying]
                    try:
                        results.append(
                            self._build_snapshot(
                                asset_group=asset_group,
                                spot_symbol=underlying,
                                spot_name=f"{asset_group}现货",
                                spot_price=spot_price,
                                future_symbol=underlying,
                                future_name=f"{asset_group}永续",
                                future_price=float(perp_row["last_price"]),
                                contract_bucket=self.GATE_PERP_BUCKET,
                                contract_type="swap",
                                expiry_ts="",
                                bucket_rank=CONTRACT_BUCKET_ORDER[self.GATE_PERP_BUCKET],
                                source_exchange=self.GATE_EXCHANGE,
                                days_to_maturity=None,
                                source_spot=self.GATE_SOURCE,
                                source_future=self.GATE_SOURCE,
                            )
                        )
                    except Exception as exc:
                        logger.warning("premium_gate_perp_parse_failed", asset_group=asset_group, error=str(exc))

                for bucket_name, row in self._build_gate_delivery_buckets(
                    delivery_contracts.get(underlying, [])
                ).items():
                    try:
                        expiry_raw = int(row.get("expire_time") or 0)
                        expiry_ts = self._format_expiry_ts(expiry_raw)
                        days_to_maturity = None
                        if expiry_raw > 0:
                            days_to_maturity = max(
                                (datetime.fromtimestamp(expiry_raw).date() - datetime.now().date()).days,
                                0,
                            )
                        results.append(
                            self._build_snapshot(
                                asset_group=asset_group,
                                spot_symbol=underlying,
                                spot_name=f"{asset_group}现货",
                                spot_price=spot_price,
                                future_symbol=str(row.get("name") or ""),
                                future_name=f"{asset_group}{CONTRACT_BUCKET_LABELS[bucket_name]}",
                                future_price=float(row["last_price"]),
                                contract_bucket=bucket_name,
                                contract_type="future",
                                expiry_ts=expiry_ts,
                                bucket_rank=CONTRACT_BUCKET_ORDER[bucket_name],
                                source_exchange=self.GATE_EXCHANGE,
                                days_to_maturity=days_to_maturity,
                                source_spot=self.GATE_SOURCE,
                                source_future=self.GATE_SOURCE,
                            )
                        )
                    except Exception as exc:
                        logger.warning(
                            "premium_gate_delivery_parse_failed",
                            asset_group=asset_group,
                            contract_bucket=bucket_name,
                            error=str(exc),
                        )
        except Exception as exc:
            logger.warning("premium_gate_crypto_fetch_failed", error=str(exc))
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=8))
    def fetch_live(self) -> list[PremiumArbitrageData]:
        logger.info("fetch_premium_live_start")
        results: list[PremiumArbitrageData] = []
        results.extend(self._build_gate_crypto_snapshots())
        results.extend(self._build_a50_snapshots())
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
                    contract_bucket=str(item.get("contract_bucket", "")),
                    contract_type=str(item.get("contract_type", "")),
                    expiry_ts=str(item.get("expiry_ts", "")),
                    bucket_rank=int(item.get("bucket_rank", 0)),
                    source_exchange=str(item.get("source_exchange", "")),
                    days_to_maturity=item.get("days_to_maturity"),
                    source_spot=item.get("source_spot", "fixture"),
                    source_future=item.get("source_future", "fixture"),
                )
            )
        return results


premium_fetcher = PremiumFetcher()
