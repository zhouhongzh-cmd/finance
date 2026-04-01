from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from config.settings import (
    load_local_runtime_config,
    load_shared_runtime_config,
    settings,
)


FUTURES_PRODUCTS: dict[str, str] = {
    "IH": "上证50",
    "IF": "沪深300",
    "IC": "中证500",
    "IM": "中证1000",
}

_threshold_lock = threading.RLock()
_threshold_cache: dict[str, dict[str, float | bool]] | None = None


def get_futures_thresholds_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "futures_thresholds.json"


def get_local_futures_thresholds_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "futures_thresholds.local.json"


def _load_threshold_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _build_default_thresholds_from_runtime(runtime_payload: dict[str, Any]) -> dict[str, dict[str, float | bool]]:
    enabled = bool(runtime_payload.get("ENABLE_FUTURES_DISCOUNT_PERCENT_THRESHOLD", True)) and bool(
        runtime_payload.get("ENABLE_FUTURES_DISCOUNT_RATE_THRESHOLD", True)
    )
    percent = float(runtime_payload.get("FUTURES_DISCOUNT_PERCENT_THRESHOLD", settings.FUTURES_DISCOUNT_PERCENT_THRESHOLD))
    annualized = float(runtime_payload.get("FUTURES_DISCOUNT_RATE_THRESHOLD", settings.FUTURES_DISCOUNT_RATE_THRESHOLD))
    return {
        product: {
            "enabled": enabled,
            "discount_percent_threshold": percent,
            "annualized_discount_threshold": annualized,
        }
        for product in FUTURES_PRODUCTS
    }


def _normalize_thresholds(
    raw: dict[str, Any] | None,
    defaults: dict[str, dict[str, float | bool]],
) -> dict[str, dict[str, float | bool]]:
    normalized = deepcopy(defaults)
    if not raw:
        return normalized

    for product, values in raw.items():
        if product not in normalized or not isinstance(values, dict):
            continue
        normalized[product] = {
            "enabled": bool(values.get("enabled", normalized[product]["enabled"])),
            "discount_percent_threshold": float(
                values.get(
                    "discount_percent_threshold",
                    normalized[product]["discount_percent_threshold"],
                )
            ),
            "annualized_discount_threshold": float(
                values.get(
                    "annualized_discount_threshold",
                    normalized[product]["annualized_discount_threshold"],
                )
            ),
        }
    return normalized


def _normalize_local_thresholds(
    raw: dict[str, Any] | None,
    defaults: dict[str, dict[str, float | bool]],
) -> dict[str, dict[str, float | bool]]:
    if not raw:
        return {}

    normalized: dict[str, dict[str, float | bool]] = {}
    for product, values in raw.items():
        if product not in defaults or not isinstance(values, dict):
            continue
        normalized[product] = {
            "enabled": bool(values.get("enabled", defaults[product]["enabled"])),
            "discount_percent_threshold": float(
                values.get(
                    "discount_percent_threshold",
                    defaults[product]["discount_percent_threshold"],
                )
            ),
            "annualized_discount_threshold": float(
                values.get(
                    "annualized_discount_threshold",
                    defaults[product]["annualized_discount_threshold"],
                )
            ),
        }
    return normalized


def _build_legacy_local_overrides(
    shared_thresholds: dict[str, dict[str, float | bool]],
) -> dict[str, dict[str, float | bool]]:
    local_runtime = load_local_runtime_config(settings)
    if not any(
        key in local_runtime
        for key in (
            "ENABLE_FUTURES_DISCOUNT_PERCENT_THRESHOLD",
            "ENABLE_FUTURES_DISCOUNT_RATE_THRESHOLD",
            "FUTURES_DISCOUNT_PERCENT_THRESHOLD",
            "FUTURES_DISCOUNT_RATE_THRESHOLD",
        )
    ):
        return {}

    shared_runtime = load_shared_runtime_config(settings)
    merged_runtime = shared_runtime.copy()
    merged_runtime.update(local_runtime)
    migrated = _build_default_thresholds_from_runtime(merged_runtime)
    return {
        product: values
        for product, values in migrated.items()
        if values != shared_thresholds.get(product)
    }


def load_futures_thresholds(force_reload: bool = False) -> dict[str, dict[str, float | bool]]:
    global _threshold_cache

    with _threshold_lock:
        if _threshold_cache is not None and not force_reload:
            return deepcopy(_threshold_cache)

        shared_defaults = _build_default_thresholds_from_runtime(load_shared_runtime_config(settings))
        shared_path = get_futures_thresholds_path()
        shared_payload = _load_threshold_payload(shared_path) if shared_path.exists() else None
        shared_thresholds = _normalize_thresholds(shared_payload, shared_defaults)
        if not shared_path.exists() or shared_payload != shared_thresholds:
            shared_path.parent.mkdir(parents=True, exist_ok=True)
            shared_path.write_text(
                json.dumps(shared_thresholds, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        local_path = get_local_futures_thresholds_path()
        local_payload = _load_threshold_payload(local_path) if local_path.exists() else None
        if local_payload is not None:
            local_thresholds = _normalize_local_thresholds(local_payload, shared_thresholds)
            if local_payload != local_thresholds:
                local_path.write_text(
                    json.dumps(local_thresholds, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        else:
            local_thresholds = _build_legacy_local_overrides(shared_thresholds)

        effective = deepcopy(shared_thresholds)
        for product, values in local_thresholds.items():
            effective[product] = {
                "enabled": bool(values["enabled"]),
                "discount_percent_threshold": float(values["discount_percent_threshold"]),
                "annualized_discount_threshold": float(values["annualized_discount_threshold"]),
            }

        _threshold_cache = effective
        return deepcopy(_threshold_cache)


def save_futures_thresholds(thresholds: dict[str, dict[str, float | bool]]) -> Path:
    global _threshold_cache

    with _threshold_lock:
        shared_thresholds = _normalize_thresholds(
            _load_threshold_payload(get_futures_thresholds_path()),
            _build_default_thresholds_from_runtime(load_shared_runtime_config(settings)),
        )
        normalized = _normalize_local_thresholds(thresholds, shared_thresholds)
        local_only = {
            product: values
            for product, values in normalized.items()
            if values != shared_thresholds.get(product)
        }
        path = get_local_futures_thresholds_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(local_only, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _threshold_cache = None
        load_futures_thresholds(force_reload=True)
        return path


def reset_futures_thresholds() -> Path:
    global _threshold_cache

    with _threshold_lock:
        path = get_local_futures_thresholds_path()
        if path.exists():
            path.unlink()
        _threshold_cache = None
    load_futures_thresholds(force_reload=True)
    return get_futures_thresholds_path()


def get_effective_futures_threshold(product_code: str) -> dict[str, float | bool]:
    normalized = product_code.upper()[:2]
    thresholds = load_futures_thresholds()
    if normalized in thresholds:
        return thresholds[normalized]
    defaults = _build_default_thresholds_from_runtime(load_shared_runtime_config(settings))
    return defaults.get(
        normalized,
        {
            "enabled": False,
            "discount_percent_threshold": 1.0,
            "annualized_discount_threshold": 8.0,
        },
    )


def get_futures_config_rows() -> list[dict[str, Any]]:
    thresholds = load_futures_thresholds()
    return [
        {
            "product_code": product,
            "name": FUTURES_PRODUCTS[product],
            "enabled": bool(thresholds[product]["enabled"]),
            "discount_percent_threshold": float(thresholds[product]["discount_percent_threshold"]),
            "annualized_discount_threshold": float(thresholds[product]["annualized_discount_threshold"]),
        }
        for product in FUTURES_PRODUCTS
    ]
