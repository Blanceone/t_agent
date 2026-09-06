"""
Decision 输出 Schema 校验（schema: decision.v1）

校验规则：
- action ∈ {BUY, SELL, HOLD}
- confidence ∈ [0, 1]，缺失/非法 → 0
- reason 非空
- risk_level ∈ {LOW, MEDIUM, HIGH}，缺失 → MEDIUM
- referenced_memory 为数组
- shares >= 0，BUY 时 100 整数倍
"""

from typing import List, Optional

from agent.common.models import ActionType, DecisionItem, DecisionOutput
from agent.common.logger import get_logger

logger = get_logger("decision.validator")

VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}


class DecisionValidator:
    """Decision 输出 Schema 校验"""

    def validate(self, raw: dict, prompt_version: str = "", context_id: str = "") -> Optional[DecisionOutput]:
        """
        校验 LLM 输出的 JSON。

        Returns:
            DecisionOutput 或 None（校验失败）
        """
        if not isinstance(raw, dict):
            logger.warning("validator_not_dict", type=str(type(raw)))
            return None

        decisions_raw = raw.get("decisions", [])
        if not isinstance(decisions_raw, list):
            logger.warning("validator_decisions_not_list")
            return None

        decisions: List[DecisionItem] = []
        for d in decisions_raw:
            item = self._validate_item(d)
            if item:
                decisions.append(item)

        return DecisionOutput(
            thought_process=str(raw.get("thought_process", "")),
            decisions=decisions,
            schema_version="decision.v1",
            prompt_version=prompt_version,
            context_id=context_id,
        )

    def _validate_item(self, d: dict) -> Optional[DecisionItem]:
        """校验单条 Decision"""
        if not isinstance(d, dict):
            return None

        # action
        action_str = str(d.get("action", "HOLD")).upper()
        try:
            action = ActionType(action_str)
        except ValueError:
            action = ActionType.HOLD

        # confidence
        confidence = d.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)):
            confidence = 0.0
        confidence = max(0.0, min(1.0, float(confidence)))

        # reason
        reason = str(d.get("reason", ""))
        if not reason:
            reason = "no reason provided"

        # risk_level
        risk_level = str(d.get("risk_level", "MEDIUM")).upper()
        if risk_level not in VALID_RISK_LEVELS:
            risk_level = "MEDIUM"

        # shares：不在此静默改数量。BUY 非整百由撮合层拒绝 INVALID_LOT。
        shares = int(d.get("shares", 0))
        if shares < 0:
            shares = 0

        # referenced_memory
        ref_memory = d.get("referenced_memory", [])
        if not isinstance(ref_memory, list):
            ref_memory = []
        ref_memory = [str(m) for m in ref_memory]

        # code
        code = str(d.get("code", ""))

        return DecisionItem(
            action=action,
            code=code,
            shares=shares,
            confidence=confidence,
            reason=reason,
            risk_level=risk_level,
            referenced_memory=ref_memory,
        )
