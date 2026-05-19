from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from config.premium_assets import (
    CRYPTO_PREMIUM_ASSETS,
    INDEX_PREMIUM_ASSETS,
    PREMIUM_ASSETS,
)


CONTRACT_BUCKETS: list[str] = [
    "PERP",
    "MONTHLY_CURRENT",
    "MONTHLY_NEXT",
    "QUARTERLY_CURRENT",
    "QUARTERLY_NEXT",
]
CONTRACT_BUCKET_LABELS: dict[str, str] = {
    "INDEX": "指数期货",
    "PERP": "永续",
    "MONTHLY_CURRENT": "当月",
    "MONTHLY_NEXT": "次月",
    "QUARTERLY_CURRENT": "近季",
    "QUARTERLY_NEXT": "次季",
}
CONTRACT_BUCKET_ORDER: dict[str, int] = {
    bucket: index for index, bucket in enumerate(CONTRACT_BUCKETS)
}
DELIVERY_SOURCE_BUCKETS: list[str] = [
    "MONTHLY_CURRENT",
    "MONTHLY_NEXT",
    "QUARTERLY_CURRENT",
    "QUARTERLY_NEXT",
]
THRESHOLD_BUCKETS: list[str] = ["PERP", "DELIVERY"]
THRESHOLD_BUCKET_LABELS: dict[str, str] = {
    "PERP": "永续",
    "DELIVERY": "交割合约共用",
}

NON_CRYPTO_PREMIUM_ASSETS: dict[str, str] = INDEX_PREMIUM_ASSETS


def _default_threshold_values() -> dict[str, float | bool]:
    return {
        "upper_enabled": True,
        "upper": 0.5,
        "annualized_upper_enabled": True,
        "annualized_upper": 8.0,
        "lower_enabled": True,
        "lower": -0.5,
        "annualized_lower_enabled": True,
        "annualized_lower": -8.0,
    }


DEFAULT_PREMIUM_THRESHOLDS: dict[str, dict[str, float | bool]] = {
    asset_group: _default_threshold_values()
    for asset_group in INDEX_PREMIUM_ASSETS
}
for asset_group in CRYPTO_PREMIUM_ASSETS:
    for bucket in THRESHOLD_BUCKETS:
        DEFAULT_PREMIUM_THRESHOLDS[f"{asset_group}_{bucket}"] = _default_threshold_values()


_threshold_lock = threading.RLock()
_threshold_cache: dict[str, dict[str, float | bool]] | None = None


def get_premium_thresholds_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "premium_thresholds.json"


def get_local_premium_thresholds_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "premium_thresholds.local.json"


def map_contract_bucket_to_threshold_bucket(contract_bucket: str | None) -> str:
    normalized_bucket = str(contract_bucket or "").upper()
    if normalized_bucket == "PERP":
        return "PERP"
    if normalized_bucket in DELIVERY_SOURCE_BUCKETS:
        return "DELIVERY"
    return normalized_bucket


def build_premium_threshold_key(asset_group: str, contract_bucket: str | None = None) -> str:
    normalized_asset = str(asset_group or "").upper()
    normalized_bucket = map_contract_bucket_to_threshold_bucket(contract_bucket)
    if normalized_asset in NON_CRYPTO_PREMIUM_ASSETS:
        return normalized_asset
    if normalized_bucket in THRESHOLD_BUCKET_LABELS:
        return f"{normalized_asset}_{normalized_bucket}"
    return normalized_asset


def split_premium_threshold_key(threshold_key: str) -> tuple[str, str]:
    normalized = str(threshold_key or "").upper()
    for bucket in THRESHOLD_BUCKETS:
        suffix = f"_{bucket}"
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)], bucket
    return normalized, ""


def is_crypto_threshold_key(threshold_key: str) -> bool:
    asset_group, contract_bucket = split_premium_threshold_key(threshold_key)
    return asset_group in CRYPTO_PREMIUM_ASSETS and contract_bucket in THRESHOLD_BUCKET_LABELS


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
        threshold_key: _with_aliases(values)
        for threshold_key, values in thresholds.items()
    }


