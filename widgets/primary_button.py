"""
Animated primary action button for DishBoard.

Drop-in replacement for QPushButton + setObjectName("primary-btn").
Adds:
  - PointingHandCursor
  - Subtle orange glow shadow that animates on hover
  - Shadow collapses on press for a satisfying "pushed" feel
"""
from PySide6.QtWidgets import QPushButton, QGraphicsDropShadowEffect
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve


class PrimaryButton(QPushButton):
    """
    Orange gradient primary button that matches the DishBoard design language.
    The QSS gradient and radius are defined in theme.qss / theme_light.qss.
    This class adds cursor + animated glow shadow on hover.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("primary-btn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Soft orange ambient shadow — starts barely visible
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setColor(QColor(255, 107, 53, 90))
        self._shadow.setBlurRadius(6)
        self._shadow.setOffset(0, 3)
        self.setGraphicsEffect(self._shadow)

        # Smooth animation on the blur radius only
        self._anim = QPropertyAnimation(self._shadow, b"blurRadius")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(int(self._shadow.blurRadius()))
        self._anim.setEndValue(18)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(int(self._shadow.blurRadius()))
        self._anim.setEndValue(6)
        self._anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._anim.stop()
        self._shadow.setBlurRadius(3)
        self._shadow.setOffset(0, 1)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._shadow.setOffset(0, 3)
        self._anim.setStartValue(3)
        self._anim.setEndValue(18)
        self._anim.start()
        super().mouseReleaseEvent(event)
