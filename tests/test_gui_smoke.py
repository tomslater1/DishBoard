from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit

from main_window import MainWindow
from tests.base import TempDBTestCase
from views.help import HelpView
from views.login import LoginView
from views.onboarding import OnboardingWizard
from views.app_tour import AppTourOverlay
from views.my_kitchen_storage import MyKitchenStorageView
from views.settings import SettingsView
from views.shopping_list import ShoppingListView


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

    def test_shopping_list_view_constructs(self):
        view = ShoppingListView(db=self.db)
        self.assertEqual(view._view_stack.count(), 2)

    def test_my_kitchen_storage_view_constructs(self):
        view = MyKitchenStorageView(db=self.db)
        self.assertEqual(view._stack.count(), 3)

    def test_help_view_constructs(self):
        view = HelpView(lambda _idx: None)
        self.assertGreater(view.sizeHint().width(), 0)

    def test_onboarding_constructs_without_text_inputs(self):
        view = OnboardingWizard(self.db)
        self.assertEqual(len(view.findChildren(QLineEdit)), 0)

    def test_main_window_constructs_and_refreshes(self):
        window = MainWindow(db=self.db)
        window.refresh_all_views()
        self.assertEqual(window.windowTitle(), "DishBoard")
        self.assertIsNotNone(window._command_palette)

    def test_app_tour_overlay_constructs(self):
        window = MainWindow(db=self.db)
        overlay = AppTourOverlay(window, self.db)
        overlay.start()
        self.assertGreater(overlay._bubble.width(), 0)


if __name__ == "__main__":
    unittest.main()
