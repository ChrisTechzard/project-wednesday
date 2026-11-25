"""Offline text-to-speech using Piper, played through PipeWire/PulseAudio."""

from __future__ import annotations

import io
import shutil
import subprocess
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from core.config import VoiceConfig
from core.events import EventBus
from core.logging import get_logger
from core.models import EventType


class TextToSpeech:
    """Speak text with a local Piper voice and support immediate cancellation."""

    def __init__(self, config: VoiceConfig, model_dir: Path, bus: EventBus) -> None:
        self._config = config
        self._model_dir = model_dir
        self._bus = bus
        self._voice: Any | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._log = get_logger("tts")

    @property
    def model_path(self) -> Path:
        return self._model_dir / f"{self._config.tts_voice}.onnx"

    @property
    def available(self) -> bool:
        return self.model_path.exists()

    def _load(self) -> Any:
        if self._voice is None:
            from piper import PiperVoice

            config_path = self.model_path.with_suffix(".onnx.json")
            self._voice = PiperVoice.load(
                str(self.model_path),
                config_path=str(config_path) if config_path.exists() else None,
            )
        return self._voice

    def stop_speaking(self) -> None:
        """Signal playback to stop at the next boundary."""
        self._stop.set()
        try:
            sd.stop()
        except sd.PortAudioError:
            pass
        self._bus.emit(EventType.SPEAKING, {"active": False}, "tts")

    def synthesize(self, text: str) -> bytes | None:
        """Return WAV bytes for the supplied text, or None on failure."""
        import wave

        from piper.config import SynthesisConfig

        text = text.strip()
        if not text or not self.available:
            return None
        try:
            buffer = io.BytesIO()
            config = SynthesisConfig(
                length_scale=1.0 / max(0.5, self._config.tts_speed),
                volume=max(0.0, min(1.0, self._config.tts_volume)),
            )
            with wave.open(buffer, "wb") as wav_file:
                self._load().synthesize_wav(text, wav_file, syn_config=config)
            return buffer.getvalue()
        except Exception as exc:
            self._log.warning("Piper synthesis failed: %s", exc)
            return self._cli_synthesize(text)

    def _cli_synthesize(self, text: str) -> bytes | None:
        binary = shutil.which("piper")
        if binary is None:
            return None
        try:
            result = subprocess.run(
                [binary, "--model", str(self.model_path), "--output_file", "/dev/stdout"],
                input=text,
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
            )
            return result.stdout if result.returncode == 0 and len(result.stdout) > 44 else None
        except (OSError, subprocess.SubprocessError) as exc:
            self._log.warning("Piper CLI failed: %s", exc)
            return None

    def speak(self, text: str) -> bool:
        """Synthesize and play a response. Returns True only on successful playback."""
        if not self._config.tts_enabled:
            return False
        self._stop.clear()
        with self._lock:
            wav = self.synthesize(text)
            if not wav:
                self._log.warning("No speech audio was produced")
                return False
            try:
                audio, sample_rate = sf.read(io.BytesIO(wav), dtype="float32")
                self._bus.emit(EventType.SPEAKING, {"active": True, "text": text}, "tts")
                sd.play(np.asarray(audio, dtype=np.float32), samplerate=sample_rate)
                sd.wait()
            except Exception as exc:
                self._log.warning("Audio playback failed: %s", exc)
                return False
            finally:
                self._bus.emit(EventType.SPEAKING, {"active": False}, "tts")
            return not self._stop.is_set()
