"""Optional live integration tests.

These are skipped unless JARVIS_LIVE_TESTS=1 so the default suite stays fast
and hardware-independent. Run with:
    JARVIS_LIVE_TESTS=1 .venv/bin/python -m pytest tests/test_integration_live.py -v
"""

from __future__ import annotations

import os

import pytest

LIVE = os.environ.get("JARVIS_LIVE_TESTS", "0") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="set JARVIS_LIVE_TESTS=1 for hardware tests")


def test_ollama_chat() -> None:
    from app.jarvis import Jarvis

    app = Jarvis()
    assert app.ollama.is_available()
    assert "llama3.2" in " ".join(app.ollama.list_models())
    reply = app.brain.respond("What is 2 plus 2?")
    assert reply.strip()


def test_wakeword_models_infer() -> None:
    from pathlib import Path

    import numpy as np

    from core.config import VoiceConfig
    from voice.wakeword import WakeWordDetector

    detector = WakeWordDetector(VoiceConfig(), Path(__file__).resolve().parent.parent / "models")
    assert detector.load() is True
    scores = [detector.predict(np.zeros(1280, dtype=np.int16)) for _ in range(20)]
    assert max(scores) < 0.5  # silence must not trigger


def test_piper_synthesis() -> None:
    from pathlib import Path

    from core.config import VoiceConfig
    from core.events import EventBus
    from voice.tts import TextToSpeech

    tts = TextToSpeech(VoiceConfig(), Path(__file__).resolve().parent.parent / "models", EventBus())
    wav = tts.synthesize("This is a test.")
    assert wav is not None and len(wav) > 1000


def test_camera_frame() -> None:
    from vision.camera import Camera

    camera = Camera()
    assert camera.open(0) is True
    try:
        frame = camera.read()
        assert frame is not None and frame.shape[0] > 100
    finally:
        camera.close()
