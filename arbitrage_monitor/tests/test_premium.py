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

def test_premium_module_integration():
    """测试 premium 模块调度独立运行。"""
    logger.info("test_premium_module_integration_start")

    import core_scheduler as cs
    from config.settings import settings

    original_run_strategy_task = cs.run_strategy_task
    original_sync_runtime_settings = cs.sync_runtime_settings
    original_is_module_watch_hours = cs.is_module_watch_hours
    original = {
        "ENABLE_PREMIUM_MONITOR": settings.ENABLE_PREMIUM_MONITOR,
        "ENABLE_PREMIUM_CRUISE": settings.ENABLE_PREMIUM_CRUISE,
        "ENABLE_PREMIUM_WATCH": settings.ENABLE_PREMIUM_WATCH,
    }
    executed: list[str] = []

    def fake_run_strategy_task(fetcher, strategy, strategy_name: str):
        executed.append(strategy_name)
        return {"status": "SUCCESS"}

    try:
        cs.run_strategy_task = fake_run_strategy_task
        cs.sync_runtime_settings = lambda: None
        cs.is_module_watch_hours = lambda prefix, now=None: prefix == "PREMIUM"
        settings.apply_updates(
            {
                "ENABLE_PREMIUM_MONITOR": True,
                "ENABLE_PREMIUM_CRUISE": True,
                "ENABLE_PREMIUM_WATCH": False,
            }
        )
        cs.run_premium_cruise_mode()
        cs.run_premium_watch_mode()
    finally:
        settings.apply_updates(original)
        cs.run_strategy_task = original_run_strategy_task
        cs.sync_runtime_settings = original_sync_runtime_settings
        cs.is_module_watch_hours = original_is_module_watch_hours

    if executed != ["Premium_Arbitrage"]:
        print(f"❌ Premium Module Integration: unexpected executed strategies {executed}")
        return False

    logger.info("premium_module_integration_ok", executed=executed)
    print("✅ Premium Module Integration: OK")
    return True


