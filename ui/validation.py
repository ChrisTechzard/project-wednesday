"""Small, dependency-free validation helpers for the settings form.

Pydantic still does the final validation when settings are saved. These checks
run first so the error can be shown next to the field that caused it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from urllib.parse import urlparse

FIELD_LABELS: Mapping[str, str] = {
    "ai.model": "Model",
    "ai.ollama_host": "Ollama host",
    "voice.microphone_name": "Microphone",
    "voice.stt_model": "STT model",
    "voice.tts_speed": "Speech speed",
    "voice.tts_volume": "Volume",
    "voice.wake_word_threshold": "Wake threshold",
    "vision.cursor_sensitivity": "Sensitivity",
    "vision.dwell_time_ms": "Dwell time",
    "general.theme": "Theme",
}

NUMERIC_RANGES: Mapping[str, tuple[float, float]] = {
    "voice.tts_speed": (0.5, 2.0),
    "voice.tts_volume": (0.0, 1.0),
    "voice.wake_word_threshold": (0.1, 0.95),
    "vision.cursor_sensitivity": (0.1, 3.0),
    "vision.dwell_time_ms": (300.0, 5000.0),
}

INTEGER_FIELDS = frozenset({"vision.dwell_time_ms"})
URL_FIELDS = frozenset({"ai.ollama_host"})
NONEMPTY_FIELDS = frozenset({"ai.model", "voice.stt_model"})
CHOICE_FIELDS: Mapping[str, tuple[str, ...]] = {
    "general.theme": ("dark", "light"),
}


def _format_number(value: float) -> str:
    return f"{value:g}"


def _validate_number(key: str, label: str, value: object) -> str:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return f"{label} must be a number."

    if not math.isfinite(number):
        return f"{label} must be a finite number."

    if key in INTEGER_FIELDS and not number.is_integer():
        return f"{label} must be a whole number."

    low, high = NUMERIC_RANGES[key]
    if number < low or number > high:
        return f"{label} must be between {_format_number(low)} and {_format_number(high)}."

    return ""


def _validate_url(label: str, value: object) -> str:
    text = str(value).strip()
    if not text.startswith(("http://", "https://")):
        return f"{label} must start with http:// or https://."
    if not urlparse(text).netloc:
        return f"{label} needs a host after the scheme."
    return ""


def _validate_choice(key: str, label: str, value: object) -> str:
    text = str(value).strip().lower()
    choices = CHOICE_FIELDS[key]
    if text not in choices:
        return f"{label} must be one of: {', '.join(choices)}."
    return ""


def validate_settings_values(raw: Mapping[str, Mapping[str, object]]) -> dict[str, str]:
    """Return field-keyed error messages for obviously invalid settings.

    Only fields shown in the Settings panel are checked. Anything not listed
    here is left to ``JarvisConfig.model_validate`` when the form is saved.
    """
    errors: dict[str, str] = {}

    for key, label in FIELD_LABELS.items():
        section, field = key.split(".", 1)
        section_values = raw.get(section)
        if section_values is None or field not in section_values:
            continue

        value = section_values[field]
        if key in NUMERIC_RANGES:
            error = _validate_number(key, label, value)
        elif key in URL_FIELDS:
            error = _validate_url(label, value)
        elif key in CHOICE_FIELDS:
            error = _validate_choice(key, label, value)
        elif key in NONEMPTY_FIELDS and not str(value).strip():
            error = f"{label} cannot be empty."
        else:
            error = ""

        if error:
            errors[key] = error

    return errors
