import json
import tempfile
from utils.theme import manager as theme_manager
from utils.themed_dialog import ThemedMessageBox
from datetime import datetime, timedelta, date

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QScrollArea, QSizePolicy, QDialog, QLineEdit, QComboBox,
    QStackedWidget, QApplication,
)
from PySide6.QtCore import Qt, QSize, QPoint, QMimeData, QTimer
from PySide6.QtGui import QDrag, QPixmap, QPainter, QBrush, QColor

from api.claude_ai import ClaudeAI
from models.database import Database
from utils.data_service import get_db
from utils.grocery_consolidation import consolidate_rows
from utils.meal_optimizer import optimize_week
from utils.platform_ops import open_path_in_default_app
from utils.planner_intelligence import (
    PLANNING_MODES,
    current_editor_label,
    dump_slot_metadata,
    get_planning_mode,
    load_slot_metadata,
    load_templates,
    pantry_expiry_items,
    planning_mode_label,
    resolve_recipe_by_title,
    save_template,
    slot_badges,
)
from utils.workers import run_async
from widgets.page_scaffold import PageScaffold, PageToolbar, StatusBanner
from widgets.primary_button import PrimaryButton

_claude = ClaudeAI()

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MEALS = [
    ("breakfast", "Breakfast", "fa5s.egg"),
    ("lunch",     "Lunch",     "fa5s.utensils"),
    ("dinner",    "Dinner",    "fa5s.concierge-bell"),
    ("snack",     "Snack",     "fa5s.apple-alt"),
]

# Keep meal chrome restrained; meal type remains clear through text and layout.
MEAL_BAND = {
    "breakfast": "#ff6b35",
    "lunch":     "#ff6b35",
    "dinner":    "#ff6b35",
    "snack":     "#ff6b35",
}

# ICS event start/end times per meal
MEAL_TIMES = {
    "breakfast": ("080000", "090000"),
    "lunch":     ("120000", "130000"),
    "dinner":    ("180000", "190000"),
    "snack":     ("153000", "160000"),
}

# Tags that surface first in the picker for each meal type
_MEAL_PRIORITY_TAGS = {
    "breakfast": ["Breakfast"],
    "lunch":     ["Lunch"],
    "dinner":    ["Dinner", "Comfort Food", "Date Night"],
    "snack":     ["Snack"],
}


def _week_start_from(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ── Meal picker dialog ────────────────────────────────────────────────────────

class MealPickerDialog(QDialog):
    def __init__(self, day: str, meal_type: str, current_name: str, db, parent=None):
        super().__init__(parent)
        # Remove native OS chrome so the window blends into the app
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(500)
        self.setMinimumHeight(560)
        self._db = db
        self._meal_type = meal_type
        self._result_name: str | None = None
        self._result_recipe_id: int | None = None
        self._should_clear = False
        self._drag_pos: QPoint | None = None
        self._selected_item: QWidget | None = None
        self._current_name = current_name  # used to pre-select matching recipe
        self._build_ui(day, meal_type, current_name)

    # ── Window dragging ───────────────────────────────────────────────────────

    def _on_title_bar_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _on_title_bar_move(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def _on_title_bar_release(self, _event):
        self._drag_pos = None

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self, day: str, meal_type: str, current_name: str):
        # Transparent outer layout — the panel widget provides the background
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)  # shadow margin
        outer.setSpacing(0)

        panel = QWidget()
        panel.setObjectName("meal-picker-panel")
        panel.setStyleSheet(
            "QWidget#meal-picker-panel {"
            f" background-color: {theme_manager.c('#0e0e0e', '#ffffff')};"
            " border-radius: 14px;"
            f" border: 1px solid {theme_manager.c('#252525', '#e0e0e0')};"
            "}"
        )
        outer.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Custom title bar ─────────────────────────────────────────────────
        band_colour = MEAL_BAND.get(meal_type, "#ff6b35")
        meal_icon_name = next((m[2] for m in MEALS if m[0] == meal_type), "fa5s.utensils")

        title_bar = QWidget()
        title_bar.setFixedHeight(52)
        title_bar.setStyleSheet(
            f"background-color: {theme_manager.c('#0a0a0a', '#f5f5f5')}; border-radius: 14px 14px 0 0;"
            f" border-bottom: 1px solid {theme_manager.c('#1a1a1a', '#e0e0e0')};"
        )
        title_bar.mousePressEvent   = self._on_title_bar_press
        title_bar.mouseMoveEvent    = self._on_title_bar_move
        title_bar.mouseReleaseEvent = self._on_title_bar_release
        title_bar.setCursor(Qt.CursorShape.SizeAllCursor)

        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(16, 0, 12, 0)
        tb.setSpacing(10)

        meal_ic = QLabel()
        meal_ic.setPixmap(
            qta.icon(meal_icon_name, color=band_colour).pixmap(QSize(14, 14))
        )
        meal_ic.setStyleSheet("background: transparent;")

        title_lbl = QLabel(f"{day}  ·  {meal_type.capitalize()}")
        title_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#cccccc', '#333333')};"
            " font-size: 13px; font-weight: 600;"
        )

        badge = QLabel(meal_type.upper())
        badge.setStyleSheet(
            f"background-color: {theme_manager.c('rgba(255,255,255,0.03)', 'rgba(0,0,0,0.03)')};"
            f"color: {theme_manager.c('#a39c93', '#7c7368')};"
            f"border: 1px solid {theme_manager.c('#2a3037', '#ddd1c4')};"
            " border-radius: 10px; padding: 2px 8px; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;"
        )

        close_btn = QPushButton()
        close_btn.setObjectName("ghost-btn")
        close_btn.setIcon(qta.icon("fa5s.times", color="#555555"))
        close_btn.setIconSize(QSize(13, 13))
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close")
        close_btn.clicked.connect(self.reject)
        # Hover: brighten icon
        close_btn.enterEvent = lambda _: close_btn.setIcon(
            qta.icon("fa5s.times", color="#e0e0e0")
        )
        close_btn.leaveEvent = lambda _: close_btn.setIcon(
            qta.icon("fa5s.times", color="#555555")
        )

        tb.addWidget(meal_ic)
        tb.addSpacing(4)
        tb.addWidget(title_lbl)
        tb.addWidget(badge)
        tb.addStretch()
        tb.addWidget(close_btn)
        layout.addWidget(title_bar)

        # ── Content ──────────────────────────────────────────────────────────
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(22, 18, 22, 22)
        cl.setSpacing(14)

        subheading = QLabel("SELECT A SAVED RECIPE")
        subheading.setStyleSheet(
            f"font-size: 10px; color: {theme_manager.c('#888888', '#555555')}; letter-spacing: 1.2px;"
            " font-weight: 700; background: transparent;"
        )
        cl.addWidget(subheading)

        # Create ok_btn BEFORE _load_recipes so pre-selection can enable it
        ok_btn = PrimaryButton("  Set Meal")
        ok_btn.setFixedHeight(40)
        ok_btn.clicked.connect(self._on_ok)
        self._ok_btn = ok_btn
        self._ok_btn.setEnabled(False)  # disabled until a recipe is selected

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._recipes_layout = QVBoxLayout(container)
        self._recipes_layout.setContentsMargins(0, 0, 4, 0)
        self._recipes_layout.setSpacing(4)
        scroll.setWidget(container)
        cl.addWidget(scroll, 1)

        self._load_recipes()

        # Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {theme_manager.c('#1a1a1a', '#cccccc')};")
        cl.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        if current_name:
            clear_btn = QPushButton("Clear meal")
            clear_btn.setObjectName("ghost-btn")
            clear_btn.setFixedHeight(40)
            clear_btn.clicked.connect(self._on_clear)
            btn_row.addWidget(clear_btn)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("ghost-btn")
        cancel_btn.setFixedHeight(40)
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        cl.addLayout(btn_row)

        layout.addWidget(content)

    def _load_recipes(self):
        try:
            all_rows = self._db.get_saved_recipes()
        except Exception:
            all_rows = []

        # Filter to only recipes tagged for this meal type
        meal_tag = self._meal_type.capitalize()  # "Breakfast", "Lunch", "Dinner", "Snack"
        rows = []
        for row in all_rows:
            try:
                tags = json.loads(row["data_json"] or "{}").get("tags", [])
                if meal_tag in tags:
                    rows.append(row)
            except Exception:
                pass

        priority_tags = _MEAL_PRIORITY_TAGS.get(self._meal_type, [])

        def sort_key(row):
            try:
                tags = json.loads(row["data_json"] or "{}").get("tags", [])
                for i, pt in enumerate(priority_tags):
                    if pt in tags:
                        return (0, i, row["title"].lower())
                return (1, 0, row["title"].lower())
            except Exception:
                return (1, 0, row["title"].lower())

        for recipe_row in sorted(rows, key=sort_key):
            self._add_recipe_row(recipe_row)

        if not rows:
            msg = (
                f"No {meal_tag} recipes yet.\n"
                f"Tag a recipe with '{meal_tag}' in the Recipes tab to see it here."
                if all_rows else
                "No saved recipes yet — head to the Recipes tab to add some!"
            )
            empty = QLabel(msg)
            empty.setStyleSheet(
                f"color: {theme_manager.c('#888888', '#666666')}; font-size: 12px;"
                " background: transparent;"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self._recipes_layout.addWidget(empty)

        self._recipes_layout.addStretch()

    def _add_recipe_row(self, recipe_row):
        try:
            data = json.loads(recipe_row["data_json"] or "{}")
            tags = data.get("tags", [])
            icon_name = data.get("icon", "fa5s.utensils")
            colour = theme_manager.c("#f1ece5", "#2d241c")
        except Exception:
            tags, icon_name, colour = [], "fa5s.utensils", theme_manager.c("#f1ece5", "#2d241c")

        item = QWidget()
        item.setObjectName("shopping-item")
        item.setFixedHeight(60)
        item.setCursor(Qt.CursorShape.PointingHandCursor)

        row_layout = QHBoxLayout(item)
        row_layout.setContentsMargins(14, 0, 14, 0)
        row_layout.setSpacing(12)

        icon_lbl = QLabel()
        try:
            icon_lbl.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(20, 20)))
        except Exception:
            icon_lbl.setPixmap(qta.icon("fa5s.utensils", color="#ff6b35").pixmap(QSize(20, 20)))
        icon_lbl.setStyleSheet("background: transparent;")
        icon_lbl.setFixedSize(28, 28)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        title = recipe_row["title"]
        title_lbl = QLabel(title[:52] + ("…" if len(title) > 52 else ""))
        title_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#e0e0e0', '#222222')};"
            " font-size: 13px; font-weight: 500;"
        )
        text_col.addWidget(title_lbl)

        priority_tags = _MEAL_PRIORITY_TAGS.get(self._meal_type, [])
        display_tags = (
            [t for t in tags if t in priority_tags]
            + [t for t in tags if t not in priority_tags]
        )
        if display_tags:
            tags_lbl = QLabel("  ·  ".join(display_tags[:4]))
            tags_lbl.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#666666', '#999999')}; font-size: 10px;"
            )
            text_col.addWidget(tags_lbl)

        row_layout.addWidget(icon_lbl)
        row_layout.addLayout(text_col)
        row_layout.addStretch()

        recipe_id = recipe_row["id"]
        recipe_title = recipe_row["title"]
        item.mousePressEvent = lambda _e, t=recipe_title, rid=recipe_id, w=item: self._select_recipe(t, rid, w)
        self._recipes_layout.addWidget(item)

        # Pre-select if this recipe matches the current slot
        if recipe_title.lower() == self._current_name.lower():
            self._select_recipe(recipe_title, recipe_id, item)

    def _select_recipe(self, title: str, recipe_id: int, item_widget: QWidget):
        # Deselect previous
        if hasattr(self, "_selected_item") and self._selected_item:
            self._selected_item.setStyleSheet("QWidget#shopping-item { background: transparent; }")
        self._selected_item = item_widget
        item_widget.setStyleSheet(
            f"QWidget#shopping-item {{ background-color: {theme_manager.c(f'rgba(255,107,53,0.12)', f'rgba(255,107,53,0.10)')};"
            f" border-radius: 8px; border: 1px solid rgba(255,107,53,0.28); }}"
        )
        self._result_name     = title
        self._result_recipe_id = recipe_id
        self._ok_btn.setEnabled(True)

    def _on_clear(self):
        self._should_clear = True
        self.accept()

    def _on_ok(self):
        if not self._result_recipe_id:
            return  # no recipe selected — do nothing
        self.accept()

    def get_result(self):
        return self._result_name, self._result_recipe_id, self._should_clear


