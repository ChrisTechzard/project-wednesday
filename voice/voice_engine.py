"""Orchestration of wake word, microphone capture, STT and TTS."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import sounddevice as sd

from core.config import ConfigManager
from core.events import EventBus
from core.logging import get_logger
from core.models import Event, EventType, Transcript

from voice.microphone import Microphone
from voice.stt import SpeechToText
from voice.tts import TextToSpeech
from voice.wakeword import WakeWordDetector


class VoiceEngine:
    """Runs wake-word monitoring and handles push-to-talk in background threads."""

    def __init__(self, config: ConfigManager, bus: EventBus, model_dir: Path) -> None:
        self._config = config
        self._bus = bus
        self._log = get_logger("voice")
        self._microphone = Microphone(config.config.voice)
        self._stt = SpeechToText(config.config.voice, model_dir / "whisper")
        self._tts = TextToSpeech(config.config.voice, model_dir, bus)
        self._wake = WakeWordDetector(config.config.voice, model_dir)
        self._frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=50)
        self._speech_queue: queue.Queue[str] = queue.Queue(maxsize=20)
        self._stream: sd.InputStream | None = None
        self._threads: list[threading.Thread] = []
        self._running = threading.Event()
        self._muted = False
        self._wake_enabled = config.config.voice.wake_word_enabled
        self._on_wake: Callable[[], None] | None = None
        self._busy = threading.Event()
        self._stop_listening = threading.Event()
        self._last_level = 0.0
        self._level_emit_time = 0.0

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def wake_enabled(self) -> bool:
        return self._wake_enabled

    @property
    def busy(self) -> bool:
        return self._busy.is_set()

    def set_on_wake(self, callback: Callable[[], None]) -> None:
        self._on_wake = callback

    def set_muted(self, muted: bool) -> None:
        """Mute or unmute the microphone."""
        self._muted = muted
        if muted:
            self._tts.stop_speaking()
        self._bus.emit(EventType.STATUS, {"muted": muted}, "voice")

    def set_wake_enabled(self, enabled: bool) -> None:
        """Enable or disable background wake-word monitoring."""
        self._wake_enabled = enabled
        if not enabled:
            self._wake.reset()
        self._bus.emit(EventType.STATUS, {"wake_word": enabled}, "voice")

    def start(self) -> None:
        """Start background speech and wake-word workers."""
        if self._running.is_set():
            return
        self._running.set()
        for name, target in (
            ("voice-wake", self._wake_loop),
            ("voice-speak", self._speak_loop),
        ):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)
        self._open_stream()
        self._log.info("Voice engine started")

    def stop(self) -> None:
        """Stop all voice workers and release the microphone."""
        self._running.clear()
        self._stop_listening.set()
        # Let workers leave the PortAudio callback path before closing the
        # stream. Killing them mid-callback can abort the process at exit.
        for thread in list(self._threads):
            if thread is not threading.current_thread() and thread.is_alive():
                thread.join(timeout=2.0)
        self._threads.clear()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except sd.PortAudioError:
                pass
            self._stream = None
        self._tts.stop_speaking()
        self._log.info("Voice engine stopped")

    @property
    def mic_level(self) -> float:
        """Most recent microphone RMS, normalised to 0..1."""
        return self._last_level

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if self._muted:
            self._last_level = 0.0
            return
        try:
            frame = np.array(indata[:, 0], dtype=np.int16, copy=True)
            self._frames.put_nowait(frame)
            rms = float(np.sqrt(np.mean(np.square(frame.astype(np.float32)))) / 32768.0)
            self._last_level = min(1.0, rms * 8.0)
            now = time.monotonic()
            if now - self._level_emit_time >= 0.1:
                self._level_emit_time = now
                self._bus.emit(EventType.STATUS, {"mic_level": round(self._last_level, 3)}, "voice")
        except queue.Full:
            pass

    def _open_stream(self) -> None:
        try:
            self._stream = self._microphone.stream(self._audio_callback)
            self._stream.start()
            self._log.info("Microphone stream opened")
        except Exception as exc:
            self._log.warning("Could not open microphone stream: %s", exc)

    def refresh_devices(self) -> None:
        """Reopen the microphone after a device setting change."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except sd.PortAudioError:
                pass
            self._stream = None
        if self._running.is_set():
            self._open_stream()

    def _wake_loop(self) -> None:
        while self._running.is_set():
            # Pause BEFORE consuming: listen_once() drains the same frame queue,
            # and a frame taken here while busy would be silently discarded.
            if self._busy.is_set() or not self._wake_enabled or self._muted:
                time.sleep(0.05)
                continue
            try:
                frame = self._frames.get(timeout=0.1)
            except queue.Empty:
                continue
            if self._busy.is_set() or not self._wake_enabled or self._muted:
                continue
            try:
                score = self._wake.predict(frame)
                if score > 0.05:
                    self._bus.emit(EventType.STATUS, {"wake_score": round(score, 3)}, "voice")
                if self._wake.is_triggered(score):
                    self._bus.emit(EventType.WAKE_WORD, {"word": self._config.config.voice.wake_word, "score": score}, "voice")
                    self._log.info("Wake word detected (score %.2f)", score)
                    self._wake.reset()
                    if self._on_wake is not None:
                        threading.Thread(target=self._on_wake, name="wake-action", daemon=True).start()
            except Exception as exc:
                self._log.warning("Wake-word processing error: %s", exc)

    def stop_listening(self) -> None:
        """Ask an in-flight listen_once() to finish early (Stop button)."""
        self._stop_listening.set()
        self._bus.emit(EventType.STATUS, {"listening": False}, "voice")

    @property
    def is_listening(self) -> bool:
        return self._busy.is_set()

    def _collect_audio(self, duration: float) -> np.ndarray:
        """Collect from the already-open mic stream; stoppable, no second stream.

        Opening a second sounddevice/PortAudio stream with sd.rec() while the
        wake-word InputStream is live deadlocks PipeWire and freezes the UI.
        The continuous stream already feeds ``_frames``, so we simply drain it.
        """
        self._stop_listening.clear()
        deadline = time.monotonic() + max(0.1, duration)
        chunks: list[np.ndarray] = []
        while time.monotonic() < deadline and not self._stop_listening.is_set():
            try:
                chunks.append(self._frames.get(timeout=0.05))
            except queue.Empty:
                continue
        if not chunks:
            return np.empty(0, dtype=np.float32)
        # Stream frames are int16; faster-whisper expects float32 in [-1, 1].
        return np.concatenate(chunks).astype(np.float32) / 32768.0

    def listen_once(self, seconds: float | None = None) -> Transcript:
        """Record one phrase from the live stream and transcribe it offline."""
        if self._muted:
            return Transcript(text="", source="muted")
        if self._busy.is_set():
            return Transcript(text="", source="busy")
        duration = seconds or self._config.config.voice.phrase_time_limit
        self._busy.set()
        self._bus.emit(EventType.STATUS, {"listening": True}, "voice")
        try:
            audio = self._collect_audio(duration)
            if self._stop_listening.is_set() and audio.size == 0:
                return Transcript(text="", source="cancelled")
            transcript = self._stt.transcribe(audio)
            self._bus.publish(
                Event(
                    type=EventType.TRANSCRIPT,
                    payload={"text": transcript.text, "source": transcript.source},
                    source="voice",
                )
            )
            return transcript
        except Exception as exc:
            self._log.warning("Listening failed: %s", exc)
            self._bus.emit(EventType.ERROR, {"message": f"Microphone error: {exc}"}, "voice")
            return Transcript(text="", source="error")
        finally:
            self._busy.clear()
            self._stop_listening.clear()
            self._bus.emit(EventType.STATUS, {"listening": False}, "voice")

    def say(self, text: str) -> None:
        """Queue a spoken response (non-blocking)."""
        if text.strip():
            self._speech_queue.put(text)

    def speak_now(self, text: str) -> bool:
        """Speak immediately and return whether playback succeeded."""
        return self._tts.speak(text)

    def _speak_loop(self) -> None:
        while self._running.is_set():
            try:
                text = self._speech_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if self._muted:
                continue
            try:
                self._tts.speak(text)
            except Exception as exc:
                self._log.warning("Speech playback error: %s", exc)

    def stop_speaking(self) -> None:
        self._tts.stop_speaking()

    def list_microphones(self) -> list[str]:
        return [device.label for device in self._microphone.list_devices()]
