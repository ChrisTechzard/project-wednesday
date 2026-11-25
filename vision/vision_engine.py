"""Vision engine: camera loop, tracking, calibration and safe selection control."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from automation.input_control import InputController
from core.config import ConfigManager
from core.events import EventBus
from core.logging import get_logger
from core.models import Event, EventType, TrackingState
from core.portal import GLib, Gio

from vision.camera import Camera
from vision.dwell import DwellController
from vision.face_tracker import FaceTracker, FaceState
from vision.gaze import GazeCalibrator


def screen_size() -> tuple[int, int]:
    """Return the primary monitor resolution using GDK."""
    try:
        display = Gio.Settings.new("org.gnome.desktop.interface")  # ensures GI is initialised
        _ = display
        import gi

        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk

        monitor = Gdk.Display.get_default().get_monitor(0)
        geometry = monitor.get_geometry()
        return int(geometry.width), int(geometry.height)
    except Exception:
        return 1920, 1080


class VisionEngine:
    """Runs webcam tracking in a daemon thread and publishes state events."""

    def __init__(
        self,
        config: ConfigManager,
        bus: EventBus,
        input_control: InputController,
        model_dir: Path,
    ) -> None:
        self._config = config
        self._bus = bus
        self._input = input_control
        self._camera = Camera()
        self._tracker = FaceTracker()
        self._calibrator = GazeCalibrator(model_dir / "gaze-calibration.json")
        self._calibrator.load()
        self._dwell = DwellController(config.config.vision.dwell_time_ms / 1000)
        self._running = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._mode = "off"
        self._enabled = config.config.vision.vision_enabled
        self._last_state = TrackingState(calibrated=self._calibrator.calibrated)
        self._smoothed_x = 0.5
        self._smoothed_y = 0.5
        self._blink_prev = False
        self._last_blink = 0.0
        self._screen_size = screen_size()  # cache; the loop must not probe GDK every frame
        self._log = get_logger("vision")

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def calibrated(self) -> bool:
        return self._calibrator.calibrated

    @property
    def calibration_samples(self) -> int:
        return self._calibrator.sample_count

    @property
    def camera_open(self) -> bool:
        return self._camera.is_open

    def start(self) -> bool:
        """Open the camera and start the tracking loop."""
        if self._running.is_set():
            return True
        if not self._enabled:
            return False
        cfg = self._config.config.vision
        if not self._camera.open(cfg.camera_index, fps=cfg.target_fps):
            self._bus.emit(EventType.ERROR, {"message": "Webcam could not be opened."}, "vision")
            return False
        self._running.set()
        self._thread = threading.Thread(target=self._loop, name="vision-loop", daemon=True)
        self._thread.start()
        self._log.info("Vision engine started on camera %s", cfg.camera_index)
        return True

    def stop(self) -> None:
        """Stop tracking and release the camera."""
        self._running.clear()
        self._camera.close()
        self._log.info("Vision engine stopped")

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled:
            self.stop()
        elif not self._running.is_set():
            self.start()

    def set_mode(self, mode: str, enabled: bool = True) -> bool:
        """Enable or disable 'head', 'gaze' or 'off' cursor control."""
        mode = mode.lower()
        if mode not in {"head", "gaze", "off"}:
            return False
        if enabled and mode != "off":
            if not self._input.available and not self._input.initialize():
                self._log.warning("Cursor control unavailable: portal session not granted")
                return False
            if not self._running.is_set() and not self.start():
                return False
        self._mode = "off" if not enabled else mode
        self._bus.emit(EventType.STATUS, {"tracking_mode": self._mode}, "vision")
        return True

    def set_camera(self, index: int) -> bool:
        """Switch camera and reopen the capture."""
        was_running = self._running.is_set()
        self.stop()
        cfg = self._config.config.vision
        self._config.update("vision", {"camera_index": index})
        if was_running:
            return self.start()
        return self._camera.open(index, fps=cfg.target_fps)

    def start_calibration(self) -> None:
        """Clear calibration samples (the UI then guides the user through targets)."""
        self._calibrator.reset()
        self._bus.emit(EventType.STATUS, {"calibration_samples": 0}, "vision")

    def capture_calibration_point(self, screen_x: float, screen_y: float) -> bool:
        """Capture the current iris position for a known screen target."""
        state = self._last_state
        if not state.face_detected:
            return False
        self._calibrator.add_sample(state.gaze_x, state.gaze_y, screen_x, screen_y)
        self._bus.emit(EventType.STATUS, {"calibration_samples": self.calibration_samples}, "vision")
        return True

    def finish_calibration(self) -> bool:
        """Fit the calibration model."""
        ok = self._calibrator.compute()
        self._bus.emit(EventType.STATUS, {"calibrated": ok}, "vision")
        return ok

    def _loop(self) -> None:
        cfg = self._config.config.vision
        interval = 1.0 / max(1, cfg.target_fps)
        while self._running.is_set():
            started = time.monotonic()
            frame = self._camera.read()
            if frame is None:
                time.sleep(0.1)
                continue
            state = self._process_frame(frame)
            self._last_state = state
            self._bus.publish(
                Event(
                    type=EventType.TRACKING_STATE,
                    payload={
                        "face_detected": state.face_detected,
                        "head_x": state.head_x,
                        "head_y": state.head_y,
                        "gaze_x": state.gaze_x,
                        "gaze_y": state.gaze_y,
                        "confidence": state.confidence,
                        "calibrated": self.calibrated,
                        "mode": self._mode,
                    },
                    source="vision",
                )
            )
            if cfg.show_preview:
                self._publish_preview(frame, state)
            elapsed = time.monotonic() - started
            time.sleep(max(0.0, interval - elapsed))

    def _process_frame(self, frame: np.ndarray) -> TrackingState:
        cfg = self._config.config.vision
        face: FaceState = self._tracker.process(frame, cfg.blink_sensitivity)
        if not face.detected:
            self._dwell.update(0, 0, False)
            return TrackingState(calibrated=self.calibrated, mode=self._mode)

        gaze_x, gaze_y = self._calibrator.map(face.gaze_x, face.gaze_y)
        self._smoothed_x = cfg.cursor_smoothing * self._smoothed_x + (1 - cfg.cursor_smoothing) * gaze_x
        self._smoothed_y = cfg.cursor_smoothing * self._smoothed_y + (1 - cfg.cursor_smoothing) * gaze_y

        width, height = self._screen_size
        cursor_x = self._smoothed_x * width
        cursor_y = self._smoothed_y * height

        if self._mode in {"head", "gaze"} and self._input.available:
            self._move_cursor(face, cursor_x, cursor_y, cfg)

        self._handle_blink(face.blink, cfg)
        self._handle_dwell(cursor_x, cursor_y, face.detected, cfg)

        return TrackingState(
            face_detected=True,
            head_x=face.yaw,
            head_y=face.pitch,
            gaze_x=gaze_x,
            gaze_y=gaze_y,
            confidence=face.confidence,
            blink=face.blink,
            calibrated=self.calibrated,
            mode=self._mode,
        )

    def _move_cursor(self, face: FaceState, cursor_x: float, cursor_y: float, cfg: Any) -> None:
        try:
            if self._mode == "head":
                dx = -face.yaw * 35.0 * cfg.cursor_sensitivity
                dy = face.pitch * 35.0 * cfg.cursor_sensitivity
                if abs(dx) > cfg.dead_zone_px / 10 or abs(dy) > cfg.dead_zone_px / 10:
                    self._input.move_relative(dx, dy)
            else:
                self._input.move(int(cursor_x), int(cursor_y))
        except RuntimeError as exc:
            self._log.debug("Cursor move skipped: %s", exc)

    def _handle_blink(self, blink: bool, cfg: Any) -> None:
        if not cfg.blink_click_enabled or not self._input.available:
            self._blink_prev = blink
            return
        now = time.monotonic()
        if blink and not self._blink_prev and now - self._last_blink > 0.6:
            self._last_blink = now
            try:
                self._input.click("left")
                self._bus.emit(EventType.SELECTION, {"source": "blink"}, "vision")
            except RuntimeError as exc:
                self._log.debug("Blink click skipped: %s", exc)
        self._blink_prev = blink

    def _handle_dwell(self, x: float, y: float, present: bool, cfg: Any) -> None:
        if not cfg.dwell_enabled or self._mode == "off" or not self._input.available:
            return
        state = self._dwell.update(x, y, present)
        self._bus.emit(EventType.DWELL_PROGRESS, {"progress": state.progress, "x": x, "y": y}, "vision")
        if state.selected:
            try:
                self._input.click("left")
                self._bus.emit(EventType.SELECTION, {"source": "dwell", "x": x, "y": y}, "vision")
            except RuntimeError as exc:
                self._log.debug("Dwell click skipped: %s", exc)

    def _publish_preview(self, frame: np.ndarray, state: TrackingState) -> None:
        preview = frame.copy()
        if state.face_detected:
            x = int(state.gaze_x * preview.shape[1])
            y = int(state.gaze_y * preview.shape[0])
            cv2.circle(preview, (x, y), 8, (0, 255, 255), 2)
            cv2.putText(
                preview,
                f"conf {state.confidence:.2f}",
                (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2,
            )
        ok, encoded = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            self._bus.emit(EventType.VISION_FRAME, {"jpeg": encoded.tobytes()}, "vision")
