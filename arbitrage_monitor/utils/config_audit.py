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
        payload[f"METALS_THRESHOLD.{symbol}.upper_enabled"] = bool(
            row.get("upper_enabled", True)
        )
        payload[f"METALS_THRESHOLD.{symbol}.lower_enabled"] = bool(
            row.get("lower_enabled", True)
        )
    return payload


def flatten_futures_threshold_values(rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for row in rows:
        product = row["product_code"]
        payload[f"FUTURES_THRESHOLD.{product}.backwardation_enabled"] = bool(
            row["backwardation_enabled"]
        )
        payload[f"FUTURES_THRESHOLD.{product}.backwardation_threshold"] = float(
            row["backwardation_threshold"]
        )
        payload[f"FUTURES_THRESHOLD.{product}.annualized_backwardation_threshold"] = float(
            row["annualized_backwardation_threshold"]
        )
        payload[f"FUTURES_THRESHOLD.{product}.contango_enabled"] = bool(
            row["contango_enabled"]
        )
        payload[f"FUTURES_THRESHOLD.{product}.contango_threshold"] = float(
            row["contango_threshold"]
        )
        payload[f"FUTURES_THRESHOLD.{product}.annualized_contango_threshold"] = float(
            row["annualized_contango_threshold"]
        )
    return payload


def flatten_premium_threshold_values(rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for row in rows:
        asset_group = row["asset_group"]
        payload[f"PREMIUM_THRESHOLD.{asset_group}.contango_enabled"] = bool(
            row["contango_enabled"]
        )
        payload[f"PREMIUM_THRESHOLD.{asset_group}.contango_threshold"] = float(
            row["contango_threshold"]
        )
        payload[f"PREMIUM_THRESHOLD.{asset_group}.annualized_contango_enabled"] = bool(
            row["annualized_contango_enabled"]
        )
        payload[f"PREMIUM_THRESHOLD.{asset_group}.annualized_contango_threshold"] = float(
            row["annualized_contango_threshold"]
        )
        payload[f"PREMIUM_THRESHOLD.{asset_group}.backwardation_enabled"] = bool(
            row["backwardation_enabled"]
        )
        payload[f"PREMIUM_THRESHOLD.{asset_group}.backwardation_threshold"] = float(
            row["backwardation_threshold"]
        )
        payload[f"PREMIUM_THRESHOLD.{asset_group}.annualized_backwardation_enabled"] = bool(
            row["annualized_backwardation_enabled"]
        )
        payload[f"PREMIUM_THRESHOLD.{asset_group}.annualized_backwardation_threshold"] = float(
            row["annualized_backwardation_threshold"]
        )
    return payload
