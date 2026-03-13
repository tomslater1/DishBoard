from __future__ import annotations

import os

from tests.base import TempDBTestCase
from utils.telemetry import get_analytics_status


class MonitoringIntegrityAndAnalyticsTests(TempDBTestCase):
    def test_integrity_scan_detects_blank_rows(self):
        self.db.conn.execute(
            "INSERT INTO recipes (source_id, source, title, data_json) VALUES (?,?,?,?)",
            ("s1", "manual", "   ", "{}"),
        )
        self.db.conn.execute(
            "INSERT INTO shopping_items (name, quantity, unit, checked, source) VALUES (?,?,?,?,?)",
            ("   ", "", "", 0, "manual"),
        )
        self.db.conn.execute(
            "INSERT INTO pantry_items (name, quantity, unit, storage) VALUES (?,?,?,?)",
            ("   ", 1, "pcs", "Pantry"),
        )
        self.db.conn.execute(
            "INSERT INTO nutrition_logs (log_date, food_name, kcal) VALUES (?,?,?)",
            ("", "  ", 0),
        )
        self.db.conn.execute(
            "INSERT INTO dishy_chat_history (session_id, role, content) VALUES (?,?,?)",
            ("  ", "  ", "  "),
        )
        self.db.conn.commit()

        report = self.db.run_integrity_scan()
        self.assertFalse(report["healthy"])
        issues = report["table_issues"]
        self.assertEqual(int(issues["recipes_empty_title"]), 1)
        self.assertEqual(int(issues["shopping_empty_name"]), 1)
        self.assertEqual(int(issues["pantry_empty_name"]), 1)
        self.assertEqual(int(issues["nutrition_missing_core"]), 1)
        self.assertEqual(int(issues["dishy_chat_missing_core"]), 1)
        self.assertGreaterEqual(int(report["issue_count"]), 5)

    def test_analytics_status_includes_host_key_and_last_event(self):
        prev_key = os.environ.get("POSTHOG_API_KEY")
        prev_host = os.environ.get("POSTHOG_HOST")
        os.environ["POSTHOG_API_KEY"] = "phc_test_key"
        os.environ["POSTHOG_HOST"] = "https://eu.i.posthog.com"

        try:
            self.db.add_telemetry_event("user-1", "app.user_session_started", "{}")
            status = get_analytics_status(self.db, "user-1")
            self.assertTrue(status["has_api_key"])
            self.assertEqual(status["host"], "https://eu.i.posthog.com")
            self.assertTrue(bool(status["last_event_at"]))
            self.assertTrue(status["enabled"])
        finally:
            if prev_key is None:
                os.environ.pop("POSTHOG_API_KEY", None)
            else:
                os.environ["POSTHOG_API_KEY"] = prev_key
            if prev_host is None:
                os.environ.pop("POSTHOG_HOST", None)
            else:
                os.environ["POSTHOG_HOST"] = prev_host


if __name__ == "__main__":
    import unittest

    unittest.main()
