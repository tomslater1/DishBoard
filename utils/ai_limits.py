"""Daily AI request limit enforcement helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from models.database import Database

DEFAULT_DAILY_LIMIT = 50


def utc_day_str(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.date().isoformat()


def get_daily_limit(db: Database) -> int:
    raw = db.get_setting("dishy_daily_limit", str(DEFAULT_DAILY_LIMIT)).strip()
    try:
        value = int(raw)
    except Exception:
        value = DEFAULT_DAILY_LIMIT
    return max(1, value)


def get_usage(db: Database, user_id: str, day: str | None = None) -> dict:
    day = day or utc_day_str()
    return db.get_ai_usage(user_id or "", day)


def remaining_requests(db: Database, user_id: str, day: str | None = None) -> int:
    usage = get_usage(db, user_id, day)
    return max(0, get_daily_limit(db) - int(usage.get("request_count", 0) or 0))


def can_make_request(db: Database, user_id: str, day: str | None = None) -> tuple[bool, int, int]:
    """Return (allowed, remaining, limit)."""
    limit = get_daily_limit(db)
    usage = get_usage(db, user_id, day)
    count = int(usage.get("request_count", 0) or 0)
    remaining = max(0, limit - count)
    return count < limit, remaining, limit


def record_attempt(db: Database, user_id: str, *, blocked: bool = False, day: str | None = None) -> dict:
    day = day or utc_day_str()
    return db.increment_ai_usage(user_id or "", day, blocked=blocked)


def record_block(db: Database, user_id: str, *, day: str | None = None) -> dict:
    day = day or utc_day_str()
    return db.increment_ai_blocked(user_id or "", day)
