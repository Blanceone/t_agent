"""
T+1 制度测试 + 持仓状态机测试

验收标准1：T+1 当日买入不可卖
验收标准2：常规卖出不产生零股；清仓允许零股
"""

from decimal import Decimal

from agent.common.models import Position, PositionState
from agent.trading.position import PositionManager


class TestT1Rule:
    """T+1 制度测试"""

    def setup_method(self):
        self.mgr = PositionManager(stop_loss_ratio=Decimal("0.92"))

    def test_new_position_not_sellable(self):
        """建仓当日不可卖"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))

        assert pos.total_shares == 1000
        assert pos.sellable_shares == 0  # T+1：当日不可卖
        assert pos.today_bought == 1000

    def test_day_start_unfreeze(self):
        """日切后解冻"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))

        # 模拟日切
        self.mgr.on_day_start(pos)

        assert pos.sellable_shares == 1000  # 解冻
        assert pos.today_bought == 0
        assert pos.stop_breach_count == 0

    def test_buy_does_not_increase_sellable(self):
        """加仓不增加可卖"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))
        self.mgr.on_day_start(pos)  # 解冻

        assert pos.sellable_shares == 1000

        # 加仓
        self.mgr.apply_buy(pos, 500, Decimal("29.00"), Decimal("5.00"))

        assert pos.total_shares == 1500
        assert pos.sellable_shares == 1000  # 不变
        assert pos.today_bought == 500

    def test_sell_reduces_sellable(self):
        """卖出减少可卖"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))
        self.mgr.on_day_start(pos)

        self.mgr.apply_sell(pos, 300, Decimal("29.00"), Decimal("5.10"))

        assert pos.total_shares == 700
        assert pos.sellable_shares == 700


class TestPositionCost:
    """成本计算测试"""

    def setup_method(self):
        self.mgr = PositionManager(stop_loss_ratio=Decimal("0.92"))

    def test_initial_cost(self):
        """建仓成本"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))

        # 成本 = (28000 + 5) / 1000 = 28.005
        assert pos.cost_price == Decimal("28.0050")
        # 止损 = 28.005 * 0.92 = 25.7646
        assert pos.stop_loss_price == Decimal("25.7646")

    def test_weighted_average_cost(self):
        """加权平均成本"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))
        self.mgr.on_day_start(pos)

        # 加仓 500股 @ 30.00，费用 5.00
        self.mgr.apply_buy(pos, 500, Decimal("30.00"), Decimal("5.00"))

        # 新成本 = (28.005*1000 + 30*500 + 5) / 1500
        # = (28005 + 15000 + 5) / 1500 = 43010 / 1500 = 28.6733...
        assert pos.total_shares == 1500
        expected_cost = (Decimal("28.005") * 1000 + Decimal("30") * 500 + Decimal("5")) / 1500
        assert abs(pos.cost_price - expected_cost) < Decimal("0.001")

    def test_sell_does_not_change_cost(self):
        """卖出不改变成本"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))
        self.mgr.on_day_start(pos)

        original_cost = pos.cost_price
        self.mgr.apply_sell(pos, 500, Decimal("30.00"), Decimal("5.10"))

        assert pos.cost_price == original_cost


class TestPositionState:
    """持仓状态机测试"""

    def setup_method(self):
        self.mgr = PositionManager(stop_loss_ratio=Decimal("0.92"))

    def test_initial_state_active(self):
        """初始状态为 ACTIVE"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))
        assert pos.position_state == PositionState.ACTIVE

    def test_transition_to_clearing(self):
        """迁移到清仓"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))
        self.mgr.transition_to_clearing(pos, "STOP_LOSS")

        assert pos.position_state == PositionState.CLEARING
        assert pos.exit_reason == "STOP_LOSS"

    def test_transition_to_liq_fail(self):
        """迁移到清仓失败"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))
        self.mgr.transition_to_liq_fail(pos)

        assert pos.position_state == PositionState.LIQ_FAIL

    def test_can_buy_only_active(self):
        """只有 ACTIVE 可以买入"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))
        assert self.mgr.can_buy(pos) is True

        self.mgr.transition_to_clearing(pos, "STOP_LOSS")
        assert self.mgr.can_buy(pos) is False

    def test_can_sell_active_and_clearing(self):
        """ACTIVE 和 CLEARING 可以卖出"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))
        assert self.mgr.can_sell(pos) is True

        self.mgr.transition_to_clearing(pos, "STOP_LOSS")
        assert self.mgr.can_sell(pos) is True

        self.mgr.transition_to_liq_fail(pos)
        assert self.mgr.can_sell(pos) is False


class TestRealizedPnl:
    """已实现盈亏测试"""

    def setup_method(self):
        self.mgr = PositionManager(stop_loss_ratio=Decimal("0.92"))

    def test_profit(self):
        """盈利卖出"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))
        self.mgr.on_day_start(pos)

        # 成本 28.005，卖出价 30.00，500股，费用 5.10
        pnl = self.mgr.apply_sell(pos, 500, Decimal("30.00"), Decimal("5.10"))

        # (30 - 28.005) * 500 - 5.10 = 997.5 - 5.10 = 992.40
        expected = (Decimal("30.00") - pos.cost_price) * 500 - Decimal("5.10")
        assert pnl == expected

    def test_loss(self):
        """亏损卖出"""
        pos = self.mgr.create_position("600584", 1000, Decimal("28.00"), Decimal("5.00"))
        self.mgr.on_day_start(pos)

        # 成本 28.005，卖出价 26.00
        pnl = self.mgr.apply_sell(pos, 500, Decimal("26.00"), Decimal("5.10"))

        assert pnl < 0
