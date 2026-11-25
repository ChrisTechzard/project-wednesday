"""Shared pytest fixtures for JARVIS tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import ConfigManager  # noqa: E402
from core.events import EventBus  # noqa: E402
from core.safety import SafetyManager  # noqa: E402


@pytest.fixture()
def config(tmp_path: Path) -> ConfigManager:
    return ConfigManager(tmp_path / "config.json")


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def safety(config: ConfigManager, bus: EventBus, tmp_path: Path) -> SafetyManager:
    return SafetyManager(config, bus, tmp_path / "logs")