# ── Calendar cell widgets ─────────────────────────────────────────────────────

class MealRowLabel(QWidget):
    """Left-side label for a meal row — coloured icon + meal type name."""

    def __init__(self, meal_type: str, label: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setFixedWidth(88)
        self.setStyleSheet("background: transparent; border: none;")

        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(6)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ic = QLabel()
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setPixmap(qta.icon(icon_name, color=theme_manager.c("#8d867d", "#756d63")).pixmap(QSize(16, 16)))
        ic.setStyleSheet("background: transparent;")

        lbl = QLabel(label.upper())
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#8d867d', '#756d63')};"
            " font-size: 10px; font-weight: 700; letter-spacing: 1px; border: none;"
        )

        vl.addStretch()
        vl.addWidget(ic)
        vl.addSpacing(4)
        vl.addWidget(lbl)
        vl.addStretch()


class DayHeader(QWidget):
    """Column header: day abbreviation, large date number, month."""

    def __init__(self, col_date: date, is_today: bool, parent=None):
        super().__init__(parent)
        self.setFixedHeight(74)

        if is_today:
            self.setStyleSheet(
                "background-color: rgba(255,107,53,0.09);"
                " border-radius: 10px;"
                " border: 1px solid rgba(255,107,53,0.22);"
            )
        else:
            self.setStyleSheet(
                f"background-color: {theme_manager.c('#0d0d0d', '#f0f0f0')};"
                " border-radius: 10px;"
                f" border: 1px solid {theme_manager.c('#1a1a1a', '#cccccc')};"
            )

        vl = QVBoxLayout(self)
        vl.setContentsMargins(6, 8, 6, 8)
        vl.setSpacing(1)

        day_lbl = QLabel(col_date.strftime("%a").upper())
        day_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        day_lbl.setStyleSheet(
            "background: transparent; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 1.2px; color: {theme_manager.c('#8d867d', '#756d63') if is_today else theme_manager.c('#555555', '#444444')};"
            " border: none;"
        )

        num_lbl = QLabel(str(col_date.day))
        num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_lbl.setStyleSheet(
            "background: transparent; font-size: 26px; font-weight: 800;"
            f" color: {theme_manager.c('#f1ece5', '#201913') if is_today else theme_manager.c('#e8e8e8', '#111111')}; border: none;"
        )

        month_lbl = QLabel(col_date.strftime("%b").upper())
        month_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        month_lbl.setStyleSheet(
            "background: transparent; font-size: 9px; letter-spacing: 0.8px;"
            f" color: {theme_manager.c('#a39c93', '#7c7368') if is_today else theme_manager.c('#777777', '#444444')}; border: none;"
        )

        vl.addWidget(day_lbl)
        vl.addWidget(num_lbl)
        vl.addWidget(month_lbl)


