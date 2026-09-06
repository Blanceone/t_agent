# Decision Prompt v2.12

日期：2026-08-24 晚（代码闸补丁，待 8/25 生效）

## 相对 v2.11

v2.11 只改了提示词。v2.12 把仍会失手的三条升到代码，并让硬约束描述与执行层一致。

### 1. 同分钟 BUY+SELL：事实仲裁（tick.py）
不再整组丢弃。可卖>0 保留 SELL、丢掉 BUY；可卖=0 保留 BUY、丢掉 SELL。
硬约束改为：「只保留当前账户可执行的一条」。

### 2. 做T次数用尽（risk.py）
`t_status=hold_only` 时 BUY/SELL 一律拒绝 `REASON_T_BUDGET_EXCEEDED`。
接回未完成（buyback_only）仍允许 BUY。

### 3. 可卖为 0 的重复 SELL
调度层直接丢掉，同一标的同一天只反馈一次，避免再刷 100+ 条拒单日志。

### 4. 买入股数不再静默取整
非整百交给撮合层 `INVALID_LOT`，避免日志与模型意图对不上。

不改：不因仓位高于目标而禁卖。

## 验证

- `python -m pytest tests/ -q`
- `python scripts/test_prompt_v32.py`