def _normalize_threshold_values(
    values: dict[str, Any],
    default: dict[str, float | bool],
) -> dict[str, float | bool]:
    upper = float(
        values.get(
            "upper",
            values.get(
                "contango_threshold",
                values.get("backwardation_threshold", default["upper"]),
            ),
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
                values.get(
                    "annualized_backwardation_threshold",
                    default["annualized_upper"],
                ),
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
    return {
        "upper_enabled": upper_enabled,
        "upper": abs(upper),
        "annualized_upper_enabled": bool(
            values.get(
                "annualized_upper_enabled",
                values.get("annualized_contango_enabled", upper_enabled),
            )
        ),
        "annualized_upper": abs(annualized_upper),
        "lower_enabled": lower_enabled,
        "lower": -abs(lower),
        "annualized_lower_enabled": bool(
            values.get(
                "annualized_lower_enabled",
                values.get("annualized_backwardation_enabled", lower_enabled),
            )
        ),
        "annualized_lower": -abs(annualized_lower),
    }


def _legacy_threshold_keys(threshold_key: str) -> list[str]:
    asset_group, threshold_bucket = split_premium_threshold_key(threshold_key)
    if threshold_bucket == "DELIVERY" and asset_group in CRYPTO_PREMIUM_ASSETS:
        return [f"{asset_group}_{bucket}" for bucket in DELIVERY_SOURCE_BUCKETS]
    return []


def _select_threshold_payload(
    raw: dict[str, Any],
    threshold_key: str,
) -> dict[str, Any] | None:
    direct = raw.get(threshold_key)
    if isinstance(direct, dict):
        return direct

    for legacy_key in _legacy_threshold_keys(threshold_key):
        legacy = raw.get(legacy_key)
        if isinstance(legacy, dict):
            return legacy
    return None


def _normalize_thresholds(raw: dict[str, Any] | None) -> dict[str, dict[str, float | bool]]:
    normalized = deepcopy(DEFAULT_PREMIUM_THRESHOLDS)
    if not raw:
        return normalized

    for threshold_key, default in normalized.items():
        payload = _select_threshold_payload(raw, threshold_key)
        if not isinstance(payload, dict):
            continue
        normalized[threshold_key] = _normalize_threshold_values(payload, default)
    return normalized


def _normalize_local_thresholds(raw: dict[str, Any] | None) -> dict[str, dict[str, float | bool]]:
    normalized: dict[str, dict[str, float | bool]] = {}
    if not raw:
        return normalized

    parsed = _normalize_thresholds(raw)
    for threshold_key in DEFAULT_PREMIUM_THRESHOLDS:
        if threshold_key in parsed and _select_threshold_payload(raw, threshold_key) is not None:
            normalized[threshold_key] = parsed[threshold_key]
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
                json.dumps(
                    _serialize_thresholds(DEFAULT_PREMIUM_THRESHOLDS),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
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
        for threshold_key, values in local_thresholds.items():
            effective[threshold_key] = values

        _threshold_cache = _serialize_thresholds(effective)
        return deepcopy(_threshold_cache)


def save_premium_thresholds(thresholds: dict[str, dict[str, float | bool]]) -> Path:
    global _threshold_cache

    with _threshold_lock:
        normalized = _normalize_local_thresholds(thresholds)
        shared_thresholds = _normalize_thresholds(
            _load_threshold_payload(get_premium_thresholds_path())
        )
        local_only = {
            threshold_key: values
            for threshold_key, values in normalized.items()
            if values != shared_thresholds.get(threshold_key)
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


def get_effective_premium_threshold(
    asset_group: str,
    contract_bucket: str | None = None,
) -> dict[str, float | bool]:
    threshold_key = build_premium_threshold_key(asset_group, contract_bucket)
    thresholds = load_premium_thresholds()
    if threshold_key in thresholds:
        return thresholds[threshold_key]
    return _with_aliases(_default_threshold_values())


def get_premium_config_rows() -> list[dict[str, Any]]:
    thresholds = load_premium_thresholds()
    rows: list[dict[str, Any]] = []

    for asset_group, name in INDEX_PREMIUM_ASSETS.items():
        rows.append(
            {
                "threshold_key": asset_group,
                "asset_group": asset_group,
                "contract_bucket": "",
                "bucket_label": "指数期货",
                "name": name,
                "market": "INDEX",
                **thresholds[asset_group],
            }
        )

    for asset_group, name in CRYPTO_PREMIUM_ASSETS.items():
        for bucket in THRESHOLD_BUCKETS:
            threshold_key = build_premium_threshold_key(asset_group, bucket)
            rows.append(
                {
                    "threshold_key": threshold_key,
                    "asset_group": asset_group,
                    "contract_bucket": bucket,
                    "bucket_label": THRESHOLD_BUCKET_LABELS[bucket],
                    "name": name,
                    "market": "CRYPTO",
                    **thresholds[threshold_key],
                }
            )
    return rows
