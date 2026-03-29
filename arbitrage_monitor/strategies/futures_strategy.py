from typing import List
from models.signals import Signal
from models.market_data import FuturesData
from strategies.base import BaseStrategy
from config.settings import settings
from utils.logger import logger


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
        annualized_threshold = settings.FUTURES_DISCOUNT_RATE_THRESHOLD
        percent_threshold = settings.FUTURES_DISCOUNT_PERCENT_THRESHOLD
        percent_enabled = settings.ENABLE_FUTURES_DISCOUNT_PERCENT_THRESHOLD
        annualized_enabled = settings.ENABLE_FUTURES_DISCOUNT_RATE_THRESHOLD

        for item in data:
            # 使用合约自身的真实剩余交割天数年化，max(1) 防止除以零（交割当天）
            annualized_discount = item.discount_rate * (365 / max(item.days_to_maturity, 1))

            logger.debug(
                "evaluating_futures",
                symbol=item.symbol,
                discount=item.discount_rate,
                annualized=annualized_discount,
            )

            percent_triggered = percent_enabled and item.discount_rate >= percent_threshold
            annualized_triggered = annualized_enabled and annualized_discount >= annualized_threshold
            if percent_triggered or annualized_triggered:
                percent_ratio = (
                    item.discount_rate / percent_threshold
                    if percent_triggered and percent_threshold > 0
                    else 0.0
                )
                annualized_ratio = (
                    annualized_discount / annualized_threshold
                    if annualized_triggered and annualized_threshold > 0
                    else 0.0
                )
                severity_ratio = max(percent_ratio, annualized_ratio)
                trigger_labels = []
                if percent_triggered:
                    trigger_labels.append("贴水率")
                if annualized_triggered:
                    trigger_labels.append("年化贴水率")
                if percent_enabled:
                    percent_line = f"贴水率阈值：{percent_threshold:.2f}%"
                else:
                    percent_line = "贴水率阈值：未启用"
                if annualized_enabled:
                    annualized_line = f"年化贴水率阈值：{annualized_threshold:.2f}%"
                else:
                    annualized_line = "年化贴水率阈值：未启用"
                msg = (
                    f"🎯 **期指深度贴水套利机会**\n"
                    f"标的：{item.symbol}\n"
                    f"期指价格：{item.price:.2f}\n"
                    f"现货价格：{item.spot_price:.2f}\n"
                    f"当前绝对贴水率：{item.discount_rate:.2f}%\n"
                    f"🔥 **估算年化贴水率：{annualized_discount:.2f}%**\n"
                    f"触发条件：{' / '.join(trigger_labels)}\n"
                    f"{percent_line}\n"
                    f"{annualized_line}"
                )
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
