from __future__ import annotations

import json

from tests.base import TempDBTestCase
from utils.meal_optimizer import optimize_week
from utils.planner_intelligence import load_slot_metadata


class MealOptimizerTests(TempDBTestCase):
    def test_meal_prep_mode_routes_leftovers_to_lunch(self):
        def _save(title: str, tags: list[str], protein: int, ingredients: list[str]):
            return self.db.save_recipe(
                source_id=title.lower().replace(" ", "-"),
                source="manual",
                title=title,
                data_json=json.dumps(
                    {
                        "title": title,
                        "tags": tags,
                        "ingredients": ingredients,
                        "nutrition_per_serving": {
                            "kcal": 500,
                            "protein_g": protein,
                            "carbs_g": 30,
                            "fat_g": 15,
                        },
                    }
                ),
            )

        _save("Overnight Oats", ["Breakfast"], 18, ["oats", "milk"])
        _save("Turkey Wrap", ["Lunch"], 28, ["turkey", "wrap"])
        dinner_id = _save("Batch Chili", ["Dinner", "Meal-Prep"], 42, ["beef", "beans", "tomato"])

        result = optimize_week(self.db, "2026-03-09", planning_mode="meal_prep", refill_all=False)
        self.assertGreater(result["prep_slots"], 0)

        rows = [dict(r) for r in self.db.conn.execute("SELECT * FROM meal_plans WHERE week_start='2026-03-09'").fetchall()]
        monday_dinner = next(r for r in rows if r["day_of_week"] == "Monday" and r["meal_type"] == "dinner")
        tuesday_lunch = next(r for r in rows if r["day_of_week"] == "Tuesday" and r["meal_type"] == "lunch")

        monday_meta = load_slot_metadata(monday_dinner["notes"])
        tuesday_meta = load_slot_metadata(tuesday_lunch["notes"])
        self.assertEqual(monday_dinner["recipe_id"], dinner_id)
        self.assertTrue(monday_meta.get("prep_batch"))
        self.assertEqual(tuesday_lunch["recipe_id"], dinner_id)
        self.assertEqual(tuesday_meta.get("leftover_source_day"), "Monday")

