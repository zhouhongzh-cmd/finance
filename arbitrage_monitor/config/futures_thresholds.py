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
    return {product: _with_aliases(values) for product, values in thresholds.items()}


def _build_default_thresholds_from_runtime(
    runtime_payload: dict[str, Any],
) -> dict[str, dict[str, float | bool]]:
    enabled = bool(runtime_payload.get("ENABLE_FUTURES_DISCOUNT_PERCENT_THRESHOLD", True))
    percent = float(
        runtime_payload.get(
            "FUTURES_DISCOUNT_PERCENT_THRESHOLD",
            settings.FUTURES_DISCOUNT_PERCENT_THRESHOLD,
        )
    )
    annualized = float(
        runtime_payload.get(
            "FUTURES_DISCOUNT_RATE_THRESHOLD",
            settings.FUTURES_DISCOUNT_RATE_THRESHOLD,
        )
    )
    return {
        product: {
            "upper_enabled": enabled,
            "upper": percent,
            "annualized_upper_enabled": enabled,
            "annualized_upper": annualized,
            "lower_enabled": enabled,
            "lower": -percent,
            "annualized_lower_enabled": enabled,
            "annualized_lower": -annualized,
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
        default = normalized[product]
        upper = float(
            values.get(
                "upper",
                values.get(
                    "backwardation_threshold",
                    values.get("discount_percent_threshold", default["upper"]),
                ),
            )
        )
        lower = float(
            values.get(
                "lower",
                -abs(
                    values.get(
                        "contango_threshold",
                        default["lower"],
                    )
                ),
            )
        )
        annualized_upper = float(
            values.get(
                "annualized_upper",
                values.get(
                    "annualized_backwardation_threshold",
                    values.get("annualized_discount_threshold", default["annualized_upper"]),
                ),
            )
        )
        annualized_lower = float(
            values.get(
                "annualized_lower",
                -abs(
                    values.get(
                        "annualized_contango_threshold",
                        default["annualized_lower"],
                    )
                ),
            )
        )
        upper_enabled = bool(
            values.get(
                "upper_enabled",
                values.get(
                    "backwardation_enabled",
                    values.get("enabled", default["upper_enabled"]),
                ),
            )
        )
        lower_enabled = bool(
            values.get(
                "lower_enabled",
                values.get(
                    "contango_enabled",
                    values.get("enabled", default["lower_enabled"]),
                ),
            )
        )
        normalized[product] = {
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


def _normalize_local_thresholds(
    raw: dict[str, Any] | None,
    defaults: dict[str, dict[str, float | bool]],
) -> dict[str, dict[str, float | bool]]:
    if not raw:
        return {}
    return _normalize_thresholds(raw, defaults)


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

        shared_defaults = _build_default_thresholds_from_runtime(
            load_shared_runtime_config(settings)
        )
        shared_path = get_futures_thresholds_path()
        shared_payload = _load_threshold_payload(shared_path) if shared_path.exists() else None
        shared_thresholds = _normalize_thresholds(shared_payload, shared_defaults)
        serialized_shared = _serialize_thresholds(shared_thresholds)
        if not shared_path.exists() or shared_payload != serialized_shared:
            shared_path.parent.mkdir(parents=True, exist_ok=True)
            shared_path.write_text(
                json.dumps(serialized_shared, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        local_path = get_local_futures_thresholds_path()
        local_payload = _load_threshold_payload(local_path) if local_path.exists() else None
        if local_payload is not None:
            local_thresholds = _normalize_local_thresholds(local_payload, shared_thresholds)
            serialized_local = _serialize_thresholds(local_thresholds)
            if local_payload != serialized_local:
                local_path.write_text(
                    json.dumps(serialized_local, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        else:
            local_thresholds = _build_legacy_local_overrides(shared_thresholds)

        effective = deepcopy(shared_thresholds)
        for product, values in local_thresholds.items():
            effective[product] = values

        _threshold_cache = _serialize_thresholds(effective)
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
            json.dumps(_serialize_thresholds(local_only), ensure_ascii=False, indent=2) + "\n",
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
    defaults = _serialize_thresholds(
        _build_default_thresholds_from_runtime(load_shared_runtime_config(settings))
    )
    return defaults.get(
        normalized,
        _with_aliases(
            {
                "upper_enabled": False,
                "upper": 1.0,
                "annualized_upper_enabled": False,
                "annualized_upper": 8.0,
                "lower_enabled": False,
                "lower": -1.0,
                "annualized_lower_enabled": False,
                "annualized_lower": -8.0,
            }
        ),
    )


def get_futures_config_rows() -> list[dict[str, Any]]:
    thresholds = load_futures_thresholds()
    return [
        {
            "product_code": product,
            "name": FUTURES_PRODUCTS[product],
            **thresholds[product],
        }
        for product in FUTURES_PRODUCTS
    ]
