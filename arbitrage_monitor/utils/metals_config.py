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
            path.parent.mkdir(parents=True, exist_ok=True)
            defaults = _normalize_thresholds(None)
            path.write_text(
                json.dumps(defaults, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            _threshold_cache = defaults
            return deepcopy(_threshold_cache)

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = None

        _threshold_cache = _normalize_thresholds(payload)
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
