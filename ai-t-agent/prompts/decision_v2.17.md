# Decision Prompt v2.17 / Planner v1.4 / MU v1.1

日期：2026-08-27 晚（审查项：MU建议句、手数示例、加仓/接回、竞价轨迹）

## 相对 v2.16 / planner.v1.3

1. MU 摘要改为指数涨跌/振幅/量比；LLM 若写「建议减少做T」会被代码覆盖。
2. 决策：`shares` 示例标明占位；「禁止加仓 BUY」≠ 禁止接回。
3. Planner：竞价快照字段标明尚未形成日内含义；max_trades_hint 不得超过上方约束。
4. 09:20 刷新后清空日内轨迹，开盘至今从 09:30 起算。

不改「高于计划价就卖」等决策权。

## 验证

- `python -m pytest tests/ -q`
- `python scripts/test_prompt_v37.py`
