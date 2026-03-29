from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd

from models.market_data import FuturesData, MetalArbitrageData
from models.signals import Signal


FUTURES_PRODUCT_ORDER = {"IH": 0, "IF": 1, "IC": 2, "IM": 3}
FUTURES_FRONT_COLUMNS = [
    "名称",
    "期指价格",
    "指数点位",
    "贴水点数",
    "贴水率(%)",
    "年化贴水率(%)",
    "时间",
]

METALS_SYMBOL_ORDER = {
    "AU0": 0,
    "AG0": 1,
    "PT0": 2,
    "PD0": 3,
    "CU0": 4,
    "AL0": 5,
    "ZN0": 6,
    "PB0": 7,
    "NI0": 8,
    "SN0": 9,
}
METALS_FRONT_COLUMNS = [
    "品种名称",
    "对比标的",
    "国内价格",
    "国际人民币价格",
    "价差",
    "价差百分比(%)",
]


def level_badge(level: str) -> str:
    return {
        "INFO": "🔵 INFO",
        "WARNING": "🟡 WARNING",
        "CRITICAL": "🔴 CRITICAL",
    }.get(level, level)


def build_futures_live_tables(
    data: Iterable[FuturesData], signals: Iterable[Signal]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    signal_map = {signal.asset: level_badge(signal.level) for signal in signals}
    rows = []
    for item in data:
        annualized = item.discount_rate * (365 / max(item.days_to_maturity, 1))
        maturity_date = (datetime.now() + timedelta(days=item.days_to_maturity)).strftime(
            "%Y-%m-%d"
        )
        rows.append(
            {
                "名称": item.symbol,
                "期指价格": round(item.price, 2),
                "指数点位": round(item.spot_price, 2),
                "贴水点数": round(item.spot_price - item.price, 2),
                "贴水率(%)": round(item.discount_rate, 4),
                "年化贴水率(%)": round(annualized, 4),
                "时间": item.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "到期日": maturity_date,
                "剩余天数": item.days_to_maturity,
                "单点指数价格": round(item.contract_multiplier, 2),
                "一手市值": round(item.notional_per_lot, 2),
                "保证金比例": round(item.margin_ratio, 2),
                "单手保证金": round(item.margin_required_per_lot, 2),
                "品种": item.product_code,
                "信号": signal_map.get(item.symbol, ""),
                "_product_order": FUTURES_PRODUCT_ORDER.get(item.product_code, 999),
                "_contract_order": int(item.symbol[-4:]) if item.symbol[-4:].isdigit() else 9999,
            }
        )

    signal_rows = [
        {
            "级别": level_badge(signal.level),
            "标的": signal.asset,
            "策略": signal.strategy_name,
            "详情": signal.message.replace("\n", " | "),
        }
        for signal in signals
    ]

    df = pd.DataFrame(rows)
    if df.empty:
        return df, pd.DataFrame(signal_rows)

    df = df.sort_values(by=["_product_order", "_contract_order", "名称"]).drop(
        columns=["_product_order", "_contract_order"]
    )
    remaining_columns = [col for col in df.columns if col not in FUTURES_FRONT_COLUMNS]
    df = df[FUTURES_FRONT_COLUMNS + remaining_columns]
    return df, pd.DataFrame(signal_rows)


def build_metals_live_tables(
    data: Iterable[MetalArbitrageData], signals: Iterable[Signal]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    signal_map = {signal.asset: level_badge(signal.level) for signal in signals}
    rows = []
    for item in data:
        asset = f"{item.metal_name} vs {item.benchmark_display_name}"
        rows.append(
            {
                "品种名称": item.metal_name,
                "对比标的": item.benchmark_display_name,
                "国内价格": round(item.dom_price, 2),
                "国际人民币价格": round(item.for_price_cny, 2),
                "价差": round(item.spread, 2),
                "价差百分比(%)": round(item.spread_pct, 4),
                "品种": item.metal_symbol,
                "分类": item.category,
                "国际美元价": round(item.for_price_usd, 4),
                "汇率": round(item.exchange_rate, 4),
                "隐含汇率": round(item.implied_rate, 4),
                "国内时间": item.dom_time,
                "国际时间": item.for_time,
                "国际日期": item.for_date,
                "人民币报价": "API" if item.used_api_cny_quote else "汇率换算",
                "信号": signal_map.get(asset, ""),
                "_symbol_order": METALS_SYMBOL_ORDER.get(item.metal_symbol, 999),
            }
        )

    signal_rows = [
        {
            "级别": level_badge(signal.level),
            "标的": signal.asset,
            "策略": signal.strategy_name,
            "详情": signal.message.replace("\n", " | "),
        }
        for signal in signals
    ]

    df = pd.DataFrame(rows)
    if df.empty:
        return df, pd.DataFrame(signal_rows)

    df = df.sort_values(by=["_symbol_order", "对比标的"]).drop(columns=["_symbol_order"])
    remaining_columns = [col for col in df.columns if col not in METALS_FRONT_COLUMNS]
    df = df[METALS_FRONT_COLUMNS + remaining_columns]
    return df, pd.DataFrame(signal_rows)
