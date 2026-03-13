"""
Supabase client singleton.

SUPABASE_URL and SUPABASE_ANON_KEY are read from os.environ. The anon key is
safe to bundle because Row Level Security enforces per-user data isolation.
"""

from __future__ import annotations

import logging
import os
import socket
from urllib.parse import urlparse

_DEFAULT_URL = "https://ixddtfprarxsgscwytro.supabase.co"
_DEFAULT_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml4ZGR0ZnByYXJ4c2dzY3d5dHJvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMxOTI3NjMsImV4cCI6MjA4ODc2ODc2M30"
    ".A6yU9gvihf1zuvo5xQ9K_7fSgfxBF5ERzVdU0yLCLuI"
)

_client = None
_log = logging.getLogger("dishboard.supabase")


def get_client():
    """Return the Supabase client, creating it on first call."""
    global _client
    if _client is not None:
        return _client

    url = os.environ.get("SUPABASE_URL", "").strip() or _DEFAULT_URL
    key = os.environ.get("SUPABASE_ANON_KEY", "").strip() or _DEFAULT_KEY

    try:
        from supabase import create_client

        _client = create_client(url, key)
        return _client
    except Exception as exc:
        _log.warning("Could not create Supabase client: %s", exc)
        return None


def reset_client():
    """Force recreation of the client on next get_client() call."""
    global _client
    _client = None


def is_online() -> bool:
    """Return True if the Supabase host is reachable (TCP port 443, 2 s timeout)."""
    url = os.environ.get("SUPABASE_URL", "").strip() or _DEFAULT_URL
    try:
        host = urlparse(url).hostname or url
        with socket.create_connection((host, 443), timeout=2):
            return True
    except Exception as exc:
        _log.info("Supabase host unreachable: %s", exc)
        return False


def is_configured() -> bool:
    """Return True if Supabase credentials are available (env vars or bundled defaults)."""
    url = os.environ.get("SUPABASE_URL", "").strip() or _DEFAULT_URL
    key = os.environ.get("SUPABASE_ANON_KEY", "").strip() or _DEFAULT_KEY
    return bool(url and key)
