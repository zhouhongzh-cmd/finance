import json
import os
import re
import akshare as ak
import httpx
from typing import List, Optional
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential
from models.market_data import CBData
from config.settings import settings
from utils.logger import logger
from utils.source_health import source_health_context


class ConvertibleFetcher:
    """可转债行情拉取器"""

    EASTMONEY_API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    EASTMONEY_PAGE_SIZE = 500

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=8)
    )
    def fetch_live(self) -> List[CBData]:
        """从 AKShare 获取实时可转债行情 (集思录数据)。"""
        cookie = settings.JSL_COOKIE if settings.JSL_COOKIE else ""
        with source_health_context("convertible_jsl"):
            df = ak.bond_cb_jsl(cookie=cookie)

        # 无论是否配置 Cookie，只要结果明显截断就触发降级
        # （集思录正常应返回数百条可转债数据，≤30 条说明被限流或 Cookie 失效）
        if len(df) <= 30:
            logger.warning(
                "jsl_rate_limited",
                detail=f"集思录返回数据仅 {len(df)} 条，疑似限流或 Cookie 失效，触发降级切换至东方财富。",
                cookie_configured=bool(settings.JSL_COOKIE),
            )
            return self._fetch_live_fallback()

        results = []
        for _, row in df.iterrows():
            symbol = f"{row.get('代码', 'N/A')}({row.get('转债名称', 'N/A')})"
            try:
                price = float(row.get("现价", 0) or 0)
                premium_rate = float(row.get("转股溢价率", 0) or 0)
                double_low = float(row.get("双低", 0) or 0)
                ytm = float(row.get("到期税前收益", 0) or 0)
            except (ValueError, TypeError):
                continue

            results.append(
                CBData(
                    symbol=symbol,
                    timestamp=datetime.now(),
                    premium_rate=premium_rate,
                    double_low=double_low,
                    price=price,
                    ytm=ytm,
                )
            )
        return results

    def _fetch_live_fallback(self) -> List[CBData]:
        """东方财富结构化备用接口，必要时回退到 akshare 的东财列表源。"""
        try:
            return self._fetch_live_fallback_eastmoney()
        except Exception as exc:
            logger.warning(
                "eastmoney_fallback_failed",
                error=str(exc),
                detail="东方财富 datacenter 备用接口失败，回退到 akshare.bond_zh_cov",
            )
            return self._fetch_live_fallback_legacy()

    def _fetch_live_fallback_eastmoney(self) -> List[CBData]:
        with source_health_context(
            "convertible_eastmoney", active_source="fallback", is_fallback=True
        ):
            rows = self._fetch_eastmoney_rows()
        results = []
        for row in rows:
            item = self._build_cbdata_from_eastmoney_row(row)
            if item is not None:
                results.append(item)
        logger.info("eastmoney_fallback_success", count=len(results))
        return results

    def _fetch_live_fallback_legacy(self) -> List[CBData]:
        """最后兜底：akshare 的东方财富转债列表接口。"""
        with source_health_context(
            "convertible_legacy_cov", active_source="fallback", is_fallback=True
        ):
            df = ak.bond_zh_cov()
        results = []
        for _, row in df.iterrows():
            symbol = f"{row.get('债券代码', 'N/A')}({row.get('债券简称', 'N/A')})"
            try:
                price = float(row.get("债现价", 0) or 0)
                premium_rate = float(row.get("转股溢价率", 0) or 0)
                transfer_value = float(row.get("转股价值", 0) or 0)
            except (ValueError, TypeError):
                continue

            if premium_rate == 0.0 and transfer_value > 0 and price > 0:
                premium_rate = (price / transfer_value - 1) * 100

            results.append(
                CBData(
                    symbol=symbol,
                    timestamp=datetime.now(),
                    premium_rate=premium_rate,
                    double_low=price + premium_rate,
                    price=price,
                    ytm=0.0,
                )
            )
        logger.info("legacy_cov_fallback_success", count=len(results))
        return results

    def _fetch_eastmoney_rows(self) -> List[dict]:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.eastmoney.com/kzz/default.html",
            "Accept": "application/json,text/javascript,*/*;q=0.01",
        }
        params = {
            "reportName": "RPT_BOND_CB_LIST",
            "columns": "ALL",
            "quoteColumns": (
                "f2~01~CONVERT_STOCK_CODE~CONVERT_STOCK_PRICE,"
                "f235~10~SECURITY_CODE~TRANSFER_PRICE,"
                "f236~10~SECURITY_CODE~TRANSFER_VALUE,"
                "f2~10~SECURITY_CODE~CURRENT_BOND_PRICE,"
                "f237~10~SECURITY_CODE~TRANSFER_PREMIUM_RATIO,"
                "f239~10~SECURITY_CODE~RESALE_TRIG_PRICE,"
                "f240~10~SECURITY_CODE~REDEEM_TRIG_PRICE,"
                "f23~01~CONVERT_STOCK_CODE~PBV_RATIO"
            ),
            "quoteType": "0",
            "source": "WEB",
            "client": "WEB",
            "pageNumber": 1,
            "pageSize": self.EASTMONEY_PAGE_SIZE,
        }

        all_rows: List[dict] = []
        with httpx.Client(timeout=settings.REQUEST_TIMEOUT, headers=headers) as client:
            first_page = client.get(self.EASTMONEY_API_URL, params=params)
            first_page.raise_for_status()
            payload = first_page.json()
            result = payload.get("result") or {}
            all_rows.extend(result.get("data") or [])
            total_pages = int(result.get("pages") or 1)

            for page in range(2, total_pages + 1):
                params["pageNumber"] = page
                response = client.get(self.EASTMONEY_API_URL, params=params)
                response.raise_for_status()
                page_payload = response.json()
                all_rows.extend((page_payload.get("result") or {}).get("data") or [])

        logger.info("eastmoney_rows_loaded", count=len(all_rows), pages=total_pages)
        return all_rows

    def _build_cbdata_from_eastmoney_row(self, row: dict) -> Optional[CBData]:
        code = row.get("SECURITY_CODE") or row.get("债券代码")
        name = row.get("SECURITY_NAME_ABBR") or row.get("债券简称")
        if not code or not name:
            return None

        price = self._to_float(
            row.get("CURRENT_BOND_PRICENEW"),
            row.get("CURRENT_BOND_PRICE"),
            row.get("ISSUE_PRICE"),
        )
        premium_rate = self._to_float(row.get("TRANSFER_PREMIUM_RATIO"))
        transfer_value = self._to_float(row.get("TRANSFER_VALUE"))

        if premium_rate == 0.0 and transfer_value > 0 and price > 0:
            premium_rate = (price / transfer_value - 1) * 100

        double_low = price + premium_rate
        ytm = self._estimate_ytm_from_row(row, price)

        return CBData(
            symbol=f"{code}({name})",
            timestamp=datetime.now(),
            premium_rate=premium_rate,
            double_low=double_low,
            price=price,
            ytm=ytm,
        )

    def _estimate_ytm_from_row(self, row: dict, price: float) -> float:
        interest_text = row.get("INTEREST_RATE_EXPLAIN") or ""
        start_date = row.get("BOND_START_DATE")
        rates = self._parse_coupon_schedule(interest_text)
        redemption_pct = self._extract_redemption_pct(row.get("REDEEM_CLAUSE") or "")

        if not start_date or not rates or price <= 0:
            return 0.0

        try:
            return self._solve_annualized_ytm(
                price=price,
                start_date_str=str(start_date).split()[0],
                coupon_rates=rates,
                redemption_pct=redemption_pct,
            )
        except Exception as exc:
            logger.debug(
                "ytm_estimation_failed",
                symbol=row.get("SECURITY_CODE"),
                error=str(exc),
            )
            return 0.0

    def _parse_coupon_schedule(self, interest_text: str) -> List[float]:
        rates = [
            float(match)
            for match in re.findall(r"第[一二三四五六七八九十]+年(?:为)?([0-9.]+)%", interest_text)
        ]
        if rates:
            return rates

        return [
            float(match)
            for match in re.findall(
                r"[0-9]{8}-[0-9]{8},票面利率:([0-9.]+)%",
                interest_text,
            )
        ]

    def _extract_redemption_pct(self, clause_text: str) -> float:
        match = re.search(r"面值的([0-9.]+)%", clause_text)
        return float(match.group(1)) if match else 100.0

    def _solve_annualized_ytm(
        self,
        price: float,
        start_date_str: str,
        coupon_rates: List[float],
        redemption_pct: float,
    ) -> float:
        start_date = datetime.fromisoformat(start_date_str)
        now = datetime.now()
        cashflows = []

        for year_index, coupon_rate in enumerate(coupon_rates, start=1):
            pay_date = start_date.replace(year=start_date.year + year_index)
            if pay_date <= now:
                continue

            amount = 100 * coupon_rate / 100
            if year_index == len(coupon_rates):
                amount += redemption_pct

            years_to_payment = (pay_date - now).days / 365
            cashflows.append((years_to_payment, amount))

        if not cashflows:
            return 0.0

        def present_value(rate: float) -> float:
            return sum(
                cashflow / ((1 + rate) ** years_to_payment)
                for years_to_payment, cashflow in cashflows
            )

        low, high = -0.99, 2.0
        for _ in range(200):
            mid = (low + high) / 2
            if present_value(mid) > price:
                low = mid
            else:
                high = mid

        return round(((low + high) / 2) * 100, 4)

    def _to_float(self, *values) -> float:
        for value in values:
            if value in (None, "", "-"):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return 0.0

    def fetch_from_fixture(self, path: str) -> List[CBData]:
        """
        从本地 fixture 读取数据进行开发与测试。
        Fixture JSON 字段: symbol, timestamp, premium_rate, double_low, price, ytm
        """
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(base_dir, path) if not os.path.isabs(path) else path

        with open(full_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        results = []
        for item in raw_data:
            dt = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
            dt = dt.replace(tzinfo=None)
            results.append(
                CBData(
                    symbol=item["symbol"],
                    timestamp=dt,
                    premium_rate=item["premium_rate"],
                    double_low=item["double_low"],
                    price=item.get("price", 100.0),   # 修复: 从 fixture 读取 price，默认 100 元
                    ytm=item.get("ytm", 0.0),          # 修复: 从 fixture 读取 ytm，默认 0%
                )
            )
        return results


convertible_fetcher = ConvertibleFetcher()
