"""Application and project launching with confirmations for risky operations."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import psutil

from core.config import ConfigManager
from core.logging import get_logger
from core.models import ToolResult
from core.safety import SafetyManager


class AppLauncher:
    """Launch desktop applications and configured projects."""

    def __init__(self, config: ConfigManager, safety: SafetyManager) -> None:
        self._config = config
        self._safety = safety
        self._log = get_logger("launcher")

    def resolve(self, name: str) -> str | None:
        """Map a friendly name to an executable using configured aliases."""
        aliases = self._config.config.automation.app_aliases
        key = name.strip().lower()
        command = aliases.get(key)
        if command is None:
            for alias, target in aliases.items():
                if alias in key or key in alias:
                    command = target
                    break
        if command is None:
            command = key.split()[0] if key else ""
        if not command:
            return None
        return command if shutil.which(command) else None

    def list_applications(self) -> list[str]:
        """Return configured application aliases."""
        return sorted(self._config.config.automation.app_aliases)

    def open_app(self, name: str) -> ToolResult:
        """Launch or focus a named application."""
        command = self.resolve(name)
        if command is None:
            known = ", ".join(self.list_applications())
            return ToolResult(False, f"I don't know how to open '{name}'. Known apps: {known}.", tool="open_application")
        try:
            subprocess.Popen(
                [command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env={**os.environ},
            )
        except OSError as exc:
            return ToolResult(False, f"Could not launch {command}: {exc}", tool="open_application")
        self._log.info("Launched application: %s (%s)", name, command)
        return ToolResult(True, f"Opening {name}.", {"command": command}, "open_application")

    def open_project(self, name: str) -> ToolResult:
        """Open a configured project folder in the preferred editor."""
        projects = self._config.config.automation.project_paths
        path: Path | None = None
        for key, value in projects.items():
            if name.strip().lower() in key.lower() or key.lower() in name.strip().lower():
                path = Path(value).expanduser()
                break
        if path is None:
            known = ", ".join(projects) or "none configured"
            return ToolResult(False, f"No project named '{name}' is configured. Known projects: {known}.", tool="open_project")
        if not path.is_dir():
            return ToolResult(False, f"Project folder does not exist: {path}", tool="open_project")
        editor = "code" if shutil.which("code") else "nautilus"
        try:
            subprocess.Popen(
                [editor, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            return ToolResult(False, f"Could not open project: {exc}", tool="open_project")
        return ToolResult(True, f"Opening project {name} in {editor}.", {"path": str(path)}, "open_project")

    def close_window(self, name: str) -> ToolResult:
        """Terminate the process matching an application name after confirmation."""
        if not name.strip():
            return ToolResult(False, "No application was specified.", tool="close_window")
        approved = self._safety.confirm_high_risk("Close application?", f"This will terminate processes matching '{name}'.")
        if not approved:
            return ToolResult(False, "Close cancelled.", tool="close_window")
        closed: list[str] = []
        for process in psutil.process_iter(["name", "cmdline"]):
            try:
                text = " ".join(process.info.get("cmdline") or []) + " " + (process.info.get("name") or "")
                if name.lower() in text.lower() and process.pid != os.getpid():
                    process.terminate()
                    closed.append(process.info.get("name") or str(process.pid))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if not closed:
            return ToolResult(False, f"No running process matched '{name}'.", tool="close_window")
        return ToolResult(True, f"Closed: {', '.join(closed[:5])}.", {"closed": closed}, "close_window")

    def is_running(self, name: str) -> bool:
        """Check whether a process name is present."""
        return any(
            name.lower() in (process.info.get("name") or "").lower()
            for process in psutil.process_iter(["name"])
        )
