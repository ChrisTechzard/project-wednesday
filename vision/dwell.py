"""Dwell selection controller with stable-target and cooldown handling."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DwellState:
    """Dwell progress for the UI."""

    progress: float
    target_x: float
    target_y: float
    selected: bool


class DwellController:
    """Fire a selection only after steady gaze for the configured duration."""

    def __init__(self, dwell_seconds: float = 0.9, radius_px: float = 60.0) -> None:
        self._dwell_seconds = max(0.3, dwell_seconds)
        self._radius = radius_px
        self._start = 0.0
        self._target = (0.0, 0.0)
        self._last_selection = 0.0

    def configure(self, dwell_seconds: float) -> None:
        self._dwell_seconds = max(0.3, dwell_seconds)

    def update(self, x: float, y: float, present: bool = True) -> DwellState:
        """Update with current cursor position in pixels."""
        now = time.monotonic()
        if not present:
            self._start = 0.0
            return DwellState(0.0, x, y, False)

        if self._start == 0.0:
            self._start = now
            self._target = (x, y)
            return DwellState(0.0, x, y, False)

        distance = ((x - self._target[0]) ** 2 + (y - self._target[1]) ** 2) ** 0.5
        if distance > self._radius:
            self._start = now
            self._target = (x, y)
            return DwellState(0.0, x, y, False)

        elapsed = now - self._start
        progress = min(1.0, elapsed / self._dwell_seconds)
        selected = False
        if progress >= 1.0 and now - self._last_selection > self._dwell_seconds + 0.5:
            selected = True
            self._last_selection = now
            self._start = now
        return DwellState(progress, x, y, selected)
