from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from utils.theme import manager as theme_manager
from widgets.page_scaffold import EmptyStateCard, OverflowActionMenu, PageScaffold, SegmentedTabs, StatStrip, StatusBanner


class DesignSystemSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_shared_primitives_construct_in_both_themes(self):
        original_mode = theme_manager.mode
        try:
            for mode in ("dark", "light"):
                theme_manager.apply(mode)
                scaffold = PageScaffold("Title", "Subtitle", "Eyebrow")
                tabs = SegmentedTabs([("one", "One"), ("two", "Two")], scaffold)
                tabs.set_current("one")
                stats = StatStrip(scaffold)
                stats.add_stat("a", "12", "Metric", "#ff6b35")
                banner = StatusBanner("System state visible", "system", scaffold)
                empty = EmptyStateCard("Nothing here", "Try again with real data.", "!")
                overflow = OverflowActionMenu(parent=scaffold)
                overflow.set_actions([{"label": "Refresh", "handler": lambda: None}])
                scaffold.set_toolbar(tabs)
                scaffold.set_stats(stats)
                scaffold.set_banner(banner)
                scaffold.body_layout().addWidget(empty)
                scaffold.body_layout().addWidget(overflow)
                self.assertGreater(scaffold.minimumSizeHint().width(), 0)
        finally:
            theme_manager.apply(original_mode)


if __name__ == "__main__":
    unittest.main()
