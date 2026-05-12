from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE_PATH = PROJECT_ROOT / ".env"
SHARED_RUNTIME_CONFIG_PATH = Path(__file__).resolve().with_name("runtime_settings.json")
LOCAL_RUNTIME_CONFIG_PATH = Path(__file__).resolve().with_name("runtime_settings.local.json")

LOCAL_ONLY_FIELDS = (
    "FEISHU_WEBHOOK_URL",
    "WECOM_WEBHOOK_URL",
    "JSL_COOKIE",
    "XUEQIU_COOKIE",
    "IB_DEFAULT_PROFILE",
    "IB_REMOTE_HOST",
    "IB_REMOTE_PORT",
    "IB_REMOTE_CLIENT_ID",
    "IB_LOCAL_HOST",
    "IB_LOCAL_PORT",
    "IB_LOCAL_CLIENT_ID",
    "IB_GATEWAY_TIMEOUT_SECONDS",
)

SYNCABLE_RUNTIME_FIELDS = (
    "CRUISE_INTERVAL_MINUTES",
    "WATCH_INTERVAL_SECONDS",
    "SENTIMENT_INTERVAL_MINUTES",
    "THREAD_POOL_SIZE",
    "REQUEST_TIMEOUT",
    "RETRY_MAX_ATTEMPTS",
    "COOLDOWN_MINUTES",
    "DATA_RETENTION_DAYS",
    "ENABLE_FUTURES_MONITOR",
    "ENABLE_CONVERTIBLE_MONITOR",
    "ENABLE_SENTIMENT_MONITOR",
    "ENABLE_METALS_MONITOR",
    "ENABLE_PREMIUM_MONITOR",
    "ENABLE_FUTURES_CRUISE",
    "ENABLE_FUTURES_WATCH",
    "ENABLE_CONVERTIBLE_CRUISE",
    "ENABLE_CONVERTIBLE_WATCH",
    "ENABLE_SENTIMENT_CRUISE",
    "ENABLE_METALS_CRUISE",
    "ENABLE_METALS_WATCH",
    "ENABLE_PREMIUM_CRUISE",
    "ENABLE_PREMIUM_WATCH",
    "MORNING_START",
    "MORNING_END",
    "AFTERNOON_START",
    "AFTERNOON_END",
    "FUTURES_CRUISE_INTERVAL_MINUTES",
    "FUTURES_WATCH_INTERVAL_SECONDS",
    "FUTURES_MORNING_START",
    "FUTURES_MORNING_END",
    "FUTURES_AFTERNOON_START",
    "FUTURES_AFTERNOON_END",
    "FUTURES_NIGHT_START",
    "FUTURES_NIGHT_END",
    "CONVERTIBLE_CRUISE_INTERVAL_MINUTES",
    "CONVERTIBLE_WATCH_INTERVAL_SECONDS",
    "CONVERTIBLE_MORNING_START",
    "CONVERTIBLE_MORNING_END",
    "CONVERTIBLE_AFTERNOON_START",
    "CONVERTIBLE_AFTERNOON_END",
    "CONVERTIBLE_NIGHT_START",
    "CONVERTIBLE_NIGHT_END",
    "SENTIMENT_CRUISE_INTERVAL_MINUTES",
    "SENTIMENT_MORNING_START",
    "SENTIMENT_MORNING_END",
    "SENTIMENT_AFTERNOON_START",
    "SENTIMENT_AFTERNOON_END",
    "SENTIMENT_NIGHT_START",
    "SENTIMENT_NIGHT_END",
    "METALS_CRUISE_INTERVAL_MINUTES",
    "METALS_WATCH_INTERVAL_SECONDS",
    "METALS_MORNING_START",
    "METALS_MORNING_END",
    "METALS_AFTERNOON_START",
    "METALS_AFTERNOON_END",
    "METALS_NIGHT_START",
    "METALS_NIGHT_END",
    "PREMIUM_CRUISE_INTERVAL_MINUTES",
    "PREMIUM_WATCH_INTERVAL_SECONDS",
    "PREMIUM_MORNING_START",
    "PREMIUM_MORNING_END",
    "PREMIUM_AFTERNOON_START",
    "PREMIUM_AFTERNOON_END",
    "PREMIUM_NIGHT_START",
    "PREMIUM_NIGHT_END",
    "CB_NEGATIVE_PREMIUM_THRESHOLD",
    "ENABLE_CB_NEGATIVE_PREMIUM_THRESHOLD",
    "CB_DOUBLE_LOW_THRESHOLD",
    "ENABLE_CB_DOUBLE_LOW_THRESHOLD",
    "CB_YTM_THRESHOLD",
    "ENABLE_CB_YTM_THRESHOLD",
    "CB_SAFE_PRICE_THRESHOLD",
    "ENABLE_CB_SAFE_PRICE_THRESHOLD",
    "FUTURES_DISCOUNT_PERCENT_THRESHOLD",
    "ENABLE_FUTURES_DISCOUNT_PERCENT_THRESHOLD",
    "FUTURES_DISCOUNT_RATE_THRESHOLD",
    "ENABLE_FUTURES_DISCOUNT_RATE_THRESHOLD",
    "SENTIMENT_HOT_SCORE_THRESHOLD",
    "ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD",
    "SENTIMENT_PULSE_THRESHOLD",
    "ENABLE_SENTIMENT_PULSE_THRESHOLD",
)


