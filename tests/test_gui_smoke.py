from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from main_window import MainWindow
from tests.base import TempDBTestCase
from views.login import LoginView
from views.settings import SettingsView


class GuiSmokeTests(TempDBTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_login_view_constructs(self):
        view = LoginView()
        self.assertGreater(view.minimumSizeHint().width(), 0)

    def test_settings_view_constructs_with_temp_db(self):
        view = SettingsView(db=self.db)
        self.assertEqual(view._stack.count(), 8)

    def test_main_window_constructs_and_refreshes(self):
        window = MainWindow(db=self.db)
        window.refresh_all_views()
        self.assertEqual(window.windowTitle(), "DishBoard")


if __name__ == "__main__":
    unittest.main()
