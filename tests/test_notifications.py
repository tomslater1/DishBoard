from __future__ import annotations

from datetime import date, datetime

from tests.base import TempDBTestCase
from utils.notifications import (
    generate_scheduled_notifications,
    list_notifications,
    mark_all_read,
    unread_count,
)


class NotificationTests(TempDBTestCase):
    def setUp(self):
        super().setUp()
        self.db.set_setting("active_user_id", "user-abc")

    def test_expiry_and_meal_reminders_are_deduped(self):
        # Expiry in 3 days should produce one warning notification.
        exp = (date.today()).replace(day=date.today().day)
        expiry = date.fromordinal(date.today().toordinal() + 3).isoformat()
        self.db.add_pantry_item("Chicken breast", quantity=2, unit="pack", storage="Fridge", expiry_date=expiry)

        recipe_id = self.db.save_recipe("r1", "manual", "Chicken Bowl", data_json='{"ingredients": ["chicken"]}')
        today = date.today()
        week_start = date.fromordinal(today.toordinal() - today.weekday()).isoformat()
        day_name = today.strftime("%A")
        self.db.set_meal_slot(week_start, day_name, "dinner", custom_name="Chicken Bowl", recipe_id=recipe_id)

        created_1 = generate_scheduled_notifications(
            self.db,
            "user-abc",
            now_local=datetime.combine(today, datetime.min.time()).replace(hour=18),
        )
        created_2 = generate_scheduled_notifications(
            self.db,
            "user-abc",
            now_local=datetime.combine(today, datetime.min.time()).replace(hour=19),
        )

        self.assertGreaterEqual(created_1, 2)
        self.assertEqual(created_2, 0)

        notes = list_notifications(self.db, "user-abc", limit=20)
        self.assertGreaterEqual(len(notes), 2)
        self.assertGreater(unread_count(self.db, "user-abc"), 0)

        changed = mark_all_read(self.db, "user-abc")
        self.assertGreater(changed, 0)
        self.assertEqual(unread_count(self.db, "user-abc"), 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
