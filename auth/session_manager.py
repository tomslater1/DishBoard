"""
Session persistence for DishBoard using OS credential storage (via keyring).

The Supabase access + refresh tokens are stored as JSON in the system keyring
so the user stays logged in between app restarts.

Thread-safe: all methods are blocking and do not touch Qt. Call
get_current_user() from the main thread at startup (before QApplication runs)
or from a run_async worker.
"""

from __future__ import annotations

import json
import logging
import time

_KEYCHAIN_SERVICE = "DishBoard"
_KEYCHAIN_USERNAME = "supabase_session"
_LOG = logging.getLogger("dishboard.session")
_DIAGNOSTICS = {
    "status": "unknown",
    "detail": "",
    "backend": "",
}
_SESSION_INVALIDATED = False

# Keys in the settings dict that we never sync to the cloud
_SENSITIVE_SETTING_KEYS = {
    "anthropic_api_key",
    "daily_tip", "daily_tip_date",
}


def _update_diagnostics(status: str, detail: str = "", backend: str = "") -> None:
    _DIAGNOSTICS["status"] = status
    _DIAGNOSTICS["detail"] = detail
    if backend:
        _DIAGNOSTICS["backend"] = backend


def get_session_diagnostics() -> dict:
    return dict(_DIAGNOSTICS)


def save_session(session_dict: dict) -> None:
    """Serialise session to JSON and store in the OS keyring."""
    global _SESSION_INVALIDATED
    try:
        import keyring

        backend = keyring.get_keyring().__class__.__name__
        keyring.set_password(
            _KEYCHAIN_SERVICE,
            _KEYCHAIN_USERNAME,
            json.dumps(session_dict),
        )
        _SESSION_INVALIDATED = False
        _update_diagnostics("available", "Session persisted successfully", backend)
    except Exception as exc:
        _update_diagnostics("degraded", f"Could not save session: {exc}")
        _LOG.warning("Could not save session to keyring: %s", exc)


def load_session() -> dict | None:
    """Load and deserialise the stored session. Returns None if absent."""
    if _SESSION_INVALIDATED:
        return None
    try:
        import keyring

        backend = keyring.get_keyring().__class__.__name__
        raw = keyring.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USERNAME)
        if raw:
            _update_diagnostics("available", "Stored session found", backend)
            return json.loads(raw)
        _update_diagnostics("available", "No stored session found", backend)
    except Exception as exc:
        _update_diagnostics("degraded", f"Could not load session: {exc}")
        _LOG.warning("Could not load session from keyring: %s", exc)
    return None


def clear_session() -> None:
    """Delete the session from the OS keyring (call on logout)."""
    global _SESSION_INVALIDATED
    _SESSION_INVALIDATED = True
    try:
        import keyring

        backend = keyring.get_keyring().__class__.__name__
        keyring.delete_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USERNAME)
        _update_diagnostics("available", "Stored session cleared", backend)
    except Exception as exc:
        _update_diagnostics("degraded", f"Stored session cleared locally; keyring delete failed: {exc}")
        _LOG.warning("Could not clear session from keyring: %s", exc)


def _build_persisted_session(response, fallback_user: dict | None = None) -> dict | None:
    """Return a persisted session payload from a Supabase AuthResponse."""
    session = getattr(response, "session", None)
    user = getattr(response, "user", None)
    if user is None and session is not None:
        user = getattr(session, "user", None)
    if user is None:
        return None
    return {
        "access_token": getattr(session, "access_token", "") if session else "",
        "refresh_token": getattr(session, "refresh_token", "") if session else "",
        "expires_at": int(getattr(session, "expires_at", 0) or 0) if session else 0,
        "expires_in": int(getattr(session, "expires_in", 0) or 0) if session else 0,
        "user": {
            "id": str(getattr(user, "id", "") or (fallback_user or {}).get("id", "")),
            "email": getattr(user, "email", "") or (fallback_user or {}).get("email", ""),
        },
    }


