"""公共 Fixture"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from agent.config.schema import AppConfig, FeeConfig
from agent.common.models import Quote


TZ_CST = timezone(timedelta(hours=8))


@pytest.fixture
def default_config() -> AppConfig:
    """标准测试配置"""
    return AppConfig()


@pytest.fixture
def fee_config() -> FeeConfig:
    """费用配置"""
    return FeeConfig()


@pytest.fixture
def sample_quote() -> Quote:
    """模拟行情：600584 长电科技"""
    return Quote(
        code="600584",
        name="长电科技",
        last=Decimal("28.00"),
        bid1=Decimal("27.90"),
        ask1=Decimal("28.10"),
        high=Decimal("28.50"),
        low=Decimal("27.50"),
        open=Decimal("27.80"),
        pre_close=Decimal("27.60"),
        limit_up=Decimal("30.36"),
        limit_down=Decimal("24.84"),
        volume=1000000,
        turnover=Decimal("28000000"),
        vwap=Decimal("28.00"),
        is_suspended=False,
        is_st=False,
        timestamp=datetime(2026, 7, 28, 9, 31, 0, tzinfo=TZ_CST),
    )


@pytest.fixture
def low_price_quote() -> Quote:
    """模拟行情：低价股 2元"""
    return Quote(
        code="601015",
        name="低价股",
        last=Decimal("2.00"),
        bid1=Decimal("1.99"),
        ask1=Decimal("2.01"),
        high=Decimal("2.10"),
        low=Decimal("1.95"),
        open=Decimal("2.00"),
        pre_close=Decimal("2.00"),
        limit_up=Decimal("2.20"),
        limit_down=Decimal("1.80"),
        volume=5000000,
        turnover=Decimal("10000000"),
        vwap=Decimal("2.00"),
        is_suspended=False,
        is_st=False,
        timestamp=datetime(2026, 7, 28, 9, 31, 0, tzinfo=TZ_CST),
    )
