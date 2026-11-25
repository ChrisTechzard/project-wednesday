"""Event bus and safety policy tests."""

from __future__ import annotations

import time

from core.models import EventType, RiskLevel, ToolRequest
from core.safety import EmergencyStop


def test_event_bus_filters_and_delivers(bus) -> None:
    seen: list[str] = []
    bus.subscribe(lambda event: seen.append(event.payload["value"]), EventType.STATUS)
    bus.subscribe(lambda event: seen.append("ALL:" + event.type.value))
    bus.emit(EventType.ERROR, {"value": "ignored"})
    bus.emit(EventType.STATUS, {"value": "ok"})
    deadline = time.time() + 2
    while time.time() < deadline and len(seen) < 2:
        time.sleep(0.01)
    assert "ok" in seen
    assert "ALL:error" in seen
    assert "ALL:status" in seen


def test_risk_classification(safety) -> None:
    assert safety.classify("open_application") == RiskLevel.LOW
    assert safety.classify("mouse_click") == RiskLevel.MEDIUM
    assert safety.classify("run_shell") == RiskLevel.HIGH
    assert safety.classify("delete_file") == RiskLevel.HIGH


def test_high_risk_tools_are_blocked(safety) -> None:
    result = safety.authorize(ToolRequest(name="delete_file", arguments={"path": "/tmp/x"}))
    assert result is not None and result.success is False


def test_emergency_stop_blocks_all_actions(safety) -> None:
    safety.emergency_stop()
    try:
        safety.check_stopped()
    except EmergencyStop:
        pass
    else:
        raise AssertionError("Expected EmergencyStop")
    try:
        safety.authorize(ToolRequest(name="open_application", arguments={"name": "firefox"}))
    except EmergencyStop:
        pass
    else:
        raise AssertionError("Expected authorize() to raise EmergencyStop")
    safety.clear_stop()
    assert safety.authorize(ToolRequest(name="open_application", arguments={"name": "firefox"})) is None


def test_audit_log_written(safety, tmp_path) -> None:
    from core.models import ToolResult

    safety.audit("open_application", ToolResult(True, "opened", tool="open_application"))
    path = tmp_path / "logs" / "actions.jsonl"
    assert path.exists()
    assert "open_application" in path.read_text(encoding="utf-8")
