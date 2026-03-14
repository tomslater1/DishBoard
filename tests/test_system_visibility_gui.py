from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tests.base import TempDBTestCase
from utils.system_visibility import SystemVisibilityService
from views.settings import _MonitoringPage


class SystemVisibilityGuiTests(TempDBTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_monitoring_page_uses_visibility_snapshot_for_summary_filters_and_changes(self):
        self.db.set_setting("sync_last_push_at", "2026-03-14T12:00:00+00:00")
        self.db.set_setting("sync_last_pull_at", "2026-03-14T12:00:00+00:00")
        self.db.conn.execute(
            "INSERT INTO recipes (title, source, data_json, updated_at, cloud_id) VALUES (?,?,?,?,?)",
            ("Monitoring Pasta", "manual", "{}", "2026-03-14T10:00:00+00:00", "recipe-cloud-1"),
        )
        self.db.add_telemetry_event("user-1", "sync.completed", '{"pushed":1,"pulled":2}')
        self.db.conn.commit()

        service = SystemVisibilityService(self.db)
        page = _MonitoringPage(db=self.db)
        page.set_visibility_service(service)
        service.refresh()

        self.assertIn("Severity:", page._severity_summary_lbl.text())
        self.assertIn("Why you're seeing this:", page._attention_reasons_lbl.text())
        self.assertIn("Recipes:", page._module_freshness_lbl.text())

        page._activity_filter.setCurrentText("Sync")
        page.refresh()
        self.assertIn("Cloud sync completed", page._recent_changes_lbl.text())


if __name__ == "__main__":
    unittest.main()
