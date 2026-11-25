"""Wednesday command-line entry point.

Usage:
    python app/main.py            # launch the graphical interface
    python app/main.py doctor     # run hardware/dependency diagnostics
    python app/main.py chat       # interactive text conversation
    python app/main.py say TEXT   # speak a sentence with offline TTS
    python app/main.py listen     # one-shot voice command
    python app/main.py voice      # headless wake-word listener (background)
    python app/main.py test       # run the automated test suite
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.jarvis import Jarvis  # noqa: E402

_active_app: Jarvis | None = None


def _shutdown(signum: int, _frame: object) -> None:
    """Handle SIGTERM/SIGINT so scripts/off.sh stops everything cleanly."""
    global _active_app
    if _active_app is not None:
        try:
            _active_app.stop()
        except Exception:
            pass
    raise SystemExit(0)


def _install_signal_handlers(app: Jarvis) -> None:
    global _active_app
    _active_app = app
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wednesday", description="Wednesday personal AI assistant")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("gui", help="launch the desktop interface (default)")
    sub.add_parser("doctor", help="report the health of every subsystem")
    sub.add_parser("chat", help="interactive text conversation in the terminal")
    sub.add_parser("listen", help="record one voice command and respond")
    sub.add_parser("voice", help="run headless wake-word background listener")
    sub.add_parser("test", help="run the pytest suite")
    say = sub.add_parser("say", help="speak text using offline Piper TTS")
    say.add_argument("text", nargs="+", help="text to speak")
    sub.add_parser("status", help="print a one-line status summary")
    return parser


def run_gui() -> int:
    import customtkinter as ctk

    from ui.main_window import MainWindow

    ctk.set_appearance_mode("dark")
    app = Jarvis()
    _install_signal_handlers(app)
    window = MainWindow(app)
    window.run()
    return 0


def run_doctor() -> int:
    app = Jarvis()
    report = app.doctor()
    print(json.dumps(report, indent=2, default=str))
    return 0


def run_chat() -> int:
    app = Jarvis()
    _install_signal_handlers(app)
    app.start()
    print("Wednesday terminal chat. Type 'quit' or 'exit' to stop.\n")
    try:
        while True:
            try:
                text = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text.lower() in {"quit", "exit", "shutdown"}:
                break
            reply = app.process_text(text, speak=False)
            print(f"Wednesday: {reply}\n")
    finally:
        app.stop()
    return 0


def run_listen() -> int:
    app = Jarvis()
    _install_signal_handlers(app)
    app.start()
    print("Listening for a voice command…")
    reply = app.voice_command()
    print(f"Wednesday: {reply}")
    app.stop()
    return 0


def run_say(words: list[str]) -> int:
    app = Jarvis()
    text = " ".join(words)
    ok = app.voice.speak_now(text)
    print(f"Spoke: {text}" if ok else "Speech output unavailable (check Piper model and audio device)")
    return 0 if ok else 1


def run_voice() -> int:
    app = Jarvis()
    _install_signal_handlers(app)
    app.start()
    app.voice.set_on_wake(app._on_wake)
    print("Wednesday headless wake-word listener active. Press Ctrl+C to stop.")
    try:
        while app.running:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
    return 0


def run_tests() -> int:
    import pytest

    return int(pytest.main([str(ROOT / "tests"), "-v"]))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "gui"
    handlers = {
        "gui": lambda: run_gui(),
        "doctor": run_doctor,
        "chat": run_chat,
        "listen": run_listen,
        "say": lambda: run_say(args.text),
        "voice": run_voice,
        "status": lambda: print(Jarvis().status_summary()) or 0,
        "test": run_tests,
    }
    return int(handlers[command]())


if __name__ == "__main__":
    raise SystemExit(main())
