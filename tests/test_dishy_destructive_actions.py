from __future__ import annotations

from datetime import date, timedelta

from api.dishy_tools import DishyActions
from tests.base import TempDBTestCase


def _monday_of(d: date) -> str:
    return (d - timedelta(days=d.weekday())).isoformat()


class DishyDestructiveActionTests(TempDBTestCase):
    def test_clear_meal_plan_current_week_only(self):
        recipe_id = self.db.save_recipe("r1", "manual", "Pasta", data_json="{}")

        current_week = _monday_of(date.today())
        other_week = (date.fromisoformat(current_week) - timedelta(days=7)).isoformat()

        self.db.set_meal_slot(current_week, "Monday", "dinner", "Pasta", recipe_id)
        self.db.set_meal_slot(other_week, "Monday", "dinner", "Pasta", recipe_id)

        actions = DishyActions(self.db)
        result = actions.execute("clear_meal_plan", {"all_weeks": False})

        self.assertIn("Cleared the entire meal plan for this week", result)
        cur_rows = self.db.conn.execute("SELECT COUNT(*) AS c FROM meal_plans WHERE week_start=?", (current_week,)).fetchone()
        old_rows = self.db.conn.execute("SELECT COUNT(*) AS c FROM meal_plans WHERE week_start=?", (other_week,)).fetchone()
        self.assertEqual(int(cur_rows["c"]), 0)
        self.assertEqual(int(old_rows["c"]), 1)

    def test_clear_shopping_and_recipe_library(self):
        self.db.add_shopping_item("milk", "1", "L")
        self.db.save_recipe("r1", "manual", "Soup", data_json="{}")

        actions = DishyActions(self.db)

        r1 = actions.execute("clear_shopping_list", {})
        r2 = actions.execute("clear_recipe_library", {})

        self.assertIn("Cleared all items from the shopping list", r1)
        self.assertIn("Deleted all recipes from the library", r2)

        s_count = self.db.conn.execute("SELECT COUNT(*) AS c FROM shopping_items").fetchone()
        r_count = self.db.conn.execute("SELECT COUNT(*) AS c FROM recipes").fetchone()

        self.assertEqual(int(s_count["c"]), 0)
        self.assertEqual(int(r_count["c"]), 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
