"""Permission policy, confirmation workflow and action audit log."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import ConfigManager
from core.events import EventBus
from core.logging import get_logger
from core.models import Event, EventType, RiskLevel, ToolRequest, ToolResult

ConfirmationHandler = Callable[[str, str], bool]


class SafetyError(PermissionError):
    """Raised when an action is blocked by the safety policy."""


class EmergencyStop(Exception):
    """Raised when the user triggers the emergency stop."""


class SafetyManager:
    """Central gatekeeper for every tool and automation action."""

    HIGH_RISK_TOOLS = {
        "delete_file",
        "overwrite_file",
        "run_shell",
        "install_package",
        "system_setting",
        "send_message",
        "purchase",
        "sudo_command",
    }
    MEDIUM_RISK_TOOLS = {
        "keyboard_type",
        "mouse_click",
        "stop_process",
        "start_service",
        "close_window",
    }

    def __init__(self, config: ConfigManager, bus: EventBus, log_dir: Path) -> None:
        self._config = config
        self._bus = bus
        self._log = get_logger("safety")
        self._stop_event = threading.Event()
        self._confirmation_handler: ConfirmationHandler | None = None
        self._audit_path = log_dir / "actions.jsonl"
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        self._audit_lock = threading.Lock()

    def set_confirmation_handler(self, handler: ConfirmationHandler) -> None:
        """Install a UI callback used to ask the user for confirmation."""
        self._confirmation_handler = handler

    def emergency_stop(self) -> None:
        """Stop all automation immediately."""
        self._stop_event.set()
        self._log.critical("EMERGENCY STOP activated")
        self._bus.emit(EventType.STATUS, {"emergency_stop": True}, "safety")

    def clear_stop(self) -> None:
        """Clear the emergency stop flag after user acknowledgement."""
        self._stop_event.clear()
        self._bus.emit(EventType.STATUS, {"emergency_stop": False}, "safety")

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def check_stopped(self) -> None:
        """Raise EmergencyStop if the stop flag is set."""
        if self.stopped:
            raise EmergencyStop("Emergency stop is active — no actions permitted")

    def classify(self, tool_name: str, declared: RiskLevel | None = None) -> RiskLevel:
        """Classify a tool by policy, ignoring weaker declared risk."""
        cfg = self._config.config.automation
        if tool_name in self.HIGH_RISK_TOOLS:
            return RiskLevel.HIGH
        if tool_name in self.MEDIUM_RISK_TOOLS:
            return RiskLevel.MEDIUM
        if tool_name == "run_shell" and not cfg.allow_shell_commands:
            return RiskLevel.HIGH
        if tool_name == "delete_file" and not cfg.allow_file_deletion:
            return RiskLevel.HIGH
        return declared or RiskLevel.LOW

    def authorize(self, request: ToolRequest) -> ToolResult | None:
        """Return None when allowed, otherwise a blocking ToolResult."""
        self.check_stopped()
        cfg = self._config.config.automation
        if not cfg.automation_enabled:
            return ToolResult(False, "Automation is disabled in settings.", tool=request.name)
        risk = self.classify(request.name, request.risk)
        if risk is RiskLevel.HIGH:
            return ToolResult(False, f"'{request.name}' is blocked by the safety policy.", tool=request.name)
        if risk is RiskLevel.MEDIUM and cfg.require_confirmation:
            return self._ask(request, risk)
        return None

    def confirm_high_risk(self, description: str, details: str) -> bool:
        """Explicitly request confirmation for a high-risk user-initiated action."""
        self.check_stopped()
        if not self._config.config.automation.require_confirmation:
            self._log.warning("Confirmation prompts disabled; allowing high-risk action")
            return True
        return self._ask_confirmation(description, details)

    def _ask(self, request: ToolRequest, risk: RiskLevel) -> ToolResult | None:
        approved = self._ask_confirmation(f"Allow {request.name}?", request.reason or str(request.arguments))
        if approved:
            return None
        return ToolResult(False, "User declined the action.", tool=request.name)

    def _ask_confirmation(self, title: str, details: str) -> bool:
        self._bus.emit(
            EventType.CONFIRMATION_REQUIRED,
            {"title": title, "details": details},
            "safety",
        )
        if self._confirmation_handler is None:
            self._log.warning("No confirmation handler registered; denying '%s'", title)
            return False
        try:
            return bool(self._confirmation_handler(title, details))
        except Exception as exc:
            self._log.exception("Confirmation handler failed: %s", exc)
            return False

    def audit(self, tool: str, result: ToolResult, risk: RiskLevel | None = None) -> None:
        """Append a tool action to the JSONL audit log."""
        record: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "tool": tool,
            "success": result.success,
            "message": result.message[:500],
            "risk": (risk or self.classify(tool)).value,
            "data": result.data,
        }
        with self._audit_lock:
            with self._audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._bus.publish(
            Event(
                type=EventType.LOG,
                payload={"level": "info" if result.success else "warning", "message": f"{tool}: {result.message}"},
                source="safety",
            )
        )
