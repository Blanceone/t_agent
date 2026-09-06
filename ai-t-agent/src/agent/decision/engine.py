"""
Decision 引擎（LLM 调用 + Schema 校验）

在连续竞价有效时段，结合 Context 调用 LLM 输出交易意图。
所有输出必须经 Risk Engine 校验。
"""

import json
from collections import deque
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from agent.common.models import (
    AccountSnapshot,
    ActionType,
    DecisionItem,
    DecisionOutput,
    Quote,
    RiskState,
)
from agent.common.logger import get_logger
from agent.common.utils import now_cst
from agent.llm.client import LLMClient, SingleFlightGuard
from agent.config.schema import AppConfig
from agent.decision.validator import DecisionValidator
from agent.trading.fee import FeeCalculator

logger = get_logger("decision.engine")


def _pct_yuan(last: Decimal, ref, label: str) -> Optional[str]:
    """现价相对参考位的 ±% 与元差。"""
    if ref is None or last is None or last <= 0:
        return None
    ref = Decimal(str(ref))
    if ref <= 0:
        return None
    return f"较{label}{(last - ref) / ref * 100:+.1f}%（{last - ref:+.2f}元）"


def _buy_unavailable_reason(cash_shares: int, cap_shares: int) -> str:
    """可买不足 1 手时的账户事实（不把现金与仓位上限捆成一句）。"""
    cash_ok = cash_shares >= 100
    cap_ok = cap_shares >= 100
    if not cap_ok and not cash_ok:
        return "购买力不足且单票上限剩余不足100股，禁止发出BUY"
    if not cap_ok:
        return "单票上限剩余不足100股，禁止加仓BUY"
    if not cash_ok:
        return "购买力不足（现金扣除预留后），禁止发出BUY"
    return "可买不足100股，禁止发出BUY"


