"""Typed, persisted configuration for JARVIS."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

CONFIG_DIR = Path.home() / ".config" / "Jarvis"
CONFIG_PATH = CONFIG_DIR / "config.json"


class AIConfig(BaseModel):
    """Local Ollama settings. Cloud is opt-in and disabled by default."""

    ollama_host: str = "http://127.0.0.1:11434"
    model: str = "llama3.2:latest"
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    timeout_seconds: int = Field(default=60, ge=5, le=600)
    cloud_enabled: bool = False
    cloud_provider: str = "none"
    cloud_api_key_env: str = ""
    max_history_messages: int = Field(default=20, ge=2, le=200)

    @field_validator("ollama_host")
    @classmethod
    def _host_must_be_http(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("ollama_host must start with http:// or https://")
        return value.rstrip("/")


class VoiceConfig(BaseModel):
    """Microphone, wake word, STT and TTS settings."""

    voice_enabled: bool = True
    microphone_name: str = ""  # empty = system default
    sample_rate: int = 16000
    wake_word_enabled: bool = True
    wake_word: str = "jarvis"
    wake_word_threshold: float = Field(default=0.5, ge=0.1, le=0.95)
    stt_model: str = "tiny.en"
    stt_device: str = "cpu"
    stt_threads: int = Field(default=2, ge=1, le=8)
    push_to_talk_enabled: bool = True
    tts_enabled: bool = True
    tts_voice: str = "en_US-lessac-medium"
    tts_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    tts_volume: float = Field(default=0.8, ge=0.0, le=1.0)
    phrase_time_limit: float = Field(default=12.0, ge=2.0, le=60.0)


class VisionConfig(BaseModel):
    """Webcam capture and head/gaze tracking settings."""

    # Camera starts with the app; MediaPipe uses about one CPU core. It can be
    # switched off any time in Settings or the Vision panel.
    vision_enabled: bool = True
    camera_index: int = 0
    target_fps: int = Field(default=10, ge=1, le=60)
    show_preview: bool = True
    head_control_enabled: bool = False
    gaze_control_enabled: bool = False
    cursor_sensitivity: float = Field(default=1.0, ge=0.1, le=3.0)
    cursor_smoothing: float = Field(default=0.35, ge=0.0, le=0.95)
    dead_zone_px: int = Field(default=25, ge=0, le=200)
    dwell_enabled: bool = True
    dwell_time_ms: int = Field(default=900, ge=300, le=5000)
    blink_click_enabled: bool = False
    blink_sensitivity: float = Field(default=0.22, ge=0.05, le=0.5)


class AutomationConfig(BaseModel):
    """Desktop control permissions and application aliases."""

    automation_enabled: bool = True
    require_confirmation: bool = True
    allow_shell_commands: bool = False
    allow_file_deletion: bool = False
    app_aliases: dict[str, str] = Field(
        default_factory=lambda: {
            "vs code": "code",
            "code": "code",
            "terminal": "gnome-terminal",
            "firefox": "firefox",
            "browser": "firefox",
            "files": "nautilus",
            "file manager": "nautilus",
            "settings": "gnome-control-center",
        }
    )
    project_paths: dict[str, str] = Field(default_factory=dict)


class MemoryConfig(BaseModel):
    """Local memory store settings."""

    memory_enabled: bool = True
    auto_save_preferences: bool = True
    remember_conversation_context: bool = True
    max_context_items: int = Field(default=30, ge=1, le=200)


class GeneralConfig(BaseModel):
    """General application settings."""

    theme: str = "dark"
    language: str = "en"
    log_level: str = "INFO"
    start_minimized: bool = False
    tray_enabled: bool = True
    emergency_hotkey: str = "<ctrl>+<shift>+j"


class JarvisConfig(BaseModel):
    """Top-level application configuration."""

    ai: AIConfig = Field(default_factory=AIConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    automation: AutomationConfig = Field(default_factory=AutomationConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    general: GeneralConfig = Field(default_factory=GeneralConfig)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "JarvisConfig":
        """Load config from disk, falling back to defaults on invalid data."""
        if not path.exists():
            config = cls()
            config.save(path)
            return config
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return cls.model_validate(raw)
        except (OSError, ValueError, TypeError) as exc:
            from core.logging import get_logger

            get_logger("config").warning("Invalid config at %s: %s — using defaults", path, exc)
            return cls()

    def save(self, path: Path = CONFIG_PATH) -> None:
        """Atomically persist configuration to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.model_dump(mode="json"), indent=2), encoding="utf-8")
        temp.replace(path)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation."""
        return self.model_dump(mode="json")

    def update_section(self, section: str, values: dict[str, Any]) -> None:
        """Validate and update one named section."""
        if not hasattr(self, section):
            raise ValueError(f"Unknown configuration section: {section}")
        current = getattr(self, section)
        if not isinstance(current, BaseModel):
            raise ValueError(f"Configuration section is not editable: {section}")
        updated = type(current).model_validate({**current.model_dump(), **values})
        setattr(self, section, updated)

    def copy(self) -> "JarvisConfig":
        """Return a deep copy."""
        return deepcopy(self)


class ConfigManager:
    """Thread-safe access to the live configuration."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._config = JarvisConfig.load(path)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def config(self) -> JarvisConfig:
        with self._lock:
            return self._config.copy()

    def update(self, section: str, values: dict[str, Any]) -> JarvisConfig:
        """Update a section and persist it."""
        with self._lock:
            self._config.update_section(section, values)
            self._config.save(self._path)
            return self._config.copy()

    def reset(self) -> JarvisConfig:
        """Reset all settings to defaults and persist."""
        with self._lock:
            self._config = JarvisConfig()
            self._config.save(self._path)
            return self._config.copy()
