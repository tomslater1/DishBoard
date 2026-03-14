"""Shared page-shell primitives for top-level DishBoard screens."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from utils.ui_tokens import SPACING, SIZING, page_margins


class OverflowActionMenu(QToolButton):
    """Shared overflow button for low-frequency page actions."""

    def __init__(self, text: str = "More", parent=None):
        super().__init__(parent)
        self.setObjectName("overflow-action-btn")
        self.setText(text)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(SIZING["control_height"])
        self._menu = QMenu(self)
        self.setMenu(self._menu)

    def set_actions(self, items: list[dict]):
        self._menu.clear()
        for item in items or []:
            title = str(item.get("label") or "").strip()
            if not title:
                continue
            children = item.get("items") or []
            if children:
                submenu = self._menu.addMenu(title)
                for child in children:
                    child_title = str(child.get("label") or "").strip()
                    if not child_title:
                        continue
                    action = submenu.addAction(child_title)
                    action.setEnabled(bool(child.get("enabled", True)))
                    handler = child.get("handler")
                    if handler is not None:
                        action.triggered.connect(handler)
                continue
            action = QAction(title, self._menu)
            action.setEnabled(bool(item.get("enabled", True)))
            handler = item.get("handler")
            if handler is not None:
                action.triggered.connect(handler)
            self._menu.addAction(action)
        self.setVisible(bool(self._menu.actions()))


class PageToolbar(QWidget):
    """Standard toolbar row with stable left/right action grouping."""

    def __init__(self, parent=None, *, density: str = "comfortable"):
        super().__init__(parent)
        self.setObjectName("page-toolbar")
        self.setProperty("density", density)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["sm"])
        self._left = QHBoxLayout()
        self._left.setContentsMargins(0, 0, 0, 0)
        self._left.setSpacing(SPACING["sm"])
        self._center = QHBoxLayout()
        self._center.setContentsMargins(0, 0, 0, 0)
        self._center.setSpacing(SPACING["sm"])
        self._right = QHBoxLayout()
        self._right.setContentsMargins(0, 0, 0, 0)
        self._right.setSpacing(SPACING["sm"])
        layout.addLayout(self._left)
        layout.addStretch()
        layout.addLayout(self._center)
        layout.addLayout(self._right)
        self._primary_action: QWidget | None = None
        self._secondary_actions: list[QWidget] = []
        self._overflow = OverflowActionMenu(parent=self)
        self._overflow.hide()
        self._right.addWidget(self._overflow)

    def add_left(self, widget: QWidget, stretch: int = 0):
        self._left.addWidget(widget, stretch)

    def add_right(self, widget: QWidget, stretch: int = 0):
        self._right.insertWidget(max(0, self._right.count() - 1), widget, stretch)

    def add_left_layout(self, layout):
        self._left.addLayout(layout)

    def add_right_layout(self, layout):
        self._right.insertLayout(max(0, self._right.count() - 1), layout)

    def set_primary_action(self, widget: QWidget | None):
        if self._primary_action is not None:
            self._center.removeWidget(self._primary_action)
            self._primary_action.setParent(None)
        self._primary_action = widget
        if widget is not None:
            widget.setProperty("actionRole", "primary")
            self._center.insertWidget(0, widget)

    def add_secondary_action(self, widget: QWidget):
        widget.setProperty("actionRole", "secondary")
        self._secondary_actions.append(widget)
        self._right.insertWidget(max(0, self._right.count() - 1), widget)

    def clear_secondary_actions(self):
        for widget in self._secondary_actions:
            self._right.removeWidget(widget)
            widget.setParent(None)
        self._secondary_actions.clear()

    def set_overflow_actions(self, items: list[dict]):
        self._overflow.set_actions(items)


class StatStrip(QWidget):
    """Shared stat row that exposes value/label/detail handles for updates."""

    def __init__(self, parent=None, *, density: str = "comfortable", max_visible: int = 4):
        super().__init__(parent)
        self.setObjectName("stat-strip")
        self.setProperty("density", density)
        self._items: dict[str, dict[str, QLabel]] = {}
        self._max_visible = max(1, int(max_visible))
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(SPACING["md"])

    def add_stat(self, key: str, value: str, label: str, color: str, detail: str = "") -> dict[str, QLabel]:
        if len(self._items) >= self._max_visible:
            raise ValueError("StatStrip max_visible exceeded")
        card = QWidget(self)
        card.setObjectName("stat-strip-card")
        card.setProperty("accent", color)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(SPACING["lg"], SPACING["md"], SPACING["lg"], SPACING["md"])
        card_layout.setSpacing(2)

        value_lbl = QLabel(value, card)
        value_lbl.setObjectName("stat-strip-value")

        label_lbl = QLabel(label, card)
        label_lbl.setObjectName("stat-strip-label")

        detail_lbl = QLabel(detail, card)
        detail_lbl.setObjectName("stat-strip-detail")
        detail_lbl.setVisible(bool(detail))

        card_layout.addWidget(value_lbl)
        card_layout.addWidget(label_lbl)
        card_layout.addWidget(detail_lbl)
        card_layout.addStretch()

        self._layout.addWidget(card, 1)
        self._items[key] = {"value": value_lbl, "label": label_lbl, "detail": detail_lbl}
        return self._items[key]

    def set_value(self, key: str, value: str):
        item = self._items.get(key)
        if item:
            item["value"].setText(value)

    def set_detail(self, key: str, detail: str):
        item = self._items.get(key)
        if item:
            item["detail"].setText(detail)
            item["detail"].setVisible(bool(detail))

    def item(self, key: str) -> dict[str, QLabel] | None:
        return self._items.get(key)


class SectionHeader(QWidget):
    """Small section header for content blocks inside a page scaffold."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        eyebrow: str = "",
        action: QWidget | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("section-header")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self._eyebrow = QLabel(eyebrow, self)
        self._eyebrow.setObjectName("page-eyebrow")
        self._eyebrow.setVisible(bool(eyebrow))
        text_col.addWidget(self._eyebrow)

        self._title = QLabel(title, self)
        self._title.setObjectName("section-header-title")
        text_col.addWidget(self._title)

        self._subtitle = QLabel(subtitle, self)
        self._subtitle.setObjectName("section-header-subtitle")
        self._subtitle.setVisible(bool(subtitle))
        text_col.addWidget(self._subtitle)

        layout.addLayout(text_col, 1)
        if action is not None:
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignVCenter)


