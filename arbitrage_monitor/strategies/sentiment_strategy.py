from typing import List
from models.signals import Signal
from strategies.base import BaseStrategy
from models.market_data import SentimentData
from config.settings import settings

class SentimentStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "Sentiment_Heat_and_Risk"

    def evaluate(self, data: List[SentimentData]) -> List[Signal]:
        signals = []
        hot_score_threshold = settings.SENTIMENT_HOT_SCORE_THRESHOLD
        pulse_threshold = settings.SENTIMENT_PULSE_THRESHOLD
        for item in data:
            # 逻辑 1: 雪球热度异常飙升
            if item.hot_score > hot_score_threshold:
                signals.append(Signal(
                    asset=f"{item.name}({item.symbol})",
                    strategy_name=self.name,
                    level="WARNING",
                    message=f"舆情热度异常飙升！当前热度值: {item.hot_score}，排行: {item.rank}",
                    timestamp=item.timestamp
                ))
                
            # 逻辑 2: 负面舆情聚集 (排雷)
            if item.sentiment_pulse < pulse_threshold:
                signals.append(Signal(
                    asset=f"{item.name}({item.symbol})",
                    strategy_name=self.name,
                    level="CRITICAL",
                    message=f"检测到极端负面情绪聚集 (排雷预警)！情绪脉冲值: {item.sentiment_pulse}",
                    timestamp=item.timestamp
                ))
                
        return signals
