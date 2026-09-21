# Decision Prompt v2.23 / Planner v1.7

日期：2026-09-08（WAIT/上限0 把空仓锁成全日 HOLD；昨天未接回 300 股不过夜）

## 相对 v2.22

v2.22 手数/次数口径保持。本版只补两处账户事实，不禁止观望，不要求必须接回或建仓。

1. 做 T 次数上限 **>0 且已用完** 才写「次数已满、只可 HOLD」。上限 0 / WAIT 不是次数用尽；空仓仍可建仓或观望。Planner：不要把 `max_trades_hint` 写成 0 来锁死买卖。
2. 未接回落入账户并跨日保留（卖出均价一并保存）。09:20 计划与分钟持仓都写正数未接回；买入是接回不是建仓。提示词「可等后续交易日」与账户事实一致。
3. 决策清仓维护未接回；止损/强平/移出池的卖出不作为做 T 接回。日切清空 `today_fills`，不清空未接回。

不改：仓位限制、`_t_budget_used` 计数、Regime 上限、必须建仓/必须接回。

## 验证

- `python -m pytest tests/unit/test_prompt_v213.py tests/unit/test_prompt_v222.py tests/unit/test_prompt_v223.py tests/unit/test_pending_buyback.py -q`
