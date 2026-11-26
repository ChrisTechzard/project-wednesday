"""Main dashboard showing live Wednesday status and quick controls."""

from __future__ import annotations

import threading
from collections.abc import Callable

import customtkinter as ctk

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
    label,
    panel,
    secondary_button,
    status_pill,
)


class DashboardFrame(ctk.CTkFrame):
    """System overview with live indicators."""

    def __init__(self, parent: ctk.CTkBaseClass, jarvis: object, bus: EventBus) -> None:
        super().__init__(parent, fg_color=BG)
        self._jarvis = jarvis
        self._bus = bus
        self._pills: dict[str, ctk.CTkLabel] = {}
        self._metrics: ctk.CTkLabel | None = None
        self._log: ctk.CTkTextbox | None = None
        self._action_buttons: list[ctk.CTkButton] = []
        self._action_status: ctk.CTkLabel | None = None
        self._busy = False
        self._refreshing = False
        self._build()

    def _build(self) -> None:
        heading = ctk.CTkFrame(self, fg_color="transparent")
        heading.pack(fill="x", padx=24, pady=(22, 0))
        label(heading, "SYSTEM OVERVIEW", 26, weight="bold").pack(side="left")
        secondary_button(heading, "Refresh", self._refresh, width=90, height=32).pack(side="right")
        label(self, "Live status of every Wednesday subsystem", 13, text_color=MUTED).pack(anchor="w", padx=24, pady=(4, 0))

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=24, pady=18)
        grid.columnconfigure((0, 1, 2, 3), weight=1)

        cards = [
            ("ai", "LOCAL AI", "Offline"),
            ("voice", "VOICE", "Idle"),
            ("camera", "CAMERA", "Off"),
            ("tracking", "TRACKING", "Off"),
        ]
        for index, (key, title, initial) in enumerate(cards):
            card = panel(grid)
            card.grid(row=0, column=index, sticky="ew", padx=(0, 10))
            label(card, title, 11, text_color=MUTED).pack(anchor="w", padx=14, pady=(14, 2))
            pill = status_pill(card, initial, False)
            pill.pack(anchor="w", padx=14, pady=(0, 14))
            self._pills[key] = pill

        quick = panel(self)
        quick.pack(fill="x", padx=24, pady=6)
        label(quick, "QUICK ACTIONS", 12, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(14, 8))
        buttons = ctk.CTkFrame(quick, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=(0, 14))
        actions = [
            ("Speak a command", self._jarvis.voice_command, "Voice command finished"),
            ("System status", lambda: self._jarvis.process_text("system status", speak=False), "Status checked"),
            ("Take screenshot", lambda: self._jarvis.process_text("take a screenshot", speak=False), "Screenshot captured"),
            ("Stop current action", self._jarvis.stop_all, "Current action stopped"),
        ]
        for index, (text, command, done_message) in enumerate(actions):
            button_factory = secondary_button if text == "Stop current action" else action_button
            button = button_factory(buttons, text, lambda c=command, m=done_message: self._run_action(m, c))
            button.grid(row=0, column=index, padx=6, sticky="ew")
            buttons.columnconfigure(index, weight=1)
            self._action_buttons.append(button)

        self._action_status = label(quick, "Ready", 11, text_color=MUTED)
        self._action_status.pack(anchor="w", padx=18, pady=(0, 12))

        metrics_card = panel(self)
        metrics_card.pack(fill="x", padx=24, pady=12)
        label(metrics_card, "HARDWARE", 12, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(14, 4))
        self._metrics = label(metrics_card, "Collecting system metrics…", 13, text_color=MUTED)
        self._metrics.pack(anchor="w", padx=16, pady=(0, 16))

        log_card = panel(self)
        log_card.pack(fill="both", expand=True, padx=24, pady=(6, 24))
        label(log_card, "ACTIVITY", 12, text_color=ACCENT, weight="bold").pack(anchor="w", padx=16, pady=(14, 6))
        self._log = ctk.CTkTextbox(log_card, height=180, fg_color="#080D15", font=ctk.CTkFont(size=12))
        self._log.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self._log.configure(state="disabled")
        bind_focus_ring(self._log)

    def _set_action_status(self, text: str, color: str = MUTED) -> None:
        if self._action_status is not None:
            self._action_status.configure(text=text, text_color=color)

    def _run_action(self, done_message: str, command: Callable[[], object]) -> None:
        """Run a quick action off the UI thread so the app never freezes."""
        if self._busy:
            self._set_action_status("Already running — please wait", WARNING)
            return
        self._busy = True
        for button in self._action_buttons:
            button.configure(state="disabled")
        self._set_action_status("Working…", ACCENT)

        def worker() -> None:
            result: object = None
            error: Exception | None = None
            try:
                result = command()
            except Exception as exc:  # never let a quick action kill the UI
                error = exc

            def done() -> None:
                self._busy = False
                for button in self._action_buttons:
                    button.configure(state="normal")
                if error is not None:
                    self._set_action_status(f"Failed: {error}", DANGER)
                    self.append_log(f"Quick action failed: {error}")
                else:
                    self._set_action_status(done_message, SUCCESS)
                    if result:
                        self.append_log(f"{done_message}: {str(result)[:120]}")
                    else:
                        self.append_log(done_message)
            self.after(0, done)

        threading.Thread(target=worker, name="quick-action", daemon=True).start()

    def _refresh(self) -> None:
        """Manual status refresh; still non-blocking and safe to repeat."""
        if self._refreshing:
            self._set_action_status("Refresh already running", WARNING)
            return
        self._refreshing = True
        self._set_action_status("Refreshing status…", ACCENT)

        def worker() -> None:
            report: dict[str, object] | None = None
            error: Exception | None = None
            try:
                report = self._jarvis.doctor(probe_cameras=False)
            except Exception as exc:
                error = exc

            def done() -> None:
                self._refreshing = False
                if error is not None:
                    self._set_action_status(f"Refresh failed: {error}", DANGER)
                    return
                if report is not None:
                    self.update_status(report)
                self._set_action_status("Status refreshed", SUCCESS)
                self.append_log("Status refreshed")
            self.after(0, done)

        threading.Thread(target=worker, name="status-refresh", daemon=True).start()

    def update_status(self, report: dict[str, object]) -> None:
        """Refresh status cards from a doctor report."""
        self._pills["ai"].configure(
            text="Online" if report.get("ollama_running") else "Offline",
            text_color=SUCCESS if report.get("ollama_running") else MUTED,
        )
        self._pills["voice"].configure(
            text=f"{len(report.get('microphones', []))} mic(s)",
            text_color=SUCCESS if report.get("microphones") else WARNING,
        )
        camera_on = bool(report.get("vision_running"))
        self._pills["camera"].configure(
            text="On" if camera_on else "Off",
            text_color=SUCCESS if camera_on else MUTED,
        )
        mode = str(report.get("tracking_mode", "off"))
        self._pills["tracking"].configure(text=mode.upper(), text_color=ACCENT if mode != "off" else MUTED)
        system = report.get("system", {})
        if self._metrics is not None and isinstance(system, dict):
            self._metrics.configure(
                text=(
                    f"CPU {system.get('cpu_percent', 0):.0f}%   "
                    f"RAM {system.get('memory_percent', 0):.0f}%   "
                    f"Disk {system.get('disk_percent', 0):.0f}%   "
                    f"Network {'online' if system.get('online') else 'offline'}"
                )
            )

    def append_log(self, message: str) -> None:
        """Append a line to the activity log."""
        if self._log is None:
            return
        self._log.configure(state="normal")
        self._log.insert("end", f"• {message}\n")
        self._log.see("end")
        self._log.configure(state="disabled")
