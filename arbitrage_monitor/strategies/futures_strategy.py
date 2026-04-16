from typing import List
from models.signals import Signal
from models.market_data import FuturesData
from strategies.base import BaseStrategy
from utils.logger import logger
from utils.futures_config import get_effective_futures_threshold


class FuturesDiscountStrategy(BaseStrategy):
    """
    期指吃贴水策略
    原理：当股指期货(如IC/IM)相对现货指数产生较深贴水时，做多期指做空现货(或平替)，
    持有到期交割赚取贴水回归的无风险收益。
    """

    @property
    def name(self) -> str:
        return "Futures_Discount_Arbitrage"

    def evaluate(self, data: List[FuturesData]) -> List[Signal]:
        signals = []

        for item in data:
            threshold = get_effective_futures_threshold(item.product_code or item.symbol)
            upper_enabled = bool(threshold["upper_enabled"])
            upper_threshold = float(threshold["upper"])
            annualized_upper_enabled = bool(threshold.get("annualized_upper_enabled", upper_enabled))
            annualized_upper_threshold = float(threshold["annualized_upper"])
            lower_enabled = bool(threshold["lower_enabled"])
            lower_threshold = float(threshold["lower"])
            annualized_lower_enabled = bool(threshold.get("annualized_lower_enabled", lower_enabled))
            annualized_lower_threshold = float(threshold["annualized_lower"])
            normalized_rate = -item.discount_rate
            annualized_normalized = normalized_rate * (365 / max(item.days_to_maturity, 1))

            logger.debug(
                "evaluating_futures",
                symbol=item.symbol,
                discount=item.discount_rate,
                normalized_rate=normalized_rate,
                annualized=annualized_normalized,
            )

            direction = ""
            severity_ratio = 0.0
            msg = ""
            if (
                upper_enabled
                and normalized_rate >= upper_threshold
                and (
                    not annualized_upper_enabled
                    or annualized_normalized >= annualized_upper_threshold
                )
            ):
                direction = "升水"
                percent_ratio = (
                    normalized_rate / upper_threshold
                    if upper_threshold > 0
                    else 0.0
                )
                annualized_ratio = (
                    annualized_normalized / annualized_upper_threshold
                    if annualized_upper_enabled and annualized_upper_threshold > 0
                    else 0.0
                )
                severity_ratio = max(percent_ratio, annualized_ratio)
                msg = (
                    f"期指双阈值触发\n"
                    f"标的：{item.symbol}\n"
                    f"方向：{direction}\n"
                    f"期指价格：{item.price:.2f}\n"
                    f"现货价格：{item.spot_price:.2f}\n"
                    f"当前升水率：{normalized_rate:.2f}%\n"
                    f"年化升水率：{annualized_normalized:.2f}%\n"
                    f"触发条件：普通升水阈值与年化升水阈值已同时满足\n"
                    f"普通升水阈值：{upper_threshold:.2f}%\n"
                    f"年化升水阈值：{annualized_upper_threshold:.2f}%"
                )
            elif (
                lower_enabled
                and normalized_rate <= lower_threshold
                and (
                    not annualized_lower_enabled
                    or annualized_normalized <= annualized_lower_threshold
                )
            ):
                direction = "贴水"
                percent_ratio = (
                    abs(normalized_rate) / abs(lower_threshold)
                    if lower_threshold != 0
                    else 0.0
                )
                annualized_ratio = (
                    abs(annualized_normalized) / abs(annualized_lower_threshold)
                    if annualized_lower_enabled and annualized_lower_threshold != 0
                    else 0.0
                )
                severity_ratio = max(percent_ratio, annualized_ratio)
                msg = (
                    f"期指双阈值触发\n"
                    f"标的：{item.symbol}\n"
                    f"方向：{direction}\n"
                    f"期指价格：{item.price:.2f}\n"
                    f"现货价格：{item.spot_price:.2f}\n"
                    f"当前贴水率：{abs(normalized_rate):.2f}%\n"
                    f"年化贴水率：{abs(annualized_normalized):.2f}%\n"
                    f"触发条件：普通贴水阈值与年化贴水阈值已同时满足\n"
                    f"普通贴水阈值：{abs(lower_threshold):.2f}%\n"
                    f"年化贴水阈值：{abs(annualized_lower_threshold):.2f}%"
                )

            if not msg:
                continue

            if item.margin_ratio > 0:
                msg += (
                    f"\n保证金比例：{item.margin_ratio:.2f}%"
                    f"\n单手名义本金：{item.notional_per_lot:,.0f}"
                    f"\n单手保证金占用：{item.margin_required_per_lot:,.0f}"
                )

            signal = Signal(
                asset=item.symbol,
                strategy_name=self.name,
                level="WARNING" if severity_ratio < 1.5 else "CRITICAL",
                message=msg,
            )
            signals.append(signal)

        return signals
