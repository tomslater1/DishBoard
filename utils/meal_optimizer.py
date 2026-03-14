"""Heuristic weekly meal-plan optimizer."""

from __future__ import annotations

import json
from datetime import date, timedelta

from utils.macro_goals import get_macro_goals
from utils.planner_intelligence import (
    current_editor_label,
    dump_slot_metadata,
    get_planning_mode,
    pantry_expiry_items,
)

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


def _day_name_to_index(day: str) -> int:
    try:
        return DAYS.index(day)
    except Exception:
        return 99


def optimize_week(
    db,
    week_start_iso: str | None = None,
    *,
    refill_all: bool = False,
    planning_mode: str | None = None,
    use_leftovers: bool = True,
) -> dict:
    if not week_start_iso:
        week_start_iso = _week_start_from(date.today()).isoformat()

    mode = planning_mode or get_planning_mode(db)
    rows = [dict(r) for r in db.get_saved_recipes()]
    if not rows:
        return {"assigned": 0, "reason": "no_recipes", "planning_mode": mode}

    goals = get_macro_goals(db)
    target_kcal_day = float(goals.get("kcal", 2000) or 2000)
    target_kcal_meal = max(250.0, target_kcal_day / 3.0)
    target_protein_meal = max(12.0, float(goals.get("protein_g", 50) or 50) / 3.0)

    pantry_tokens: set[str] = set()
    for item in db.get_pantry_items():
        name = str(item.get("name") or "").lower()
        pantry_tokens.update(p for p in name.split() if len(p) > 2)

    expiry_tokens: set[str] = set()
    for item in pantry_expiry_items(db, limit=10, soon_days=4):
        expiry_tokens.update(
            token
            for token in str(item.get("name") or "").lower().replace(",", " ").split()
            if len(token) > 2
        )

    existing_rows = [dict(r) for r in db.get_meal_plan(week_start_iso)]
    existing = {(r["day_of_week"], r["meal_type"]): dict(r) for r in existing_rows}
    editor = current_editor_label(db)

    candidates: list[dict] = []
    for row in rows:
        try:
            data = json.loads(row.get("data_json") or "{}")
        except Exception:
            data = {}
        tags = [str(t or "") for t in (data.get("tags") or [])]
        tag_set = {t.lower() for t in tags}
        meal_type = _meal_type_from_tags(tags)
        nutr = _nutrition(data)
        tokens = _ingredient_tokens(data)
        pantry_hits = len(tokens & pantry_tokens)
        expiry_hits = len(tokens & expiry_tokens)
        total_time = float(
            data.get("total_time")
            or ((data.get("prep_time", 0) or 0) + (data.get("cook_time", 0) or 0))
            or row.get("ready_mins")
            or 0
        )
        candidates.append(
            {
                "id": row.get("id"),
                "title": row.get("title") or "",
                "meal_type": meal_type,
                "kcal": nutr["kcal"],
                "protein_g": nutr["protein_g"],
                "pantry_hits": pantry_hits,
                "expiry_hits": expiry_hits,
                "fav": int(row.get("is_favourite") or 0),
                "tags": tag_set,
                "total_time": total_time,
            }
        )

    used_recent: list[int] = []
    leftover_queue: list[dict] = []
    assigned = 0
    leftover_assignments = 0
    prep_slots = 0

    for day in DAYS:
        for meal in MEALS:
            slot = existing.get((day, meal))
            if slot and slot.get("recipe_id") and not refill_all:
                used_recent.append(int(slot.get("recipe_id") or 0))
                continue

            if meal == "lunch" and use_leftovers and leftover_queue:
                leftover = leftover_queue[0]
                meta = {
                    "leftover_source_day": leftover["source_day"],
                    "planning_mode": mode,
                    "owner_label": editor,
                }
                db.set_meal_slot(
                    week_start_iso,
                    day,
                    meal,
                    custom_name=leftover["title"],
                    recipe_id=leftover["recipe_id"],
                    notes=dump_slot_metadata(meta),
                )
                leftover["remaining"] -= 1
                if leftover["remaining"] <= 0:
                    leftover_queue.pop(0)
                used_recent.append(int(leftover["recipe_id"] or 0))
                assigned += 1
                leftover_assignments += 1
                continue

            pool = [c for c in candidates if c["meal_type"] in {meal, "dinner"}]
            if not pool:
                pool = candidates[:]

            def _score(c: dict) -> tuple:
                kcal_penalty = abs(float(c.get("kcal") or 0) - target_kcal_meal)
                protein_bonus = float(c.get("protein_g") or 0)
                recency_penalty = 25 if int(c.get("id") or 0) in used_recent[-6:] else 0
                pantry_bonus = float(c.get("pantry_hits") or 0)
                expiry_bonus = float(c.get("expiry_hits") or 0)
                quick_bonus = 1 if ("quick (< 30 min)" in c.get("tags", set()) or float(c.get("total_time") or 0) <= 30) else 0
                prep_bonus = 1 if ({"meal-prep", "batch cook"} & set(c.get("tags", set()))) else 0
                family_bonus = 1 if "kid-friendly" in c.get("tags", set()) else 0
                budget_bonus = 1 if "budget-friendly" in c.get("tags", set()) else 0

                mode_bonus = 0.0
                mode_penalty = 0.0
                if mode == "high_protein":
                    mode_bonus += protein_bonus * 0.6
                    mode_penalty += abs(protein_bonus - target_protein_meal) * 1.2
                elif mode == "pantry_first":
                    mode_bonus += pantry_bonus * 4.0
                elif mode == "low_effort":
                    mode_bonus += quick_bonus * 12.0
                    mode_penalty += float(c.get("total_time") or 0) / 6.0
                elif mode == "family_friendly":
                    mode_bonus += family_bonus * 15.0
                elif mode == "budget":
                    mode_bonus += budget_bonus * 12.0
                    mode_bonus += pantry_bonus * 2.5
                elif mode == "meal_prep":
                    mode_bonus += prep_bonus * 16.0
                    mode_bonus += protein_bonus * 0.25
                elif mode == "reduce_waste":
                    mode_bonus += expiry_bonus * 8.0
                    mode_bonus += pantry_bonus * 2.0

                return (
                    -(float(c.get("fav") or 0) * 10.0 + mode_bonus + pantry_bonus),
                    kcal_penalty + recency_penalty + mode_penalty,
                    -expiry_bonus,
                    str(c.get("title") or ""),
                )

            pool.sort(key=_score)
            pick = pool[0]
            rid = int(pick.get("id") or 0)

            meta = {"planning_mode": mode, "owner_label": editor}
            is_prep_candidate = meal == "dinner" and (
                mode == "meal_prep" or {"meal-prep", "batch cook"} & set(pick.get("tags", set()))
            )
            if is_prep_candidate:
                meta["prep_batch"] = True
                meta["leftover_portions"] = 2 if mode == "meal_prep" else 1
                leftover_queue.append(
                    {
                        "recipe_id": rid if rid > 0 else None,
                        "title": str(pick.get("title") or "Meal"),
                        "source_day": day,
                        "remaining": int(meta["leftover_portions"]),
                    }
                )
                prep_slots += 1

            db.set_meal_slot(
                week_start_iso,
                day,
                meal,
                custom_name=str(pick.get("title") or "Meal"),
                recipe_id=rid if rid > 0 else None,
                notes=dump_slot_metadata(meta),
            )
            used_recent.append(rid)
            assigned += 1

    return {
        "assigned": assigned,
        "week_start": week_start_iso,
        "target_kcal_meal": round(target_kcal_meal, 1),
        "planning_mode": mode,
        "leftover_assignments": leftover_assignments,
        "prep_slots": prep_slots,
    }

