from __future__ import annotations

from tests.base import TempDBTestCase


class NutritionTotalsTests(TempDBTestCase):
    def test_nutrition_totals_range_and_days(self):
        self.db.add_nutrition_log("2026-03-10", "Meal A", 500, 30, 40, 20, 5, 3)
        self.db.add_nutrition_log("2026-03-10", "Snack A", 200, 10, 20, 8, 2, 6)
        self.db.add_nutrition_log("2026-03-12", "Meal B", 700, 45, 60, 25, 7, 5)

        totals = self.db.get_nutrition_totals_for_range("2026-03-10", "2026-03-12")

        self.assertEqual(totals["entries"], 3)
        self.assertEqual(totals["days"], 2)
        self.assertEqual(totals["kcal"], 1400.0)
        self.assertEqual(totals["protein_g"], 85.0)
        self.assertEqual(totals["carbs_g"], 120.0)
        self.assertEqual(totals["fat_g"], 53.0)
        self.assertEqual(totals["fiber_g"], 14.0)
        self.assertEqual(totals["sugar_g"], 14.0)


if __name__ == "__main__":
    import unittest

    unittest.main()
