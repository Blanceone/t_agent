"""LLM 连通性测试"""
import sys
sys.path.insert(0, "/opt/ai-t-agent/src")

from agent.config.loader import load_config
from agent.llm.client import LLMClient

config = load_config()
print(f"模型: {config.llm.model}")
print(f"Provider: {config.llm.provider}")

client = LLMClient(config.llm)
result = client.call("请回复OK两个字", timeout_ms=15000)

if result:
    print(f"LLM 正常! 响应: {result}")
else:
    print("LLM 调用失败，请检查 API Key 和网络")
    sys.exit(1)
