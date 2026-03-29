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
