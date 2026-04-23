from __future__ import annotations

from pathlib import Path
from typing import Any

from config.settings import (
    SYNCABLE_RUNTIME_FIELDS,
    get_local_runtime_config_path,
    save_local_runtime_config,
    settings,
)


GUI_CONFIG_FIELDS = [
    "ENABLE_FUTURES_MONITOR",
    "ENABLE_CONVERTIBLE_MONITOR",
    "ENABLE_SENTIMENT_MONITOR",
    "ENABLE_METALS_MONITOR",
    "ENABLE_PREMIUM_MONITOR",
    "ENABLE_FUTURES_CRUISE",
    "ENABLE_FUTURES_WATCH",
    "ENABLE_CONVERTIBLE_CRUISE",
    "ENABLE_CONVERTIBLE_WATCH",
    "ENABLE_SENTIMENT_CRUISE",
    "ENABLE_METALS_CRUISE",
    "ENABLE_METALS_WATCH",
    "ENABLE_PREMIUM_CRUISE",
    "ENABLE_PREMIUM_WATCH",
    "ENABLE_FUTURES_DISCOUNT_PERCENT_THRESHOLD",
    "FUTURES_DISCOUNT_PERCENT_THRESHOLD",
    "ENABLE_FUTURES_DISCOUNT_RATE_THRESHOLD",
    "FUTURES_DISCOUNT_RATE_THRESHOLD",
    "ENABLE_CB_NEGATIVE_PREMIUM_THRESHOLD",
    "CB_NEGATIVE_PREMIUM_THRESHOLD",
    "ENABLE_CB_SAFE_PRICE_THRESHOLD",
    "CB_SAFE_PRICE_THRESHOLD",
    "ENABLE_CB_DOUBLE_LOW_THRESHOLD",
    "CB_DOUBLE_LOW_THRESHOLD",
    "ENABLE_CB_YTM_THRESHOLD",
    "CB_YTM_THRESHOLD",
    "ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD",
    "SENTIMENT_HOT_SCORE_THRESHOLD",
    "ENABLE_SENTIMENT_PULSE_THRESHOLD",
    "SENTIMENT_PULSE_THRESHOLD",
    "FUTURES_CRUISE_INTERVAL_MINUTES",
    "FUTURES_WATCH_INTERVAL_SECONDS",
    "FUTURES_MORNING_START",
    "FUTURES_MORNING_END",
    "FUTURES_AFTERNOON_START",
    "FUTURES_AFTERNOON_END",
    "FUTURES_NIGHT_START",
    "FUTURES_NIGHT_END",
    "CONVERTIBLE_CRUISE_INTERVAL_MINUTES",
    "CONVERTIBLE_WATCH_INTERVAL_SECONDS",
    "CONVERTIBLE_MORNING_START",
    "CONVERTIBLE_MORNING_END",
    "CONVERTIBLE_AFTERNOON_START",
    "CONVERTIBLE_AFTERNOON_END",
    "CONVERTIBLE_NIGHT_START",
    "CONVERTIBLE_NIGHT_END",
    "SENTIMENT_CRUISE_INTERVAL_MINUTES",
    "SENTIMENT_MORNING_START",
    "SENTIMENT_MORNING_END",
    "SENTIMENT_AFTERNOON_START",
    "SENTIMENT_AFTERNOON_END",
    "SENTIMENT_NIGHT_START",
    "SENTIMENT_NIGHT_END",
    "METALS_CRUISE_INTERVAL_MINUTES",
    "METALS_WATCH_INTERVAL_SECONDS",
    "METALS_MORNING_START",
    "METALS_MORNING_END",
    "METALS_AFTERNOON_START",
    "METALS_AFTERNOON_END",
    "METALS_NIGHT_START",
    "METALS_NIGHT_END",
    "PREMIUM_CRUISE_INTERVAL_MINUTES",
    "PREMIUM_WATCH_INTERVAL_SECONDS",
    "PREMIUM_MORNING_START",
    "PREMIUM_MORNING_END",
    "PREMIUM_AFTERNOON_START",
    "PREMIUM_AFTERNOON_END",
    "PREMIUM_NIGHT_START",
    "PREMIUM_NIGHT_END",
    "COOLDOWN_MINUTES",
    "DATA_RETENTION_DAYS",
]


def get_env_path() -> Path:
    return get_local_runtime_config_path()


def get_gui_config_values() -> dict[str, Any]:
    return {field: getattr(settings, field) for field in GUI_CONFIG_FIELDS}


def serialize_env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_env_updates(updates: dict[str, Any], env_path: Path | None = None) -> Path:
    config_path = env_path or get_env_path()
    filtered_updates = {
        key: value for key, value in updates.items() if key in SYNCABLE_RUNTIME_FIELDS
    }
    save_local_runtime_config(settings, filtered_updates, path=config_path)
    return config_path


def apply_runtime_updates(updates: dict[str, Any]) -> dict[str, Any]:
    filtered_updates = {
        key: value for key, value in updates.items() if key in GUI_CONFIG_FIELDS
    }
    settings.apply_updates(filtered_updates)
    return get_gui_config_values()
