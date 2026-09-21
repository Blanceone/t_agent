# Decision Prompt v2.29 / Planner v1.8

日期：2026-09-17（持仓常卡在 200/300 股：净值×50%/现价再整手取整）

## 相对 v2.28

把单票仓位上限从净值 50% 改为 100%。仓位大小交给模型；现金预留 20% 和 100 股整手仍是账户事实。

1. `max_single_position_ratio`: 0.50 → 1.00（配置 + schema 默认）。
2. 规则 2/3：加仓/建仓约束改为现金预留与最多可买，不再写「单票上限」当日常禁令。
3. 未接回 300、空仓时，购买力足够则可一次最多买到整手后的未接回股数（不再先被 50% 砍成 200）。

不改：现金预留 20%、整手、T+1、次数计数、不强制当日接回、v2.28 历史对照。

## 验证

- `python -m pytest tests/unit/test_prompt_v213.py tests/unit/test_prompt_v228.py tests/unit/test_prompt_v229.py tests/unit -q`
