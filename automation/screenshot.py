"""Screen capture using the GNOME screenshot portal, with an X11 fallback."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from core.logging import get_logger
from core.portal import GLib, PortalError, PortalRequest, call, new_token, predicted_handle

INTERFACE = "org.freedesktop.portal.Screenshot"


class ScreenshotService:
    """Capture the screen and store images in the project's screenshots/ directory."""

    def __init__(self, output_dir: Path) -> None:
        self._dir = output_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._log = get_logger("screenshot")

    def capture(self, interactive: bool = False) -> tuple[bool, str]:
        """Capture the screen; return (success, path_or_error_message)."""
        path = self._dir / f"screenshot-{time.strftime('%Y%m%d-%H%M%S')}.png"
        if self._via_portal(path, interactive):
            return True, str(path)
        if self._via_x11(path):
            return True, str(path)
        return False, "Screen capture is unavailable: the screenshot portal was denied and no X11 display is usable."

    def _via_portal(self, path: Path, interactive: bool) -> bool:
        try:
            token = new_token()
            # Subscribe first: a remembered permission may reply immediately.
            request = PortalRequest(predicted_handle(token), timeout_seconds=90)
            request.subscribe()
            (handle,) = call(
                INTERFACE,
                "Screenshot",
                "sa{sv}",
                "",
                {
                    "handle_token": GLib.Variant("s", token),
                    "interactive": GLib.Variant("b", interactive),
                    "modal": GLib.Variant("b", False),
                },
                timeout_ms=10000,
            )
            if handle != request.handle:
                request.set_handle(handle)
            response = request.wait()
            uri = str(response.get("uri", ""))
            if not uri:
                return False
            source = Path(unquote(urlparse(uri).path))
            if not source.exists():
                return False
            shutil.copyfile(source, path)
            self._log.info("Screenshot saved via portal: %s", path)
            return True
        except (PortalError, OSError, ValueError) as exc:
            self._log.warning("Portal screenshot failed: %s", exc)
            return False

    def _via_x11(self, path: Path) -> bool:
        if not shutil.which("import"):
            return False
        try:
            import subprocess

            result = subprocess.run(
                ["import", "-window", "root", str(path)],
                capture_output=True,
                timeout=15,
                check=False,
            )
            if result.returncode == 0 and path.exists() and path.stat().st_size > 1024:
                self._log.info("Screenshot saved via ImageMagick: %s", path)
                return True
        except (OSError, subprocess.SubprocessError) as exc:
            self._log.debug("X11 screenshot failed: %s", exc)
        return False
