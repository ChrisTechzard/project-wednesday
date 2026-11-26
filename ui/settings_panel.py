"""Settings panel for every configurable Wednesday subsystem."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import customtkinter as ctk
from pydantic import ValidationError

from core.events import EventBus
from core.models import EventType

from ui.validation import validate_settings_values
from ui.widgets import ACCENT, BORDER, BG, DANGER, MUTED, SUCCESS, WARNING, action_button, bind_focus_ring, danger_button, label, panel


@dataclass(slots=True)
class FieldRow:
    """Controls that make up one labelled settings field."""

    title: ctk.CTkLabel
    control: ctk.CTkBaseClass
    error: ctk.CTkLabel


class SettingsFrame(ctk.CTkScrollableFrame):
    """Editable settings with inline validation and explicit save/reset."""

    def __init__(self, parent: ctk.CTkBaseClass, jarvis: Any, bus: EventBus) -> None:
        super().__init__(parent, fg_color=BG)
        self._jarvis = jarvis
        self._bus = bus
        self._vars: dict[str, Any] = {}
        self._field_keys: dict[int, str] = {}
        self._field_rows: dict[str, FieldRow] = {}
        self._form_status: ctk.CTkLabel | None = None
        self._build()

    def _field_changed(self, key: str) -> None:
        """Clear a field error as soon as the user edits that field."""
        row = self._field_rows.get(key)
        if row is not None:
            row.error.configure(text="")
            row.control.configure(border_width=1, border_color=BORDER)
        if self._form_status is not None:
            self._form_status.configure(text="Unsaved changes", text_color=WARNING)

    def _text_var(self, section: str, field: str, value: Any) -> ctk.StringVar:
        var = ctk.StringVar(value=str(value))
        key = f"{section}.{field}"
        self._vars[key] = var
        self._field_keys[id(var)] = key
        var.trace_add("write", lambda *_: self._field_changed(key))
        return var

    def _bool_var(self, section: str, field: str, value: Any) -> ctk.BooleanVar:
        var = ctk.BooleanVar(value=bool(value))
        key = f"{section}.{field}"
        self._vars[key] = var
        var.trace_add("write", lambda *_: self._field_changed(key))
        return var

    def _field(self, parent: ctk.CTkBaseClass, title: str, var: ctk.StringVar, width: int = 240) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.columnconfigure(0, weight=1)
        title_label = label(row, title, 12, text_color=MUTED)
        title_label.grid(row=0, column=0, sticky="w", pady=(0, 4))

        entry = ctk.CTkEntry(row, textvariable=var, width=width, height=34)
        entry.grid(row=0, column=1, sticky="e", pady=(0, 4))
        bind_focus_ring(entry)

        error = label(row, "", 11, text_color=DANGER, height=16)
        error.grid(row=1, column=0, columnspan=2, sticky="w")
        row.pack(fill="x", padx=16, pady=4)

        key = self._field_keys.get(id(var))
        if key is not None:
            self._field_rows[key] = FieldRow(title_label, entry, error)

    def _combo_field(
        self,
        parent: ctk.CTkBaseClass,
        title: str,
        var: ctk.StringVar,
        values: list[str],
        width: int = 240,
    ) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.columnconfigure(0, weight=1)
        title_label = label(row, title, 12, text_color=MUTED)
        title_label.grid(row=0, column=0, sticky="w", pady=(0, 4))

        combo = ctk.CTkComboBox(row, variable=var, values=values, width=width, height=34)
        combo.grid(row=0, column=1, sticky="e", pady=(0, 4))
        bind_focus_ring(combo)

        error = label(row, "", 11, text_color=DANGER, height=16)
        error.grid(row=1, column=0, columnspan=2, sticky="w")
        row.pack(fill="x", padx=16, pady=4)

        key = self._field_keys.get(id(var))
        if key is not None:
            self._field_rows[key] = FieldRow(title_label, combo, error)

    def _toggle(self, parent: ctk.CTkBaseClass, title: str, var: ctk.BooleanVar) -> None:
        checkbox = ctk.CTkCheckBox(
            parent,
            text=title,
            variable=var,
            height=36,
            checkbox_width=18,
            checkbox_height=18,
        )
        checkbox.pack(anchor="w", padx=16, pady=2)
        bind_focus_ring(checkbox)

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
        self._combo_field(voice, "Microphone", self._text_var("voice", "microphone_name", cfg.voice.microphone_name), [""] + mics, 260)
        self._field(voice, "Speech speed (0.5–2.0)", self._text_var("voice", "tts_speed", cfg.voice.tts_speed), 100)
        self._field(voice, "Volume (0.0–1.0)", self._text_var("voice", "tts_volume", cfg.voice.tts_volume), 100)
        self._field(voice, "STT model", self._text_var("voice", "stt_model", cfg.voice.stt_model))
        self._field(voice, "Wake threshold (0.1–0.95)", self._text_var("voice", "wake_word_threshold", cfg.voice.wake_word_threshold), 100)

        vision = panel(self)
        vision.pack(fill="x", padx=8, pady=6)
        label(vision, "VISION & TRACKING", 13, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(14, 6))
        self._toggle(vision, "Enable camera/vision engine at startup", self._bool_var("vision", "vision_enabled", cfg.vision.vision_enabled))
        self._toggle(vision, "Head cursor control", self._bool_var("vision", "head_control_enabled", cfg.vision.head_control_enabled))
        self._toggle(vision, "Gaze cursor control", self._bool_var("vision", "gaze_control_enabled", cfg.vision.gaze_control_enabled))
        self._toggle(vision, "Dwell selection", self._bool_var("vision", "dwell_enabled", cfg.vision.dwell_enabled))
        self._toggle(vision, "Blink click (experimental)", self._bool_var("vision", "blink_click_enabled", cfg.vision.blink_click_enabled))
        self._field(vision, "Dwell time (300–5000 ms)", self._text_var("vision", "dwell_time_ms", cfg.vision.dwell_time_ms), 100)
        self._field(vision, "Sensitivity (0.1–3.0)", self._text_var("vision", "cursor_sensitivity", cfg.vision.cursor_sensitivity), 100)

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
        self._combo_field(general, "Theme", self._text_var("general", "theme", cfg.general.theme), ["dark", "light"], 140)
        self._toggle(general, "Tray icon / background operation", self._bool_var("general", "tray_enabled", cfg.general.tray_enabled))
        self._toggle(general, "Start minimized", self._bool_var("general", "start_minimized", cfg.general.start_minimized))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=8, pady=18)
        action_button(actions, "SAVE SETTINGS", self.save, width=160).pack(side="left", padx=6)
        action_button(actions, "RESET DEFAULTS", self._reset, width=160).pack(side="left", padx=6)
        danger_button(actions, "CLEAR MEMORY", self._clear_memory, width=140).pack(side="left", padx=6)

        self._form_status = label(self, "Change a setting, then save when you're happy.", 12, text_color=MUTED)
        self._form_status.pack(anchor="w", padx=14, pady=(0, 18))

    def _clear_errors(self) -> None:
        for row in self._field_rows.values():
            row.error.configure(text="")
            row.control.configure(border_width=1, border_color=BORDER)

    def _show_errors(self, errors: dict[str, str]) -> None:
        for key, message in errors.items():
            row = self._field_rows.get(key)
            if row is not None:
                row.error.configure(text=message)
                row.control.configure(border_width=2, border_color=DANGER)
        if errors:
            first_row = self._field_rows.get(next(iter(errors)))
            if first_row is not None:
                first_row.control.focus_set()

    def save(self) -> None:
        """Validate, apply and persist the form."""
        from core.config import JarvisConfig

        raw: dict[str, dict[str, Any]] = {}
        for key, var in self._vars.items():
            section, field = key.split(".", 1)
            raw.setdefault(section, {})[field] = var.get()

        self._clear_errors()
        errors = validate_settings_values(raw)
        if errors:
            self._show_errors(errors)
            if self._form_status is not None:
                self._form_status.configure(text=f"Fix {len(errors)} field(s) before saving", text_color=DANGER)
            return

        try:
            validated = JarvisConfig.model_validate({**self._jarvis.config.to_dict(), **raw})
        except ValidationError as exc:
            field_errors: dict[str, str] = {}
            for detail in exc.errors():
                location = detail.get("loc", ())
                if len(location) >= 2:
                    field_errors[f"{location[0]}.{location[1]}"] = str(detail.get("msg", "Invalid value"))
            self._show_errors(field_errors)
            if self._form_status is not None:
                self._form_status.configure(text="Could not save — check the highlighted fields", text_color=DANGER)
            self._bus.emit(EventType.ERROR, {"message": "Settings were not saved"}, "settings")
            return

        for section in ("ai", "voice", "vision", "automation", "memory", "general"):
            self._jarvis.config.update(section, validated.model_dump()[section])
        self._jarvis.voice.refresh_devices()
        self._jarvis.voice.set_wake_enabled(validated.voice.wake_word_enabled)
        self._jarvis.memory.set_enabled(validated.memory.memory_enabled)
        if self._form_status is not None:
            self._form_status.configure(text="Saved", text_color=SUCCESS)
        self._jarvis.bus.emit(EventType.STATUS, {"settings_saved": True}, "settings")

    def _reset(self) -> None:
        self._jarvis.config.reset()
        cfg = self._jarvis.config.config
        for key, var in self._vars.items():
            section, field = key.split(".", 1)
            value = getattr(cfg, section).model_dump()[field]
            if isinstance(var, ctk.BooleanVar):
                var.set(bool(value))
            else:
                var.set(str(value))
        self._clear_errors()
        if self._form_status is not None:
            self._form_status.configure(text="Defaults restored — restart to apply everything", text_color=WARNING)
        self._bus.emit(EventType.STATUS, {"message": "Settings reset to defaults — restart to apply all."}, "settings")

    def _clear_memory(self) -> None:
        from core.models import RiskLevel, ToolRequest

        result = self._jarvis.tools.execute(ToolRequest(name="clear_memory", risk=RiskLevel.HIGH))
        self._bus.emit(EventType.STATUS, {"message": result.message}, "settings")
