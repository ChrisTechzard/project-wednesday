"""Thread-safe publish/subscribe event bus."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from core.logging import get_logger
from core.models import Event, EventType

Subscriber = Callable[[Event], None]


class EventBus:
    """Fan-out event bus with one queue per subscriber.

    Publishers never block on subscribers; each subscriber is drained by its
    own queue so a slow UI cannot stall the voice or vision threads.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, tuple[EventType | None, queue.Queue[Event]]] = {}
        self._log = get_logger("events")
        self._drop_count = 0
        self._last_drop_log = 0.0

    def subscribe(
        self,
        callback: Subscriber,
        event_type: EventType | None = None,
    ) -> str:
        """Register a callback and return an opaque subscription id."""
        subscription_id = uuid.uuid4().hex
        q: queue.Queue[Event] = queue.Queue(maxsize=200)
        with self._lock:
            self._subscribers[subscription_id] = (event_type, q)

        threading.Thread(
            target=self._drain,
            args=(subscription_id, callback, q),
            name=f"event-{subscription_id[:8]}",
            daemon=True,
        ).start()
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscription by id."""
        with self._lock:
            self._subscribers.pop(subscription_id, None)

    def publish(self, event: Event) -> None:
        """Deliver an event to every matching subscriber without blocking."""
        with self._lock:
            subscribers = list(self._subscribers.items())
        for subscription_id, (event_type, q) in subscribers:
            if event_type is not None and event.type != event_type:
                continue
            try:
                q.put_nowait(event)
            except queue.Full:
                # Prefer fresh data over a stale backlog: discard the oldest
                # queued event so the UI catches up to the current state.
                try:
                    q.get_nowait()
                    q.task_done()
                    q.put_nowait(event)
                    continue
                except queue.Empty:
                    pass
                # A slow UI can overflow the queue every frame. Logging every
                # drop floods the disk and feeds the lag, so rate-limit to one
                # summary per second.
                with self._lock:
                    self._drop_count += 1
                    now = time.monotonic()
                    if now - self._last_drop_log >= 1.0:
                        self._log.warning(
                            "Dropped %d events for slow subscribers (last: %s)",
                            self._drop_count,
                            event.type.value,
                        )
                        self._drop_count = 0
                        self._last_drop_log = now

    def emit(
        self,
        event_type: EventType,
        payload: dict[str, Any] | None = None,
        source: str = "",
    ) -> None:
        """Convenience wrapper for publishing an event."""
        self.publish(Event(type=event_type, payload=payload or {}, source=source))

    def _drain(self, subscription_id: str, callback: Subscriber, q: queue.Queue[Event]) -> None:
        while True:
            event = q.get()
            with self._lock:
                if subscription_id not in self._subscribers:
                    return
            try:
                callback(event)
            except Exception as exc:  # subscriber must never kill the bus
                self._log.exception("Subscriber %s failed on %s: %s", subscription_id, event.type.value, exc)
            finally:
                q.task_done()
