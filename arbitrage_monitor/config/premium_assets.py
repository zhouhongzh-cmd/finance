from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CRYPTO_PREMIUM_ASSETS: dict[str, str] = {
    "BTC": "比特币",
    "ETH": "以太坊",
    "XRP": "瑞波币",
    "BNB": "币安币",
    "SOL": "索拉纳",
    "DOGE": "狗狗币",
    "ADA": "艾达币",
    "TRX": "波场",
    "LINK": "Chainlink",
    "AVAX": "Avalanche",
}


@dataclass(frozen=True)
class IndexPremiumAsset:
    asset_group: str
    name: str
    spot_symbol: str
    spot_name: str
    spot_source: str
    future_source: str
    future_symbol: str = ""
    future_name: str = ""
    source_exchange: str = ""
    akshare_name_keyword: str = ""
    bucket_rank: int = 0
    unavailable_reason: str = ""
    ib_enabled: bool = False
    ib_profile: str = ""
    ib_spot_contract: dict[str, Any] | None = None
    ib_future_contract: dict[str, Any] | None = None
    ib_future_chain_contract: dict[str, Any] | None = None
    ib_future_chain_limit: int = 0


INDEX_PREMIUM_ASSET_CONFIGS: dict[str, IndexPremiumAsset] = {
    "A50": IndexPremiumAsset(
        asset_group="A50",
        name="富时中国A50",
        spot_symbol="XIN9.FGI",
        spot_name="A50现货",
        spot_source="yfinance",
        future_source="akshare_global",
        source_exchange="A50",
        akshare_name_keyword="A50",
        bucket_rank=0,
    ),
    "HSI": IndexPremiumAsset(
        asset_group="HSI",
        name="恒生指数",
        spot_symbol="HSI",
        spot_name="恒生指数现货",
        spot_source="akshare_hk_index",
        future_source="ib",
        source_exchange="HKEX",
        unavailable_reason="IB 不可用时当前默认源仍未提供稳定可用的恒指期货价格",
        ib_enabled=True,
        ib_profile="remote",
        ib_spot_contract={
            "symbol": "HSI",
            "sec_type": "IND",
            "exchange": "HKFE",
            "currency": "HKD",
        },
        ib_future_contract={
            "symbol": "HSI",
            "sec_type": "CONTFUT",
            "exchange": "HKFE",
            "currency": "HKD",
        },
        ib_future_chain_contract={
            "symbol": "HSI",
            "sec_type": "FUT",
            "exchange": "HKFE",
            "currency": "HKD",
        },
        ib_future_chain_limit=4,
    ),
    "HSTECH": IndexPremiumAsset(
        asset_group="HSTECH",
        name="恒生科技指数",
        spot_symbol="HSTECH",
        spot_name="恒生科技指数现货",
        spot_source="ib",
        future_source="ib",
        source_exchange="HKEX",
        unavailable_reason="IB 不可用时当前默认源未提供稳定可用的恒生科技指数期货价格",
        ib_enabled=True,
        ib_profile="remote",
        ib_spot_contract={
            "symbol": "HSTECH",
            "sec_type": "IND",
            "exchange": "HKFE",
            "currency": "HKD",
        },
        ib_future_contract={
            "symbol": "HSTECH",
            "sec_type": "CONTFUT",
            "exchange": "HKFE",
            "currency": "HKD",
        },
        ib_future_chain_contract={
            "symbol": "HSTECH",
            "sec_type": "FUT",
            "exchange": "HKFE",
            "currency": "HKD",
        },
        ib_future_chain_limit=4,
    ),
    "NDX": IndexPremiumAsset(
        asset_group="NDX",
        name="纳斯达克100",
        spot_symbol="NDX",
        spot_name="纳斯达克100现货",
        spot_source="akshare_global_index",
        future_source="akshare_global",
        future_symbol="NQ=F",
        future_name="纳斯达克100连续期货",
        source_exchange="CME",
        akshare_name_keyword="小型纳指当月连续",
        bucket_rank=0,
        ib_spot_contract={
            "symbol": "NDX",
            "sec_type": "IND",
            "exchange": "NASDAQ",
            "currency": "USD",
        },
        ib_future_contract={
            "symbol": "NQ",
            "sec_type": "CONTFUT",
            "exchange": "CME",
            "currency": "USD",
        },
    ),
    "SPX": IndexPremiumAsset(
        asset_group="SPX",
        name="标普500",
        spot_symbol="SPX",
        spot_name="标普500现货",
        spot_source="akshare_global_index",
        future_source="akshare_global",
        future_symbol="ES=F",
        future_name="标普500连续期货",
        source_exchange="CME",
        akshare_name_keyword="小型标普当月连续",
        bucket_rank=0,
        ib_spot_contract={
            "symbol": "SPX",
            "sec_type": "IND",
            "exchange": "CBOE",
            "currency": "USD",
        },
        ib_future_contract={
            "symbol": "ES",
            "sec_type": "CONTFUT",
            "exchange": "CME",
            "currency": "USD",
        },
    ),
    "DJI": IndexPremiumAsset(
        asset_group="DJI",
        name="道琼斯工业指数",
        spot_symbol="DJIA",
        spot_name="道指现货",
        spot_source="akshare_global_index",
        future_source="akshare_global",
        future_symbol="YM=F",
        future_name="道指连续期货",
        source_exchange="CBOT",
        akshare_name_keyword="小型道指",
        bucket_rank=0,
        ib_spot_contract={
            "symbol": "DJI",
            "sec_type": "IND",
            "exchange": "CBOT",
            "currency": "USD",
        },
        ib_future_contract={
            "symbol": "YM",
            "sec_type": "CONTFUT",
            "exchange": "CBOT",
            "currency": "USD",
        },
    ),
    "NIKKEI225": IndexPremiumAsset(
        asset_group="NIKKEI225",
        name="日经225",
        spot_symbol="N225",
        spot_name="日经225现货",
        spot_source="akshare_global_index",
        future_source="yfinance",
        future_symbol="NKD=F",
        future_name="日经225连续期货",
        source_exchange="CME",
        bucket_rank=0,
    ),
}

INDEX_PREMIUM_ASSETS: dict[str, str] = {
    asset_group: config.name
    for asset_group, config in INDEX_PREMIUM_ASSET_CONFIGS.items()
}

PREMIUM_ASSETS: dict[str, str] = {
    **INDEX_PREMIUM_ASSETS,
    **CRYPTO_PREMIUM_ASSETS,
}


def is_index_premium_asset(asset_group: str) -> bool:
    return str(asset_group or "").upper() in INDEX_PREMIUM_ASSETS


def is_crypto_premium_asset(asset_group: str) -> bool:
    return str(asset_group or "").upper() in CRYPTO_PREMIUM_ASSETS
