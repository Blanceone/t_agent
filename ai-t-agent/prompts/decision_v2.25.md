# Decision Prompt v2.25 / Planner v1.7

日期：2026-09-09（v2.24 首日复盘）

## 相对 v2.24

v2.24 跨日接回角色与可买上限保持。本版只补预计算，不改硬约束，不要求必须接回，不禁止高于卖出价接回。

1. 有未接回时预计算增加接回价差：`若按现价接回：卖出均价A-现价B=±X元/股（买在卖出价上方/下方）`，并可附 `扣往返费用后约±Y元/股`。方向是卖出价减现价，与「较卖出均价」（现价减卖出价）分开，避免把现价上涨当成这半笔 T 还能赚。
2. 费用行去掉「打平」，只报 `N股往返费用约F元（约P元/股）`。
3. 文首标明现价接回价差是数据，不是接回时机的硬指令。

## 验证

- `python -m pytest tests/unit/test_prompt_v213.py tests/unit/test_prompt_v222.py tests/unit/test_prompt_v223.py tests/unit/test_prompt_v224.py tests/unit/test_prompt_v225.py tests/unit/test_pending_buyback.py -q`
