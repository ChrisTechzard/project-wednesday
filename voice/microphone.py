"""Microphone discovery and blocking audio capture via sounddevice."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import numpy as np
import sounddevice as sd

from core.config import VoiceConfig
from core.logging import get_logger


@dataclass(frozen=True, slots=True)
class AudioDevice:
    """A discovered input device."""

    index: int
    name: str
    channels: int
    sample_rate: float

    @property
    def label(self) -> str:
        return f"{self.index}: {self.name}"


class Microphone:
    """Provide device discovery and short recordings at 16 kHz mono."""

    def __init__(self, config: VoiceConfig) -> None:
        self._config = config
        self._log = get_logger("microphone")
        self._lock = threading.RLock()

    def list_devices(self) -> list[AudioDevice]:
        """Return all available audio input devices."""
        result: list[AudioDevice] = []
        try:
            devices: list[dict[str, Any]] = sd.query_devices()
            for index, device in enumerate(devices):
                if int(device.get("max_input_channels", 0)) > 0:
                    result.append(
                        AudioDevice(
                            index=index,
                            name=str(device.get("name", f"device {index}")),
                            channels=int(device["max_input_channels"]),
                            sample_rate=float(device.get("default_samplerate", 16000)),
                        )
                    )
        except sd.PortAudioError as exc:
            self._log.warning("Could not query audio devices: %s", exc)
        return result

    def resolve_device(self) -> int | None:
        """Return the configured device index or the system default."""
        configured = self._config.microphone_name.strip()
        devices = self.list_devices()
        if configured:
            for device in devices:
                if configured == device.name or configured == device.label or configured == str(device.index):
                    return device.index
            self._log.warning("Configured microphone '%s' not found; using default", configured)
        try:
            default = sd.query_devices(kind="input")
            for device in devices:
                if device.name == default.get("name"):
                    return device.index
        except (sd.PortAudioError, KeyError, TypeError):
            pass
        return devices[0].index if devices else None

    def record(self, seconds: float, device: int | None = None) -> np.ndarray:
        """Record mono 16-bit float audio and return a flat numpy array."""
        with self._lock:
            selected = device if device is not None else self.resolve_device()
            frames = int(max(0.1, seconds) * self._config.sample_rate)
            recording = sd.rec(
                frames,
                samplerate=self._config.sample_rate,
                channels=1,
                dtype="float32",
                device=selected,
            )
            sd.wait()
            return np.asarray(recording, dtype=np.float32).flatten()

    @staticmethod
    def rms(audio: np.ndarray) -> float:
        """Return the root-mean-square amplitude of an audio buffer."""
        if audio.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio, dtype=np.float32))))

    def stream(self, callback: Any, blocksize: int = 1280) -> Any:
        """Open a continuous input stream; caller is responsible for closing it."""
        return sd.InputStream(
            samplerate=self._config.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=blocksize,
            device=self.resolve_device(),
            callback=callback,
        )
