from __future__ import annotations

import uuid

from tests.base import TempDBTestCase
from utils.startup_health import get_last_health_report, run_startup_health_check


class StartupHealthTests(TempDBTestCase):
    def test_health_check_removes_invalid_tombstones_and_recovers_jobs(self):
        valid_uuid = str(uuid.uuid4())
        self.db.add_tombstone("recipes", "53")
        self.db.add_tombstone("recipes", valid_uuid)

        self.db.upsert_workflow_job(
            "job.test.health",
            "notifications.scan",
            run_every_minutes=15,
            next_run_at="2026-03-13T00:00:00+00:00",
        )
        self.db.conn.execute(
            "UPDATE workflow_jobs SET status='running', updated_at=? WHERE job_key=?",
            ("2026-03-12T00:00:00+00:00", "job.test.health"),
        )
        self.db.conn.commit()

        report = run_startup_health_check(self.db)
        self.assertEqual(int(report.get("invalid_tombstones_removed", 0)), 1)
        self.assertEqual(int(report.get("recovered_workflow_jobs", 0)), 1)

        pending = self.db.get_pending_tombstones()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["cloud_id"], valid_uuid)

        saved_report = get_last_health_report(self.db)
        self.assertEqual(saved_report.get("invalid_tombstones_removed"), 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
