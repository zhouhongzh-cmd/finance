from __future__ import annotations

from typing import List

from models.market_data import PremiumArbitrageData
from models.signals import Signal
from strategies.base import BaseStrategy
from config.premium_thresholds import CONTRACT_BUCKET_LABELS, get_effective_premium_threshold


class PremiumArbitrageStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "Premium_Arbitrage"

    def evaluate(self, data: List[PremiumArbitrageData]) -> List[Signal]:
        signals: List[Signal] = []

        for item in data:
            threshold = get_effective_premium_threshold(item.asset_group, item.contract_bucket)
            upper_enabled = bool(threshold.get("upper_enabled", True))
            upper_threshold = float(threshold["upper"])
            annualized_upper_enabled = bool(threshold.get("annualized_upper_enabled", True))
            annualized_upper_threshold = float(threshold["annualized_upper"])
            lower_enabled = bool(threshold.get("lower_enabled", True))
            lower_threshold = float(threshold["lower"])
            annualized_lower_enabled = bool(threshold.get("annualized_lower_enabled", True))
            annualized_lower_threshold = float(threshold["annualized_lower"])

            annualized_premium_rate = None
            is_annualized_supported = item.contract_bucket != "PERP" and item.days_to_maturity is not None
            if is_annualized_supported:
                annualized_premium_rate = item.premium_rate * (
                    365 / max(int(item.days_to_maturity), 1)
                )
            annualized_display_value = annualized_premium_rate if annualized_premium_rate is not None else None

            direction = None
            ordinary_triggered = False
            annualized_triggered = False
            annualized_required = False
            severity_ratio = 0.0

            if upper_enabled and item.premium_rate >= upper_threshold:
                direction = "升水"
                ordinary_triggered = True
                annualized_required = annualized_upper_enabled and annualized_premium_rate is not None
                annualized_triggered = (
                    not annualized_required
                    or annualized_premium_rate >= annualized_upper_threshold
                )
                ordinary_ratio = (
                    item.premium_rate / upper_threshold if upper_threshold > 0 else 0.0
                )
                annualized_ratio = (
                    annualized_premium_rate / annualized_upper_threshold
                    if annualized_required and annualized_upper_threshold > 0
                    else ordinary_ratio
                )
                severity_ratio = max(ordinary_ratio, annualized_ratio)
            elif lower_enabled and item.premium_rate <= lower_threshold:
                direction = "贴水"
                ordinary_triggered = True
                annualized_required = annualized_lower_enabled and annualized_premium_rate is not None
                annualized_triggered = (
                    not annualized_required
                    or annualized_premium_rate <= annualized_lower_threshold
                )
                ordinary_ratio = (
                    abs(item.premium_rate) / abs(lower_threshold)
                    if lower_threshold != 0
                    else 0.0
                )
                annualized_ratio = (
                    abs(annualized_premium_rate) / abs(annualized_lower_threshold)
                    if annualized_required and annualized_lower_threshold != 0
                    else ordinary_ratio
                )
                severity_ratio = max(ordinary_ratio, annualized_ratio)

            if not ordinary_triggered or not annualized_triggered or direction is None:
                continue

            level = "CRITICAL" if severity_ratio >= 1.5 else "WARNING"
            bucket_label = CONTRACT_BUCKET_LABELS.get(item.contract_bucket, item.contract_bucket or "多合约")
            asset_label = (
                f"{item.asset_group} {bucket_label} {item.future_symbol}".strip()
                if item.asset_group != "A50"
                else f"A50 {item.future_name or item.future_symbol}"
            )
            annualized_display = (
                f"{annualized_display_value:.2f}%"
                if annualized_display_value is not None
                else "N/A（永续或未提供交割日）"
            )
            if direction == "升水":
                ordinary_line = f"普通升水阈值：{'启用' if upper_enabled else '关闭'} / {upper_threshold:.2f}%"
                annualized_line = (
                    f"年化升水阈值：{'启用' if annualized_upper_enabled else '关闭'} / {annualized_upper_threshold:.2f}%"
                )
            else:
                ordinary_line = (
                    f"普通贴水阈值：{'启用' if lower_enabled else '关闭'} / {abs(lower_threshold):.2f}%"
                )
                annualized_line = (
                    f"年化贴水阈值：{'启用' if annualized_lower_enabled else '关闭'} / {abs(annualized_lower_threshold):.2f}%"
                )

            annualized_note = (
                "年化阈值：已参与判定"
                if annualized_required
                else "年化阈值：未参与判定"
            )
            message = (
                f"期现溢价阈值触发\n"
                f"资产组：{item.asset_group}\n"
                f"合约桶：{bucket_label}\n"
                f"现货：{item.spot_name} ({item.spot_symbol}) {item.spot_price:,.2f}\n"
                f"期货：{item.future_name} ({item.future_symbol}) {item.future_price:,.2f}\n"
                f"方向：{direction}\n"
                f"溢价值：{item.premium:+,.2f}\n"
                f"溢价率：{item.premium_rate:.2f}%\n"
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
