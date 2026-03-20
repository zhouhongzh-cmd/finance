from __future__ import annotations

from pathlib import Path
from typing import Any

from config.settings import settings


GUI_CONFIG_FIELDS = [
    "ENABLE_FUTURES_MONITOR",
    "ENABLE_CONVERTIBLE_MONITOR",
    "ENABLE_SENTIMENT_MONITOR",
    "ENABLE_METALS_MONITOR",
    "FUTURES_DISCOUNT_RATE_THRESHOLD",
    "CB_NEGATIVE_PREMIUM_THRESHOLD",
    "CB_SAFE_PRICE_THRESHOLD",
    "CB_DOUBLE_LOW_THRESHOLD",
    "CB_YTM_THRESHOLD",
    "SENTIMENT_HOT_SCORE_THRESHOLD",
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
    "COOLDOWN_MINUTES",
    "DATA_RETENTION_DAYS",
]


def get_env_path() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def get_gui_config_values() -> dict[str, Any]:
    return {field: getattr(settings, field) for field in GUI_CONFIG_FIELDS}


def serialize_env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_env_updates(updates: dict[str, Any], env_path: Path | None = None) -> Path:
    env_path = env_path or get_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()
    else:
        existing_lines = []

    remaining_updates = {
        key: serialize_env_value(value)
        for key, value in updates.items()
        if key in GUI_CONFIG_FIELDS
    }

    new_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue

        key, _, _value = line.partition("=")
        normalized_key = key.strip()
        if normalized_key in remaining_updates:
            new_lines.append(f"{normalized_key}={remaining_updates.pop(normalized_key)}")
        else:
            new_lines.append(line)

    if remaining_updates:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        for key, value in remaining_updates.items():
            new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return env_path


def apply_runtime_updates(updates: dict[str, Any]) -> dict[str, Any]:
    filtered_updates = {key: value for key, value in updates.items() if key in GUI_CONFIG_FIELDS}
    settings.apply_updates(filtered_updates)
    return get_gui_config_values()