class MealSlot(QWidget):
    """A single meal cell — colour-coded by meal type, shows name prominently."""

    def __init__(self, day: str, meal_type: str, on_click, on_open_recipe=None,
                 on_drop=None, parent=None):
        super().__init__(parent)
        self._day = day
        self._meal_type = meal_type
        self._on_click = on_click
        self._on_open_recipe = on_open_recipe
        self._on_drop = on_drop
        self._meal_name = ""
        self._recipe_id: int | None = None
        self._metadata: dict = {}
        self._highlighted = False
        self._drag_start_pos: QPoint | None = None
        self.setObjectName("meal-slot")
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)
        self._build()

    def _build(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Left colour accent strip
        self._strip = QWidget()
        self._strip.setFixedWidth(5)
        self._strip.setStyleSheet(f"background-color: {theme_manager.c('#1e1e1e', '#d8d8d8')};")
        outer.addWidget(self._strip)

        # Content
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(12, 12, 12, 10)
        cl.setSpacing(6)

        meal_icon_name = next((m[2] for m in MEALS if m[0] == self._meal_type), "fa5s.utensils")

        type_row = QHBoxLayout()
        type_row.setSpacing(6)
        ic = QLabel()
        self._meal_icon_lbl = ic
        ic.setPixmap(qta.icon(meal_icon_name, color=theme_manager.c("#8d867d", "#756d63")).pixmap(QSize(13, 13)))
        ic.setStyleSheet("background: transparent;")
        type_lbl = QLabel(self._meal_type.capitalize())
        self._type_lbl = type_lbl
        type_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#8d867d', '#756d63')};"
            " font-size: 11px; font-weight: 700; letter-spacing: 0.4px;"
        )

        self._edit_btn = QPushButton()
        self._edit_btn.setObjectName("ghost-btn")
        self._edit_btn.setIcon(qta.icon("fa5s.pen", color="#555555"))
        self._edit_btn.setIconSize(QSize(10, 10))
        self._edit_btn.setFixedSize(24, 24)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setToolTip("Edit meal")
        self._edit_btn.clicked.connect(
            lambda: self._on_click(self._day, self._meal_type, self._meal_name)
        )

        type_row.addWidget(ic)
        type_row.addWidget(type_lbl)
        type_row.addStretch()
        type_row.addWidget(self._edit_btn)
        cl.addLayout(type_row)

        self._name_lbl = QLabel("Add meal")
        self._name_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#555555', '#aaaaaa')}; font-size: 14px;"
        )
        self._name_lbl.setWordWrap(True)
        cl.addWidget(self._name_lbl)

        self._meta_wrap = QWidget()
        self._meta_wrap.setStyleSheet("background: transparent;")
        self._meta_row = QHBoxLayout(self._meta_wrap)
        self._meta_row.setContentsMargins(0, 0, 0, 0)
        self._meta_row.setSpacing(6)
        self._meta_wrap.setVisible(False)
        cl.addWidget(self._meta_wrap)
        cl.addStretch()

        # Recipe button — only visible when a linked recipe exists
        self._recipe_btn = QPushButton("  View Recipe →")
        self._recipe_btn.setIcon(qta.icon("fa5s.book-open", color=theme_manager.c("#8d867d", "#756d63")))
        self._recipe_btn.setIconSize(QSize(12, 12))
        self._recipe_btn.setFixedHeight(30)
        self._recipe_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style_recipe_button()
        self._recipe_btn.setVisible(False)
        self._recipe_btn.clicked.connect(self._open_recipe)
        cl.addWidget(self._recipe_btn)

        outer.addWidget(content, 1)
        self._content_widget = content

    def _band_rgb(self) -> str:
        return "255,107,53"

    def _style_recipe_button(self) -> None:
        self._recipe_btn.setIcon(qta.icon("fa5s.book-open", color=theme_manager.c("#8d867d", "#756d63")))
        self._recipe_btn.setStyleSheet(
            "QPushButton {"
            f" background-color: {theme_manager.c('rgba(255,255,255,0.03)', 'rgba(255,107,53,0.05)')};"
            f" color: {theme_manager.c('#8d867d', '#756d63')};"
            f" border: 1px solid {theme_manager.c('#2a3037', '#ddd1c4')};"
            " border-radius: 6px; font-size: 12px; font-weight: 600; padding: 0 10px; text-align: left; }"
            "QPushButton:hover {"
            f" background-color: {theme_manager.c('#181d22', '#efe2d4')};"
            " border-color: rgba(255,107,53,0.22);"
            "}"
        )

    def _open_recipe(self):
        if self._on_open_recipe and self._recipe_id is not None:
            self._on_open_recipe(self._recipe_id)

    def set_meal(self, name: str, colour: str = "", recipe_id: int | None = None, metadata: dict | None = None):
        self._meal_name = name
        self._recipe_id = recipe_id
        self._metadata = dict(metadata or {})
        if name:
            self._name_lbl.setText(name)
            self._name_lbl.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#e8e8e8', '#1a1a1a')};"
                " font-size: 14px; font-weight: 600;"
            )
            strip_c = "#ff6b35"
            self._strip.setStyleSheet(f"background-color: {strip_c};")
            self._recipe_btn.setVisible(recipe_id is not None)
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self._name_lbl.setText("Add meal")
            self._metadata = {}
            self._name_lbl.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#444444', '#bbbbbb')};"
                " font-size: 14px;"
            )
            self._strip.setStyleSheet(
                f"background-color: {theme_manager.c('#1a1a1a', '#d5d5d5')};"
            )
            self._recipe_btn.setVisible(False)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_badges()
        self._apply_highlight_style()

    def current_name(self) -> str:
        return self._meal_name

    def current_metadata(self) -> dict:
        return dict(self._metadata)

    def apply_theme(self) -> None:
        meal_icon_name = next((m[2] for m in MEALS if m[0] == self._meal_type), "fa5s.utensils")
        self._style_recipe_button()
        self._edit_btn.setIcon(qta.icon("fa5s.pen", color=theme_manager.c("#555555", "#888888")))
        self.set_meal(self._meal_name, recipe_id=self._recipe_id, metadata=self._metadata)
        self._meal_icon_lbl.setPixmap(
            qta.icon(meal_icon_name, color=theme_manager.c("#8d867d", "#756d63")).pixmap(QSize(13, 13))
        )
        self._type_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#8d867d', '#756d63')};"
            " font-size: 11px; font-weight: 700; letter-spacing: 0.4px;"
        )

    def highlight_temporarily(self, duration_ms: int = 1800) -> None:
        self._highlighted = True
        self._apply_highlight_style()
        QTimer.singleShot(duration_ms, self._clear_highlight)

    def _clear_highlight(self):
        self._highlighted = False
        self._apply_highlight_style()

    def _apply_highlight_style(self):
        self._content_widget.setStyleSheet(
            (
                f"background:{theme_manager.c('rgba(255,107,53,0.08)', 'rgba(255,107,53,0.06)')};"
                f"border:1px solid {theme_manager.c('rgba(255,107,53,0.24)', 'rgba(255,107,53,0.20)')};"
                "border-radius:10px;"
            ) if self._highlighted else "background: transparent; border: none;"
        )

    def _refresh_badges(self):
        while self._meta_row.count():
            item = self._meta_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        badges = slot_badges(self._metadata)
        self._meta_wrap.setVisible(bool(badges))
        for icon_name, text, colour in badges:
            self._meta_row.addWidget(_meta_chip(icon_name, text, colour))
        self._meta_row.addStretch()

    # ── Mouse / drag ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            if not self._meal_name:
                self._on_click(self._day, self._meal_type, self._meal_name)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or not self._meal_name:
            return
        if self._drag_start_pos is None:
            return
        dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
        if dist < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        payload = {
            "day": self._day,
            "meal_type": self._meal_type,
            "meal_name": self._meal_name,
            "recipe_id": self._recipe_id,
            "metadata": self._metadata,
        }
        mime.setData("application/x-dishy-slot", json.dumps(payload).encode("utf-8"))
        rid = str(self._recipe_id) if self._recipe_id is not None else ""
        mime.setText(f"{self._day}|{self._meal_type}|{self._meal_name}|{rid}")
        drag.setMimeData(mime)

        # Build a drag ghost pill
        band_c = MEAL_BAND.get(self._meal_type, "#ff6b35")
        pix = QPixmap(220, 38)
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(band_c)
        c.setAlpha(210)
        p.setBrush(QBrush(c))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, 220, 38, 8, 8)
        p.setPen(QColor("#ffffff"))
        f = p.font()
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        display = self._meal_name[:28] + ("…" if len(self._meal_name) > 28 else "")
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, display)
        p.end()
        drag.setPixmap(pix)
        drag.setHotSpot(QPoint(110, 19))
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start_pos = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.source() is not self:
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText() and event.source() is not self:
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasText() or event.source() is self:
            return
        src_meta = {}
        if event.mimeData().hasFormat("application/x-dishy-slot"):
            try:
                payload = json.loads(bytes(event.mimeData().data("application/x-dishy-slot")).decode("utf-8"))
                src_day = str(payload.get("day") or "")
                src_meal_type = str(payload.get("meal_type") or "")
                src_meal_name = str(payload.get("meal_name") or "")
                src_recipe_id = int(payload.get("recipe_id")) if payload.get("recipe_id") is not None else None
                src_meta = dict(payload.get("metadata") or {})
            except Exception:
                return
        else:
            parts = event.mimeData().text().split("|")
            if len(parts) != 4:
                return
            src_day, src_meal_type, src_meal_name, src_rid = parts
            src_recipe_id = int(src_rid) if src_rid else None
        if self._on_drop:
            self._on_drop(
                src_day, src_meal_type, src_meal_name, src_recipe_id, src_meta,
                self._day, self._meal_type, self._meal_name, self._recipe_id, self._metadata,
            )
        event.acceptProposedAction()


