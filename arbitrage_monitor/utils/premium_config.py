from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any


PREMIUM_ASSETS: dict[str, str] = {
    "BTC": "比特币",
    "A50": "富时中国A50",
}

DEFAULT_PREMIUM_THRESHOLDS: dict[str, dict[str, float | bool]] = {
    "BTC": {
        "upper_enabled": True,
        "upper": 0.5,
        "annualized_upper_enabled": True,
        "annualized_upper": 8.0,
        "lower_enabled": True,
        "lower": -0.5,
        "annualized_lower_enabled": True,
        "annualized_lower": -8.0,
    },
    "A50": {
        "upper_enabled": True,
        "upper": 0.5,
        "annualized_upper_enabled": True,
        "annualized_upper": 8.0,
        "lower_enabled": True,
        "lower": -0.5,
        "annualized_lower_enabled": True,
        "annualized_lower": -8.0,
    },
}

_threshold_lock = threading.RLock()
_threshold_cache: dict[str, dict[str, float | bool]] | None = None


def get_premium_thresholds_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "premium_thresholds.json"


def get_local_premium_thresholds_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "premium_thresholds.local.json"


def _load_threshold_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _with_aliases(values: dict[str, float | bool]) -> dict[str, float | bool]:
    upper = float(values["upper"])
    lower = float(values["lower"])
    upper_enabled = bool(values.get("upper_enabled", True))
    lower_enabled = bool(values.get("lower_enabled", True))
    annualized_upper = float(values["annualized_upper"])
    annualized_lower = float(values["annualized_lower"])
    annualized_upper_enabled = bool(values.get("annualized_upper_enabled", upper_enabled))
    annualized_lower_enabled = bool(values.get("annualized_lower_enabled", lower_enabled))
    return {
        "upper_enabled": upper_enabled,
        "upper": upper,
        "annualized_upper_enabled": annualized_upper_enabled,
        "annualized_upper": annualized_upper,
        "lower_enabled": lower_enabled,
        "lower": lower,
        "annualized_lower_enabled": annualized_lower_enabled,
        "annualized_lower": annualized_lower,
        "contango_enabled": upper_enabled,
        "contango_threshold": upper,
        "annualized_contango_enabled": annualized_upper_enabled,
        "annualized_contango_threshold": annualized_upper,
        "backwardation_enabled": lower_enabled,
        "backwardation_threshold": abs(lower),
        "annualized_backwardation_enabled": annualized_lower_enabled,
        "annualized_backwardation_threshold": abs(annualized_lower),
    }


def _serialize_thresholds(
    thresholds: dict[str, dict[str, float | bool]]
) -> dict[str, dict[str, float | bool]]:
    return {
        asset_group: _with_aliases(values)
        for asset_group, values in thresholds.items()
    }


def _normalize_thresholds(raw: dict[str, Any] | None) -> dict[str, dict[str, float | bool]]:
    normalized = deepcopy(DEFAULT_PREMIUM_THRESHOLDS)
    if not raw:
        return normalized

    for asset_group, values in raw.items():
        if asset_group not in normalized or not isinstance(values, dict):
            continue
        default = normalized[asset_group]
        upper = float(
            values.get(
                "upper",
                values.get("contango_threshold", values.get("backwardation_threshold", default["upper"])),
            )
        )
        lower = float(
            values.get(
                "lower",
                -abs(values.get("backwardation_threshold", default["lower"])),
            )
        )
        annualized_upper = float(
            values.get(
                "annualized_upper",
                values.get(
                    "annualized_contango_threshold",
                    values.get("annualized_backwardation_threshold", default["annualized_upper"]),
                ),
            )
        )
        annualized_lower = float(
            values.get(
                "annualized_lower",
                -abs(values.get("annualized_backwardation_threshold", default["annualized_lower"])),
            )
        )
        upper_enabled = bool(
            values.get(
                "upper_enabled",
                values.get("contango_enabled", default["upper_enabled"]),
            )
        )
        lower_enabled = bool(
            values.get(
                "lower_enabled",
                values.get("backwardation_enabled", default["lower_enabled"]),
            )
        )
        normalized[asset_group] = {
            "upper_enabled": upper_enabled,
            "upper": abs(upper),
            "annualized_upper_enabled": bool(
                values.get("annualized_upper_enabled", values.get("annualized_contango_enabled", upper_enabled))
            ),
            "annualized_upper": abs(annualized_upper),
            "lower_enabled": lower_enabled,
            "lower": -abs(lower),
            "annualized_lower_enabled": bool(
                values.get("annualized_lower_enabled", values.get("annualized_backwardation_enabled", lower_enabled))
            ),
            "annualized_lower": -abs(annualized_lower),
        }
    return normalized