class Settings(BaseSettings):
    # 兼容旧全局调度字段
    CRUISE_INTERVAL_MINUTES: int = 5
    WATCH_INTERVAL_SECONDS: int = 30
    SENTIMENT_INTERVAL_MINUTES: int = 3
    THREAD_POOL_SIZE: int = 20

    # 兼容旧全局交易时段字段
    MORNING_START: str = "09:30"
    MORNING_END: str = "11:30"
    AFTERNOON_START: str = "13:00"
    AFTERNOON_END: str = "15:00"

    # 网络
    REQUEST_TIMEOUT: int = 15
    RETRY_MAX_ATTEMPTS: int = 3

    # 冷却期
    COOLDOWN_MINUTES: int = 30
    DATA_RETENTION_DAYS: int = 14

    # 通知
    FEISHU_WEBHOOK_URL: str = ""
    WECOM_WEBHOOK_URL: str = ""

    # 外部数据鉴权
    JSL_COOKIE: str = ""
    XUEQIU_COOKIE: str = ""

    # IB Gateway / TWS
    IB_DEFAULT_PROFILE: Literal["remote", "local"] = "remote"
    IB_REMOTE_HOST: str = "100.99.204.61"
    IB_REMOTE_PORT: int = 4001
    IB_REMOTE_CLIENT_ID: int = 60101
    IB_LOCAL_HOST: str = "127.0.0.1"
    IB_LOCAL_PORT: int = 4002
    IB_LOCAL_CLIENT_ID: int = 60102
    IB_GATEWAY_TIMEOUT_SECONDS: int = 15

    # 策略开关
    ENABLE_FUTURES_MONITOR: bool = True
    ENABLE_CONVERTIBLE_MONITOR: bool = True
    ENABLE_SENTIMENT_MONITOR: bool = True
    ENABLE_METALS_MONITOR: bool = True
    ENABLE_PREMIUM_MONITOR: bool = False
    ENABLE_FUTURES_CRUISE: bool = True
    ENABLE_FUTURES_WATCH: bool = False
    ENABLE_CONVERTIBLE_CRUISE: bool = True
    ENABLE_CONVERTIBLE_WATCH: bool = False
    ENABLE_SENTIMENT_CRUISE: bool = True
    ENABLE_METALS_CRUISE: bool = True
    ENABLE_METALS_WATCH: bool = False
    ENABLE_PREMIUM_CRUISE: bool = True
    ENABLE_PREMIUM_WATCH: bool = False

    # 模块级调度: 期指
    FUTURES_CRUISE_INTERVAL_MINUTES: int = 5
    FUTURES_WATCH_INTERVAL_SECONDS: int = 30
    FUTURES_MORNING_START: str = "09:30"
    FUTURES_MORNING_END: str = "11:30"
    FUTURES_AFTERNOON_START: str = "13:00"
    FUTURES_AFTERNOON_END: str = "15:00"
    FUTURES_NIGHT_START: str = ""
    FUTURES_NIGHT_END: str = ""

    # 模块级调度: 可转债
    CONVERTIBLE_CRUISE_INTERVAL_MINUTES: int = 5
    CONVERTIBLE_WATCH_INTERVAL_SECONDS: int = 30
    CONVERTIBLE_MORNING_START: str = "09:30"
    CONVERTIBLE_MORNING_END: str = "11:30"
    CONVERTIBLE_AFTERNOON_START: str = "13:00"
    CONVERTIBLE_AFTERNOON_END: str = "15:00"
    CONVERTIBLE_NIGHT_START: str = ""
    CONVERTIBLE_NIGHT_END: str = ""

    # 模块级调度: 舆情
    SENTIMENT_CRUISE_INTERVAL_MINUTES: int = 3
    SENTIMENT_MORNING_START: str = "09:00"
    SENTIMENT_MORNING_END: str = "11:30"
    SENTIMENT_AFTERNOON_START: str = "13:00"
    SENTIMENT_AFTERNOON_END: str = "15:30"
    SENTIMENT_NIGHT_START: str = ""
    SENTIMENT_NIGHT_END: str = ""

    # 模块级调度: 金属套利
    METALS_CRUISE_INTERVAL_MINUTES: int = 15
    METALS_WATCH_INTERVAL_SECONDS: int = 60
    METALS_MORNING_START: str = "09:00"
    METALS_MORNING_END: str = "11:30"
    METALS_AFTERNOON_START: str = "13:30"
    METALS_AFTERNOON_END: str = "15:00"
    METALS_NIGHT_START: str = "21:00"
    METALS_NIGHT_END: str = "02:30"

    # 模块级调度: 期现溢价
    PREMIUM_CRUISE_INTERVAL_MINUTES: int = 5
    PREMIUM_WATCH_INTERVAL_SECONDS: int = 30
    PREMIUM_MORNING_START: str = "09:00"
    PREMIUM_MORNING_END: str = "11:30"
    PREMIUM_AFTERNOON_START: str = "13:00"
    PREMIUM_AFTERNOON_END: str = "16:00"
    PREMIUM_NIGHT_START: str = "20:00"
    PREMIUM_NIGHT_END: str = "06:00"

    # 策略阈值
    CB_NEGATIVE_PREMIUM_THRESHOLD: float = 0.0
    CB_DOUBLE_LOW_THRESHOLD: float = 130.0
    CB_YTM_THRESHOLD: float = 2.0
    CB_SAFE_PRICE_THRESHOLD: float = 130.0
    FUTURES_DISCOUNT_PERCENT_THRESHOLD: float = 1.0
    FUTURES_DISCOUNT_RATE_THRESHOLD: float = 8.0
    SENTIMENT_HOT_SCORE_THRESHOLD: int = 5_000_000
    SENTIMENT_PULSE_THRESHOLD: float = -0.8
    ENABLE_CB_NEGATIVE_PREMIUM_THRESHOLD: bool = True
    ENABLE_CB_DOUBLE_LOW_THRESHOLD: bool = True
    ENABLE_CB_YTM_THRESHOLD: bool = True
    ENABLE_CB_SAFE_PRICE_THRESHOLD: bool = True
    ENABLE_FUTURES_DISCOUNT_PERCENT_THRESHOLD: bool = True
    ENABLE_FUTURES_DISCOUNT_RATE_THRESHOLD: bool = True
    ENABLE_SENTIMENT_HOT_SCORE_THRESHOLD: bool = True
    ENABLE_SENTIMENT_PULSE_THRESHOLD: bool = True

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def reload_from_env(self) -> None:
        """重新从 `.env` 加载本机密钥，再覆盖共享运行配置。"""
        refreshed = self.__class__()
        for field_name in LOCAL_ONLY_FIELDS:
            setattr(self, field_name, getattr(refreshed, field_name))
        apply_effective_runtime_config(self)

    def apply_updates(self, updates: dict[str, Any]) -> None:
        """用新值更新当前实例，并做基础类型校验。"""
        payload = {field: getattr(self, field) for field in self.model_fields}
        payload.update(updates)
        validated = self.__class__(**payload)
        for field_name in self.model_fields:
            setattr(self, field_name, getattr(validated, field_name))


