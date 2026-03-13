from __future__ import annotations

import unittest

from utils.data_validators import sanitize_cloud_row, sanitize_import_row


class DataValidatorTests(unittest.TestCase):
    def test_cloud_shopping_row_is_normalized(self):
        row, reason = sanitize_cloud_row(
            "shopping_items",
            {"id": "x1", "user_id": "u1", "name": "  Almond   Milk  ", "checked": "1"},
            user_id="u1",
        )
        self.assertEqual(reason, "ok")
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "Almond Milk")
        self.assertEqual(row["checked"], 1)

    def test_cloud_scope_guard_blocks_wrong_household(self):
        row, reason = sanitize_cloud_row(
            "shopping_items",
            {
                "id": "x2",
                "user_id": "u2",
                "household_id": "house-b",
                "name": "Eggs",
                "checked": 0,
            },
            user_id="u1",
            household_id="house-a",
            household_scope_enabled=True,
            household_shared_tables={"shopping_items"},
        )
        self.assertIsNone(row)
        self.assertEqual(reason, "scope_mismatch_household")

    def test_meal_plan_rejects_invalid_day(self):
        row, reason = sanitize_cloud_row(
            "meal_plans",
            {
                "id": "mp1",
                "user_id": "u1",
                "week_start": "2026-03-09",
                "day_of_week": "Funday",
                "meal_type": "dinner",
            },
            user_id="u1",
        )
        self.assertIsNone(row)
        self.assertEqual(reason, "meal_plan_bad_day")

    def test_import_rows_drop_invalid_entries(self):
        self.assertIsNone(sanitize_import_row("shopping_items", {"name": "   "}))
        self.assertIsNone(
            sanitize_import_row(
                "meal_plans",
                {
                    "week_start": "not-a-date",
                    "day_of_week": "Monday",
                    "meal_type": "dinner",
                },
            )
        )


if __name__ == "__main__":
    unittest.main()
