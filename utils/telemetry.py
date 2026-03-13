"""Observability hooks (local event log + optional Sentry/PostHog)."""

from __future__ import annotations

import json
import logging
import os
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from models.database import Database

_LOG = logging.getLogger("dishboard.telemetry")


@dataclass
class _TelemetryState:
    db_path: str = ""
    user_id: str = ""
    enabled: bool = True
    posthog_enabled: bool = True
    sentry_enabled: bool = True


_STATE = _TelemetryState()
_POSTHOG = None
_SENTRY = None


def _open_db() -> Database | None:
    if not _STATE.db_path:
        return None
    try:
        db = Database(_STATE.db_path)
        db.connect()
        return db
    except Exception:
        return None


def _bool(raw: str, default: bool = True) -> bool:
    text = (raw or "").strip().lower()
    if not text:
        return default
    return text not in {"0", "false", "off", "no"}


def init_telemetry(db: Database, user_id: str = "") -> None:
    """Initialize local event logging plus optional external telemetry providers."""
    global _POSTHOG, _SENTRY

    _STATE.db_path = db.path
    _STATE.user_id = user_id or ""
    _STATE.enabled = _bool(db.get_setting("telemetry_enabled", "1"), True)
    _STATE.posthog_enabled = _bool(db.get_setting("posthog_enabled", "1"), True)
    _STATE.sentry_enabled = _bool(db.get_setting("sentry_enabled", "1"), True)

    if not _STATE.enabled:
        return

    if _STATE.sentry_enabled and _SENTRY is None:
        dsn = os.environ.get("SENTRY_DSN", "").strip()
        if dsn:
            try:
                import sentry_sdk

                sentry_sdk.init(
                    dsn=dsn,
                    traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
                    environment=os.environ.get("APP_ENV", "production"),
                    release=os.environ.get("APP_VERSION", "unknown"),
                )
                _SENTRY = sentry_sdk
            except Exception as exc:
                _LOG.warning("Sentry init failed: %s", exc)

    if _STATE.posthog_enabled and _POSTHOG is None:
        key = os.environ.get("POSTHOG_API_KEY", "").strip()
        host = (os.environ.get("POSTHOG_HOST", "https://app.posthog.com") or "").strip()
        if key:
            try:
                from posthog import Posthog

                _POSTHOG = Posthog(project_api_key=key, host=host)
            except Exception as exc:
                _LOG.warning("PostHog init failed: %s", exc)


def set_user(user_id: str) -> None:
    _STATE.user_id = user_id or ""


def _record_local_event(name: str, properties: dict[str, Any] | None = None, *, user_id: str = "") -> None:
    db = _open_db()
    if db is None:
        return
    try:
        payload = dict(properties or {})
        payload.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        db.add_telemetry_event(user_id or _STATE.user_id, name, json.dumps(payload, default=str))
    except Exception:
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def track_event(name: str, properties: dict[str, Any] | None = None, *, user_id: str = "") -> None:
    if not _STATE.enabled:
        return

    props = dict(properties or {})
    props.setdefault("platform", platform.system())
    props.setdefault("platform_release", platform.release())

    _record_local_event(name, props, user_id=user_id)

    if _POSTHOG is not None and _STATE.posthog_enabled:
        try:
            distinct_id = user_id or _STATE.user_id or "anonymous"
            _POSTHOG.capture(distinct_id=distinct_id, event=name, properties=props)
        except Exception:
            pass


def capture_exception(exc: Exception | str, *, context: dict[str, Any] | None = None, user_id: str = "") -> None:
    err_text = str(exc)
    payload = {"error": err_text}
    if context:
        payload.update(context)
    track_event("exception", payload, user_id=user_id)

    if _SENTRY is not None and _STATE.sentry_enabled:
        try:
            _SENTRY.capture_exception(exc if isinstance(exc, Exception) else Exception(err_text))
        except Exception:
            pass


def get_analytics_status(db: Database, user_id: str = "") -> dict[str, Any]:
    """Return current analytics wiring status for the Settings monitoring UI."""
    enabled = _bool(db.get_setting("telemetry_enabled", "1"), True)
    posthog_enabled = _bool(db.get_setting("posthog_enabled", "1"), True)
    key = os.environ.get("POSTHOG_API_KEY", "").strip()
    host = (os.environ.get("POSTHOG_HOST", "https://app.posthog.com") or "").strip()
    last_event_at = db.get_latest_telemetry_event_at(user_id or "")
    return {
        "enabled": bool(enabled),
        "posthog_enabled": bool(posthog_enabled),
        "has_api_key": bool(key),
        "host": host,
        "client_ready": bool(_POSTHOG is not None),
        "connected": bool(enabled and posthog_enabled and key and _POSTHOG is not None),
        "last_event_at": last_event_at,
    }
