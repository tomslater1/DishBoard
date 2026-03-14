"""
SyncIndicator — small sidebar widget showing cloud sync status.

States: synced | syncing | offline | error | logged_out
Supports expanded (icon + text) and collapsed (icon only) sidebar modes.
"""

from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel



_STATES = {
    "synced":     ("fa5s.cloud",              "Synced",       "#34d399"),
    "syncing":    ("fa5s.sync",               "Syncing…",     "#f0a500"),
    "offline":    ("fa5s.cloud",              "Offline",      "#555555"),
    "error":      ("fa5s.exclamation-circle", "Sync error",   "#dc3545"),
    "logged_out": ("fa5s.user-slash",         "Not signed in","#555555"),
    "live":       ("fa5s.broadcast-tower",    "Live",         "#34d399"),
}


class SyncIndicator(QWidget):
    retry_requested = Signal()   # emitted when user clicks in error state

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = True
        self._current_state = "logged_out"
        self._build_ui()
        self.set_state("logged_out")

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(7)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(14, 14)
        self._icon_lbl.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self._icon_lbl)

        self._text_lbl = QLabel()
        self._text_lbl.setStyleSheet(
            "font-size: 11px; font-weight: 600; background: transparent; border: none;"
        )
        layout.addWidget(self._text_lbl)
        layout.addStretch()

    def set_state(self, state: str) -> None:
        self._current_state = state
        icon_name, text, colour = _STATES.get(state, _STATES["logged_out"])
        self._icon_lbl.setPixmap(
            qta.icon(icon_name, color=colour).pixmap(QSize(14, 14))
        )
        self._text_lbl.setText(text)
        self._text_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {colour};"
            " background: transparent; border: none;"
        )

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._text_lbl.setVisible(expanded)

    def set_error(self, detail: str = "") -> None:
        """Show the error state with an optional tooltip describing the failure."""
        self.set_state("error")
        tip = "Sync failed — click to retry"
        if detail:
            tip = f"Sync failed: {detail[:120]}\nClick to retry"
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if self._current_state == "error":
            self.setToolTip("")
            self.retry_requested.emit()
        super().mousePressEvent(event)
