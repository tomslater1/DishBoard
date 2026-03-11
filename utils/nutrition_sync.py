"""
NutritionSyncService — background QTimer that continuously reconciles today's
meal plan against the nutrition log, logging and analyzing macros automatically.

Runs on the main thread (QTimer), dispatches background workers only when a
recipe needs macro analysis (network call). All DB reads/writes happen on
their own connections so there is no cross-thread sqlite conflict.
"""

from __future__ import annotations

import json
import os
from datetime import date

from PySide6.QtCore import QObject, QTimer

from models.database import Database
from utils.workers import run_async


class NutritionSyncService(QObject):
    """
    Wakes up every INTERVAL_MS milliseconds and:
      1. Reads today's meal plan slots from the DB.
      2. For each slot with a recipe_id, tries to log it to the nutrition tracker.
      3. If the recipe has no stored macros, dispatches a background worker that
         calls Claude to analyze them, saves the result, and then logs.
      4. Calls refresh_fn() whenever new log entries are added.
    """

    INTERVAL_MS = 10_000  # 10 seconds — feels live without hammering the API

    def __init__(self, refresh_fn, parent: QObject | None = None):
        super().__init__(parent)
        self._refresh_fn = refresh_fn
        # Each sync cycle opens its own DB connection so there's no conflict
        # with the views' connections.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._sync)
        self._timer.start(self.INTERVAL_MS)
        # Track which recipe_ids are currently being analyzed so we don't
        # queue duplicate background jobs.
        self._analyzing: set[int] = set()

    def sync_now(self) -> None:
        """Trigger an immediate sync (e.g. right after a meal slot is set)."""
        self._sync()

    # ── internal ─────────────────────────────────────────────────────────────

    def _open_db(self) -> Database:
        db = Database()
        db.connect()
        return db

    def _sync(self) -> None:
        try:
            db        = self._open_db()
            today_str = date.today().isoformat()
            slots     = db.get_today_meal_slots()
            if not slots:
                return

            # Build set of already-logged food names for today (lower-cased)
            existing = {r["food_name"].lower() for r in db.get_nutrition_logs(today_str)}

            added_any = False
            for slot in slots:
                recipe_id = slot.get("recipe_id")
                name      = (slot.get("custom_name") or "").strip()
                if not recipe_id or not name:
                    continue
                if name.lower() in existing:
                    continue  # already logged — nothing to do

                # Try to log directly (works if recipe already has macros)
                logged = db.auto_log_meal_nutrition(today_str, name, recipe_id)
                if logged:
                    existing.add(name.lower())
                    added_any = True
                elif recipe_id not in self._analyzing:
                    # Recipe has no macros yet — analyze in background
                    self._analyzing.add(recipe_id)
                    self._background_analyze(recipe_id, name, today_str)

            if added_any:
                self._refresh_fn()

        except Exception:
            pass

    def _background_analyze(self, recipe_id: int, meal_name: str, date_str: str) -> None:
        """Open a fresh DB connection, fetch ingredients, call Claude, save macros, log."""

        def _work():
            try:
                db = self._open_db()
                row = db.conn.execute(
                    "SELECT data_json FROM recipes WHERE id=?", (recipe_id,)
                ).fetchone()
                if not row:
                    return False
                d          = json.loads(row["data_json"] or "{}")
                per_s      = d.get("nutrition_per_serving", {})
                # Re-check — maybe another path already populated it
                if float(per_s.get("kcal", 0) or 0) > 0:
                    return db.auto_log_meal_nutrition(date_str, meal_name, recipe_id)
                ingredients = d.get("ingredients", [])
                if not ingredients:
                    return False
                servings = int(d.get("servings") or 2)
                from api.claude_ai import ClaudeAI as _AI
                _ai  = _AI()
                nutr = _ai.analyze_recipe_nutrition(ingredients, servings)
                d["nutrition_ingredients"] = nutr.get("ingredients", [])
                d["nutrition_total"]       = nutr.get("total", {})
                d["nutrition_per_serving"] = nutr.get("per_serving", {})
                db.conn.execute(
                    "UPDATE recipes SET data_json=? WHERE id=?",
                    (json.dumps(d), recipe_id),
                )
                db.conn.commit()
                return db.auto_log_meal_nutrition(date_str, meal_name, recipe_id)
            except Exception:
                return False

        def _done(result):
            self._analyzing.discard(recipe_id)
            if result:
                self._refresh_fn()

        run_async(_work, _done)
