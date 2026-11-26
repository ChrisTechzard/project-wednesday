"""Pure text helpers used by the conversation transcript."""

from __future__ import annotations

from datetime import datetime

USER_SPEAKER = "You"
ASSISTANT_SPEAKER = "Wednesday"


def format_transcript_line(
    speaker: str,
    text: str,
    timestamp: datetime | None = None,
) -> tuple[str, str]:
    """Return the text to insert and the tag used to style it."""
    stamp = (timestamp or datetime.now()).strftime("%H:%M")
    tag = "user" if speaker == USER_SPEAKER else "assistant"
    return f"[{stamp}] {speaker}: {text}\n\n", tag


def welcome_line(timestamp: datetime | None = None) -> str:
    """Return the first line shown in an empty transcript."""
    line, _ = format_transcript_line(
        ASSISTANT_SPEAKER,
        "Wednesday online. How can I help?",
        timestamp,
    )
    return line
