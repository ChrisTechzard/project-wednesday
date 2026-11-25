"""Webcam discovery and release-safe capture."""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np

from core.logging import get_logger


class Camera:
    """Thin wrapper around OpenCV's VideoCapture."""

    def __init__(self) -> None:
        self._log = get_logger("camera")
        self._capture: Any | None = None
        self._index: int | None = None

    @staticmethod
    def list_cameras(max_index: int = 6) -> list[int]:
        """Probe camera indices and return those that open successfully."""
        available: list[int] = []
        for index in range(max_index):
            capture = cv2.VideoCapture(index)
            if capture.isOpened():
                available.append(index)
            capture.release()
        return available

    def open(self, index: int, width: int = 640, height: int = 480, fps: int = 15) -> bool:
        """Open a camera with conservative settings for low CPU load."""
        self.close()
        # Webcam devices can briefly report busy while desktop services probe
        # them at startup. Retry a few times before giving up.
        capture: Any | None = None
        for attempt in range(3):
            candidate = cv2.VideoCapture(index)
            if candidate.isOpened():
                capture = candidate
                break
            candidate.release()
            if attempt < 2:
                time.sleep(0.5)
        if capture is None:
            self._log.warning("Camera %s could not be opened after 3 attempts", index)
            return False
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        capture.set(cv2.CAP_PROP_FPS, fps)
        self._capture = capture
        self._index = index
        self._log.info("Camera %s opened", index)
        return True

    def read(self) -> np.ndarray | None:
        """Return the next BGR frame, or None on failure."""
        if self._capture is None or not self._capture.isOpened():
            return None
        ok, frame = self._capture.read()
        return frame if ok else None

    def close(self) -> None:
        """Release the camera device."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None
            self._index = None
            self._log.info("Camera released")

    @property
    def is_open(self) -> bool:
        return self._capture is not None and self._capture.isOpened()
