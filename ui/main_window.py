"""Main JARVIS application window with navigation and event routing."""

from __future__ import annotations

import threading
from typing import Any

import customtkinter as ctk

from core.events import EventBus
from core.logging import get_logger
from core.models import Event, EventType

from ui.conversation import ConversationFrame
from ui.dashboard import DashboardFrame
from ui.settings_panel import SettingsFrame
from ui.vision_panel import VisionFrame
from ui.widgets import ACCENT, BG, DANGER, MUTED, PANEL, TEXT, label

NAV_ITEMS = [
    ("dashboard", "⌂  Dashboard"),
    ("conversation", "✦  Conversation"),
    ("vision", "◉  Vision & Tracking"),
    ("settings", "⚙  Settings"),
]


class ConfirmationDialog(ctk.CTkToplevel):
    """Modal yes/no dialog used by the safety manager."""

    def __init__(self, parent: ctk.CTkBaseClass, title: str, details: str) -> None:
        super().__init__(parent)
        self.result = False
        self.title("Wednesday — Confirm Action")
        self.geometry("440x220")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.transient(parent)
        self.attributes("-topmost", True)

        label(self, title, 18, weight="bold").pack(anchor="w", padx=24, pady=(24, 8))
        detail = label(self, details, 13, text_color=MUTED, wraplength=390, justify="left")
        detail.pack(anchor="w", padx=24)
        label(self, "Only confirm if you trust this action.", 11, text_color="#FFB020").pack(anchor="w", padx=24, pady=(10, 0))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=22)
        ctk.CTkButton(buttons, text="DENY", width=120, height=38, fg_color=DANGER, hover_color="#C42E3E", command=self._deny).pack(side="left")
        ctk.CTkButton(buttons, text="ALLOW", width=120, height=38, fg_color="#0089A8", hover_color=ACCENT, command=self._allow).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self._deny)

    def _allow(self) -> None:
        self.result = True
        self.destroy()

    def _deny(self) -> None:
        self.result = False
        self.destroy()


