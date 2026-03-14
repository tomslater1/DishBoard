from __future__ import annotations

import threading

from tests.base import TempDBTestCase


class DatabaseConnectionTests(TempDBTestCase):
    def test_connection_uses_wal_busy_timeout_and_autocommit(self):
        self.assertIsNone(self.db.conn.isolation_level)
        self.assertEqual(self.db.conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(self.db.conn.execute("PRAGMA busy_timeout").fetchone()[0], 30000)

    def test_shared_database_instance_opens_a_connection_for_each_thread(self):
        self.db.set_setting("threading_probe", "main-thread")
        main_conn = self.db.conn
        result: dict[str, object] = {}
        errors: list[Exception] = []

        def _worker() -> None:
            try:
                result["value"] = self.db.get_setting("threading_probe", "")
                result["conn"] = self.db.conn
                self.db.set_setting("threading_writer", "worker-thread")
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=_worker)
        worker.start()
        worker.join(timeout=5)

        self.assertFalse(worker.is_alive(), "Worker thread did not finish in time.")
        self.assertFalse(errors, f"Cross-thread Database access failed: {errors}")
        self.assertEqual("main-thread", result.get("value"))
        self.assertIsNot(main_conn, result.get("conn"))
        self.assertEqual("worker-thread", self.db.get_setting("threading_writer", ""))