class SegmentedTabs(QWidget):
    """Button-based shared local navigation."""

    tab_changed = Signal(str)

    def __init__(self, tabs: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setObjectName("segmented-tabs")
        self._buttons: dict[str, QPushButton] = {}
        self._current_key: str | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["sm"])
        for key, label in tabs:
            btn = QPushButton(label, self)
            btn.setObjectName("segmented-tab-btn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(SIZING["tab_height"])
            btn.clicked.connect(lambda checked=False, k=key: self.set_current(k))
            self._buttons[key] = btn
            layout.addWidget(btn)
        layout.addStretch()

    def set_current(self, key: str):
        if key == self._current_key:
            return
        self._current_key = key
        for name, btn in self._buttons.items():
            checked = name == key
            btn.setChecked(checked)
            btn.setProperty("active", checked)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.tab_changed.emit(key)

    def current_key(self) -> str | None:
        return self._current_key

    def button(self, key: str) -> QPushButton | None:
        return self._buttons.get(key)


class StatusBanner(QWidget):
    """Compact inline banner for helper text, warnings, and system state."""

    def __init__(self, text: str = "", variant: str = "system", parent=None):
        super().__init__(parent)
        self.setObjectName("status-banner")
        self.setProperty("variant", variant)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"])
        layout.setSpacing(SPACING["sm"])
        self._label = QLabel(text, self)
        self._label.setObjectName("status-banner-text")
        self._label.setWordWrap(True)
        layout.addWidget(self._label)
        self.setVisible(bool(text))

    def set_text(self, text: str):
        self._label.setText(text)
        self.setVisible(bool(text))

    def set_variant(self, variant: str):
        self.setProperty("variant", variant)
        self.style().unpolish(self)
        self.style().polish(self)


class EmptyStateCard(QWidget):
    """Shared empty state treatment for sparse or first-run screens."""

    def __init__(
        self,
        title: str,
        body: str,
        icon: str = "",
        action: QWidget | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("empty-state-card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["xl"])
        layout.setSpacing(SPACING["sm"])
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon = QLabel(icon, self)
        self._icon.setObjectName("empty-state-icon")
        self._icon.setVisible(bool(icon))
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon)

        self._title = QLabel(title, self)
        self._title.setObjectName("empty-state-title")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)

        self._body = QLabel(body, self)
        self._body.setObjectName("empty-state-body")
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.setWordWrap(True)
        layout.addWidget(self._body)

        if action is not None:
            layout.addSpacing(SPACING["sm"])
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignCenter)


