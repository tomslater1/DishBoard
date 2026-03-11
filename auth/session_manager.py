"""
Session persistence for DishBoard using macOS Keychain (via the keyring library).

The Supabase access + refresh tokens are stored as JSON under the DishBoard
Keychain entry so the user stays logged in between app restarts.

Thread-safe: all methods are blocking and do not touch Qt.  Call
get_current_user() from the main thread at startup (before QApplication runs)
or from a run_async worker.
"""

from __future__ import annotations

import json
import os

_KEYCHAIN_SERVICE  = "DishBoard"
_KEYCHAIN_USERNAME = "supabase_session"

# Keys in the settings dict that we never sync to the cloud
_SENSITIVE_SETTING_KEYS = {
    "anthropic_api_key",
    "daily_tip", "daily_tip_date",
}


# ── Keychain helpers ──────────────────────────────────────────────────────────

def save_session(session_dict: dict) -> None:
    """Serialise session to JSON and store in macOS Keychain."""
    try:
        import keyring
        keyring.set_password(
            _KEYCHAIN_SERVICE,
            _KEYCHAIN_USERNAME,
            json.dumps(session_dict),
        )
    except Exception:
        pass


def load_session() -> dict | None:
    """Load and deserialise the stored session. Returns None if absent."""
    try:
        import keyring
        raw = keyring.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USERNAME)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


def clear_session() -> None:
    """Delete the session from Keychain (call on logout)."""
    try:
        import keyring
        keyring.delete_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USERNAME)
    except Exception:
        pass


# ── Session restore ───────────────────────────────────────────────────────────

def get_current_user() -> dict | None:
    """Attempt to restore a previous Supabase session on app startup.

    Returns:
        dict with at least {"id": ..., "email": ...} if session is valid.
        dict with {"_network_unavailable": True, ...} if tokens exist but the
            network is down — the user stays logged in with cached local data.
        None if no session exists or the token is truly invalid/expired.
    """
    stored = load_session()
    if not stored:
        return None

    access_token  = stored.get("access_token", "")
    refresh_token = stored.get("refresh_token", "")
    user_info     = stored.get("user", {})

    if not access_token or not user_info.get("id"):
        return None

    from auth.supabase_client import get_client
    client = get_client()
    if client is None:
        # Supabase client could not be created — treat as network unavailable
        return {**user_info, "_network_unavailable": True}

    try:
        response = client.auth.set_session(access_token, refresh_token)
        if response and response.user:
            u = response.user
            new_session = {
                "access_token":  response.session.access_token if response.session else access_token,
                "refresh_token": response.session.refresh_token if response.session else refresh_token,
                "user": {
                    "id":    str(u.id),
                    "email": u.email or user_info.get("email", ""),
                },
            }
            save_session(new_session)
            return new_session["user"]
    except Exception as e:
        err = str(e).lower()
        # Network error — keep the user logged in with cached local data
        if any(k in err for k in ("connect", "timeout", "network", "name resolution",
                                  "ssl", "socket", "unreachable", "failed to")):
            return {**user_info, "_network_unavailable": True}
        # Auth error (invalid/expired token) — force re-login
        clear_session()
        return None

    return None


def build_session_dict(response) -> dict:
    """Build the dict we persist from a Supabase AuthResponse."""
    u = response.user
    s = response.session
    return {
        "access_token":  s.access_token  if s else "",
        "refresh_token": s.refresh_token if s else "",
        "user": {
            "id":    str(u.id),
            "email": u.email or "",
        },
    }
