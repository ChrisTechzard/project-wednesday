"""Vision dashboard: webcam preview, tracking controls and calibration."""

from __future__ import annotations

import io
import threading
from typing import Any

import customtkinter as ctk
from PIL import Image, ImageDraw

from core.events import EventBus
from core.models import Event, EventType

from ui.widgets import ACCENT, BG, DANGER, MUTED, TEXT, action_button, label, panel

CALIBRATION_TARGETS = [(0.1, 0.1), (0.5, 0.1), (0.9, 0.1), (0.1, 0.5), (0.5, 0.5), (0.9, 0.5), (0.1, 0.9), (0.5, 0.9), (0.9, 0.9)]


class VisionFrame(ctk.CTkFrame):
    """Live webcam preview and control surface for head/gaze tracking."""

    def __init__(self, parent: ctk.CTkBaseClass, jarvis: Any, bus: EventBus) -> None:
        super().__init__(parent, fg_color=BG)
        self._jarvis = jarvis
        self._bus = bus
        self._preview_label: ctk.CTkLabel | None = None
        self._photo: Any = None
        self._preview_size = (480, 360)
        self._mode_var = ctk.StringVar(value="off")
        self._confidence = label(self, "Confidence: —", 12, text_color=MUTED)
        self._status = label(self, "Camera off", 12, text_color=MUTED)
        self._calib_status = label(self, "Not calibrated", 12, text_color=MUTED)
        self._calib_index = 0
        self._calibrating = False
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
        ctk.CTkButton(
            cam_buttons,
            text="Camera OFF",
            width=100,
            height=36,
            fg_color=DANGER,
            hover_color="#C42E3E",
            command=self._camera_off,
        ).pack(side="left", padx=4)

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
        calib_buttons = ctk.CTkFrame(right, fg_color="transparent")
        calib_buttons.pack(fill="x", padx=12, pady=8)
        action_button(calib_buttons, "Start calibration", self._start_calibration, width=130).pack(side="left", padx=4)
        action_button(calib_buttons, "Capture point", self._capture_point, width=120).pack(side="left", padx=4)

        self._sensitivity = self._slider(right, "Sensitivity", 0.1, 3.0, self._jarvis.config.config.vision.cursor_sensitivity, self._on_sensitivity)
        self._smoothing = self._slider(right, "Smoothing", 0.0, 0.9, self._jarvis.config.config.vision.cursor_smoothing, self._on_smoothing)
        self._dwell = self._slider(right, "Dwell time (ms)", 300, 3000, self._jarvis.config.config.vision.dwell_time_ms, self._on_dwell)

        self._blink_var = ctk.BooleanVar(value=self._jarvis.config.config.vision.blink_click_enabled)
        ctk.CTkCheckBox(right, text="Blink to click (experimental)", variable=self._blink_var, command=self._on_blink).pack(anchor="w", padx=16, pady=(12, 16))

    def _slider(self, parent: ctk.CTkBaseClass, title: str, low: float, high: float, value: float, command: Any) -> ctk.CTkSlider:
        label(parent, f"{title}: {value}", 12, text_color=MUTED).pack(anchor="w", padx=16, pady=(10, 0))
        slider = ctk.CTkSlider(parent, from_=low, to=high, command=command)
        slider.set(value)
        slider.pack(fill="x", padx=16)
        return slider

    # ---- actions ------------------------------------------------------

    def _camera_on(self) -> None:
        threading.Thread(target=self._jarvis.vision.start, name="camera-on", daemon=True).start()
        self.after(400, lambda: self._status.configure(text="Starting camera…", text_color=ACCENT))

    def _camera_off(self) -> None:
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
        self._calib_status.configure(text=f"Look at target 1/{len(CALIBRATION_TARGETS)} then press Capture point", text_color=ACCENT)

    def _capture_point(self) -> None:
        if not self._calibrating:
            self._start_calibration()
            return
        if self._calib_index >= len(CALIBRATION_TARGETS):
            ok = self._jarvis.vision.finish_calibration()
            self._calibrating = False
            self._calib_status.configure(text="Calibrated" if ok else "Calibration failed — retry", text_color="#3DDC84" if ok else DANGER)
            return
        tx, ty = CALIBRATION_TARGETS[self._calib_index]
        if self._jarvis.vision.capture_calibration_point(tx, ty):
            self._calib_index += 1
            if self._calib_index >= len(CALIBRATION_TARGETS):
                ok = self._jarvis.vision.finish_calibration()
                self._calibrating = False
                self._calib_status.configure(text="Calibrated" if ok else "Calibration failed — retry", text_color="#3DDC84" if ok else DANGER)
            else:
                self._calib_status.configure(text=f"Look at target {self._calib_index + 1}/{len(CALIBRATION_TARGETS)} then press Capture point", text_color=ACCENT)
        else:
            self._calib_status.configure(text="No face detected — stay in view and retry", text_color=DANGER)

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

    def _draw_placeholder(self) -> None:
        image = Image.new("RGB", self._preview_size, (4, 7, 12))
        draw = ImageDraw.Draw(image)
        draw.text((24, 20), "Camera preview unavailable", fill=(143, 163, 191))
        draw.text((24, 40), "Click Camera ON to start the webcam", fill=(90, 110, 140))
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
            if detected:
                self.after(0, lambda: self._status.configure(text="Tracking active", text_color="#3DDC84"))

    def _render_frame(self, data: bytes) -> None:
        try:
            image = Image.open(io.BytesIO(data)).convert("RGB")
            image.thumbnail(self._preview_size)
            self._set_image(image)
        except Exception:
            pass
