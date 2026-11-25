"""Regression tests for cancellable mic recording and the STOP button."""

from __future__ import annotations

import threading
import time

import numpy as np

from app.jarvis import Jarvis
from core.models import Transcript
from voice.voice_engine import VoiceEngine


def _engine(config, bus) -> VoiceEngine:
    return VoiceEngine(config, bus, config.root if hasattr(config, "root") else config.path.parent)


def test_collect_audio_stops_early(config, bus) -> None:
    engine = _engine(config, bus)
    # Pretend the microphone stream is already delivering 80 ms int16 frames.
    frame = np.full(1280, 1000, dtype=np.int16)

    def feed() -> None:
        for _ in range(200):
            engine._frames.put(frame)
            time.sleep(0.01)

    threading.Thread(target=feed, daemon=True).start()
    engine._busy.set()
    threading.Timer(0.2, engine.stop_listening).start()

    started = time.monotonic()
    audio = engine._collect_audio(duration=10.0)
    elapsed = time.monotonic() - started

    assert elapsed < 2.0
    assert audio.size > 0
    assert audio.dtype == np.float32
    assert float(np.max(np.abs(audio))) <= 1.0


def test_listen_once_reports_cancelled(config, bus) -> None:
    engine = _engine(config, bus)
    engine._stt.transcribe = lambda audio: Transcript(text="should not happen")  # type: ignore[method-assign]
    threading.Timer(0.1, engine.stop_listening).start()
    transcript = engine.listen_once(seconds=10)
    assert transcript.source == "cancelled"
    assert transcript.is_empty
    assert not engine.busy


def test_stop_all_discards_in_flight_reply(monkeypatch) -> None:
    jarvis = Jarvis()
    real_respond = jarvis.brain.respond

    def slow_respond(text: str) -> str:
        time.sleep(0.3)
        return real_respond(text)

    monkeypatch.setattr(jarvis.brain, "respond", slow_respond)
    result: list[str] = []
    thread = threading.Thread(
        target=lambda: result.append(jarvis.process_text("what time is it", speak=False)),
        daemon=True,
    )
    thread.start()
    time.sleep(0.05)
    jarvis.stop_all()
    thread.join(timeout=5)
    assert result == [""]
