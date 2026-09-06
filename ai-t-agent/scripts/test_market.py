"""验证行情接入：分别测试 tencent / tushare / akshare 三个数据源"""
import sys
sys.path.insert(0, "/opt/ai-t-agent/src")

from agent.config.loader import load_config
from agent.market.service import MarketService

config = load_config()

for source in ("tencent", "tushare", "akshare"):
    config.market.data_source = source
    svc = MarketService(config)
    svc.set_watchlist(["002185", "600584"])
    # 直接调用对应 fetcher，避免回退链掩盖失败
    fetcher = getattr(svc, f"_fetch_{source}")
    try:
        quotes = fetcher()
    except Exception as e:
        print(f"[{source}] 异常: {e}")
        continue
    if not quotes:
        print(f"[{source}] ✗ 拉取为空")
        continue
    print(f"[{source}] ✓ 共 {len(quotes)} 只:")
    for code, q in quotes.items():
        print(f"    {code} {q.name}: 现价={q.last} 昨收={q.pre_close} 高={q.high} 低={q.low}")

# 最后验证链式回退的 refresh()
config.market.data_source = "tencent"
svc = MarketService(config)
svc.set_watchlist(["002185", "600584"])
quotes = svc.refresh()
print(f"\nrefresh() 链式回退: {'✓ 成功' if quotes else '✗ 失败'}，共 {len(quotes)} 只")
