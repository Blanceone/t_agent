"""服务器日志分析脚本：统计事件分布、错误、决策情况"""
import json
import collections

LOG = "/opt/ai-t-agent/data/logs/event_log.jsonl"

events = collections.Counter()
errors = []
decisions = collections.Counter()
by_day = collections.defaultdict(lambda: collections.Counter())
llm_calls = []

with open(LOG, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        ev = e.get("event", "?")
        events[ev] += 1
        ts = e.get("timestamp", "")[:10]
        by_day[ts][ev] += 1
        if e.get("level") == "error":
            errors.append(e)
        if "decision" in ev or ev in ("signal_generated", "order_submitted", "order_filled", "trade_executed"):
            decisions[ev] += 1
        if ev.startswith("llm_call"):
            llm_calls.append(e)

print("=== 事件类型分布 TOP25 ===")
for k, v in events.most_common(25):
    print(f"  {k}: {v}")

print("\n=== 按天统计 ===")
for day in sorted(by_day):
    c = by_day[day]
    total = sum(c.values())
    errs = sum(v for k, v in c.items() if k in ())
    print(f"  {day}: 共{total}条事件")
    for k, v in c.most_common(6):
        print(f"      {k}: {v}")

print(f"\n=== 错误事件 ({len(errors)}条) ===")
for e in errors[:15]:
    print(f"  [{e.get('timestamp', '')[:19]}] {e.get('module')}: {e.get('event')} - {e.get('error', '')}")

print(f"\n=== 决策/交易相关事件 ===")
for k, v in decisions.items():
    print(f"  {k}: {v}")
if not decisions:
    print("  (无任何决策或交易事件)")

print(f"\n=== LLM 调用事件 ({len(llm_calls)}条) ===")
for e in llm_calls[-10:]:
    print(f"  [{e.get('timestamp', '')[:19]}] {e.get('event')} model={e.get('model')} err={e.get('error', '')}")
