"""Sync resilience helpers: exponential backoff + lightweight circuit breaker."""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone


class SyncResilienceController:
    """Tracks sync failures and determines when the next attempt is allowed."""

    def __init__(
        self,
        *,
        min_backoff_seconds: int = 5,
        max_backoff_seconds: int = 120,
        circuit_after_failures: int = 5,
        circuit_open_seconds: int = 180,
    ):
        self._min_backoff = max(1, int(min_backoff_seconds))
        self._max_backoff = max(self._min_backoff, int(max_backoff_seconds))
        self._circuit_after = max(2, int(circuit_after_failures))
        self._circuit_open = max(self._min_backoff, int(circuit_open_seconds))

        self._consecutive_failures = 0
        self._blocked_until = 0.0
        self._circuit_until = 0.0
        self._last_error = ""
        self._last_success_at = ""
        self._last_failure_at = ""

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def can_attempt(self, *, now: float | None = None, force: bool = False) -> tuple[bool, int, str]:
        """Return `(allowed, retry_in_seconds, reason)` for a potential sync attempt."""
        current = self._now() if now is None else float(now)
        if force:
            return True, 0, "forced"

        if self._circuit_until > current:
            remaining = int(math.ceil(self._circuit_until - current))
            return False, max(1, remaining), "circuit_open"

        if self._blocked_until > current:
            remaining = int(math.ceil(self._blocked_until - current))
            return False, max(1, remaining), "backoff"

        return True, 0, "ready"

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._blocked_until = 0.0
        self._circuit_until = 0.0
        self._last_error = ""
        self._last_success_at = self._utc_now_iso()

    def record_failure(self, err: str = "", *, now: float | None = None) -> dict:
        current = self._now() if now is None else float(now)
        self._consecutive_failures += 1
        self._last_error = str(err or "").strip()
        self._last_failure_at = self._utc_now_iso()

        if self._consecutive_failures >= self._circuit_after:
            self._circuit_until = current + self._circuit_open
            self._blocked_until = self._circuit_until
            reason = "circuit_open"
            retry_in = self._circuit_open
        else:
            delay = min(self._max_backoff, self._min_backoff * (2 ** (self._consecutive_failures - 1)))
            self._blocked_until = current + delay
            reason = "backoff"
            retry_in = delay

        status = self.status(now=current)
        status["retry_in_seconds"] = int(retry_in)
        status["reason"] = reason
        return status

    def reset(self) -> None:
        self._consecutive_failures = 0
        self._blocked_until = 0.0
        self._circuit_until = 0.0
        self._last_error = ""

    def status(self, *, now: float | None = None) -> dict:
        current = self._now() if now is None else float(now)
        is_open = self._circuit_until > current
        retry_in = 0
        if is_open:
            retry_in = int(math.ceil(self._circuit_until - current))
        elif self._blocked_until > current:
            retry_in = int(math.ceil(self._blocked_until - current))

        return {
            "consecutive_failures": int(self._consecutive_failures),
            "retry_in_seconds": max(0, int(retry_in)),
            "circuit_open": bool(is_open),
            "last_error": self._last_error,
            "last_success_at": self._last_success_at,
            "last_failure_at": self._last_failure_at,
        }
