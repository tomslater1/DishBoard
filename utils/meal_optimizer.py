"""Heuristic weekly meal-plan optimizer."""

from __future__ import annotations

import json
from datetime import date, timedelta

from utils.macro_goals import get_macro_goals

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MEALS = ["breakfast", "lunch", "dinner"]


def _week_start_from(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _meal_type_from_tags(tags: list[str]) -> str:
    tset = {str(t or "").strip().lower() for t in tags or []}
    for candidate in ("breakfast", "lunch", "dinner", "snack", "dessert"):
        if candidate in tset:
            return candidate
    return "dinner"


def _nutrition(data: dict) -> dict:
    per = data.get("nutrition_per_serving") or data.get("nutrition") or {}
    return {
        "kcal": float(per.get("kcal", 0) or 0),
        "protein_g": float(per.get("protein_g", 0) or 0),
        "carbs_g": float(per.get("carbs_g", 0) or 0),
        "fat_g": float(per.get("fat_g", 0) or 0),
    }


def _ingredient_tokens(data: dict) -> set[str]:
    out: set[str] = set()
    for ing in data.get("ingredients", []) or []:
        parts = str(ing or "").lower().replace(",", " ").replace("/", " ").split()
        out.update(p for p in parts if len(p) > 2)
    return out


def optimize_week(db, week_start_iso: str | None = None, *, refill_all: bool = False) -> dict:
    if not week_start_iso:
        week_start_iso = _week_start_from(date.today()).isoformat()

    rows = [dict(r) for r in db.get_saved_recipes()]
    if not rows:
        return {"assigned": 0, "reason": "no_recipes"}

    goals = get_macro_goals(db)
    target_kcal_day = float(goals.get("kcal", 2000) or 2000)
    target_kcal_meal = max(250.0, target_kcal_day / 3.0)

    pantry_tokens: set[str] = set()
    for item in db.get_pantry_items():
        name = str(item.get("name") or "").lower()
        pantry_tokens.update(p for p in name.split() if len(p) > 2)

    existing = {(r["day_of_week"], r["meal_type"]): dict(r) for r in db.get_meal_plan(week_start_iso)}

    candidates: list[dict] = []
    for row in rows:
        try:
            data = json.loads(row.get("data_json") or "{}")
        except Exception:
            data = {}
        tags = data.get("tags") or []
        meal_type = _meal_type_from_tags(tags)
        nutr = _nutrition(data)
        tokens = _ingredient_tokens(data)
        pantry_hits = len(tokens & pantry_tokens)
        candidates.append(
            {
                "id": row.get("id"),
                "title": row.get("title") or "",
                "meal_type": meal_type,
                "kcal": nutr["kcal"],
                "pantry_hits": pantry_hits,
                "fav": int(row.get("is_favourite") or 0),
            }
        )

    used_recent: list[int] = []
    assigned = 0
    for day in DAYS:
        for meal in MEALS:
            slot = existing.get((day, meal))
            if slot and slot.get("recipe_id") and not refill_all:
                used_recent.append(int(slot.get("recipe_id") or 0))
                continue

            pool = [c for c in candidates if c["meal_type"] in {meal, "dinner"}]
            if not pool:
                pool = candidates[:]

            def _score(c: dict) -> tuple:
                kcal_penalty = abs(float(c.get("kcal") or 0) - target_kcal_meal)
                recency_penalty = 25 if int(c.get("id") or 0) in used_recent[-6:] else 0
                return (
                    -float(c.get("fav") or 0),
                    -float(c.get("pantry_hits") or 0),
                    kcal_penalty + recency_penalty,
                    str(c.get("title") or ""),
                )

            pool.sort(key=_score)
            pick = pool[0]
            rid = int(pick.get("id") or 0)
            db.set_meal_slot(
                week_start_iso,
                day,
                meal,
                custom_name=str(pick.get("title") or "Meal"),
                recipe_id=rid if rid > 0 else None,
            )
            used_recent.append(rid)
            assigned += 1

    return {
        "assigned": assigned,
        "week_start": week_start_iso,
        "target_kcal_meal": round(target_kcal_meal, 1),
    }
