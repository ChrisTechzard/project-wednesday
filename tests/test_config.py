"""Configuration persistence and validation tests."""

from __future__ import annotations

from core.config import ConfigManager, JarvisConfig


def test_defaults_are_private_and_local() -> None:
    cfg = JarvisConfig()
    assert cfg.ai.cloud_enabled is False
    assert cfg.ai.model == "llama3.2:latest"
    assert cfg.automation.allow_shell_commands is False
    assert cfg.memory.memory_enabled is True


def test_config_persists_round_trip(tmp_path) -> None:
    manager = ConfigManager(tmp_path / "cfg.json")
    manager.update("vision", {"dwell_time_ms": 1500, "camera_index": 2})
    reloaded = ConfigManager(tmp_path / "cfg.json")
    assert reloaded.config.vision.dwell_time_ms == 1500
    assert reloaded.config.vision.camera_index == 2


def test_invalid_section_rejected(config: ConfigManager) -> None:
    try:
        config.update("nonexistent", {"x": 1})
    except ValueError:
        return
    raise AssertionError("Expected ValueError for unknown section")


def test_invalid_value_rejected(config: ConfigManager) -> None:
    import pydantic

    try:
        config.update("ai", {"temperature": 99.0})
    except pydantic.ValidationError:
        return
    raise AssertionError("Expected validation error for out-of-range temperature")
