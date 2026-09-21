# Decision Prompt v2.26 / Planner v1.7

日期：2026-09-14（v2.25 复盘：跨分钟看不到自己上一分钟结论）

## 相对 v2.25

v2.25 接回价差预计算保持。本版只补跨分钟记忆，不改硬约束，不要求必须照做上一分钟。

1. 模型每分钟输出 `minute_conclusion`（一句话：动作+要点）。缺省时用该分钟 `reason` 兜底。
2. 追加到当日队列（最多 30 条），写入下一分钟 Prompt 的「今日先前结论」。
3. 文首标明先前结论是数据、不是必须执行的硬指令；本分钟仍按当前数据判断，可以改变结论。
4. 09:20 日切清空。不写入硬性约束。

用来减轻 9/14 那种 09:39「卖是杀跌」与 09:40「高抛」互不认账：下一分钟能看见上一分钟自己写的话。

## 验证

- `python -m pytest tests/unit/test_prompt_v213.py tests/unit/test_prompt_v222.py tests/unit/test_prompt_v223.py tests/unit/test_prompt_v224.py tests/unit/test_prompt_v225.py tests/unit/test_prompt_v226.py tests/unit/test_pending_buyback.py -q`
