from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from models.database import Database


class TempDBTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "dishboard_test.db"
        self.db = Database(str(db_path))
        self.db.connect()
        self.db.init_db()

    def tearDown(self) -> None:
        try:
            self.db.close()
        finally:
            self._tmpdir.cleanup()
