"""
Dishy runtime tool executor.

DishyActions — executes tool calls, writes to the DB, and records which
               views need refreshing on the main thread.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.database import Database

# ── Tool schemas (Anthropic format) ──────────────────────────────────────────



# ── Colour / icon helpers ─────────────────────────────────────────────────────

_TAG_COLOUR_ICON: dict[str, tuple[str, str]] = {
    "breakfast":  ("#ff9a5c", "fa5s.bacon"),
    "lunch":      ("#34d399", "fa5s.sun"),
    "dinner":     ("#7c6af7", "fa5s.moon"),
    "snack":      ("#f0a500", "fa5s.apple-alt"),
    "vegetarian": ("#34d399", "fa5s.seedling"),
    "vegan":      ("#34d399", "fa5s.seedling"),
    "quick":      ("#f0a500", "fa5s.bolt"),
    "healthy":    ("#34d399", "fa5s.heart"),
    "dessert":    ("#e05c7a", "fa5s.birthday-cake"),
    "baking":     ("#e05c7a", "fa5s.birthday-cake"),
    "italian":    ("#e05c7a", "fa5s.pizza-slice"),
    "spicy":      ("#ff6b35", "fa5s.pepper-hot"),
    "bbq":        ("#ff6b35", "fa5s.fire"),
    "seafood":    ("#4fc3f7", "fa5s.fish"),
    "chicken":    ("#ff9a5c", "fa5s.drumstick-bite"),
    "pasta":      ("#e05c7a", "fa5s.pizza-slice"),
    "soup":       ("#4fc3f7", "fa5s.mug-hot"),
    "salad":      ("#34d399", "fa5s.leaf"),
}

_DEFAULT_COLOURS = ["#7c6af7", "#ff6b35", "#34d399", "#e05c7a", "#f0a500", "#4fc3f7"]
_DEFAULT_ICONS   = [
    "fa5s.utensils", "fa5s.drumstick-bite", "fa5s.fish",
    "fa5s.carrot", "fa5s.bread-slice", "fa5s.leaf",
]


def _pick_colour_icon(tags: list[str]) -> tuple[str, str]:
    for tag in (t.lower() for t in tags):
        if tag in _TAG_COLOUR_ICON:
            return _TAG_COLOUR_ICON[tag]
    h = abs(hash(tuple(sorted(tags)))) if tags else 0
    return _DEFAULT_COLOURS[h % len(_DEFAULT_COLOURS)], _DEFAULT_ICONS[h % len(_DEFAULT_ICONS)]


def _current_week_start() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


# ── UI helpers (used by chat surfaces) ───────────────────────────────────────

TOOL_STATUS_MESSAGES: dict[str, str] = {
    "save_recipe":                  "Saving recipe...",
    "set_meal_slot":                "Updating meal plan...",
    "fill_week_meal_plan":          "Planning your week...",
    "add_shopping_items":           "Adding to shopping list...",
    "shopping_list_from_meal_plan": "Building shopping list...",
    "log_recipe_nutrition":         "Logging nutrition...",
    "sync_meal_plan_nutrition":     "Syncing nutrition...",
    "delete_meal_slot":             "Removing meal...",
    "clear_meal_day":               "Clearing day...",
    "delete_recipe":                "Removing recipe...",
    "delete_shopping_item":         "Removing item...",
    "clear_meal_plan":              "Clearing meal plan...",
    "clear_recipe_library":         "Clearing library...",
    "clear_shopping_list":          "Clearing shopping list...",
    "add_pantry_item":              "Adding to My Kitchen...",
    "remove_pantry_item":           "Removing from My Kitchen...",
    "clear_pantry_section":         "Clearing My Kitchen...",
    "swap_meal_slots":              "Swapping meals...",
}


def summarise_tool_calls(tool_names: list) -> list:
    """
    Collapse a repeated list of tool call names into one summary label per
    category.  Returns a list of human-readable confirmation strings — one
    entry per tool type that appeared, regardless of how many times.
    """
    from collections import Counter
    counts = Counter(tool_names)
    labels: list[str] = []
    _ORDER = [
        "save_recipe", "fill_week_meal_plan", "set_meal_slot",
        "add_shopping_items", "shopping_list_from_meal_plan",
        "log_recipe_nutrition", "sync_meal_plan_nutrition",
        "delete_meal_slot", "clear_meal_day", "delete_recipe", "delete_shopping_item",
        "clear_meal_plan", "clear_recipe_library", "clear_shopping_list",
    ]
    seen: set = set()
    for key in _ORDER:
        n = counts.get(key, 0)
        if not n:
            continue
        seen.add(key)
        if key == "save_recipe":
            labels.append(f"{n} recipe{'s' if n > 1 else ''} saved to your library")
        elif key == "set_meal_slot":
            labels.append(f"{n} meal{'s' if n > 1 else ''} added to planner")
        elif key == "fill_week_meal_plan":
            labels.append("Week plan filled")
        elif key == "add_shopping_items":
            labels.append("Items added to shopping list")
        elif key == "shopping_list_from_meal_plan":
            labels.append("Shopping list built from meal plan")
        elif key == "log_recipe_nutrition":
            labels.append(f"{n} recipe{'s' if n > 1 else ''} logged to nutrition")
        elif key == "sync_meal_plan_nutrition":
            labels.append("Nutrition synced")
        elif "delete" in key or "clear" in key:
            labels.append(key.replace("_", " ").capitalize())
    for key in counts:
        if key not in seen:
            labels.append(key.replace("_", " ").capitalize())
    return labels


def _maybe_analyze_and_log(db, recipe_id: int, meal_name: str, date_str: str) -> bool:
    """If a recipe has no nutrition data, analyze it now (blocking, call from background thread),
    save the result back to the recipe, then log it to the nutrition tracker.
    Returns True if a log entry was added."""
    try:
        row = db.conn.execute(
            "SELECT data_json FROM recipes WHERE id=?", (recipe_id,)
        ).fetchone()
        if not row:
            return False
        d = json.loads(row["data_json"] or "{}")
        per_s = d.get("nutrition_per_serving", {})
        if float(per_s.get("kcal", 0) or 0) > 0:
            # Already has nutrition — just log it
            return db.auto_log_meal_nutrition(date_str, meal_name, recipe_id)
        ingredients = d.get("ingredients", [])
        if not ingredients:
            return False
        servings = int(d.get("servings") or 2)
        from api.claude_ai import ClaudeAI as _AI
        _ai = _AI()
        nutr = _ai.analyze_recipe_nutrition(ingredients, servings)
        d["nutrition_ingredients"] = nutr.get("ingredients", [])
        d["nutrition_total"]       = nutr.get("total", {})
        d["nutrition_per_serving"] = nutr.get("per_serving", {})
        db.conn.execute(
            "UPDATE recipes SET data_json=? WHERE id=?", (json.dumps(d), recipe_id)
        )
        db.conn.commit()
        return db.auto_log_meal_nutrition(date_str, meal_name, recipe_id)
    except Exception:
        return False


# ── DishyActions ──────────────────────────────────────────────────────────────

class DishyActions:
    """
    Executes Dishy tool calls against the local database.

    execute() runs inside a background worker thread, so we MUST NOT reuse
    the Database connection that was created on the main thread — SQLite
    raises ProgrammingError if a connection is used from a different thread.
    Instead we store only the DB path and open a fresh connection per call.

    After the full chat_with_tools loop completes, read pending_refreshes on
    the main thread to know which views to reload.
    """

    def __init__(self, db: "Database"):
        self._db_path = db.path          # path only — NOT the connection
        self.pending_refreshes: list[str] = []
        self.saved_recipe_id:   int | None = None
        self._managed_tool_db: "Database | None" = None
        self._tool_db_scope_active = False

    def _open_db(self) -> "Database":
        """Open a fresh, thread-local Database connection."""
        if self._tool_db_scope_active and self._managed_tool_db is not None:
            return self._managed_tool_db
        from models.database import Database as _DB
        db = _DB(self._db_path)
        db.connect()
        if self._tool_db_scope_active:
            self._managed_tool_db = db
        return db

    def clear_pending(self):
        self.pending_refreshes.clear()
        self.saved_recipe_id = None

    def get_context_string(self) -> str:
        """
        Build a live context block injected into every Dishy message so it knows
        the user's current data without having to ask.  Called on the main thread.
        """
        db = None
        try:
            db    = self._open_db()
            today = date.today().isoformat()
            lines: list[str] = ["## Live app context"]

            # ── User profile ──────────────────────────────────────────────────
            _HOUSEHOLD_LABELS = {
                "just_me": "cooking for 1", "2_people": "cooking for 2",
                "3_4_people": "cooking for 3–4", "5_plus": "cooking for 5+",
            }
            _SKILL_LABELS = {
                "beginner": "beginner cook", "intermediate": "intermediate cook",
                "advanced": "advanced cook",
            }
            _GOAL_LABELS = {
                "1_2": "1–2 meals/week", "3_4": "3–4 meals/week", "5_plus": "5+ meals/week",
            }
            _SCENARIO_LABELS = {
                "meal_prep": "meal preps in batches",
                "cooking_for_kids": "cooks for kids",
                "weight_loss": "focused on weight loss",
                "muscle_building": "building muscle",
                "quick_meals": "needs quick weeknight meals",
                "adventurous": "loves trying new cuisines",
                "budget_cooking": "cooks on a budget",
                "healthy_eating": "prefers healthy whole foods",
                "learning_to_cook": "learning to cook",
                "dinner_parties": "hosts dinner parties",
            }

            profile_parts: list[str] = []
            name = db.get_setting("user_name", "")
            if name:
                profile_parts.append(f"name is {name}")
            household = db.get_setting("user_household_size", "")
            if household in _HOUSEHOLD_LABELS:
                profile_parts.append(_HOUSEHOLD_LABELS[household])
            skill = db.get_setting("cooking_skill", "")
            if skill in _SKILL_LABELS:
                profile_parts.append(_SKILL_LABELS[skill])
            goal = db.get_setting("weekly_cooking_goal", "")
            if goal in _GOAL_LABELS:
                profile_parts.append(f"aims for {_GOAL_LABELS[goal]}")
            height_cm = str(db.get_setting("body_height_cm", "") or "").strip()
            weight_kg = str(db.get_setting("body_weight_kg", "") or "").strip()
            if height_cm and weight_kg:
                profile_parts.append(f"body metrics {height_cm} cm, {weight_kg} kg")
            if profile_parts:
                lines.append(f"User profile: {'; '.join(profile_parts)}")

            # Linked-account profile 2 metrics (used for shared goal guidance)
            linked_hid = str(db.get_setting("household_id", "") or "").strip()
            if linked_hid:
                p2_name = str(db.get_setting("household_user2_name", "") or "").strip() or "Profile 2"
                p2_h = str(db.get_setting("household_user2_height_cm", "") or "").strip()
                p2_w = str(db.get_setting("household_user2_weight_kg", "") or "").strip()
                if p2_h and p2_w:
                    lines.append(f"Linked profile: {p2_name} ({p2_h} cm, {p2_w} kg)")

            # ── Dietary preferences ───────────────────────────────────────────
            prefs = db.get_setting("dietary_prefs", "")
            if prefs:
                prefs_readable = prefs.replace("_", "-").replace(",", ", ")
                lines.append(f"Dietary requirements: {prefs_readable}")
            allergens = db.get_setting("allergens", "")
            if allergens:
                allergens_readable = allergens.replace("_", " ").replace(",", ", ")
                lines.append(f"Allergens to avoid: {allergens_readable}")
            scenarios = db.get_setting("lifestyle_scenarios", "")
            if scenarios:
                scenario_labels = [_SCENARIO_LABELS.get(s, s) for s in scenarios.split(",") if s]
                lines.append(f"Cooking lifestyle: {'; '.join(scenario_labels)}")
            cuisines = db.get_setting("cuisine_preferences", "")
            if cuisines:
                cuisines_readable = cuisines.replace("_", " ").replace(",", ", ").title()
                lines.append(f"Favourite cuisines: {cuisines_readable}")

            # ── Nutrition goals ──────────────────────────────────────────────
            try:
                from utils.macro_goals import get_macro_goals

                goals = get_macro_goals(db)
                lines.append(
                    "Daily nutrition goals: "
                    f"{round(float(goals.get('kcal', 0) or 0))} kcal | "
                    f"{round(float(goals.get('protein_g', 0) or 0))}g protein | "
                    f"{round(float(goals.get('carbs_g', 0) or 0))}g carbs | "
                    f"{round(float(goals.get('fat_g', 0) or 0))}g fat | "
                    f"{round(float(goals.get('fiber_g', 0) or 0))}g fiber | "
                    f"{round(float(goals.get('sugar_g', 0) or 0))}g sugar"
                )
            except Exception:
                pass

            # ── Saved recipes ─────────────────────────────────────────────────
            recipes = db.get_saved_recipes()
            if recipes:
                titles = [r["title"] for r in recipes[:40]]
                extra  = f" (+ {len(recipes) - 40} more)" if len(recipes) > 40 else ""
                lines.append(f"Saved recipes ({len(recipes)} total){extra}: {', '.join(titles)}")

                # Favourites
                favs = [r["title"] for r in recipes if r["is_favourite"]]
                if favs:
                    lines.append(f"Favourite recipes: {', '.join(favs[:20])}")

                # Per-category breakdown
                try:
                    cat_counts: dict[str, int] = {}
                    for r in recipes:
                        tags = json.loads(r["data_json"] or "{}").get("tags", [])
                        for t in tags:
                            if t in ("Breakfast", "Lunch", "Dinner", "Snack", "Dessert"):
                                cat_counts[t] = cat_counts.get(t, 0) + 1
                                break
                    if cat_counts:
                        breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(cat_counts.items()))
                        lines.append(f"Recipe library breakdown: {breakdown}")
                except Exception:
                    pass

                # Recipes with no nutrition data
                try:
                    no_nutr = []
                    for r in recipes:
                        dj    = json.loads(r["data_json"] or "{}")
                        per_s = dj.get("nutrition_per_serving", {})
                        if not float(per_s.get("kcal", 0) or 0):
                            no_nutr.append(r["title"])
                    if no_nutr:
                        lines.append(
                            f"Recipes missing nutrition data ({len(no_nutr)}): "
                            f"{', '.join(no_nutr[:10])}"
                            + (" (+ more)" if len(no_nutr) > 10 else "")
                        )
                except Exception:
                    pass
            else:
                lines.append("Saved recipes: none yet")

            # ── This week's meal plan ─────────────────────────────────────────
            week_start = _current_week_start()
            meal_rows  = db.get_meal_plan(week_start)
            DAYS  = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            MEALS = ["breakfast","lunch","dinner","snack"]
            if meal_rows:
                by_day: dict[str, dict] = {}
                for row in meal_rows:
                    by_day.setdefault(row["day_of_week"], {})[row["meal_type"]] = row["custom_name"] or ""
                plan_lines = []
                for day in DAYS:
                    slots = by_day.get(day, {})
                    parts = [f"{m}: {slots[m]}" for m in MEALS if slots.get(m)]
                    if parts:
                        plan_lines.append(f"  {day}: {', '.join(parts)}")
                if plan_lines:
                    lines.append("This week's meal plan:\n" + "\n".join(plan_lines))
                else:
                    lines.append("This week's meal plan: empty")
            else:
                lines.append("This week's meal plan: empty")

            # ── Shopping list (unchecked) ─────────────────────────────────────
            unchecked = [row["name"] for row in db.get_shopping_items() if not row["checked"]]
            if unchecked:
                lines.append(f"Shopping list ({len(unchecked)} items): {', '.join(unchecked[:25])}")
            else:
                lines.append("Shopping list: empty")

            # ── My Kitchen (pantry / fridge / freezer) ────────────────────────
            pantry_items = db.get_pantry_items()
            if pantry_items:
                by_storage: dict[str, list] = {"Pantry": [], "Fridge": [], "Freezer": []}
                for item in pantry_items:
                    label = item["name"]
                    if item.get("quantity"):
                        label += f" ({item['quantity']} {item.get('unit', '')})"
                    by_storage.get(item["storage"], by_storage["Pantry"]).append(label)
                lines.append("\n### My Kitchen")
                for section, items in by_storage.items():
                    if items:
                        lines.append(f"{section}: {', '.join(items)}")
            else:
                lines.append("\n### My Kitchen\nEmpty — user hasn't added any ingredients yet.")

            # ── Expiring soon ─────────────────────────────────────────────────
            if pantry_items:
                expiring: list[str] = []
                for item in pantry_items:
                    exp = (item.get("expiry_date") or "").strip()
                    if not exp:
                        continue
                    try:
                        delta = (date.fromisoformat(exp) - date.today()).days
                    except ValueError:
                        continue
                    if delta < 0:
                        expiring.append(f"{item['name']} (EXPIRED {abs(delta)}d ago)")
                    elif delta <= 3:
                        expiring.append(f"{item['name']} (expires in {delta}d)")
                if expiring:
                    lines.append(f"⚠️ Expiring soon: {', '.join(expiring)}")

            # ── Today's nutrition ─────────────────────────────────────────────
            logs = db.get_nutrition_logs(today)
            if logs:
                kcal    = sum(r["kcal"]      for r in logs)
                protein = sum(r["protein_g"] for r in logs)
                carbs   = sum(r["carbs_g"]   for r in logs)
                fat     = sum(r["fat_g"]     for r in logs)
                fiber   = sum(r["fiber_g"]   for r in logs)
                foods   = ", ".join(r["food_name"] for r in logs)
                lines.append(
                    f"Today's nutrition: {kcal:.0f} kcal | {protein:.0f}g protein | "
                    f"{carbs:.0f}g carbs | {fat:.0f}g fat | {fiber:.0f}g fiber. "
                    f"Foods logged: {foods}"
                )
            else:
                lines.append("Today's nutrition: nothing logged yet")

            # ── Today's meal plan nutrition sync status ────────────────────────
            # Show which of today's planned meals are logged vs still pending,
            # so Dishy knows when to proactively offer to sync.
            today_name = date.today().strftime("%A")
            today_plan_rows = db.conn.execute(
                "SELECT meal_type, custom_name, recipe_id FROM meal_plans "
                "WHERE week_start=? AND day_of_week=?",
                (week_start, today_name),
            ).fetchall()
            if today_plan_rows:
                logged_names = {r["food_name"].lower() for r in logs}
                sync_lines: list[str] = []
                unsynced_count = 0
                for meal in today_plan_rows:
                    meal_name  = meal["custom_name"] or ""
                    meal_type  = meal["meal_type"]
                    recipe_id  = meal["recipe_id"]
                    has_nutr   = False
                    meal_kcal  = ""
                    if recipe_id:
                        try:
                            rec = db.conn.execute(
                                "SELECT data_json FROM recipes WHERE id=?", (recipe_id,)
                            ).fetchone()
                            if rec:
                                dj    = json.loads(rec["data_json"] or "{}")
                                per_s = dj.get("nutrition_per_serving", {})
                                k     = float(per_s.get("kcal", 0) or 0)
                                if k > 0:
                                    has_nutr  = True
                                    meal_kcal = f" ({round(k)} kcal)"
                        except Exception:
                            pass
                    already_logged = meal_name.lower() in logged_names
                    if already_logged:
                        status = "logged"
                    elif has_nutr:
                        status = "not yet logged"
                        unsynced_count += 1
                    else:
                        status = "no nutrition data"
                    sync_lines.append(
                        f"  {meal_type.capitalize()} — {meal_name}{meal_kcal}: {status}"
                    )
                sync_summary = "all synced" if unsynced_count == 0 else f"{unsynced_count} meal(s) not yet logged"
                lines.append(
                    f"Today's meal plan sync status ({sync_summary}):\n" + "\n".join(sync_lines)
                )

            # ── This week's nutrition (last 7 days) ───────────────────────────
            week_ago = (date.today() - timedelta(days=6)).isoformat()
            weekly = db.get_nutrition_totals_for_range(week_ago, today)
            if weekly["entries"] > 0 and weekly["days"] > 0:
                avg_kcal = weekly["kcal"] / weekly["days"]
                lines.append(
                    f"This week's nutrition ({weekly['days']} days tracked): "
                    f"{round(weekly['kcal'])} kcal total | avg {round(avg_kcal)} kcal/day | "
                    f"{round(weekly['protein_g'])}g protein | {round(weekly['carbs_g'])}g carbs | "
                    f"{round(weekly['fat_g'])}g fat"
                )
            else:
                lines.append("This week's nutrition: no data logged this week")

            return "\n".join(lines)
        except Exception:
            return ""
        finally:
            try:
                if db is not None and db is not self._managed_tool_db:
                    db.close()
            except Exception:
                pass

    def get_memory_context(self, query: str) -> str:
        """Return compact, query-targeted memory snippets for the current turn."""
        db = None
        try:
            db = self._open_db()
            active_user = db.get_setting("active_user_id", "")
            try:
                from utils.feature_flags import FeatureFlagService

                if not FeatureFlagService(db, active_user).is_enabled("dishy_memory_context", default=True):
                    return ""
            except Exception:
                pass

            from utils.ai_memory import build_memory_context

            return build_memory_context(db, query, max_items=12)
        except Exception:
            return ""
        finally:
            try:
                if db is not None and db is not self._managed_tool_db:
                    db.close()
            except Exception:
                pass

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """Dispatch a tool. Returns a plain-text result string sent back to Claude."""
        self._tool_db_scope_active = True
        self._managed_tool_db = None
        try:
            handler = getattr(self, f"_tool_{tool_name}", None)
            if handler is None:
                return f"Unknown tool: {tool_name}"
            return handler(tool_input)
        except Exception as exc:
            return f"Error running {tool_name}: {exc}"
        finally:
            try:
                if self._managed_tool_db is not None:
                    self._managed_tool_db.close()
            except Exception:
                pass
            self._managed_tool_db = None
            self._tool_db_scope_active = False

    # ── Individual tool handlers ──────────────────────────────────────────────

    # Canonical meal-type tags used by the filter bar (title-case)
    _MEAL_TAGS = {"Breakfast", "Lunch", "Dinner", "Snack", "Dessert"}
    # Map any case variant to the canonical form
    _MEAL_TAG_NORM = {t.lower(): t for t in _MEAL_TAGS}

    def _normalise_tags(self, tags: list[str]) -> list[str]:
        """Ensure meal-type tags are title-case to match the filter bar chips."""
        result = []
        seen_meal = False
        for t in tags:
            canonical = self._MEAL_TAG_NORM.get(t.strip().lower())
            if canonical:
                if not seen_meal:
                    result.append(canonical)
                    seen_meal = True
            else:
                result.append(t.strip())
        return result

    def _tool_save_recipe(self, inp: dict) -> str:
        title        = (inp.get("title") or "Untitled Recipe").strip()
        summary      = (inp.get("summary") or "").strip()
        servings     = int(inp.get("servings") or 2)
        ready_mins   = int(inp.get("ready_mins") or 30)
        ingredients  = inp.get("ingredients") or []
        instructions = inp.get("instructions") or []
        raw_tags     = inp.get("tags") or []
        tags         = self._normalise_tags(raw_tags)
        # Always prepend the Dishy tag so AI-created recipes are identifiable
        if "Dishy" not in tags:
            tags = ["Dishy"] + tags

        # Dishy recipes always use Dishy's own branding
        colour = "#34d399"   # Dishy green
        icon   = "fa5s.robot"
        recipe_data: dict = {
            "ingredients":  ingredients,
            "instructions": instructions,
            "tags":         tags,
            "colour":       colour,
            "icon":         icon,
            "description":  summary,
        }

        # Use nutrition provided directly by Claude (in the tool input) if non-zero.
        # This avoids a redundant Haiku re-analysis API call on every save.
        inline_nutr = inp.get("nutrition_per_serving") or {}
        _MACRO_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g")
        inline_has_data = isinstance(inline_nutr, dict) and any(
            float(inline_nutr.get(k, 0) or 0) > 0 for k in _MACRO_KEYS
        )

        if inline_has_data:
            # Reconstruct a per-serving dict from Claude's inline values
            per_serving = {k: float(inline_nutr.get(k, 0) or 0) for k in _MACRO_KEYS}
            # Derive totals by multiplying per serving by servings count
            total = {k: round(per_serving[k] * servings, 1) for k in _MACRO_KEYS}
            recipe_data["nutrition_per_serving"] = per_serving
            recipe_data["nutrition_total"]       = total
            recipe_data["nutrition_ingredients"] = []   # detailed breakdown not available inline
        else:
            # Fallback: call analyze_recipe_nutrition (slower but guaranteed)
            try:
                from api.claude_ai import ClaudeAI as _ClaudeAI
                _ai = _ClaudeAI()
                nutr = _ai.analyze_recipe_nutrition(ingredients, servings)
                recipe_data["nutrition_ingredients"] = nutr.get("ingredients", [])
                recipe_data["nutrition_total"]       = nutr.get("total", {})
                recipe_data["nutrition_per_serving"] = nutr.get("per_serving", {})
            except Exception:
                pass  # save anyway as last resort — the recipe view will back-fill

        data_json = json.dumps(recipe_data)

        db = self._open_db()
        recipe_id = db.save_recipe(
            source_id=f"dishy_{int(datetime.now().timestamp())}",
            source="dishy",
            title=title,
            image_url="",
            summary=summary,
            servings=servings,
            ready_mins=ready_mins,
            data_json=data_json,
        )
        self.saved_recipe_id = recipe_id

        # Background image upload (no-op if no image URL)
        _image_url = inp.get("image_url") or ""
        if _image_url:
            try:
                from utils.image_upload import upload_recipe_image, is_supabase_url
                from auth.supabase_client import get_client as _get_sb, is_online
                from utils.workers import run_async
                if not is_supabase_url(_image_url) and is_online():
                    _sb = _get_sb()
                    if _sb:
                        _session = _sb.auth.get_session()
                        _user_id = str(_session.session.user.id)
                        _rid = recipe_id

                        def _upload_img():
                            return upload_recipe_image(_sb, _user_id, _rid, _image_url)

                        def _update_img(cdn_url):
                            if cdn_url:
                                try:
                                    _udb = self._open_db()
                                    _udb.conn.execute(
                                        "UPDATE recipes SET image_url=? WHERE id=?",
                                        (cdn_url, _rid)
                                    )
                                    _udb.conn.commit()
                                except Exception:
                                    pass

                        run_async(_upload_img, _update_img)
            except Exception:
                pass

        if "recipes" not in self.pending_refreshes:
            self.pending_refreshes.append("recipes")
        if "nutrition" not in self.pending_refreshes:
            self.pending_refreshes.append("nutrition")
        return f"Recipe '{title}' saved successfully (id {recipe_id})."

    def _tool_set_meal_slot(self, inp: dict) -> str:
        day       = (inp.get("day") or "").strip()
        meal_type = (inp.get("meal_type") or "").strip()
        name      = (inp.get("meal_name") or "").strip()

        if not all([day, meal_type, name]):
            return "Missing fields: day, meal_type, and meal_name are all required."

        # Meals MUST link to a saved recipe — no custom names without a recipe
        db = self._open_db()
        recipe_id: int | None = None
        for r in db.get_saved_recipes():
            if r["title"].strip().lower() == name.lower():
                recipe_id = r["id"]
                break

        if not recipe_id:
            saved_titles = [r["title"] for r in db.get_saved_recipes()]
            suggestions  = ", ".join(f"'{t}'" for t in saved_titles[:5])
            return (
                f"Cannot add '{name}' — meals must be linked to a saved recipe. "
                f"That recipe doesn't exist in the library yet. "
                f"Save it first using save_recipe, then set the meal slot. "
                f"Available recipes include: {suggestions or 'none yet'}."
            )

        week_start = _current_week_start()
        db.set_meal_slot(
            week_start, day, meal_type,
            custom_name=name, recipe_id=recipe_id,
        )
        if "meal_planner" not in self.pending_refreshes:
            self.pending_refreshes.append("meal_planner")

        # Auto-log nutrition if this slot is for today
        if recipe_id and day.lower() == date.today().strftime("%A").lower():
            logged = db.auto_log_meal_nutrition(date.today().isoformat(), name, recipe_id)
            if not logged:
                # Recipe may lack nutrition data — analyze now (we're on a background thread)
                _maybe_analyze_and_log(db, recipe_id, name, date.today().isoformat())
            if "nutrition" not in self.pending_refreshes:
                self.pending_refreshes.append("nutrition")

        return f"Set {day} {meal_type} to '{name}'."

    def _tool_fill_week_meal_plan(self, inp: dict) -> str:
        db    = self._open_db()

        ws    = date.fromisoformat(_current_week_start())
        we    = ws + timedelta(days=6)
        label = f"{ws.strftime('%d %b')} – {we.strftime('%d %b %Y')}"

        # Use the plan Claude decided on and passed directly via the tool parameter.
        # This eliminates a redundant Haiku API sub-call to plan_week_structured.
        plan: dict = inp.get("plan") or {}
        if not plan:
            # Fallback: generate plan with Haiku (old path, only hit if Claude omits 'plan')
            from api.claude_ai import ClaudeAI
            ai    = ClaudeAI()
            saved = [r["title"] for r in db.get_saved_recipes()]
            prefs = (inp.get("preferences") or "").strip() or db.get_setting("dietary_prefs", "")
            plan  = ai.plan_week_structured(saved, prefs, label)

        # Cache saved recipes once for ID matching
        saved_rows  = db.get_saved_recipes()
        recipe_map  = {r["title"].strip().lower(): r["id"] for r in saved_rows}
        week_start  = _current_week_start()
        DAYS  = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        MEALS = ["breakfast", "lunch", "dinner", "snack"]
        filled = 0
        for day in DAYS:
            day_plan = plan.get(day, {})
            for meal_type in MEALS:
                name = (day_plan.get(meal_type) or "").strip()
                if name:
                    recipe_id = recipe_map.get(name.lower())
                    if not recipe_id:
                        continue
                    db.set_meal_slot(
                        week_start, day, meal_type,
                        custom_name=name, recipe_id=recipe_id,
                    )
                    filled += 1

        if "meal_planner" not in self.pending_refreshes:
            self.pending_refreshes.append("meal_planner")

        # Auto-log nutrition for today's meals from the new plan
        today_name = date.today().strftime("%A")
        today_str  = date.today().isoformat()
        today_plan = plan.get(today_name, {})
        for meal_type in ["breakfast", "lunch", "dinner", "snack"]:
            name = (today_plan.get(meal_type) or "").strip()
            if name:
                rid = recipe_map.get(name.lower())
                if rid:
                    logged = db.auto_log_meal_nutrition(today_str, name, rid)
                    if not logged:
                        # Recipe may lack nutrition — analyze + save + log (on background thread)
                        _maybe_analyze_and_log(db, rid, name, today_str)
        if "nutrition" not in self.pending_refreshes:
            self.pending_refreshes.append("nutrition")

        return f"Filled {filled} meal slots for the week of {label}."

    def _tool_add_shopping_items(self, inp: dict) -> str:
        db    = self._open_db()
        items = inp.get("items") or []
        added = 0
        for item in items:
            name = (item.get("name") or "").strip()
            if not name:
                continue
            qty  = (item.get("quantity") or "").strip()
            unit = (item.get("unit") or "").strip()
            # Inline quantity/unit into the display name for simplicity
            display = f"{qty} {unit} {name}".strip() if (qty or unit) else name
            db.add_shopping_item(display, quantity=qty, unit=unit, source="dishy")
            added += 1
        if "shopping_list" not in self.pending_refreshes:
            self.pending_refreshes.append("shopping_list")
        return f"Added {added} item(s) to the shopping list."

    def _tool_delete_meal_slot(self, inp: dict) -> str:
        day       = (inp.get("day") or "").strip()
        meal_type = (inp.get("meal_type") or "").strip()
        if not (day and meal_type):
            return "Missing fields: day and meal_type are required."
        db         = self._open_db()
        week_start = _current_week_start()
        db.clear_meal_slot(week_start, day, meal_type)
        if "meal_planner" not in self.pending_refreshes:
            self.pending_refreshes.append("meal_planner")
        return f"Removed {day} {meal_type} from the meal plan."

    def _tool_clear_meal_day(self, inp: dict) -> str:
        day = (inp.get("day") or "").strip()
        if not day:
            return "Missing field: day is required."
        db         = self._open_db()
        week_start = _current_week_start()
        db.clear_meal_day_slots(week_start, day)
        if "meal_planner" not in self.pending_refreshes:
            self.pending_refreshes.append("meal_planner")
        return f"Cleared all meals (breakfast, lunch, dinner, snack) for {day}."

    def _tool_clear_meal_plan(self, inp: dict) -> str:
        db         = self._open_db()
        all_weeks  = bool(inp.get("all_weeks", False))
        if all_weeks:
            db.clear_all_meal_plans()
            if "meal_planner" not in self.pending_refreshes:
                self.pending_refreshes.append("meal_planner")
            return "Cleared all meal plan data across every week."
        week_start = _current_week_start()
        db.clear_week_meal_plan(week_start)
        if "meal_planner" not in self.pending_refreshes:
            self.pending_refreshes.append("meal_planner")
        return "Cleared the entire meal plan for this week."

    def _tool_swap_meal_slots(self, inp: dict) -> str:
        day1   = (inp.get("day1")        or "").strip()
        type1  = (inp.get("meal_type1")  or "").strip()
        day2   = (inp.get("day2")        or "").strip()
        type2  = (inp.get("meal_type2")  or "").strip()
        if not all([day1, type1, day2, type2]):
            return "Missing fields: day1, meal_type1, day2, and meal_type2 are all required."
        db         = self._open_db()
        week_start = _current_week_start()

        def _get_slot(day, meal_type):
            return db.conn.execute(
                "SELECT id, recipe_id, custom_name, notes FROM meal_plans "
                "WHERE week_start=? AND day_of_week=? AND meal_type=?",
                (week_start, day, meal_type),
            ).fetchone()

        slot1 = _get_slot(day1, type1)
        slot2 = _get_slot(day2, type2)

        # Nothing in either slot — nothing to swap
        if slot1 is None and slot2 is None:
            return f"Both {day1} {type1} and {day2} {type2} are empty — nothing to swap."

        def _upsert(day, meal_type, source_slot):
            if source_slot is None:
                db.conn.execute(
                    "DELETE FROM meal_plans WHERE week_start=? AND day_of_week=? AND meal_type=?",
                    (week_start, day, meal_type),
                )
            else:
                existing = _get_slot(day, meal_type)
                if existing:
                    db.conn.execute(
                        "UPDATE meal_plans SET recipe_id=?, custom_name=?, notes=?, updated_at=datetime('now') "
                        "WHERE week_start=? AND day_of_week=? AND meal_type=?",
                        (source_slot["recipe_id"], source_slot["custom_name"],
                         source_slot["notes"], week_start, day, meal_type),
                    )
                else:
                    db.conn.execute(
                        "INSERT INTO meal_plans (week_start, day_of_week, meal_type, recipe_id, custom_name, notes) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (week_start, day, meal_type, source_slot["recipe_id"],
                         source_slot["custom_name"], source_slot["notes"]),
                    )

        _upsert(day1, type1, slot2)
        _upsert(day2, type2, slot1)
        db.conn.commit()

        if "meal_planner" not in self.pending_refreshes:
            self.pending_refreshes.append("meal_planner")

        name1 = (slot1["custom_name"] if slot1 else "empty") if slot1 else "empty"
        name2 = (slot2["custom_name"] if slot2 else "empty") if slot2 else "empty"
        return (
            f"Swapped {day1} {type1} ({name1}) ↔ {day2} {type2} ({name2})."
        )

    def _tool_delete_shopping_item(self, inp: dict) -> str:
        name = (inp.get("item_name") or "").strip()
        if not name:
            return "Missing field: item_name is required."
        db      = self._open_db()
        deleted = db.delete_shopping_item_by_name(name)
        if "shopping_list" not in self.pending_refreshes:
            self.pending_refreshes.append("shopping_list")
        if deleted:
            return f"Removed '{name}' from the shopping list."
        return f"No item named '{name}' found in the shopping list."

    def _tool_clear_shopping_list(self, inp: dict) -> str:
        db = self._open_db()
        db.clear_all_shopping_items()
        if "shopping_list" not in self.pending_refreshes:
            self.pending_refreshes.append("shopping_list")
        return "Cleared all items from the shopping list."

    def _tool_delete_recipe(self, inp: dict) -> str:
        title   = (inp.get("title") or "").strip()
        if not title:
            return "Missing field: title is required."
        db      = self._open_db()
        deleted = db.delete_recipe_by_title(title)
        if "recipes" not in self.pending_refreshes:
            self.pending_refreshes.append("recipes")
        if deleted:
            return f"Deleted recipe '{title}' from your library."
        return f"No recipe titled '{title}' found."

    def _tool_clear_recipe_library(self, inp: dict) -> str:
        db = self._open_db()
        db.delete_all_recipes()
        if "recipes" not in self.pending_refreshes:
            self.pending_refreshes.append("recipes")
        return "Deleted all recipes from the library."

    def _tool_log_recipe_nutrition(self, inp: dict) -> str:
        title          = (inp.get("recipe_title") or "").strip()
        servings_eaten = float(inp.get("servings_eaten") or 1)
        if not title:
            return "Missing field: recipe_title is required."
        db  = self._open_db()
        row = db.conn.execute(
            "SELECT * FROM recipes WHERE lower(title) = lower(?) LIMIT 1", (title,)
        ).fetchone()
        if not row:
            return (
                f"No recipe titled '{title}' found in your library. "
                "Check the title or ask the user to confirm."
            )
        data = json.loads(row["data_json"] or "{}")
        nutr = data.get("nutrition_per_serving") or data.get("nutrition_total")
        if not nutr:
            return (
                f"Recipe '{title}' doesn't have nutrition data stored yet. "
                "Open it in the Recipes tab to generate its nutrition breakdown first, "
                "or ask the user to log the food manually from the Nutrition page."
            )
        today = date.today().isoformat()

        def _g(key: str, alt: str = "") -> float:
            v = float(nutr.get(key, 0) or 0)
            if not v and alt:
                v = float(nutr.get(alt, 0) or 0)
            return v * servings_eaten

        kcal    = _g("kcal")
        protein = _g("protein_g", "protein")
        carbs   = _g("carbs_g",   "carbs")
        fat     = _g("fat_g",     "fat")
        fiber   = _g("fiber_g",   "fiber")
        sugar   = _g("sugar_g",   "sugar")

        label = title + (f" ×{servings_eaten}" if servings_eaten != 1 else "")
        db.add_nutrition_log(today, label[:80], kcal, protein, carbs, fat, fiber, sugar)
        if "nutrition" not in self.pending_refreshes:
            self.pending_refreshes.append("nutrition")
        return (
            f"Logged '{title}' to today's nutrition: "
            f"{round(kcal)} kcal | {round(protein, 1)}g protein | "
            f"{round(carbs, 1)}g carbs | {round(fat, 1)}g fat."
        )

    def _tool_sync_meal_plan_nutrition(self, inp: dict) -> str:
        day_input = (inp.get("day") or "today").strip().lower()
        overwrite = bool(inp.get("overwrite", False))

        today = date.today()
        if day_input in ("today", ""):
            target_date = today
            target_day  = today.strftime("%A")
        else:
            day_names = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
            if day_input in day_names:
                week_s_date = date.fromisoformat(_current_week_start())
                offset      = day_names.index(day_input)
                target_date = week_s_date + timedelta(days=offset)
                target_day  = day_input.capitalize()
            else:
                return (
                    f"Unrecognised day '{inp.get('day')}'. "
                    "Use a day name like 'Monday' or 'today'."
                )

        date_str   = target_date.isoformat()
        db         = self._open_db()
        week_start = _current_week_start()

        plan_rows = db.conn.execute(
            "SELECT meal_type, custom_name, recipe_id FROM meal_plans "
            "WHERE week_start=? AND day_of_week=?",
            (week_start, target_day),
        ).fetchall()

        if not plan_rows:
            return (
                f"No meals are planned for {target_day}. "
                "Add meals to the Meal Planner first, then I can track the nutrition."
            )

        existing: set[str] = set()
        if not overwrite:
            existing = {r["food_name"].lower() for r in db.get_nutrition_logs(date_str)}

        logged:               list[str] = []
        skipped_duplicate:    list[str] = []
        skipped_no_nutrition: list[str] = []

        total_kcal = total_protein = total_carbs = total_fat = 0.0

        for meal in plan_rows:
            recipe_id = meal["recipe_id"]
            meal_name = (meal["custom_name"] or "").strip()
            meal_type = meal["meal_type"]

            if not recipe_id or not meal_name:
                continue

            if meal_name.lower() in existing:
                skipped_duplicate.append(meal_name)
                continue

            rec = db.conn.execute(
                "SELECT data_json FROM recipes WHERE id=?", (recipe_id,)
            ).fetchone()
            if not rec:
                continue

            try:
                dj    = json.loads(rec["data_json"] or "{}")
                per_s = dj.get("nutrition_per_serving", {})
                kcal  = float(per_s.get("kcal", 0) or 0)
                if kcal <= 0:
                    skipped_no_nutrition.append(meal_name)
                    continue
                prot  = float(per_s.get("protein_g", 0) or 0)
                carbs = float(per_s.get("carbs_g",   0) or 0)
                fat   = float(per_s.get("fat_g",     0) or 0)
                fiber = float(per_s.get("fiber_g",   0) or 0)
                sugar = float(per_s.get("sugar_g",   0) or 0)
                db.add_nutrition_log(
                    date_str, meal_name[:80],
                    kcal, prot, carbs, fat, fiber, sugar,
                )
                existing.add(meal_name.lower())
                total_kcal    += kcal
                total_protein += prot
                total_carbs   += carbs
                total_fat     += fat
                logged.append(
                    f"{meal_type.capitalize()}: {meal_name} — "
                    f"{round(kcal)} kcal | {round(prot,1)}g protein | "
                    f"{round(carbs,1)}g carbs | {round(fat,1)}g fat"
                )
            except Exception:
                pass

        if "nutrition" not in self.pending_refreshes:
            self.pending_refreshes.append("nutrition")

        parts: list[str] = []
        if logged:
            parts.append(
                f"Logged {len(logged)} meal(s) for {target_day}:\n" +
                "\n".join(logged)
            )
            parts.append(
                f"Total for {target_day}: "
                f"{round(total_kcal)} kcal | "
                f"{round(total_protein,1)}g protein | "
                f"{round(total_carbs,1)}g carbs | "
                f"{round(total_fat,1)}g fat"
            )
        if skipped_duplicate:
            parts.append(
                f"Already logged (skipped): {', '.join(skipped_duplicate)}"
            )
        if skipped_no_nutrition:
            parts.append(
                f"No nutrition data for: {', '.join(skipped_no_nutrition)} "
                f"— open these recipes in the Recipes tab to generate their nutrition breakdown."
            )
        if not parts:
            return f"Nothing new to log for {target_day} — all meals already tracked."
        return "\n".join(parts)

    # Common pantry staples to skip when building from meal plan
    _PANTRY_STAPLES = {
        "salt", "sea salt", "kosher salt", "table salt", "black pepper", "pepper",
        "white pepper", "ground pepper", "olive oil", "vegetable oil", "sunflower oil",
        "oil", "water", "sugar", "brown sugar", "caster sugar", "icing sugar",
        "plain flour", "flour", "self-raising flour", "baking powder", "baking soda",
        "bicarbonate of soda", "vanilla extract", "vanilla essence",
    }

    @staticmethod
    def _ingredient_base_key(ing: str) -> str:
        """Extract a normalised base name for deduplication (strips leading quantities)."""
        import re
        # Strip leading quantity patterns: digits, fractions, units
        cleaned = re.sub(
            r"^[\d\s\/½¼¾⅓⅔⅛⅜⅝⅞]+\s*"
            r"(g|kg|ml|l|oz|lb|cup|cups|tsp|tbsp|tablespoons?|teaspoons?|"
            r"cloves?|pinch|dash|handful|bunch|can|cans|slice|slices|"
            r"piece|pieces|head|heads|sprig|sprigs|cm|inch|inches|"
            r"portions?|packets?|packs?|tins?|jars?|bottles?|"
            r"large|medium|small|big)?\s*",
            ing.lower().strip(),
            flags=re.IGNORECASE,
        )
        return cleaned.strip(" ,()")

    def _tool_shopping_list_from_meal_plan(self, inp: dict) -> str:
        db          = self._open_db()
        week_start  = _current_week_start()
        rows        = db.get_meal_plan(week_start)
        saved_rows  = db.get_saved_recipes()
        recipe_by_id = {r["id"]: r for r in saved_rows}

        # Collect all raw ingredients from this week's plan
        all_ingredients: list[str] = []
        for row in rows:
            recipe_id = row["recipe_id"]
            if not recipe_id:
                continue
            recipe = recipe_by_id.get(recipe_id)
            if not recipe:
                continue
            try:
                data = json.loads(recipe["data_json"] or "{}")
            except Exception:
                continue
            all_ingredients.extend(data.get("ingredients", []))

        # Deduplicate by base ingredient key; skip pantry staples
        seen_keys: set[str] = set()
        added: int = 0
        skipped_staples: int = 0
        for ing in all_ingredients:
            base = self._ingredient_base_key(ing)
            if not base:
                continue
            # Check if it's a pantry staple
            if base in self._PANTRY_STAPLES:
                skipped_staples += 1
                continue
            # Deduplicate by base key
            if base in seen_keys:
                continue
            seen_keys.add(base)
            db.add_shopping_item(ing, source="meal_plan")
            added += 1

        if "shopping_list" not in self.pending_refreshes:
            self.pending_refreshes.append("shopping_list")

        msg = f"Added {added} ingredient(s) from this week's meal plan to the shopping list."
        if skipped_staples:
            msg += (
                f" Skipped {skipped_staples} pantry staple(s) (salt, pepper, oil, etc.) "
                "— a Pantry mode is coming soon to let you manage what you already have."
            )
        return msg

    def _tool_add_pantry_item(self, inp: dict) -> str:
        name     = (inp.get("name") or "").strip()
        if not name:
            return "Missing field: name is required."
        qty_str  = (inp.get("quantity") or "").strip()
        unit     = (inp.get("unit") or "").strip()
        storage  = (inp.get("storage") or "Pantry").strip()
        if storage not in ("Pantry", "Fridge", "Freezer"):
            storage = "Pantry"
        try:
            qty = float(qty_str) if qty_str else None
        except ValueError:
            qty = None
        db = self._open_db()
        db.add_pantry_item(name, qty, unit, storage)
        if "my_kitchen" not in self.pending_refreshes:
            self.pending_refreshes.append("my_kitchen")
        qty_label = f" ({qty_str} {unit})".strip() if (qty_str or unit) else ""
        return f"Added '{name}'{qty_label} to {storage} in My Kitchen."

    def _tool_remove_pantry_item(self, inp: dict) -> str:
        name    = (inp.get("name") or "").strip()
        storage = (inp.get("storage") or "").strip()
        if not name:
            return "Missing field: name is required."
        db    = self._open_db()
        items = db.get_pantry_items(storage if storage else None)
        name_lower = name.lower()
        match = None
        for item in items:
            if (item["name"].lower() in name_lower or name_lower in item["name"].lower()):
                match = item
                break
        if not match:
            return f"No item matching '{name}' found in My Kitchen."
        db.delete_pantry_item(match["id"])
        if "my_kitchen" not in self.pending_refreshes:
            self.pending_refreshes.append("my_kitchen")
        return f"Removed '{match['name']}' from {match['storage']} in My Kitchen."

    def _tool_clear_pantry_section(self, inp: dict) -> str:
        storage = (inp.get("storage") or "").strip()
        if not storage:
            return "Missing field: storage is required."
        db = self._open_db()
        if storage == "all":
            db.clear_pantry()
            msg = "Cleared all items from My Kitchen (Pantry, Fridge, and Freezer)."
        elif storage in ("Pantry", "Fridge", "Freezer"):
            db.clear_pantry(storage)
            msg = f"Cleared all items from {storage} in My Kitchen."
        else:
            return f"Invalid storage '{storage}'. Use Pantry, Fridge, Freezer, or all."
        if "my_kitchen" not in self.pending_refreshes:
            self.pending_refreshes.append("my_kitchen")
        return msg
