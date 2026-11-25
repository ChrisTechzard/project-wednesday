"""Main dashboard showing live Wednesday status and quick controls."""

from __future__ import annotations

import threading

import customtkinter as ctk

from core.events import EventBus
from core.models import Event, EventType

from ui.widgets import ACCENT, BG, MUTED, TEXT, action_button, label, panel, status_pill


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
        self._build()

    def _build(self) -> None:
        label(self, "SYSTEM OVERVIEW", 26, weight="bold").pack(anchor="w", padx=24, pady=(22, 4))
        label(self, "Live status of every Wednesday subsystem", 13, text_color=MUTED).pack(anchor="w", padx=24)

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
            ("Emergency stop", self._jarvis.stop_all, "All actions halted"),
        ]
        for index, (text, command, done_message) in enumerate(actions):
            button = action_button(buttons, text, lambda c=command, m=done_message: self._run_action(m, c))
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

    def _set_action_status(self, text: str, color: str = "#8FA3BF") -> None:
        if self._action_status is not None:
            self._action_status.configure(text=text, text_color=color)

    def _run_action(self, done_message: str, command) -> None:
        """Run a quick action off the UI thread so the app never freezes."""
        if self._busy:
            self._set_action_status("Already running — please wait", "#FFB020")
            return
        self._busy = True
        for button in self._action_buttons:
            button.configure(state="disabled")
        self._set_action_status("Working…", "#00D4FF")

        def worker() -> None:
            result = None
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
                    self._set_action_status(f"Failed: {error}", "#FF6B6B")
                    self.append_log(f"Quick action failed: {error}")
                else:
                    self._set_action_status(done_message, "#3DDC84")
                    if result:
                        self.append_log(f"{done_message}: {str(result)[:120]}")
                    else:
                        self.append_log(done_message)
            self.after(0, done)

        threading.Thread(target=worker, name="quick-action", daemon=True).start()

    def update_status(self, report: dict[str, object]) -> None:
        """Refresh status cards from a doctor report."""
        self._pills["ai"].configure(
            text="● Online" if report.get("ollama_running") else "● Offline",
            text_color="#3DDC84" if report.get("ollama_running") else "#8FA3BF",
        )
        self._pills["voice"].configure(
            text=f"● {len(report.get('microphones', []))} mic(s)",
            text_color="#3DDC84" if report.get("microphones") else "#FFB020",
        )
        camera_on = bool(report.get("vision_running"))
        self._pills["camera"].configure(
            text="● On" if camera_on else "● Off",
            text_color="#3DDC84" if camera_on else "#8FA3BF",
        )
        mode = str(report.get("tracking_mode", "off"))
        self._pills["tracking"].configure(text=f"● {mode.upper()}", text_color="#00D4FF" if mode != "off" else "#8FA3BF")
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