def _minutes_until(now, hhmm: str) -> int:
    """now 距离当天 hh:mm 的整分钟数（可负）。"""
    hour, minute = [int(x) for x in hhmm.split(":", 1)]
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    rounded = now.replace(second=0, microsecond=0)
    return int((target - rounded).total_seconds() // 60)


def _hm_minutes(hhmm: str) -> int:
    hour, minute = [int(x) for x in hhmm.split(":", 1)]
    return hour * 60 + minute


def _intraday_lot_note(sold: int, bought: int) -> str:
    """今日买卖手数事实。未接回只在已卖>已买时为正数，不打印 0 或负数。"""
    if not sold and not bought:
        return ""
    if sold > bought:
        return f", 今日已卖{sold}股/已买{bought}股/未接回{sold - bought}股"
    if sold > 0:
        extra = f"，净买入{bought - sold}股" if bought > sold else ""
        return f", 今日已卖{sold}股/已买{bought}股，接回已闭环{extra}"
    return f", 今日已买{bought}股（今日无卖出，不是接回）"


def _session_elapsed_minutes(now, am_start: str, am_end: str, pm_start: str) -> int:
    """连续竞价已过的交易分钟（午休不计入）。开盘前为 0。"""
    now_m = now.hour * 60 + now.minute
    am_s = _hm_minutes(am_start)
    am_e = _hm_minutes(am_end)
    pm_s = _hm_minutes(pm_start)
    am_len = am_e - am_s
    if now_m < am_s:
        return 0
    if now_m <= am_e:
        return now_m - am_s
    if now_m < pm_s:
        return am_len
    return am_len + (now_m - pm_s)


class DecisionEngine:
    """分钟级 LLM 决策引擎"""

    def __init__(self, config: AppConfig, llm_client: LLMClient):
        self._config = config
        self._llm = llm_client
        self._single_flight = SingleFlightGuard()
        self._prompt_version = config.prompt.decision_version
        self._validator = DecisionValidator()
        self._fee_calc = FeeCalculator(config.fee)
        # 日级上下文：股票池 + Today Plan（由 Scheduler 日切时注入）
        self._watchlist: List[str] = []
        self._today_plan = None
        self._market_service = None
        self._trading_engine = None
        self._memory_retriever = None
        self._regime: str = ""
        self._market_summary: str = ""
        self._yesterday_summary: str = ""
        # 反馈闭环：最近被风控拒绝的决策（跨分钟记忆）
        self._recent_feedback: deque = deque(maxlen=6)
        # 可观测性：最近一次的 Prompt 与 LLM 原始响应（供 Replay 落盘）
        self._last_prompt: str = ""
        self._last_raw: Optional[dict] = None

    def set_daily_context(self, watchlist: List[str], today_plan, market_service=None,
                          trading_engine=None, memory_retriever=None,
                          regime: str = "", market_summary: str = "",
                          yesterday_summary: str = "") -> None:
        """日切时注入日级上下文（股票池/计划/行情服务/交易引擎/记忆/市场状态/昨日复盘）"""
        self._watchlist = watchlist or []
        self._today_plan = today_plan
        self._market_service = market_service
        self._trading_engine = trading_engine
        self._memory_retriever = memory_retriever
        self._regime = regime
        self._market_summary = market_summary
        self._yesterday_summary = yesterday_summary
        if not watchlist:
            self._recent_feedback.clear()

    def record_feedback(self, feedback: str) -> None:
        """记录风控拒绝反馈（由 TickExecutor 在拒单时调用），供后续 Prompt 注入"""
        ts = now_cst().strftime("%H:%M")
        self._recent_feedback.append(f"[{ts}] {feedback}")


    def t_status(self, code: str) -> str:
        """open | buyback_only | hold_only"""
        plan = None
        today = self._today_plan
        if today is not None:
            for p in getattr(today, "plans", None) or []:
                if getattr(p, "code", None) == code:
                    plan = p
                    break
        fills = 0
        sell_n = 0
        buy_sh = 0
        sell_sh = 0
        trading = self._trading_engine
        if trading is not None:
            for f in getattr(trading, "today_fills", []) or []:
                if getattr(f, "code", None) != code:
                    continue
                fills += 1
                action = getattr(f, "action", None)
                shares = int(getattr(f, "shares", 0) or 0)
                if action == ActionType.BUY:
                    buy_sh += shares
                elif action == ActionType.SELL:
                    sell_sh += shares
                    sell_n += 1
        used = self._t_budget_used(plan, code, {code: fills}, {code: sell_n})
        cap = int(
            getattr(plan, "max_trades_hint", None)
            or getattr(plan, "max_trades_hint", 0)
            or 0
        )
        if cap <= 0 or used < cap:
            return "open"
        if sell_sh - buy_sh > 0:
            return "buyback_only"
        return "hold_only"

    def decide(
        self,
        snapshot: AccountSnapshot,
        quotes: Dict[str, Quote],
        risk_state: RiskState,
        tick_id: str,
    ) -> Optional[DecisionOutput]:
        """
        主决策流程。

        1. 单飞行检查
        2. 构建 Prompt
        3. 调用 LLM
        4. Schema 校验
        5. 失败重试 1 次
        6. 仍失败 → None（本分钟 HOLD）
        """
        if not self._single_flight.try_acquire():
            logger.info("decision_skipped_single_flight", tick_id=tick_id)
            return None

        try:
            prompt = self._build_prompt(snapshot, quotes, risk_state)
            self._last_prompt = prompt
            raw = self._llm.call_json(prompt, self._config.llm.timeout_ms)
            self._last_raw = raw

            if raw is None:
                # 内容安全拦截时不重试（重试大概率仍被拦截，徒增耗时）
                if getattr(self._llm, "last_error", None) != "content_filter":
                    raw = self._llm.call_json(prompt, self._config.llm.timeout_ms)

            if raw is None:
                logger.warning("decision_llm_failed", tick_id=tick_id)
                return None

            decision = self._validator.validate(
                raw,
                prompt_version=self._prompt_version,
                context_id=f"ctx_{tick_id}",
            )
            if decision:
                self._audit_log(decision, tick_id)
            return decision

        except Exception as e:
            logger.error("decision_error", error=str(e), tick_id=tick_id)
            return None
        finally:
            self._single_flight.release()

    @staticmethod
    def _t_budget_used(plan, code: str, fills_by_code: Dict[str, int],
                       sell_fills_by_code: Dict[str, int]) -> int:
        """做T预算消耗。先卖后买：次数=卖出笔数（接回买入不计入）；其它策略按全部成交笔数。"""
        if plan is not None and getattr(plan, "t_strategy", "") == "SELL_FIRST_THEN_BUY_BACK":
            return sell_fills_by_code.get(code, 0)
        return fills_by_code.get(code, 0)

    def _audit_log(self, decision: DecisionOutput, tick_id: str) -> None:
        """决策审计日志：落盘每分钟的 LLM 决策内容与思路（诊断用）"""
        try:
            path = Path("data/logs/decisions.jsonl")
            path.parent.mkdir(parents=True, exist_ok=True)
            rec = {
                "timestamp": now_cst().isoformat(),
                "tick_id": tick_id,
                "thought": decision.thought_process[:200],
                "decisions": [
                    {"action": d.action.value, "code": d.code, "shares": d.shares,
                     "confidence": d.confidence, "reason": d.reason[:120]}
                    for d in decision.decisions
                ],
            }
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _build_prompt(self, snapshot: AccountSnapshot, quotes: Dict[str, Quote],
                      risk_state: RiskState) -> str:
        """构建 Decision Prompt"""
        # 风控状态中性化展示（降低触发内容安全审查的概率）
        state_display = {
            "NORMAL": "正常",
            "HALT": "限制交易（只能卖出）",
            "LIQUIDATE": "紧急状态（禁止一切操作）",
        }.get(risk_state.value, risk_state.value)

        # 今日成交流水与费用（来自 TradingEngine）
        today_fills = []
        fees_today = Decimal("0")
        fills_by_code: Dict[str, int] = {}
        sell_fills_by_code: Dict[str, int] = {}  # 卖出笔数 = 先卖后买策略下的做T次数
        buys_by_code: Dict[str, int] = {}   # 今日买入股数（用于未完成做T检测）
        sells_by_code: Dict[str, int] = {}  # 今日卖出股数
        sell_notional: Dict[str, Decimal] = {}  # 今日卖出金额，用于卖出均价
        if self._trading_engine is not None:
            for f in getattr(self._trading_engine, "today_fills", []):
                today_fills.append(
                    f"- {f.timestamp.strftime('%H:%M')} {f.action.value} {f.code} "
                    f"{f.shares}股 @{f.price} 费用{f.fee}"
                )
                fees_today += f.fee
                fills_by_code[f.code] = fills_by_code.get(f.code, 0) + 1
                if f.action == ActionType.BUY:
                    buys_by_code[f.code] = buys_by_code.get(f.code, 0) + f.shares
                elif f.action == ActionType.SELL:
                    sells_by_code[f.code] = sells_by_code.get(f.code, 0) + f.shares
                    sell_fills_by_code[f.code] = sell_fills_by_code.get(f.code, 0) + 1
                    sell_notional[f.code] = (
                        sell_notional.get(f.code, Decimal("0")) + f.price * f.shares
                    )
        sell_avg_by_code: Dict[str, Decimal] = {}
        for code, qty in sells_by_code.items():
            if qty > 0:
                sell_avg_by_code[code] = sell_notional[code] / qty

        # 回撤状态
        drawdown_text = "无"
        if snapshot.peak_nav > 0:
            dd_peak = (snapshot.peak_nav - snapshot.nav_mark) / snapshot.peak_nav * 100
            dd_day = ((snapshot.nav_mark - snapshot.last_nav) / snapshot.last_nav * 100
                      if snapshot.last_nav > 0 else Decimal(0))
            drawdown_text = f"距峰值回撤{dd_peak:.2f}%, 较昨收{dd_day:+.2f}%"

        # 市场环境（Regime + 大盘指数 + 昨日复盘）
        env_lines = []
        if self._regime:
            env_lines.append(f"- 市场状态: {self._regime}  摘要: {self._market_summary or '无'}")
        if self._market_service is not None:
            try:
                idx = self._market_service.get_index_quote()
                if idx is not None and idx.pre_close > 0:
                    chg = (idx.last - idx.pre_close) / idx.pre_close * 100
                    env_lines.append(f"- 上证指数: {idx.last} ({chg:+.2f}%)")
            except Exception:
                pass
        if self._yesterday_summary:
            env_lines.append(f"- 昨日复盘: {self._yesterday_summary[:120]}")
        env_text = chr(10).join(env_lines) if env_lines else "无"

        # 计划索引（持仓区块也需要目标仓位比例，提前构建）
        plan_by_code = {}
        if self._today_plan and getattr(self._today_plan, "plans", None):
            plan_by_code = {p.code: p for p in self._today_plan.plans}

        holdings_info = []
        for code, pos in snapshot.positions.items():
            q = quotes.get(code)
            if q:
                # 可卖为0时明确禁令，避免 LLM 反复提交 T+1 锁定股的卖单
                sell_note = "（今日买入T+1锁定，禁止发出SELL）" if pos.sellable_shares <= 0 else ""
                # 距风控线空间
                stop_gap = ((q.last - pos.stop_loss_price) / pos.stop_loss_price * 100
                            if pos.stop_loss_price > 0 else Decimal(0))
                # 预计算：浮动盈亏与仓位比例（客观数值，免去模型乘除心算）
                pnl = (q.last - pos.cost_price) * pos.total_shares
                pnl_pct = ((q.last / pos.cost_price - 1) * 100
                           if pos.cost_price > 0 else Decimal(0))
                pos_ratio = (pos.total_shares * q.last / snapshot.nav_mark * 100
                             if snapshot.nav_mark > 0 else Decimal(0))
                target_note = ""
                _pp = plan_by_code.get(code)
                if _pp is not None:
                    target_note = f"（目标{_pp.target_position_ratio * 100:.1f}%）"
                sold = sells_by_code.get(code, 0)
                bought = buys_by_code.get(code, 0)
                lot_note = _intraday_lot_note(sold, bought)
                holdings_info.append(
                    f"- {code}: 持仓{pos.total_shares}股, 可卖{pos.sellable_shares}股{sell_note}, "
                    f"成本{pos.cost_price}, 现价{q.last}, "
                    f"浮动盈亏{pnl:+.2f}元({pnl_pct:+.2f}%), "
                    f"仓位比例{pos_ratio:.1f}%{target_note}{lot_note}, "
                    f"风控线{pos.stop_loss_price}(现价距风控线{stop_gap:+.2f}%)"
                )

        # 清仓后持仓区仍要写未接回，否则模型会把接回当成建仓（8/28 10:10）
        for code in self._watchlist:
            if code in snapshot.positions:
                continue
            sold = sells_by_code.get(code, 0)
            bought = buys_by_code.get(code, 0)
            pending = sold - bought
            if pending <= 0:
                continue
            q = quotes.get(code)
            extra = ""
            avg = sell_avg_by_code.get(code)
            if avg is not None and q is not None:
                extra = (
                    f", 今日卖出均价{avg:.2f}, 现价{q.last}"
                    f"（较卖出均价{q.last - avg:+.2f}元）"
                )
            holdings_info.append(
                f"- {code}: 持仓0股, 可卖0股（今日卖出未接回，禁止发出SELL）"
                f"{_intraday_lot_note(sold, bought)}{extra}"
            )

        # 购买力计算（与 Risk Engine 现金预留/单票上限规则一致）
        reserved_ratio = self._config.risk.reserved_min_cash_ratio
        max_pos_ratio = self._config.risk.max_single_position_ratio
        buy_power = snapshot.cash_available - snapshot.nav_mark * reserved_ratio - Decimal("5")

        # 日K技术位缓存
        kline_tech = {}
        intraday_data: Dict[str, dict] = {}
        if self._market_service is not None:
            try:
                kline_tech = self._market_service.kline_tech()
            except Exception:
                pass
            try:
                intraday_data = self._market_service.intraday_summary()
            except Exception:
                pass

        # 股票池行情（含未持仓标的 + 可买上限 + 涨跌停空间 + 技术位）
        watchlist_info = []
        hard_constraints = []  # 动态硬约束，置顶注入 Prompt
        max_buyable_by_code: Dict[str, int] = {}
        for code in self._watchlist:
            q = quotes.get(code)
            if not q:
                continue
            held = code in snapshot.positions
            chg = f"{(q.last - q.pre_close) / q.pre_close * 100:.2f}%" if q.pre_close > 0 else "0%"

            # 可买上限 = min(现金约束, 单票仓位上限)，向下取整到 100 股
            price = q.ask1 or q.last
            cash_limit = 0
            cap_limit = 0
            max_buyable = 0
            if price > 0:
                cash_limit = int(buy_power / price) if buy_power > 0 else 0
                current_shares = snapshot.positions[code].total_shares if held else 0
                cap_limit = int((snapshot.nav_mark * max_pos_ratio) / price) - current_shares
                max_buyable = max(0, min(cash_limit, cap_limit)) // 100 * 100
            max_buyable_by_code[code] = max_buyable

            pos = snapshot.positions.get(code)
            p = plan_by_code.get(code)
            t_used = self._t_budget_used(p, code, fills_by_code, sell_fills_by_code)
            pending_buyback = sells_by_code.get(code, 0) - buys_by_code.get(code, 0)
            budget_done = bool(p and t_used >= p.max_trades_hint)
            hold_only = budget_done and pending_buyback <= 0
            buyback_only = budget_done and pending_buyback > 0
            risk_halt = risk_state.value == "HALT"
            risk_liq = risk_state.value == "LIQUIDATE"

            # 行情行买卖提示须与硬约束同一套事实
            if risk_liq or hold_only:
                buy_hint = "禁止发出BUY（今日该标的只可HOLD）"
            elif risk_halt:
                buy_hint = "禁止发出BUY（风控限制交易）"
            elif buyback_only:
                buy_hint = f"仅允许接回BUY（尚有{pending_buyback}股未接回）"
            elif pending_buyback > 0 and not held and max_buyable > 0:
                buy_hint = (
                    f"最多可买{max_buyable}股（今日未接回{pending_buyback}股，买入是接回不是建仓）"
                )
            elif max_buyable > 0:
                buy_hint = f"最多可买{max_buyable}股（超过此数量发出BUY将被拒绝）"
            else:
                buy_hint = _buy_unavailable_reason(cash_limit, cap_limit)
            if not held:
                if pending_buyback > 0:
                    sell_hint = ", 禁止发出SELL（持仓0股，今日未接回中）"
                else:
                    sell_hint = ", 禁止发出SELL（无持仓，无股可卖）"
            elif pos.sellable_shares <= 0:
                sell_hint = ", 禁止发出SELL（T+1锁定）"
            elif hold_only:
                sell_hint = ", 禁止发出SELL（今日该标的只可HOLD）"
            else:
                sell_hint = ""

            # 硬约束：卖/买/HOLD 互斥，不叠互相打架的通行证
            if not held:
                if pending_buyback > 0:
                    hard_constraints.append(
                        f"{code} 持仓0股（今日卖出未接回），无股可卖，禁止发出SELL"
                    )
                    hard_constraints.append(
                        f"{code} 今日已卖{sells_by_code.get(code, 0)}股、"
                        f"未接回{pending_buyback}股：买入是接回该笔做T，不是建仓；"
                        f"计划中的卖出步骤不可执行（无股可卖）；"
                        f"是否接回由你根据数据判断，不强制当日"
                    )
                else:
                    hard_constraints.append(f"{code} 无持仓，无股可卖，禁止发出SELL")
                    if p and p.t_strategy == "SELL_FIRST_THEN_BUY_BACK":
                        hard_constraints.append(
                            f"{code} 无持仓：计划中的卖出步骤不可执行（无股可卖），"
                            f"仅可执行计划中的买入建仓部分，或不满足买入条件时观望")
            elif pos.sellable_shares <= 0:
                hard_constraints.append(
                    f"{code} 持仓{pos.total_shares}股但可卖为0（T+1锁定）："
                    f"计划中的卖出步骤不可执行（无股可卖），禁止发出SELL")

            if risk_liq or risk_halt:
                pass
            elif hold_only:
                hard_constraints.append(
                    f"{code} 今日做T已完成{t_used}次，达到上限{p.max_trades_hint}次，"
                    f"停止交易只可HOLD")
            elif buyback_only:
                hard_constraints.append(
                    f"{code} 今日做T预算已用完，但尚有{pending_buyback}股卖出未接回："
                    f"仅允许接回BUY完成本次做T（不强制今日接回），"
                    f"禁止发出SELL和新建仓BUY")
            elif max_buyable <= 0:
                hard_constraints.append(
                    f"{code} {_buy_unavailable_reason(cash_limit, cap_limit)}")
            else:
                hard_constraints.append(f"{code} 最多可买{max_buyable}股，超过将被拒绝")
            vol_wan_hand = q.volume / 100 / 10000  # 万手
            amt = f"{q.turnover / Decimal('100000000'):.2f}亿" if q.turnover >= Decimal("100000000") \
                else f"{q.turnover / Decimal('10000'):.0f}万"

            # 涨跌停空间
            limit_note = ""
            if q.limit_up > q.last > 0:
                up_gap = (q.limit_up - q.last) / q.last * 100
                dn_gap = (q.last - q.limit_down) / q.last * 100 if q.limit_down > 0 else Decimal(0)
                limit_note = f", 距涨停{up_gap:.1f}%/距跌停{dn_gap:.1f}%"

            # 日K技术位
            tech_note = ""
            t = kline_tech.get(code)
            if t:
                parts = [f"MA5 {t['ma5']:.2f}"]
                if t.get("ma20"):
                    parts.append(f"MA20 {t['ma20']:.2f}")
                if t.get("support"):
                    parts.append(f"支撑{t['support']:.2f}")
                if t.get("resistance"):
                    parts.append(f"压力{t['resistance']:.2f}")
                tech_note = ", 技术位: " + "/".join(parts)

            # 预计算数据（客观数值，免去模型心算比较）
            calc_parts = []
            if t and q.last > 0:
                for label, key in (("MA5", "ma5"), ("MA20", "ma20"),
                                   ("支撑", "support"), ("压力", "resistance")):
                    ref = t.get(key)
                    if ref and ref > 0:
                        calc_parts.append(
                            f"较{label}{(q.last - ref) / ref * 100:+.1f}%"
                            f"（{q.last - ref:+.2f}元）")
            if q.vwap and q.vwap > 0:
                vs_vwap = _pct_yuan(q.last, q.vwap, "日内均价")
                if vs_vwap:
                    calc_parts.append(vs_vwap)
            vs_open = _pct_yuan(q.last, q.open, "今开")
            if vs_open:
                calc_parts.append(vs_open)
            if q.open and q.pre_close and q.pre_close > 0:
                calc_parts.append(
                    f"今开较昨收{(q.open - q.pre_close) / q.pre_close * 100:+.1f}%"
                    f"（{q.open - q.pre_close:+.2f}元）")
            if q.pre_close and q.pre_close > 0 and q.high is not None and q.low is not None:
                amp = (q.high - q.low) / q.pre_close * 100
                calc_parts.append(f"振幅{amp:.1f}%")
            vs_high = _pct_yuan(q.last, q.high, "日内最高")
            if vs_high:
                calc_parts.append(vs_high)
            if q.low and q.low > 0:
                calc_parts.append(
                    f"自日内最低回升{(q.last - q.low) / q.low * 100:+.1f}%"
                    f"（{q.last - q.low:+.2f}元）")
            if q.high > q.low:
                rng = (q.last - q.low) / (q.high - q.low) * 100
                calc_parts.append(f"日内区间位置{rng:.0f}%")
            s = intraday_data.get(code)
            if s:
                if "trend_open" in s:
                    calc_parts.append(f"开盘至今{s['trend_open']:+.2f}%")
                if "trend_10m" in s:
                    calc_parts.append(f"近10分钟{s['trend_10m']:+.2f}%")
                if s.get("tick_count", 0) >= 30 and "trend_30m" in s:
                    calc_parts.append(f"近30分钟{s['trend_30m']:+.2f}%")
                if s.get("vol_1m") is not None:
                    calc_parts.append(f"近1分钟成交{s['vol_1m'] / 100 / 10000:.2f}万手")
            avg_vol = (t or {}).get("avg_volume_5d") if t else None
            if avg_vol and avg_vol > 0 and q.volume > 0:
                calc_parts.append(f"量比{q.volume / avg_vol:.2f}")
            avg_sell = sell_avg_by_code.get(code)
            pending_here = sells_by_code.get(code, 0) - buys_by_code.get(code, 0)
            if pending_here > 0 and avg_sell is not None:
                vs_sell = _pct_yuan(q.last, avg_sell, "今日卖出均价")
                if vs_sell:
                    calc_parts.append(vs_sell)
            px = q.ask1 or q.last
            lot = self._config.feature.round_trip_est_shares
            if px and px > 0 and lot > 0:
                fee_rt = self._fee_calc.round_trip_fee_est(px, lot)
                per = fee_rt / Decimal(lot)
                calc_parts.append(
                    f"{lot}股往返费用约{fee_rt:.2f}元（约{per:.2f}元/股打平）")
            calc_note = ", 预计算: " + ", ".join(calc_parts) if calc_parts else ""

            ba_bits = []
            if q.bid1 is not None:
                ba_bits.append(f"买一{q.bid1}")
                if q.bid1_volume:
                    ba_bits.append(f"买一量{q.bid1_volume}手")
            if q.ask1 is not None:
                ba_bits.append(f"卖一{q.ask1}")
                if q.ask1_volume:
                    ba_bits.append(f"卖一量{q.ask1_volume}手")
            if q.bid1 is not None and q.ask1 is not None:
                ba_bits.append(f"价差{q.ask1 - q.bid1:.2f}元")
            ba_note = (", " + ", ".join(ba_bits)) if ba_bits else ""

            flag_note = ""
            if q.is_st:
                flag_note += ", ST"
            if q.is_suspended:
                flag_note += ", 停牌"

            watchlist_info.append(
                f"- {code} {q.name}: {'已持仓' if held else '未持仓'}, 现价{q.last}{ba_note}, "
                f"涨跌{chg}, 今开{q.open}, 最高{q.high}, 最低{q.low}, 昨收{q.pre_close}, "
                f"成交{vol_wan_hand:.1f}万手/{amt}, 日内均价{q.vwap:.2f}"
                f"{limit_note}{tech_note}{flag_note}, "
                f"{buy_hint}{sell_hint}{calc_note}"
            )

        # 全局执行事实（置顶）：同分钟两腿会被整组丢弃——8/24 出现 6 次
        hard_constraints.insert(
            0,
            "同一标的同一分钟只能输出一个方向（BUY或SELL或HOLD）；"
            "同时输出BUY和SELL时，只保留当前账户可执行的一条（可卖>0保留SELL，可卖=0保留BUY），另一条丢弃",
        )
        if risk_state.value == "HALT":
            hard_constraints.append("风控状态为限制交易：只允许SELL，禁止一切BUY")
        elif risk_state.value == "LIQUIDATE":
            hard_constraints.append("风控状态为紧急：禁止一切操作，只能输出HOLD")
        constraints_text = chr(10).join(f"- {c}" for c in hard_constraints) \
            if hard_constraints else "无"

        # 日内轨迹摘要（最近30分钟高/低/走势）
        intraday_info = []
        if self._market_service is not None:
            try:
                for code, s in intraday_data.items():
                    if code not in self._watchlist:
                        continue
                    extra = ""
                    if s.get("path_10m"):
                        extra += f" {s['path_10m']}"
                    if s.get("high_at") is not None and s.get("low_at") is not None:
                        extra += (
                            f" 最高{s['high_at'].strftime('%H:%M')}出现"
                            f"（距今{s.get('high_ago_min', 0)}分钟）"
                            f" 最低{s['low_at'].strftime('%H:%M')}出现"
                            f"（距今{s.get('low_ago_min', 0)}分钟）"
                        )
                    intraday_info.append(
                        f"- {code}: 近30分钟最高{s['recent_high']} 最低{s['recent_low']} "
                        f"走势{s['trend_30m']:+.2f}%{extra}"
                    )
            except Exception:
                pass

        # Today Plan（含 T 预算消耗与剩余，预算剩余笔数预计算，免去模型减法）
        plan_text = "无"
        if self._today_plan and getattr(self._today_plan, "plans", None):
            lines = []
            for p in self._today_plan.plans:
                t_used = self._t_budget_used(p, p.code, fills_by_code, sell_fills_by_code)
                remaining = max(0, p.max_trades_hint - t_used)
                pos = snapshot.positions.get(p.code)
                pending = sells_by_code.get(p.code, 0) - buys_by_code.get(p.code, 0)
                if p and t_used >= p.max_trades_hint and pending <= 0:
                    exec_now = "HOLD（做T次数已满）"
                elif p and t_used >= p.max_trades_hint and pending > 0:
                    exec_now = f"接回买入（未接回{pending}股）"
                elif pos is None:
                    if pending > 0:
                        exec_now = f"接回买入（未接回{pending}股）或观望；不是建仓"
                        mb = max_buyable_by_code.get(p.code, 0)
                        if mb > 0:
                            exec_now += f"；最多可买{mb}股"
                    else:
                        exec_now = "买入建仓或观望（无持仓）"
                elif pos.sellable_shares <= 0:
                    exec_now = "HOLD（T+1不可卖）"
                    if pending > 0:
                        exec_now += f"；未接回{pending}股"
                else:
                    bits = [f"可卖{pos.sellable_shares}股"]
                    if pending > 0:
                        bits.append(f"未接回{pending}股")
                    mb = max_buyable_by_code.get(p.code, 0)
                    if mb > 0:
                        bits.append(f"最多可买{mb}股")
                    exec_now = "；".join(bits) + "；同一分钟只能选一个方向"
                if p.t_strategy == "SELL_FIRST_THEN_BUY_BACK":
                    remain_note = (
                        f"（剩余{remaining}次；每笔SELL占1次，分批各计1次；接回买入不计入）"
                    )
                else:
                    remain_note = f"（剩余{remaining}次，接回买入不计入）"
                lines.append(
                    f"- {p.code}: 策略={p.t_strategy}, 目标仓位比例={p.target_position_ratio}, "
                    f"风险={p.risk_level}, 今日已做T {t_used}次/上限{p.max_trades_hint}次"
                    f"{remain_note}, 计划={p.trade_plan}；"
                    f"当前可执行={exec_now}"
                )
            bias = getattr(self._today_plan, "global_bias", None)
            gen_at = getattr(self._today_plan, "generated_at", "") or ""
            last_at = getattr(self._today_plan, "last_at_plan", None) or {}
            cmp_bits = []
            for code in self._watchlist:
                q = quotes.get(code)
                old = last_at.get(code)
                if q is None or old is None:
                    continue
                old_d = Decimal(str(old))
                delta = q.last - old_d
                cmp_bits.append(
                    f"{code}当时现价{old_d:.2f}，当前{q.last:.2f}（较计划时{delta:+.2f}元）"
                )
            meta = ""
            if gen_at and cmp_bits:
                meta = f"计划生成于{gen_at}；" + "；".join(cmp_bits) + "。\n"
            elif gen_at:
                meta = f"计划生成于{gen_at}。\n"
            plan_text = (
                meta
                + f"整体偏好={bias.value if hasattr(bias, 'value') else bias}\n"
                + chr(10).join(lines)
            )

        # 相关记忆（长期记忆模块）
        memory_text = ""
        if self._memory_retriever is not None and self._watchlist:
            try:
                items = self._memory_retriever.retrieve_for_decision(self._watchlist)
                if items:
                    memory_text = chr(10).join(f"- {m.content[:80]}" for m in items[:5])
            except Exception:
                pass

        # 今日已成交与风控反馈
        fills_text = chr(10).join(today_fills) if today_fills else "今日暂无成交"
        feedback_text = chr(10).join(self._recent_feedback) if self._recent_feedback \
            else "无（注意：被拒绝的指令不要重复提交）"

        now = now_cst()
        suspend_hm = self._config.scheduler.session_pm_end
        mins_left = _minutes_until(now, suspend_hm)
        elapsed = _session_elapsed_minutes(
            now,
            self._config.scheduler.session_am_start,
            self._config.scheduler.session_am_end,
            self._config.scheduler.session_pm_start,
        )
        if mins_left >= 0:
            clock_text = (
                f"{now.strftime('%H:%M')}，连续竞价已过{elapsed}分钟，"
                f"距停止下单{suspend_hm}还有{mins_left}分钟"
            )
        else:
            clock_text = f"{now.strftime('%H:%M')}（已过停止下单{suspend_hm}）"
        reserved_pct = float(reserved_ratio) * 100
        power_shown = buy_power if buy_power > 0 else Decimal("0")
        power_text = f"{power_shown:.2f}（已扣现金预留{reserved_pct:.0f}%及最低佣金）"

        prompt = f"""你是一个A股日内交易决策引擎。根据当前账户状态、行情和今日计划，输出交易决策。
你每分钟被调用一次。买入按卖一成交、卖出按买一成交。跨分钟记忆见下方"今日已成交"和"风控反馈"；不要重复提交已被拒绝的指令。同一标的可以跨分钟分批买卖。
本次股数由本分钟决定，可以小于可卖或未接回全部，也可以等于全部可卖；计划里写的股数不是必须一次做完的手数。
今日计划是开盘时的框架与偏好（方向、预算、相对条件），不是本分钟必须命中的绝对成交价。本分钟根据下方当前行情与预计算判断；计划里若出现绝对价，以本分钟数据为准，不要把「现价高于/低于计划价」当成禁止买卖的条件。
未接回仅在今日已卖多于已买时出现且为正数。持仓区写有未接回股数时，买入是接回该笔做T，不是建仓。无未接回时买入不是接回（已持仓为加仓，空仓为建仓）。仓位比例相对目标、日内区间位置是数据，不是减仓或卖出的硬指令；区间位置须同时看连续竞价已过分钟与最高/最低出现时刻。

## 硬性约束（最高优先级，逐条检查后再决策，违反将被立即拒绝）
{constraints_text}

## 市场环境
{env_text}

## 当前状态
- 日期时段: 连续竞价
- 当前时刻: {clock_text}
- 风控状态: {state_display}
- 账户净值: {snapshot.nav_mark}
- 可用现金: {snapshot.cash_available}
- 购买力: {power_text}
- 当日已实现盈亏: {snapshot.realized_pnl_today}
- 当日已付费用: {fees_today}
- 回撤状态: {drawdown_text}

## 持仓
{chr(10).join(holdings_info) if holdings_info else "无持仓"}

## 今日已成交（你的历史操作，不要重复）
{fills_text}

## 最近风控反馈（这些指令已被拒绝，不要重复提交）
{feedback_text}

## 股票池行情
{chr(10).join(watchlist_info) if watchlist_info else "无行情"}

## 日内走势（最近30分钟）
{chr(10).join(intraday_info) if intraday_info else "开盘初期暂无轨迹"}

## 今日计划（Today Plan，开盘框架，价位为参考）
{plan_text}

## 相关记忆
{memory_text if memory_text else "无"}

## 规则
1. 已持仓的股票：做T（高抛低吸）或继续持有
2. 股票池中未持仓且今日无未接回的股票：允许买入建立底仓（目标仓位参考今日计划的目标仓位比例，首次建仓不超过净值的25%）。未持仓但持仓区写有未接回股数时，买入是接回该笔做T，不是建仓
3. 加仓：已持仓且低于目标仓位比例时允许买入，累计不超过目标仓位比例。接回（买入今日已卖出但尚未买回的股份）不是加仓：仓位高于目标时仍允许接回，但不得超过未接回股数，且仍受可买手数/现金/单票上限约束。无未接回时买入不是接回
4. 买入必须100股整数倍，且不得超过该标的标注的买入容量/最多可买股数；标注"禁止发出BUY"的标的不得输出BUY。标注"禁止加仓BUY"只禁止加仓，不等于禁止接回：卖出后的接回仍允许（受未接回股数与最多可买约束）
5. 当日涨幅、距压力位、仓位相对目标、日内区间位置见行情预计算（数据，非禁令，也不是减仓指令）
6. 卖出前提：持仓区该标的可卖数量>0。持仓0股的未接回行不能SELL。标注"T+1锁定，禁止发出SELL"或"禁止发出SELL（无持仓/持仓0股）"的标的不得输出SELL；已清仓当天不得再输出SELL。清仓后若持仓区仍有未接回，买入是接回不是建仓；无未接回才是建仓
7. 卖出数量必须为100股整数倍，或等于全部可卖数量（一次性清仓允许零股）；卖出不得超过可卖数量。本次股数不必等于可卖全部或未接回全部
8. 同一标的同一分钟只能输出一个方向（BUY或SELL或HOLD），禁止同时输出BUY和SELL（立即执行下等于白付手续费；代码会只保留可执行的一条）
9. 每只票当日做T次数见今日计划该标的一行；次数用尽后的限制见置顶硬约束
10. 做T：一次做T=卖出+买回（高抛低吸）。同一分钟只能选一个方向。卖出后未接回股数见持仓区（仅已卖>已买时写未接回；已闭环写接回已闭环；今日无卖出的买入不是接回。持仓0股且有未接回时仍会写未接回，不要当成从未持仓的建仓）；是否接回、何时接回由你根据当前数据判断，不强制当日接回；接回不占用新的做T次数
11. confidence < 0.6 的决策会被风控拒绝
12. 风控状态为限制交易时只能卖出不能买入

## 输出格式（严格JSON）
shares 为本次股数：买入必须100股整数倍且不超过最多可买；卖出必须100股整数倍，或等于全部可卖。本次不必等于可卖全部或未接回全部。示例中的100只是字段占位，不是默认手数。
```json
{{
  "thought_process": "分析思路",
  "decisions": [
    {{
      "action": "BUY|SELL|HOLD",
      "code": "股票代码",
      "shares": 100,
      "confidence": 0.8,
      "reason": "决策理由",
      "risk_level": "LOW|MEDIUM|HIGH",
      "referenced_memory": []
    }}
  ]
}}
```

如果没有好的机会，所有标的输出HOLD。"""

        return prompt

    def _parse_decision(self, raw: dict, tick_id: str) -> Optional[DecisionOutput]:
        """解析并校验 Decision JSON"""
        try:
            decisions = []
            for d in raw.get("decisions", []):
                action_str = d.get("action", "HOLD").upper()
                try:
                    action = ActionType(action_str)
                except ValueError:
                    action = ActionType.HOLD

                confidence = d.get("confidence", 0.0)
                if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
                    confidence = 0.0

                item = DecisionItem(
                    action=action,
                    code=d.get("code", ""),
                    shares=int(d.get("shares", 0)),
                    confidence=float(confidence),
                    reason=d.get("reason", ""),
                    risk_level=d.get("risk_level", "MEDIUM"),
                    referenced_memory=d.get("referenced_memory", []),
                )
                decisions.append(item)

            return DecisionOutput(
                thought_process=raw.get("thought_process", ""),
                decisions=decisions,
                prompt_version=self._prompt_version,
                context_id=f"ctx_{tick_id}",
            )
        except Exception as e:
            logger.error("decision_parse_failed", error=str(e))
            return None
