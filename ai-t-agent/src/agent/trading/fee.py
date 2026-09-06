"""
A股费用计算器

费用模型：
- 印花税：卖出金额 0.05%（仅卖出）
- 过户费：成交金额 0.001%（双边）
- 佣金：双边万2.5，单笔最低5元

精度：全链路 Decimal，保留2位小数。
验收：2元股价100股往返费用 ≈ 10.10元。
"""

from decimal import Decimal, ROUND_HALF_UP

from agent.common.models import FeeDetail
from agent.config.schema import FeeConfig


class FeeCalculator:
    """A股费用计算器"""

    def __init__(self, config: FeeConfig):
        self._stamp_tax_rate = config.stamp_tax_rate
        self._transfer_fee_rate = config.transfer_fee_rate
        self._commission_rate = config.commission_rate
        self._min_commission = config.min_commission

    def buy_fee(self, amount: Decimal) -> FeeDetail:
        """
        计算买入费用。

        Args:
            amount: 买入金额 (price * shares)

        Returns:
            FeeDetail（stamp_tax=0）
        """
        commission = self._calc_commission(amount)
        transfer_fee = self._round(amount * self._transfer_fee_rate)
        return FeeDetail(
            commission=commission,
            stamp_tax=Decimal("0"),
            transfer_fee=transfer_fee,
        )

    def sell_fee(self, amount: Decimal) -> FeeDetail:
        """
        计算卖出费用。

        Args:
            amount: 卖出金额 (price * shares)

        Returns:
            FeeDetail（含印花税）
        """
        commission = self._calc_commission(amount)
        transfer_fee = self._round(amount * self._transfer_fee_rate)
        stamp_tax = self._round(amount * self._stamp_tax_rate)
        return FeeDetail(
            commission=commission,
            stamp_tax=stamp_tax,
            transfer_fee=transfer_fee,
        )

    def round_trip_fee_est(self, price: Decimal, shares: int = 100) -> Decimal:
        """
        往返费用估算（用于 Feature 注入 Decision Context）。

        公式（PRD Chapter 5.2 C）：
        max(买入额×0.00025, 5) + 买入额×0.00001
        + max(卖出额×0.00025, 5) + 卖出额×0.0005 + 卖出额×0.00001

        Args:
            price: 估算价格（ask1/bid1/last）
            shares: 股数（默认100）

        Returns:
            往返总费用
        """
        amount = price * shares
        buy = self.buy_fee(amount)
        sell = self.sell_fee(amount)
        return buy.total + sell.total

    def _calc_commission(self, amount: Decimal) -> Decimal:
        """计算佣金（含最低5元约束）"""
        raw = amount * self._commission_rate
        commission = max(raw, self._min_commission)
        return self._round(commission)

    @staticmethod
    def _round(value: Decimal) -> Decimal:
        """四舍五入到分（2位小数）"""
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