class _PremiumFakeIBProvider:
    def __init__(
        self,
        *,
        pair=None,
        exc: Exception | None = None,
        default_profile: str = "remote",
        contract_rows=None,
        snapshot_map=None,
    ):
        self._pair = pair
        self._exc = exc
        self._contract_rows = contract_rows or {}
        self._snapshot_map = snapshot_map or {}
        self.settings = type("S", (), {"IB_DEFAULT_PROFILE": default_profile})()

    def get_index_pair_snapshot(self, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._pair

    def resolve_contracts(self, specs, **kwargs):
        if self._exc is not None:
            raise self._exc
        return {spec.key: list(self._contract_rows.get(spec.key, [])) for spec in specs}

    def get_market_snapshot(self, resolved_contract, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._snapshot_map[resolved_contract.key]


def test_premium_ib_hsi_snapshot():
    from config.premium_assets import INDEX_PREMIUM_ASSET_CONFIGS
    from fetchers.premium_fetcher import PremiumFetcher
    from providers.ib_gateway import IBIndexPairSnapshot, IBMarketSnapshot

    pair = IBIndexPairSnapshot(
        asset_key="HSI",
        profile="remote",
        spot=IBMarketSnapshot(
            key="HSI_spot",
            symbol="HSI",
            sec_type="IND",
            exchange="HKFE",
            primary_exchange="",
            currency="HKD",
            local_symbol="HSI",
            trading_class="HSI",
            con_id=1,
            last_price=18234.0,
            close_price=18200.0,
            market_data_type=3,
            source="ib.remote.reqMktData",
        ),
        future=IBMarketSnapshot(
            key="HSI_future",
            symbol="HSI",
            sec_type="CONTFUT",
            exchange="HKFE",
            primary_exchange="",
            currency="HKD",
            local_symbol="HSI-CONT",
            trading_class="HSI",
            con_id=2,
            last_price=18280.0,
            close_price=18250.0,
            market_data_type=3,
            source="ib.remote.reqMktData",
        ),
    )
    fetcher = PremiumFetcher(ib_provider=_PremiumFakeIBProvider(pair=pair))

    rows = fetcher._build_ib_index_snapshot(INDEX_PREMIUM_ASSET_CONFIGS["HSI"])

    assert len(rows) == 1
    row = rows[0]
    assert row.asset_group == "HSI"
    assert row.contract_bucket == "INDEX"
    assert row.source_spot == "ib.remote.reqMktData"
    assert row.source_future == "ib.remote.reqMktData"
    assert row.spot_price == 18234.0
    assert row.future_price == 18280.0


def test_premium_ib_hstech_snapshot():
    from config.premium_assets import INDEX_PREMIUM_ASSET_CONFIGS
    from fetchers.premium_fetcher import PremiumFetcher
    from providers.ib_gateway import IBIndexPairSnapshot, IBMarketSnapshot

    pair = IBIndexPairSnapshot(
        asset_key="HSTECH",
        profile="remote",
        spot=IBMarketSnapshot(
            key="HSTECH_spot",
            symbol="HSTECH",
            sec_type="IND",
            exchange="HKFE",
            primary_exchange="",
            currency="HKD",
            local_symbol="HSTECH",
            trading_class="",
            con_id=11,
            last_price=4123.0,
            close_price=4100.0,
            market_data_type=3,
            source="ib.remote.reqMktData",
        ),
        future=IBMarketSnapshot(
            key="HSTECH_future",
            symbol="HSTECH",
            sec_type="CONTFUT",
            exchange="HKFE",
            primary_exchange="",
            currency="HKD",
            local_symbol="HTIK6",
            trading_class="HTI",
            con_id=12,
            last_price=4150.0,
            close_price=4130.0,
            market_data_type=3,
            source="ib.remote.reqMktData",
        ),
    )
    fetcher = PremiumFetcher(ib_provider=_PremiumFakeIBProvider(pair=pair))

    rows = fetcher._build_ib_index_snapshot(INDEX_PREMIUM_ASSET_CONFIGS["HSTECH"])

    assert len(rows) == 1
    row = rows[0]
    assert row.asset_group == "HSTECH"
    assert row.future_symbol == "HTIK6"
    assert row.source_spot == "ib.remote.reqMktData"
    assert row.source_future == "ib.remote.reqMktData"


def test_premium_ib_hsi_future_chain_snapshot():
    from config.premium_assets import INDEX_PREMIUM_ASSET_CONFIGS
    from fetchers.premium_fetcher import PremiumFetcher
    from providers.ib_gateway import IBMarketSnapshot, IBResolvedContract

    fetcher = PremiumFetcher(
        ib_provider=_PremiumFakeIBProvider(
            contract_rows={
                "HSI_spot": [
                    IBResolvedContract(
                        key="HSI_spot",
                        symbol="HSI",
                        sec_type="IND",
                        exchange="HKFE",
                        primary_exchange="",
                        currency="HKD",
                        local_symbol="HSI",
                        trading_class="HSI",
                        con_id=1,
                        last_trade_date_or_contract_month="",
                    )
                ],
                "HSI_future_chain": [
                    IBResolvedContract(
                        key="HSI_future_chain",
                        symbol="HSI",
                        sec_type="FUT",
                        exchange="HKFE",
                        primary_exchange="",
                        currency="HKD",
                        local_symbol="HSIK6",
                        trading_class="HSI",
                        con_id=2,
                        last_trade_date_or_contract_month="20260529",
                    ),
                    IBResolvedContract(
                        key="HSI_future_chain",
                        symbol="HSI",
                        sec_type="FUT",
                        exchange="HKFE",
                        primary_exchange="",
                        currency="HKD",
                        local_symbol="HSIM6",
                        trading_class="HSI",
                        con_id=3,
                        last_trade_date_or_contract_month="20260627",
                    ),
                ],
            },
            snapshot_map={
                "HSI_spot": IBMarketSnapshot(
                    key="HSI_spot",
                    symbol="HSI",
                    sec_type="IND",
                    exchange="HKFE",
                    primary_exchange="",
                    currency="HKD",
                    local_symbol="HSI",
                    trading_class="HSI",
                    con_id=1,
                    last_price=18000.0,
                    close_price=17900.0,
                    market_data_type=3,
                    source="ib.remote.reqMktData",
                ),
                "HSI_future_chain": IBMarketSnapshot(
                    key="HSI_future_chain",
                    symbol="HSI",
                    sec_type="FUT",
                    exchange="HKFE",
                    primary_exchange="",
                    currency="HKD",
                    local_symbol="HSIK6",
                    trading_class="HSI",
                    con_id=2,
                    last_price=18100.0,
                    close_price=18080.0,
                    market_data_type=3,
                    source="ib.remote.reqMktData",
                ),
            },
        )
    )
    original_limit = INDEX_PREMIUM_ASSET_CONFIGS["HSI"].ib_future_chain_limit
    rows = fetcher._build_ib_chain_index_snapshots(INDEX_PREMIUM_ASSET_CONFIGS["HSI"])

    assert rows
    assert rows[0].asset_group == "HSI"
    assert rows[0].future_symbol == "HSIK6"
    assert rows[0].source_future == "ib.remote.reqMktData"


def test_premium_ib_failure_fallback():
    from config.premium_assets import INDEX_PREMIUM_ASSET_CONFIGS
    from fetchers.premium_fetcher import PremiumFetcher

    fetcher = PremiumFetcher(ib_provider=_PremiumFakeIBProvider(exc=RuntimeError("boom")))
    original_spot_fetch = fetcher._fetch_index_spot_price
    original_akshare_fetch = fetcher._build_akshare_index_snapshots
    original_yfinance_fetch = fetcher._build_yfinance_index_snapshot
    original_index_configs = INDEX_PREMIUM_ASSET_CONFIGS.copy()
    asset = INDEX_PREMIUM_ASSET_CONFIGS["NDX"]

    try:
        INDEX_PREMIUM_ASSET_CONFIGS.clear()
        INDEX_PREMIUM_ASSET_CONFIGS["NDX"] = asset
        fetcher._fetch_index_spot_price = lambda cfg: (20000.0, "fixture.spot")
        fetcher._build_akshare_index_snapshots = lambda cfg, spot, source: []
        fetcher._build_yfinance_index_snapshot = lambda cfg, spot, source: [
            fetcher._build_snapshot(
                asset_group=cfg.asset_group,
                spot_symbol=cfg.spot_symbol,
                spot_name=cfg.spot_name,
                spot_price=spot,
                future_symbol=cfg.future_symbol,
                future_name=cfg.future_name,
                future_price=20100.0,
                contract_bucket="INDEX",
                contract_type="future",
                source_exchange=cfg.source_exchange,
                source_spot=source,
                source_future="fixture.future",
            )
        ]
        rows = fetcher._build_index_snapshots()
    finally:
        INDEX_PREMIUM_ASSET_CONFIGS.clear()
        INDEX_PREMIUM_ASSET_CONFIGS.update(original_index_configs)
        fetcher._fetch_index_spot_price = original_spot_fetch
        fetcher._build_akshare_index_snapshots = original_akshare_fetch
        fetcher._build_yfinance_index_snapshot = original_yfinance_fetch

    ndx_rows = [row for row in rows if row.asset_group == "NDX"]
    assert ndx_rows
    assert ndx_rows[0].source_future == "fixture.future"
