"""GNOME portal helpers using the system GObject bindings.

The venv deliberately stays free of system packages; this module adds the
system dist-packages path only for GI, then uses DBus portals which are the
supported way to capture the screen and inject input on Wayland.
"""

from __future__ import annotations

import sys
import threading
import uuid
from pathlib import Path
from typing import Any

SYSTEM_DIST_PACKAGES = Path("/usr/lib/python3/dist-packages")
if SYSTEM_DIST_PACKAGES.exists() and str(SYSTEM_DIST_PACKAGES) not in sys.path:
    sys.path.append(str(SYSTEM_DIST_PACKAGES))

import gi  # noqa: E402

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

PORTAL_NAME = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"
RESPONSE_MEMBER = "Response"


class PortalError(RuntimeError):
    """Raised when a portal request fails or is denied."""


def new_token() -> str:
    """Return a unique portal handle token."""
    return f"jarvis_{uuid.uuid4().hex[:12]}"


def predicted_handle(token: str) -> str:
    """Return the DBus object path a portal will use for ``handle_token``."""
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    sender = bus.get_unique_name().replace(":", "").replace(".", "_")
    return f"{PORTAL_PATH}/request/{sender}/{token}"


def proxy(interface: str) -> Gio.DBusProxy:
    """Return a DBus proxy for a portal interface."""
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return Gio.DBusProxy.new_sync(
        bus,
        Gio.DBusProxyFlags.NONE,
        None,
        PORTAL_NAME,
        PORTAL_PATH,
        interface,
        None,
    )


def call(interface: str, method: str, signature: str, *args: Any, timeout_ms: int = 15000) -> tuple[Any, ...]:
    """Call a portal method synchronously with a GLib.Variant signature.

    ``signature`` describes the method's parameter list (e.g. ``sa{sv}``);
    Gio expects a single tuple variant, so it is wrapped in parentheses here.
    """
    target = proxy(interface)
    tuple_signature = signature if signature.startswith("(") else f"({signature})"
    variant = GLib.Variant(tuple_signature, args) if signature else None
    try:
        result = target.call_sync(method, variant, Gio.DBusCallFlags.NONE, timeout_ms, None)
        return tuple(result.unpack()) if result is not None else ()
    except GLib.Error as exc:
        raise PortalError(f"{interface}.{method} failed: {exc.message}") from exc


class PortalRequest:
    """Wait for a portal Request::Response signal in a bounded main loop.

    Subscribe **before** issuing the portal method call: if the user already
    granted permission, the portal can emit Response immediately and a
    subscribe-after-call race would miss it.
    """

    def __init__(self, handle: str, timeout_seconds: float = 60.0) -> None:
        self.handle = handle
        self.timeout_seconds = timeout_seconds
        self.response: dict[str, Any] | None = None
        self._loop: GLib.MainLoop | None = None
        self._subscription: int | None = None
        self._bus: Gio.DBusConnection | None = None

    def subscribe(self) -> None:
        """Subscribe to the Response signal for this handle."""
        if self._subscription is not None:
            return
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._subscription = self._bus.signal_subscribe(
            PORTAL_NAME,
            REQUEST_INTERFACE,
            RESPONSE_MEMBER,
            self.handle,
            None,
            Gio.DBusSignalFlags.NO_MATCH_RULE,
            self._on_signal,
            None,
        )

    def set_handle(self, handle: str) -> None:
        """Switch to a different handle (resubscribing if needed)."""
        if handle == self.handle:
            return
        if self._bus is not None and self._subscription is not None:
            self._bus.signal_unsubscribe(self._subscription)
        self._subscription = None
        self.handle = handle
        self.subscribe()

    def wait(self) -> dict[str, Any]:
        """Block until a response arrives or the timeout expires."""
        self.subscribe()
        self._loop = GLib.MainLoop()
        timer = threading.Timer(self.timeout_seconds, self._stop)
        timer.daemon = True
        timer.start()
        try:
            self._loop.run()
        finally:
            timer.cancel()
            if self._bus is not None and self._subscription is not None:
                self._bus.signal_unsubscribe(self._subscription)
                self._subscription = None
        if self.response is None:
            raise PortalError("Portal request timed out or was cancelled.")
        if int(self.response.get("response", 1)) != 0:
            raise PortalError(f"Portal request denied: {self.response}")
        return self.response

    def _on_signal(self, _bus: Any, _sender: str, _path: str, _interface: str, _signal: str, params: Any, _data: Any) -> None:
        unpacked = params.unpack() if isinstance(params, GLib.Variant) else params
        if isinstance(unpacked, dict):
            self.response = unpacked
        elif isinstance(unpacked, (tuple, list)) and len(unpacked) >= 2 and isinstance(unpacked[1], dict):
            # org.freedesktop.portal.Request::Response is (uint32 response, a{sv} results)
            self.response = dict(unpacked[1])
            self.response["response"] = unpacked[0]
        else:
            self.response = {}
        self._stop()

    def _stop(self) -> None:
        if self._loop is not None and self._loop.is_running():
            self._loop.quit()


def request_response(handle: str, timeout_seconds: float = 60.0) -> dict[str, Any]:
    """Convenience wrapper around PortalRequest.wait()."""
    return PortalRequest(handle, timeout_seconds).wait()


def owner_check(name: str) -> bool:
    """Return True if a DBus name has an owner."""
    try:
        result = call("org.freedesktop.DBus.Peer", "Ping", "")
        _ = result
        return bool(name)
    except PortalError:
        return False
