"""Minimal runtime service registry + event bus for cross-module coordination."""

from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Any, Callable


class ServiceRegistry:
    def __init__(self):
        self._lock = RLock()
        self._services: dict[str, Any] = {}

    def register(self, key: str, service: Any) -> None:
        with self._lock:
            self._services[str(key)] = service

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._services.get(str(key), default)

    def unregister(self, key: str) -> Any:
        with self._lock:
            return self._services.pop(str(key), None)

    def clear(self) -> None:
        with self._lock:
            self._services.clear()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._services)


class EventBus:
    def __init__(self):
        self._lock = RLock()
        self._subs: dict[str, list[Callable[[dict], None]]] = defaultdict(list)

    def subscribe(self, topic: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        key = str(topic)
        with self._lock:
            self._subs[key].append(callback)

        def _dispose() -> None:
            with self._lock:
                lst = self._subs.get(key, [])
                if callback in lst:
                    lst.remove(callback)

        return _dispose

    def publish(self, topic: str, payload: dict | None = None) -> None:
        key = str(topic)
        body = dict(payload or {})
        with self._lock:
            callbacks = list(self._subs.get(key, []))
        for callback in callbacks:
            try:
                callback(body)
            except Exception:
                continue


registry = ServiceRegistry()
bus = EventBus()
