"""
初始化模拟账户 + 股票池

用法：
    python -m scripts.seed_account --codes 600584,002049 --cash 30000
"""

import argparse
import sys
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.config.loader import load_config
from agent.trading.engine import TradingEngine
from agent.common.event_log import EventLog
from agent.common.utils import today_str


def main():
    parser = argparse.ArgumentParser(description="初始化模拟账户")
    parser.add_argument("--codes", type=str, default="600584,002049",
                        help="初始股票代码，逗号分隔")
    parser.add_argument("--cash", type=float, default=30000,
                        help="初始资金")
    parser.add_argument("--reset", action="store_true",
                        help="重置已有账户")
    args = parser.parse_args()

    config = load_config()
    account_path = f"{config.data_dir}/account/state.json"

    # 检查是否已存在
    if Path(account_path).exists() and not args.reset:
        print(f"账户已存在: {account_path}")
        print("使用 --reset 参数重置")
        return

    # 创建引擎
    event_log = EventLog(f"{config.data_dir}/logs")
    engine = TradingEngine(config, event_log)

    # 设置初始资金
    engine.account.cash.available = Decimal(str(args.cash))
    engine.account.initial_cash = Decimal(str(args.cash))
    engine.account.last_nav = Decimal(str(args.cash))
    engine.account.peak_nav = Decimal(str(args.cash))

    # 添加股票池
    codes = [c.strip() for c in args.codes.split(",")]
    date_str = today_str()
    for code in codes:
        engine.account.add_to_watchlist(code, date_str)
        print(f"  添加到股票池: {code}")

    # 保存
    engine.account.save(account_path)
    print(f"\n账户初始化完成:")
    print(f"  资金: {args.cash}")
    print(f"  股票池: {codes}")
    print(f"  保存至: {account_path}")


if __name__ == "__main__":
    main()
