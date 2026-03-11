"""
Lightweight theme manager for DishBoard.

Usage:
    from utils.theme import manager

    manager.apply("light")           # switch to light, saves preference
    manager.c("#111111", "#f5f5f5")  # dark/light colour helper
    manager.theme_changed.connect(my_slot)
"""

import os
import json

from PySide6.QtCore import QObject, Signal
from utils.paths import get_data_dir, get_resource_path

_CONFIG    = os.path.join(get_data_dir(), "config.json")
_DARK_QSS  = get_resource_path("assets/styles/theme.qss")
_LIGHT_QSS = get_resource_path("assets/styles/theme_light.qss")


class _ThemeManager(QObject):
    """Singleton theme manager — use the module-level ``manager`` instance."""

    theme_changed = Signal(str)   # emits "dark" or "light"

    def __init__(self):
        super().__init__()
        self._mode: str = "dark"

    # ------------------------------------------------------------------ public

    @property
    def mode(self) -> str:
        return self._mode

    def c(self, dark: str, light: str) -> str:
        """Return the colour string appropriate for the current theme."""
        return dark if self._mode == "dark" else light

    def load(self) -> str:
        """Load the persisted theme preference and return it."""
        try:
            with open(_CONFIG) as f:
                self._mode = json.load(f).get("theme", "dark")
        except Exception:
            self._mode = "dark"
        return self._mode

    def apply(self, mode: str):
        """Switch to *mode* ("dark"/"light"), persist the choice, refresh QSS."""
        from PySide6.QtWidgets import QApplication
        self._mode = mode
        self._save(mode)
        app = QApplication.instance()
        if not app:
            return

        if mode == "dark":
            try:
                from qt_material import apply_stylesheet
                apply_stylesheet(app, theme="dark_amber.xml", extra={"density_scale": "0"})
            except Exception:
                pass
            if os.path.exists(_DARK_QSS):
                with open(_DARK_QSS) as f:
                    app.setStyleSheet(app.styleSheet() + "\n" + f.read())
            # Override qt_material amber palette so QLineEdit text is orange, not yellow
            from PySide6.QtGui import QPalette, QColor
            palette = app.palette()
            palette.setColor(QPalette.ColorRole.Text, QColor("#ff6b35"))
            app.setPalette(palette)
        else:
            if os.path.exists(_LIGHT_QSS):
                with open(_LIGHT_QSS) as f:
                    app.setStyleSheet(f.read())

        self.theme_changed.emit(mode)

    # ----------------------------------------------------------------- private

    def _save(self, mode: str):
        cfg: dict = {}
        try:
            with open(_CONFIG) as f:
                cfg = json.load(f)
        except Exception:
            pass
        cfg["theme"] = mode
        try:
            with open(_CONFIG, "w") as f:
                json.dump(cfg, f)
        except Exception:
            pass


manager = _ThemeManager()
