"""Webcam gaze calibration mapping normalised iris position to screen coordinates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from core.logging import get_logger


class GazeCalibrator:
    """Polynomial calibration with graceful fallback to linear mapping."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._samples: list[tuple[float, float, float, float]] = []
        self._coefficients: dict[str, Any] = {}
        self._log = get_logger("gaze")

    @property
    def calibrated(self) -> bool:
        return bool(self._coefficients)

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    def add_sample(self, iris_x: float, iris_y: float, screen_x: float, screen_y: float) -> None:
        """Record one calibration point in normalised screen coordinates."""
        self._samples.append((float(iris_x), float(iris_y), float(screen_x), float(screen_y)))

    def compute(self) -> bool:
        """Fit per-axis polynomial mappings. Returns True on success."""
        if len(self._samples) < 4:
            return False
        data = np.array(self._samples, dtype=np.float64)
        iris_x, iris_y, screen_x, screen_y = data.T
        features = self._features(iris_x, iris_y)
        try:
            if features.shape[0] >= features.shape[1] + 1:
                cx, *_ = np.linalg.lstsq(features, screen_x, rcond=None)
                cy, *_ = np.linalg.lstsq(features, screen_y, rcond=None)
            else:
                cx, *_ = np.linalg.lstsq(self._linear(iris_x, iris_y), screen_x, rcond=None)
                cy, *_ = np.linalg.lstsq(self._linear(iris_x, iris_y), screen_y, rcond=None)
            self._coefficients = {"x": cx.tolist(), "y": cy.tolist()}
            self.save()
            self._log.info("Gaze calibration fitted with %d samples", len(self._samples))
            return True
        except np.linalg.LinAlgError as exc:
            self._log.warning("Calibration fit failed: %s", exc)
            return False

    @staticmethod
    def _linear(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return np.column_stack([np.ones_like(x), x, y])

    @staticmethod
    def _features(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return np.column_stack(
            [
                np.ones_like(x),
                x,
                y,
                x * x,
                y * y,
                x * y,
                np.abs(x - 0.5),
                np.abs(y - 0.5),
            ]
        )

    def map(self, iris_x: float, iris_y: float) -> tuple[float, float]:
        """Map iris coordinates to normalised screen coordinates."""
        if not self._coefficients:
            return float(np.clip(iris_x, 0, 1)), float(np.clip(iris_y, 0, 1))
        features = np.array(self._features(np.array([iris_x]), np.array([iris_y]))[0], dtype=np.float64)
        cx = np.array(self._coefficients["x"], dtype=np.float64)
        cy = np.array(self._coefficients["y"], dtype=np.float64)
        if features.shape[0] != cx.shape[0]:
            features = np.array(self._linear(np.array([iris_x]), np.array([iris_y]))[0])
        x = float(np.dot(features, cx))
        y = float(np.dot(features, cy))
        return float(np.clip(x, 0, 1)), float(np.clip(y, 0, 1))

    def begin(self) -> None:
        """Start collecting a new sample set without losing the saved fit."""
        self._samples.clear()

    def cancel(self) -> None:
        """Abandon the current samples but keep the last successful fit."""
        self._samples.clear()

    def reset(self) -> None:
        """Remove both the samples and any saved calibration."""
        self._samples.clear()
        self._coefficients.clear()
        self._path.unlink(missing_ok=True)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"coefficients": self._coefficients, "samples": self._samples}, indent=2),
            encoding="utf-8",
        )

    def load(self) -> bool:
        if not self._path.exists():
            return False
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._coefficients = data.get("coefficients", {})
            self._samples = [tuple(item) for item in data.get("samples", [])]
            return self.calibrated
        except (OSError, ValueError, TypeError) as exc:
            self._log.warning("Could not load calibration: %s", exc)
            return False
