"""Settings panel for every configurable JARVIS subsystem."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from core.events import EventBus
from core.models import EventType

from ui.widgets import ACCENT, BG, DANGER, MUTED, action_button, label, panel


class SettingsFrame(ctk.CTkScrollableFrame):
    """Editable settings with explicit save, reset and memory management."""

    def __init__(self, parent: ctk.CTkBaseClass, jarvis: Any, bus: EventBus) -> None:
        super().__init__(parent, fg_color=BG)
        self._jarvis = jarvis
        self._bus = bus
        self._vars: dict[str, Any] = {}
        self._build()

    def _text_var(self, section: str, key: str, value: Any) -> ctk.StringVar:
        var = ctk.StringVar(value=str(value))
        self._vars[f"{section}.{key}"] = var
        return var

    def _bool_var(self, section: str, key: str, value: Any) -> ctk.BooleanVar:
        var = ctk.BooleanVar(value=bool(value))
        self._vars[f"{section}.{key}"] = var
        return var

    def _field(self, parent: ctk.CTkBaseClass, title: str, var: ctk.StringVar, width: int = 240) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)
        label(row, title, 12, text_color=MUTED).pack(side="left")
        ctk.CTkEntry(row, textvariable=var, width=width, height=30).pack(side="right")

    def _toggle(self, parent: ctk.CTkBaseClass, title: str, var: ctk.BooleanVar) -> None:
        ctk.CTkCheckBox(parent, text=title, variable=var).pack(anchor="w", padx=16, pady=4)

    def _build(self) -> None:
        cfg = self._jarvis.config.config
        label(self, "SETTINGS", 26, weight="bold").pack(anchor="w", padx=8, pady=(20, 4))
        label(self, "All settings are stored locally in ~/.config/Jarvis", 12, text_color=MUTED).pack(anchor="w", padx=8)

        ai = panel(self)
        ai.pack(fill="x", padx=8, pady=12)
        label(ai, "AI (LOCAL OLLAMA)", 13, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(14, 6))
        self._field(ai, "Model", self._text_var("ai", "model", cfg.ai.model))
        self._field(ai, "Ollama host", self._text_var("ai", "ollama_host", cfg.ai.ollama_host))
        self._toggle(ai, "Enable cloud AI (off by default — needs credentials)", self._bool_var("ai", "cloud_enabled", cfg.ai.cloud_enabled))

        voice = panel(self)
        voice.pack(fill="x", padx=8, pady=6)
        label(voice, "VOICE", 13, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(14, 6))
        self._toggle(voice, "Voice responses enabled", self._bool_var("voice", "tts_enabled", cfg.voice.tts_enabled))
        self._toggle(voice, "Wake-word listening (say 'Jarvis')", self._bool_var("voice", "wake_word_enabled", cfg.voice.wake_word_enabled))
        mics = self._jarvis.voice.list_microphones()
        mic_var = self._text_var("voice", "microphone_name", cfg.voice.microphone_name)
        row = ctk.CTkFrame(voice, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)
        label(row, "Microphone", 12, text_color=MUTED).pack(side="left")
        ctk.CTkComboBox(row, variable=mic_var, values=[""] + mics, width=260).pack(side="right")
        self._field(voice, "Speech speed (0.5–2.0)", self._text_var("voice", "tts_speed", cfg.voice.tts_speed), 100)
        self._field(voice, "Volume (0.0–1.0)", self._text_var("voice", "tts_volume", cfg.voice.tts_volume), 100)
        self._field(voice, "STT model", self._text_var("voice", "stt_model", cfg.voice.stt_model))
        self._field(voice, "Wake threshold", self._text_var("voice", "wake_word_threshold", cfg.voice.wake_word_threshold), 100)

        vision = panel(self)
        vision.pack(fill="x", padx=8, pady=6)
        label(vision, "VISION & TRACKING", 13, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(14, 6))
        self._toggle(vision, "Enable camera/vision engine at startup", self._bool_var("vision", "vision_enabled", cfg.vision.vision_enabled))
        self._toggle(vision, "Head cursor control", self._bool_var("vision", "head_control_enabled", cfg.vision.head_control_enabled))
        self._toggle(vision, "Gaze cursor control", self._bool_var("vision", "gaze_control_enabled", cfg.vision.gaze_control_enabled))
        self._toggle(vision, "Dwell selection", self._bool_var("vision", "dwell_enabled", cfg.vision.dwell_enabled))
        self._toggle(vision, "Blink click (experimental)", self._bool_var("vision", "blink_click_enabled", cfg.vision.blink_click_enabled))
        self._field(vision, "Dwell time (ms)", self._text_var("vision", "dwell_time_ms", cfg.vision.dwell_time_ms), 100)
        self._field(vision, "Sensitivity", self._text_var("vision", "cursor_sensitivity", cfg.vision.cursor_sensitivity), 100)

        automation = panel(self)
        automation.pack(fill="x", padx=8, pady=6)
        label(automation, "AUTOMATION & SAFETY", 13, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(14, 6))
        self._toggle(automation, "Desktop automation enabled", self._bool_var("automation", "automation_enabled", cfg.automation.automation_enabled))
        self._toggle(automation, "Confirm medium/high-risk actions", self._bool_var("automation", "require_confirmation", cfg.automation.require_confirmation))
        self._toggle(automation, "Allow AI shell commands (not recommended)", self._bool_var("automation", "allow_shell_commands", cfg.automation.allow_shell_commands))
        self._toggle(automation, "Allow file deletion", self._bool_var("automation", "allow_file_deletion", cfg.automation.allow_file_deletion))

        memory_panel = panel(self)
        memory_panel.pack(fill="x", padx=8, pady=6)
        label(memory_panel, "MEMORY", 13, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(14, 6))
        self._toggle(memory_panel, "Memory enabled", self._bool_var("memory", "memory_enabled", cfg.memory.memory_enabled))
        self._toggle(memory_panel, "Use memories in conversation context", self._bool_var("memory", "remember_conversation_context", cfg.memory.remember_conversation_context))
        counts = self._jarvis.memory.counts()
        label(memory_panel, f"Stored: {counts['memories']} facts, {counts['messages']} chat messages", 12, text_color=MUTED).pack(anchor="w", padx=16, pady=6)

        general = panel(self)
        general.pack(fill="x", padx=8, pady=6)
        label(general, "GENERAL", 13, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(14, 6))
        ctk.CTkComboBox(general, values=["dark", "light"], variable=self._text_var("general", "theme", cfg.general.theme), width=140).pack(anchor="w", padx=16, pady=4)
        self._toggle(general, "Tray icon / background operation", self._bool_var("general", "tray_enabled", cfg.general.tray_enabled))
        self._toggle(general, "Start minimized", self._bool_var("general", "start_minimized", cfg.general.start_minimized))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=8, pady=18)
        action_button(actions, "SAVE SETTINGS", self._save, width=160).pack(side="left", padx=6)
        action_button(actions, "RESET DEFAULTS", self._reset, width=160).pack(side="left", padx=6)
        ctk.CTkButton(actions, text="CLEAR MEMORY", width=140, height=36, fg_color=DANGER, hover_color="#C42E3E", command=self._clear_memory).pack(side="left", padx=6)

    def _save(self) -> None:
        from core.config import JarvisConfig

        raw: dict[str, dict[str, Any]] = {}
        for key, var in self._vars.items():
            section, field = key.split(".", 1)
            raw.setdefault(section, {})[field] = var.get()
        try:
            validated = JarvisConfig.model_validate({**self._jarvis.config.to_dict(), **raw})
        except Exception as exc:
            self._bus.emit(EventType.ERROR, {"message": f"Invalid settings: {exc}"}, "settings")
            return
        for section in ("ai", "voice", "vision", "automation", "memory", "general"):
            self._jarvis.config.update(section, validated.model_dump()[section])
        self._jarvis.voice.refresh_devices()
        self._jarvis.voice.set_wake_enabled(validated.voice.wake_word_enabled)
        self._jarvis.memory.set_enabled(validated.memory.memory_enabled)
        self._jarvis.bus.emit(EventType.STATUS, {"settings_saved": True}, "settings")

    def _reset(self) -> None:
        self._jarvis.config.reset()
        self._bus.emit(EventType.STATUS, {"message": "Settings reset to defaults — restart to apply all."}, "settings")

    def _clear_memory(self) -> None:
        from core.models import RiskLevel, ToolRequest

        result = self._jarvis.tools.execute(ToolRequest(name="clear_memory", risk=RiskLevel.HIGH))
        self._bus.emit(EventType.STATUS, {"message": result.message}, "settings")