class MainWindow(ctk.CTk):
    """Primary application window."""

    def __init__(self, jarvis: Any) -> None:
        super().__init__()
        self.jarvis = jarvis
        self._bus: EventBus = jarvis.bus
        self._log = get_logger("ui")
        self._frames: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._current = "dashboard"
        self._closed = False
        self._confirm_pending: threading.Event | None = None
        self._confirm_result = False

        self.title("Wednesday — Personal AI Assistant")
        self.geometry("1180x760")
        self.minsize(960, 640)
        ctk.set_appearance_mode(jarvis.config.config.general.theme)
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=BG)

        self._build()
        self._bus.subscribe(self._on_event)
        self.jarvis.set_confirmation_handler(self._confirm)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(1500, self._refresh_status)
        self.after(100, self._start_subsystems)

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        sidebar = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, width=210)
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sidebar.grid_propagate(False)

        label(sidebar, "WEDNESDAY", 20, weight="bold", text_color=ACCENT).pack(anchor="w", padx=20, pady=(26, 2))
        label(sidebar, "Personal AI workstation", 10, text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 24))

        for key, text in NAV_ITEMS:
            button = ctk.CTkButton(
                sidebar,
                text=text,
                anchor="w",
                height=42,
                fg_color="transparent",
                text_color=MUTED,
                hover_color="#162437",
                command=lambda k=key: self.show(k),
            )
            button.pack(fill="x", padx=12, pady=3)
            self._nav_buttons[key] = button

        self._side_status = label(sidebar, "● Initialising", 11, text_color=MUTED, wraplength=180)
        self._side_status.pack(anchor="w", padx=20, pady=(24, 6))
        ctk.CTkButton(
            sidebar,
            text="■  EMERGENCY STOP",
            height=40,
            fg_color=DANGER,
            hover_color="#C42E3E",
            command=self._emergency_stop,
        ).pack(fill="x", padx=12, pady=(6, 20))
        self._nav_buttons["dashboard"].configure(fg_color="#162437", text_color=TEXT)

        header = ctk.CTkFrame(self, fg_color=BG, height=56)
        header.grid(row=0, column=1, sticky="ew", padx=18, pady=(14, 0))
        self._header_title = label(header, "Dashboard", 18, weight="bold")
        self._header_title.pack(side="left")
        self._header_status = label(header, "AI offline", 12, text_color=MUTED)
        self._header_status.pack(side="right", padx=12)

        container = ctk.CTkFrame(self, fg_color=BG)
        container.grid(row=1, column=1, sticky="nsew", padx=18, pady=12)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        self._frames["dashboard"] = DashboardFrame(container, self.jarvis, self._bus)
        self._frames["conversation"] = ConversationFrame(container, self.jarvis, self._bus)
        self._frames["vision"] = VisionFrame(container, self.jarvis, self._bus)
        self._frames["settings"] = SettingsFrame(container, self.jarvis, self._bus)
        for frame in self._frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

    def show(self, key: str) -> None:
        """Switch the visible panel."""
        if key not in self._frames:
            return
        self._current = key
        self._frames[key].tkraise()
        titles = {"dashboard": "Dashboard", "conversation": "Conversation", "vision": "Vision & Tracking", "settings": "Settings"}
        self._header_title.configure(text=titles.get(key, key.title()))
        for name, button in self._nav_buttons.items():
            active = name == key
            button.configure(fg_color="#162437" if active else "transparent", text_color=TEXT if active else MUTED)

    # ---- lifecycle ----------------------------------------------------

    def _start_subsystems(self) -> None:
        threading.Thread(target=self.jarvis.start, name="jarvis-start", daemon=True).start()

    def _on_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        threading.Thread(target=self.jarvis.stop, name="jarvis-stop", daemon=True).start()
        self.destroy()

    def _emergency_stop(self) -> None:
        """Halt all actions and fully quit — this is the 'turn off' button."""
        self.jarvis.emergency_stop()
        self._side_status.configure(text="● EMERGENCY STOP", text_color=DANGER)
        self._header_status.configure(text="STOPPED", text_color=DANGER)
        self.after(100, self._on_close)

    # ---- confirmation bridge -----------------------------------------

    def _confirm(self, title: str, details: str) -> bool:
        """Called from worker threads; marshal the dialog to the UI thread."""
        self._confirm_pending = threading.Event()
        self.after(0, lambda: self._show_confirmation(title, details))
        self._confirm_pending.wait(timeout=120)
        return self._confirm_result

    def _show_confirmation(self, title: str, details: str) -> None:
        dialog = ConfirmationDialog(self, title, details)
        self.wait_window(dialog)
        self._confirm_result = dialog.result
        if self._confirm_pending is not None:
            self._confirm_pending.set()

    # ---- event routing ------------------------------------------------

    def _on_event(self, event: Event) -> None:
        if self._closed:
            return
        self.after(0, lambda: self._dispatch(event))

    def _dispatch(self, event: Event) -> None:
        dashboard = self._frames["dashboard"]
        conversation = self._frames["conversation"]
        vision = self._frames["vision"]

        if event.type in {EventType.LOG, EventType.TOOL_RESULT}:
            message = event.payload.get("message") or f"{event.payload.get('tool', 'tool')}: {event.payload.get('success', '')}"
            dashboard.append_log(str(message)[:200])
        elif event.type == EventType.ERROR:
            message = str(event.payload.get("message", "Unknown error"))
            dashboard.append_log(f"ERROR: {message}")
        elif event.type == EventType.STATUS:
            self._side_status.configure(text="● Online" if not self.jarvis.safety.stopped else "● STOPPED", text_color="#3DDC84" if not self.jarvis.safety.stopped else DANGER)
            if "settings_saved" in event.payload:
                dashboard.append_log("Settings saved")
            if "message" in event.payload:
                dashboard.append_log(str(event.payload["message"]))
        elif event.type == EventType.SPEAKING:
            self._header_status.configure(text="Speaking…" if event.payload.get("active") else "Listening", text_color=ACCENT if event.payload.get("active") else MUTED)
        elif event.type == EventType.WAKE_WORD:
            dashboard.append_log("Wake word detected")

        conversation.on_event(event)
        vision.on_event(event)

    def _refresh_status(self) -> None:
        if self._closed:
            return
        try:
            report = self.jarvis.doctor(probe_cameras=False)
            self._frames["dashboard"].update_status(report)
            self._header_status.configure(text=f"AI {'online' if report['ollama_running'] else 'offline'}", text_color="#3DDC84" if report["ollama_running"] else MUTED)
        except Exception as exc:
            self._log.debug("Status refresh failed: %s", exc)
        # doctor() probes cameras and Ollama; 30 s avoids periodic CPU spikes.
        self.after(30000, self._refresh_status)

    def run(self) -> None:
        """Start the Tk main loop."""
        self.mainloop()
