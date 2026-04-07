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
            contango_enabled = bool(threshold.get("contango_enabled", True))
            contango_threshold = float(threshold["contango_threshold"])
            annualized_contango_enabled = bool(threshold.get("annualized_contango_enabled", True))
            annualized_contango_threshold = float(threshold["annualized_contango_threshold"])
            backwardation_enabled = bool(threshold.get("backwardation_enabled", True))
            backwardation_threshold = float(threshold["backwardation_threshold"])
            annualized_backwardation_enabled = bool(
                threshold.get("annualized_backwardation_enabled", True)
            )
            annualized_backwardation_threshold = float(
                threshold["annualized_backwardation_threshold"]
            )

            annualized_premium_rate = None
            if item.days_to_maturity is not None:
                annualized_premium_rate = item.premium_rate * (
                    365 / max(int(item.days_to_maturity), 1)
                )

            direction = None
            ordinary_triggered = False
            annualized_triggered = False
            annualized_required = False
            severity_ratio = 0.0

            if contango_enabled and item.premium_rate >= contango_threshold:
                direction = "升水"
                ordinary_triggered = True
                annualized_required = annualized_contango_enabled and annualized_premium_rate is not None
                annualized_triggered = (
                    not annualized_required
                    or annualized_premium_rate >= annualized_contango_threshold
                )
                ordinary_ratio = (
                    item.premium_rate / contango_threshold if contango_threshold > 0 else 0.0
                )
                annualized_ratio = (
                    annualized_premium_rate / annualized_contango_threshold
                    if annualized_required and annualized_contango_threshold > 0
                    else ordinary_ratio
                )
                severity_ratio = max(ordinary_ratio, annualized_ratio)
            elif backwardation_enabled and item.premium_rate <= backwardation_threshold:
                direction = "贴水"
                ordinary_triggered = True
                annualized_required = (
                    annualized_backwardation_enabled and annualized_premium_rate is not None
                )
                annualized_triggered = (
                    not annualized_required
                    or annualized_premium_rate <= annualized_backwardation_threshold
                )
                ordinary_ratio = (
                    abs(item.premium_rate) / abs(backwardation_threshold)
                    if backwardation_threshold != 0
                    else 0.0
                )
                annualized_ratio = (
                    abs(annualized_premium_rate) / abs(annualized_backwardation_threshold)
                    if annualized_required and annualized_backwardation_threshold != 0
                    else ordinary_ratio
                )
                severity_ratio = max(ordinary_ratio, annualized_ratio)

            if not ordinary_triggered or not annualized_triggered or direction is None:
                continue

            level = "CRITICAL" if severity_ratio >= 1.5 else "WARNING"
            asset_label = (
                "BTC 期现" if item.asset_group == "BTC" else f"A50 {item.future_name or item.future_symbol}"
            )
            annualized_display = (
                f"{annualized_premium_rate:+.2f}%"
                if annualized_premium_rate is not None
                else "N/A（未提供交割日）"
            )
            if direction == "升水":
                ordinary_line = f"普通升水阈值：{'启用' if contango_enabled else '关闭'} / {contango_threshold:.2f}%"
                annualized_line = (
                    f"年化升水阈值：{'启用' if annualized_contango_enabled else '关闭'} / {annualized_contango_threshold:.2f}%"
                )
            else:
                ordinary_line = (
                    f"普通贴水阈值：{'启用' if backwardation_enabled else '关闭'} / {backwardation_threshold:.2f}%"
                )
                annualized_line = (
                    f"年化贴水阈值：{'启用' if annualized_backwardation_enabled else '关闭'} / {annualized_backwardation_threshold:.2f}%"
                )

            annualized_note = (
                "年化阈值：已参与判定"
                if annualized_required
                else "年化阈值：未参与判定"
            )
            message = (
                f"期现溢价阈值触发\n"
                f"资产组：{item.asset_group}\n"
                f"现货：{item.spot_name} ({item.spot_symbol}) {item.spot_price:,.2f}\n"
                f"期货：{item.future_name} ({item.future_symbol}) {item.future_price:,.2f}\n"
                f"方向：{direction}\n"
                f"溢价值：{item.premium:+,.2f}\n"
                f"溢价率：{item.premium_rate:+.2f}%\n"
                f"剩余天数：{item.days_to_maturity if item.days_to_maturity is not None else 'N/A'}\n"
                f"年化溢价率：{annualized_display}\n"
                f"{ordinary_line}\n"
                f"{annualized_line}\n"
                f"{annualized_note}"
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
