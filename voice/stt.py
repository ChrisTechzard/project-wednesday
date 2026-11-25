"""Offline speech recognition with faster-whisper (CTranslate2, CPU int8)."""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from core.config import VoiceConfig
from core.logging import get_logger
from core.models import Transcript

from voice.microphone import Microphone


class SpeechToText:
    """Lazy-loading wrapper around faster-whisper."""

    def __init__(self, config: VoiceConfig, model_dir: Path) -> None:
        self._config = config
        self._model_dir = model_dir
        self._model: Any | None = None
        self._lock = threading.RLock()
        self._log = get_logger("stt")

    def _load(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from faster_whisper import WhisperModel

                    self._model_dir.mkdir(parents=True, exist_ok=True)
                    self._log.info("Loading STT model %s (first run may download weights)", self._config.stt_model)
                    self._model = WhisperModel(
                        self._config.stt_model,
                        device=self._config.stt_device,
                        compute_type="int8",
                        cpu_threads=self._config.stt_threads,
                        download_root=str(self._model_dir),
                    )
        return self._model

    def transcribe(self, audio: np.ndarray) -> Transcript:
        """Transcribe a float32 mono 16 kHz numpy array."""
        if audio.size == 0 or Microphone.rms(audio) < 0.005:
            return Transcript(text="", confidence=0.0, duration_seconds=len(audio) / 16000)
        try:
            segments, info = self._load().transcribe(
                audio,
                beam_size=1,
                language="en",
                vad_filter=True,
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
            confidence = float(getattr(info, "avg_logprob", 0.0))
            return Transcript(text=text, confidence=confidence, duration_seconds=len(audio) / 16000)
        except Exception as exc:
            self._log.exception("Speech recognition failed: %s", exc)
            return Transcript(text="", confidence=0.0, duration_seconds=len(audio) / 16000)

    def transcribe_file(self, path: Path) -> Transcript:
        """Transcribe a WAV file via soundfile."""
        import soundfile as sf

        audio, sample_rate = sf.read(str(path), dtype="float32")
        if sample_rate != 16000:
            target_length = int(len(audio) * 16000 / sample_rate)
            indices = np.linspace(0, len(audio) - 1, target_length)
            audio = np.interp(indices, np.arange(len(audio)), audio)
        return self.transcribe(np.asarray(audio, dtype=np.float32))
