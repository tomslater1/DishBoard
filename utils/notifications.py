"""In-app notification generation and retrieval."""

from __future__ import annotations

import json
from datetime import date, datetime

from models.database import Database


def _active_user_id(db: Database, user_id: str | None = None) -> str:
    return (user_id or db.get_setting("active_user_id", "") or "").strip()


def notifications_enabled(db: Database) -> bool:
    raw = db.get_setting("in_app_notifications_enabled", "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def list_notifications(db: Database, user_id: str | None = None, *, limit: int = 100, unread_only: bool = False) -> list[dict]:
    uid = _active_user_id(db, user_id)
    if not uid:
        return []
    return db.get_in_app_notifications(uid, limit=limit, unread_only=unread_only)


def unread_count(db: Database, user_id: str | None = None) -> int:
    uid = _active_user_id(db, user_id)
    if not uid:
        return 0
    return db.get_unread_notification_count(uid)


def mark_read(db: Database, notification_id: int) -> None:
    db.mark_in_app_notification_read(notification_id)


def mark_all_read(db: Database, user_id: str | None = None) -> int:
    uid = _active_user_id(db, user_id)
    if not uid:
        return 0
    return db.mark_all_in_app_notifications_read(uid)


def add_notification(
    db: Database,
    notif_type: str,
    title: str,
    message: str,
    *,
    severity: str = "info",
    data: dict | None = None,
    dedupe_key: str | None = None,
    user_id: str | None = None,
) -> int | None:
    uid = _active_user_id(db, user_id)
    if not uid or not notifications_enabled(db):
        return None
    return db.add_in_app_notification(
        uid,
        notif_type,
        title,
        message,
        severity=severity,
        data_json=json.dumps(data or {}),
        dedupe_key=dedupe_key,
    )


def _generate_expiry_notifications(db: Database, user_id: str, today: date) -> int:
    created = 0
    for item in db.get_pantry_items():
        expiry = str(item.get("expiry_date") or "").strip()
        if not expiry:
            continue
        try:
            exp_date = date.fromisoformat(expiry)
        except Exception:
            continue
        delta = (exp_date - today).days

        if delta in (3, 1):
            key = f"expiry:{user_id}:{item.get('id')}:{delta}:{today.isoformat()}"
            title = "Pantry item expiring soon"
            msg = f"{item.get('name', 'Item')} expires in {delta} day{'s' if delta != 1 else ''}."
            n_id = add_notification(
                db,
                "pantry_expiry",
                title,
                msg,
                severity="warning",
                data={"item_id": item.get("id"), "storage": item.get("storage", "Pantry"), "days_remaining": delta},
                dedupe_key=key,
                user_id=user_id,
            )
            if n_id:
                created += 1

        if delta == 0:
            key = f"expiry-today:{user_id}:{item.get('id')}:{today.isoformat()}"
            n_id = add_notification(
                db,
                "pantry_expiry_today",
                "Pantry item expires today",
                f"{item.get('name', 'Item')} expires today.",
                severity="warning",
                data={"item_id": item.get("id"), "storage": item.get("storage", "Pantry"), "days_remaining": 0},
                dedupe_key=key,
                user_id=user_id,
            )
            if n_id:
                created += 1

    return created


def _generate_daily_meal_reminder(db: Database, user_id: str, now_local: datetime) -> int:
    # Reminder at/after 17:00 local time; one per day.
    if now_local.hour < 17:
        return 0

    today = now_local.date()
    key = f"meal-reminder:{user_id}:{today.isoformat()}"

    meal_rows = db.get_today_meal_slots()
    if not meal_rows:
        return 0

    meal_names: list[str] = []
    for row in meal_rows:
        name = (row.get("custom_name") or "").strip()
        if name:
            meal_names.append(name)
    if meal_names:
        preview = ", ".join(meal_names[:3])
    else:
        preview = "your planned meals"

    n_id = add_notification(
        db,
        "daily_meal_reminder",
        "Meal plan reminder",
        f"Tonight's plan includes {preview}. You're set for dinner prep.",
        severity="info",
        data={"meal_count": len(meal_rows), "date": today.isoformat()},
        dedupe_key=key,
        user_id=user_id,
    )
    return 1 if n_id else 0


def generate_scheduled_notifications(db: Database, user_id: str | None = None, *, now_local: datetime | None = None) -> int:
    """Create deduped notifications from pantry expiry + daily meal reminder."""
    uid = _active_user_id(db, user_id)
    if not uid or not notifications_enabled(db):
        return 0

    now_local = now_local or datetime.now()
    today = now_local.date()
    created = 0

    created += _generate_expiry_notifications(db, uid, today)
    created += _generate_daily_meal_reminder(db, uid, now_local)
    return created


def cleanup_old_notifications(db: Database, *, older_than_days: int = 30) -> int:
    return db.delete_old_read_notifications(older_than_days)
