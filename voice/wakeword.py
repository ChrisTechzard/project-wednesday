"""Offline 'hey jarvis' wake-word detection using openWakeWord ONNX models.

Feature extraction follows the openWakeWord design (Apache-2.0, David Scripka):
mel-spectrogram -> Google speech embedding -> small classification model.
Models are CC BY-NC-SA 4.0 and are kept locally in the project's models/ directory.

Only the ONNX feature models are used, avoiding the tflite-runtime dependency
that has no Python 3.12 wheel. The code below is a focused port of the
streaming feature pipeline from openwakeword.utils.AudioFeatures.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

from core.config import VoiceConfig
from core.logging import get_logger

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1280  # 80 ms
FEATURE_FRAMES = 16   # model input length
MAX_MEL_FRAMES = 10 * 97


class WakeWordDetector:
    """Streaming detector that scores 80 ms int16 PCM frames."""

    def __init__(self, config: VoiceConfig, model_dir: Path) -> None:
        self._config = config
        self._dir = model_dir
        self._log = get_logger("wakeword")
        self._lock = threading.RLock()
        self._sessions: dict[str, Any] = {}
        self._n_features = FEATURE_FRAMES
        self._scores: deque[float] = deque(maxlen=30)
        self._frames_seen = 0
        self._last_trigger = 0.0
        self._ready = False
        self._raw_buffer: deque[int] = deque(maxlen=SAMPLE_RATE * 10)
        self._mel_buffer = np.ones((76, 32), dtype=np.float32)
        self._feature_buffer = np.zeros((120, 96), dtype=np.float32)
        self._accumulated = 0
        self._remainder = np.empty(0, dtype=np.int16)

    @property
    def available(self) -> bool:
        required = ["melspectrogram.onnx", "embedding_model.onnx", "hey_jarvis_v0.1.onnx"]
        return all((self._dir / name).exists() for name in required)

    def load(self) -> bool:
        """Lazily initialise ONNX sessions. Returns False if models are missing."""
        if self._ready:
            return True
        if not self.available:
            self._log.warning("Wake-word models are missing from %s", self._dir)
            return False
        with self._lock:
            import onnxruntime as ort

            options = ort.SessionOptions()
            options.inter_op_num_threads = 1
            options.intra_op_num_threads = 1
            for key, filename in (
                ("mel", "melspectrogram.onnx"),
                ("embed", "embedding_model.onnx"),
                ("wake", "hey_jarvis_v0.1.onnx"),
            ):
                self._sessions[key] = ort.InferenceSession(
                    str(self._dir / filename),
                    sess_options=options,
                    providers=["CPUExecutionProvider"],
                )
            self._n_features = int(self._sessions["wake"].get_inputs()[0].shape[1])
            self.reset()
            self._ready = True
            self._log.info("Wake-word detector loaded (%s)", self._config.wake_word)
            return True

    def reset(self) -> None:
        """Clear streaming buffers and seed the feature history like openWakeWord."""
        self._raw_buffer.clear()
        self._mel_buffer = np.ones((76, 32), dtype=np.float32)
        self._accumulated = 0
        self._remainder = np.empty(0, dtype=np.int16)
        self._scores.clear()
        self._frames_seen = 0
        rng = np.random.default_rng()
        self._feature_buffer = self._embeddings(
            rng.integers(-1000, 1000, SAMPLE_RATE * 4, dtype=np.int16)
        )

    # ---- feature extraction ------------------------------------------

    def _mel(self, samples: np.ndarray) -> np.ndarray:
        """Compute a transformed mel-spectrogram for int16 audio samples."""
        output = self._sessions["mel"].run(None, {"input": samples.astype(np.float32)[None, :]})[0]
        spec = np.squeeze(output) / 10.0 + 2.0
        return spec

    def _embeddings(self, samples: np.ndarray) -> np.ndarray:
        """Compute speech embeddings for a full audio buffer -> (N, 96)."""
        spec = self._mel(np.asarray(samples, dtype=np.int16))
        if spec.ndim == 1:
            spec = spec[None, :]
        windows = [
            spec[i : i + 76].astype(np.float32)[None, :, :, None]
            for i in range(0, spec.shape[0], 8)
            if spec[i : i + 76].shape[0] == 76
        ]
        if not windows:
            return self._feature_buffer[-120:, :]
        batch = np.concatenate(windows, axis=0)
        return np.squeeze(self._sessions["embed"].run(None, {"input_1": batch})[0])

    def _features(self, n_frames: int) -> np.ndarray:
        """Return the most recent feature frames shaped (1, n_frames, 96)."""
        return self._feature_buffer[-n_frames:, :][None, :, :].astype(np.float32)

    def _streaming_features(self, frame: np.ndarray) -> int:
        """Buffer audio and update features; return number of processed samples."""
        if self._remainder.size:
            frame = np.concatenate((self._remainder, frame))
            self._remainder = np.empty(0, dtype=np.int16)

        if self._accumulated + frame.size >= CHUNK_SAMPLES:
            remainder = (self._accumulated + frame.size) % CHUNK_SAMPLES
            if remainder:
                self._raw_buffer.extend(frame[:-remainder].tolist())
                self._accumulated += frame.size - remainder
                self._remainder = frame[-remainder:]
            else:
                self._raw_buffer.extend(frame.tolist())
                self._accumulated += frame.size
        else:
            self._accumulated += frame.size
            self._raw_buffer.extend(frame.tolist())

        processed = 0
        if self._accumulated >= CHUNK_SAMPLES and self._accumulated % CHUNK_SAMPLES == 0:
            n = self._accumulated
            context = list(self._raw_buffer)[-n - CHUNK_SAMPLES * 3 :]
            self._mel_buffer = np.vstack((self._mel_buffer, self._mel(np.array(context, dtype=np.int16))))
            if self._mel_buffer.shape[0] > MAX_MEL_FRAMES:
                self._mel_buffer = self._mel_buffer[-MAX_MEL_FRAMES:, :]

            for i in range(n // CHUNK_SAMPLES - 1, -1, -1):
                ndx = -8 * i
                ndx = ndx if ndx != 0 else len(self._mel_buffer)
                window = self._mel_buffer[-76 + ndx : ndx].astype(np.float32)[None, :, :, None]
                if window.shape[1] == 76:
                    self._feature_buffer = np.vstack(
                        (self._feature_buffer, np.squeeze(self._sessions["embed"].run(None, {"input_1": window})[0]))
                    )
            self._feature_buffer = self._feature_buffer[-120:, :]
            processed = n
            self._accumulated = 0
        return processed

    # ---- public prediction -------------------------------------------

    def predict(self, frame_16k_int16: np.ndarray) -> float:
        """Feed one audio frame and return the wake-word score in [0, 1]."""
        if not self._ready and not self.load():
            return 0.0
        with self._lock:
            processed = self._streaming_features(np.asarray(frame_16k_int16, dtype=np.int16).flatten())
            session = self._sessions["wake"]
            if processed == CHUNK_SAMPLES:
                score = float(session.run(None, {"x.1": self._features(self._n_features)})[0][0][0])
            elif processed > CHUNK_SAMPLES:
                predictions = [
                    float(session.run(None, {"x.1": self._features(self._n_features)})[0][0][0])
                    for _ in range(processed // CHUNK_SAMPLES)
                ]
                score = max(predictions) if predictions else 0.0
            elif self._scores:
                score = self._scores[-1]
            else:
                score = 0.0

            self._frames_seen += 1
            if self._frames_seen < 5:  # model warm-up, as in openWakeWord
                score = 0.0
            self._scores.append(score)
            return score

    def is_triggered(self, score: float) -> bool:
        """Apply threshold, patience and cooldown to avoid false triggers."""
        now = time.monotonic()
        threshold = self._config.wake_word_threshold
        if score < threshold or now - self._last_trigger < 3.0:
            return False
        recent = list(self._scores)[-3:]
        if len(recent) >= 2 and sum(value >= threshold for value in recent) >= 2:
            self._last_trigger = now
            return True
        return False
