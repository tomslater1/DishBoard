from __future__ import annotations

from tests.base import TempDBTestCase
from auth.cloud_sync import CloudSyncService, SyncResult


class _FakeTableQuery:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._eq_filters: dict[str, str] = {}

    def select(self, _cols: str):
        return self

    def eq(self, key: str, value: str):
        self._eq_filters[key] = value
        return self

    def gt(self, _key: str, _value: str):
        return self

    def execute(self):
        class _Res:
            def __init__(self, data):
                self.data = data
        if "user_id" in self._eq_filters:
            wanted = self._eq_filters["user_id"]
            filtered = [r for r in self._rows if str(r.get("user_id", "")) == wanted]
            return _Res(filtered)
        return _Res(self._rows)


class _FakeClient:
    def __init__(self, table_rows: dict[str, list[dict]]):
        self._table_rows = table_rows

    def table(self, name: str):
        return _FakeTableQuery(self._table_rows.get(name, []))


class SyncMergeAndTombstoneTests(TempDBTestCase):
    def test_upsert_row_from_cloud_respects_newer_local_timestamp(self):
        local_id = self.db.save_recipe(
            source_id="r1",
            source="manual",
            title="Local Newer",
            data_json="{}",
        )
        self.db.set_cloud_id("recipes", local_id, "cloud-1")
        self.db.conn.execute(
            "UPDATE recipes SET updated_at=? WHERE id=?",
            ("2026-03-12 12:00:00", local_id),
        )
        self.db.conn.commit()

        older_cloud = {
            "id": "cloud-1",
            "title": "Cloud Older",
            "updated_at": "2026-03-12T11:00:00+00:00",
        }
        self.db.upsert_row_from_cloud("recipes", older_cloud, {})

        row = self.db.conn.execute("SELECT title FROM recipes WHERE id=?", (local_id,)).fetchone()
        self.assertEqual(row["title"], "Local Newer")

        newer_cloud = {
            "id": "cloud-1",
            "title": "Cloud Newer",
            "updated_at": "2026-03-12T13:30:00+00:00",
        }
        self.db.upsert_row_from_cloud("recipes", newer_cloud, {})

        row2 = self.db.conn.execute("SELECT title FROM recipes WHERE id=?", (local_id,)).fetchone()
        self.assertEqual(row2["title"], "Cloud Newer")

    def test_tombstone_roundtrip(self):
        self.db.add_tombstone("recipes", "cloud-abc")
        pending = self.db.get_pending_tombstones()

        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["table_name"], "recipes")
        self.assertEqual(pending[0]["cloud_id"], "cloud-abc")

        self.db.clear_tombstone(pending[0]["id"])
        self.assertEqual(self.db.get_pending_tombstones(), [])

    def test_meal_plan_slot_reconciliation_avoids_unique_conflict(self):
        recipe_id = self.db.save_recipe("r1", "manual", "Local Meal", data_json="{}")
        self.db.set_meal_slot("2026-03-09", "Monday", "dinner", "Local Meal", recipe_id)
        self.db.conn.execute(
            "UPDATE meal_plans SET updated_at=? WHERE week_start=? AND day_of_week=? AND meal_type=?",
            ("2026-03-12T12:00:00+00:00", "2026-03-09", "Monday", "dinner"),
        )
        self.db.conn.commit()

        # Older cloud duplicate for same slot should not insert a second row.
        self.db.upsert_row_from_cloud(
            "meal_plans",
            {
                "id": "cloud-old",
                "week_start": "2026-03-09",
                "day_of_week": "Monday",
                "meal_type": "dinner",
                "custom_name": "Cloud Older",
                "updated_at": "2026-03-12T11:00:00+00:00",
            },
            {},
        )

        # Newer cloud duplicate for same slot should update existing row, not violate unique key.
        self.db.upsert_row_from_cloud(
            "meal_plans",
            {
                "id": "cloud-new",
                "week_start": "2026-03-09",
                "day_of_week": "Monday",
                "meal_type": "dinner",
                "custom_name": "Cloud Newer",
                "updated_at": "2026-03-12T13:00:00+00:00",
            },
            {},
        )

        count = self.db.conn.execute(
            "SELECT COUNT(*) AS c FROM meal_plans WHERE week_start=? AND day_of_week=? AND meal_type=?",
            ("2026-03-09", "Monday", "dinner"),
        ).fetchone()
        row = self.db.conn.execute(
            "SELECT custom_name, cloud_id FROM meal_plans WHERE week_start=? AND day_of_week=? AND meal_type=?",
            ("2026-03-09", "Monday", "dinner"),
        ).fetchone()

        self.assertEqual(int(count["c"]), 1)
        self.assertEqual(row["custom_name"], "Cloud Newer")
        self.assertEqual(row["cloud_id"], "cloud-new")

    def test_reconcile_meal_plan_recipe_links_from_recipe_cloud_id(self):
        recipe_id = self.db.save_recipe("r1", "manual", "Linked Recipe", data_json="{}")
        self.db.set_cloud_id("recipes", recipe_id, "recipe-cloud-1")

        self.db.conn.execute(
            "INSERT INTO meal_plans (day_of_week, meal_type, recipe_id, custom_name, week_start, recipe_cloud_id, updated_at)"
            " VALUES (?, ?, NULL, ?, ?, ?, ?)",
            ("Monday", "dinner", "Linked Recipe", "2026-03-09", "recipe-cloud-1", "2026-03-12T12:00:00+00:00"),
        )
        self.db.conn.commit()

        linked = self.db.reconcile_meal_plan_recipe_links()
        self.assertEqual(linked, 1)

        row = self.db.conn.execute(
            "SELECT recipe_id FROM meal_plans WHERE week_start=? AND day_of_week=? AND meal_type=?",
            ("2026-03-09", "Monday", "dinner"),
        ).fetchone()
        self.assertEqual(row["recipe_id"], recipe_id)

    def test_cleanup_unlinked_cloud_meal_plans_adds_tombstones(self):
        self.db.conn.execute(
            "INSERT INTO meal_plans (day_of_week, meal_type, recipe_id, custom_name, week_start, cloud_id, recipe_cloud_id, updated_at)"
            " VALUES (?, ?, NULL, ?, ?, ?, NULL, ?)",
            ("Tuesday", "lunch", "Ghost Meal", "2026-03-09", "meal-cloud-ghost", "2026-03-12T12:00:00+00:00"),
        )
        self.db.conn.commit()

        removed = self.db.cleanup_unlinked_cloud_meal_plans()
        self.assertEqual(removed, 1)

        cnt = self.db.conn.execute("SELECT COUNT(*) AS c FROM meal_plans").fetchone()
        self.assertEqual(int(cnt["c"]), 0)

        tombs = self.db.get_pending_tombstones()
        self.assertEqual(len(tombs), 1)
        self.assertEqual(tombs[0]["table_name"], "meal_plans")
        self.assertEqual(tombs[0]["cloud_id"], "meal-cloud-ghost")

    def test_pull_table_skips_invalid_shopping_rows(self):
        svc = CloudSyncService("user-1")
        result = SyncResult()
        fake = _FakeClient({
            "shopping_items": [
                {
                    "id": "shop-1",
                    "user_id": "user-1",
                    "name": "  Milk  ",
                    "quantity": "1",
                    "unit": "L",
                    "checked": 0,
                    "source": "manual",
                    "updated_at": "2026-03-13T01:00:00+00:00",
                },
                {
                    "id": "shop-2",
                    "user_id": "user-1",
                    "name": "   ",
                    "quantity": "",
                    "unit": "",
                    "checked": 0,
                    "source": "manual",
                    "updated_at": "2026-03-13T01:00:00+00:00",
                },
                {
                    "id": "shop-3",
                    "user_id": "user-2",
                    "name": "Other user row",
                    "quantity": "",
                    "unit": "",
                    "checked": 0,
                    "source": "manual",
                    "updated_at": "2026-03-13T01:00:00+00:00",
                },
            ]
        })

        svc._pull_table(
            self.db,
            fake,
            "shopping_items",
            {},
            "1970-01-01T00:00:00+00:00",
            result,
        )

        rows = self.db.get_shopping_items()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Milk")
        self.assertEqual(result.pulled, 1)

    def test_add_shopping_item_rejects_blank_names(self):
        a = self.db.add_shopping_item("")
        b = self.db.add_shopping_item("   ")
        c = self.db.add_shopping_item("  eggs   large ")
        rows = self.db.get_shopping_items()

        self.assertEqual(a, 0)
        self.assertEqual(b, 0)
        self.assertGreater(c, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "eggs large")


if __name__ == "__main__":
    import unittest

    unittest.main()
