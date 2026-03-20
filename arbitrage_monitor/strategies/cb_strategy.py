from typing import List
from models.signals import Signal
from models.market_data import CBData
from strategies.base import BaseStrategy
from config.settings import settings

class ConvertibleStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "Convertible_Arbitrage"

    def evaluate(self, data: List[CBData]) -> List[Signal]:
        signals = []
        for item in data:
            # 策略 1: 负溢价套利
            # 如果转股溢价率低于配置项且价格处于安全区
            if item.premium_rate < settings.CB_NEGATIVE_PREMIUM_THRESHOLD and item.price < settings.CB_SAFE_PRICE_THRESHOLD:
                level = "CRITICAL" if item.premium_rate < -2.0 else "WARNING"
                signals.append(Signal(
                    asset=item.symbol,
                    strategy_name=self.name,
                    level=level,
                    message=f"可转债出现负溢价！当前溢价率: {item.premium_rate}%, 现价: {item.price}。存在套利空间。",
                    timestamp=item.timestamp
                ))
                continue
            
            # 策略 2: 双低策略 (双低值低于配置阈值 且 到期收益率高于指定值)
            if item.double_low < settings.CB_DOUBLE_LOW_THRESHOLD and item.ytm > settings.CB_YTM_THRESHOLD:
                signals.append(Signal(
                    asset=item.symbol,
                    strategy_name=self.name,
                    level="INFO",
                    message=f"可转债触发双低防守轮动！双低: {item.double_low}, 现价: {item.price}, 税前YTM: {item.ytm}%。",
                    timestamp=item.timestamp
                ))
        return signals
