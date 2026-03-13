"""ThemedMessageBox — custom-styled replacement for QMessageBox in DishBoard."""
from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
)

from utils.theme import manager as theme_manager

_CANCEL_WORDS = {"cancel", "later", "skip", "no"}
_DESTRUCT_WORDS = ("delete", "clear", "remove", "wipe", "leave", "sign out")

_KIND_ICON = {
    "info":     ("fa5s.check-circle",        "#34d399"),
    "warning":  ("fa5s.exclamation-triangle", "#f0a500"),
    "critical": ("fa5s.times-circle",         "#e05c7a"),
    "question": ("fa5s.question-circle",      "#7c6af7"),
}


def _btn_style(text: str) -> str:
    tm = theme_manager
    lower = text.lower()
    if lower in _CANCEL_WORDS:
        return (
            f"QPushButton {{"
            f" background: transparent;"
            f" border: 1px solid {tm.c('#333333', '#dddddd')};"
            f" border-radius: 9px; padding: 0 20px;"
            f" color: {tm.c('#888888', '#666666')}; font-size: 13px;"
            f"}}"
            f"QPushButton:hover {{ background: {tm.c('#1e1e1e', '#f0f0f0')}; }}"
        )
    elif any(w in lower for w in _DESTRUCT_WORDS):
        return (
            "QPushButton {"
            " background: #e05c7a; color: #ffffff; border: none;"
            " border-radius: 9px; padding: 0 20px; font-size: 13px; font-weight: 600;"
            "}"
            "QPushButton:hover { background: #c94e6a; }"
        )
    else:
        return (
            "QPushButton {"
            " background: #ff6b35; color: #ffffff; border: none;"
            " border-radius: 9px; padding: 0 20px; font-size: 13px; font-weight: 600;"
            "}"
            "QPushButton:hover { background: #e05a28; }"
        )


class ThemedMessageBox(QDialog):
    """Custom-themed replacement for QMessageBox. Use static class methods."""

    def __init__(self, title: str, text: str, buttons: list[str],
                 kind: str = "info", parent=None):
        super().__init__(parent)
        self._clicked: str | None = None
        self._buttons_list = buttons
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self._build_ui(title, text, kind)

    def _build_ui(self, title: str, text: str, kind: str):
        tm = theme_manager

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        card = QWidget()
        card.setObjectName("tmb-card")
        card.setStyleSheet(
            f"QWidget#tmb-card {{"
            f"  background: {tm.c('#161616', '#ffffff')};"
            f"  border-radius: 14px;"
            f"  border: 1px solid {tm.c('#2a2a2a', '#e0e0e0')};"
            f"}}"
        )
        card.setMinimumWidth(380)
        card.setMaximumWidth(560)

        vl = QVBoxLayout(card)
        vl.setContentsMargins(30, 28, 30, 24)
        vl.setSpacing(0)

        if kind in _KIND_ICON:
            icon_name, icon_color = _KIND_ICON[kind]
            icon_lbl = QLabel()
            icon_lbl.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(QSize(40, 40)))
            icon_lbl.setStyleSheet("background: transparent;")
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vl.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)
            vl.addSpacing(14)

        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700;"
            f" color: {tm.c('#f0f0f0', '#1a1a1a')}; background: transparent;"
        )
        vl.addWidget(title_lbl)
        vl.addSpacing(8)

        text_lbl = QLabel(text)
        text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_lbl.setWordWrap(True)
        text_lbl.setTextFormat(Qt.TextFormat.AutoText)
        text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_lbl.setStyleSheet(
            f"font-size: 13px;"
            f" color: {tm.c('#999999', '#555555')}; background: transparent;"
        )
        vl.addWidget(text_lbl)
        vl.addSpacing(24)

        if len(self._buttons_list) == 1:
            btn_row = QHBoxLayout()
            btn_row.setSpacing(8)
            btn_row.addStretch()
            btn = self._make_btn(self._buttons_list[0])
            btn.setMinimumWidth(120)
            btn_row.addWidget(btn)
            btn_row.addStretch()
            vl.addLayout(btn_row)
        elif len(self._buttons_list) <= 3:
            btn_row = QHBoxLayout()
            btn_row.setSpacing(8)
            for label in self._buttons_list:
                btn = self._make_btn(label)
                btn.setMinimumWidth(130)
                btn_row.addWidget(btn, 1)
            vl.addLayout(btn_row)
        else:
            # Four+ actions are stacked vertically so long labels never clip.
            btn_col = QVBoxLayout()
            btn_col.setSpacing(8)
            for label in self._buttons_list:
                btn = self._make_btn(label)
                btn.setMinimumWidth(220)
                btn_col.addWidget(btn)
            vl.addLayout(btn_col)
        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

    def _make_btn(self, label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(38)
        btn.setMinimumWidth(120)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(_btn_style(label))
        btn.clicked.connect(lambda checked=False, t=label: self._on_click(t))
        return btn

    def _on_click(self, text: str):
        self._clicked = text
        if text.lower() in _CANCEL_WORDS:
            self.reject()
        else:
            self.accept()

    def clicked_button(self) -> str | None:
        return self._clicked

    @staticmethod
    def information(parent, title: str, text: str):
        ThemedMessageBox(title, text, ["OK"], kind="info", parent=parent).exec()

    @staticmethod
    def warning(parent, title: str, text: str):
        ThemedMessageBox(title, text, ["OK"], kind="warning", parent=parent).exec()

    @staticmethod
    def critical(parent, title: str, text: str):
        ThemedMessageBox(title, text, ["OK"], kind="critical", parent=parent).exec()

    @staticmethod
    def confirm(parent, title: str, text: str,
                confirm_text: str = "Yes", cancel_text: str = "Cancel") -> bool:
        dlg = ThemedMessageBox(
            title, text, [cancel_text, confirm_text],
            kind="question", parent=parent,
        )
        return dlg.exec() == QDialog.DialogCode.Accepted

    @staticmethod
    def show_buttons(parent, title: str, text: str, buttons: list[str],
                     kind: str = "question") -> str | None:
        dlg = ThemedMessageBox(title, text, buttons, kind=kind, parent=parent)
        dlg.exec()
        return dlg.clicked_button()
