from __future__ import annotations

from tests.base import TempDBTestCase


class DatabaseConnectionTests(TempDBTestCase):
    def test_connection_uses_wal_busy_timeout_and_autocommit(self):
        self.assertIsNone(self.db.conn.isolation_level)
        self.assertEqual(self.db.conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(self.db.conn.execute("PRAGMA busy_timeout").fetchone()[0], 30000)

