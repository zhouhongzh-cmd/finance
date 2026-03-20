from __future__ import annotations

from typing import List

from models.market_data import MetalArbitrageData
from models.signals import Signal
from strategies.base import BaseStrategy
from utils.metals_config import get_effective_metal_threshold


class MetalsArbitrageStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "Metals_Arbitrage"

    def evaluate(self, data: List[MetalArbitrageData]) -> List[Signal]:
        signals: List[Signal] = []

        for item in data:
            threshold = get_effective_metal_threshold(item.metal_symbol)
            upper = float(threshold["upper"])
            lower = float(threshold["lower"])
            spread_pct = item.spread_pct

            triggered = spread_pct >= upper or spread_pct <= lower
            if not triggered:
                continue

            severity_base = max(abs(upper), abs(lower))
            level = (
                "CRITICAL"
                if severity_base > 0 and abs(spread_pct) >= (severity_base * 1.5)
                else "WARNING"
            )
            direction = "国内溢价" if spread_pct >= 0 else "国内折价"
            message = (
                f"金属套利阈值触发\n"
                f"标的：{item.metal_name} vs {item.benchmark_display_name}\n"
                f"方向：{direction}\n"
                f"国内价格：{item.dom_price:.2f} {item.domestic_unit}\n"
                f"外盘美元价：{item.for_price_usd:.4f}\n"
                f"外盘人民币价：{item.for_price_cny:.2f} {item.domestic_unit}\n"
                f"价差：{item.spread:.2f}\n"
                f"价差百分比：{item.spread_pct:.2f}%\n"
                f"隐含汇率：{item.implied_rate:.4f}\n"
                f"阈值区间：[{lower:.2f}%, {upper:.2f}%]"
            )
            signals.append(
                Signal(
                    asset=f"{item.metal_name} vs {item.benchmark_display_name}",
                    strategy_name=self.name,
                    level=level,
                    message=message,
                    timestamp=item.timestamp,
                )
            )

        return signals
