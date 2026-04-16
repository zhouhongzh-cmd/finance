from __future__ import annotations

from typing import Any


OUNCE_TO_GRAM = 31.1034768
SILVER_CONVERSION = 32.1507
COMEX_COPPER_FACTOR = 22.0462
DEFAULT_EXCHANGE_RATE = 7.20


METALS_CONFIG: dict[str, dict[str, Any]] = {
    "AU0": {
        "name": "黄金",
        "category": "precious",
        "domestic_symbol": "au0",
        "domestic_name": "沪金主力",
        "domestic_unit": "元/克",
        "foreign_benchmarks": [
            {
                "name": "伦敦金",
                "symbol": "XAU",
                "display_name": "LME金",
                "unit_factor": OUNCE_TO_GRAM,
                "has_cny_quote": True,
                "rate_direction": "div",
            },
            {
                "name": "COMEX黄金",
                "symbol": "GC",
                "display_name": "COMEX GC",
                "unit_factor": OUNCE_TO_GRAM,
                "has_cny_quote": True,
                "rate_direction": "div",
            },
        ],
        "alert_threshold": {"upper": 1.0, "lower": -1.0},
    },
    "AG0": {
        "name": "白银",
        "category": "precious",
        "domestic_symbol": "ag0",
        "domestic_name": "沪银主力",
        "domestic_unit": "元/千克",
        "foreign_benchmarks": [
            {
                "name": "伦敦银",
                "symbol": "XAG",
                "display_name": "LME银",
                "unit_factor": SILVER_CONVERSION,
                "has_cny_quote": True,
                "rate_direction": "div_kg",
            },
            {
                "name": "COMEX白银",
                "symbol": "SI",
                "display_name": "COMEX SI",
                "unit_factor": SILVER_CONVERSION,
                "has_cny_quote": True,
                "rate_direction": "div_kg",
            },
        ],
        "alert_threshold": {"upper": 2.0, "lower": -2.0},
    },
    "PT0": {
        "name": "铂金",
        "category": "precious",
        "domestic_symbol": "pt0",
        "domestic_name": "沪铂主力",
        "domestic_unit": "元/克",
        "foreign_benchmarks": [
            {
                "name": "伦敦铂",
                "symbol": "XPT",
                "display_name": "LME铂",
                "unit_factor": OUNCE_TO_GRAM,
                "has_cny_quote": True,
                "rate_direction": "div",
            },
        ],
        "alert_threshold": {"upper": 2.0, "lower": -2.0},
    },
    "PD0": {
        "name": "钯金",
        "category": "precious",
        "domestic_symbol": "pd0",
        "domestic_name": "沪钯主力",
        "domestic_unit": "元/克",
        "foreign_benchmarks": [
            {
                "name": "伦敦钯",
                "symbol": "XPD",
                "display_name": "LME钯",
                "unit_factor": OUNCE_TO_GRAM,
                "has_cny_quote": True,
                "rate_direction": "div",
            },
        ],
        "alert_threshold": {"upper": 2.0, "lower": -2.0},
    },
    "CU0": {
        "name": "铜",
        "category": "base",
        "domestic_symbol": "cu0",
        "domestic_name": "沪铜主力",
        "domestic_unit": "元/吨",
        "foreign_benchmarks": [
            {
                "name": "LME铜3个月",
                "symbol": "CAD",
                "display_name": "LME铜",
                "unit_factor": 1.0,
                "has_cny_quote": True,
                "rate_direction": "base",
            },
            {
                "name": "COMEX铜",
                "symbol": "HG",
                "display_name": "COMEX铜",
                "unit_factor": COMEX_COPPER_FACTOR,
                "has_cny_quote": True,
                "rate_direction": "mul",
            },
        ],
        "alert_threshold": {"upper": 1.5, "lower": -1.5},
    },
    "AL0": {
        "name": "铝",
        "category": "base",
        "domestic_symbol": "al0",
        "domestic_name": "沪铝主力",
        "domestic_unit": "元/吨",
        "foreign_benchmarks": [
            {
                "name": "LME铝3个月",
                "symbol": "AHD",
                "display_name": "LME铝",
                "unit_factor": 1.0,
                "has_cny_quote": True,
                "rate_direction": "base",
            },
        ],
        "alert_threshold": {"upper": 1.5, "lower": -1.5},
    },
    "ZN0": {
        "name": "锌",
        "category": "base",
        "domestic_symbol": "zn0",
        "domestic_name": "沪锌主力",
        "domestic_unit": "元/吨",
        "foreign_benchmarks": [
            {
                "name": "LME锌3个月",
                "symbol": "ZSD",
                "display_name": "LME锌",
                "unit_factor": 1.0,
                "has_cny_quote": True,
                "rate_direction": "base",
            },
        ],
        "alert_threshold": {"upper": 1.5, "lower": -1.5},
    },
    "PB0": {
        "name": "铅",
        "category": "base",
        "domestic_symbol": "pb0",
        "domestic_name": "沪铅主力",
        "domestic_unit": "元/吨",
        "foreign_benchmarks": [
            {
                "name": "LME铅3个月",
                "symbol": "PBD",
                "display_name": "LME铅",
                "unit_factor": 1.0,
                "has_cny_quote": True,
                "rate_direction": "base",
            },
        ],
        "alert_threshold": {"upper": 1.5, "lower": -1.5},
    },
    "NI0": {
        "name": "镍",
        "category": "base",
        "domestic_symbol": "ni0",
        "domestic_name": "沪镍主力",
        "domestic_unit": "元/吨",
        "foreign_benchmarks": [
            {
                "name": "LME镍3个月",
                "symbol": "NID",
                "display_name": "LME镍",
                "unit_factor": 1.0,
                "has_cny_quote": True,
                "rate_direction": "base",
            },
        ],
        "alert_threshold": {"upper": 2.0, "lower": -2.0},
    },
    "SN0": {
        "name": "锡",
        "category": "base",
        "domestic_symbol": "sn0",
        "domestic_name": "沪锡主力",
        "domestic_unit": "元/吨",
        "foreign_benchmarks": [
            {
                "name": "LME锡3个月",
                "symbol": "SND",
                "display_name": "LME锡",
                "unit_factor": 1.0,
                "has_cny_quote": True,
                "rate_direction": "base",
            },
        ],
        "alert_threshold": {"upper": 2.0, "lower": -2.0},
    },
}


def get_default_metals_thresholds() -> dict[str, dict[str, float | bool]]:
    return {
        symbol: {
            "upper": abs(float(item["alert_threshold"]["upper"])),
            "lower": -abs(float(item["alert_threshold"]["lower"])),
            "upper_enabled": True,
            "lower_enabled": True,
        }
        for symbol, item in METALS_CONFIG.items()
    }
