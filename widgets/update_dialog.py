"""
Update available notification dialog for DishBoard.

Shown when utils/updater.check_for_update() finds a newer GitHub release.
Opens the GitHub Releases download page in the user's browser.
"""

from __future__ import annotations

import webbrowser

import qtawesome as qta
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QWidget,
)

from utils.theme import manager as theme_manager


class UpdateDialog(QDialog):
    """Modal dialog informing the user that a new version is available."""

    def __init__(self, update_info: dict, parent=None):
        super().__init__(parent)
        self._info = update_info
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self._build_ui()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        self._drag_pos = None

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        tm = theme_manager
        version = self._info.get("version", "")
        notes   = self._info.get("notes", "").strip()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        card = QWidget()
        card.setObjectName("update-card")
        card.setFixedWidth(440)
        card.setStyleSheet(
            f"QWidget#update-card {{"
            f"  background: {tm.c('#161616', '#ffffff')};"
            f"  border-radius: 14px;"
            f"  border: 1px solid {tm.c('#2a2a2a', '#e0e0e0')};"
            f"}}"
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 22)
        layout.setSpacing(14)

        # Icon
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("fa5s.arrow-circle-up", color="#34d399").pixmap(QSize(38, 38)))
        icon_lbl.setStyleSheet("background: transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        title = QLabel(f"DishBoard v{version} is available")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700;"
            f" color: {tm.c('#f0f0f0', '#111111')}; background: transparent;"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        sub = QLabel("You're running an older version. Update to get the latest features and fixes.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            f"font-size: 12px; color: {tm.c('#888888', '#666666')}; background: transparent;"
        )
        sub.setWordWrap(True)
        layout.addWidget(sub)

        if notes:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color: {tm.c('#2a2a2a', '#dddddd')};")
            layout.addWidget(sep)

            notes_label = QLabel(notes)
            notes_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            notes_label.setStyleSheet(
                f"font-size: 11px; color: {tm.c('#cccccc', '#444444')};"
                f"background: {tm.c('#1a1a1a', '#f5f5f5')};"
                f"border-radius: 8px; padding: 10px; border: none;"
            )
            notes_label.setWordWrap(True)
            notes_label.setMaximumHeight(160)
            layout.addWidget(notes_label)

        layout.addSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        later_btn = QPushButton("Later")
        later_btn.setFixedHeight(38)
        later_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        later_btn.setStyleSheet(
            f"QPushButton {{"
            f"  border: 1px solid {tm.c('#333333', '#cccccc')};"
            f"  border-radius: 9px; background: transparent;"
            f"  color: {tm.c('#888888', '#666666')}; font-size: 13px; padding: 0 18px;"
            f"}}"
            f"QPushButton:hover {{ background: {tm.c('#1e1e1e', '#eeeeee')}; }}"
        )
        later_btn.clicked.connect(self.reject)

        download_btn = QPushButton("Download Update")
        download_btn.setFixedHeight(38)
        download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        download_btn.setStyleSheet(
            "QPushButton { background: #ff6b35; color: #ffffff; border: none;"
            " border-radius: 9px; font-size: 13px; font-weight: 600; padding: 0 18px; }"
            "QPushButton:hover { background: #e05a28; }"
        )
        download_btn.clicked.connect(self._on_download)

        btn_row.addWidget(later_btn)
        btn_row.addStretch()
        btn_row.addWidget(download_btn)
        layout.addLayout(btn_row)

        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

    def _on_download(self):
        url = self._info.get("download_url", "")
        if url:
            webbrowser.open(url)
        self.accept()