def get_shared_runtime_config_path() -> Path:
    return SHARED_RUNTIME_CONFIG_PATH


def get_local_runtime_config_path() -> Path:
    return LOCAL_RUNTIME_CONFIG_PATH


def _build_runtime_payload(source: Settings) -> dict[str, Any]:
    return {field: getattr(source, field) for field in SYNCABLE_RUNTIME_FIELDS}


def _normalize_runtime_payload(
    source: Settings, payload: dict[str, Any]
) -> dict[str, Any]:
    merged = {field: getattr(source, field) for field in source.model_fields}
    merged.update({field: value for field, value in payload.items() if field in SYNCABLE_RUNTIME_FIELDS})
    validated = source.__class__(**merged)
    return _build_runtime_payload(validated)


def _normalize_local_runtime_payload(
    source: Settings, payload: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    merged = {field: getattr(source, field) for field in source.model_fields}
    merged.update({field: value for field, value in payload.items() if field in SYNCABLE_RUNTIME_FIELDS})
    validated = source.__class__(**merged)
    return {
        field: getattr(validated, field)
        for field in SYNCABLE_RUNTIME_FIELDS
        if field in payload
    }


def load_shared_runtime_config(base: Settings, force_reload: bool = False) -> dict[str, Any]:
    path = get_shared_runtime_config_path()
    defaults = _build_runtime_payload(base)

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(defaults, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return defaults.copy()

    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw_payload = {}

    if not isinstance(raw_payload, dict):
        raw_payload = {}

    merged = defaults.copy()
    merged.update(
        {
            field: raw_payload[field]
            for field in SYNCABLE_RUNTIME_FIELDS
            if field in raw_payload
        }
    )
    normalized = _normalize_runtime_payload(base, merged)
    if force_reload or normalized != raw_payload:
        path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return normalized.copy()


def load_local_runtime_config(base: Settings, force_reload: bool = False) -> dict[str, Any]:
    path = get_local_runtime_config_path()
    if not path.exists():
        return {}

    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw_payload = {}

    if not isinstance(raw_payload, dict):
        raw_payload = {}

    normalized = _normalize_local_runtime_payload(base, raw_payload)
    if force_reload or normalized != raw_payload:
        path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return normalized.copy()


def load_effective_runtime_config(base: Settings, force_reload: bool = False) -> dict[str, Any]:
    shared = load_shared_runtime_config(base, force_reload=force_reload)
    local = load_local_runtime_config(base, force_reload=force_reload)
    if not local:
        return shared

    merged = shared.copy()
    merged.update(
        {
            field: local[field]
            for field in SYNCABLE_RUNTIME_FIELDS
            if field in local
        }
    )
    return _normalize_runtime_payload(base, merged)


def save_shared_runtime_config(
    base: Settings,
    updates: dict[str, Any] | None = None,
    path: Path | None = None,
) -> Path:
    config_path = path or get_shared_runtime_config_path()
    current = load_shared_runtime_config(base)
    if updates:
        current.update(
            {
                field: value
                for field, value in updates.items()
                if field in SYNCABLE_RUNTIME_FIELDS
            }
        )
    normalized = _normalize_runtime_payload(base, current)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return config_path


def save_local_runtime_config(
    base: Settings,
    updates: dict[str, Any] | None = None,
    path: Path | None = None,
) -> Path:
    config_path = path or get_local_runtime_config_path()
    current = load_local_runtime_config(base)
    if updates:
        current.update(
            {
                field: value
                for field, value in updates.items()
                if field in SYNCABLE_RUNTIME_FIELDS
            }
        )
    normalized = _normalize_local_runtime_payload(base, current)
    shared = load_shared_runtime_config(base)
    normalized = {
        field: value
        for field, value in normalized.items()
        if shared.get(field) != value
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return config_path


def apply_effective_runtime_config(target: Settings) -> None:
    effective = load_effective_runtime_config(target)
    for field_name, value in effective.items():
        setattr(target, field_name, value)


settings = Settings()
apply_effective_runtime_config(settings)
