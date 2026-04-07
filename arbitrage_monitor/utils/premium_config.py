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
        "contango_enabled": True,
        "contango_threshold": 0.5,
        "annualized_contango_enabled": True,
        "annualized_contango_threshold": 8.0,
        "backwardation_enabled": True,
        "backwardation_threshold": -0.5,
        "annualized_backwardation_enabled": True,
        "annualized_backwardation_threshold": -8.0,
    },
    "A50": {
        "contango_enabled": True,
        "contango_threshold": 0.5,
        "annualized_contango_enabled": True,
        "annualized_contango_threshold": 8.0,
        "backwardation_enabled": True,
        "backwardation_threshold": -0.5,
        "annualized_backwardation_enabled": True,
        "annualized_backwardation_threshold": -8.0,
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


def _normalize_thresholds(raw: dict[str, Any] | None) -> dict[str, dict[str, float | bool]]:
    normalized = deepcopy(DEFAULT_PREMIUM_THRESHOLDS)
    if not raw:
        return normalized

    for asset_group, values in raw.items():
        if asset_group not in normalized or not isinstance(values, dict):
            continue
        normalized[asset_group] = {
            "contango_enabled": bool(
                values.get(
                    "contango_enabled",
                    values.get("upper_enabled", normalized[asset_group]["contango_enabled"]),
                )
            ),
            "contango_threshold": float(
                values.get(
                    "contango_threshold",
                    values.get("upper", normalized[asset_group]["contango_threshold"]),
                )
            ),
            "annualized_contango_enabled": bool(
                values.get(
                    "annualized_contango_enabled",
                    normalized[asset_group]["annualized_contango_enabled"],
                )
            ),
            "annualized_contango_threshold": float(
                values.get(
                    "annualized_contango_threshold",
                    normalized[asset_group]["annualized_contango_threshold"],
                )
            ),
            "backwardation_enabled": bool(
                values.get(
                    "backwardation_enabled",
                    values.get("lower_enabled", normalized[asset_group]["backwardation_enabled"]),
                )
            ),
            "backwardation_threshold": float(
                values.get(
                    "backwardation_threshold",
                    values.get("lower", normalized[asset_group]["backwardation_threshold"]),
                )
            ),
            "annualized_backwardation_enabled": bool(
                values.get(
                    "annualized_backwardation_enabled",
                    normalized[asset_group]["annualized_backwardation_enabled"],
                )
            ),
            "annualized_backwardation_threshold": float(
                values.get(
                    "annualized_backwardation_threshold",
                    normalized[asset_group]["annualized_backwardation_threshold"],
                )
            ),
        }
    return normalized


def _normalize_local_thresholds(raw: dict[str, Any] | None) -> dict[str, dict[str, float | bool]]:
    normalized: dict[str, dict[str, float | bool]] = {}
    if not raw:
        return normalized

    for asset_group, values in raw.items():
        if asset_group not in DEFAULT_PREMIUM_THRESHOLDS or not isinstance(values, dict):
            continue
        defaults = DEFAULT_PREMIUM_THRESHOLDS[asset_group]
        normalized[asset_group] = {
            "contango_enabled": bool(
                values.get("contango_enabled", values.get("upper_enabled", defaults["contango_enabled"]))
            ),
            "contango_threshold": float(
                values.get("contango_threshold", values.get("upper", defaults["contango_threshold"]))
            ),
            "annualized_contango_enabled": bool(
                values.get(
                    "annualized_contango_enabled",
                    defaults["annualized_contango_enabled"],
                )
            ),
            "annualized_contango_threshold": float(
                values.get(
                    "annualized_contango_threshold",
                    defaults["annualized_contango_threshold"],
                )
            ),
            "backwardation_enabled": bool(
                values.get(
                    "backwardation_enabled",
                    values.get("lower_enabled", defaults["backwardation_enabled"]),
                )
            ),
            "backwardation_threshold": float(
                values.get(
                    "backwardation_threshold",
                    values.get("lower", defaults["backwardation_threshold"]),
                )
            ),
            "annualized_backwardation_enabled": bool(
                values.get(
                    "annualized_backwardation_enabled",
                    defaults["annualized_backwardation_enabled"],
                )
            ),
            "annualized_backwardation_threshold": float(
                values.get(
                    "annualized_backwardation_threshold",
                    defaults["annualized_backwardation_threshold"],
                )
            ),
        }
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
                json.dumps(DEFAULT_PREMIUM_THRESHOLDS, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        shared_payload = _load_threshold_payload(shared_path)
        shared_thresholds = _normalize_thresholds(shared_payload)
        if shared_payload != shared_thresholds:
            shared_path.write_text(
                json.dumps(shared_thresholds, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        local_path = get_local_premium_thresholds_path()
        local_payload = _load_threshold_payload(local_path) if local_path.exists() else None
        local_thresholds = _normalize_local_thresholds(local_payload)
        if local_payload is not None and local_payload != local_thresholds:
            local_path.write_text(
                json.dumps(local_thresholds, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        effective = deepcopy(shared_thresholds)
        for asset_group, values in local_thresholds.items():
            effective[asset_group] = values

        _threshold_cache = effective
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
            json.dumps(local_only, ensure_ascii=False, indent=2) + "\n",
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
    return {
        "contango_enabled": True,
        "contango_threshold": 0.5,
        "annualized_contango_enabled": True,
        "annualized_contango_threshold": 8.0,
        "backwardation_enabled": True,
        "backwardation_threshold": -0.5,
        "annualized_backwardation_enabled": True,
        "annualized_backwardation_threshold": -8.0,
    }


def get_premium_config_rows() -> list[dict[str, Any]]:
    thresholds = load_premium_thresholds()
    return [
        {
            "asset_group": asset_group,
            "name": PREMIUM_ASSETS[asset_group],
            "contango_enabled": bool(thresholds[asset_group]["contango_enabled"]),
            "contango_threshold": float(thresholds[asset_group]["contango_threshold"]),
            "annualized_contango_enabled": bool(
                thresholds[asset_group]["annualized_contango_enabled"]
            ),
            "annualized_contango_threshold": float(
                thresholds[asset_group]["annualized_contango_threshold"]
            ),
            "backwardation_enabled": bool(thresholds[asset_group]["backwardation_enabled"]),
            "backwardation_threshold": float(thresholds[asset_group]["backwardation_threshold"]),
            "annualized_backwardation_enabled": bool(
                thresholds[asset_group]["annualized_backwardation_enabled"]
            ),
            "annualized_backwardation_threshold": float(
                thresholds[asset_group]["annualized_backwardation_threshold"]
            ),
        }
        for asset_group in PREMIUM_ASSETS
    ]
