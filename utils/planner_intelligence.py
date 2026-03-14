"""Meal-planner intelligence helpers.

These helpers keep planner features lightweight by storing user-facing
metadata in `meal_plans.notes` and personal templates in synced settings.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone


PLANNING_MODES: list[tuple[str, str, str]] = [
    ("balanced", "Balanced", "Keep the week varied and nutritionally steady."),
    ("high_protein", "High Protein", "Bias toward higher-protein recipes and leftovers."),
    ("pantry_first", "Pantry First", "Prefer recipes that use ingredients already in My Kitchen."),
    ("low_effort", "Low Effort", "Prefer quick, simple, low-friction meals."),
    ("family_friendly", "Family Friendly", "Prefer crowd-pleasing, easy-to-share meals."),
    ("budget", "Budget", "Bias toward pantry-heavy and budget-friendly recipes."),
    ("meal_prep", "Meal Prep", "Plan batch cooking and deliberate leftovers."),
    ("reduce_waste", "Reduce Waste", "Use up expiring ingredients first and route leftovers forward."),
]

_VALID_MODES = {key for key, _label, _desc in PLANNING_MODES}
_TEMPLATE_SETTING_KEY = "planner_templates_json"


def planning_mode_label(mode: str) -> str:
    for key, label, _desc in PLANNING_MODES:
        if key == mode:
            return label
    return "Balanced"
def get_planning_mode(db) -> str:
    raw = str(db.get_setting("meal_planning_mode", "balanced") or "").strip().lower()
    return raw if raw in _VALID_MODES else "balanced"


def _safe_json_loads(raw: str | None, fallback):
    try:
        parsed = json.loads(raw or "")
    except Exception:
        parsed = fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def load_slot_metadata(notes: str | None) -> dict:
    data = _safe_json_loads(notes, {})
    out = {}
    if data.get("prep_batch"):
        out["prep_batch"] = True
    try:
        leftovers = int(data.get("leftover_portions") or 0)
    except Exception:
        leftovers = 0
    if leftovers > 0:
        out["leftover_portions"] = leftovers
    source_day = str(data.get("leftover_source_day") or "").strip()
    if source_day:
        out["leftover_source_day"] = source_day
    owner = str(data.get("owner_label") or "").strip()
    if owner:
        out["owner_label"] = owner[:40]
    planning_mode = str(data.get("planning_mode") or "").strip().lower()
    if planning_mode in _VALID_MODES:
        out["planning_mode"] = planning_mode
    template_name = str(data.get("template_name") or "").strip()
    if template_name:
        out["template_name"] = template_name[:80]
    recipe_scale = data.get("recipe_scale")
    try:
        if recipe_scale:
            out["recipe_scale"] = round(float(recipe_scale), 2)
    except Exception:
        pass
    return out


def dump_slot_metadata(meta: dict | None) -> str:
    clean = load_slot_metadata(json.dumps(meta or {}))
    if not clean:
        return ""
    return json.dumps(clean, separators=(",", ":"), sort_keys=True)


def slot_badges(meta: dict | None) -> list[tuple[str, str, str]]:
    clean = load_slot_metadata(json.dumps(meta or {}))
    badges: list[tuple[str, str, str]] = []
    if clean.get("prep_batch"):
        badges.append(("fa5s.layer-group", "Prep", "#34d399"))
    leftovers = int(clean.get("leftover_portions") or 0)
    if leftovers > 0:
        badges.append(("fa5s.box-open", f"Leftovers x{leftovers}", "#f0a500"))
    source_day = str(clean.get("leftover_source_day") or "").strip()
    if source_day:
        badges.append(("fa5s.recycle", f"From {source_day[:3]}", "#60a5fa"))
    owner = str(clean.get("owner_label") or "").strip()
    if owner:
        badges.append(("fa5s.user", owner, "#4fc3f7"))
    template_name = str(clean.get("template_name") or "").strip()
    if template_name:
        badges.append(("fa5s.bookmark", template_name[:16], "#c084fc"))
    return badges[:3]


def current_editor_label(db) -> str:
    name = str(db.get_setting("user_name", "") or "").strip()
    if name:
        return name[:24]
    role = str(db.get_setting("household_role", "") or "").strip().lower()
    if role == "owner":
        return "Household owner"
    if role:
        return role.capitalize()
    return "You"


def pantry_expiry_items(db, *, limit: int = 6, soon_days: int = 3) -> list[dict]:
    try:
        from views.my_kitchen_storage import _days_until_expiry
    except Exception:
        return []

    items = []
    try:
        pantry_rows = db.get_pantry_items()
    except Exception:
        pantry_rows = []
    for row in pantry_rows:
        expiry = row.get("expiry_date") or ""
        days = _days_until_expiry(expiry)
        if days is None or days > soon_days:
            continue
        entry = dict(row)
        entry["days_until_expiry"] = int(days)
        items.append(entry)
    items.sort(key=lambda item: (item.get("days_until_expiry", 99), str(item.get("name") or "").lower()))
    return items[:limit]


def summarise_week(rows: list[dict] | list) -> dict:
    prep_slots = 0
    leftover_slots = 0
    planned = 0
    modes: dict[str, int] = {}
    editors: set[str] = set()
    for row in rows or []:
        meta = load_slot_metadata((row.get("notes") if isinstance(row, dict) else row["notes"]) or "")
        if (row.get("custom_name") if isinstance(row, dict) else row["custom_name"]) or (
            row.get("recipe_id") if isinstance(row, dict) else row["recipe_id"]
        ):
            planned += 1
        if meta.get("prep_batch"):
            prep_slots += 1
        if int(meta.get("leftover_portions") or 0) > 0 or meta.get("leftover_source_day"):
            leftover_slots += 1
        owner = str(meta.get("owner_label") or "").strip()
        if owner:
            editors.add(owner)
        mode = str(meta.get("planning_mode") or "").strip()
        if mode:
            modes[mode] = modes.get(mode, 0) + 1
    return {
        "planned_slots": planned,
        "prep_slots": prep_slots,
        "leftover_slots": leftover_slots,
        "active_modes": modes,
        "editors": sorted(editors),
    }


def load_templates(db) -> list[dict]:
    rows = _safe_json_loads(db.get_setting(_TEMPLATE_SETTING_KEY, "[]"), [])
    templates: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = " ".join(str(row.get("name") or "").split()).strip()[:80]
        slots = row.get("slots") or []
        if not name or not isinstance(slots, list):
            continue
        clean_slots = []
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            day = str(slot.get("day") or "").strip()
            meal_type = str(slot.get("meal_type") or "").strip()
            title = " ".join(str(slot.get("recipe_title") or "").split()).strip()
            if not day or not meal_type or not title:
                continue
            clean_slots.append(
                {
                    "day": day,
                    "meal_type": meal_type,
                    "recipe_title": title[:120],
                    "metadata": load_slot_metadata(json.dumps(slot.get("metadata") or {})),
                }
            )
        if not clean_slots:
            continue
        templates.append(
            {
                "name": name,
                "mode": str(row.get("mode") or "balanced").strip().lower() or "balanced",
                "created_at": str(row.get("created_at") or "").strip(),
                "slots": clean_slots,
            }
        )
    templates.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return templates


def save_template(db, name: str, rows: list[dict] | list, *, mode: str | None = None) -> list[dict]:
    title = " ".join(str(name or "").split()).strip()[:80]
    if not title:
        title = f"Week template {datetime.now().strftime('%d %b %Y')}"

    templates = [tpl for tpl in load_templates(db) if tpl.get("name", "").lower() != title.lower()]
    slots: list[dict] = []
    for row in rows or []:
        custom_name = row.get("custom_name") if isinstance(row, dict) else row["custom_name"]
        if not custom_name:
            continue
        slots.append(
            {
                "day": row.get("day_of_week") if isinstance(row, dict) else row["day_of_week"],
                "meal_type": row.get("meal_type") if isinstance(row, dict) else row["meal_type"],
                "recipe_title": custom_name,
                "metadata": load_slot_metadata((row.get("notes") if isinstance(row, dict) else row["notes"]) or ""),
            }
        )
    if not slots:
        return templates
    templates.insert(
        0,
        {
            "name": title,
            "mode": (mode or "balanced"),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "slots": slots,
        },
    )
    templates = templates[:18]
    db.set_setting(_TEMPLATE_SETTING_KEY, json.dumps(templates, separators=(",", ":")))
    return templates


def template_recipe_lookup(db) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    try:
        rows = db.get_saved_recipes()
    except Exception:
        rows = []
    for row in rows:
        key = str(row["title"] or "").strip().lower()
        if key:
            lookup[key] = dict(row)
    return lookup


def resolve_recipe_by_title(db, recipe_title: str):
    lookup = template_recipe_lookup(db)
    return lookup.get(str(recipe_title or "").strip().lower())
