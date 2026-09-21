# Decision Prompt v2.27 / Planner v1.8

日期：2026-09-15（v2.26 复盘：历史结论生效，14:26 仍被「仅允许接回完成做T」推去高接）

## 相对 v2.26

次数计数、Regime 上限、风控拒绝不变。本版只减提示词里的策略口径，硬约束回到账户/流动性事实。

1. 次数用尽且有未接回：写「禁止 SELL 和新建仓 BUY；接回 BUY 仍可执行（不强制今日）」。不再写「仅允许接回完成做 T」。
2. 真空仓：只保留「无持仓禁止 SELL」。不再写「仅可执行计划中的买入建仓部分」。
3. 规则去掉「高抛低吸」「首次建仓不超过 25%」「低于目标才允许加仓」。仓位相对目标是数据。
4. Planner：去掉「必须遵守」和「合适低位」；仓位相对目标不要写成必须加减仓。

不改：`_t_budget_used`、Regime `max_trades`、同分钟单向、T+1、现金/单票上限、不强制当日接回。

## 验证

- `python -m pytest tests/unit/test_prompt_v213.py tests/unit/test_prompt_v222.py tests/unit/test_prompt_v223.py tests/unit/test_prompt_v224.py tests/unit/test_prompt_v225.py tests/unit/test_prompt_v226.py tests/unit/test_prompt_v227.py tests/unit/test_pending_buyback.py -q`
