"""
Memory 压缩与晋升

- 压缩：定期将旧 SHORT/TRADE 细节压缩为摘要
- 晋升：高重要度 REFLECTION/HOLDING 记忆晋升为 LONG 类型（永久保留）
"""

import sqlite3
from pathlib import Path
from typing import List

from agent.common.logger import get_logger

logger = get_logger("memory.compressor")


class MemoryCompressor:
    """Memory 压缩器 + 晋升器"""

    def __init__(self, db_path: str = "data/memory/memory.db",
                 compress_after_days: int = 30,
                 promote_importance_threshold: float = 0.85):
        self._db_path = Path(db_path)
        self._compress_after_days = compress_after_days
        self._promote_threshold = promote_importance_threshold

    def compress_old(self) -> int:
        """
        将超过 N 天的 SHORT/TRADE 类型记忆标记为压缩。

        Returns:
            压缩的条目数
        """
        if not self._db_path.exists():
            return 0

        conn = sqlite3.connect(str(self._db_path))

        cursor = conn.execute(
            """SELECT memory_id, content FROM memory_items
               WHERE compressed = 0
               AND type IN ('SHORT', 'TRADE')
               AND julianday('now') - julianday(created_at) > ?""",
            (self._compress_after_days,)
        )
        rows = cursor.fetchall()

        count = 0
        for memory_id, content in rows:
            summary = content[:100] + "..." if len(content) > 100 else content
            conn.execute(
                "UPDATE memory_items SET compressed = 1, content = ? WHERE memory_id = ?",
                (summary, memory_id)
            )
            count += 1

        conn.commit()
        conn.close()

        if count > 0:
            logger.info("memory_compressed", count=count, after_days=self._compress_after_days)

        return count

    def promote_important(self) -> int:
        """
        将高重要度的 REFLECTION/HOLDING 记忆晋升为 LONG 类型。

        晋升条件：importance >= threshold 且 type 不是 LONG。
        晋升后永久保留，不受压缩影响。

        Returns:
            晋升的条目数
        """
        if not self._db_path.exists():
            return 0

        conn = sqlite3.connect(str(self._db_path))

        cursor = conn.execute(
            """SELECT memory_id, type, content FROM memory_items
               WHERE type IN ('REFLECTION', 'HOLDING', 'PORTFOLIO')
               AND importance >= ?
               AND archived = 0""",
            (self._promote_threshold,)
        )
        rows = cursor.fetchall()

        count = 0
        for memory_id, mem_type, content in rows:
            conn.execute(
                "UPDATE memory_items SET type = 'LONG' WHERE memory_id = ?",
                (memory_id,)
            )
            count += 1
            logger.info("memory_promoted", memory_id=memory_id, from_type=mem_type)

        conn.commit()
        conn.close()

        if count > 0:
            logger.info("memory_promotion_done", count=count)

        return count

    def run_daily(self) -> dict:
        """每日维护：压缩 + 晋升"""
        compressed = self.compress_old()
        promoted = self.promote_important()
        stats = self.get_stats()
        return {"compressed": compressed, "promoted": promoted, **stats}

    def get_stats(self) -> dict:
        """获取 Memory 统计"""
        if not self._db_path.exists():
            return {"total": 0, "compressed": 0, "active": 0, "long_term": 0}

        conn = sqlite3.connect(str(self._db_path))
        total = conn.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0]
        compressed = conn.execute(
            "SELECT COUNT(*) FROM memory_items WHERE compressed = 1"
        ).fetchone()[0]
        long_term = conn.execute(
            "SELECT COUNT(*) FROM memory_items WHERE type = 'LONG'"
        ).fetchone()[0]
        conn.close()

        return {"total": total, "compressed": compressed,
                "active": total - compressed, "long_term": long_term}
