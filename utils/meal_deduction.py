"""
MealDeductionService — automatically deducts ingredients from My Kitchen
when a meal's scheduled time passes.

Meal cutoff times:
  Breakfast → after 10:00
  Lunch     → after 14:00
  Dinner    → after 20:00
"""
from __future__ import annotations

import json
from datetime import datetime, date

from PySide6.QtCore import QObject, QTimer, Signal


# Cutoff hour (24h) after which a meal is considered "cooked"
_CUTOFF_HOURS: dict[str, int] = {
    "breakfast": 10,
    "lunch":     14,
    "dinner":    20,
}


class MealDeductionService(QObject):
    """QTimer-driven service that deducts pantry ingredients when meal times pass."""

    ingredients_deducted = Signal()

    def __init__(self, db, parent: QObject | None = None):
        super().__init__(parent)
        self._db = db
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._timer.start(60_000)  # every 60 seconds

    def start(self) -> None:
        """Ensure the timer is running."""
        if not self._timer.isActive():
            self._timer.start(60_000)

    def stop(self) -> None:
        self._timer.stop()

    def _check(self) -> None:
        try:
            now = datetime.now()
            today = date.today().isoformat()
            slots = self._db.get_today_meal_plan_with_nutrition()

            for slot in slots:
                meal_type = slot.get("meal_type", "").lower()
                cutoff = _CUTOFF_HOURS.get(meal_type)
                if cutoff is None:
                    continue

                # Only deduct if current hour has passed the cutoff
                if now.hour < cutoff:
                    continue

                # Check if already deducted today
                key = f"deducted_{today}_{meal_type}"
                already = self._db.get_setting(key, "")
                if already == "1":
                    continue

                # Parse ingredients from the recipe's data_json
                data_json_str = slot.get("data_json") or "{}"
                try:
                    data = json.loads(data_json_str)
                    ingredients = data.get("ingredients", [])
                except Exception:
                    ingredients = []

                if ingredients:
                    self._db.deduct_pantry_ingredients(ingredients)

                # Mark as deducted regardless (avoid retrying meals with no ingredients)
                self._db.set_setting(key, "1")
                self.ingredients_deducted.emit()

        except Exception:
            pass  # Never crash the main thread
