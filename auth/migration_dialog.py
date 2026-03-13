"""
MigrationDialog — shown once on first sign-in when local data exists.

Asks the user whether to upload their existing local data to their new account.
The upload runs via CloudSyncService.push_all() with a progress label.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QWidget,
)

import qtawesome as qta

from utils.theme import manager as theme_manager
from utils.workers import run_async


class MigrationDialog(QDialog):
    def __init__(self, recipe_count: int, user_id: str, parent=None):
        super().__init__(parent)
        self._user_id = user_id
        self._recipe_count = recipe_count
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self._build_ui(recipe_count)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        self._drag_pos = None

    def _build_ui(self, recipe_count: int):
        tm = theme_manager

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        card = QWidget()
        card.setObjectName("migration-card")
        card.setFixedWidth(420)
        card.setStyleSheet(
            f"QWidget#migration-card {{"
            f"  background: {tm.c('#161616', '#ffffff')};"
            f"  border-radius: 14px;"
            f"  border: 1px solid {tm.c('#2a2a2a', '#e0e0e0')};"
            f"}}"
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        # Icon + heading
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("fa5s.cloud-upload-alt", color="#ff6b35").pixmap(QSize(36, 36)))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent;")
        layout.addWidget(icon_lbl)

        title = QLabel("You have existing data")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"font-size: 17px; font-weight: 700; background: transparent;"
            f" color: {tm.c('#f0f0f0', '#1a1a1a')};"
        )
        layout.addWidget(title)

        # Recipe count summary
        summary = QLabel(
            f"We found <b>{recipe_count} recipe{'s' if recipe_count != 1 else ''}</b> "
            f"stored locally on this device.<br><br>"
            f"Would you like to upload them to your new account so they sync "
            f"across all your devices?"
        )
        summary.setWordWrap(True)
        summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        summary.setStyleSheet(
            f"font-size: 13px; color: {tm.c('#888888', '#555555')};"
            f" background: transparent; line-height: 1.5;"
        )
        layout.addWidget(summary)

        layout.addSpacing(4)

        # Progress label (hidden until upload starts)
        self._progress_lbl = QLabel("")
        self._progress_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_lbl.setStyleSheet(
            "font-size: 12px; color: #34d399; background: transparent;"
        )
        self._progress_lbl.setVisible(False)
        layout.addWidget(self._progress_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._skip_btn = QPushButton("Skip for now")
        self._skip_btn.setFixedHeight(44)
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent; border: 1px solid {tm.c('#333333', '#dddddd')};"
            f"  border-radius: 10px; color: {tm.c('#888888', '#666666')};"
            f"  font-size: 13px; font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{ border-color: {tm.c('#555555', '#aaaaaa')};"
            f" color: {tm.c('#cccccc', '#333333')}; }}"
        )
        self._skip_btn.clicked.connect(self.reject)

        self._upload_btn = QPushButton("  Upload my data")
        self._upload_btn.setIcon(qta.icon("fa5s.cloud-upload-alt", color="#ffffff"))
        self._upload_btn.setIconSize(QSize(14, 14))
        self._upload_btn.setFixedHeight(44)
        self._upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upload_btn.setStyleSheet(
            "QPushButton {"
            "  background: #ff6b35; color: #ffffff; border: none;"
            "  border-radius: 10px; font-size: 13px; font-weight: 700;"
            "}"
            "QPushButton:hover { background: #e05a28; }"
            "QPushButton:disabled { background: #553322; color: #888; }"
        )
        self._upload_btn.clicked.connect(self._on_upload)

        btn_row.addWidget(self._skip_btn)
        btn_row.addWidget(self._upload_btn)
        layout.addLayout(btn_row)

        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

    def _on_upload(self):
        self._upload_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        self._progress_lbl.setText("Uploading… please wait")
        self._progress_lbl.setVisible(True)

        user_id = self._user_id

        def _work():
            from auth.cloud_sync import CloudSyncService
            return CloudSyncService(user_id).push_all()

        def _done(result):
            pushed = result.pushed
            self._progress_lbl.setText(
                f"Done! Uploaded {pushed} item{'s' if pushed != 1 else ''}."
            )
            # Auto-close after a short delay
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1200, self.accept)

        def _err(err: str):
            self._progress_lbl.setText(f"Upload failed: {err[:80]}")
            self._progress_lbl.setStyleSheet(
                "font-size: 12px; color: #dc3545; background: transparent;"
            )
            self._upload_btn.setEnabled(True)
            self._skip_btn.setEnabled(True)

        run_async(_work, on_result=_done, on_error=_err)
