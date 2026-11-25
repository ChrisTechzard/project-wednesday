"""Memory store tests, including the sensitive-data filter."""

from __future__ import annotations

from pathlib import Path

from ai.memory import MemoryStore


def test_remember_recall_forget(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3")
    assert "Remembered" in store.remember("editor", "VS Code", "preference")
    assert "VS Code" in store.recall("editor")
    assert store.counts()["memories"] == 1
    assert "Forgot 1" in store.forget("editor")
    assert store.counts()["memories"] == 0


def test_sensitive_information_is_not_stored(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3")
    result = store.remember("wifi password", "hunter2")
    assert "will not store" in result.lower()
    assert store.counts()["memories"] == 0


def test_disabled_memory_is_no_op(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3", enabled=False)
    store.remember("project", "Jarvis")
    assert store.counts()["memories"] == 0
    store.set_enabled(True)
    store.remember("project", "Jarvis")
    assert store.counts()["memories"] == 1


def test_clear_removes_everything(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.remember("a", "b")
    store.log_message("user", "hello")
    assert store.counts() == {"memories": 1, "messages": 1}
    store.clear()
    assert store.counts() == {"memories": 0, "messages": 0}
