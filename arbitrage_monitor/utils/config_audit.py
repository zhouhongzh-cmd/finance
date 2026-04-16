from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from utils.db_manager import DBManager


db_manager = DBManager()


def _serialize_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def record_config_changes(
    old_values: dict[str, Any],
    new_values: dict[str, Any],
    *,
    source: str,
    destination: str,
    immediate_effect: bool = True,
) -> int:
    changed_at = datetime.now().isoformat()
    all_keys = sorted(set(old_values) | set(new_values))
    rows = []
    for key in all_keys:
        old_value = old_values.get(key)
        new_value = new_values.get(key)
        if old_value == new_value:
            continue
        rows.append(
            {
                "changed_at": changed_at,
                "config_key": key,
                "old_value": _serialize_value(old_value),
                "new_value": _serialize_value(new_value),
                "source": source,
                "destination": destination,
                "immediate_effect": immediate_effect,
            }
        )

    db_manager.save_config_changes(rows)
    return len(rows)


def flatten_threshold_values(rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for row in rows:
        symbol = row["symbol"]
        payload[f"METALS_THRESHOLD.{symbol}.upper"] = float(row["upper"])
        payload[f"METALS_THRESHOLD.{symbol}.lower"] = float(row["lower"])
        payload[f"METALS_THRESHOLD.{symbol}.upper_enabled"] = bool(row.get("upper_enabled", True))
        payload[f"METALS_THRESHOLD.{symbol}.lower_enabled"] = bool(row.get("lower_enabled", True))
    return payload


def flatten_futures_threshold_values(rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for row in rows:
        product = row["product_code"]
        payload[f"FUTURES_THRESHOLD.{product}.upper_enabled"] = bool(row["upper_enabled"])
        payload[f"FUTURES_THRESHOLD.{product}.upper"] = float(row["upper"])
        payload[f"FUTURES_THRESHOLD.{product}.annualized_upper_enabled"] = bool(
            row["annualized_upper_enabled"]
        )
        payload[f"FUTURES_THRESHOLD.{product}.annualized_upper"] = float(row["annualized_upper"])
        payload[f"FUTURES_THRESHOLD.{product}.lower_enabled"] = bool(row["lower_enabled"])
        payload[f"FUTURES_THRESHOLD.{product}.lower"] = float(row["lower"])
        payload[f"FUTURES_THRESHOLD.{product}.annualized_lower_enabled"] = bool(
            row["annualized_lower_enabled"]
        )
        payload[f"FUTURES_THRESHOLD.{product}.annualized_lower"] = float(row["annualized_lower"])
    return payload


def flatten_premium_threshold_values(rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for row in rows:
        asset_group = row["asset_group"]
        payload[f"PREMIUM_THRESHOLD.{asset_group}.upper_enabled"] = bool(row["upper_enabled"])
        payload[f"PREMIUM_THRESHOLD.{asset_group}.upper"] = float(row["upper"])
        payload[f"PREMIUM_THRESHOLD.{asset_group}.annualized_upper_enabled"] = bool(
            row["annualized_upper_enabled"]
        )
        payload[f"PREMIUM_THRESHOLD.{asset_group}.annualized_upper"] = float(row["annualized_upper"])
        payload[f"PREMIUM_THRESHOLD.{asset_group}.lower_enabled"] = bool(row["lower_enabled"])
        payload[f"PREMIUM_THRESHOLD.{asset_group}.lower"] = float(row["lower"])
        payload[f"PREMIUM_THRESHOLD.{asset_group}.annualized_lower_enabled"] = bool(
            row["annualized_lower_enabled"]
        )
        payload[f"PREMIUM_THRESHOLD.{asset_group}.annualized_lower"] = float(row["annualized_lower"])
    return payload
