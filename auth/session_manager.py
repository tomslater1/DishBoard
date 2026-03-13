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

_KEYCHAIN_SERVICE = "DishBoard"
_KEYCHAIN_USERNAME = "supabase_session"
_LOG = logging.getLogger("dishboard.session")
_DIAGNOSTICS = {
    "status": "unknown",
    "detail": "",
    "backend": "",
}

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
    try:
        import keyring

        backend = keyring.get_keyring().__class__.__name__
        keyring.set_password(
            _KEYCHAIN_SERVICE,
            _KEYCHAIN_USERNAME,
            json.dumps(session_dict),
        )
        _update_diagnostics("available", "Session persisted successfully", backend)
    except Exception as exc:
        _update_diagnostics("degraded", f"Could not save session: {exc}")
        _LOG.warning("Could not save session to keyring: %s", exc)


def load_session() -> dict | None:
    """Load and deserialise the stored session. Returns None if absent."""
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
    try:
        import keyring

        backend = keyring.get_keyring().__class__.__name__
        keyring.delete_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USERNAME)
        _update_diagnostics("available", "Stored session cleared", backend)
    except Exception as exc:
        _update_diagnostics("degraded", f"Could not clear session: {exc}")
        _LOG.warning("Could not clear session from keyring: %s", exc)


def get_current_user() -> dict | None:
    """Attempt to restore a previous Supabase session on app startup."""
    stored = load_session()
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
        if response and response.user:
            u = response.user
            new_session = {
                "access_token": response.session.access_token if response.session else access_token,
                "refresh_token": response.session.refresh_token if response.session else refresh_token,
                "user": {
                    "id": str(u.id),
                    "email": u.email or user_info.get("email", ""),
                },
            }
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
    u = response.user
    s = response.session
    return {
        "access_token": s.access_token if s else "",
        "refresh_token": s.refresh_token if s else "",
        "user": {
            "id": str(u.id),
            "email": u.email or "",
        },
    }
