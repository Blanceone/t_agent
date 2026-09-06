"""
Memory 持久化存储 + 写入 + 检索 + 压缩

Memory 必须长期保留，不能每天重新开始。
存储：SQLite + JSONL 双写
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from agent.common.models import MemoryItem, MemoryType
from agent.common.logger import get_logger
from agent.common.utils import gen_memory_id, today_str

logger = get_logger("memory.store")


class MemoryStore:
    """Memory 持久化（SQLite + JSONL 双写）"""

    def __init__(self, db_path: str = "data/memory/memory.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._jsonl_path = self._db_path.parent / "items.jsonl"
        self._seq = 0
        self._init_db()
        self._recover_seq()

    def _init_db(self):
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_items (
                memory_id TEXT PRIMARY KEY,
                schema_version TEXT NOT NULL DEFAULT 'memory.v1',
                type TEXT NOT NULL,
                codes TEXT NOT NULL,
                created_at TEXT NOT NULL,
                ttl_days INTEGER,
                tags TEXT,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                importance REAL DEFAULT 0.5,
                compressed INTEGER DEFAULT 0,
                original_ref TEXT,
                archived INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_items(type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_importance ON memory_items(importance DESC)")
        conn.commit()
        conn.close()

    def _recover_seq(self):
        """从数据库恢复当日 seq 计数器，防止重启后 ID 碰撞覆盖"""
        try:
            conn = sqlite3.connect(str(self._db_path))
            row = conn.execute(
                "SELECT COUNT(*) FROM memory_items WHERE created_at = ?",
                (today_str(),)
            ).fetchone()
            self._seq = row[0] if row else 0
            conn.close()
        except Exception:
            self._seq = 0

    def write(self, item: MemoryItem) -> str:
        """写入一条 Memory"""
        conn = sqlite3.connect(str(self._db_path))
        conn.execute(
            """INSERT OR REPLACE INTO memory_items
               (memory_id, schema_version, type, codes, created_at, ttl_days, tags, content, source, importance, compressed, original_ref)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.memory_id, item.schema_version, item.type.value,
             json.dumps(item.codes), item.created_at, item.ttl_days,
             json.dumps(item.tags), item.content, item.source,
             item.importance, int(item.compressed), item.original_ref)
        )
        conn.commit()
        conn.close()

        # JSONL 备份
        with open(self._jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "memory_id": item.memory_id, "type": item.type.value,
                "codes": item.codes, "content": item.content,
                "source": item.source, "importance": item.importance,
                "created_at": item.created_at, "tags": item.tags,
            }, ensure_ascii=False) + "\n")

        logger.info("memory_written", memory_id=item.memory_id, type=item.type.value)
        return item.memory_id

    def query(self, codes: Optional[List[str]] = None, types: Optional[List[MemoryType]] = None,
              tags: Optional[List[str]] = None, limit: int = 8) -> List[MemoryItem]:
        """检索 Top-K（按 importance + recency 排序）"""
        conn = sqlite3.connect(str(self._db_path))
        sql = "SELECT * FROM memory_items WHERE archived = 0"
        params: list = []

        if types:
            placeholders = ",".join("?" * len(types))
            sql += f" AND type IN ({placeholders})"
            params.extend(t.value for t in types)

        # codes 过滤下推到 SQL 层，避免 LIMIT 后再过滤导致结果不足
        if codes:
            code_conditions = " OR ".join("codes LIKE ?" for _ in codes)
            sql += f" AND ({code_conditions})"
            params.extend(f'%"{c}"%' for c in codes)

        sql += " ORDER BY importance DESC, created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        conn.close()

        items = []
        for row in rows:
            item = MemoryItem(
                memory_id=row[0], schema_version=row[1],
                type=MemoryType(row[2]), codes=json.loads(row[3]),
                created_at=row[4], ttl_days=row[5],
                tags=json.loads(row[6]) if row[6] else [],
                content=row[7], source=row[8], importance=row[9],
                compressed=bool(row[10]), original_ref=row[11],
            )
            items.append(item)

        return items

    def next_id(self) -> str:
        self._seq += 1
        return gen_memory_id(today_str(), self._seq)


class MemoryWriter:
    """Memory 写入器"""

    def __init__(self, store: MemoryStore):
        self._store = store

    def write_reflection(self, content: str, codes: List[str], tags: List[str],
                         importance: float = 0.7) -> str:
        item = MemoryItem(
            memory_id=self._store.next_id(),
            type=MemoryType.REFLECTION,
            codes=codes, created_at=today_str(),
            ttl_days=None, tags=tags,
            content=content, source="reflection_v1",
            importance=importance,
        )
        return self._store.write(item)

    def write_risk_event(self, event_type: str, code: str, detail: str) -> str:
        item = MemoryItem(
            memory_id=self._store.next_id(),
            type=MemoryType.HOLDING,
            codes=[code], created_at=today_str(),
            ttl_days=None, tags=[event_type.lower()],
            content=detail, source="risk_event",
            importance=0.9,
        )
        return self._store.write(item)

    def write_trade(self, content: str, codes: List[str]) -> str:
        item = MemoryItem(
            memory_id=self._store.next_id(),
            type=MemoryType.TRADE,
            codes=codes, created_at=today_str(),
            ttl_days=None, tags=["trade"],
            content=content, source="trade_result",
            importance=0.6,
        )
        return self._store.write(item)


class MemoryRetriever:
    """Memory 检索器"""

    def __init__(self, store: MemoryStore, top_k: int = 8, max_tokens: int = 1500):
        self._store = store
        self._top_k = top_k
        self._max_tokens = max_tokens

    def retrieve_for_decision(self, codes: List[str]) -> List[MemoryItem]:
        return self._store.query(codes=codes, limit=self._top_k)

    def retrieve_for_reflection(self) -> List[MemoryItem]:
        return self._store.query(limit=self._top_k)
