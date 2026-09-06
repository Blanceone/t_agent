"""
行情接入 + Feature Engine

数据源：tencent（主） / akshare（备）（可配置）
"""

from collections import deque
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import requests

from agent.common.models import FeatureSnapshot, Quote
from agent.common.logger import get_logger
from agent.common.utils import now_cst
from agent.config.schema import AppConfig
from agent.trading.fee import FeeCalculator

logger = get_logger("market.service")

# 日内轨迹保留最近 60 个 Tick（约1小时）
INTRAY_MAX_TICKS = 60
# 大盘指数代码（腾讯接口）
INDEX_SYMBOL = "sh000001"


def _bar_ymd(date_s) -> str:
    return str(date_s).replace("-", "")[:8]


def avg_volume_5d_shares(bars: List[dict], today_ymd: str) -> Optional[float]:
    """近5个已收盘日均量（股）。日K成交量为手。"""
    completed = [b for b in bars if _bar_ymd(b.get("date", ""))
                 and _bar_ymd(b["date"]) < today_ymd]
    win = completed[-5:]
    if not win:
        return None
    avg_hand = sum(float(b["volume"]) for b in win) / len(win)
    if avg_hand <= 0:
        return None
    return avg_hand * 100.0


def path_10m_label(prices: List) -> Optional[str]:
    """近10分钟窗口内高点与低点的先后（数据，非判断）。"""
    if len(prices) < 3:
        return None
    i_hi = max(range(len(prices)), key=lambda i: prices[i])
    i_lo = min(range(len(prices)), key=lambda i: prices[i])
    if i_hi == i_lo:
        return None
    if i_hi < i_lo:
        return "近10分钟高点早于低点"
    return "近10分钟低点早于高点"


def _dec_field(raw: str, fallback: Decimal) -> Decimal:
    try:
        if raw:
            v = Decimal(str(raw))
            if v > 0:
                return v
    except Exception:
        pass
    return fallback

logger = get_logger("market.service")

# 日内轨迹保留最近 60 个 Tick（约1小时）
INTRAY_MAX_TICKS = 60
# 大盘指数代码（腾讯接口）
INDEX_SYMBOL = "sh000001"


