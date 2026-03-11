"""
Supabase client singleton.

SUPABASE_URL and SUPABASE_ANON_KEY are read from os.environ (loaded from .env
at startup, same as other API keys).  The anon key is safe to bundle — Supabase
Row Level Security policies enforce per-user data isolation server-side.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse


# Default project credentials — safe to bundle. The anon key is a public JWT;
# all data security is enforced by Row Level Security policies server-side.
_DEFAULT_URL = "https://ixddtfprarxsgscwytro.supabase.co"
_DEFAULT_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml4ZGR0ZnByYXJ4c2dzY3d5dHJvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMxOTI3NjMsImV4cCI6MjA4ODc2ODc2M30"
    ".A6yU9gvihf1zuvo5xQ9K_7fSgfxBF5ERzVdU0yLCLuI"
)

_client = None   # module-level singleton — created lazily on first get_client() call


def get_client():
    """Return the Supabase client, creating it on first call.

    Falls back to the bundled default project if env vars are not set,
    so fresh installs work without any .env or DB configuration.
    Thread-safe for reads — the singleton is only written once.
    """
    global _client
    if _client is not None:
        return _client

    url = os.environ.get("SUPABASE_URL", "").strip() or _DEFAULT_URL
    key = os.environ.get("SUPABASE_ANON_KEY", "").strip() or _DEFAULT_KEY

    try:
        from supabase import create_client
        _client = create_client(url, key)
        return _client
    except Exception:
        return None


def reset_client():
    """Force recreation of the client on next get_client() call.
    Call this after SUPABASE_URL / SUPABASE_ANON_KEY are set at runtime.
    """
    global _client
    _client = None


def is_online() -> bool:
    """Return True if the Supabase host is reachable (TCP port 443, 2 s timeout).

    Never raises — used as a lightweight guard before sync attempts.
    """
    url = os.environ.get("SUPABASE_URL", "").strip() or _DEFAULT_URL
    try:
        host = urlparse(url).hostname or url
        with socket.create_connection((host, 443), timeout=2):
            return True
    except Exception:
        return False


def is_configured() -> bool:
    """Return True if Supabase credentials are available (env vars or bundled defaults)."""
    url = os.environ.get("SUPABASE_URL", "").strip() or _DEFAULT_URL
    key = os.environ.get("SUPABASE_ANON_KEY", "").strip() or _DEFAULT_KEY
    return bool(url and key)
