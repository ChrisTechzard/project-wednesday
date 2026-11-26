"""Pure helper tests for the settings form and transcript."""

from __future__ import annotations

from datetime import datetime

from ui.formatting import USER_SPEAKER, format_transcript_line, welcome_line
from ui.validation import validate_settings_values
from ui.widgets import raise_panel


class FakePanel:
    def __init__(self) -> None:
        self.raised_by = ""

    def lift(self) -> None:
        self.raised_by = "lift"

    def tkraise(self) -> None:
        self.raised_by = "tkraise"


def test_validation_accepts_a_known_good_form() -> None:
    raw = {
        "ai": {"model": "llama3.2:latest", "ollama_host": "http://127.0.0.1:11434"},
        "voice": {"tts_speed": "1.0", "tts_volume": "0.8", "wake_word_threshold": "0.5", "stt_model": "tiny.en"},
        "vision": {"cursor_sensitivity": "1.0", "dwell_time_ms": "900"},
        "general": {"theme": "dark"},
    }
    assert validate_settings_values(raw) == {}


def test_validation_points_at_each_bad_field() -> None:
    raw = {
        "ai": {"model": "  ", "ollama_host": "localhost:11434"},
        "voice": {"tts_speed": "4", "tts_volume": "abc", "wake_word_threshold": "0.05"},
        "vision": {"cursor_sensitivity": "9", "dwell_time_ms": "900.5"},
        "general": {"theme": "solarized"},
    }
    errors = validate_settings_values(raw)
    assert errors["ai.model"] == "Model cannot be empty."
    assert errors["ai.ollama_host"].startswith("Ollama host must start")
    assert "0.5 and 2" in errors["voice.tts_speed"]
    assert errors["voice.tts_volume"] == "Volume must be a number."
    assert "vision.dwell_time_ms" in errors
    assert errors["general.theme"] == "Theme must be one of: dark, light."


def test_transcript_line_uses_time_and_speaker_tag() -> None:
    stamp = datetime(2026, 11, 26, 14, 5)
    line, tag = format_transcript_line(USER_SPEAKER, "hello", stamp)
    assert line == "[14:05] You: hello\n\n"
    assert tag == "user"

    line, tag = format_transcript_line("Wednesday", "hi", stamp)
    assert line == "[14:05] Wednesday: hi\n\n"
    assert tag == "assistant"


def test_welcome_line_is_styled_as_system_text() -> None:
    line = welcome_line(datetime(2026, 11, 26, 9, 30))
    assert line.startswith("[09:30] Wednesday:")


def test_raise_panel_uses_lift_so_scrollable_settings_stays_visible() -> None:
    panel = FakePanel()
    raise_panel(panel)
    assert panel.raised_by == "lift"
