# Decision Prompt v2.28 / Planner v1.8

日期：2026-09-15（v2.27 减硬逻辑后：历史记录看得见，但提示词仍说「可以改变结论」，权重偏低）

## 相对 v2.27

不改硬约束、不要求必须照做上一分钟动作。本版只提高今日历史在推理中的权重。

1. 文首：开始本分钟推理前，先读「今日已成交」和「今日先前结论」，对照自己已经写下的判断，再结合本分钟数据。
2. 先前结论要认真对待；事实未变时不要无故推翻，事实已变时可以改变结论。仍写明不是必须执行的硬指令。
3. 区块标题与 `thought_process` 示例改为「推理前先读 / 先对照」。

不改：v2.26 队列（最多 30 条）、日切清空、v2.27 账户事实硬约束。

## 验证

- `python -m pytest tests/unit/test_prompt_v213.py tests/unit/test_prompt_v222.py tests/unit/test_prompt_v223.py tests/unit/test_prompt_v224.py tests/unit/test_prompt_v225.py tests/unit/test_prompt_v226.py tests/unit/test_prompt_v227.py tests/unit/test_prompt_v228.py tests/unit/test_pending_buyback.py -q`