def _normalize_local_thresholds(raw: dict[str, Any] | None) -> dict[str, dict[str, float | bool]]:
    normalized: dict[str, dict[str, float | bool]] = {}
    if not raw:
        return normalized

    parsed = _normalize_thresholds(raw)
    for asset_group in DEFAULT_PREMIUM_THRESHOLDS:
        if asset_group in parsed and asset_group in raw:
            normalized[asset_group] = parsed[asset_group]
    return normalized


def load_premium_thresholds(force_reload: bool = False) -> dict[str, dict[str, float | bool]]:
    global _threshold_cache

    with _threshold_lock:
        if _threshold_cache is not None and not force_reload:
            return deepcopy(_threshold_cache)

        shared_path = get_premium_thresholds_path()
        if not shared_path.exists():
            shared_path.parent.mkdir(parents=True, exist_ok=True)
            shared_path.write_text(
                json.dumps(_serialize_thresholds(DEFAULT_PREMIUM_THRESHOLDS), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        shared_payload = _load_threshold_payload(shared_path)
        shared_thresholds = _normalize_thresholds(shared_payload)
        serialized_shared = _serialize_thresholds(shared_thresholds)
        if shared_payload != serialized_shared:
            shared_path.write_text(
                json.dumps(serialized_shared, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        local_path = get_local_premium_thresholds_path()
        local_payload = _load_threshold_payload(local_path) if local_path.exists() else None
        local_thresholds = _normalize_local_thresholds(local_payload)
        serialized_local = _serialize_thresholds(local_thresholds)
        if local_payload is not None and local_payload != serialized_local:
            local_path.write_text(
                json.dumps(serialized_local, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        effective = deepcopy(shared_thresholds)
        for asset_group, values in local_thresholds.items():
            effective[asset_group] = values

        _threshold_cache = _serialize_thresholds(effective)
        return deepcopy(_threshold_cache)


def save_premium_thresholds(thresholds: dict[str, dict[str, float | bool]]) -> Path:
    global _threshold_cache

    with _threshold_lock:
        normalized = _normalize_local_thresholds(thresholds)
        shared_thresholds = _normalize_thresholds(_load_threshold_payload(get_premium_thresholds_path()))
        local_only = {
            asset_group: values
            for asset_group, values in normalized.items()
            if values != shared_thresholds.get(asset_group)
        }
        path = get_local_premium_thresholds_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_serialize_thresholds(local_only), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _threshold_cache = None
        load_premium_thresholds(force_reload=True)
        return path


def reset_premium_thresholds() -> Path:
    global _threshold_cache

    with _threshold_lock:
        path = get_local_premium_thresholds_path()
        if path.exists():
            path.unlink()
        _threshold_cache = None
    load_premium_thresholds(force_reload=True)
    return get_premium_thresholds_path()


def get_effective_premium_threshold(asset_group: str) -> dict[str, float | bool]:
    normalized = asset_group.upper()
    thresholds = load_premium_thresholds()
    if normalized in thresholds:
        return thresholds[normalized]
    return _with_aliases(
        {
            "upper_enabled": True,
            "upper": 0.5,
            "annualized_upper_enabled": True,
            "annualized_upper": 8.0,
            "lower_enabled": True,
            "lower": -0.5,
            "annualized_lower_enabled": True,
            "annualized_lower": -8.0,
        }
    )


def get_premium_config_rows() -> list[dict[str, Any]]:
    thresholds = load_premium_thresholds()
    return [
        {
            "asset_group": asset_group,
            "name": PREMIUM_ASSETS[asset_group],
            **thresholds[asset_group],
        }
        for asset_group in PREMIUM_ASSETS
    ]
