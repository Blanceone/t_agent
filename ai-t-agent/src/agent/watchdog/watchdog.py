"""
WatchDog 进程监控

职责：
- 监控主进程心跳
- LLM 连续超时 → 降级模式
- 行情中断 → 告警
- 磁盘空间 → 告警
- 账户一致性 → 日终校验

原则：隔离重启、保留账本、告警、降级。不可直接改账。
"""

import json
import os
import time
from pathlib import Path
from datetime import datetime

from agent.common.logger import get_logger, setup_logging

logger = get_logger("watchdog")


class WatchDog:
    """进程监控"""

    def __init__(self, data_dir: str = "data", heartbeat_timeout: int = 90):
        self._data_dir = Path(data_dir)
        self._heartbeat_file = self._data_dir / "heartbeat.json"
        self._heartbeat_timeout = heartbeat_timeout
        self._running = False
        self._llm_fail_count = 0

    def run(self):
        """主监控循环"""
        self._running = True
        logger.info("watchdog_started")

        while self._running:
            try:
                self._check_heartbeat()
                self._check_disk_space()
                time.sleep(30)
            except Exception as e:
                logger.error("watchdog_error", error=str(e))
                time.sleep(10)

    def stop(self):
        self._running = False

    def _check_heartbeat(self):
        """检查主进程心跳"""
        if not self._heartbeat_file.exists():
            return

        try:
            data = json.loads(self._heartbeat_file.read_text())
            last_beat = datetime.fromisoformat(data["timestamp"])
            elapsed = (datetime.now() - last_beat).total_seconds()

            if elapsed > self._heartbeat_timeout:
                logger.critical(
                    "heartbeat_timeout",
                    elapsed_sec=elapsed,
                    threshold=self._heartbeat_timeout,
                )
                # 这里可以触发重启（systemd 会自动处理）
        except Exception:
            pass

    def _check_disk_space(self):
        """检查磁盘空间"""
        try:
            import shutil
            total, used, free = shutil.disk_usage(str(self._data_dir))
            free_gb = free / (1024 ** 3)
            if free_gb < 1.0:
                logger.critical("disk_space_low", free_gb=f"{free_gb:.2f}")
        except Exception:
            pass

    def update_heartbeat(self):
        """更新心跳（由主进程调用）"""
        self._heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
        self._heartbeat_file.write_text(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "pid": os.getpid(),
        }))


def main():
    setup_logging("INFO")
    wd = WatchDog()
    try:
        wd.run()
    except KeyboardInterrupt:
        wd.stop()


if __name__ == "__main__":
    main()
