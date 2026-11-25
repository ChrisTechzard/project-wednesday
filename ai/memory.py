"""SQLite-backed local memory with a sensitive-data filter."""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.logging import get_logger

SENSITIVE_PATTERN = re.compile(
    r"(password|passwd|secret|api[_-]?key|token|private[_-]?key|credit[_-]?card|pin\b)",
    re.IGNORECASE,
)


class MemoryStore:
    """Persistent key/value memories plus recent conversation context."""

    def __init__(self, db_path: Path, enabled: bool = True) -> None:
        self._path = db_path
        self._enabled = enabled
        self._lock = threading.RLock()
        self._log = get_logger("memory")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (category, key)
                );
                CREATE TABLE IF NOT EXISTS conversation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def remember(self, key: str, value: str, category: str = "general") -> str:
        """Store a fact. Refuses obviously sensitive values."""
        if not self._enabled:
            return "Memory is disabled."
        key, value = key.strip(), value.strip()
        if not key or not value:
            return "Nothing to remember: both a name and a value are required."
        if SENSITIVE_PATTERN.search(key) or SENSITIVE_PATTERN.search(value):
            return "I will not store passwords, tokens, API keys or other secrets."
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO memories (category, key, value, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(category, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (category, key, value, now, now),
            )
        self._log.info("Remembered %s/%s", category, key)
        return f"Remembered: {key} = {value}"

    def recall(self, key: str) -> str:
        """Retrieve one memory by key (searches all categories)."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT category, value FROM memories WHERE key LIKE ? ORDER BY updated_at DESC LIMIT 1",
                (f"%{key.strip()}%",),
            ).fetchone()
        if row is None:
            return f"I have no memory matching '{key}'."
        return f"{row['key'] if 'key' in row.keys() else key}: {row['value']}"

    def list_all(self, limit: int = 50) -> list[dict[str, str]]:
        """Return stored memories, newest first."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT category, key, value, updated_at FROM memories ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def forget(self, key: str) -> str:
        """Delete a single memory by key."""
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM memories WHERE key LIKE ?", (f"%{key.strip()}%",))
            count = cursor.rowcount
        return f"Forgot {count} matching memory/m memories." if count else f"No memory matching '{key}'."

    def clear(self) -> str:
        """Delete all stored memories and conversation context."""
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM memories")
            conn.execute("DELETE FROM conversation")
        return "All memories and conversation context have been cleared."

    def context_lines(self, limit: int = 10) -> list[str]:
        """Return compact memory lines for prompt injection."""
        return [f"- {item['key']}: {item['value']}" for item in self.list_all(limit)]

    def log_message(self, role: str, content: str) -> None:
        """Append one conversation message."""
        if not self._enabled or not content.strip():
            return
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO conversation (role, content, created_at) VALUES (?, ?, ?)",
                (role, content[:4000], datetime.now().isoformat(timespec="seconds")),
            )

    def recent_messages(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent conversation messages in chronological order."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversation ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def counts(self) -> dict[str, int]:
        """Return memory and conversation counts for diagnostics."""
        with self._lock, self._connect() as conn:
            memories = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            messages = conn.execute("SELECT COUNT(*) FROM conversation").fetchone()[0]
        return {"memories": int(memories), "messages": int(messages)}
