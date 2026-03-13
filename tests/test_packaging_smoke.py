from __future__ import annotations

import unittest
from pathlib import Path


class PackagingSmokeTests(unittest.TestCase):
    def test_windows_build_script_uses_project_venv(self):
        script = Path("build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn(".venv\\Scripts\\python.exe", script)
        self.assertIn("-m PyInstaller", script)
        self.assertIn("scripts/pre_release_checks.py", script)

    def test_pyinstaller_spec_has_cross_platform_assets(self):
        spec = Path("DishBoard.spec").read_text(encoding="utf-8")
        self.assertIn("assets/styles", spec)
        self.assertIn("assets/icons", spec)
        self.assertIn("keyring.backends.Windows", spec)
        self.assertIn("keyring.backends.macOS", spec)


if __name__ == "__main__":
    unittest.main()
