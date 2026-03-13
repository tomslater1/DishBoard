from __future__ import annotations

from tests.base import TempDBTestCase


class AccountSwitchWipeTests(TempDBTestCase):
    def _count(self, table: str) -> int:
        row = self.db.conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
        return int(row["c"])

    def test_clear_user_data_preserves_device_settings_only(self):
        self.db.set_setting("theme", "dark")
        self.db.set_setting("supabase_url", "https://example.supabase.co")
        self.db.set_setting("supabase_anon_key", "anon")
        self.db.set_setting("active_user_id", "user-a")
        self.db.set_setting("onboarding_complete", "1")
        self.db.set_setting("dietary_prefs", "vegetarian")

        recipe_id = self.db.save_recipe(
            source_id="r1",
            source="manual",
            title="Test Recipe",
            data_json="{}",
        )
        self.db.set_meal_slot("2026-03-09", "Monday", "dinner", "Test Recipe", recipe_id)
        self.db.add_shopping_item("eggs", "12", "pcs")
        self.db.add_nutrition_log("2026-03-12", "Omelette", 250, 20, 3, 17, 0, 1)
        self.db.save_dishy_message("s1", "user", "hello")
        self.db.add_pantry_item("milk", 1, "L", "Fridge")

        self.assertEqual(self._count("recipes"), 1)
        self.assertEqual(self._count("meal_plans"), 1)
        self.assertEqual(self._count("shopping_items"), 1)

        self.db.clear_user_data()

        self.assertEqual(self._count("recipes"), 0)
        self.assertEqual(self._count("meal_plans"), 0)
        self.assertEqual(self._count("shopping_items"), 0)
        self.assertEqual(self._count("nutrition_logs"), 0)
        self.assertEqual(self._count("dishy_chat_history"), 0)
        self.assertEqual(self._count("pantry_items"), 0)
        self.assertEqual(self._count("sync_tombstones"), 0)

        self.assertEqual(self.db.get_setting("theme"), "dark")
        self.assertEqual(self.db.get_setting("supabase_url"), "https://example.supabase.co")
        self.assertEqual(self.db.get_setting("supabase_anon_key"), "anon")
        self.assertEqual(self.db.get_setting("active_user_id"), "user-a")

        self.assertEqual(self.db.get_setting("onboarding_complete"), "")
        self.assertEqual(self.db.get_setting("dietary_prefs"), "")

    def test_ensure_active_user_scope_wipes_when_user_changes(self):
        self.db.set_setting("active_user_id", "user-a")
        self.db.add_shopping_item("milk")
        self.assertEqual(self._count("shopping_items"), 1)

        wiped = self.db.ensure_active_user_scope("user-b")
        self.assertTrue(wiped)
        self.assertEqual(self._count("shopping_items"), 0)
        self.assertEqual(self.db.get_setting("active_user_id"), "user-b")

    def test_ensure_active_user_scope_wipes_legacy_cache_without_owner(self):
        self.db.add_shopping_item("eggs")
        self.assertEqual(self.db.get_setting("active_user_id"), "")
        self.assertEqual(self._count("shopping_items"), 1)

        wiped = self.db.ensure_active_user_scope("user-a")
        self.assertTrue(wiped)
        self.assertEqual(self._count("shopping_items"), 0)
        self.assertEqual(self.db.get_setting("active_user_id"), "user-a")


if __name__ == "__main__":
    import unittest

    unittest.main()
