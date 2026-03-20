from pydantic_settings import BaseSettings, SettingsConfigDict

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
    DATA_RETENTION_DAYS: int = 30

    # 通知
    FEISHU_WEBHOOK_URL: str = ""
    WECOM_WEBHOOK_URL: str = ""

    # 外部数据鉴权
    JSL_COOKIE: str = ""
    XUEQIU_COOKIE: str = ""

    # 策略开关
    ENABLE_FUTURES_MONITOR: bool = True
    ENABLE_CONVERTIBLE_MONITOR: bool = True
    ENABLE_SENTIMENT_MONITOR: bool = True
    ENABLE_METALS_MONITOR: bool = True

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

    # 策略阈值
    CB_NEGATIVE_PREMIUM_THRESHOLD: float = 0.0
    CB_DOUBLE_LOW_THRESHOLD: float = 130.0
    CB_YTM_THRESHOLD: float = 2.0
    CB_SAFE_PRICE_THRESHOLD: float = 130.0
    FUTURES_DISCOUNT_RATE_THRESHOLD: float = 8.0
    SENTIMENT_HOT_SCORE_THRESHOLD: int = 5_000_000
    SENTIMENT_PULSE_THRESHOLD: float = -0.8

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def reload_from_env(self) -> None:
        """重新从 .env 加载配置并覆盖当前实例。"""
        refreshed = self.__class__()
        for field_name in self.model_fields:
            setattr(self, field_name, getattr(refreshed, field_name))

    def apply_updates(self, updates: dict) -> None:
        """用新值更新当前实例，并做基础类型校验。"""
        payload = {field: getattr(self, field) for field in self.model_fields}
        payload.update(updates)
        validated = self.__class__(**payload)
        for field_name in self.model_fields:
            setattr(self, field_name, getattr(validated, field_name))

settings = Settings()
