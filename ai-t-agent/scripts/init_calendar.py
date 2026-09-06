"""
生成A股交易日历

用法：
    python -m scripts.init_calendar --year 2026
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def generate_calendar(year: int) -> dict:
    """使用 akshare 生成交易日历"""
    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        dates = df["trade_date"].astype(str).tolist()
        # 过滤年份
        year_str = str(year)
        days = []
        for d in dates:
            if d.startswith(year_str):
                days.append({"date": d, "session": "full"})
        return {"year": year, "days": days}
    except Exception as e:
        print(f"akshare 获取失败: {e}")
        print("使用工作日回退方案...")
        return generate_fallback(year)


def generate_fallback(year: int) -> dict:
    """回退方案：生成工作日日历（不含节假日）"""
    from datetime import date, timedelta
    days = []
    d = date(year, 1, 1)
    end = date(year, 12, 31)
    while d <= end:
        if d.weekday() < 5:  # 周一到周五
            days.append({"date": d.strftime("%Y-%m-%d"), "session": "full"})
        d += timedelta(days=1)
    return {"year": year, "days": days, "note": "fallback_weekdays_only"}


def main():
    parser = argparse.ArgumentParser(description="生成交易日历")
    parser.add_argument("--year", type=int, default=2026, help="年份")
    args = parser.parse_args()

    calendar = generate_calendar(args.year)

    output_path = Path(__file__).parent.parent / "config" / "trading_calendar.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(calendar, f, ensure_ascii=False, indent=2)

    print(f"交易日历已生成: {output_path}")
    print(f"  年份: {args.year}")
    print(f"  交易日数: {len(calendar['days'])}")


if __name__ == "__main__":
    main()
