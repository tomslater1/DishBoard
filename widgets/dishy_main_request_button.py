"""
DishyMainRequestButton — reusable green AI-branded action button.

Drop-in wherever Dishy is the primary action on a page.

Usage:
    from widgets.dishy_main_request_button import DishyMainRequestButton

    btn = DishyMainRequestButton("Generate from Meal Plan")
    btn.clicked.connect(my_slot)

    # Optional custom subtitle (defaults to "✦ Powered by Dishy AI"):
    btn = DishyMainRequestButton("Build Shopping List", subtitle="Let Dishy handle it")
"""
import qtawesome as qta
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QBrush, QPainterPath


class DishyMainRequestButton(QWidget):
    """
    Green gradient button with robot icon + title + 'Powered by Dishy AI' subtitle.
    Implemented as QWidget to avoid QPushButton rendering conflicts with child labels.
    """

    clicked = Signal()

    def __init__(self, title: str, subtitle: str = "✦ Powered by Dishy AI", parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(48)
        self._hovered = False
        self._pressed = False

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(12)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._ico = QLabel(self)
        self._ico.setPixmap(qta.icon("fa5s.robot", color="#ffffff").pixmap(16, 16))
        self._ico.setStyleSheet("background:transparent")
        self._ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ico.setFixedSize(20, 20)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._lbl_title = QLabel(title, self)
        self._lbl_title.setStyleSheet(
            "font-size:13px;font-weight:700;color:#ffffff;background:transparent"
        )

        self._lbl_sub = QLabel(subtitle, self)
        self._lbl_sub.setStyleSheet(
            "font-size:9px;color:rgba(255,255,255,200);"
            "background:transparent;letter-spacing:0.3px"
        )

        text_col.addWidget(self._lbl_title)
        text_col.addWidget(self._lbl_sub)

        row.addWidget(self._ico)
        row.addLayout(text_col)
        row.addStretch()

    # ── painting ───────────────────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        grad = QLinearGradient(0, 0, self.width(), 0)
        if self._pressed:
            grad.setColorAt(0, QColor("#157a50"))
            grad.setColorAt(1, QColor("#2bb87e"))
        elif self._hovered:
            grad.setColorAt(0, QColor("#1fa86e"))
            grad.setColorAt(1, QColor("#3de8a8"))
        else:
            grad.setColorAt(0, QColor("#1a8f5e"))
            grad.setColorAt(1, QColor("#34d399"))

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 10, 10)
        p.fillPath(path, QBrush(grad))
        p.end()

    # ── mouse events ──────────────────────────────────────────────────────────

    def enterEvent(self, e):
        self._hovered = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovered = False
        self._pressed = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(e.pos()):
                self.clicked.emit()
        super().mouseReleaseEvent(e)
