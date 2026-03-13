"""
Shared UI-thread database service.

Most views run on the main Qt thread and should reuse one SQLite connection
to reduce lock contention and simplify state consistency across tabs.
Background workers must still open their own Database connections.
"""

from __future__ import annotations

from threading import Lock

from models.database import Database

_LOCK = Lock()
_DB: Database | None = None


def get_db(*, init: bool = False) -> Database:
    """Return the shared Database connection for the UI thread."""
    global _DB
    with _LOCK:
        if _DB is None:
            _DB = Database()
            _DB.connect()
        if init:
            _DB.init_db()
        return _DB


def close_db() -> None:
    """Close and clear the shared Database connection."""
    global _DB
    with _LOCK:
        if _DB is not None:
            _DB.close()
            _DB = None

