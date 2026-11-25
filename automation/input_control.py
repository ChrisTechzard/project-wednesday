"""Desktop pointer and keyboard injection for Wayland via the RemoteDesktop portal."""

from __future__ import annotations

import threading
from typing import Any

from core.logging import get_logger
from core.portal import (
    PORTAL_NAME,
    GLib,
    PortalError,
    PortalRequest,
    call,
    new_token,
    owner_check,
    predicted_handle,
)

INTERFACE = "org.freedesktop.portal.RemoteDesktop"
DEVICE_KEYBOARD = 1
DEVICE_POINTER = 2

KEYSYMS: dict[str, int] = {
    "enter": 0xFF0D,
    "return": 0xFF0D,
    "tab": 0xFF09,
    "escape": 0xFF1B,
    "esc": 0xFF1B,
    "space": 0x0020,
    "backspace": 0xFF08,
    "delete": 0xFFFF,
    "up": 0xFF52,
    "down": 0xFF54,
    "left": 0xFF51,
    "right": 0xFF53,
    "ctrl": 0xFFE3,
    "control": 0xFFE3,
    "shift": 0xFFE1,
    "alt": 0xFFE9,
    "super": 0xFFEB,
}

_BUTTONS = {"left": 1, "middle": 2, "right": 3}


class InputController:
    """Inject mouse and keyboard events through an authorised portal session.

    The portal shows a one-time consent dialog; no root access or uinput
    permissions are required, which is why it is preferred on Wayland.
    """

    def __init__(self) -> None:
        self._log = get_logger("input")
        self._session: str | None = None
        self._lock = threading.RLock()
        self._x = 0.0
        self._y = 0.0

    @property
    def available(self) -> bool:
        return self._session is not None

    @property
    def backend(self) -> str:
        if self.available:
            return "freedesktop RemoteDesktop portal"
        try:
            if owner_check(PORTAL_NAME):
                return "freedesktop portal (consent required)"
        except Exception:
            pass
        return "unavailable"

    def initialize(self, timeout_seconds: float = 90.0) -> bool:
        """Request a remote-control session. May display a consent dialog."""
        with self._lock:
            if self._session is not None:
                return True
            try:
                def request(method: str, signature: str, *args: Any, options: dict[str, Any] | None = None) -> dict[str, Any]:
                    """Call a portal method and wait for its Response signal."""
                    token = new_token()
                    opts = dict(options or {})
                    opts["handle_token"] = GLib.Variant("s", token)
                    pending = PortalRequest(predicted_handle(token), timeout_seconds)
                    pending.subscribe()  # before the call, to avoid a reply race
                    call_args = (opts,) if signature == "a{sv}" and not args else (*args, opts)
                    (handle,) = call(INTERFACE, method, signature, *call_args)
                    if handle != pending.handle:
                        pending.set_handle(handle)
                    return pending.wait()

                response = request(
                    "CreateSession",
                    "a{sv}",
                    options={"session_handle_token": GLib.Variant("s", new_token())},
                )
                session = str(response.get("session_handle", ""))
                if not session:
                    raise PortalError("Portal did not return a session handle.")

                request(
                    "SelectDevices",
                    "oa{sv}",
                    session,
                    options={"types": GLib.Variant("u", DEVICE_KEYBOARD | DEVICE_POINTER)},
                )
                request("Start", "osa{sv}", session, "")

                self._session = session
                self._log.info("RemoteDesktop portal session established: %s", session)
                return True
            except PortalError as exc:
                self._log.warning("RemoteDesktop portal unavailable: %s", exc)
                return False

    def _require_session(self) -> str:
        if self._session is None:
            raise RuntimeError("Desktop input control is not active. Enable it in Settings first.")
        return self._session

    def move(self, x: int, y: int) -> None:
        """Move the pointer by a relative delta."""
        session = self._require_session()
        dx, dy = float(x) - self._x, float(y) - self._y
        self._x, self._y = float(x), float(y)
        call(INTERFACE, "NotifyPointerMotion", "oa{sv}dd", session, {}, dx, dy)

    def move_relative(self, dx: float, dy: float) -> None:
        """Move the pointer by an explicit relative delta."""
        session = self._require_session()
        call(INTERFACE, "NotifyPointerMotion", "oa{sv}dd", session, {}, float(dx), float(dy))
        self._x += dx
        self._y += dy

    def scroll(self, steps: int) -> None:
        """Scroll vertically using discrete axis steps."""
        session = self._require_session()
        call(INTERFACE, "NotifyPointerAxisDiscrete", "oa{sv}ui", session, {}, 1, int(steps))

    def click(self, button: str = "left") -> None:
        """Press and release a mouse button."""
        session = self._require_session()
        code = _BUTTONS.get(button.lower(), 1)
        call(INTERFACE, "NotifyPointerButton", "oa{sv}iu", session, {}, code, 1)
        call(INTERFACE, "NotifyPointerButton", "oa{sv}iu", session, {}, code, 0)

    def key(self, combination: str) -> None:
        """Send a key combination such as 'ctrl+shift+j'."""
        session = self._require_session()
        parts = [part.strip().lower() for part in combination.split("+") if part.strip()]
        if not parts:
            raise ValueError("No key specified.")
        codes: list[int] = []
        for part in parts:
            if part in KEYSYMS:
                codes.append(KEYSYMS[part])
            elif len(part) == 1 and part.isprintable():
                codes.append(ord(part))
            else:
                raise ValueError(f"Unsupported key: {part}")
        for code in codes:
            call(INTERFACE, "NotifyKeyboardKeysym", "oa{sv}iu", session, {}, code, 1)
        for code in reversed(codes):
            call(INTERFACE, "NotifyKeyboardKeysym", "oa{sv}iu", session, {}, code, 0)

    def type_text(self, text: str) -> None:
        """Type plain text by sending one keysym per character."""
        for char in text:
            if char == "\n":
                self.key("enter")
            elif char != "\r":
                self.key(char)
