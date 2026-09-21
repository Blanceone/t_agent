# Decision Prompt v2.30 / Planner v1.9

日期：2026-09-21（未接回 300 把最多可买焊死；空仓只能当接回）

## 相对 v2.29

1. 有未接回时，最多可买不再与未接回取小；只保留现金预留 20%、单票 100%、整手。
2. 提示词不再做接回/建仓/闭环记账。未接回是账户事实（股数、卖出均价），不是买入上限，也不强制买回。买入可以超过未接回。
3. 「今日已成交」只写当天买卖手数。次数用尽后仍可 BUY，禁止再卖。

不改：现金预留 20%、整手、T+1、`_t_budget_used` 计数、v2.28 历史对照、接回价差预计算（数据，不是时机硬指令）。

## 验证

- `python -m pytest tests/unit/test_prompt_v213.py tests/unit/test_prompt_v222.py tests/unit/test_prompt_v223.py tests/unit/test_prompt_v224.py tests/unit/test_prompt_v227.py tests/unit/test_prompt_v229.py tests/unit/test_prompt_v230.py tests/unit/test_pending_buyback.py -q`
