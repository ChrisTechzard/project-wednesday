"""Reusable UI widgets for the Wednesday interface."""

from __future__ import annotations

import tkinter
from collections.abc import Callable
from tkinter import TclError

import customtkinter as ctk

ACCENT = "#00D4FF"
ACCENT_DARK = "#0089A8"
SUCCESS = "#3DDC84"
WARNING = "#FFB020"
DANGER = "#FF4D5E"
BG = "#070B12"
PANEL = "#0E1520"
PANEL_LIGHT = "#151F2E"
TEXT = "#F8FAFC"
MUTED = "#9FB2CC"
BORDER = "#334155"
FOCUS = "#FFFFFF"


def panel(parent: ctk.CTkBaseClass, **kwargs: object) -> ctk.CTkFrame:
    """Create a consistently styled card frame."""
    return ctk.CTkFrame(
        parent,
        fg_color=PANEL,
        corner_radius=14,
        border_width=1,
        border_color=BORDER,
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
    """Create a status indicator whose wording, not just colour, carries meaning."""
    return ctk.CTkLabel(
        parent,
        text=text,
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=SUCCESS if ok else MUTED,
    )


def _focus_target(widget: ctk.CTkBaseClass) -> tkinter.Misc:
    """Return the inner Tk widget that actually receives keyboard focus."""
    for attribute in ("_text_label", "_entry", "_textbox", "_canvas"):
        target = getattr(widget, attribute, None)
        if isinstance(target, tkinter.Misc):
            return target
    return widget


def bind_focus_ring(widget: ctk.CTkBaseClass) -> None:
    """Show a visible border while a CustomTkinter control has keyboard focus.

    CustomTkinter draws its own border, so the usual Tk focus outline is not
    enough. Binding the inner focus target keeps the ring visible for buttons
    and check boxes too.
    """
    try:
        original_width = int(widget.cget("border_width"))
        original_color = widget.cget("border_color")
    except (AttributeError, TclError, TypeError, ValueError):
        return

    target = _focus_target(widget)

    def focus_in(_event: object | None = None) -> None:
        widget.configure(border_width=2, border_color=FOCUS)

    def focus_out(_event: object | None = None) -> None:
        widget.configure(border_width=original_width, border_color=original_color)

    target.bind("<FocusIn>", focus_in, add="+")
    target.bind("<FocusOut>", focus_out, add="+")


def center_window(window: ctk.CTkBaseClass, parent: ctk.CTkBaseClass) -> None:
    """Centre a dialog over its parent without relying on the WM."""
    window.update_idletasks()
    parent.update_idletasks()
    width = window.winfo_reqwidth() or 440
    height = window.winfo_reqheight() or 220
    parent_width = parent.winfo_width()
    parent_height = parent.winfo_height()
    if parent_width <= 1:
        parent_width = parent.winfo_reqwidth()
    if parent_height <= 1:
        parent_height = parent.winfo_reqheight()
    x = parent.winfo_rootx() + max(0, (parent_width - width) // 2)
    y = parent.winfo_rooty() + max(0, (parent_height - height) // 2)
    window.geometry(f"+{max(0, x)}+{max(0, y)}")


def _button(
    parent: ctk.CTkBaseClass,
    text: str,
    command: Callable[[], object] | None,
    fg_color: str,
    hover_color: str,
    text_color: str,
    **kwargs: object,
) -> ctk.CTkButton:
    kwargs.setdefault("height", 40)
    button = ctk.CTkButton(
        parent,
        text=text,
        command=command,
        fg_color=fg_color,
        hover_color=hover_color,
        text_color=text_color,
        font=ctk.CTkFont(size=13, weight="bold"),
        corner_radius=10,
        **kwargs,
    )
    bind_focus_ring(button)
    return button


def action_button(parent: ctk.CTkBaseClass, text: str, command: Callable[[], object] | None, **kwargs: object) -> ctk.CTkButton:
    """Create a primary action button."""
    return _button(parent, text, command, ACCENT_DARK, ACCENT, "#031018", **kwargs)


def secondary_button(parent: ctk.CTkBaseClass, text: str, command: Callable[[], object] | None, **kwargs: object) -> ctk.CTkButton:
    """Create a lower-emphasis button for cancel and refresh actions."""
    return _button(parent, text, command, PANEL_LIGHT, "#223049", TEXT, **kwargs)


def danger_button(parent: ctk.CTkBaseClass, text: str, command: Callable[[], object] | None, **kwargs: object) -> ctk.CTkButton:
    """Create a button for destructive or stopping actions."""
    return _button(parent, text, command, DANGER, "#C42E3E", "#FFFFFF", **kwargs)