class PageScaffold(QWidget):
    """Shared top-level page shell with predictable header, toolbar, and body rhythm."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        eyebrow: str = "",
        parent=None,
        compact: bool = False,
        density: str = "comfortable",
        quiet_header: bool = False,
    ):
        super().__init__(parent)
        self.setObjectName("page-scaffold")
        self.setProperty("density", density)
        self.setProperty("quietHeader", quiet_header)
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(*page_margins(compact=compact))
        self._outer.setSpacing(SPACING["section_gap_sm"])

        self._header = QWidget(self)
        self._header.setObjectName("page-header")
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(SPACING["lg"])

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(3)

        self._eyebrow = QLabel(eyebrow, self._header)
        self._eyebrow.setObjectName("page-eyebrow")
        self._eyebrow.setVisible(bool(eyebrow))
        text_col.addWidget(self._eyebrow)

        self._title = QLabel(title, self._header)
        self._title.setObjectName("page-title")
        text_col.addWidget(self._title)

        self._subtitle = QLabel(subtitle, self._header)
        self._subtitle.setObjectName("page-date")
        self._subtitle.setWordWrap(True)
        self._subtitle.setVisible(bool(subtitle))
        text_col.addWidget(self._subtitle)

        header_layout.addLayout(text_col, 1)

        self._header_action_slot = QWidget(self._header)
        self._header_action_slot.setObjectName("page-header-action-slot")
        self._header_action_layout = QHBoxLayout(self._header_action_slot)
        self._header_action_layout.setContentsMargins(0, 0, 0, 0)
        self._header_action_layout.setSpacing(SPACING["sm"])
        header_layout.addWidget(self._header_action_slot, 0, Qt.AlignmentFlag.AlignTop)
        self._header_action_slot.hide()

        self._toolbar_slot = QWidget(self)
        self._toolbar_slot.setObjectName("page-toolbar-slot")
        self._toolbar_layout = QVBoxLayout(self._toolbar_slot)
        self._toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self._toolbar_layout.setSpacing(SPACING["sm"])
        self._toolbar_slot.hide()

        self._banner_slot = QWidget(self)
        self._banner_slot.setObjectName("page-banner-slot")
        self._banner_layout = QVBoxLayout(self._banner_slot)
        self._banner_layout.setContentsMargins(0, 0, 0, 0)
        self._banner_layout.setSpacing(SPACING["sm"])
        self._banner_slot.hide()

        self._stats_slot = QWidget(self)
        self._stats_slot.setObjectName("page-stats-slot")
        self._stats_layout = QVBoxLayout(self._stats_slot)
        self._stats_layout.setContentsMargins(0, 0, 0, 0)
        self._stats_layout.setSpacing(0)
        self._stats_slot.hide()

        self._body = QWidget(self)
        self._body.setObjectName("page-body")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(SPACING["section_gap_sm"])

        self._outer.addWidget(self._header)
        self._outer.addWidget(self._toolbar_slot)
        self._outer.addWidget(self._banner_slot)
        self._outer.addWidget(self._stats_slot)
        self._outer.addWidget(self._body, 1)

    def set_title(self, title: str):
        self._title.setText(title)

    def set_subtitle(self, subtitle: str):
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))

    def set_eyebrow(self, eyebrow: str):
        self._eyebrow.setText(eyebrow)
        self._eyebrow.setVisible(bool(eyebrow))

    def set_header_action(self, widget: QWidget | None):
        self._clear_layout(self._header_action_layout)
        if widget is None:
            self._header_action_slot.hide()
            return
        self._header_action_layout.addWidget(widget)
        self._header_action_slot.show()

    def set_toolbar(self, widget: QWidget | None):
        self._clear_layout(self._toolbar_layout)
        if widget is None:
            self._toolbar_slot.hide()
            return
        self._toolbar_layout.addWidget(widget)
        self._toolbar_slot.show()

    def set_banner(self, widget: QWidget | None):
        self._clear_layout(self._banner_layout)
        if widget is None:
            self._banner_slot.hide()
            return
        self._banner_layout.addWidget(widget)
        self._banner_slot.show()

    def set_stats(self, widget: QWidget | None):
        self._clear_layout(self._stats_layout)
        if widget is None:
            self._stats_slot.hide()
            return
        self._stats_layout.addWidget(widget)
        self._stats_slot.show()

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def body_widget(self) -> QWidget:
        return self._body

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
