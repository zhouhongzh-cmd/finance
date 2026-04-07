from __future__ import annotations

from typing import List

from models.market_data import PremiumArbitrageData
from models.signals import Signal
from strategies.base import BaseStrategy
from utils.premium_config import get_effective_premium_threshold


class PremiumArbitrageStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "Premium_Arbitrage"

    def evaluate(self, data: List[PremiumArbitrageData]) -> List[Signal]:
        signals: List[Signal] = []

        for item in data:
            threshold = get_effective_premium_threshold(item.asset_group)
            upper = float(threshold["upper"])
            lower = float(threshold["lower"])
            upper_enabled = bool(threshold.get("upper_enabled", True))
            lower_enabled = bool(threshold.get("lower_enabled", True))

            triggered = (upper_enabled and item.premium_rate >= upper) or (
                lower_enabled and item.premium_rate <= lower
            )
            if not triggered:
                continue

            active_bounds = []
            if upper_enabled:
                active_bounds.append(abs(upper))
            if lower_enabled:
                active_bounds.append(abs(lower))
            severity_base = max(active_bounds) if active_bounds else 0.0
            level = (
                "CRITICAL"
                if severity_base > 0 and abs(item.premium_rate) >= severity_base * 1.5
                else "WARNING"
            )
            direction = "升水" if item.premium_rate >= 0 else "贴水"
            asset_label = (
                "BTC 期现" if item.asset_group == "BTC" else f"A50 {item.future_name or item.future_symbol}"
            )
            message = (
                f"期现溢价阈值触发\n"
                f"资产组：{item.asset_group}\n"
                f"现货：{item.spot_name} ({item.spot_symbol}) {item.spot_price:,.2f}\n"
                f"期货：{item.future_name} ({item.future_symbol}) {item.future_price:,.2f}\n"
                f"方向：{direction}\n"
                f"溢价值：{item.premium:+,.2f}\n"
                f"溢价率：{item.premium_rate:+.2f}%\n"
                f"阈值区间：[{lower:.2f}%, {upper:.2f}%]\n"
                f"下阈值：{'启用' if lower_enabled else '关闭'} / 上阈值：{'启用' if upper_enabled else '关闭'}"
            )
            signals.append(
                Signal(
                    asset=asset_label,
                    strategy_name=self.name,
                    level=level,
                    message=message,
                    timestamp=item.timestamp,
                )
            )

        return signals
