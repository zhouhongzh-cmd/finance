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
        threshold = settings.FUTURES_DISCOUNT_RATE_THRESHOLD

        for item in data:
            # 使用合约自身的真实剩余交割天数年化，max(1) 防止除以零（交割当天）
            annualized_discount = item.discount_rate * (365 / max(item.days_to_maturity, 1))

            logger.debug(
                "evaluating_futures",
                symbol=item.symbol,
                discount=item.discount_rate,
                annualized=annualized_discount,
            )

            if annualized_discount > threshold:
                msg = (
                    f"🎯 **期指深度贴水套利机会**\n"
                    f"标的：{item.symbol}\n"
                    f"期指价格：{item.price:.2f}\n"
                    f"现货价格：{item.spot_price:.2f}\n"
                    f"当前绝对贴水率：{item.discount_rate:.2f}%\n"
                    f"🔥 **估算年化贴水率：{annualized_discount:.2f}%** (阈值：{threshold}%)"
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
                    level="WARNING"
                    if annualized_discount < (threshold * 1.5)
                    else "CRITICAL",
                    message=msg,
                )
                signals.append(signal)

        return signals
