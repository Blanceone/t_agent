# Decision Prompt v2.24 / Planner v1.7

日期：2026-09-08（v2.23 部署后审查）

## 相对 v2.23

v2.23 跨日未接回与上限 0 口径保持。本版只补两处事实，不改仓位限制，不要求必须接回。

1. 当天冲减过未接回且已清零：持仓行写「接回已闭环」，不要写「今日无卖出，不是接回」。无未接回的纯买入仍标成不是接回。
2. 有未接回时，最多可买 = min(购买力/单票上限, 未接回) 向下取整到 100 股。空仓接回不会按购买力买过未接回变成建仓。

## 验证

- `python -m pytest tests/unit/test_prompt_v213.py tests/unit/test_prompt_v222.py tests/unit/test_prompt_v223.py tests/unit/test_prompt_v224.py tests/unit/test_pending_buyback.py -q`