def ensure_valid_session(*, min_ttl_seconds: int = 120) -> dict | None:
    """Ensure the Supabase client has a usable session, refreshing if needed.

    Returns the refreshed/stored session payload or ``None`` when no valid
    persisted session exists.
    """
    stored = load_session()
    if not stored:
        return None

    refresh_token = str(stored.get("refresh_token") or "").strip()
    access_token = str(stored.get("access_token") or "").strip()
    user_info = dict(stored.get("user") or {})
    if not refresh_token or not user_info.get("id"):
        _update_diagnostics("invalid", "Stored session is incomplete", _DIAGNOSTICS.get("backend", ""))
        return None

    from auth.supabase_client import get_client

    client = get_client()
    if client is None:
        _update_diagnostics("network_unavailable", "Supabase client unavailable while validating session")
        return stored

    try:
        current = client.auth.get_session()
        current_session = getattr(current, "session", current)
        if current_session is not None:
            expires_at = int(getattr(current_session, "expires_at", 0) or 0)
            if expires_at and expires_at > int(time.time()) + int(min_ttl_seconds):
                return stored
    except Exception:
        pass

    try:
        response = client.auth.refresh_session(refresh_token)
        new_session = _build_persisted_session(response, fallback_user=user_info)
        if new_session and new_session.get("access_token"):
            save_session(new_session)
            _update_diagnostics("available", "Session refreshed successfully", _DIAGNOSTICS.get("backend", ""))
            return new_session
    except Exception as exc:
        err = str(exc).lower()
        if any(
            token in err
            for token in ("connect", "timeout", "network", "name resolution", "ssl", "socket", "unreachable", "failed to")
        ):
            _update_diagnostics("network_unavailable", str(exc), _DIAGNOSTICS.get("backend", ""))
            return stored
        _LOG.warning("Session refresh failed, falling back to set_session: %s", exc)

    if access_token:
        try:
            response = client.auth.set_session(access_token, refresh_token)
            new_session = _build_persisted_session(response, fallback_user=user_info)
            if new_session and new_session.get("access_token"):
                save_session(new_session)
                _update_diagnostics("available", "Session restored successfully", _DIAGNOSTICS.get("backend", ""))
                return new_session
        except Exception as exc:
            err = str(exc).lower()
            if any(
                token in err
                for token in ("connect", "timeout", "network", "name resolution", "ssl", "socket", "unreachable", "failed to")
            ):
                _update_diagnostics("network_unavailable", str(exc), _DIAGNOSTICS.get("backend", ""))
                return stored
            _update_diagnostics("invalid", str(exc), _DIAGNOSTICS.get("backend", ""))
            _LOG.warning("Stored session became invalid while validating: %s", exc)
            clear_session()
            return None

    _update_diagnostics("invalid", "Stored session could not be refreshed", _DIAGNOSTICS.get("backend", ""))
    clear_session()
    return None


def get_current_user() -> dict | None:
    """Attempt to restore a previous Supabase session on app startup."""
    stored = ensure_valid_session(min_ttl_seconds=300) or load_session()
    if not stored:
        if _DIAGNOSTICS["status"] == "unknown":
            _update_diagnostics("available", "No stored session found")
        return None

    access_token = stored.get("access_token", "")
    refresh_token = stored.get("refresh_token", "")
    user_info = stored.get("user", {})

    if not access_token or not user_info.get("id"):
        _update_diagnostics("invalid", "Stored session is incomplete", _DIAGNOSTICS.get("backend", ""))
        return None

    from auth.supabase_client import get_client

    client = get_client()
    if client is None:
        _update_diagnostics("network_unavailable", "Supabase client unavailable while restoring session")
        return {**user_info, "_network_unavailable": True}

    try:
        response = client.auth.set_session(access_token, refresh_token)
        new_session = _build_persisted_session(response, fallback_user=user_info)
        if new_session and new_session.get("user", {}).get("id"):
            save_session(new_session)
            _update_diagnostics("available", "Session restored successfully", _DIAGNOSTICS.get("backend", ""))
            return new_session["user"]
    except Exception as exc:
        err = str(exc).lower()
        if any(
            token in err
            for token in ("connect", "timeout", "network", "name resolution", "ssl", "socket", "unreachable", "failed to")
        ):
            _update_diagnostics("network_unavailable", str(exc), _DIAGNOSTICS.get("backend", ""))
            return {**user_info, "_network_unavailable": True}
        _update_diagnostics("invalid", str(exc), _DIAGNOSTICS.get("backend", ""))
        _LOG.warning("Stored session became invalid: %s", exc)
        clear_session()
        return None

    _update_diagnostics("invalid", "Stored session could not be restored", _DIAGNOSTICS.get("backend", ""))
    return None


def build_session_dict(response) -> dict:
    """Build the dict we persist from a Supabase AuthResponse."""
    return _build_persisted_session(response) or {
        "access_token": "",
        "refresh_token": "",
        "expires_at": 0,
        "expires_in": 0,
        "user": {"id": "", "email": ""},
    }
