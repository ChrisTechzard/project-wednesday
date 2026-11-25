"""Application orchestrator wiring all Wednesday subsystems together."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from ai.brain import Brain
from ai.memory import MemoryStore
from ai.ollama_client import OllamaClient
from ai.tools import ToolContext, ToolRegistry
from automation.input_control import InputController
from automation.launcher import AppLauncher
from automation.screen_analyzer import ScreenAnalyzer
from automation.screenshot import ScreenshotService
from automation.system_monitor import SystemMonitor
from core.config import ConfigManager
from core.events import EventBus
from core.logging import get_logger, setup_logging
from core.models import Event, EventType, ToolResult
from core.safety import SafetyManager
from voice.voice_engine import VoiceEngine
from vision.vision_engine import VisionEngine

ROOT = Path(__file__).resolve().parent.parent


class Jarvis:
    """Owns component lifetimes and provides the public API used by the UI."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self.logs_dir = root / "logs"
        self.models_dir = root / "models"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.logger = setup_logging(self.logs_dir)
        self.log = get_logger("jarvis")

        self.config = ConfigManager()
        self.bus = EventBus()
        self.safety = SafetyManager(self.config, self.bus, self.logs_dir)
        self.ollama = OllamaClient(self.config.config.ai)
        self.memory = MemoryStore(
            Path.home() / ".local" / "share" / "Jarvis" / "memory.sqlite3",
            self.config.config.memory.memory_enabled,
        )
        self.system = SystemMonitor()
        self.launcher = AppLauncher(self.config, self.safety)
        self.screenshot = ScreenshotService(root / "screenshots")
        self.screen_analyzer = ScreenAnalyzer(self.screenshot, self.ollama)
        self.input = InputController()
        self.voice = VoiceEngine(self.config, self.bus, self.models_dir)
        self.vision = VisionEngine(self.config, self.bus, self.input, self.models_dir)

        context = ToolContext(
            config=self.config,
            safety=self.safety,
            memory=self.memory,
            bus=self.bus,
            open_app=self.launcher.open_app,
            close_window=self.launcher.close_window,
            open_project=self.launcher.open_project,
            system_status=self.system.status,
            screenshot=self.screenshot.capture,
            describe_screen=self.screen_analyzer.analyse,
            input_control=self.input,
            vision_control=self.vision,
            voice_control=self.voice,
            set_sleeping=self.brain_set_sleeping,
            shutdown=self.stop,
        )
        self.tools = ToolRegistry(context)
        self.brain = Brain(self.config, self.bus, self.memory, self.ollama, self.tools)
        self.voice.set_on_wake(self._on_wake)
        self._running = False
        self._request_lock = threading.Lock()
        self._generation = 0

    # ---- lifecycle ----------------------------------------------------

    def brain_set_sleeping(self, value: bool) -> None:
        self.brain.set_sleeping(value)

    def start(self) -> None:
        """Start background subsystems."""
        if self._running:
            return
        self._running = True
        self.voice.start()
        if self.config.config.vision.vision_enabled:
            self.vision.start()
        self.bus.publish(Event(type=EventType.STARTUP, source="jarvis"))
        self.log.info("Wednesday started")

    def stop(self) -> None:
        """Stop all subsystems and release hardware."""
        self.voice.stop()
        self.vision.stop()
        self._running = False
        self.bus.publish(Event(type=EventType.SHUTDOWN, source="jarvis"))
        self.log.info("Wednesday stopped")

    @property
    def running(self) -> bool:
        return self._running

    # ---- interaction --------------------------------------------------

    def process_text(self, text: str, speak: bool = True) -> str:
        """Process typed or transcribed text and optionally speak the reply.

        A generation counter lets the Stop button discard a response that was
        still being generated when Stop was pressed.
        """
        with self._request_lock:
            generation = self._generation
        reply = self.brain.respond(text)
        with self._request_lock:
            cancelled = generation != self._generation
        if cancelled:
            return ""
        if speak and reply:
            self.voice.say(reply)
        return reply

    def stop_all(self) -> None:
        """Cancel in-flight listening, AI generation and speech playback."""
        with self._request_lock:
            self._generation += 1
        self.voice.stop_listening()
        self.voice.stop_speaking()
        self.bus.emit(EventType.STATUS, {"message": "Stopped"}, "jarvis")
        self.log.info("Stop requested")

    def voice_command(self, seconds: float | None = None) -> str:
        """Record one phrase, transcribe it and respond."""
        transcript = self.voice.listen_once(seconds)
        if transcript.is_empty:
            return "I did not catch that."
        return self.process_text(transcript.text)

    def _on_wake(self) -> None:
        self.voice.say("Yes?")
        self.voice_command()

    def set_confirmation_handler(self, handler: Any) -> None:
        self.safety.set_confirmation_handler(handler)

    def emergency_stop(self) -> None:
        self.safety.emergency_stop()
        self.voice.stop_speaking()

    # ---- diagnostics --------------------------------------------------

    def doctor(self, probe_cameras: bool = True) -> dict[str, Any]:
        """Return a structured health report for the CLI and UI.

        The periodic UI refresh skips camera probing: opening six V4L2 devices
        every 30 s produces OpenCV warnings and needless CPU work.
        """
        cfg = self.config.config
        vision_cameras = []
        if probe_cameras:
            try:
                from vision.camera import Camera

                vision_cameras = Camera.list_cameras()
            except Exception as exc:
                self.log.debug("Camera probe failed: %s", exc)
        online = self.ollama.is_available()
        return {
            "ollama_running": online,
            "ollama_models": self.ollama.list_models() if online else [],
            "microphones": self.voice.list_microphones(),
            "cameras": vision_cameras,
            "vision_running": self.vision.camera_open,
            "tts_voice_present": self.voice._tts.available,
            "wake_models_present": self.voice._wake.available,
            "stt_model": cfg.voice.stt_model,
            "input_backend": self.input.backend,
            "tracking_mode": self.vision.mode,
            "gaze_calibrated": self.vision.calibrated,
            "session_type": os.environ.get("XDG_SESSION_TYPE", "unknown"),
            "memory": self.memory.counts(),
            "system": self.system.status(),
        }

    def status_summary(self) -> str:
        """Return a short human-readable status line."""
        report = self.doctor()
        return (
            f"AI {'online' if report['ollama_running'] else 'offline'} | "
            f"Mic {len(report['microphones'])} | Cam {len(report['cameras'])} | "
            f"Tracking {report['tracking_mode']} | "
            f"Input {report['input_backend']}"
        )
