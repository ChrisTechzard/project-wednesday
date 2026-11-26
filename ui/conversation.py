"""Conversation panel for text and voice interaction."""

from __future__ import annotations

import threading

import customtkinter as ctk

from core.events import EventBus
from core.models import Event, EventType

from ui.formatting import USER_SPEAKER, format_transcript_line, welcome_line
from ui.widgets import (
    ACCENT,
    BG,
    DANGER,
    MUTED,
    TEXT,
    action_button,
    bind_focus_ring,
    danger_button,
    label,
    panel,
    secondary_button,
)


class ConversationFrame(ctk.CTkFrame):
    """Chat transcript with text input and microphone controls."""

    def __init__(self, parent: ctk.CTkBaseClass, jarvis: object, bus: EventBus) -> None:
        super().__init__(parent, fg_color=BG)
        self._jarvis = jarvis
        self._bus = bus
        self._transcript: ctk.CTkTextbox | None = None
        self._entry: ctk.CTkEntry | None = None
        self._status: ctk.CTkLabel | None = None
        self._meter: ctk.CTkProgressBar | None = None
        self._mic_hint: ctk.CTkLabel | None = None
        self._send_button: ctk.CTkButton | None = None
        self._mic_button: ctk.CTkButton | None = None
        self._busy = False
        self._listening = False
        self._build()

    def _build(self) -> None:
        label(self, "CONVERSATION", 26, weight="bold").pack(anchor="w", padx=24, pady=(22, 4))
        label(self, "Type or speak to Wednesday", 13, text_color=MUTED).pack(anchor="w", padx=24)

        transcript_bar = ctk.CTkFrame(self, fg_color="transparent")
        transcript_bar.pack(fill="x", padx=24, pady=(14, 0))
        label(transcript_bar, "TRANSCRIPT", 12, text_color=ACCENT, weight="bold").pack(side="left")
        secondary_button(transcript_bar, "CLEAR", self.clear_transcript, width=78, height=32).pack(side="right")
        secondary_button(transcript_bar, "COPY", self.copy_transcript, width=78, height=32).pack(side="right", padx=4)

        card = panel(self)
        card.pack(fill="both", expand=True, padx=24, pady=(8, 18))
        self._transcript = ctk.CTkTextbox(card, fg_color="#080D15", font=ctk.CTkFont(size=13), wrap="word")
        self._transcript.pack(fill="both", expand=True, padx=14, pady=14)
        self._transcript.tag_config("user", foreground=ACCENT)
        self._transcript.tag_config("assistant", foreground=TEXT)
        self._transcript.tag_config("system", foreground=MUTED)
        bind_focus_ring(self._transcript)
        self._insert_line(welcome_line(), "system")

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=24, pady=(0, 12))
        self._entry = ctk.CTkEntry(
            controls,
            placeholder_text="Type a command or message…",
            height=42,
            font=ctk.CTkFont(size=14),
        )
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry.bind("<Return>", lambda event: self.send())
        bind_focus_ring(self._entry)

        self._send_button = action_button(controls, "SEND", self.send, width=80)
        self._send_button.pack(side="left", padx=4)
        self._mic_button = action_button(controls, "MIC", self.toggle_listen, width=78)
        self._mic_button.pack(side="left", padx=4)
        danger_button(controls, "STOP", self.stop, width=70).pack(side="left", padx=4)

        self._status = label(self, "Ready", 12, text_color=MUTED)
        self._status.pack(anchor="w", padx=24, pady=(4, 4))

        meter_row = ctk.CTkFrame(self, fg_color="transparent")
        meter_row.pack(fill="x", padx=24, pady=(0, 18))
        label(meter_row, "MIC", 11, text_color=MUTED).pack(side="left", padx=(0, 10))
        self._meter = ctk.CTkProgressBar(meter_row, height=8, progress_color=ACCENT)
        self._meter.pack(side="left", fill="x", expand=True)
        self._meter.set(0)
        self._mic_hint = label(meter_row, "quiet", 11, text_color=MUTED)
        self._mic_hint.pack(side="left", padx=(10, 0))

    def _update_meter(self, level: float) -> None:
        if self._meter is not None:
            self._meter.set(max(0.0, min(1.0, level)))
        if self._mic_hint is not None:
            if level < 0.08:
                self._mic_hint.configure(text="quiet", text_color=MUTED)
            elif level < 0.6:
                self._mic_hint.configure(text="good", text_color="#3DDC84")
            else:
                self._mic_hint.configure(text="loud", text_color="#FFB020")

    def _set_status(self, text: str, color: str = MUTED) -> None:
        if self._status is not None:
            self._status.configure(text=text, text_color=color)

    def _sync_controls(self) -> None:
        """Keep SEND/MIC states tied to whether a request is in flight."""
        if self._send_button is not None:
            self._send_button.configure(state="disabled" if self._busy else "normal")
        if self._mic_button is not None:
            self._mic_button.configure(
                text="RECORDING" if self._listening else "MIC",
                state="disabled" if self._busy else "normal",
            )

    def send(self) -> None:
        """Send typed text to the brain (one request at a time)."""
        if self._busy or self._entry is None:
            return
        text = self._entry.get().strip()
        if not text:
            return
        self._busy = True
        self._entry.delete(0, "end")
        self._append(USER_SPEAKER, text)
        self._set_status("Thinking…", ACCENT)
        self._sync_controls()
        threading.Thread(target=self._respond, args=(text,), name="ui-send", daemon=True).start()

    def _respond(self, text: str) -> None:
        reply = ""
        try:
            reply = self._jarvis.process_text(text)
        finally:
            def done() -> None:
                self._busy = False
                self._sync_controls()
                if reply:
                    self._append("Wednesday", reply)
                self._set_status("Ready" if reply else "Stopped")
            self.after(0, done)

    def toggle_listen(self) -> None:
        """MIC starts recording; click again (or STOP) to finish early."""
        if self._listening:
            self._jarvis.voice.stop_listening()
            self._set_status("Finishing recording…", ACCENT)
            return
        if self._busy or self._jarvis.voice.busy:
            self._set_status("Already busy — press STOP first", DANGER)
            return
        self._listening = True
        self._sync_controls()
        self._set_status("Listening… click MIC or STOP when done", ACCENT)
        threading.Thread(target=self._listen_worker, name="ui-listen", daemon=True).start()

    def _listen_worker(self) -> None:
        transcript = self._jarvis.voice.listen_once()

        def finish() -> None:
            self._listening = False
            self._sync_controls()

        self.after(0, finish)
        if transcript.is_empty:
            label_text = "Recording cancelled" if transcript.source == "cancelled" else "No speech detected"
            self.after(0, lambda: self._set_status(label_text))
            return
        self.after(0, lambda: self._append(USER_SPEAKER, transcript.text))
        self._busy = True
        self.after(0, lambda: (self._set_status("Thinking…", ACCENT), self._sync_controls()))
        reply = ""
        try:
            reply = self._jarvis.process_text(transcript.text)
        finally:
            def done() -> None:
                self._busy = False
                self._sync_controls()
                if reply:
                    self._append("Wednesday", reply)
                self._set_status("Ready" if reply else "Stopped")
            self.after(0, done)

    def stop(self) -> None:
        """STOP cancels recording, AI generation and speech."""
        self._jarvis.stop_all()
        self._listening = False
        self._busy = False
        self._sync_controls()
        self._set_status("Stopped", DANGER)

    def copy_transcript(self) -> None:
        """Copy the visible transcript to the system clipboard."""
        if self._transcript is None:
            return
        text = self._transcript.get("1.0", "end").strip()
        if not text:
            self._set_status("Nothing to copy")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self._set_status("Transcript copied", ACCENT)

    def clear_transcript(self) -> None:
        """Start a fresh transcript without touching stored chat history."""
        if self._transcript is None:
            return
        self._transcript.configure(state="normal")
        self._transcript.delete("1.0", "end")
        self._insert_line(welcome_line(), "system")
        self._transcript.configure(state="disabled")
        self._set_status("Transcript cleared")

    def _append(self, speaker: str, text: str) -> None:
        line, tag = format_transcript_line(speaker, text)
        self._insert_line(line, tag)

    def _insert_line(self, text: str, tag: str) -> None:
        if self._transcript is None:
            return
        self._transcript.configure(state="normal")
        self._transcript.insert("end", text, (tag,))
        self._transcript.see("end")
        self._transcript.configure(state="disabled")

    def on_event(self, event: Event) -> None:
        """Handle transcript/speaking events from the event bus."""
        if event.type == EventType.STATUS and "mic_level" in event.payload:
            level = float(event.payload["mic_level"])
            self.after(0, lambda: self._update_meter(level))
        elif event.type == EventType.TRANSCRIPT and self._status is not None:
            text = str(event.payload.get("text", ""))
            self.after(0, lambda: self._set_status(f"Heard: {text[:70]}", ACCENT))
        elif event.type == EventType.SPEAKING and self._status is not None:
            active = bool(event.payload.get("active"))
            if active or not self._busy:
                color = ACCENT if active else MUTED
                self.after(0, lambda: self._set_status("Speaking…" if active else "Ready", color))
