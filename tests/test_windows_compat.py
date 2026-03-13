from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import utils.paths as paths
import utils.updater as updater
import utils.platform_ops as platform_ops


class WindowsCompatTests(unittest.TestCase):
    def test_frozen_windows_data_dir_uses_appdata(self):
        with patch.object(paths.sys, "platform", "win32"), patch.object(paths.sys, "frozen", True, create=True):
            with patch.dict(os.environ, {"APPDATA": r"C:\\Users\\Test\\AppData\\Roaming"}, clear=False):
                out = paths.get_data_dir()
                self.assertTrue(out.startswith(r"C:\\Users\\Test\\AppData\\Roaming"))
                self.assertTrue(out.endswith("DishBoard"))

    def test_preferred_asset_suffixes_by_platform(self):
        with patch.object(updater.sys, "platform", "win32"):
            self.assertEqual(updater._preferred_asset_suffixes()[0], ".exe")
        with patch.object(updater.sys, "platform", "darwin"):
            self.assertEqual(updater._preferred_asset_suffixes()[0], ".dmg")

    def test_platform_font_family_switches_for_windows(self):
        with patch.object(platform_ops.sys, "platform", "win32"):
            self.assertEqual(platform_ops.preferred_ui_font_family(), "Segoe UI")


if __name__ == "__main__":
    unittest.main()
