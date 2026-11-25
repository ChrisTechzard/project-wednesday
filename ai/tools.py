"""Typed tool registry: the only bridge between AI reasoning and system actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from core.config import ConfigManager
from core.events import EventBus
from core.logging import get_logger
from core.models import EventType, RiskLevel, ToolRequest, ToolResult
from core.safety import EmergencyStop, SafetyManager

from ai.memory import MemoryStore

ScreenshotFn = Callable[[], tuple[bool, str]]
ScreenDescribeFn = Callable[[str], str]


@dataclass(slots=True)
class ToolContext:
    """Dependencies injected into tool handlers."""

    config: ConfigManager
    safety: SafetyManager
    memory: MemoryStore
    bus: EventBus
    open_app: Callable[[str], ToolResult]
    close_window: Callable[[str], ToolResult]
    open_project: Callable[[str], ToolResult]
    system_status: Callable[[], dict[str, Any]]
    screenshot: ScreenshotFn
    describe_screen: ScreenDescribeFn
    input_control: Any = None
    vision_control: Any = None
    voice_control: Any = None
    set_sleeping: Callable[[bool], None] = lambda value: None
    shutdown: Callable[[], None] = lambda: None


class ToolRegistry:
    """Executes named tools with safety checks, validation and audit logging."""

    SCHEMAS: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "get_system_status",
                "description": "Get current CPU, memory, disk and network status.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "open_application",
                "description": "Open or focus a desktop application by name.",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "Application name"}},
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "open_project",
                "description": "Open a configured project folder in the editor.",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Open a web search in the default browser.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "take_screenshot",
                "description": "Capture the current screen and save it to the screenshots folder.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "describe_screen",
                "description": "Analyse the current screen with OCR/vision and answer a question about it.",
                "parameters": {
                    "type": "object",
                    "properties": {"question": {"type": "string"}},
                    "required": ["question"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remember",
                "description": "Save a non-sensitive fact to memory.",
                "parameters": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                    "required": ["key", "value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "recall",
                "description": "Recall a stored fact.",
                "parameters": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_memories",
                "description": "List everything currently stored in memory.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "forget",
                "description": "Delete one stored memory.",
                "parameters": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "clear_memory",
                "description": "Delete all memories and conversation context (requires confirmation).",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_tracking",
                "description": "Enable or disable head or gaze cursor control.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": ["head", "gaze", "off"]},
                        "enabled": {"type": "boolean"},
                    },
                    "required": ["mode"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "go_to_sleep",
                "description": "Disable wake-word listening until the user wakes JARVIS.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
    ]

    def __init__(self, context: ToolContext) -> None:
        self._ctx = context
        self._log = get_logger("tools")
        self._handlers: dict[str, Callable[[dict[str, Any]], ToolResult]] = {
            "get_system_status": self._system_status,
            "get_time": self._get_time,
            "open_application": self._open_application,
            "close_window": self._close_window,
            "open_project": self._open_project,
            "search_web": self._search_web,
            "take_screenshot": self._take_screenshot,
            "describe_screen": self._describe_screen,
            "remember": self._remember,
            "recall": self._recall,
            "list_memories": self._list_memories,
            "forget": self._forget,
            "clear_memory": self._clear_memory,
            "set_tracking": self._set_tracking,
            "mouse_move": self._mouse_move,
            "mouse_click": self._mouse_click,
            "key_press": self._key_press,
            "stop_speaking": self._stop_speaking,
            "go_to_sleep": self._go_to_sleep,
            "shutdown_assistant": self._shutdown,
        }

    def execute(self, request: ToolRequest) -> ToolResult:
        """Validate, authorize, execute and audit a tool request."""
        handler = self._handlers.get(request.name)
        if handler is None:
            result = ToolResult(False, f"Unknown tool '{request.name}'.", tool=request.name)
            self._ctx.safety.audit(request.name, result)
            return result

        denial = self._ctx.safety.authorize(request)
        if denial is not None:
            self._ctx.safety.audit(request.name, denial)
            return denial

        try:
            result = handler(dict(request.arguments))
        except EmergencyStop:
            raise
        except Exception as exc:
            self._log.exception("Tool %s failed: %s", request.name, exc)
            result = ToolResult(False, f"{request.name} failed: {exc}", tool=request.name)
        self._ctx.safety.audit(request.name, result)
        self._ctx.bus.emit(
            EventType.TOOL_RESULT,
            {"tool": request.name, "success": result.success, "message": result.message},
            "tools",
        )
        return result

    # ---- handlers -----------------------------------------------------

    def _system_status(self, args: dict[str, Any]) -> ToolResult:
        status = self._ctx.system_status()
        message = (
            f"CPU {status.get('cpu_percent', 0):.0f}%, "
            f"RAM {status.get('memory_percent', 0):.0f}%, "
            f"Disk {status.get('disk_percent', 0):.0f}% used, "
            f"network {'online' if status.get('online') else 'offline'}."
        )
        return ToolResult(True, message, status, "get_system_status")

    def _get_time(self, args: dict[str, Any]) -> ToolResult:
        now = datetime.now().strftime("%A, %d %B %Y at %H:%M")
        return ToolResult(True, f"The time is {now}.", {"time": now}, "get_time")

    def _open_application(self, args: dict[str, Any]) -> ToolResult:
        name = str(args.get("name", "")).strip()
        if not name:
            return ToolResult(False, "No application name was provided.", tool="open_application")
        return self._ctx.open_app(name)

    def _close_window(self, args: dict[str, Any]) -> ToolResult:
        return self._ctx.close_window(str(args.get("name", "")))

    def _open_project(self, args: dict[str, Any]) -> ToolResult:
        return self._ctx.open_project(str(args.get("name", "")))

    def _search_web(self, args: dict[str, Any]) -> ToolResult:
        from urllib.parse import quote_plus

        import webbrowser

        query = str(args.get("query", "")).strip()
        if not query:
            return ToolResult(False, "No search query was provided.", tool="search_web")
        try:
            webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
            return ToolResult(True, f"Searching the web for '{query}'.", {"query": query}, "search_web")
        except Exception as exc:
            return ToolResult(False, f"Could not open browser: {exc}", tool="search_web")

    def _take_screenshot(self, args: dict[str, Any]) -> ToolResult:
        success, message = self._ctx.screenshot()
        return ToolResult(success, message, tool="take_screenshot")

    def _describe_screen(self, args: dict[str, Any]) -> ToolResult:
        question = str(args.get("question", "What is on the screen?"))
        answer = self._ctx.describe_screen(question)
        return ToolResult(bool(answer), answer, tool="describe_screen")

    def _remember(self, args: dict[str, Any]) -> ToolResult:
        message = self._ctx.memory.remember(str(args.get("key", "")), str(args.get("value", "")))
        return ToolResult(not message.startswith("I will not") and not message.startswith("Nothing"), message, tool="remember")

    def _recall(self, args: dict[str, Any]) -> ToolResult:
        message = self._ctx.memory.recall(str(args.get("key", "")))
        return ToolResult("no memory" not in message.lower(), message, tool="recall")

    def _list_memories(self, args: dict[str, Any]) -> ToolResult:
        items = self._ctx.memory.list_all()
        message = "I have no stored memories." if not items else "\n".join(
            f"- {item['key']}: {item['value']}" for item in items
        )
        return ToolResult(True, message, {"items": items}, "list_memories")

    def _forget(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(True, self._ctx.memory.forget(str(args.get("key", ""))), tool="forget")

    def _clear_memory(self, args: dict[str, Any]) -> ToolResult:
        approved = self._ctx.safety.confirm_high_risk("Clear all memories?", "This deletes all saved facts and chat context.")
        if not approved:
            return ToolResult(False, "Clear memory was cancelled.", tool="clear_memory")
        return ToolResult(True, self._ctx.memory.clear(), tool="clear_memory")

    def _set_tracking(self, args: dict[str, Any]) -> ToolResult:
        mode = str(args.get("mode", "off")).lower()
        enabled = bool(args.get("enabled", mode != "off"))
        controller = self._ctx.vision_control
        if controller is None:
            return ToolResult(False, "Vision tracking is not available.", tool="set_tracking")
        ok = controller.set_mode("off" if mode == "off" else mode, enabled)
        return ToolResult(ok, f"Tracking mode set to {mode if enabled else 'off'}.", tool="set_tracking")

    def _mouse_move(self, args: dict[str, Any]) -> ToolResult:
        if self._ctx.input_control is None:
            return ToolResult(False, "Desktop input control is not available on this session.", tool="mouse_move")
        try:
            self._ctx.input_control.move(int(args["x"]), int(args["y"]))
            return ToolResult(True, "Pointer moved.", tool="mouse_move")
        except (KeyError, ValueError, TypeError, RuntimeError) as exc:
            return ToolResult(False, f"Could not move pointer: {exc}", tool="mouse_move")

    def _mouse_click(self, args: dict[str, Any]) -> ToolResult:
        if self._ctx.input_control is None:
            return ToolResult(False, "Desktop input control is not available on this session.", tool="mouse_click")
        try:
            self._ctx.input_control.click(str(args.get("button", "left")))
            return ToolResult(True, "Clicked.", tool="mouse_click")
        except RuntimeError as exc:
            return ToolResult(False, f"Could not click: {exc}", tool="mouse_click")

    def _key_press(self, args: dict[str, Any]) -> ToolResult:
        if self._ctx.input_control is None:
            return ToolResult(False, "Desktop input control is not available on this session.", tool="key_press")
        try:
            self._ctx.input_control.key(str(args.get("keys", "")))
            return ToolResult(True, "Key combination sent.", tool="key_press")
        except RuntimeError as exc:
            return ToolResult(False, f"Could not send keys: {exc}", tool="key_press")

    def _stop_speaking(self, args: dict[str, Any]) -> ToolResult:
        if self._ctx.voice_control is not None:
            self._ctx.voice_control.stop_speaking()
        return ToolResult(True, "Speech stopped.", tool="stop_speaking")

    def _go_to_sleep(self, args: dict[str, Any]) -> ToolResult:
        self._ctx.set_sleeping(True)
        return ToolResult(True, "Going to sleep. Say 'Jarvis, wake up' when you need me.", tool="go_to_sleep")

    def _shutdown(self, args: dict[str, Any]) -> ToolResult:
        self._ctx.shutdown()
        return ToolResult(True, "Shutting down JARVIS.", tool="shutdown_assistant")
