"""Host metrics and network diagnostics."""

from __future__ import annotations

import platform
from datetime import datetime
from typing import Any

import psutil
import requests

from core.logging import get_logger


class SystemMonitor:
    """Collect local system information without elevated privileges."""

    def __init__(self) -> None:
        self._log = get_logger("system")

    def status(self) -> dict[str, Any]:
        """Return a snapshot of CPU, memory, disk and connectivity."""
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu_percent": float(psutil.cpu_percent(interval=0.2)),
            "memory_percent": float(memory.percent),
            "memory_used_gb": round(memory.used / 1024**3, 2),
            "disk_percent": float(disk.percent),
            "disk_free_gb": round(disk.free / 1024**3, 2),
            "online": self.is_online(),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    @staticmethod
    def is_online() -> bool:
        """Check outbound connectivity with a short timeout."""
        try:
            return requests.get("https://detectportal.firefox.com/success.txt", timeout=2).ok
        except requests.RequestException:
            return False

    def info(self) -> dict[str, str]:
        """Return static host information."""
        return {
            "hostname": platform.node(),
            "os": f"{platform.system()} {platform.release()}",
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "cpu": platform.processor() or "unknown",
            "cores": str(psutil.cpu_count(logical=True)),
            "memory_gb": f"{psutil.virtual_memory().total / 1024**3:.1f}",
        }
