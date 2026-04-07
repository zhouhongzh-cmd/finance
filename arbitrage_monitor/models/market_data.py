from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class BaseMarketData:
    """基础行情数据 (开发时其他 AI 可自行继承扩展)"""
    symbol: str
    timestamp: datetime

@dataclass
class FuturesData(BaseMarketData):
    """期指行情快照"""
    price: float
    spot_price: float
    discount_rate: float
    product_code: str = ""
    contract_multiplier: int = 0
    margin_ratio: float = 0.0
    notional_per_lot: float = 0.0
    margin_required_per_lot: float = 0.0
    days_to_maturity: int = 15  # 距交割剩余天数，用于年化计算；默认15天作为安全兜底

@dataclass
class FuturesMarginData(BaseMarketData):
    """股指期货保证金比例快照"""
    margin_ratio: float
    source: str = ""
    source_url: str = ""
    notes: str = ""

@dataclass
class CBData(BaseMarketData):
    """转债行情快照"""
    premium_rate: float
    double_low: float
    price: float = 0.0
    ytm: float = 0.0
    bond_code: str = ""
    bond_name: str = ""
    listing_status: str = ""
    is_listed: bool = False
    is_delisted: bool = False
    listing_date: str = ""
    delist_date: str = ""

@dataclass
class CryptoFundingData(BaseMarketData):
    """资金费率快照"""
    funding_rate: float
    predicted_rate: Optional[float] = None

@dataclass
class SentimentData(BaseMarketData):
    """舆情数据快照 (原定义在 fetchers/sentiment_spider.py，已迁移至此以遵守分层架构)"""
    name: str
    hot_score: int
    sentiment_pulse: float
    rank: int


@dataclass
class MetalArbitrageData(BaseMarketData):
    """金属跨市场套利对快照，一条记录对应一个国内品种与一个外盘基准。"""
    metal_symbol: str
    metal_name: str
    benchmark_symbol: str
    benchmark_name: str
    benchmark_display_name: str
    domestic_symbol: str
    domestic_name: str
    domestic_unit: str
    category: str
    dom_price: float
    for_price_usd: float
    for_price_cny: float
    exchange_rate: float
    implied_rate: float
    spread: float
    spread_pct: float
    dom_time: str = ""
    for_time: str = ""
    for_date: str = ""
    used_api_cny_quote: bool = False


@dataclass
class PremiumArbitrageData(BaseMarketData):
    """期现溢价快照，一条记录对应一个现货/期货对。"""
    asset_group: str
    spot_symbol: str
    spot_name: str
    spot_price: float
    future_symbol: str
    future_name: str
    future_price: float
    premium: float
    premium_rate: float
    state: str
    source_spot: str = ""
    source_future: str = ""
