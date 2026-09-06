"""
决策落地前的账户事实过滤。

不替代 Risk；只处理「提示词说了但代码原先没做对」的两件事：
1. 同分钟 BUY+SELL：按可卖数量保留可执行腿，而不是两条都丢。
2. 可卖不足的 SELL：由调用方按日去重反馈，避免复读刷日志。
"""

from typing import Any, Dict, Set, Tuple

from agent.common.models import ActionType, DecisionItem

def sellable_shares(position: Any) -> int:
    if position is None:
        return 0
    return int(getattr(position, "sellable_shares", 0) or 0)


def keep_action_on_conflict(sellable: int) -> ActionType:
    """可卖>0 先卖后买的当前步骤是卖；否则卖出不可执行，保留买。"""
    return ActionType.SELL if sellable > 0 else ActionType.BUY


def conflict_drop_actions(
    decisions: list,
    positions: Dict[str, Any],
) -> Dict[str, ActionType]:
    """
    返回 {code: 应丢弃的方向}。
    无冲突的标的不出现在结果里。
    """
    buy_codes = {it.code for it in decisions if it.action == ActionType.BUY}
    sell_codes = {it.code for it in decisions if it.action == ActionType.SELL}
    drop: Dict[str, ActionType] = {}
    for code in buy_codes & sell_codes:
        keep = keep_action_on_conflict(sellable_shares(positions.get(code)))
        drop[code] = ActionType.BUY if keep == ActionType.SELL else ActionType.SELL
    return drop


def is_impossible_sell(item: DecisionItem, position: Any) -> bool:
    if item.action != ActionType.SELL:
        return False
    return item.shares > sellable_shares(position)


class OncePerDay:
    """同一 (日期, 标的, 原因) 只允许反馈/打日志一次。"""

    def __init__(self) -> None:
        self._date = ""
        self._seen: Set[Tuple[str, str, str]] = set()

    def reset_if_new_day(self, date_str: str) -> None:
        if date_str != self._date:
            self._date = date_str
            self._seen.clear()

    def first_time(self, date_str: str, code: str, reason: str) -> bool:
        self.reset_if_new_day(date_str)
        key = (date_str, code, reason)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True
