"""Primary action button for DishBoard.

This class intentionally avoids QGraphicsEffect-based shadows because they
caused recurring Qt painter warnings on some platforms.
"""
from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt


class PrimaryButton(QPushButton):
    """
    Orange gradient primary button that matches the DishBoard design language.
    The QSS gradient and radius are defined in theme.qss / theme_light.qss.
    This class only adds a pointer cursor; visual effects are stylesheet-based.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("primary-btn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
