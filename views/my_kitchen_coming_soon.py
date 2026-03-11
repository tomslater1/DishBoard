import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
)
from PySide6.QtCore import Qt, QSize

from utils.theme import manager as theme_manager

COLOUR = "#e8924a"


class MyKitchenComingSoonView(QWidget):
    """Coming soon placeholder for the My Kitchen pantry/storage tracker."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("view-container")
        self._build_ui()

    def _build_ui(self):
        if self.layout():
            QWidget().setLayout(self.layout())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Centre column
        col = QWidget()
        col.setStyleSheet("background: transparent;")
        col.setMaximumWidth(480)
        vl = QVBoxLayout(col)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icon bubble
        icon_bg = QWidget()
        icon_bg.setFixedSize(88, 88)
        icon_bg.setStyleSheet(
            f"background: rgba(232,146,74,0.10); border-radius: 22px;"
            f" border: 1px solid rgba(232,146,74,0.18);"
        )
        icon_bg_l = QHBoxLayout(icon_bg)
        icon_bg_l.setContentsMargins(0, 0, 0, 0)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("fa5s.box-open", color=COLOUR).pixmap(QSize(34, 34)))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        icon_bg_l.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon_row.addWidget(icon_bg)
        icon_row.addStretch()
        vl.addLayout(icon_row)
        vl.addSpacing(22)

        # "Coming soon" badge
        badge = QLabel("COMING SOON")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedHeight(28)
        badge.setStyleSheet(
            f"color: {COLOUR}; font-size: 11px; font-weight: 700; letter-spacing: 2px;"
            f" background: rgba(232,146,74,0.10); border-radius: 7px;"
            f" border: 1px solid rgba(232,146,74,0.20); padding: 0 14px;"
        )
        badge_row = QHBoxLayout()
        badge_row.addStretch()
        badge_row.addWidget(badge)
        badge_row.addStretch()
        vl.addLayout(badge_row)
        vl.addSpacing(18)

        # Title
        title = QLabel("My Kitchen")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {theme_manager.c('#f0f0f0', '#1a1a1a')}; font-size: 30px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        vl.addWidget(title)
        vl.addSpacing(12)

        # Description
        desc = QLabel(
            "Track everything in your pantry, fridge, and freezer.\n"
            "DishBoard will know exactly what you have — and what you're running low on."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {theme_manager.c('#888888', '#666666')}; font-size: 15px; line-height: 1.5;"
            " background: transparent; border: none;"
        )
        vl.addWidget(desc)
        vl.addSpacing(28)

        # Feature teaser chips row
        teaser_items = [
            ("fa5s.search",       "Smart pantry search"),
            ("fa5s.bell",         "Low stock alerts"),
            ("fa5s.robot",        "Dishy integration"),
        ]
        chips_row = QHBoxLayout()
        chips_row.setSpacing(10)
        chips_row.addStretch()
        for icon_name, label_text in teaser_items:
            chip = QWidget()
            chip.setStyleSheet(
                f"background: {theme_manager.c('rgba(255,255,255,0.04)', 'rgba(0,0,0,0.04)')};"
                f" border-radius: 8px;"
                f" border: 1px solid {theme_manager.c('rgba(255,255,255,0.08)', 'rgba(0,0,0,0.08)')};"
            )
            chip_l = QHBoxLayout(chip)
            chip_l.setContentsMargins(10, 6, 12, 6)
            chip_l.setSpacing(6)

            chip_icon = QLabel()
            chip_icon.setPixmap(
                qta.icon(icon_name, color=theme_manager.c("#666666", "#999999")).pixmap(QSize(11, 11))
            )
            chip_icon.setStyleSheet("background: transparent; border: none;")

            chip_lbl = QLabel(label_text)
            chip_lbl.setStyleSheet(
                f"color: {theme_manager.c('#888888', '#777777')}; font-size: 13px;"
                " background: transparent; border: none;"
            )
            chip_l.addWidget(chip_icon)
            chip_l.addWidget(chip_lbl)
            chips_row.addWidget(chip)
        chips_row.addStretch()
        vl.addLayout(chips_row)

        outer.addStretch()
        outer.addWidget(col, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch()

    def apply_theme(self, _mode: str):
        self._build_ui()
