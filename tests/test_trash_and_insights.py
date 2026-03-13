from __future__ import annotations

from tests.base import TempDBTestCase


class TestTrashAndInsights(TempDBTestCase):
    def test_recipe_delete_moves_to_trash_and_restores(self):
        rid = self.db.save_recipe("x", "manual", "Trash Soup", data_json='{"ingredients": ["1 onion"], "instructions": ["Cook"]}')
        self.db.delete_recipe(rid)

        items = self.db.list_trash_items(limit=10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["entity_type"], "recipes")

        restored = self.db.restore_trash_item(items[0]["id"])
        self.assertTrue(restored)

        row = self.db.conn.execute("SELECT COUNT(*) AS c FROM recipes WHERE title='Trash Soup'").fetchone()
        self.assertEqual(int(row["c"]), 1)

    def test_pantry_delete_logs_waste(self):
        pid = self.db.add_pantry_item("Spinach", quantity=2, unit="bag", storage="Fridge")
        self.db.delete_pantry_item(pid)

        summary = self.db.get_pantry_waste_summary(days=30)
        self.assertEqual(int(summary["entries"]), 1)
        self.assertGreater(float(summary["estimated_value"]), 0.0)

    def test_sync_integrity_report_present(self):
        report = self.db.get_sync_integrity_report()
        self.assertIn("pending_tombstones", report)
        self.assertIn("unsynced_rows", report)
        self.assertIn("orphan_meal_slots", report)
