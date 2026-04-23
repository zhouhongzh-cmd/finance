from __future__ import annotations

from typing import List

from models.market_data import MetalArbitrageData
from models.signals import Signal
from strategies.base import BaseStrategy
from config.metals_thresholds import get_effective_metal_threshold


class MetalsArbitrageStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "Metals_Arbitrage"

    def evaluate(self, data: List[MetalArbitrageData]) -> List[Signal]:
        signals: List[Signal] = []

        for item in data:
            threshold = get_effective_metal_threshold(item.metal_symbol)
            upper_threshold = float(threshold["upper"])
            lower_threshold = float(threshold["lower"])
            upper_enabled = bool(threshold.get("upper_enabled", True))
            lower_enabled = bool(threshold.get("lower_enabled", True))
            spread_pct = item.spread_pct

            direction = ""
            severity_base = 0.0
            if upper_enabled and spread_pct >= upper_threshold:
                direction = "升水"
                severity_base = upper_threshold
            elif lower_enabled and spread_pct <= lower_threshold:
                direction = "贴水"
                severity_base = abs(lower_threshold)
            if not direction:
                continue

            level = (
                "CRITICAL"
                if severity_base > 0 and abs(spread_pct) >= (severity_base * 1.5)
                else "WARNING"
            )
            message = (
                f"金属套利阈值触发\n"
                f"标的：{item.metal_name} vs {item.benchmark_display_name}\n"
                f"方向：{direction}\n"
                f"国内价格：{item.dom_price:.2f} {item.domestic_unit}\n"
                f"外盘美元价：{item.for_price_usd:.4f}\n"
                f"外盘人民币价：{item.for_price_cny:.2f} {item.domestic_unit}\n"
                f"价差：{item.spread:.2f}\n"
                f"价差百分比：{abs(item.spread_pct):.2f}%\n"
                f"隐含汇率：{item.implied_rate:.4f}\n"
                f"升水阈值：{'启用' if upper_enabled else '关闭'} / {upper_threshold:.2f}%\n"
                f"贴水阈值：{'启用' if lower_enabled else '关闭'} / {abs(lower_threshold):.2f}%"
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
