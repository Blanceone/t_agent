"""
Market Understanding（市场理解）

每日 09:20 日切后触发，产出：
- Market Regime（四态：TREND/RANGE/HIGH_VOL/LOW_VOL）
- Risk Level / Trading Suggestion / Strategy Preference
- 今日市场摘要

规则：代码规则优先生成候选 Regime，LLM 可确认或微调。
降级：RANGE + MEDIUM + CONSERVATIVE。
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from agent.common.models import MarketRegime, Quote
from agent.common.logger import get_logger
from agent.llm.client import LLMClient

logger = get_logger("market.understanding")


@dataclass
class MarketUnderstandingOutput:
    """市场理解输出"""
    date: str
    today_market_summary: str = ""
    market_regime: MarketRegime = MarketRegime.RANGE
    regime_secondary: List[str] = field(default_factory=list)
    today_risk_level: str = "MEDIUM"  # LOW/MEDIUM/HIGH
    today_trading_suggestion: str = "ACTIVE_T"  # ACTIVE_T/REDUCE_T/DEFENSIVE/NO_NEW_BUY
    today_strategy_preference: str = "BALANCED"  # AGGRESSIVE/BALANCED/CONSERVATIVE
    index_view: Dict[str, dict] = field(default_factory=dict)
    holdings_context: Dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    degraded: bool = False  # 是否降级输出


class RegimeDetector:
    """
    代码规则优先的 Regime 判定器。

    判定逻辑（基于指数 Feature）：
    - HIGH_VOL: 振幅 > 3% 或 量比 > 2.0
    - LOW_VOL: 振幅 < 1% 且 量比 < 0.7
    - TREND: 涨跌幅绝对值 > 1.5% 且 非高波动
    - RANGE: 其余情况
    """

    def __init__(
        self,
        high_vol_amplitude: float = 0.03,
        high_vol_volume_ratio: float = 2.0,
        low_vol_amplitude: float = 0.01,
        low_vol_volume_ratio: float = 0.7,
        trend_chg_threshold: float = 0.015,
    ):
        self._high_vol_amp = high_vol_amplitude
        self._high_vol_vr = high_vol_volume_ratio
        self._low_vol_amp = low_vol_amplitude
        self._low_vol_vr = low_vol_volume_ratio
        self._trend_chg = trend_chg_threshold

    def detect(
        self,
        index_chg_pct: float = 0.0,
        index_amplitude: float = 0.0,
        index_volume_ratio: float = 1.0,
    ) -> MarketRegime:
        """
        基于指数 Feature 判定 Regime。

        Args:
            index_chg_pct: 指数涨跌幅（如 0.015 = 1.5%）
            index_amplitude: 指数振幅（如 0.025 = 2.5%）
            index_volume_ratio: 量比（相对近期均量）
        """
        # HIGH_VOL 优先
        if index_amplitude > self._high_vol_amp or index_volume_ratio > self._high_vol_vr:
            return MarketRegime.HIGH_VOL

        # LOW_VOL
        if index_amplitude < self._low_vol_amp and index_volume_ratio < self._low_vol_vr:
            return MarketRegime.LOW_VOL

        # TREND
        if abs(index_chg_pct) > self._trend_chg:
            return MarketRegime.TREND

        # 默认 RANGE
        return MarketRegime.RANGE


class MarketUnderstandingEngine:
    """市场理解引擎"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._llm = llm_client
        self._regime_detector = RegimeDetector()

    def run(
        self,
        date: str,
        quotes: Dict[str, Quote],
        watchlist: List[str],
        yesterday_summary: str = "",
        market_service=None,
    ) -> MarketUnderstandingOutput:
        """
        执行每日市场理解。

        流程：
        1. 代码汇总指数/持仓 Feature → Regime 候选
        2. LLM 确认/微调（可选）
        3. 失败则降级
        """
        # Step 1: 代码规则判定（优先真实大盘指数，回退自选股平均）
        index_chg, index_amp, index_vr = self._compute_index_features(
            quotes, watchlist, market_service
        )
        code_regime = self._regime_detector.detect(index_chg, index_amp, index_vr)

        # 构建基础输出
        output = MarketUnderstandingOutput(
            date=date,
            market_regime=code_regime,
            confidence=0.7,
        )

        # 根据 Regime 设置默认约束
        self._apply_regime_defaults(output)

        # Step 2: LLM 增强（可选）
        if self._llm:
            try:
                llm_result = self._llm_enhance(output, quotes, watchlist,
                                               yesterday_summary, market_service)
                if llm_result:
                    output = llm_result
            except Exception as e:
                logger.warning("mu_llm_failed", error=str(e))
                output.degraded = True

        # 摘要只用指数事实，不用 LLM 的操作建议（8/27「建议减少做T」会锁死分钟决策）
        output.today_market_summary = self._generate_summary(
            output, index_chg, index_amp, index_vr)

        logger.info(
            "market_understanding_done",
            date=date,
            regime=output.market_regime.value,
            risk_level=output.today_risk_level,
            degraded=output.degraded,
        )
        return output

    def _compute_index_features(
        self, quotes: Dict[str, Quote], watchlist: List[str], market_service=None
    ) -> tuple:
        """计算市场特征：优先真实大盘指数（上证），回退自选股平均"""
        # 量比：优先「今日累计成交/近5日均量」，否则用日K快照
        volume_ratio = 1.0
        if market_service is not None:
            try:
                vrs = []
                tech = market_service.kline_tech()
                for code, t in tech.items():
                    avg = t.get("avg_volume_5d")
                    q = quotes.get(code) if quotes else None
                    if avg and avg > 0 and q and q.volume > 0:
                        vrs.append(q.volume / avg)
                    elif t.get("volume_ratio"):
                        vrs.append(t["volume_ratio"])
                if vrs:
                    volume_ratio = sum(vrs) / len(vrs)
            except Exception:
                pass

        # 优先真实指数
        idx = market_service.get_index_quote() if market_service else None
        if idx is not None and idx.pre_close > 0:
            chg = float((idx.last - idx.pre_close) / idx.pre_close)
            amp = float((idx.high - idx.low) / idx.pre_close) if idx.high > idx.low \
                else abs(chg)
            return chg, amp, volume_ratio

        # 回退：自选股平均
        if not quotes:
            return 0.0, 0.0, volume_ratio

        chg_list = []
        amp_list = []
        for code in watchlist:
            q = quotes.get(code)
            if q and q.pre_close > 0:
                chg = float((q.last - q.pre_close) / q.pre_close)
                amp = float((q.high - q.low) / q.pre_close)
                chg_list.append(chg)
                amp_list.append(amp)

        if not chg_list:
            return 0.0, 0.0, volume_ratio

        return sum(chg_list) / len(chg_list), sum(amp_list) / len(amp_list), volume_ratio

    def _apply_regime_defaults(self, output: MarketUnderstandingOutput):
        """根据 Regime 设置默认风险/策略约束"""
        regime = output.market_regime

        if regime == MarketRegime.HIGH_VOL:
            output.today_risk_level = "HIGH"
            output.today_trading_suggestion = "REDUCE_T"
            output.today_strategy_preference = "CONSERVATIVE"
        elif regime == MarketRegime.LOW_VOL:
            output.today_risk_level = "LOW"
            output.today_trading_suggestion = "REDUCE_T"
            output.today_strategy_preference = "CONSERVATIVE"
        elif regime == MarketRegime.TREND:
            output.today_risk_level = "MEDIUM"
            output.today_trading_suggestion = "ACTIVE_T"
            output.today_strategy_preference = "AGGRESSIVE"
        else:  # RANGE
            output.today_risk_level = "MEDIUM"
            output.today_trading_suggestion = "ACTIVE_T"
            output.today_strategy_preference = "BALANCED"

    def _llm_enhance(
        self,
        base: MarketUnderstandingOutput,
        quotes: Dict[str, Quote],
        watchlist: List[str],
        yesterday_summary: str,
        market_service=None,
    ) -> Optional[MarketUnderstandingOutput]:
        """LLM 确认/微调 Regime"""
        holdings_info = []
        for code in watchlist:
            q = quotes.get(code)
            if q and q.pre_close > 0:
                chg = float((q.last - q.pre_close) / q.pre_close) * 100
                holdings_info.append(f"- {code}: 涨跌{chg:.2f}%")

        # 大盘指数环境
        index_text = "无"
        idx = market_service.get_index_quote() if market_service else None
        if idx is not None and idx.pre_close > 0:
            chg = float((idx.last - idx.pre_close) / idx.pre_close) * 100
            index_text = f"{idx.name} 现价{idx.last} 涨跌{chg:+.2f}%"

        prompt = f"""你是A股市场分析师。根据以下数据判断今日市场状态。

## 市场数据
- 代码判定 Regime: {base.market_regime.value}
- 大盘指数: {index_text}
- 股票池涨跌:
{chr(10).join(holdings_info) if holdings_info else "无数据"}
- 昨日复盘: {yesterday_summary[:200] if yesterday_summary else "无"}

## Regime 选项
- TREND: 趋势市（单边上涨或下跌）
- RANGE: 震荡市（区间波动）
- HIGH_VOL: 高波动（剧烈震荡、放量）
- LOW_VOL: 低波动（缩量横盘）

## 说明
today_market_summary 只写事实（涨跌、振幅、量能），不要写操作建议（减少做T、控制仓位、等待方向、不宜买入等）。摘要字段仍会被代码用指数数据覆盖。

## 输出（严格JSON）
```json
{{
  "market_regime": "TREND|RANGE|HIGH_VOL|LOW_VOL",
  "today_risk_level": "LOW|MEDIUM|HIGH",
  "today_trading_suggestion": "ACTIVE_T|REDUCE_T|DEFENSIVE|NO_NEW_BUY",
  "today_strategy_preference": "AGGRESSIVE|BALANCED|CONSERVATIVE",
  "today_market_summary": "一句话事实，不要写操作建议",
  "confidence": 0.8
}}
```"""

        raw = self._llm.call_json(prompt, timeout_ms=30000)
        if not raw:
            return None

        # 校验 Regime 合法性
        regime_str = str(raw.get("market_regime", "")).upper()
        try:
            regime = MarketRegime(regime_str)
        except ValueError:
            logger.warning("mu_invalid_regime", raw_regime=regime_str)
            return None  # 非法则回退代码结果

        output = MarketUnderstandingOutput(
            date=base.date,
            today_market_summary=str(raw.get("today_market_summary", "")),
            market_regime=regime,
            today_risk_level=str(raw.get("today_risk_level", "MEDIUM")).upper(),
            today_trading_suggestion=str(raw.get("today_trading_suggestion", "ACTIVE_T")).upper(),
            today_strategy_preference=str(raw.get("today_strategy_preference", "BALANCED")).upper(),
            confidence=float(raw.get("confidence", 0.8)),
            degraded=False,
        )

        # 校验枚举合法性
        if output.today_risk_level not in ("LOW", "MEDIUM", "HIGH"):
            output.today_risk_level = "MEDIUM"
        if output.today_trading_suggestion not in ("ACTIVE_T", "REDUCE_T", "DEFENSIVE", "NO_NEW_BUY"):
            output.today_trading_suggestion = "ACTIVE_T"
        if output.today_strategy_preference not in ("AGGRESSIVE", "BALANCED", "CONSERVATIVE"):
            output.today_strategy_preference = "BALANCED"

        return output

    def _generate_summary(
        self, output: MarketUnderstandingOutput, chg: float, amp: float, vr: float = 1.0
    ) -> str:
        """生成简要摘要（仅数据，不含操作建议）"""
        regime_desc = {
            MarketRegime.TREND: "趋势市",
            MarketRegime.RANGE: "震荡市",
            MarketRegime.HIGH_VOL: "高波动",
            MarketRegime.LOW_VOL: "低波动",
        }
        return (
            f"{regime_desc.get(output.market_regime, '震荡市')}，"
            f"指数涨跌{chg * 100:+.2f}%，振幅{amp * 100:.1f}%，量比{vr:.2f}"
        )
