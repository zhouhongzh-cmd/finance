from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd

from models.market_data import FuturesData, MetalArbitrageData, PremiumArbitrageData
from models.signals import Signal


FUTURES_PRODUCT_ORDER = {"IH": 0, "IF": 1, "IC": 2, "IM": 3}
FUTURES_FRONT_COLUMNS = [
    "名称",
    "期指价格",
    "指数点位",
    "方向",
    "价差点数",
    "价差率(%)",
    "年化价差率(%)",
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

PREMIUM_GROUP_ORDER = {"BTC": 0, "A50": 1}
PREMIUM_FRONT_COLUMNS = [
    "资产组",
    "市场",
    "现货代码",
    "现货价格",
    "期货代码",
    "期货价格",
    "溢价值",
    "溢价率(%)",
    "年化溢价率(%)",
    "剩余天数",
    "状态",
    "时间",
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
        direction = "贴水" if item.discount_rate >= 0 else "升水"
        rate_value = item.discount_rate if item.discount_rate >= 0 else -item.discount_rate
        annualized_value = annualized if annualized >= 0 else -annualized
        rows.append(
            {
                "名称": item.symbol,
                "期指价格": round(item.price, 2),
                "指数点位": round(item.spot_price, 2),
                "方向": direction,
                "价差点数": round(abs(item.spot_price - item.price), 2),
                "价差率(%)": round(rate_value, 4),
                "年化价差率(%)": round(annualized_value, 4),
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


def build_premium_live_tables(
    data: Iterable[PremiumArbitrageData], signals: Iterable[Signal]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    signal_map = {signal.asset: level_badge(signal.level) for signal in signals}
    rows = []
    for item in data:
        asset = "BTC 期现" if item.asset_group == "BTC" else f"A50 {item.future_name or item.future_symbol}"
        annualized = (
            item.premium_rate * (365 / max(item.days_to_maturity, 1))
            if item.days_to_maturity is not None
            else None
        )
        rows.append(
            {
                "资产组": item.asset_group,
                "市场": "加密货币" if item.asset_group == "BTC" else "A50",
                "现货代码": item.spot_symbol,
                "现货名称": item.spot_name,
                "现货价格": round(item.spot_price, 4),
                "期货代码": item.future_symbol,
                "期货名称": item.future_name,
                "期货价格": round(item.future_price, 4),
                "溢价值": round(item.premium, 4),
                "溢价率(%)": round(item.premium_rate, 4),
                "年化溢价率(%)": round(annualized, 4) if annualized is not None else "N/A",
                "剩余天数": item.days_to_maturity if item.days_to_maturity is not None else "N/A",
                "状态": "升水" if item.state == "contango" else "贴水",
                "现货来源": item.source_spot,
                "期货来源": item.source_future,
                "时间": item.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "信号": signal_map.get(asset, ""),
                "_group_order": PREMIUM_GROUP_ORDER.get(item.asset_group, 999),
                "_contract_order": 0 if item.future_symbol == "CN00Y" else 1,
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

    df = df.sort_values(by=["_group_order", "_contract_order", "期货代码"]).drop(
        columns=["_group_order", "_contract_order"]
    )
    remaining_columns = [col for col in df.columns if col not in PREMIUM_FRONT_COLUMNS]
    df = df[PREMIUM_FRONT_COLUMNS + remaining_columns]
    return df, pd.DataFrame(signal_rows)
