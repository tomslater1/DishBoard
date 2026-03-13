"""Shared validation/sanitization helpers for cloud pull + local imports."""

from __future__ import annotations

from datetime import date

VALID_WEEKDAYS = {
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
}
VALID_MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack"}
VALID_STORAGES = {"Pantry", "Fridge", "Freezer"}


def _clean_text(value) -> str:
    return " ".join(str(value or "").split()).strip()


def _is_iso_date(value) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        date.fromisoformat(text)
        return True
    except Exception:
        return False


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def sanitize_cloud_row(
    table: str,
    row: dict,
    *,
    user_id: str = "",
    household_id: str = "",
    household_scope_enabled: bool = False,
    household_shared_tables: set[str] | None = None,
) -> tuple[dict | None, str]:
    """Return `(sanitized_row, reason)` or `(None, reason)` when invalid."""
    if not isinstance(row, dict):
        return None, "row_not_object"

    shared_tables = household_shared_tables or set()
    t = str(table or "").strip()
    out = dict(row)

    row_user = str(out.get("user_id") or "").strip()
    row_household = str(out.get("household_id") or "").strip()
    uid = str(user_id or "").strip()
    hid = str(household_id or "").strip()

    if household_scope_enabled and t in shared_tables and hid:
        if row_household and row_household != hid:
            return None, "scope_mismatch_household"
        # Legacy shared rows may have no household_id. Accept only own legacy rows.
        if not row_household and row_user and uid and row_user != uid:
            return None, "scope_mismatch_legacy_user"
    elif uid and row_user and row_user != uid:
        return None, "scope_mismatch_user"

    if t == "recipes":
        out["title"] = _clean_text(out.get("title"))
        if not out["title"]:
            return None, "recipe_missing_title"
        image_url = str(out.get("image_url") or "").strip()
        if image_url and not image_url.startswith(("http://", "https://")):
            out["image_url"] = ""
        return out, "ok"

    if t == "meal_plans":
        week_start = str(out.get("week_start") or "").strip()
        day_of_week = str(out.get("day_of_week") or "").strip()
        meal_type = str(out.get("meal_type") or "").strip().lower()
        if not _is_iso_date(week_start):
            return None, "meal_plan_bad_week_start"
        if day_of_week not in VALID_WEEKDAYS:
            return None, "meal_plan_bad_day"
        if meal_type not in VALID_MEAL_TYPES:
            return None, "meal_plan_bad_type"
        out["week_start"] = week_start
        out["day_of_week"] = day_of_week
        out["meal_type"] = meal_type
        return out, "ok"

    if t == "shopping_items":
        out["name"] = _clean_text(out.get("name"))
        if not out["name"]:
            return None, "shopping_missing_name"
        out["checked"] = 1 if _to_int(out.get("checked"), 0) else 0
        return out, "ok"

    if t == "nutrition_logs":
        log_date = str(out.get("log_date") or "").strip()
        food_name = _clean_text(out.get("food_name"))
        if not (_is_iso_date(log_date) and food_name):
            return None, "nutrition_missing_fields"
        out["log_date"] = log_date
        out["food_name"] = food_name
        for key in ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g"):
            out[key] = _to_float(out.get(key), 0.0)
        return out, "ok"

    if t == "dishy_chat_history":
        out["session_id"] = _clean_text(out.get("session_id"))
        out["role"] = str(out.get("role") or "").strip().lower()
        out["content"] = str(out.get("content") or "").strip()
        if not (out["session_id"] and out["role"] and out["content"]):
            return None, "chat_missing_fields"
        return out, "ok"

    if t == "pantry_items":
        out["name"] = _clean_text(out.get("name"))
        if not out["name"]:
            return None, "pantry_missing_name"
        storage = str(out.get("storage") or "Pantry").strip().title()
        if storage not in VALID_STORAGES:
            storage = "Pantry"
        out["storage"] = storage
        return out, "ok"

    return out, "ok"


def sanitize_import_row(table: str, row: dict) -> dict | None:
    """Sanitize backup import rows. Returns filtered row dict or None."""
    if not isinstance(row, dict):
        return None

    t = str(table or "").strip()
    out = dict(row)

    if t == "recipes":
        out["title"] = _clean_text(out.get("title"))
        if not out["title"]:
            return None
        out["source"] = _clean_text(out.get("source") or "manual") or "manual"
        image = str(out.get("image_url") or "").strip()
        out["image_url"] = image if image.startswith(("http://", "https://")) else ""
        return out

    if t == "meal_plans":
        row2, reason = sanitize_cloud_row("meal_plans", out)
        if row2 is None:
            return None
        return {
            "day_of_week": row2.get("day_of_week"),
            "meal_type": row2.get("meal_type"),
            "recipe_id": row2.get("recipe_id"),
            "custom_name": _clean_text(row2.get("custom_name")),
            "week_start": row2.get("week_start"),
            "notes": str(row2.get("notes") or "").strip(),
        }

    if t == "shopping_items":
        row2, _ = sanitize_cloud_row("shopping_items", out)
        if row2 is None:
            return None
        return {
            "name": row2.get("name"),
            "quantity": str(row2.get("quantity") or "").strip(),
            "unit": str(row2.get("unit") or "").strip(),
            "checked": row2.get("checked", 0),
            "source": str(row2.get("source") or "manual").strip() or "manual",
            "added_at": row2.get("added_at"),
        }

    if t == "pantry_items":
        row2, _ = sanitize_cloud_row("pantry_items", out)
        if row2 is None:
            return None
        exp = str(row2.get("expiry_date") or "").strip()
        if exp and not _is_iso_date(exp):
            exp = ""
        return {
            "name": row2.get("name"),
            "quantity": row2.get("quantity"),
            "unit": str(row2.get("unit") or "").strip(),
            "storage": row2.get("storage", "Pantry"),
            "expiry_date": exp,
            "added_at": row2.get("added_at"),
        }

    if t == "nutrition_logs":
        row2, _ = sanitize_cloud_row("nutrition_logs", out)
        if row2 is None:
            return None
        return {
            "log_date": row2.get("log_date"),
            "food_name": row2.get("food_name"),
            "kcal": row2.get("kcal", 0.0),
            "protein_g": row2.get("protein_g", 0.0),
            "carbs_g": row2.get("carbs_g", 0.0),
            "fat_g": row2.get("fat_g", 0.0),
            "fiber_g": row2.get("fiber_g", 0.0),
            "sugar_g": row2.get("sugar_g", 0.0),
            "logged_at": row2.get("logged_at"),
        }

    return out
