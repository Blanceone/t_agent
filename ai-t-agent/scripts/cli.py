"""
CLI 用户指令接口

用法：
    python -m scripts.cli ADD 600584
    python -m scripts.cli REMOVE 600584
    python -m scripts.cli PAUSE
    python -m scripts.cli RESUME
    python -m scripts.cli SET_CASH 50000
    python -m scripts.cli STATUS   # 账户/持仓现价/股票池现价/最近10笔成交
    python -m scripts.cli CLEAR_ALL
"""

import argparse
import json
import sys
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.config.loader import load_config
from agent.trading.engine import TradingEngine
from agent.trading.status import (
    RECENT_TRADE_LIMIT,
    fetch_quotes,
    format_status,
    load_recent_trades,
)
from agent.common.event_log import EventLog
from agent.common.utils import today_str


def get_engine():
    config = load_config()
    event_log = EventLog(f"{config.data_dir}/logs")
    engine = TradingEngine(config, event_log)
    account_path = f"{config.data_dir}/account/state.json"
    engine.account.load(account_path)
    return engine, config


def notify_service(engine):
    """写信号文件通知常驻服务重载账户。

    CLI 与服务是独立进程：不写信号的话，服务会用旧内存副本 persist() 覆盖本次修改。
    """
    flag = engine.cli_flag_path()
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(today_str())


def cmd_add(code: str):
    engine, config = get_engine()
    limit = config.trading.watchlist_limit
    if len(engine.account.watchlist) >= limit:
        print(f"错误: 股票池已达上限 {limit}")
        return
    if engine.account.add_to_watchlist(code, today_str()):
        engine.account.save()
        notify_service(engine)
        print(f"已添加: {code}（常驻服务将在下个 Tick/日切时生效）")
    else:
        print(f"已存在: {code}")


def cmd_remove(code: str):
    engine, _ = get_engine()
    if code in engine.account.positions:
        engine.enqueue_liquidation(code, "USER_REMOVE")
        engine.account.save()
        notify_service(engine)
        print(f"已触发清仓: {code}（清仓完成后移出池）")
    elif engine.account.remove_from_watchlist(code):
        engine.account.save()
        notify_service(engine)
        print(f"已移除: {code}（常驻服务将在下个 Tick/日切时生效）")
    else:
        print(f"不在池中: {code}")


def cmd_status():
    engine, config = get_engine()
    acc = engine.account
    codes = list(dict.fromkeys([*acc.watchlist.keys(), *acc.positions.keys()]))
    quotes = fetch_quotes(config, codes)
    log_path = Path(config.data_dir) / "logs" / "agent.log"
    trades = load_recent_trades(log_path, RECENT_TRADE_LIMIT)
    print(format_status(acc, quotes, trades))


def cmd_set_cash(amount: float):
    engine, _ = get_engine()
    engine.account.cash.available = Decimal(str(amount))
    engine.account.initial_cash = Decimal(str(amount))
    engine.account.last_nav = Decimal(str(amount))
    engine.account.peak_nav = Decimal(str(amount))
    engine.account.save()
    notify_service(engine)
    print(f"资金已调整为: {amount}（常驻服务将在下个 Tick/日切时生效）")


def cmd_pause():
    print("PAUSE 指令已记录（需在运行时通过 Scheduler 生效）")
    # 写入状态文件
    state_file = Path("data/account/mode.json")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"mode": "PAUSE"}))


def cmd_resume():
    print("RESUME 指令已记录")
    state_file = Path("data/account/mode.json")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"mode": "NORMAL"}))


def cmd_clear_all():
    engine, _ = get_engine()
    for code in list(engine.account.positions.keys()):
        engine.enqueue_liquidation(code, "USER_REMOVE")
    engine.account.save()
    notify_service(engine)
    print("已触发全部清仓（常驻服务将在下个 Tick/日切时生效）")


def main():
    parser = argparse.ArgumentParser(description="AI-T-Agent CLI")
    parser.add_argument("command", choices=["ADD", "REMOVE", "PAUSE", "RESUME",
                                            "SET_CASH", "STATUS", "CLEAR_ALL"])
    parser.add_argument("arg", nargs="?", default=None)
    args = parser.parse_args()

    if args.command == "ADD":
        if not args.arg:
            print("用法: cli ADD <code>")
            return
        cmd_add(args.arg)
    elif args.command == "REMOVE":
        if not args.arg:
            print("用法: cli REMOVE <code>")
            return
        cmd_remove(args.arg)
    elif args.command == "STATUS":
        cmd_status()
    elif args.command == "SET_CASH":
        if not args.arg:
            print("用法: cli SET_CASH <amount>")
            return
        cmd_set_cash(float(args.arg))
    elif args.command == "PAUSE":
        cmd_pause()
    elif args.command == "RESUME":
        cmd_resume()
    elif args.command == "CLEAR_ALL":
        cmd_clear_all()


if __name__ == "__main__":
    main()