class MarketService:
    """行情接入服务"""

    def __init__(self, config: AppConfig):
        self._config = config
        self._watchlist: List[str] = []
        self._latest_quotes: Dict[str, Quote] = {}
        # 日内分钟级轨迹：code -> deque[(时间, 现价, 累计成交量, 累计成交额)]
        self._intraday: Dict[str, deque] = {}
        # 全日最高/最低首次刷新时刻
        self._extreme_ts: Dict[str, dict] = {}
        # 大盘指数快照（上证指数，仅用于环境感知，不参与交易/NAV）
        self._index_quote: Optional[Quote] = None
        # 日K技术位缓存：code -> {ma5, ma20, support, resistance, volume_ratio, closes}
        self._kline_tech: Dict[str, dict] = {}

    def set_watchlist(self, codes: List[str]):
        self._watchlist = codes

    def get_quotes(self) -> Dict[str, Quote]:
        """获取最新行情"""
        # 实际实现中从 akshare/tushare 拉取
        # MVP 阶段返回缓存或模拟数据
        return self._latest_quotes

    def update_quotes(self, quotes: Dict[str, Quote]):
        """外部注入行情（用于测试/模拟）"""
        self._latest_quotes = quotes

    def refresh(self) -> Dict[str, Quote]:
        """刷新行情（主源 + 链式回退：tencent → tushare → akshare）"""
        primary = self._config.market.data_source
        if primary not in ("tencent", "tushare", "akshare"):
            primary = "tencent"
        # 回退链：主源优先，其余按可靠性排序
        order = [primary] + [s for s in ("tencent", "tushare", "akshare") if s != primary]

        fetchers = {
            "tencent": self._fetch_tencent,
            "tushare": self._fetch_tushare,
            "akshare": self._fetch_akshare,
        }

        try:
            for i, source in enumerate(order):
                if i > 0:
                    logger.warning("market_source_fallback", from_=order[i - 1], to=source)
                quotes = fetchers[source]()
                if quotes:
                    self._latest_quotes = quotes
                    self._record_intraday(quotes)
                    self._fetch_index()  # 大盘指数旁路拉取（失败不影响个股）
                    return quotes
            return self._latest_quotes
        except Exception as e:
            logger.error("market_refresh_failed", error=str(e))
            return self._latest_quotes

    def get_index_quote(self) -> Optional[Quote]:
        """获取大盘指数快照（上证指数）"""
        return self._index_quote

    def _fetch_index(self) -> None:
        """拉取上证指数（腾讯接口，独立于个股行情）"""
        try:
            resp = requests.get(
                f"https://qt.gtimg.cn/q={INDEX_SYMBOL}",
                timeout=5,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            resp.encoding = "gbk"
            payload = resp.text.split("=", 1)[1].strip().strip('";')
            f = payload.split("~")
            if len(f) < 40 or not f[3]:
                return
            last = Decimal(f[3])
            pre_close = Decimal(f[4]) if f[4] else last
            high = Decimal(f[33]) if len(f) > 33 and f[33] else last
            low = Decimal(f[34]) if len(f) > 34 and f[34] else last
            self._index_quote = Quote(
                code="000001", name=f[1] or "上证指数",
                last=last, bid1=last, ask1=last,
                high=high, low=low, open=last,
                pre_close=pre_close,
                limit_up=last, limit_down=last,
                volume=0, turnover=Decimal(0), vwap=last,
                is_suspended=False, is_st=False,
                timestamp=now_cst(),
            )
        except Exception as e:
            logger.warning("index_fetch_failed", error=str(e))

    # ==================== 日K技术位 ====================

    def refresh_klines(self, days: int = 30) -> None:
        """日切时拉取股票池日K并计算技术位（MA5/MA20/支撑/压力/量比）"""
        for code in self._watchlist:
            try:
                bars = self._fetch_kline(code, days)
                if not bars:
                    continue
                closes = [Decimal(str(b["close"])) for b in bars]
                ma5 = sum(closes[-5:]) / min(5, len(closes))
                ma20 = sum(closes[-20:]) / min(20, len(closes)) if len(closes) >= 20 else None
                # 支撑/压力：最近5个交易日（不含最新一根）的低点/高点
                win = bars[-6:-1] if len(bars) >= 6 else bars[:-1]
                support = min(Decimal(str(b["low"])) for b in win) if win else None
                resistance = max(Decimal(str(b["high"])) for b in win) if win else None
                today_ymd = now_cst().strftime("%Y%m%d")
                avg_vol = avg_volume_5d_shares(bars, today_ymd)
                # 量比快照：最新一根 / 近5日均量（开盘前可能含未完成K，分钟层用今日累计/均量覆盖）
                vols = [float(b["volume"]) for b in bars]
                vr = (vols[-1] / (sum(vols[-6:-1]) / len(vols[-6:-1]))) \
                    if len(vols) >= 6 and sum(vols[-6:-1]) > 0 else None
                self._kline_tech[code] = {
                    "ma5": ma5, "ma20": ma20,
                    "support": support, "resistance": resistance,
                    "volume_ratio": vr,
                    "avg_volume_5d": avg_vol,
                }
            except Exception as e:
                logger.warning("kline_fetch_failed", code=code, error=str(e))
        if self._kline_tech:
            logger.info("kline_tech_ready", codes=list(self._kline_tech.keys()))

    def kline_tech(self) -> Dict[str, dict]:
        """获取日K技术位缓存"""
        return self._kline_tech

    def _fetch_kline(self, code: str, days: int = 30) -> List[dict]:
        """腾讯日K接口，返回按时间升序的K线列表 [{date, open, close, high, low, volume}]"""
        symbol = self._tencent_symbol(code)
        resp = requests.get(
            f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            f"?param={symbol},day,,,{days},qfq",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        data = resp.json().get("data", {}).get(symbol, {})
        raw = data.get("qfqday") or data.get("day") or []
        bars = []
        for row in raw:
            # [日期, 开, 收, 高, 低, 成交量, ...]
            if len(row) < 6:
                continue
            bars.append({
                "date": row[0],
                "open": float(row[1]), "close": float(row[2]),
                "high": float(row[3]), "low": float(row[4]),
                "volume": float(row[5]),
            })
        return bars

    # ==================== 日内轨迹 ====================

    def reset_intraday(self) -> None:
        """日切时清空日内轨迹"""
        self._intraday.clear()
        self._extreme_ts.clear()

    def _record_intraday(self, quotes: Dict[str, Quote]) -> None:
        """记录分钟级轨迹（现价/累计量额）及全日高低出现时刻"""
        ts = now_cst()
        for code, q in quotes.items():
            dq = self._intraday.setdefault(code, deque(maxlen=INTRAY_MAX_TICKS))
            dq.append((ts, q.last, q.volume, q.turnover))
            ext = self._extreme_ts.get(code)
            if ext is None:
                self._extreme_ts[code] = {
                    "high": q.high, "low": q.low,
                    "high_ts": ts, "low_ts": ts,
                }
            else:
                if q.high > ext["high"]:
                    ext["high"] = q.high
                    ext["high_ts"] = ts
                if q.low < ext["low"]:
                    ext["low"] = q.low
                    ext["low_ts"] = ts

    def intraday_summary(self) -> Dict[str, dict]:
        """
        生成日内轨迹摘要（供决策 Prompt 注入）。
        """
        result = {}
        now = now_cst()
        for code, dq in self._intraday.items():
            if not dq:
                continue
            all_points = list(dq)
            window = all_points[-30:]  # 最近30个Tick
            prices = [p for _, p, _, _ in window]
            entry = {
                "recent_high": max(prices),
                "recent_low": min(prices),
                "tick_count": len(dq),
            }
            if len(window) >= 2 and window[0][1] > 0:
                entry["trend_30m"] = (prices[-1] - prices[0]) / prices[0] * 100
            else:
                entry["trend_30m"] = Decimal(0)
            w10 = all_points[-10:]
            if len(w10) >= 2 and w10[0][1] > 0:
                entry["trend_10m"] = (w10[-1][1] - w10[0][1]) / w10[0][1] * 100
            p10 = [p for _, p, _, _ in w10]
            label = path_10m_label(p10)
            if label:
                entry["path_10m"] = label
            if len(all_points) >= 2 and all_points[0][1] > 0:
                entry["trend_open"] = (all_points[-1][1] - all_points[0][1]) / all_points[0][1] * 100
            if len(all_points) >= 2:
                dv = all_points[-1][2] - all_points[-2][2]
                if dv < 0:
                    dv = 0
                entry["vol_1m"] = dv
            ext = self._extreme_ts.get(code)
            if ext:
                entry["high_at"] = ext["high_ts"]
                entry["low_at"] = ext["low_ts"]
                entry["high_ago_min"] = int((now - ext["high_ts"]).total_seconds() // 60)
                entry["low_ago_min"] = int((now - ext["low_ts"]).total_seconds() // 60)
            result[code] = entry
        return result

    @staticmethod
    def _tencent_symbol(code: str) -> str:
        """6位代码 → 腾讯接口符号（sh/sz/bj 前缀）"""
        if code.startswith(("6", "9", "5")):
            return f"sh{code}"
        if code.startswith(("4", "8")):
            return f"bj{code}"
        return f"sz{code}"

    def _fetch_tencent(self) -> Dict[str, Quote]:
        """腾讯行情批量拉取（轻量、单次 HTTP 请求）

        响应格式: v_sh600584="1~长电科技~600584~现价~昨收~今开~..."
        字段索引: 1=名称 3=现价 4=昨收 5=今开 30=时间 33=最高 34=最低
                 36=成交量(手) 37=成交额(万) 47=涨停价 48=跌停价
        """
        if not self._watchlist:
            return {}

        symbols = ",".join(self._tencent_symbol(c) for c in self._watchlist)
        resp = requests.get(
            f"https://qt.gtimg.cn/q={symbols}",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        resp.encoding = "gbk"

        quotes = {}
        for line in resp.text.strip().split(";"):
            line = line.strip()
            if "=" not in line:
                continue
            try:
                payload = line.split("=", 1)[1].strip().strip('"')
                f = payload.split("~")
                if len(f) < 49 or not f[3]:
                    continue
                code = f[2]
                if code not in self._watchlist:
                    continue
                last = Decimal(f[3])
                pre_close = Decimal(f[4]) if f[4] else Decimal(0)
                volume_hand = int(float(f[36])) if f[36] else 0  # 手
                turnover_wan = Decimal(f[37]) if f[37] else Decimal(0)  # 万元
                bid1 = _dec_field(f[9] if len(f) > 9 else "", last)
                ask1 = _dec_field(f[19] if len(f) > 19 else "", last)
                bid1_vol = int(float(f[10])) if len(f) > 10 and f[10] else None
                ask1_vol = int(float(f[20])) if len(f) > 20 and f[20] else None

                quotes[code] = Quote(
                    code=code, name=f[1],
                    last=last,
                    bid1=bid1, ask1=ask1,
                    bid1_volume=bid1_vol, ask1_volume=ask1_vol,
                    high=Decimal(f[33]) if f[33] else last,
                    low=Decimal(f[34]) if f[34] else last,
                    open=Decimal(f[5]) if f[5] else last,
                    pre_close=pre_close,
                    limit_up=Decimal(f[47]) if f[47] else last,
                    limit_down=Decimal(f[48]) if f[48] else last,
                    volume=volume_hand * 100,  # 转为股
                    turnover=turnover_wan * Decimal(10000),  # 转为元
                    vwap=(turnover_wan * Decimal(10000) / Decimal(volume_hand * 100))
                    if volume_hand > 0 else last,
                    is_suspended=not f[3],
                    is_st="ST" in f[1].upper(),
                    timestamp=now_cst(),
                )
            except (ValueError, IndexError) as e:
                logger.warning("tencent_quote_parse_failed", line_preview=line[:80], error=str(e))
                continue
        return quotes

    def _fetch_akshare(self) -> Dict[str, Quote]:
        """akshare 行情拉取（全市场快照一次拉取，按 watchlist 过滤）"""
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            quotes = {}
            for code in self._watchlist:
                try:
                    row = df[df["代码"] == code]
                    if not row.empty:
                        r = row.iloc[0]
                        quotes[code] = Quote(
                            code=code, name=str(r.get("名称", "")),
                            last=Decimal(str(r.get("最新价", 0))),
                            bid1=Decimal(str(r.get("买一") or r.get("最新价", 0))),
                            ask1=Decimal(str(r.get("卖一") or r.get("最新价", 0))),
                            high=Decimal(str(r.get("最高", 0))),
                            low=Decimal(str(r.get("最低", 0))),
                            open=Decimal(str(r.get("今开", 0))),
                            pre_close=Decimal(str(r.get("昨收", 0))),
                            limit_up=Decimal(str(r.get("涨停价", 0))),
                            limit_down=Decimal(str(r.get("跌停价", 0))),
                            volume=int(r.get("成交量", 0)),
                            turnover=Decimal(str(r.get("成交额", 0))),
                            vwap=Decimal(str(r.get("最新价", 0))),
                            is_suspended=False, is_st=False,
                            timestamp=now_cst(),
                        )
                except Exception:
                    continue
            self._latest_quotes = quotes
            return quotes
        except ImportError:
            logger.warning("akshare_not_available")
            return {}
        except Exception as e:
            logger.error("akshare_fetch_failed", error=str(e))
            return {}

    def _fetch_tushare(self) -> Dict[str, Quote]:
        """tushare 实时行情（免费接口 get_realtime_quotes，无需 token）"""
        if not self._watchlist:
            return {}
        try:
            import os
            import tushare as ts

            token = os.getenv(self._config.market.tushare_token_env, "")
            if token:
                ts.set_token(token)

            df = ts.get_realtime_quotes(self._watchlist)
            if df is None or df.empty:
                return {}

            quotes = {}
            for _, r in df.iterrows():
                code = str(r.get("code", ""))
                if code not in self._watchlist:
                    continue
                try:
                    last = Decimal(str(r.get("price", 0)))
                    if last <= 0:
                        continue
                    bid1 = Decimal(str(r.get("b1_p", 0))) or last
                    ask1 = Decimal(str(r.get("a1_p", 0))) or last
                    quotes[code] = Quote(
                        code=code, name=str(r.get("name", "")),
                        last=last,
                        bid1=bid1, ask1=ask1,
                        high=Decimal(str(r.get("high", 0))) or last,
                        low=Decimal(str(r.get("low", 0))) or last,
                        open=Decimal(str(r.get("open", 0))) or last,
                        pre_close=Decimal(str(r.get("pre_close", 0))) or last,
                        limit_up=last, limit_down=last,  # 免费接口无涨跌停价
                        volume=int(float(r.get("volume", 0))),
                        turnover=Decimal(str(r.get("amount", 0))),
                        vwap=(Decimal(str(r.get("amount", 0))) / Decimal(str(r.get("volume", 0))))
                        if float(r.get("volume", 0)) > 0 else last,
                        is_suspended=False, is_st="ST" in str(r.get("name", "")).upper(),
                        timestamp=now_cst(),
                    )
                except Exception:
                    continue
            return quotes
        except ImportError:
            logger.warning("tushare_not_available")
            return {}
        except Exception as e:
            logger.error("tushare_fetch_failed", error=str(e))
            return {}


class FeatureEngine:
    """基础 Feature 预计算"""

    def __init__(self, config: AppConfig, fee_calc: FeeCalculator):
        self._config = config
        self._fee_calc = fee_calc

    def compute(self, quote: Quote) -> FeatureSnapshot:
        """从 Quote 计算基础 Feature"""
        pre_close = quote.pre_close
        last = quote.last

        open_chg = float((quote.open - pre_close) / pre_close) if pre_close > 0 else 0.0
        chg_1d = float((last - pre_close) / pre_close) if pre_close > 0 else 0.0
        amplitude = float((quote.high - quote.low) / pre_close) if pre_close > 0 else 0.0

        # 往返费用估算
        est_price = quote.ask1 or quote.bid1 or last
        round_trip = self._fee_calc.round_trip_fee_est(est_price, self._config.feature.round_trip_est_shares)

        return FeatureSnapshot(
            code=quote.code,
            pre_close=pre_close,
            open=quote.open,
            high=quote.high,
            low=quote.low,
            last=last,
            open_chg_pct=open_chg,
            chg_pct_1d=chg_1d,
            chg_pct_5d=None,  # 需要历史数据
            chg_pct_10d=None,
            vwap=quote.vwap,
            amplitude=amplitude,
            volume=quote.volume,
            volume_ratio=None,  # 需要历史数据
            turnover_rate=None,
            round_trip_fee_est=round_trip,
        )
