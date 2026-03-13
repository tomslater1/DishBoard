from __future__ import annotations

from tests.base import TempDBTestCase
from utils.ai_limits import can_make_request, record_attempt, remaining_requests, utc_day_str


class AILimitTests(TempDBTestCase):
    def test_default_limit_is_enforced(self):
        user_id = "user-1"
        day = utc_day_str()

        for _ in range(50):
            allowed, _remaining, _limit = can_make_request(self.db, user_id, day)
            self.assertTrue(allowed)
            record_attempt(self.db, user_id, day=day)

        allowed, remaining, limit = can_make_request(self.db, user_id, day)
        self.assertFalse(allowed)
        self.assertEqual(limit, 50)
        self.assertEqual(remaining, 0)

    def test_custom_limit_setting(self):
        self.db.set_setting("dishy_daily_limit", "3")
        user_id = "user-2"
        day = utc_day_str()

        for _ in range(2):
            record_attempt(self.db, user_id, day=day)

        self.assertEqual(remaining_requests(self.db, user_id, day), 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
