from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from tests.base import TempDBTestCase
from utils.system_visibility import SystemVisibilityService


class _FakeSyncService(QObject):
    sync_started = Signal()
    sync_finished = Signal(int, int)
    sync_error = Signal(str)
    runtime_status_changed = Signal(dict)

    def __init__(self):
        super().__init__()
        self._status: dict = {}

    def runtime_status(self) -> dict:
        return dict(self._status)

    def set_status(self, **status) -> None:
        self._status = dict(status)
        self.runtime_status_changed.emit(self.runtime_status())


class SystemVisibilityTests(TempDBTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_recent_changes_include_core_modules_in_descending_order(self):
        self.db.conn.execute(
            "INSERT INTO recipes (title, source, data_json, updated_at, cloud_id) VALUES (?,?,?,?,?)",
            ("Lemon Pasta", "manual", "{}", "2026-03-14T09:00:00+00:00", "recipe-cloud-1"),
        )
        self.db.conn.execute(
            "INSERT INTO meal_plans (day_of_week, meal_type, custom_name, week_start, updated_at, cloud_id) VALUES (?,?,?,?,?,?)",
            ("Friday", "dinner", "Lemon Pasta", "2026-03-09", "2026-03-14T10:00:00+00:00", "plan-cloud-1"),
        )
        self.db.conn.execute(
            "INSERT INTO shopping_items (name, checked, updated_at, cloud_id) VALUES (?,?,?,?)",
            ("Parsley", 0, "2026-03-14T11:00:00+00:00", "shop-cloud-1"),
        )
        self.db.conn.execute(
            "INSERT INTO pantry_items (name, storage, updated_at, cloud_id) VALUES (?,?,?,?)",
            ("Olive oil", "Pantry", "2026-03-14T12:00:00+00:00", "pantry-cloud-1"),
        )
        self.db.conn.execute(
            "INSERT INTO nutrition_logs (log_date, food_name, kcal, updated_at, cloud_id) VALUES (?,?,?,?,?)",
            ("2026-03-14", "Protein oats", 420, "2026-03-14T13:00:00+00:00", "nutrition-cloud-1"),
        )
        self.db.conn.execute(
            "INSERT INTO dishy_chat_history (session_id, role, content, updated_at) VALUES (?,?,?,?)",
            ("session-1", "assistant", "Try a lemon pasta with parsley.", "2026-03-14T14:00:00+00:00"),
        )
        self.db.conn.execute(
            "INSERT INTO in_app_notifications (user_id, notif_type, title, message, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (
                "user-1",
                "pantry_expiry",
                "Pantry item expiring soon",
                "Olive oil is expiring soon.",
                "2026-03-14T15:00:00+00:00",
                "2026-03-14T15:00:00+00:00",
            ),
        )
        self.db.conn.execute(
            "INSERT INTO trash_bin (user_id, entity_type, payload_json, reason, deleted_at) VALUES (?,?,?,?,?)",
            ("user-1", "recipe", "{}", "deleted", "2026-03-14T16:00:00+00:00"),
        )
        self.db.add_telemetry_event(
            "user-1",
            "sync.completed",
            json.dumps({"pushed": 1, "pulled": 2}),
        )
        self.db.conn.execute(
            "UPDATE telemetry_events SET created_at=? WHERE event_name='sync.completed'",
            ("2026-03-14T17:00:00+00:00",),
        )
        self.db.conn.commit()

        changes = self.db.get_visibility_recent_changes(limit=20)

        modules = {item["module"] for item in changes}
        self.assertTrue({"recipes", "planner", "shopping", "pantry", "nutrition", "dishy", "system"}.issubset(modules))
        self.assertEqual(changes[0]["title"], "Cloud sync completed")
        ordered_times = [item["occurred_at"] for item in changes]
        self.assertEqual(ordered_times, sorted(ordered_times, reverse=True))

    def test_service_classifies_modules_and_exposes_actions(self):
        self.db.set_setting("sync_last_push_at", "2026-03-14T12:00:00+00:00")
        self.db.set_setting("sync_last_pull_at", "2026-03-14T12:00:00+00:00")
        self.db.conn.execute(
            "INSERT INTO recipes (title, source, data_json, updated_at, cloud_id) VALUES (?,?,?,?,?)",
            ("Fresh recipe", "manual", "{}", "2026-03-14T10:00:00+00:00", "recipe-cloud-1"),
        )
        self.db.conn.execute(
            "INSERT INTO shopping_items (name, checked, updated_at, cloud_id) VALUES (?,?,?,?)",
            ("Unsynced milk", 0, "2026-03-14T12:30:00+00:00", None),
        )
        self.db.conn.commit()

        service = SystemVisibilityService(self.db)
        snapshot = service.snapshot()
        by_module = {item.module: item for item in snapshot.module_freshness}

        self.assertEqual(by_module["recipes"].state, "fresh")
        self.assertEqual(by_module["shopping"].state, "stale")
        self.assertEqual(by_module["nutrition"].state, "idle")
        self.assertEqual(snapshot.overall_state, "stale")
        self.assertEqual(snapshot.severity, "critical")
        self.assertIn("module_stale", snapshot.attention_reasons)
        self.assertTrue(any(action.action_id == "review_shopping" for action in snapshot.recommended_actions))

        with service.start_work(
            "dishy.test",
            "ai",
            "dishy",
            "Dishy is replying",
            "Testing active AI work.",
            attention_reason="ai_in_progress",
        ):
            ai_snapshot = service.snapshot()
            ai_modules = {item.module: item for item in ai_snapshot.module_freshness}
            self.assertEqual(ai_modules["dishy"].state, "working")
            self.assertEqual(ai_snapshot.overall_state, "ai_busy")
            self.assertIn("ai_in_progress", ai_snapshot.attention_reasons)
            self.assertTrue(any(action.action_id == "open_dishy" for action in ai_snapshot.recommended_actions))

    def test_sync_runtime_updates_snapshot_state_and_escalates(self):
        self.db.set_setting("sync_last_push_at", "2026-03-14T12:00:00+00:00")
        self.db.set_setting("sync_last_pull_at", "2026-03-14T12:00:00+00:00")
        service = SystemVisibilityService(self.db)
        fake_sync = _FakeSyncService()
        service.bind_sync_service(fake_sync)

        fake_sync.set_status(last_success_at="2026-03-14T12:00:00+00:00", is_syncing=True)
        self.assertEqual(service.snapshot().overall_state, "syncing")
        self.assertEqual(service.snapshot().severity, "info")

        failure_at = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat(timespec="seconds")
        fake_sync.set_status(
            last_error="offline",
            last_failure_at=failure_at,
            retry_in_seconds=30,
            consecutive_failures=3,
            is_syncing=False,
        )
        offline_snapshot = service.snapshot()
        self.assertEqual(offline_snapshot.overall_state, "offline")
        self.assertEqual(offline_snapshot.severity, "critical")
        self.assertIn("sync_offline", offline_snapshot.attention_reasons)
        self.assertIn("sync_critical", offline_snapshot.attention_reasons)
        self.assertTrue(any(action.action_id == "retry_sync" for action in offline_snapshot.recommended_actions))

        fake_sync.set_status(circuit_open=True, retry_in_seconds=45, is_syncing=False, last_error="")
        recovering_snapshot = service.snapshot()
        self.assertEqual(recovering_snapshot.overall_state, "recovering")
        self.assertIn("sync_backoff", recovering_snapshot.attention_reasons)

    def test_repeated_ai_failures_promote_attention_and_monitoring_actions(self):
        service = SystemVisibilityService(self.db)

        service.start_work("ai.test.1", "ai", "dishy", "Dishy is replying", "First run").fail("rate limited")
        service.start_work("ai.test.2", "ai", "dishy", "Dishy is replying", "Second run").fail("timeout")

        snapshot = service.snapshot()
        self.assertEqual(snapshot.overall_state, "attention")
        self.assertEqual(snapshot.severity, "critical")
        self.assertIn("ai_failed", snapshot.attention_reasons)
        self.assertIn("ai_repeated_failure", snapshot.attention_reasons)
        self.assertTrue(any(action.action_id == "open_dishy" for action in snapshot.recommended_actions))
        self.assertTrue(any(action.action_id == "open_monitoring" for action in snapshot.recommended_actions))

    def test_feed_summary_collapses_repeated_sync_completions(self):
        self.db.add_telemetry_event("user-1", "sync.completed", json.dumps({"pushed": 1, "pulled": 2}))
        self.db.add_telemetry_event("user-1", "sync.completed", json.dumps({"pushed": 0, "pulled": 1}))
        self.db.conn.execute(
            "UPDATE telemetry_events SET created_at=? WHERE id=(SELECT MIN(id) FROM telemetry_events)",
            ("2026-03-14T10:00:00+00:00",),
        )
        self.db.conn.execute(
            "UPDATE telemetry_events SET created_at=? WHERE id=(SELECT MAX(id) FROM telemetry_events)",
            ("2026-03-14T11:00:00+00:00",),
        )
        self.db.conn.commit()

        snapshot = SystemVisibilityService(self.db).snapshot()
        digest = next(item for item in snapshot.feed_summary if item.title == "Cloud sync completed")
        self.assertEqual(digest.count, 2)
        self.assertEqual(digest.activity_type, "sync")

    def test_expired_work_is_removed_and_surfaces_timeout_digest(self):
        service = SystemVisibilityService(self.db)
        handle = service.start_work("job.timeout", "job", "system", "Long-running job", "Doing too much work.")
        del handle
        service._active_work["job.timeout"].timeout_at = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        ).isoformat(timespec="seconds")

        service.refresh()

        self.assertFalse(service.snapshot().active_work)
        self.assertTrue(any("timed out" in item.title.lower() for item in service.snapshot().feed_summary))

if __name__ == "__main__":
    unittest.main()
