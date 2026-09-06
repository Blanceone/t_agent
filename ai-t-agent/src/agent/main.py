"""
AI-T-Agent 主入口

加载配置 → 初始化模块 → 启动 Scheduler
"""

import sys
from pathlib import Path

from agent.config.loader import load_config
from agent.common.logger import setup_logging, get_logger
from agent.common.event_log import EventLog
from agent.trading.engine import TradingEngine
from agent.risk.engine import RiskEngine
from agent.market.service import MarketService, FeatureEngine
from agent.memory.store import MemoryStore, MemoryWriter, MemoryRetriever
from agent.llm.client import LLMClient
from agent.decision.engine import DecisionEngine
from agent.reflection.stats import ReflectionEngine
from agent.replay.store import ReplayStore
from agent.scheduler.scheduler import Scheduler


def main():
    """主入口"""
    # 1. 加载配置
    config = load_config()

    # 2. 初始化日志
    setup_logging(config.log_level, f"{config.data_dir}/logs")
    logger = get_logger("main")
    logger.info("agent_starting", env=config.env)

    # 3. 初始化 Event Log
    event_log = EventLog(f"{config.data_dir}/logs")

    # 4. 初始化 Trading Engine
    trading_engine = TradingEngine(config, event_log)

    # 尝试加载已有账户
    account_path = f"{config.data_dir}/account/state.json"
    if not trading_engine.account.load(account_path):
        logger.info("new_account_created", initial_cash=str(config.trading.initial_cash))

    # 5. 初始化 Risk Engine
    risk_engine = RiskEngine(config.risk, event_log)

    # 6. 初始化 Market Service
    market_service = MarketService(config)
    market_service.set_watchlist(list(trading_engine.account.watchlist.keys()))

    # 7. 初始化 Memory
    memory_store = MemoryStore(config.memory.db_path)
    memory_writer = MemoryWriter(memory_store)
    memory_retriever = MemoryRetriever(memory_store, config.memory.memory_top_k)

    # 8. 初始化 LLM + Decision
    llm_client = LLMClient(config.llm)
    decision_engine = DecisionEngine(config, llm_client)

    # 9. 初始化 Reflection
    reflection_engine = ReflectionEngine(event_log, memory_writer, llm_client,
                                         report_dir=f"{config.data_dir}/reports")

    # 10. 初始化 Replay
    replay_store = ReplayStore(f"{config.data_dir}/replay")

    # 11. 启动 Scheduler
    scheduler = Scheduler(
        config=config,
        trading_engine=trading_engine,
        risk_engine=risk_engine,
        decision_engine=decision_engine,
        market_service=market_service,
        reflection_engine=reflection_engine,
        event_log=event_log,
        llm_client=llm_client,
        memory_retriever=memory_retriever,
        replay_store=replay_store,
    )

    logger.info("agent_initialized", modules="all")

    try:
        scheduler.run()
    except KeyboardInterrupt:
        logger.info("agent_shutdown", reason="keyboard_interrupt")
        scheduler.stop()
        trading_engine.persist()


if __name__ == "__main__":
    main()
