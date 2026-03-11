"""
Update available notification dialog for DishBoard.

Shown when utils/updater.check_for_update() finds a newer GitHub release.
Opens the GitHub Releases download page in the user's browser.
"""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame,
)

from utils.theme import manager as theme_manager


class UpdateDialog(QDialog):
    """Modal dialog informing the user that a new version is available."""

    def __init__(self, update_info: dict, parent=None):
        super().__init__(parent)
        self._info = update_info
        self.setWindowTitle("Update Available")
        self.setModal(True)
        self.setFixedWidth(420)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        tm = theme_manager
        version = self._info.get("version", "")
        notes   = self._info.get("notes", "").strip()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)

        # Header row — emoji + title
        title = QLabel(f"🎉  DishBoard v{version} is available")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700;"
            f"color: {tm.c('#ffffff', '#111111')};"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        # Subtitle
        sub = QLabel("You're running an older version. Update to get the latest features and fixes.")
        sub.setStyleSheet(
            f"font-size: 12px; color: {tm.c('#aaaaaa', '#666666')};"
        )
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # Release notes (only if non-empty)
        if notes:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color: {tm.c('#2a2a2a', '#dddddd')};")
            layout.addWidget(sep)

            notes_label = QLabel(notes)
            notes_label.setStyleSheet(
                f"font-size: 11px; color: {tm.c('#cccccc', '#444444')};"
                f"background: {tm.c('#1a1a1a', '#f5f5f5')};"
                f"border-radius: 6px; padding: 10px;"
            )
            notes_label.setWordWrap(True)
            notes_label.setMaximumHeight(160)
            layout.addWidget(notes_label)

        layout.addSpacing(4)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        later_btn = QPushButton("Later")
        later_btn.setFixedHeight(36)
        later_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        later_btn.setStyleSheet(
            f"QPushButton {{"
            f"  border: 1px solid {tm.c('#333333', '#cccccc')};"
            f"  border-radius: 8px;"
            f"  background: transparent;"
            f"  color: {tm.c('#aaaaaa', '#666666')};"
            f"  font-size: 13px;"
            f"  padding: 0 16px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: {tm.c('#1e1e1e', '#eeeeee')};"
            f"}}"
        )
        later_btn.clicked.connect(self.reject)

        download_btn = QPushButton("Download Update")
        download_btn.setObjectName("primary-btn")
        download_btn.setFixedHeight(36)
        download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        download_btn.clicked.connect(self._on_download)

        btn_row.addWidget(later_btn)
        btn_row.addStretch()
        btn_row.addWidget(download_btn)
        layout.addLayout(btn_row)

        # Dialog background
        self.setStyleSheet(
            f"QDialog {{"
            f"  background: {tm.c('#111111', '#ffffff')};"
            f"  border-radius: 12px;"
            f"}}"
        )

    def _on_download(self):
        url = self._info.get("download_url", "")
        if url:
            webbrowser.open(url)
        self.accept()
