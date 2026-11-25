"""Shared typed data models used across JARVIS components."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """Names of events published on the application event bus."""

    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    STATUS = "status"
    TRANSCRIPT = "transcript"
    SPEAKING = "speaking"
    WAKE_WORD = "wake_word"
    RESPONSE = "response"
    TOOL_REQUEST = "tool_request"
    TOOL_RESULT = "tool_result"
    CONFIRMATION_REQUIRED = "confirmation_required"
    VISION_FRAME = "vision_frame"
    TRACKING_STATE = "tracking_state"
    DWELL_PROGRESS = "dwell_progress"
    SELECTION = "selection"
    SCREENSHOT = "screenshot"
    ERROR = "error"
    LOG = "log"


@dataclass(frozen=True, slots=True)
class Event:
    """Immutable event passed through the event bus."""

    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class Transcript:
    """A speech recognition result."""

    text: str
    source: str = "microphone"
    confidence: float = 0.0
    duration_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


class RiskLevel(str, Enum):
    """Risk classification for tool operations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class ToolRequest:
    """A requested action from the AI or user interface."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The outcome of a tool execution."""

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    tool: str = ""


@dataclass(frozen=True, slots=True)
class SystemStatus:
    """Snapshot of host metrics."""

    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    disk_percent: float
    disk_free_gb: float
    online: bool
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class TrackingState:
    """Current computer-vision tracking state."""

    face_detected: bool = False
    head_x: float = 0.0  # normalised -1..1
    head_y: float = 0.0
    gaze_x: float = 0.5  # normalised 0..1 screen coordinates
    gaze_y: float = 0.5
    confidence: float = 0.0
    blink: bool = False
    calibrated: bool = False
    mode: str = "off"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One message in the conversation history."""

    role: str  # system | user | assistant | tool
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_ollama(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}
