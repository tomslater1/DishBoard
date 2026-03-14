"""Mixed-result command panel dialog used by the main application shell."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, Qt, QSize, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QListView,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from utils.theme import manager as theme_manager

_GROUP_ORDER = {
    "Recent": 0,
    "Quick Add": 1,
    "Commands": 2,
    "Recipes": 3,
    "Meal Planner": 4,
    "My Kitchen": 5,
    "Shopping": 6,
    "Nutrition": 7,
    "Settings": 8,
    "Dishy": 9,
}


@dataclass
class PaletteEntry:
    id: str
    kind: str
    title: str
    subtitle: str
    group: str
    keywords: tuple[str, ...] = field(default_factory=tuple)
    sort_priority: int = 100
    payload: dict = field(default_factory=dict)
    recent: bool = False


@dataclass
class PaletteField:
    key: str
    label: str
    placeholder: str = ""
    field_type: str = "text"
    required: bool = False
    options: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    default: str = ""


@dataclass
class QuickAddForm:
    id: str
    title: str
    subtitle: str
    primary_label: str
    secondary_label: str = "Back"
    helper_text: str = ""
    fields: tuple[PaletteField, ...] = field(default_factory=tuple)
    preview_rows: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    preview_payload: dict = field(default_factory=dict)
    mode: str = "edit"


def _normalize(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _display_text(text: str) -> str:
    return " ".join(str(text or "").replace("_", " ").split())


def _qt_safe_text(text: str) -> str:
    return _display_text(text).replace("&", "&&")


def _qt_plain_text(text: str) -> str:
    return str(text or "").replace("&&", "&")


def _match_bucket(entry: PaletteEntry, query: str) -> int | None:
    if not query:
        return 99

    title = _normalize(entry.title)
    subtitle = _normalize(entry.subtitle)
    keywords = [_normalize(keyword) for keyword in entry.keywords]

    if title.startswith(query):
        return 0
    if any(word.startswith(query) for word in title.split()):
        return 1
    if any(query in haystack for haystack in [title, subtitle, *keywords] if haystack):
        return 2
    return None


def rank_entries(entries: list[PaletteEntry], query: str) -> list[PaletteEntry]:
    normalized_query = _normalize(query)
    if not normalized_query:
        return sorted(
            entries,
            key=lambda entry: (
                _GROUP_ORDER.get(entry.group, 99),
                int(entry.sort_priority),
                entry.title.lower(),
            ),
        )

    ranked: list[tuple[int, int, int, str, PaletteEntry]] = []
    for entry in entries:
        bucket = _match_bucket(entry, normalized_query)
        if bucket is None:
            continue
        ranked.append(
            (
                bucket,
                _GROUP_ORDER.get(entry.group, 99),
                int(entry.sort_priority),
                entry.title.lower(),
                entry,
            )
        )
    ranked.sort(key=lambda item: item[:4])
    return [entry for *_meta, entry in ranked]


class _EntryRow(QWidget):
    def __init__(self, entry: PaletteEntry, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._selected = False
        self._hovered = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._accent = QWidget(self)
        self._accent.setFixedWidth(3)
        layout.addWidget(self._accent)

        body = QWidget(self)
        self._body = body
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(8, 12, 10, 12)
        body_layout.setSpacing(10)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)

        self._title = QLabel(_qt_safe_text(entry.title), self)
        self._subtitle = QLabel(_qt_safe_text(entry.subtitle), self)
        self._subtitle.setWordWrap(True)
        self._meta = QLabel("Recent" if entry.recent else entry.group, self)
        self._meta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        text_col.addWidget(self._title)
        text_col.addWidget(self._subtitle)
        body_layout.addLayout(text_col, 1)
        body_layout.addWidget(self._meta)
        layout.addWidget(body, 1)

        self.setMouseTracking(True)
        self.apply_theme()

    def enterEvent(self, event):
        self._hovered = True
        self.apply_theme()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.apply_theme()
        super().leaveEvent(event)

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self.apply_theme()

    def apply_theme(self) -> None:
        wash = theme_manager.c("rgba(255,107,53,0.08)", "rgba(255,107,53,0.06)")
        hover = theme_manager.c("rgba(255,255,255,0.03)", "rgba(0,0,0,0.03)")
        self._accent.setStyleSheet(
            f"background:{'#ff6b35' if self._selected else 'transparent'}; border:none;"
        )
        self._body.setStyleSheet(
            (
                f"background:{wash}; border:none; border-radius:0px;"
            ) if self._selected else (
                f"background:{hover}; border:none; border-radius:0px;"
            ) if self._hovered else "background:transparent; border:none;"
        )
        self._title.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#f2ece4', '#1f1914')}; font-size: 14px; font-weight: 700;"
        )
        self._subtitle.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#968f86', '#756b61')}; font-size: 11px; font-weight: 500;"
        )
        self._meta.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#817a72', '#8a7f74')}; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;"
        )


class _GroupHeaderRow(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._label = QLabel(_qt_safe_text(title.upper()), self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 12, 6, 2)
        layout.setSpacing(0)
        layout.addWidget(self._label)
        self.apply_theme()

    def apply_theme(self) -> None:
        self._label.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#807a73', '#897f75')};"
            " font-size: 10px; font-weight: 700; letter-spacing: 1.2px;"
        )


class _EntryListWidget(QListWidget):
    entry_activated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(2)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.currentItemChanged.connect(self._restyle_rows)
        self.itemClicked.connect(self._on_item_clicked)

    def _is_entry_item(self, item: QListWidgetItem | None) -> bool:
        return bool(item and item.data(Qt.ItemDataRole.UserRole))

    def _restyle_rows(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        for row in range(self.count()):
            item = self.item(row)
            widget = self.itemWidget(item)
            if isinstance(widget, _EntryRow):
                widget.set_selected(item is current)

    def select_first_entry(self) -> None:
        for row in range(self.count()):
            item = self.item(row)
            if self._is_entry_item(item):
                self.setCurrentRow(row)
                return

    def move_selection(self, delta: int) -> None:
        if self.count() == 0:
            return
        current_row = self.currentRow()
        if current_row < 0:
            self.select_first_entry()
            return
        row = current_row
        while True:
            row += delta
            if row < 0 or row >= self.count():
                break
            if self._is_entry_item(self.item(row)):
                self.setCurrentRow(row)
                self.scrollToItem(self.item(row))
                break

    def activate_current_entry(self) -> None:
        item = self.currentItem()
        if not self._is_entry_item(item):
            return
        self.entry_activated.emit(item.data(Qt.ItemDataRole.UserRole))

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if not self._is_entry_item(item):
            return
        self.setCurrentItem(item)
        self.activate_current_entry()


class CommandPaletteDialog(QDialog):
    query_changed = Signal(str)
    entry_activated = Signal(object)
    form_action_requested = Signal(str, str, object)
    form_field_changed = Signal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[PaletteEntry] = []
        self._active_form: QuickAddForm | None = None
        self._form_widgets: dict[str, QWidget] = {}
        self._form_suggestion_hosts: dict[str, QWidget] = {}
        self._form_suggestion_layouts: dict[str, QVBoxLayout] = {}
        self._form_suggestion_panels: dict[str, QWidget] = {}
        self._form_suggestion_values: dict[str, dict] = {}
        self.setModal(False)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("command-panel")
        self._build_ui()
        self.apply_theme()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(0)

        card = QWidget(self)
        self._card = card
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 22)
        card_layout.setSpacing(10)

        self._input = QLineEdit(self)
        self._input.setFrame(False)
        self._input.setPlaceholderText("Search commands, recipes, pantry, shopping, settings, or Dishy…")
        self._input.textChanged.connect(self.query_changed.emit)
        self._input.installEventFilter(self)
        card_layout.addWidget(self._input)

        self._underline = QWidget(self)
        self._underline.setFixedHeight(1)
        card_layout.addWidget(self._underline)

        self._hint = QLabel("Up/Down to move, Enter to run, Esc to close", self)
        card_layout.addWidget(self._hint)

        self._stack = QStackedWidget(self)

        self._list = _EntryListWidget(self)
        self._list.entry_activated.connect(self.entry_activated.emit)
        self._stack.addWidget(self._list)

        self._form_page = QWidget(self)
        form_layout = QVBoxLayout(self._form_page)
        form_layout.setContentsMargins(0, 6, 0, 0)
        form_layout.setSpacing(14)
        self._form_title = QLabel("", self._form_page)
        self._form_subtitle = QLabel("", self._form_page)
        self._form_subtitle.setWordWrap(True)
        form_layout.addWidget(self._form_title)
        form_layout.addWidget(self._form_subtitle)

        self._form_fields_wrap = QWidget(self._form_page)
        self._form_fields_layout = QVBoxLayout(self._form_fields_wrap)
        self._form_fields_layout.setContentsMargins(0, 0, 0, 0)
        self._form_fields_layout.setSpacing(10)
        form_layout.addWidget(self._form_fields_wrap)

        self._form_helper = QLabel("", self._form_page)
        self._form_helper.setWordWrap(True)
        form_layout.addWidget(self._form_helper)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(14)
        self._secondary_btn = QPushButton("", self._form_page)
        self._secondary_btn.clicked.connect(lambda: self._emit_form_action("secondary"))
        self._primary_btn = QPushButton("", self._form_page)
        self._primary_btn.clicked.connect(lambda: self._emit_form_action("primary"))
        button_row.addWidget(self._secondary_btn)
        button_row.addStretch()
        button_row.addWidget(self._primary_btn)
        form_layout.addLayout(button_row)
        form_layout.addStretch()
        self._stack.addWidget(self._form_page)

        card_layout.addWidget(self._stack, 1)
        outer.addWidget(card)
        self.resize(780, 560)

    def apply_theme(self) -> None:
        self.setStyleSheet("background: transparent;")
        self._card.setStyleSheet(
            "QWidget {"
            f" background: {theme_manager.c('#0f1317', '#fffaf4')};"
            " border: none;"
            " border-radius: 20px;"
            "}"
        )
        self._input.setStyleSheet(
            "QLineEdit {"
            " background: transparent;"
            " border: none;"
            f" color: {theme_manager.c('#f2ece4', '#1f1914')};"
            " padding: 8px 0 10px 0;"
            " font-size: 18px; font-weight: 700;"
            "}"
        )
        self._underline.setStyleSheet(
            f"background:{theme_manager.c('rgba(255,255,255,0.10)', 'rgba(0,0,0,0.10)')};"
        )
        self._hint.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#8d867d', '#7a7065')};"
            " font-size: 11px; font-weight: 600;"
        )
        self._list.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            "QListWidget::item { background: transparent; border: none; padding: 0px; }"
        )
        self._form_title.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#f2ece4', '#1f1914')}; font-size: 18px; font-weight: 700;"
        )
        self._form_subtitle.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#8f877d', '#756b61')}; font-size: 12px; font-weight: 500;"
        )
        self._form_helper.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#8f877d', '#756b61')}; font-size: 11px; font-weight: 600;"
        )
        for btn in (self._primary_btn, self._secondary_btn):
            btn.setStyleSheet(
                "QPushButton {"
                " background: transparent;"
                " border: none;"
                f" color: {theme_manager.c('#ff885d', '#d86131')};"
                " font-size: 13px; font-weight: 700; padding: 4px 0;"
                "}"
                "QPushButton:hover {"
                f" color: {theme_manager.c('#ff9a74', '#c44f25')};"
                "}"
                "QPushButton:disabled {"
                f" color: {theme_manager.c('#5d5852', '#b2a79c')};"
                "}"
            )
        for row in range(self._list.count()):
            widget = self._list.itemWidget(self._list.item(row))
            if isinstance(widget, (_EntryRow, _GroupHeaderRow)):
                widget.apply_theme()
        for widget in self._form_widgets.values():
            self._style_field_widget(widget)
        for host in self._form_suggestion_hosts.values():
            host.setStyleSheet("background: transparent; border: none;")
        for panel in self._form_suggestion_panels.values():
            panel.setStyleSheet(
                "QWidget {"
                f" background: {theme_manager.c('rgba(255,255,255,0.03)', 'rgba(0,0,0,0.03)')};"
                f" border-top: 1px solid {theme_manager.c('rgba(255,255,255,0.05)', 'rgba(0,0,0,0.05)')};"
                " border-left: none; border-right: none; border-bottom: none;"
                " border-radius: 0px;"
                "}"
            )

    def set_entries(self, entries: list[PaletteEntry]) -> None:
        current_id = None
        item = self._list.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole):
            current_id = item.data(Qt.ItemDataRole.UserRole).id
        self._entries = list(entries)
        self._list.clear()
        if not self._entries:
            empty_item = QListWidgetItem(self._list)
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_item.setSizeHint(QSize(0, 64))
            label = QLabel(_qt_safe_text("No matching results"), self._list)
            label.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#8d867d', '#7a7065')}; font-size: 13px; font-weight: 600;"
            )
            self._list.setItemWidget(empty_item, label)
            return

        last_group = None
        selected_row = -1
        for entry in self._entries:
            if entry.group != last_group:
                last_group = entry.group
                header_item = QListWidgetItem(self._list)
                header_item.setFlags(Qt.ItemFlag.NoItemFlags)
                header_item.setSizeHint(QSize(0, 24))
                self._list.setItemWidget(header_item, _GroupHeaderRow(entry.group, self._list))
            item = QListWidgetItem(self._list)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item.setSizeHint(QSize(0, 64))
            self._list.setItemWidget(item, _EntryRow(entry, self._list))
            if entry.id == current_id:
                selected_row = self._list.row(item)

        if selected_row >= 0:
            self._list.setCurrentRow(selected_row)
        else:
            self._list.select_first_entry()
        self.apply_theme()

    def show_palette(self, initial_query: str = "") -> None:
        self.clear_form()
        self._input.setText(initial_query)
        self.reposition()
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._input.selectAll()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        frame = parent.frameGeometry()
        x = frame.x() + int((frame.width() - self.width()) / 2)
        y = frame.y() + max(36, int((frame.height() - self.height()) / 5))
        self.move(x, y)

    def filtered_entry_ids(self) -> list[str]:
        return [entry.id for entry in self._entries]

    def set_query(self, query: str) -> None:
        self._input.setText(query)

    def query_text(self) -> str:
        return self._input.text()

    def active_form_id(self) -> str | None:
        return self._active_form.id if self._active_form else None

    def form_helper_text(self) -> str:
        return self._form_helper.text()

    def field_suggestion_titles(self, field_key: str) -> list[str]:
        host = self._form_suggestion_hosts.get(field_key)
        layout = self._form_suggestion_layouts.get(field_key)
        if host is None or layout is None or host.isHidden():
            return []
        titles: list[str] = []
        for idx in range(layout.count()):
            item = layout.itemAt(idx)
            widget = item.widget() if item else None
            if isinstance(widget, QPushButton):
                titles.append(_qt_plain_text(widget.text()))
        return titles

    def show_quick_add(self, form: QuickAddForm) -> None:
        self._active_form = form
        self._stack.setCurrentWidget(self._form_page)
        self._input.hide()
        self._underline.hide()
        self._hint.hide()
        self._form_title.setText(_qt_safe_text(form.title))
        self._form_subtitle.setText(_qt_safe_text(form.subtitle))
        self._primary_btn.setText(form.primary_label)
        self._secondary_btn.setText(form.secondary_label)
        self._form_helper.setText(_qt_safe_text(form.helper_text))
        self._rebuild_form_widgets(form)

    def update_form_message(self, text: str, *, is_error: bool = False) -> None:
        colour = "#ff6b35" if is_error else theme_manager.c("#8f877d", "#756b61")
        self._form_helper.setStyleSheet(
            f"background: transparent; color: {colour}; font-size: 11px; font-weight: 600;"
        )
        self._form_helper.setText(_qt_safe_text(text))

    def set_form_pending(self, pending: bool) -> None:
        self._primary_btn.setEnabled(not pending)
        self._secondary_btn.setEnabled(not pending)
        for widget in self._form_widgets.values():
            widget.setEnabled(not pending)

    def clear_form(self) -> None:
        self._active_form = None
        self._form_suggestion_values.clear()
        self._stack.setCurrentWidget(self._list)
        self._input.show()
        self._underline.show()
        self._hint.show()
        self.set_form_pending(False)

    def set_form_values(self, values: dict) -> None:
        for key, value in (values or {}).items():
            widget = self._form_widgets.get(key)
            if widget is None:
                continue
            if isinstance(widget, QLineEdit):
                widget.setText(str(value or ""))
            elif isinstance(widget, QComboBox):
                idx = widget.findData(str(value or ""))
                if idx < 0:
                    idx = widget.findText(str(value or ""))
                if idx >= 0:
                    widget.setCurrentIndex(idx)

    def current_form_values(self) -> dict:
        return self._collect_form_values()

    def set_field_suggestions(self, field_key: str, suggestions: list[dict]) -> None:
        host = self._form_suggestion_hosts.get(field_key)
        layout = self._form_suggestion_layouts.get(field_key)
        if host is None or layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not suggestions:
            host.hide()
            return
        for suggestion in suggestions[:5]:
            title = str(suggestion.get("title") or "").strip()
            if not title:
                continue
            subtitle = str(suggestion.get("subtitle") or "").strip()
            text = title if not subtitle else f"{title} · {subtitle}"
            button = QPushButton(_qt_safe_text(text), host)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton {"
                " background: transparent;"
                " border: none;"
                f" color: {theme_manager.c('#c9c0b6', '#54483c')};"
                " text-align: left;"
                " padding: 7px 2px;"
                " font-size: 11px; font-weight: 600;"
                "}"
                "QPushButton:hover {"
                f" color: {theme_manager.c('#f0e7de', '#241c15')};"
                f" background: {theme_manager.c('rgba(255,255,255,0.03)', 'rgba(0,0,0,0.03)')};"
                "}"
            )
            button.clicked.connect(
                lambda _checked=False, key=field_key, payload=dict(suggestion): self._apply_suggestion(key, payload)
            )
            layout.addWidget(button)
        host.show()

    def eventFilter(self, watched, event) -> bool:
        if watched is self._input and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Down:
                self._list.move_selection(1)
                return True
            if event.key() == Qt.Key.Key_Up:
                self._list.move_selection(-1)
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._list.activate_current_entry()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.reject()
                return True
        if self.isVisible() and event.type() == QEvent.Type.MouseButtonPress:
            popup = QApplication.activePopupWidget()
            if popup is not None:
                return super().eventFilter(watched, event)
            pos = None
            if hasattr(event, "globalPosition"):
                pos = event.globalPosition().toPoint()
            elif hasattr(event, "globalPos"):
                pos = event.globalPos()
            if pos is not None and not self.frameGeometry().contains(pos):
                self.reject()
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if self._active_form is not None and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._emit_form_action("primary")
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QApplication.instance().installEventFilter(self)
        self.reposition()

    def hideEvent(self, event) -> None:
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass
        super().hideEvent(event)

    def _rebuild_form_widgets(self, form: QuickAddForm) -> None:
        self._form_widgets.clear()
        self._form_suggestion_hosts.clear()
        self._form_suggestion_layouts.clear()
        self._form_suggestion_panels.clear()
        self._form_suggestion_values.clear()
        while self._form_fields_layout.count():
            item = self._form_fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if form.mode == "preview":
            for label_text, value in form.preview_rows:
                row = QWidget(self._form_fields_wrap)
                layout = QVBoxLayout(row)
                layout.setContentsMargins(0, 0, 0, 8)
                layout.setSpacing(3)
                label = QLabel(_qt_safe_text(label_text), row)
                label.setStyleSheet(
                    f"background: transparent; color: {theme_manager.c('#8f877d', '#756b61')}; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
                )
                value_lbl = QLabel(_qt_safe_text(value), row)
                value_lbl.setWordWrap(True)
                value_lbl.setStyleSheet(
                    f"background: transparent; color: {theme_manager.c('#f2ece4', '#1f1914')}; font-size: 14px; font-weight: 600;"
                )
                layout.addWidget(label)
                layout.addWidget(value_lbl)
                self._form_fields_layout.addWidget(row)
            return

        for field in form.fields:
            wrapper = QWidget(self._form_fields_wrap)
            layout = QVBoxLayout(wrapper)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            label = QLabel(_qt_safe_text(field.label), wrapper)
            label.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#8f877d', '#756b61')}; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
            )
            layout.addWidget(label)
            editor = self._build_field_editor(field, wrapper)
            self._form_widgets[field.key] = editor
            layout.addWidget(editor)
            line = QWidget(wrapper)
            line.setFixedHeight(1)
            line.setStyleSheet(
                f"background:{theme_manager.c('rgba(255,255,255,0.10)', 'rgba(0,0,0,0.10)')};"
            )
            layout.addWidget(line)
            if field.field_type == "recipe_search":
                suggestion_host = QWidget(wrapper)
                suggestion_host_layout = QVBoxLayout(suggestion_host)
                suggestion_host_layout.setContentsMargins(0, 6, 0, 0)
                suggestion_host_layout.setSpacing(0)
                suggestion_panel = QWidget(suggestion_host)
                suggestion_panel.setObjectName("palette-suggestion-panel")
                suggestion_panel_layout = QVBoxLayout(suggestion_panel)
                suggestion_panel_layout.setContentsMargins(10, 4, 10, 4)
                suggestion_panel_layout.setSpacing(0)
                suggestion_host_layout.addWidget(suggestion_panel)
                suggestion_layout = suggestion_panel_layout
                suggestion_layout.setSpacing(0)
                suggestion_host.hide()
                suggestion_host.setStyleSheet("background: transparent; border: none;")
                self._form_suggestion_hosts[field.key] = suggestion_host
                self._form_suggestion_layouts[field.key] = suggestion_layout
                self._form_suggestion_panels[field.key] = suggestion_panel
                layout.addWidget(suggestion_host)
            self._form_fields_layout.addWidget(wrapper)

        first_widget = next(iter(self._form_widgets.values()), None)
        if first_widget is not None:
            first_widget.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.apply_theme()

    def _build_field_editor(self, field: PaletteField, parent: QWidget):
        if field.field_type == "choice":
            editor = QComboBox(parent)
            editor.setView(QListView(editor))
            for label, value in field.options:
                editor.addItem(label, value)
            idx = editor.findData(field.default)
            if idx >= 0:
                editor.setCurrentIndex(idx)
        else:
            editor = QLineEdit(parent)
            editor.setFrame(False)
            editor.setPlaceholderText(field.placeholder)
            editor.setText(field.default)
            if field.field_type == "number":
                editor.setInputMask("")
        self._style_field_widget(editor)
        if isinstance(editor, QLineEdit):
            editor.textChanged.connect(
                lambda text, key=field.key: self._on_form_field_text_changed(key, text)
            )
            editor.returnPressed.connect(lambda: self._emit_form_action("primary"))
        elif isinstance(editor, QComboBox):
            editor.currentTextChanged.connect(
                lambda text, key=field.key: self._on_form_field_text_changed(key, text)
            )
        return editor

    def _style_field_widget(self, widget: QWidget) -> None:
        if isinstance(widget, QLineEdit):
            widget.setStyleSheet(
                "QLineEdit {"
                " background: transparent;"
                " border: none;"
                f" color: {theme_manager.c('#f2ece4', '#1f1914')};"
                " padding: 6px 0;"
                " font-size: 14px; font-weight: 600;"
                "}"
            )
        elif isinstance(widget, QComboBox):
            widget.setStyleSheet(
                "QComboBox {"
                " background: transparent;"
                " border: none;"
                f" color: {theme_manager.c('#f2ece4', '#1f1914')};"
                " padding: 6px 18px 6px 0;"
                " font-size: 14px; font-weight: 600;"
                "}"
                "QComboBox::drop-down { border: none; width: 16px; }"
                "QComboBox::down-arrow { image: none; border: none; }"
                "QComboBox:on { border: none; }"
                "QAbstractItemView {"
                f" background: {theme_manager.c('#111418', '#fffaf4')};"
                f" color: {theme_manager.c('#f2ece4', '#1f1914')};"
                " border: none;"
                " outline: none;"
                " selection-background-color: transparent;"
                " padding: 4px 0;"
                "}"
                "QAbstractItemView::item {"
                " border: none;"
                " padding: 8px 10px;"
                " margin: 0px;"
                "}"
                "QAbstractItemView::item:selected {"
                f" background: {theme_manager.c('rgba(255,107,53,0.14)', 'rgba(255,107,53,0.10)')};"
                f" color: {theme_manager.c('#ff9a74', '#bf4d22')};"
                " border: none;"
                " outline: none;"
                "}"
                "QAbstractItemView::item:hover {"
                f" background: {theme_manager.c('rgba(255,255,255,0.04)', 'rgba(0,0,0,0.04)')};"
                "}"
            )

    def _collect_form_values(self) -> dict:
        if self._active_form is None:
            return {}
        values: dict[str, str] = {}
        for key, widget in self._form_widgets.items():
            if isinstance(widget, QLineEdit):
                values[key] = widget.text().strip()
            elif isinstance(widget, QComboBox):
                values[key] = str(widget.currentData() or widget.currentText() or "").strip()
        for key, suggestion in self._form_suggestion_values.items():
            values[f"{key}_selected_id"] = suggestion.get("id")
            values[f"{key}_selected_title"] = suggestion.get("title")
        if self._active_form.preview_payload:
            values["_preview_payload"] = dict(self._active_form.preview_payload)
        return values

    def _emit_form_action(self, action: str) -> None:
        if self._active_form is None:
            return
        self.form_action_requested.emit(self._active_form.id, action, self._collect_form_values())

    def _on_form_field_text_changed(self, field_key: str, value: str) -> None:
        current = self._form_suggestion_values.get(field_key)
        if current is not None and str(current.get("title") or "") != str(value or "").strip():
            self._form_suggestion_values.pop(field_key, None)
        if self._active_form is None:
            return
        self.form_field_changed.emit(self._active_form.id, field_key, str(value or ""))

    def _apply_suggestion(self, field_key: str, suggestion: dict) -> None:
        widget = self._form_widgets.get(field_key)
        title = str(suggestion.get("title") or "").strip()
        if isinstance(widget, QLineEdit):
            widget.setText(title)
        self._form_suggestion_values[field_key] = {
            "id": suggestion.get("id"),
            "title": title,
        }
        self.set_field_suggestions(field_key, [])
