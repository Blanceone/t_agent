"""
LLM 统一调用客户端 + 单飞行控制
"""

import json
import os
from typing import Optional

from agent.common.logger import get_logger
from agent.common.errors import LLMTimeoutError
from agent.config.schema import LLMConfig

logger = get_logger("llm.client")


class SingleFlightGuard:
    """LLM 单飞行：上次未返回则本分钟跳过"""

    def __init__(self):
        self._in_flight = False

    def try_acquire(self) -> bool:
        if self._in_flight:
            return False
        self._in_flight = True
        return True

    def release(self):
        self._in_flight = False

    @property
    def in_flight(self) -> bool:
        return self._in_flight


class LLMClient:
    """LLM 统一调用客户端"""

    def __init__(self, config: LLMConfig):
        self._config = config
        self._client = None
        # 最近一次调用失败类型：None / "content_filter" / "call_failed"
        self.last_error: Optional[str] = None
        self._init_client()

    def _init_client(self):
        """延迟初始化 OpenAI 客户端"""
        try:
            from openai import OpenAI
            api_key = os.getenv(self._config.api_key_env, "")
            base_url = os.getenv(self._config.base_url_env, None)
            if api_key:
                # max_retries=0：快速失败降级，避免重试放大等待时间阻塞日切流程
                self._client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)
        except ImportError:
            logger.warning("openai_not_installed")

    def call(self, prompt: str, timeout_ms: Optional[int] = None) -> Optional[str]:
        """
        调用 LLM。

        Returns:
            LLM 响应文本，失败返回 None
        """
        if self._client is None:
            logger.warning("llm_client_not_initialized")
            self.last_error = "call_failed"
            return None

        timeout = (timeout_ms or self._config.timeout_ms) / 1000.0

        try:
            kwargs = {
                "model": self._config.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self._config.temperature,
                "timeout": timeout,
            }
            if self._config.extra_body:
                kwargs["extra_body"] = self._config.extra_body
            response = self._client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            self.last_error = None
            return content
        except Exception as e:
            msg = str(e)
            if "contentFilter" in msg or "1301" in msg:
                # 内容安全审查拦截（降级为 warning，避免刷屏）
                self.last_error = "content_filter"
                logger.warning("llm_content_filtered", model=self._config.model)
            else:
                self.last_error = "call_failed"
                logger.error("llm_call_failed", error=msg, model=self._config.model)
            return None

    def call_json(self, prompt: str, timeout_ms: Optional[int] = None) -> Optional[dict]:
        """调用 LLM 并解析 JSON"""
        raw = self.call(prompt, timeout_ms)
        if raw is None:
            return None

        try:
            # 尝试提取 ```json 块
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]
            return json.loads(raw.strip())
        except (json.JSONDecodeError, IndexError):
            logger.warning("llm_json_parse_failed", raw_preview=raw[:200])
            return None
