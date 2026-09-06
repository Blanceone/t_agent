"""
费用计算精度测试

验收标准4：股价约2元时，100股往返费用约10.1元（含双边最低佣金）
"""

from decimal import Decimal

from agent.config.schema import FeeConfig
from agent.trading.fee import FeeCalculator


class TestFeeCalculator:
    """费用计算器测试"""

    def setup_method(self):
        self.fee_calc = FeeCalculator(FeeConfig())

    def test_buy_fee_low_price(self):
        """低价股买入费用：2元×100股=200元"""
        amount = Decimal("200")  # 2.00 * 100
        detail = self.fee_calc.buy_fee(amount)

        # 佣金 = max(200 * 0.00025, 5) = max(0.05, 5) = 5.00
        assert detail.commission == Decimal("5.00")
        # 过户费 = 200 * 0.00001 = 0.002 → 0.00
        assert detail.transfer_fee == Decimal("0.00")
        # 印花税 = 0（买入无印花税）
        assert detail.stamp_tax == Decimal("0")
        # 总计 = 5.00
        assert detail.total == Decimal("5.00")

    def test_sell_fee_low_price(self):
        """低价股卖出费用：2元×100股=200元"""
        amount = Decimal("200")
        detail = self.fee_calc.sell_fee(amount)

        # 佣金 = max(200 * 0.00025, 5) = 5.00
        assert detail.commission == Decimal("5.00")
        # 过户费 = 200 * 0.00001 = 0.002 → 0.00
        assert detail.transfer_fee == Decimal("0.00")
        # 印花税 = 200 * 0.0005 = 0.10
        assert detail.stamp_tax == Decimal("0.10")
        # 总计 = 5.10
        assert detail.total == Decimal("5.10")

    def test_round_trip_fee_acceptance(self):
        """
        验收标准4：2元股价100股往返费用 ≈ 10.10元

        买入：佣金5.00 + 过户费0.00 = 5.00
        卖出：佣金5.00 + 过户费0.00 + 印花税0.10 = 5.10
        总计：10.10
        """
        price = Decimal("2.00")
        total = self.fee_calc.round_trip_fee_est(price, shares=100)
        assert total == Decimal("10.10")

    def test_buy_fee_high_price(self):
        """高价股买入费用：28元×100股=2800元"""
        amount = Decimal("2800")
        detail = self.fee_calc.buy_fee(amount)

        # 佣金 = max(2800 * 0.00025, 5) = max(0.70, 5) = 5.00
        assert detail.commission == Decimal("5.00")
        # 过户费 = 2800 * 0.00001 = 0.028 → 0.03
        assert detail.transfer_fee == Decimal("0.03")

    def test_buy_fee_very_high_price(self):
        """超高价股买入：100元×1000股=100000元"""
        amount = Decimal("100000")
        detail = self.fee_calc.buy_fee(amount)

        # 佣金 = max(100000 * 0.00025, 5) = max(25, 5) = 25.00
        assert detail.commission == Decimal("25.00")
        # 过户费 = 100000 * 0.00001 = 1.00
        assert detail.transfer_fee == Decimal("1.00")

    def test_sell_fee_high_price(self):
        """高价股卖出费用：28元×100股=2800元"""
        amount = Decimal("2800")
        detail = self.fee_calc.sell_fee(amount)

        # 佣金 = 5.00
        assert detail.commission == Decimal("5.00")
        # 印花税 = 2800 * 0.0005 = 1.40
        assert detail.stamp_tax == Decimal("1.40")
        # 过户费 = 0.03
        assert detail.transfer_fee == Decimal("0.03")

    def test_min_commission_boundary(self):
        """最低佣金边界：金额=20000时佣金恰好=5元"""
        amount = Decimal("20000")
        detail = self.fee_calc.buy_fee(amount)
        # 20000 * 0.00025 = 5.00
        assert detail.commission == Decimal("5.00")

    def test_above_min_commission(self):
        """超过最低佣金：金额=20001"""
        amount = Decimal("20001")
        detail = self.fee_calc.buy_fee(amount)
        # 20001 * 0.00025 = 5.00025 → 5.00 (四舍五入)
        assert detail.commission == Decimal("5.00")

        amount = Decimal("40000")
        detail = self.fee_calc.buy_fee(amount)
        # 40000 * 0.00025 = 10.00
        assert detail.commission == Decimal("10.00")
