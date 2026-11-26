"""Vision dashboard: webcam preview, tracking controls and calibration."""

from __future__ import annotations

import io
import threading
from collections.abc import Callable
from typing import Any

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from core.events import EventBus
from core.models import Event, EventType

from ui.widgets import (
    ACCENT,
    BG,
    DANGER,
    MUTED,
    SUCCESS,
    WARNING,
    action_button,
    bind_focus_ring,
    danger_button,
    label,
    panel,
    secondary_button,
)

CALIBRATION_TARGETS = [
    (0.1, 0.1), (0.5, 0.1), (0.9, 0.1),
    (0.1, 0.5), (0.5, 0.5), (0.9, 0.5),
    (0.1, 0.9), (0.5, 0.9), (0.9, 0.9),
]
ACCENT_RGB = (0, 212, 255)


class VisionFrame(ctk.CTkFrame):
    """Live webcam preview and control surface for head/gaze tracking."""

    def __init__(self, parent: ctk.CTkBaseClass, jarvis: Any, bus: EventBus) -> None:
        super().__init__(parent, fg_color=BG)
        self._jarvis = jarvis
        self._bus = bus
        self._preview_label: ctk.CTkLabel | None = None
        self._photo: Any = None
        self._preview_size = (480, 360)
        self._last_frame: Image.Image | None = None
        self._mode_var = ctk.StringVar(value="off")
        self._confidence = label(self, "Confidence: —", 12, text_color=MUTED)
        self._status = label(self, "Camera off", 12, text_color=MUTED)
        self._calib_status = label(self, "Not calibrated", 12, text_color=MUTED)
        self._calib_index = 0
        self._calibrating = False
        self._start_button: ctk.CTkButton | None = None
        self._capture_button: ctk.CTkButton | None = None
        self._cancel_button: ctk.CTkButton | None = None
        self._calib_progress: ctk.CTkProgressBar | None = None
        self._build()

    def _build(self) -> None:
        label(self, "VISION & TRACKING", 26, weight="bold").pack(anchor="w", padx=24, pady=(22, 4))
        label(self, "Webcam face, head and gaze interaction", 13, text_color=MUTED).pack(anchor="w", padx=24)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=18)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)

        left = panel(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        preview_holder = ctk.CTkFrame(left, fg_color="#04070C", corner_radius=10, width=488, height=368)
        preview_holder.pack(padx=12, pady=12)
        preview_holder.pack_propagate(False)
        self._preview_label = ctk.CTkLabel(preview_holder, text="Camera preview unavailable", text_color=MUTED, font=ctk.CTkFont(size=12))
        self._preview_label.pack(fill="both", expand=True)
        self._draw_placeholder()

        status_row = ctk.CTkFrame(left, fg_color="transparent")
        status_row.pack(fill="x", padx=12, pady=(0, 12))
        self._status.pack(side="left", padx=(0, 16))
        self._confidence.pack(side="left")

        right = panel(body)
        right.grid(row=0, column=1, sticky="nsew")

        label(right, "CAMERA", 12, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(14, 6))
        cam_buttons = ctk.CTkFrame(right, fg_color="transparent")
        cam_buttons.pack(fill="x", padx=12)
        action_button(cam_buttons, "Camera ON", self._camera_on, width=100).pack(side="left", padx=4)
        danger_button(cam_buttons, "Camera OFF", self._camera_off, width=100).pack(side="left", padx=4)

        label(right, "CURSOR CONTROL", 12, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(18, 6))
        modes = ctk.CTkSegmentedButton(
            right,
            values=["off", "head", "gaze"],
            variable=self._mode_var,
            command=self._set_mode,
        )
        modes.pack(fill="x", padx=16)

        label(right, "Calibration", 12, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(18, 4))
        self._calib_status.pack(anchor="w", padx=16)
        self._calib_progress = ctk.CTkProgressBar(right, height=8, progress_color=ACCENT)
        self._calib_progress.pack(fill="x", padx=16, pady=(8, 0))
        self._calib_progress.set(0)

        calib_buttons = ctk.CTkFrame(right, fg_color="transparent")
        calib_buttons.pack(fill="x", padx=12, pady=8)
        self._start_button = action_button(calib_buttons, "Start calibration", self._start_calibration, width=130)
        self._start_button.pack(side="left", padx=4)
        self._capture_button = action_button(calib_buttons, "Capture point", self._capture_point, width=120)
        self._capture_button.pack(side="left", padx=4)
        self._cancel_button = secondary_button(calib_buttons, "Cancel", self._cancel_calibration, width=90)
        self._cancel_button.pack(side="left", padx=4)

        self._sensitivity = self._slider(right, "Sensitivity", 0.1, 3.0, self._jarvis.config.config.vision.cursor_sensitivity, self._on_sensitivity)
        self._smoothing = self._slider(right, "Smoothing", 0.0, 0.9, self._jarvis.config.config.vision.cursor_smoothing, self._on_smoothing)
        self._dwell = self._slider(
            right,
            "Dwell time (ms)",
            300,
            5000,
            self._jarvis.config.config.vision.dwell_time_ms,
            self._on_dwell,
            formatter=lambda value: str(int(value)),
        )

        self._blink_var = ctk.BooleanVar(value=self._jarvis.config.config.vision.blink_click_enabled)
        blink = ctk.CTkCheckBox(right, text="Blink to click (experimental)", variable=self._blink_var, height=36, command=self._on_blink)
        blink.pack(anchor="w", padx=16, pady=(12, 16))
        bind_focus_ring(blink)
        self._set_calibration_ui()

    def _slider(
        self,
        parent: ctk.CTkBaseClass,
        title: str,
        low: float,
        high: float,
        value: float,
        command: Callable[[float], object],
        formatter: Callable[[float], str] | None = None,
    ) -> ctk.CTkSlider:
        format_value = formatter or (lambda number: f"{number:.2f}")
        readout = label(parent, f"{title}: {format_value(value)}", 12, text_color=MUTED)
        readout.pack(anchor="w", padx=16, pady=(10, 0))

        def changed(new_value: float) -> None:
            command(new_value)
            readout.configure(text=f"{title}: {format_value(new_value)}")

        slider = ctk.CTkSlider(parent, from_=low, to=high, command=changed)
        slider.set(value)
        slider.pack(fill="x", padx=16)
        bind_focus_ring(slider)
        return slider

    # ---- actions ------------------------------------------------------

    def _camera_on(self) -> None:
        threading.Thread(target=self._jarvis.vision.start, name="camera-on", daemon=True).start()
        self.after(400, lambda: self._status.configure(text="Starting camera…", text_color=ACCENT))

    def _camera_off(self) -> None:
        if self._calibrating:
            self._cancel_calibration()
        self._jarvis.vision.stop()
        self._draw_placeholder()
        self._status.configure(text="Camera off", text_color=MUTED)

    def _set_mode(self, value: str) -> None:
        def worker() -> None:
            ok = self._jarvis.vision.set_mode(value, enabled=value != "off")
            self.after(0, lambda: self._status.configure(text=f"Mode: {value}" if ok else f"Mode {value} unavailable (permission?)", text_color=ACCENT if ok else DANGER))
        threading.Thread(target=worker, name="set-mode", daemon=True).start()

    def _start_calibration(self) -> None:
        self._jarvis.vision.start_calibration()
        self._calib_index = 0
        self._calibrating = True
        self._set_calibration_ui()

    def _capture_point(self) -> None:
        if not self._calibrating:
            self._start_calibration()
            return
        if self._calib_index >= len(CALIBRATION_TARGETS):
            self._finish_calibration()
            return

        target_x, target_y = CALIBRATION_TARGETS[self._calib_index]
        if not self._jarvis.vision.capture_calibration_point(target_x, target_y):
            self._calib_status.configure(text="No face detected — stay in view and retry", text_color=DANGER)
            return

        self._calib_index += 1
        if self._calib_index >= len(CALIBRATION_TARGETS):
            self._finish_calibration()
        else:
            self._set_calibration_ui()

    def _finish_calibration(self) -> None:
        ok = self._jarvis.vision.finish_calibration()
        self._calibrating = False
        self._set_calibration_ui()
        self._calib_status.configure(
            text="Calibrated" if ok else "Calibration failed — try again",
            text_color=SUCCESS if ok else DANGER,
        )

    def _cancel_calibration(self) -> None:
        if not self._calibrating:
            self._calib_status.configure(text="No calibration in progress", text_color=MUTED)
            return
        had_fit = bool(self._jarvis.vision.calibrated)
        self._jarvis.vision.cancel_calibration()
        self._calibrating = False
        self._calib_index = 0
        self._set_calibration_ui()
        self._calib_status.configure(
            text="Calibration cancelled — previous fit kept" if had_fit else "Calibration cancelled",
            text_color=WARNING,
        )

    def _set_calibration_ui(self) -> None:
        total = len(CALIBRATION_TARGETS)
        if self._calibrating:
            index = min(self._calib_index, total - 1)
            self._calib_status.configure(
                text=f"Target {index + 1}/{total} — look at the circle, then press Capture",
                text_color=ACCENT,
            )
            if self._calib_progress is not None:
                self._calib_progress.set(self._calib_index / total)
            if self._capture_button is not None:
                self._capture_button.configure(text=f"Capture point ({index + 1}/{total})")
            if self._start_button is not None:
                self._start_button.configure(state="disabled")
            if self._cancel_button is not None:
                self._cancel_button.configure(state="normal")
            self._render_target()
            return

        calibrated = bool(self._jarvis.vision.calibrated)
        self._calib_status.configure(
            text="Calibrated" if calibrated else "Not calibrated",
            text_color=SUCCESS if calibrated else MUTED,
        )
        if self._calib_progress is not None:
            self._calib_progress.set(0)
        if self._capture_button is not None:
            self._capture_button.configure(text="Capture point")
        if self._start_button is not None:
            self._start_button.configure(state="normal")
        if self._cancel_button is not None:
            self._cancel_button.configure(state="disabled")
        self._restore_preview()

    def _on_sensitivity(self, value: float) -> None:
        self._jarvis.config.update("vision", {"cursor_sensitivity": round(float(value), 2)})

    def _on_smoothing(self, value: float) -> None:
        self._jarvis.config.update("vision", {"cursor_smoothing": round(float(value), 2)})

    def _on_dwell(self, value: float) -> None:
        self._jarvis.config.update("vision", {"dwell_time_ms": int(value)})
        self._jarvis.vision._dwell.configure(float(value) / 1000)

    def _on_blink(self) -> None:
        self._jarvis.config.update("vision", {"blink_click_enabled": bool(self._blink_var.get())})

    # ---- preview rendering -------------------------------------------

    def _placeholder_image(self) -> Image.Image:
        image = Image.new("RGB", self._preview_size, (4, 7, 12))
        draw = ImageDraw.Draw(image)
        draw.text((24, 20), "Camera preview unavailable", fill=(159, 178, 204))
        draw.text((24, 40), "Click Camera ON to start the webcam", fill=(110, 128, 152))
        return image

    def _draw_placeholder(self) -> None:
        self._last_frame = None
        self._render_target()

    def _render_target(self) -> None:
        if not self._calibrating:
            self._restore_preview()
            return
        base = self._last_frame if self._last_frame is not None else self._placeholder_image()
        self._set_image(self._with_target(base, self._calib_index))

    def _with_target(self, image: Image.Image, index: int) -> Image.Image:
        framed = image.copy()
        draw = ImageDraw.Draw(framed)
        width, height = framed.size
        target_x, target_y = CALIBRATION_TARGETS[min(index, len(CALIBRATION_TARGETS) - 1)]
        x, y = int(target_x * width), int(target_y * height)
        radius = 20

        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=ACCENT_RGB, width=3)
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=ACCENT_RGB)
        draw.line((x - 30, y, x - 10, y), fill=ACCENT_RGB, width=2)
        draw.line((x + 10, y, x + 30, y), fill=ACCENT_RGB, width=2)
        draw.line((x, y - 30, x, y - 10), fill=ACCENT_RGB, width=2)
        draw.line((x, y + 10, x, y + 30), fill=ACCENT_RGB, width=2)
        draw.text(
            (12, 12),
            f"Target {index + 1}/{len(CALIBRATION_TARGETS)} — look here, then press Capture",
            fill=ACCENT_RGB,
            font=ImageFont.load_default(),
        )
        return framed

    def _restore_preview(self) -> None:
        image = self._last_frame if self._last_frame is not None else self._placeholder_image()
        self._set_image(image)

    def _set_image(self, image: Image.Image) -> None:
        self._photo = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
        if self._preview_label is not None:
            self._preview_label.configure(image=self._photo, text="")

    def on_event(self, event: Event) -> None:
        """Route live frames and tracking state into the UI thread."""
        if event.type == EventType.VISION_FRAME:
            data = event.payload.get("jpeg")
            if isinstance(data, bytes):
                self.after(0, lambda: self._render_frame(data))
        elif event.type == EventType.TRACKING_STATE:
            detected = bool(event.payload.get("face_detected"))
            conf = float(event.payload.get("confidence", 0.0))
            text = f"Face: {'detected' if detected else 'not detected'}"
            self.after(0, lambda: self._confidence.configure(text=f"{text} | Confidence: {conf:.2f}"))
            if detected and not self._calibrating:
                self.after(0, lambda: self._status.configure(text="Tracking active", text_color=SUCCESS))

    def _render_frame(self, data: bytes) -> None:
        try:
            image = Image.open(io.BytesIO(data)).convert("RGB")
            image.thumbnail(self._preview_size)
            self._last_frame = image.copy()
            self._set_image(self._with_target(image, self._calib_index) if self._calibrating else image)
        except Exception:
            pass
