"""Reusable UI widgets for the JARVIS interface."""

from __future__ import annotations

import customtkinter as ctk

ACCENT = "#00D4FF"
ACCENT_DARK = "#0089A8"
SUCCESS = "#3DDC84"
WARNING = "#FFB020"
DANGER = "#FF4D5E"
BG = "#070B12"
PANEL = "#0E1520"
PANEL_LIGHT = "#151F2E"
TEXT = "#E8F1FF"
MUTED = "#8FA3BF"


def panel(parent: ctk.CTkBaseClass, **kwargs: object) -> ctk.CTkFrame:
    """Create a consistently styled card frame."""
    return ctk.CTkFrame(
        parent,
        fg_color=PANEL,
        corner_radius=14,
        border_width=1,
        border_color="#1C2C42",
        **kwargs,
    )


def label(parent: ctk.CTkBaseClass, text: str, size: int = 14, **kwargs: object) -> ctk.CTkLabel:
    """Create a label with default typography."""
    weight = kwargs.pop("weight", "normal")
    return ctk.CTkLabel(
        parent,
        text=text,
        font=ctk.CTkFont(size=size, weight=weight),
        text_color=kwargs.pop("text_color", TEXT),
        **kwargs,
    )


def status_pill(parent: ctk.CTkBaseClass, text: str, ok: bool) -> ctk.CTkLabel:
    """Create a coloured status indicator."""
    return ctk.CTkLabel(
        parent,
        text=f"● {text}",
        font=ctk.CTkFont(size=12, weight="bold"),
        text_color=SUCCESS if ok else MUTED,
    )


def action_button(parent: ctk.CTkBaseClass, text: str, command: object, **kwargs: object) -> ctk.CTkButton:
    """Create a primary action button."""
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        fg_color=ACCENT_DARK,
        hover_color=ACCENT,
        text_color="#031018",
        font=ctk.CTkFont(size=13, weight="bold"),
        corner_radius=10,
        height=36,
        **kwargs,
    )
