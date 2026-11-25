"""Brain routing and validated action-protocol tests."""

from __future__ import annotations

from ai.brain import Brain


def test_parse_action_valid() -> None:
    parsed = Brain._parse_action('ACTION: open_application {"name": "firefox"}')
    assert parsed == ("open_application", {"name": "firefox"})


def test_parse_action_rejects_hallucinated_tool() -> None:
    assert Brain._parse_action('ACTION: math {"op": "+"}') is None
    assert Brain._parse_action('ACTION: sudo_command {"cmd": "rm -rf /"}') is None


def test_parse_action_rejects_malformed_json() -> None:
    assert Brain._parse_action("ACTION: open_application {not json}") is None


def test_parse_action_ignores_plain_text() -> None:
    assert Brain._parse_action("The answer is 4.") is None