def _meta_chip(icon_name: str, text: str, colour: str = "#4caf8a") -> QWidget:
    chip = QWidget()
    chip.setStyleSheet(
        f"background: {theme_manager.c('rgba(255,255,255,0.03)', 'rgba(0,0,0,0.03)')};"
        f" border: 1px solid {theme_manager.c('#2a3037', '#ddd1c4')};"
        " border-radius: 12px;"
    )
    hl = QHBoxLayout(chip)
    hl.setContentsMargins(8, 4, 10, 4)
    hl.setSpacing(5)
    ic = QLabel()
    ic.setPixmap(qta.icon(icon_name, color=theme_manager.c("#8d867d", "#756d63")).pixmap(QSize(11, 11)))
    ic.setStyleSheet("background: transparent;")
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background: transparent; color: {theme_manager.c('#a39c93', '#555555')};"
        " font-size: 11px; font-weight: 600;"
    )
    hl.addWidget(ic)
    hl.addWidget(lbl)
    return chip


# ── Main view ─────────────────────────────────────────────────────────────────

class MealPlannerView(QWidget):
    def __init__(self, navigate_to=None, shopping_view=None, db: Database | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("view-container")
        self._navigate_to = navigate_to or (lambda i: None)
        self._shopping_view = shopping_view
        self._db = db or get_db()
        self._week_start = _week_start_from(datetime.now().date())
        self._slots: dict[tuple, MealSlot] = {}
        self._ask_dishy_fn = None       # set by MainWindow via set_ask_dishy()
        self._nutrition_refresh_fn = None  # set by MainWindow via set_nutrition_refresh()
        self._nutrition_sync_fn = None     # kept for API compat; no longer used
        self._sync_fn = None               # set by MainWindow to trigger cloud sync
        self._planning_mode = get_planning_mode(self._db)
        self._mode_combo: QComboBox | None = None
        self._template_name_input: QLineEdit | None = None
        self._template_combo: QComboBox | None = None
        self._planner_summary_lbl: StatusBanner | None = None
        self._planner_toolbar: PageToolbar | None = None
        self._build_ui()

    def set_ask_dishy(self, fn):
        """Called by MainWindow to wire the per-tab Ask Dishy button."""
        self._ask_dishy_fn = fn

    def set_nutrition_refresh(self, fn):
        """Called by MainWindow so the planner can trigger a nutrition refresh."""
        self._nutrition_refresh_fn = fn

    def set_nutrition_sync(self, fn):
        """Kept for API compatibility; no longer used."""
        self._nutrition_sync_fn = fn

    def set_sync_fn(self, fn):
        """Called by MainWindow to trigger cloud sync after data mutations."""
        self._sync_fn = fn

    def refresh(self):
        """Reload the current week's data — called after Dishy updates the planner."""
        # Clear all slots to empty state first so removed meals don't linger
        for slot in self._slots.values():
            slot.set_meal("", "")
        self._load_week_data()
        self._refresh_planner_controls()

    def apply_theme(self, _mode=None):
        for slot in self._slots.values():
            slot.apply_theme()
        self._refresh_planner_controls()

    def show_root_page(self):
        """Return Meal Planner to its main weekly planner page."""
        self._page_stack.setCurrentIndex(0)

    def activate_planner(self) -> None:
        """Palette-safe entrypoint for the current week's planner."""
        self.show_root_page()
        self._go_to_today()

    def current_week_start_iso(self) -> str:
        return self._week_start.isoformat()

    def open_meal_slot(self, day: str, meal_type: str) -> bool:
        self.show_root_page()
        slot = self._slots.get((day, meal_type))
        if slot is None:
            return False
        slot.highlight_temporarily()
        return True

    def save_meal_slot_from_palette(self, day: str, meal_type: str, recipe_id: int) -> bool:
        slot = self._slots.get((day, meal_type))
        recipe_row = self._get_recipe_row(recipe_id)
        if slot is None or recipe_row is None:
            return False
        metadata = self._build_slot_metadata(recipe_row, meal_type)
        self._db.set_meal_slot(
            self._week_start.isoformat(),
            day,
            meal_type,
            custom_name=str(recipe_row["title"] or ""),
            recipe_id=recipe_id,
            notes=dump_slot_metadata(metadata),
        )
        colour = ""
        try:
            colour = json.loads(recipe_row["data_json"] or "{}").get("colour", "")
        except Exception:
            pass
        slot.set_meal(str(recipe_row["title"] or ""), colour, recipe_id=recipe_id, metadata=metadata)
        slot.highlight_temporarily()
        if self._nutrition_refresh_fn:
            self._nutrition_refresh_fn()
        if self._sync_fn:
            self._sync_fn()
        return True

    def _on_mode_changed(self, *_args):
        if not self._mode_combo:
            return
        self._set_planning_mode(str(self._mode_combo.currentData() or "balanced"))

    def _set_planning_mode(self, mode: str):
        self._planning_mode = str(mode or "balanced")
        self._db.set_setting("meal_planning_mode", self._planning_mode)
        if self._mode_combo:
            idx = self._mode_combo.findData(self._planning_mode)
            if idx >= 0:
                self._mode_combo.blockSignals(True)
                self._mode_combo.setCurrentIndex(idx)
                self._mode_combo.blockSignals(False)
        self._refresh_planner_controls()
        if self._sync_fn:
            self._sync_fn()

    def _refresh_planner_controls(self):
        templates = load_templates(self._db)
        if self._template_combo:
            current_name = self._template_combo.currentData()
            self._template_combo.blockSignals(True)
            self._template_combo.clear()
            self._template_combo.addItem("Choose template", "")
            for tpl in templates:
                self._template_combo.addItem(tpl["name"], tpl["name"])
            idx = self._template_combo.findData(current_name)
            self._template_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self._template_combo.blockSignals(False)

        if self._planner_summary_lbl:
            self._planner_summary_lbl.set_text("")
        if self._planner_toolbar:
            mode_items = []
            for key, label, _desc in PLANNING_MODES:
                mode_items.append(
                    {
                        "label": f"Planning mode: {label}",
                        "handler": lambda checked=False, k=key: self._set_planning_mode(k),
                        "enabled": key != self._planning_mode,
                    }
                )
            template_items = [
                {
                    "label": tpl["name"],
                    "handler": lambda checked=False, name=tpl["name"]: self._apply_template_by_name(name),
                }
                for tpl in templates
            ]
            self._planner_toolbar.set_overflow_actions(
                [
                    {"label": "Generate shopping list", "handler": self._generate_shopping_list},
                    {"label": "Optimize week", "handler": self._auto_optimize_week},
                    {"label": "Save template", "handler": self._save_current_template},
                    {"label": "Pantry rescue", "handler": self._run_pantry_rescue},
                    {"label": "Export to calendar", "handler": self._export_to_calendar},
                    {"label": "Ask Dishy", "handler": self._ask_dishy_planner},
                    {"label": "Modes", "items": mode_items},
                    {"label": "Apply template", "items": template_items, "enabled": bool(template_items)},
                ]
            )

    def _current_week_rows(self) -> list[dict]:
        try:
            return [dict(r) for r in self._db.get_meal_plan(self._week_start.isoformat())]
        except Exception:
            return []

    def _save_current_template(self):
        rows = self._current_week_rows()
        if not rows:
            ThemedMessageBox.information(self, "Save Template", "Plan a few meals first, then save the week as a reusable template.")
            return
        name = self._template_name_input.text().strip() if self._template_name_input else ""
        templates = save_template(self._db, name, rows, mode=self._planning_mode)
        if self._template_name_input:
            self._template_name_input.clear()
        self._refresh_planner_controls()
        if self._sync_fn:
            self._sync_fn()
        latest = templates[0]["name"] if templates else "Template"
        ThemedMessageBox.information(self, "Template saved", f"Saved '{latest}' for quick re-use in the Meal Planner.")

    def _apply_selected_template(self):
        if not self._template_combo:
            return
        selected = str(self._template_combo.currentData() or "").strip()
        self._apply_template_by_name(selected)

    def _apply_template_by_name(self, selected: str):
        templates = load_templates(self._db)
        template = next((tpl for tpl in templates if tpl.get("name") == selected), None)
        if not template:
            ThemedMessageBox.information(self, "Apply Template", "Choose a saved template first.")
            return
        applied = 0
        missing: list[str] = []
        for slot in template.get("slots", []):
            row = resolve_recipe_by_title(self._db, slot.get("recipe_title", ""))
            if not row:
                missing.append(str(slot.get("recipe_title") or ""))
                continue
            meta = dict(slot.get("metadata") or {})
            meta["template_name"] = template.get("name", "")
            meta.setdefault("planning_mode", template.get("mode") or self._planning_mode)
            meta.setdefault("owner_label", current_editor_label(self._db))
            self._db.set_meal_slot(
                self._week_start.isoformat(),
                str(slot.get("day") or ""),
                str(slot.get("meal_type") or ""),
                custom_name=str(row.get("title") or ""),
                recipe_id=int(row.get("id") or 0) or None,
                notes=dump_slot_metadata(meta),
            )
            applied += 1
        self.refresh()
        if self._nutrition_refresh_fn:
            self._nutrition_refresh_fn()
        if self._sync_fn:
            self._sync_fn()
        msg = f"Applied {applied} slot(s) from '{template.get('name', 'template')}'."
        if missing:
            msg += "\n\nSkipped missing recipes: " + ", ".join(missing[:4])
        ThemedMessageBox.information(self, "Template applied", msg)

    def _run_pantry_rescue(self):
        try:
            result = optimize_week(
                self._db,
                self._week_start.isoformat(),
                refill_all=False,
                planning_mode="reduce_waste",
                use_leftovers=True,
            )
        except Exception as exc:
            ThemedMessageBox.warning(self, "Pantry Rescue failed", str(exc)[:320])
            return
        self.refresh()
        if self._nutrition_refresh_fn:
            self._nutrition_refresh_fn()
        if self._sync_fn:
            self._sync_fn()
        ThemedMessageBox.information(
            self,
            "Pantry Rescue complete",
            f"Updated {int(result.get('assigned', 0) or 0)} slot(s) using pantry-first, expiry-aware planning.",
        )

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._page_stack = QStackedWidget()
        root.addWidget(self._page_stack)

        # ── Page 0: planner grid ─────────────────────────────────────────────
        planner_page = QWidget()
        planner_page.setObjectName("view-container")
        planner_page.setMinimumWidth(500)  # keeps nav bar readable at small window widths

        outer = QVBoxLayout(planner_page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._planner_scaffold = PageScaffold(
            "Meal Planner",
            "Build the week one slot at a time or let Dishy fill the gaps. Today's meals flow straight into Nutrition.",
            eyebrow="Food Operations",
            parent=planner_page,
            quiet_header=True,
        )
        outer.addWidget(self._planner_scaffold)

        # ── Week navigation bar ──────────────────────────────────────────────
        nav = QHBoxLayout()
        nav.setSpacing(8)

        prev_btn = QPushButton()
        prev_btn.setObjectName("ghost-btn")
        prev_btn.setIcon(qta.icon("fa5s.chevron-left", color="#888888"))
        prev_btn.setIconSize(QSize(12, 12))
        prev_btn.setFixedSize(36, 36)
        prev_btn.setToolTip("Previous week")
        prev_btn.clicked.connect(self._prev_week)

        self._week_lbl = QLabel()
        self._week_lbl.setStyleSheet(
            "background: transparent; font-size: 15px; font-weight: 700;"
        )
        self._week_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        next_btn = QPushButton()
        next_btn.setObjectName("ghost-btn")
        next_btn.setIcon(qta.icon("fa5s.chevron-right", color="#888888"))
        next_btn.setIconSize(QSize(12, 12))
        next_btn.setFixedSize(36, 36)
        next_btn.setToolTip("Next week")
        next_btn.clicked.connect(self._next_week)

        today_btn = QPushButton("Today")
        today_btn.setObjectName("ghost-btn")
        today_btn.setFixedHeight(36)
        today_btn.clicked.connect(self._go_to_today)

        self._dishy_btn = QPushButton("  Fill Week")
        self._dishy_btn.setObjectName("ghost-btn")
        self._dishy_btn.setIcon(qta.icon("fa5s.magic", color="#ff6b35"))
        self._dishy_btn.setIconSize(QSize(13, 13))
        self._dishy_btn.setFixedHeight(36)
        self._dishy_btn.setToolTip("Let Dishy auto-fill the whole week's meal plan")
        self._dishy_btn.clicked.connect(self._fill_with_dishy)

        self._opt_btn = QPushButton("  Optimize Week")
        self._opt_btn.setObjectName("ghost-btn")
        self._opt_btn.setIcon(qta.icon("fa5s.chart-line", color="#ff6b35"))
        self._opt_btn.setIconSize(QSize(13, 13))
        self._opt_btn.setFixedHeight(36)
        self._opt_btn.setToolTip("Fill empty slots with a balanced, pantry-aware plan")
        self._opt_btn.clicked.connect(self._auto_optimize_week)
        self._opt_btn.hide()

        nav.addWidget(prev_btn)
        nav.addWidget(self._week_lbl, 1)
        nav.addWidget(next_btn)
        nav.addSpacing(6)

        mode_lbl = QLabel("Planning mode")
        mode_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#888888', '#666666')};"
            " font-size: 12px; font-weight: 700;"
        )

        self._mode_combo = QComboBox()
        self._mode_combo.setFixedHeight(36)
        self._mode_combo.setMinimumWidth(170)
        for key, label, _desc in PLANNING_MODES:
            self._mode_combo.addItem(label, key)
        idx = max(0, self._mode_combo.findData(self._planning_mode))
        self._mode_combo.setCurrentIndex(idx)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self._template_name_input = QLineEdit()
        self._template_name_input.setPlaceholderText("Template name")
        self._template_name_input.setFixedHeight(36)
        self._template_name_input.setMinimumWidth(160)

        self._template_combo = QComboBox()
        self._template_combo.setFixedHeight(36)
        self._template_combo.setMinimumWidth(180)
        self._planner_toolbar = PageToolbar(self._planner_scaffold, density="compact")
        self._planner_toolbar.add_left_layout(nav)
        self._planner_toolbar.add_secondary_action(today_btn)
        self._planner_toolbar.set_primary_action(self._dishy_btn)
        self._planner_scaffold.set_toolbar(self._planner_toolbar)

        self._planner_summary_lbl = StatusBanner("", "system", self._planner_scaffold)
        self._planner_scaffold.set_banner(self._planner_summary_lbl)

        # ── Calendar grid ────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setHorizontalSpacing(10)
        self._grid_layout.setVerticalSpacing(10)
        self._grid_layout.setColumnStretch(0, 0)
        for col in range(1, 8):
            self._grid_layout.setColumnStretch(col, 1)
        scroll.setWidget(self._grid_container)
        self._planner_scaffold.body_layout().addWidget(scroll, 1)

        # Wrap the planner page in a scroll area so the header/nav stays accessible at narrow widths
        planner_scroll = QScrollArea()
        planner_scroll.setWidgetResizable(True)
        planner_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        planner_scroll.setWidget(planner_page)
        self._page_stack.addWidget(planner_scroll)   # index 0

        # ── Page 1: recipe detail ────────────────────────────────────────────
        self._recipe_detail_page = self._build_recipe_detail_page()
        self._page_stack.addWidget(self._recipe_detail_page)  # index 1

        self._rebuild_grid()

    # ── Grid construction ─────────────────────────────────────────────────────

    def _rebuild_grid(self):
        self._slots.clear()
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        end = self._week_start + timedelta(days=6)
        if self._week_start.month == end.month:
            label = f"{self._week_start.day} – {end.day} {end.strftime('%B %Y')}"
        else:
            label = (
                f"{self._week_start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
            )
        self._week_lbl.setText(label)

        today = datetime.now().date()

        # Corner spacer (aligns with DayHeader height)
        corner = QWidget()
        corner.setFixedHeight(74)
        corner.setFixedWidth(88)
        corner.setStyleSheet("background: transparent;")
        self._grid_layout.addWidget(corner, 0, 0)

        for col, day in enumerate(DAYS):
            col_date = self._week_start + timedelta(days=col)
            self._grid_layout.addWidget(DayHeader(col_date, col_date == today), 0, col + 1)

            for row, (meal_type, _, _) in enumerate(MEALS):
                slot = MealSlot(
                    day, meal_type,
                    on_click=self._on_slot_clicked,
                    on_open_recipe=self._show_recipe_detail,
                    on_drop=self._on_slot_drop,
                )
                self._slots[(day, meal_type)] = slot
                self._grid_layout.addWidget(slot, row + 1, col + 1)

        # Row labels in column 0
        for row, (meal_type, label, icon_name) in enumerate(MEALS):
            row_label = MealRowLabel(meal_type, label, icon_name)
            self._grid_layout.addWidget(row_label, row + 1, 0)

        self._grid_layout.setRowStretch(0, 0)
        for row in range(1, len(MEALS) + 1):
            self._grid_layout.setRowStretch(row, 1)

        self._load_week_data()
        self._refresh_planner_controls()

    def _load_week_data(self):
        try:
            rows = self._db.get_meal_plan(self._week_start.isoformat())
            for row in rows:
                key = (row["day_of_week"], row["meal_type"])
                if key not in self._slots or not row["custom_name"]:
                    continue
                colour = ""
                recipe_id = row["recipe_id"] or None
                if recipe_id:
                    try:
                        r = self._db.conn.execute(
                            "SELECT data_json FROM recipes WHERE id=?",
                            (recipe_id,),
                        ).fetchone()
                        if r:
                            colour = json.loads(r["data_json"] or "{}").get("colour", "")
                    except Exception:
                        pass
                metadata = load_slot_metadata(row["notes"] or "")
                self._slots[key].set_meal(row["custom_name"], colour, recipe_id=recipe_id, metadata=metadata)
        except Exception:
            pass

    # ── Recipe detail (inline panel) ──────────────────────────────────────────

    def _build_recipe_detail_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("view-container")
        vl = QVBoxLayout(page)
        vl.setContentsMargins(28, 28, 28, 20)
        vl.setSpacing(16)

        # Back button
        back_btn = QPushButton("← Back to Planner")
        back_btn.setObjectName("ghost-btn")
        back_btn.setFixedHeight(34)
        back_btn.setFixedWidth(160)
        back_btn.clicked.connect(lambda: self._page_stack.setCurrentIndex(0))
        vl.addWidget(back_btn)

        # Scrollable content area — rebuilt each time a recipe is shown
        self._detail_scroll = QScrollArea()
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._detail_content = QWidget()
        self._detail_content.setStyleSheet("background: transparent;")
        self._detail_content_layout = QVBoxLayout(self._detail_content)
        self._detail_content_layout.setContentsMargins(0, 0, 12, 36)
        self._detail_content_layout.setSpacing(18)
        self._detail_scroll.setWidget(self._detail_content)
        vl.addWidget(self._detail_scroll, 1)
        return page

    def _show_recipe_detail(self, recipe_id: int):
        try:
            rd = self._db.conn.execute(
                "SELECT * FROM recipes WHERE id=?", (recipe_id,)
            ).fetchone()
            if not rd:
                return
            data = json.loads(rd["data_json"] or "{}")
            data.setdefault("title", rd["title"] or "")
        except Exception:
            return
        self._populate_recipe_detail(data)
        self._page_stack.setCurrentIndex(1)
        self._detail_scroll.verticalScrollBar().setValue(0)

    def _populate_recipe_detail(self, recipe: dict):
        # Replace the scroll area's widget entirely — avoids deleteLater() overlap issues
        old = self._detail_scroll.takeWidget()
        if old:
            old.deleteLater()
        self._detail_content = QWidget()
        self._detail_content.setStyleSheet("background: transparent;")
        self._detail_content_layout = QVBoxLayout(self._detail_content)
        self._detail_content_layout.setContentsMargins(0, 0, 12, 36)
        self._detail_content_layout.setSpacing(18)
        self._detail_scroll.setWidget(self._detail_content)

        colour = theme_manager.c("#f1ece5", "#2d241c")
        icon_name = recipe.get("icon", "fa5s.utensils")

        # ── Title row ────────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(26, 26)))
        icon_lbl.setStyleSheet("background: transparent;")
        title_lbl = QLabel(recipe.get("title", "Untitled Recipe"))
        title_lbl.setStyleSheet(
            "background: transparent; font-size: 22px; font-weight: 700;"
        )
        title_lbl.setWordWrap(True)
        title_row.addWidget(icon_lbl)
        title_row.addSpacing(10)
        title_row.addWidget(title_lbl, 1)
        self._detail_content_layout.addLayout(title_row)

        # ── Meta chips ───────────────────────────────────────────────────────
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        total = recipe.get("total_time") or (
            (recipe.get("prep_time", 0) or 0) + (recipe.get("cook_time", 0) or 0)
        )
        if total:
            meta_row.addWidget(_meta_chip("fa5s.clock", f"{total} min", colour))
        servings = recipe.get("yields") or recipe.get("servings")
        if servings:
            meta_row.addWidget(_meta_chip("fa5s.users", str(servings), colour))
        meta_row.addStretch()
        self._detail_content_layout.addLayout(meta_row)

        # ── Tags ─────────────────────────────────────────────────────────────
        tags = recipe.get("tags", [])
        if tags:
            tag_row = QHBoxLayout()
            tag_row.setSpacing(6)
            for tag in tags[:8]:
                chip = QLabel(tag)
                chip.setStyleSheet(
                    f"background: {theme_manager.c('rgba(255,255,255,0.03)', 'rgba(0,0,0,0.03)')};"
                    f" color: {theme_manager.c('#a39c93', '#7c7368')};"
                    f" border: 1px solid {theme_manager.c('#2a3037', '#ddd1c4')};"
                    " border-radius: 10px; padding: 2px 10px; font-size: 11px; font-weight: 600;"
                )
                tag_row.addWidget(chip)
            tag_row.addStretch()
            self._detail_content_layout.addLayout(tag_row)

        # ── Divider helper ───────────────────────────────────────────────────
        def _div():
            d = QWidget()
            d.setFixedHeight(1)
            d.setStyleSheet(f"background: {theme_manager.c('#1e1e1e', '#e5e5e5')};")
            return d

        def _section(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#8d867d', '#756d63')};"
                " font-size: 11px; font-weight: 700; letter-spacing: 1.2px;"
            )
            return lbl

        # ── Ingredients ──────────────────────────────────────────────────────
        ingredients = recipe.get("ingredients", [])
        if ingredients:
            self._detail_content_layout.addWidget(_div())
            self._detail_content_layout.addWidget(_section("INGREDIENTS"))
            ing_wrap = QVBoxLayout()
            ing_wrap.setSpacing(6)
            for ing in ingredients:
                row = QHBoxLayout()
                dot = QLabel("·")
                dot.setStyleSheet(
                    "background: transparent; color: #ff6b35;"
                    " font-size: 20px; font-weight: 700;"
                )
                dot.setFixedWidth(16)
                lbl = QLabel(str(ing))
                lbl.setStyleSheet(
                    f"background: transparent; color: {theme_manager.c('#c0c0c0', '#222222')};"
                    " font-size: 14px;"
                )
                lbl.setWordWrap(True)
                row.addWidget(dot)
                row.addWidget(lbl, 1)
                ing_wrap.addLayout(row)
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            container.setLayout(ing_wrap)
            self._detail_content_layout.addWidget(container)

        # ── Instructions ─────────────────────────────────────────────────────
        instructions = recipe.get("instructions", [])
        if instructions:
            self._detail_content_layout.addWidget(_div())
            self._detail_content_layout.addWidget(_section("INSTRUCTIONS"))
            steps_wrap = QVBoxLayout()
            steps_wrap.setSpacing(10)
            for i, step in enumerate(instructions, 1):
                row = QHBoxLayout()
                row.setAlignment(Qt.AlignmentFlag.AlignTop)
                num = QLabel(str(i))
                num.setFixedWidth(26)
                num.setFixedHeight(26)
                num.setAlignment(Qt.AlignmentFlag.AlignCenter)
                num.setStyleSheet(
                    "background: rgba(255,107,53,0.12); color: #ff6b35; border-radius: 13px;"
                    " font-size: 11px; font-weight: 700;"
                )
                lbl = QLabel(str(step))
                lbl.setStyleSheet(
                    f"background: transparent; color: {theme_manager.c('#c0c0c0', '#222222')};"
                    " font-size: 14px;"
                )
                lbl.setWordWrap(True)
                row.addWidget(num)
                row.addSpacing(10)
                row.addWidget(lbl, 1)
                steps_wrap.addLayout(row)
            container2 = QWidget()
            container2.setStyleSheet("background: transparent;")
            container2.setLayout(steps_wrap)
            self._detail_content_layout.addWidget(container2)

        # ── Nutrition ────────────────────────────────────────────────────────
        nutr = recipe.get("nutrition_per_serving") or recipe.get("nutrition") or {}
        if nutr and any(nutr.get(k, 0) for k in ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g")):
            self._detail_content_layout.addWidget(_div())
            self._detail_content_layout.addWidget(_section("NUTRITION PER SERVING"))
            nutr_row = QHBoxLayout()
            nutr_row.setSpacing(12)
            for label, key, unit in [
                ("Calories", "kcal", "kcal"),
                ("Protein",  "protein_g", "g"),
                ("Carbs",    "carbs_g",   "g"),
                ("Fat",      "fat_g",     "g"),
                ("Fiber",    "fiber_g",   "g"),
                ("Sugar",    "sugar_g",   "g"),
            ]:
                val = nutr.get(key, 0)
                if val:
                    card = QWidget()
                    card.setStyleSheet(
                        f"background: {theme_manager.c('rgba(255,255,255,0.03)', 'rgba(0,0,0,0.03)')};"
                        " border: none;"
                        " border-radius: 8px;"
                    )
                    cl = QVBoxLayout(card)
                    cl.setContentsMargins(12, 8, 12, 8)
                    cl.setSpacing(2)
                    val_lbl = QLabel(f"{val:.0f}{unit}")
                    val_lbl.setStyleSheet(
                        f"background: transparent; color: {theme_manager.c('#f1ece5', '#201913')};"
                        " font-size: 16px; font-weight: 700;"
                    )
                    name_lbl = QLabel(label)
                    name_lbl.setStyleSheet(
                        f"background: transparent; color: {theme_manager.c('#888888', '#666666')};"
                        " font-size: 10px;"
                    )
                    cl.addWidget(val_lbl)
                    cl.addWidget(name_lbl)
                    nutr_row.addWidget(card)
            nutr_row.addStretch()
            self._detail_content_layout.addLayout(nutr_row)

        self._detail_content_layout.addStretch()

    # ── Slot interaction ──────────────────────────────────────────────────────

    def _on_slot_clicked(self, day: str, meal_type: str, current_name: str):
        dlg = MealPickerDialog(day, meal_type, current_name, self._db, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        name, recipe_id, should_clear = dlg.get_result()
        slot = self._slots.get((day, meal_type))
        if not slot:
            return

        slot.current_name()  # kept for reference only; nutrition now reads from meal_plans

        if should_clear:
            self._db.clear_meal_slot(self._week_start.isoformat(), day, meal_type)
            slot.set_meal("")
            if self._nutrition_refresh_fn:
                self._nutrition_refresh_fn()
            if self._sync_fn:
                self._sync_fn()
        elif name:
            recipe_row = self._get_recipe_row(recipe_id)
            metadata = self._build_slot_metadata(recipe_row, meal_type)
            self._db.set_meal_slot(
                self._week_start.isoformat(), day, meal_type,
                custom_name=name, recipe_id=recipe_id, notes=dump_slot_metadata(metadata),
            )
            colour = ""
            if recipe_row:
                try:
                    colour = json.loads(recipe_row["data_json"] or "{}").get("colour", "")
                except Exception:
                    colour = ""
            slot.set_meal(name, colour, recipe_id=recipe_id, metadata=metadata)
            if self._nutrition_refresh_fn:
                self._nutrition_refresh_fn()
            if self._sync_fn:
                self._sync_fn()
        else:
            self._db.clear_meal_slot(self._week_start.isoformat(), day, meal_type)
            slot.set_meal("")
            if self._nutrition_refresh_fn:
                self._nutrition_refresh_fn()
            if self._sync_fn:
                self._sync_fn()

    # ── Drag-and-drop handler ─────────────────────────────────────────────────

    def _get_recipe_colour(self, recipe_id: int | None) -> str:
        if not recipe_id:
            return ""
        try:
            r = self._db.conn.execute(
                "SELECT data_json FROM recipes WHERE id=?", (recipe_id,)
            ).fetchone()
            if r:
                return json.loads(r["data_json"] or "{}").get("colour", "")
        except Exception:
            pass
        return ""

    def _get_recipe_row(self, recipe_id: int | None):
        if not recipe_id:
            return None
        try:
            return self._db.conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
        except Exception:
            return None

    def _build_slot_metadata(self, recipe_row, meal_type: str, *, template_name: str = "") -> dict:
        meta = {
            "planning_mode": self._planning_mode,
            "owner_label": current_editor_label(self._db),
        }
        if template_name:
            meta["template_name"] = template_name
        if recipe_row is not None:
            try:
                data = json.loads(recipe_row["data_json"] or "{}")
            except Exception:
                data = {}
            tags = {str(t or "").strip().lower() for t in (data.get("tags") or [])}
            if meal_type == "dinner" and (
                self._planning_mode == "meal_prep" or {"meal-prep", "batch cook"} & tags
            ):
                meta["prep_batch"] = True
                meta["leftover_portions"] = 2 if self._planning_mode == "meal_prep" else 1
        return meta

    def _on_slot_drop(self,
                      src_day: str, src_meal_type: str,
                      src_name: str, src_rid: int | None, src_meta: dict | None,
                      dst_day: str, dst_meal_type: str,
                      dst_name: str, dst_rid: int | None, dst_meta: dict | None):
        if src_day == dst_day and src_meal_type == dst_meal_type:
            return
        src_slot = self._slots.get((src_day, src_meal_type))
        dst_slot = self._slots.get((dst_day, dst_meal_type))
        if not src_slot:
            return
        week_start = self._week_start.isoformat()

        do_move = False
        do_swap = False

        if dst_name:
            result = ThemedMessageBox.show_buttons(
                self, "Move Meal",
                f"<b>{dst_name}</b> is already in {dst_day} {dst_meal_type.capitalize()}.<br><br>"
                "What would you like to do?",
                ["Cancel", "Replace", "Swap"],
                kind="question",
            )
            if result == "Swap":
                do_swap = True
            elif result == "Replace":
                do_move = True
            # else Cancel — do nothing
        else:
            do_move = True

        if do_swap:
            self._db.set_meal_slot(week_start, src_day, src_meal_type,
                                   custom_name=dst_name, recipe_id=dst_rid, notes=dump_slot_metadata(dst_meta))
            self._db.set_meal_slot(week_start, dst_day, dst_meal_type,
                                   custom_name=src_name, recipe_id=src_rid, notes=dump_slot_metadata(src_meta))
            src_slot.set_meal(dst_name, self._get_recipe_colour(dst_rid), recipe_id=dst_rid, metadata=dst_meta or {})
            if dst_slot:
                dst_slot.set_meal(src_name, self._get_recipe_colour(src_rid), recipe_id=src_rid, metadata=src_meta or {})
        elif do_move:
            self._db.clear_meal_slot(week_start, src_day, src_meal_type)
            self._db.set_meal_slot(week_start, dst_day, dst_meal_type,
                                   custom_name=src_name, recipe_id=src_rid, notes=dump_slot_metadata(src_meta))
            src_slot.set_meal("")
            if dst_slot:
                dst_slot.set_meal(src_name, self._get_recipe_colour(src_rid), recipe_id=src_rid, metadata=src_meta or {})
        else:
            return  # cancelled

        if self._nutrition_refresh_fn:
            self._nutrition_refresh_fn()
        if self._sync_fn:
            self._sync_fn()

    # ── Week navigation ───────────────────────────────────────────────────────

    def _prev_week(self):
        self._week_start -= timedelta(weeks=1)
        self._rebuild_grid()

    def _next_week(self):
        self._week_start += timedelta(weeks=1)
        self._rebuild_grid()

    def _go_to_today(self):
        self._week_start = _week_start_from(datetime.now().date())
        self._rebuild_grid()

    # ── Shopping list generation ──────────────────────────────────────────────

    def _generate_shopping_list(self):
        try:
            rows = self._db.get_meal_plan(self._week_start.isoformat())
        except Exception:
            return

        pantry_names = {
            str(item.get("name") or "").strip().lower()
            for item in self._db.get_pantry_items()
            if str(item.get("name") or "").strip()
        }
        items: list[dict] = []
        skipped_pantry = 0
        for row in rows:
            if row["recipe_id"]:
                try:
                    r = self._db.conn.execute(
                        "SELECT data_json FROM recipes WHERE id=?", (row["recipe_id"],)
                    ).fetchone()
                    if r and r["data_json"]:
                        data = json.loads(r["data_json"])
                        for ing in data.get("ingredients", []):
                            raw = " ".join(str(ing or "").split()).strip()
                            if not raw:
                                continue
                            lowered = raw.lower()
                            if any(pantry_name and pantry_name in lowered for pantry_name in pantry_names):
                                skipped_pantry += 1
                                continue
                            items.append({"name": raw, "quantity": "", "unit": "", "source": "meal_plan"})
                        continue
                except Exception:
                    pass
            if row["custom_name"]:
                items.append({"name": row["custom_name"], "quantity": "", "unit": "", "source": "meal_plan"})

        if not items:
            ThemedMessageBox.information(self, "Nothing to add", "No meals are planned for this week yet.")
            return

        merged_rows, _stats = consolidate_rows(items)
        for item in merged_rows:
            try:
                self._db.add_shopping_item(
                    str(item.get("name") or ""),
                    quantity=str(item.get("quantity") or ""),
                    unit=str(item.get("unit") or ""),
                    source=str(item.get("source") or "meal_plan"),
                )
            except Exception:
                pass

        if self._shopping_view:
            self._shopping_view.load_from_db()

        if skipped_pantry:
            ThemedMessageBox.information(
                self,
                "Shopping list built",
                f"Added {len(merged_rows)} optimized item(s) and skipped {skipped_pantry} pantry overlap(s).",
            )
        self._navigate_to(5)

    # ── Ask Dishy (per-tab button) ────────────────────────────────────────────

    def _ask_dishy_planner(self):
        if self._ask_dishy_fn:
            self._ask_dishy_fn(
                "Help me plan my meals. You can add individual meals to specific days, "
                "or fill the whole week. What would you like to know — "
                "any dietary preferences, or shall I just suggest a balanced plan?"
            )

    # ── Fill with Dishy ───────────────────────────────────────────────────────

    def _fill_with_dishy(self):
        self._dishy_btn.setText("  Filling…")
        self._dishy_btn.setEnabled(False)

        try:
            saved = [r["title"] for r in self._db.get_saved_recipes()]
        except Exception:
            saved = []

        try:
            dietary = self._db.get_setting("dietary_prefs", "")
        except Exception:
            dietary = ""

        expiry_items = pantry_expiry_items(self._db, limit=4)
        if expiry_items:
            dietary = (dietary + " Use up soon: " + ", ".join(str(item.get("name") or "") for item in expiry_items)).strip()

        end = self._week_start + timedelta(days=6)
        week_label = (
            f"{self._week_start.strftime('%d %b')} – {end.strftime('%d %b %Y')} "
            f"({planning_mode_label(self._planning_mode)} mode)"
        )

        run_async(
            _claude.plan_week_structured,
            saved, dietary, week_label,
            on_result=self._on_dishy_plan,
            on_error=self._on_dishy_error,
        )

    def _auto_optimize_week(self):
        self._opt_btn.setEnabled(False)
        self._opt_btn.setText("  Optimizing…")
        try:
            result = optimize_week(
                self._db,
                self._week_start.isoformat(),
                refill_all=False,
                planning_mode=self._planning_mode,
                use_leftovers=True,
            )
            assigned = int(result.get("assigned", 0) or 0)
            self.refresh()
            if self._nutrition_refresh_fn:
                self._nutrition_refresh_fn()
            if self._sync_fn:
                self._sync_fn()
            if assigned > 0:
                ThemedMessageBox.information(
                    self,
                    "Week optimized",
                    f"Updated {assigned} slot(s) in {planning_mode_label(self._planning_mode)} mode.\n"
                    f"Prep slots: {int(result.get('prep_slots', 0) or 0)} · "
                    f"Leftover lunches: {int(result.get('leftover_assignments', 0) or 0)}",
                )
            else:
                ThemedMessageBox.information(
                    self,
                    "Nothing to optimize",
                    "No updates were needed for this week.",
                )
        except Exception as exc:
            ThemedMessageBox.warning(self, "Optimize Week failed", str(exc)[:320])
        finally:
            self._opt_btn.setEnabled(True)
            self._opt_btn.setText("  Optimize Week")

    def _on_dishy_plan(self, plan: dict):
        filled = 0
        missing: list[str] = []
        for day in DAYS:
            day_meals = plan.get(day, {})
            for meal_type, _, _ in MEALS:
                name = day_meals.get(meal_type, "").strip()
                if not name:
                    continue
                # Only fill empty slots so user's existing choices are preserved
                slot = self._slots.get((day, meal_type))
                if slot and not slot.current_name():
                    recipe_row = resolve_recipe_by_title(self._db, name)
                    if recipe_row is None:
                        missing.append(name)
                        continue
                    metadata = self._build_slot_metadata(recipe_row, meal_type)
                    self._db.set_meal_slot(
                        self._week_start.isoformat(), day, meal_type,
                        custom_name=str(recipe_row["title"] or name),
                        recipe_id=int(recipe_row["id"] or 0) or None,
                        notes=dump_slot_metadata(metadata),
                    )
                    slot.set_meal(
                        str(recipe_row["title"] or name),
                        self._get_recipe_colour(int(recipe_row["id"] or 0) or None),
                        recipe_id=int(recipe_row["id"] or 0) or None,
                        metadata=metadata,
                    )
                    filled += 1

        self._dishy_btn.setText("  Fill Week")
        self._dishy_btn.setEnabled(True)
        self._refresh_planner_controls()
        if filled and self._nutrition_refresh_fn:
            self._nutrition_refresh_fn()
        if filled and self._sync_fn:
            self._sync_fn()

        if filled:
            extra = ""
            if missing:
                extra = "\n\nSkipped suggestions that are not saved recipes: " + ", ".join(missing[:4])
            ThemedMessageBox.information(
                self, "Dishy filled your week!",
                f"Added {filled} meal suggestion{'s' if filled != 1 else ''} "
                f"to empty slots.\n\nExisting meals were left untouched.{extra}",
            )
        else:
            ThemedMessageBox.information(
                self, "Week already full",
                "All slots are already filled — clear some meals first if you'd like Dishy to suggest new ones.",
            )

    def _on_dishy_error(self, err: str):
        self._dishy_btn.setText("  Fill Week")
        self._dishy_btn.setEnabled(True)
        ThemedMessageBox.warning(
            self, "Dishy couldn't generate a plan",
            "Something went wrong — check your API key and connection.\n\n"
            + err[:300],
        )

    # ── Apple Calendar export ─────────────────────────────────────────────────

    def _export_to_calendar(self):
        try:
            rows = self._db.get_meal_plan(self._week_start.isoformat())
        except Exception:
            rows = []

        now_str = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//DishBoard//Meal Planner//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]

        event_count = 0
        for row in rows:
            meal_name = row["custom_name"]
            if not meal_name:
                continue

            meal_type = row["meal_type"]
            try:
                day_index = DAYS.index(row["day_of_week"])
            except ValueError:
                continue

            event_date = self._week_start + timedelta(days=day_index)
            date_str = event_date.strftime("%Y%m%d")
            start_t, end_t = MEAL_TIMES.get(meal_type, ("120000", "130000"))
            uid = f"dishboard-{date_str}-{meal_type}@dishboard"
            safe_name = (
                meal_name.replace("\\", "\\\\")
                         .replace(";", "\\;")
                         .replace(",", "\\,")
            )

            ics_lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_str}",
                f"DTSTART:{date_str}T{start_t}",
                f"DTEND:{date_str}T{end_t}",
                f"SUMMARY:{meal_type.capitalize()}: {safe_name}",
                "DESCRIPTION:Added from DishBoard Meal Planner",
                "END:VEVENT",
            ]
            event_count += 1

        if event_count == 0:
            ThemedMessageBox.information(self, "Nothing to export", "No meals are planned for this week yet.")
            return

        ics_lines.append("END:VCALENDAR")

        try:
            with tempfile.NamedTemporaryFile(
                suffix=".ics", delete=False, mode="w", encoding="utf-8"
            ) as f:
                f.write("\r\n".join(ics_lines) + "\r\n")
                tmp_path = f.name

            ok, err = open_path_in_default_app(tmp_path)
            if not ok:
                raise RuntimeError(err or "Could not open calendar file")
        except Exception as e:
            ThemedMessageBox.warning(self, "Export failed", f"Could not open Calendar:\n{e}")
