from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from config.metals import METALS_CONFIG, get_default_metals_thresholds


_threshold_lock = threading.Lock()
_threshold_cache: dict[str, dict[str, float]] | None = None


def get_metals_thresholds_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "metals_thresholds.json"


def get_legacy_metals_thresholds_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "metals_thresholds.json"


def _load_threshold_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _diff_thresholds(
    current: dict[str, dict[str, float]],
    legacy: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol, legacy_values in legacy.items():
        current_values = current.get(symbol)
        if current_values is None:
            continue
        if (
            float(current_values["upper"]) == float(legacy_values["upper"])
            and float(current_values["lower"]) == float(legacy_values["lower"])
        ):
            continue
        rows.append(
            {
                "symbol": symbol,
                "name": METALS_CONFIG[symbol]["name"],
                "current_upper": float(current_values["upper"]),
                "current_lower": float(current_values["lower"]),
                "legacy_upper": float(legacy_values["upper"]),
                "legacy_lower": float(legacy_values["lower"]),
            }
        )
    return rows


def _normalize_thresholds(raw: dict[str, Any] | None) -> dict[str, dict[str, float]]:
    defaults = get_default_metals_thresholds()
    normalized = deepcopy(defaults)

    if not raw:
        return normalized

    for symbol, values in raw.items():
        if symbol not in normalized or not isinstance(values, dict):
            continue
        upper = values.get("upper", normalized[symbol]["upper"])
        lower = values.get("lower", normalized[symbol]["lower"])
        normalized[symbol] = {"upper": float(upper), "lower": float(lower)}

    return normalized


def load_metals_thresholds(force_reload: bool = False) -> dict[str, dict[str, float]]:
    global _threshold_cache

    with _threshold_lock:
        if _threshold_cache is not None and not force_reload:
            return deepcopy(_threshold_cache)

        path = get_metals_thresholds_path()

        if not path.exists():
            defaults = _normalize_thresholds(None)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(defaults, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            _threshold_cache = defaults
            return deepcopy(_threshold_cache)

        payload = _load_threshold_payload(path)
        normalized = _normalize_thresholds(payload)

        _threshold_cache = normalized
        if payload != _threshold_cache:
            path.write_text(
                json.dumps(_threshold_cache, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return deepcopy(_threshold_cache)


def save_metals_thresholds(thresholds: dict[str, dict[str, float]]) -> Path:
    global _threshold_cache

    with _threshold_lock:
        normalized = _normalize_thresholds(thresholds)
        path = get_metals_thresholds_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _threshold_cache = normalized
        return path


def get_legacy_metals_thresholds_preview() -> dict[str, Any] | None:
    legacy_path = get_legacy_metals_thresholds_path()
    if not legacy_path.exists():
        return None

    legacy_payload = _load_threshold_payload(legacy_path)
    legacy_thresholds = _normalize_thresholds(legacy_payload)
    current_thresholds = load_metals_thresholds(force_reload=True)
    differences = _diff_thresholds(current_thresholds, legacy_thresholds)
    if not differences:
        return None

    return {
        "legacy_path": legacy_path,
        "current_path": get_metals_thresholds_path(),
        "differences": differences,
        "legacy_thresholds": legacy_thresholds,
    }


def migrate_legacy_metals_thresholds(delete_legacy: bool = True) -> dict[str, Any]:
    preview = get_legacy_metals_thresholds_preview()
    if preview is None:
        return {
            "migrated": False,
            "path": get_metals_thresholds_path(),
            "removed_legacy": False,
            "count": 0,
        }

    path = save_metals_thresholds(preview["legacy_thresholds"])
    removed_legacy = False
    legacy_path = Path(preview["legacy_path"])
    if delete_legacy and legacy_path.exists():
        legacy_path.unlink()
        removed_legacy = True

    return {
        "migrated": True,
        "path": path,
        "removed_legacy": removed_legacy,
        "count": len(preview["differences"]),
    }


def reset_metals_thresholds() -> Path:
    return save_metals_thresholds(get_default_metals_thresholds())


def get_effective_metal_threshold(symbol: str) -> dict[str, float]:
    thresholds = load_metals_thresholds()
    if symbol in thresholds:
        return thresholds[symbol]
    return {"upper": 2.0, "lower": -2.0}


def get_metals_config_rows() -> list[dict[str, Any]]:
    thresholds = load_metals_thresholds()
    rows: list[dict[str, Any]] = []
    for symbol, config in METALS_CONFIG.items():
        current = thresholds.get(symbol, config["alert_threshold"])
        rows.append(
            {
                "symbol": symbol,
                "name": config["name"],
                "category": config["category"],
                "upper": float(current["upper"]),
                "lower": float(current["lower"]),
            }
        )
    return rows
