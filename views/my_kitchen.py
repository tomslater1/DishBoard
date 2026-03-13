from datetime import datetime, timedelta
import json
import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QLineEdit, QGridLayout, QScrollArea, QCheckBox, QFrame,
)
from PySide6.QtCore import Qt, QSize

from models.database import Database
from utils.data_service import get_db
from utils.theme import manager as _tm
from utils.macro_goals import get_macro_goals, get_broadcaster
from views.nutrition import MacroRing
from views.shopping_list import CATEGORIES, _categorize
from views.my_kitchen_storage import (
    _STORAGE_CATEGORIES, _categorize_kitchen_item, _TABS as _KITCHEN_TABS,
    _days_until_expiry, get_pantry_broadcaster,
)


def _greeting() -> str:
    h = datetime.now().hour
    if 5  <= h < 12: return "Good morning"
    if 12 <= h < 17: return "Good afternoon"
    if 17 <= h < 22: return "Good evening"
    return "Good night"


def _date_str() -> str:
    return datetime.now().strftime("%A, %d %B %Y")


def _week_start() -> str:
    today = datetime.now().date()
    return (today - timedelta(days=today.weekday())).isoformat()


def _card_header(icon_name: str, icon_colour: str, label: str) -> QHBoxLayout:
    """Shared header row used by all cards for visual consistency."""
    hdr = QHBoxLayout()
    ic = QLabel()
    ic.setPixmap(qta.icon(icon_name, color=icon_colour).pixmap(QSize(13, 13)))
    ic.setStyleSheet("background: transparent;")
    lbl = QLabel(label)
    lbl.setObjectName("section-label")
    hdr.addWidget(ic)
    hdr.addSpacing(6)
    hdr.addWidget(lbl)
    hdr.addStretch()
    return hdr


def _stat_card(icon_name: str, value: str, label: str, colour: str, on_click=None) -> QWidget:
    card = QWidget()
    card.setObjectName("stat-card")
    if on_click:
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mousePressEvent = lambda e: on_click()
    row = QHBoxLayout(card)
    row.setContentsMargins(18, 12, 18, 12)
    row.setSpacing(12)
    icon_lbl = QLabel()
    icon_lbl.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(20, 20)))
    icon_lbl.setStyleSheet("background: transparent;")
    icon_lbl.setFixedSize(20, 20)
    text_col = QVBoxLayout()
    text_col.setSpacing(1)
    text_col.setContentsMargins(0, 0, 0, 0)
    val = QLabel(value)
    val.setObjectName("stat-value")
    lbl = QLabel(label)
    lbl.setObjectName("stat-label")
    text_col.addWidget(val)
    text_col.addWidget(lbl)
    row.addWidget(icon_lbl)
    row.addLayout(text_col)
    row.addStretch()
    return card


_DISHY_CHIPS = [
    ("Give me a meal plan for this week", "fa5s.calendar-alt"),
    ("High-protein dinner ideas",          "fa5s.fire"),
]

_DASH_MACROS = [
    ("kcal",      "Calories", "kcal", "#ff6b35"),
    ("protein_g", "Protein",  "g",    "#4fc3f7"),
    ("carbs_g",   "Carbs",    "g",    "#aed581"),
    ("fat_g",     "Fat",      "g",    "#ffb74d"),
]


class _ExpiryAlertCard(QWidget):
    """
    Compact banner shown on the home dashboard when pantry items are expiring soon.
    Hidden when nothing is expiring. Updates via _PantryBroadcaster signal.
    """

    def __init__(self, db: Database, navigate_to, trigger_dishy, parent=None):
        super().__init__(parent)
        self._db = db
        self._navigate_to = navigate_to
        self._trigger_dishy = trigger_dishy
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._inner = QWidget()
        self._inner.setObjectName("card")
        layout.addWidget(self._inner)
        self._inner_layout = QHBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(16, 10, 16, 10)
        self._inner_layout.setSpacing(10)
        self.refresh()

    def refresh(self):
        # Clear existing widgets
        while self._inner_layout.count():
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            items = self._db.get_pantry_items()
        except Exception:
            items = []

        expiring = []
        for item in items:
            days = _days_until_expiry(item.get("expiry_date") or "")
            if days is not None and days <= 3:
                expiring.append((item["name"], days))

        if not expiring:
            self.hide()
            return

        self.show()

        # Warning icon
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("fa5s.exclamation-triangle", color="#f0a500").pixmap(QSize(14, 14)))
        icon_lbl.setStyleSheet("background: transparent;")
        self._inner_layout.addWidget(icon_lbl)

        # Build label text
        names = []
        for name, days in expiring[:3]:
            if days < 0:
                names.append(f"{name} (expired)")
            elif days == 0:
                names.append(f"{name} (today)")
            else:
                names.append(f"{name} ({days}d)")
        extra = len(expiring) - 3
        text = ", ".join(names)
        if extra > 0:
            text += f" +{extra} more"

        msg = QLabel(f"Expiring soon: {text}")
        msg.setStyleSheet(
            f"background: transparent; color: {_tm.c('#e0e0e0', '#1a1a1a')};"
            " font-size: 12px;"
        )
        self._inner_layout.addWidget(msg, 1)

        # "Use it up" button
        btn = QPushButton("Use it up →")
        btn.setObjectName("ghost-btn")
        btn.setFixedHeight(24)
        item_names = ", ".join(n for n, _ in expiring)
        msg_text = f"Suggest recipes I can make using these items that are expiring soon: {item_names}"
        btn.clicked.connect(lambda: (self._navigate_to(6), self._trigger_dishy(msg_text)))
        self._inner_layout.addWidget(btn)

    def apply_theme(self, _mode: str):
        self.refresh()


class _KitchenPreviewCard(QWidget):
    """
    Compact My Kitchen storage preview for the home dashboard.
    Mirrors the Shopping List preview card layout — scrollable, category-grouped.
    Refreshes in place when pantry data changes.
    """

    def __init__(self, db: Database, navigate_to, parent=None):
        super().__init__(parent)
        self._db = db
        self._navigate_to = navigate_to

        # Outer wrapper is transparent — inner plain QWidget gets objectName("card")
        # so the global QWidget#card stylesheet matches it exactly like the shopping card
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._card = QWidget()
        self._card.setObjectName("card")
        outer.addWidget(self._card)

        self._root = QVBoxLayout(self._card)
        self._root.setContentsMargins(20, 16, 20, 14)
        self._root.setSpacing(8)
        self._root.addLayout(self._build_header())

        # Body container — cleared and rebuilt on each refresh()
        self._body = QWidget()
        self._body.setStyleSheet("background: transparent;")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        self._root.addWidget(self._body, 1)

        self.refresh()

    def apply_theme(self, mode: str):
        pass

    def _build_header(self) -> QHBoxLayout:
        hdr = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(qta.icon("fa5s.box-open", color="#e8924a").pixmap(QSize(20, 20)))
        ic.setStyleSheet("background: transparent;")
        title_lbl = QLabel("MY KITCHEN")
        title_lbl.setStyleSheet(
            f"background: transparent; color: {_tm.c('#888888', '#666666')};"
            " font-size: 13px; font-weight: 700; letter-spacing: 1px;"
        )
        view_btn = QPushButton("View →")
        view_btn.setObjectName("ghost-btn")
        view_btn.setFixedHeight(24)
        view_btn.clicked.connect(lambda: self._navigate_to(4))
        hdr.addWidget(ic)
        hdr.addSpacing(8)
        hdr.addWidget(title_lbl)
        hdr.addStretch()
        hdr.addWidget(view_btn)
        return hdr

    def _scroll_style(self) -> str:
        return (
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { background: transparent; width: 4px; margin: 0; }"
            f"QScrollBar::handle:vertical {{ background: {_tm.c('#2a2a2a', '#cccccc')};"
            " border-radius: 2px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

    def refresh(self):
        """Clear and rebuild the card body from live DB data."""
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            all_items = self._db.get_pantry_items()
        except Exception:
            all_items = []

        total = len(all_items)

        if all_items:
            from collections import defaultdict

            # Group by storage section
            storage_groups: dict[str, list] = defaultdict(list)
            for item in all_items:
                storage_groups[item.get("storage", "Pantry")].append(item)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setStyleSheet(self._scroll_style())

            inner = QWidget()
            inner.setStyleSheet("background: transparent;")
            inner_layout = QVBoxLayout(inner)
            inner_layout.setContentsMargins(0, 0, 4, 0)
            inner_layout.setSpacing(3)

            txt_main = _tm.c('#e0e0e0', '#1a1a1a')
            txt_sub  = _tm.c('#666666', '#888888')

            for storage, color, icon_name in _KITCHEN_TABS:
                items_for_storage = storage_groups.get(storage, [])
                if not items_for_storage:
                    continue

                # Storage section header (Pantry / Fridge / Freezer)
                sec_hdr = QWidget()
                sec_hdr.setStyleSheet("background: transparent;")
                sec_hdr.setFixedHeight(28)
                sec_l = QHBoxLayout(sec_hdr)
                sec_l.setContentsMargins(0, 6, 0, 2)
                sec_l.setSpacing(6)
                sec_ic = QLabel()
                sec_ic.setPixmap(qta.icon(icon_name, color=color).pixmap(QSize(13, 13)))
                sec_ic.setStyleSheet("background: transparent;")
                sec_lbl = QLabel(storage.upper())
                sec_lbl.setStyleSheet(
                    f"background: transparent; color: {color};"
                    " font-size: 10px; font-weight: 700; letter-spacing: 0.8px;"
                )
                cnt_lbl = QLabel(f"({len(items_for_storage)})")
                cnt_lbl.setStyleSheet(
                    f"background: transparent; color: {_tm.c('#555555', '#aaaaaa')}; font-size: 10px;"
                )
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setStyleSheet(
                    f"background: {_tm.c('#2a2a2a', '#e8e8e8')}; border: none; max-height: 1px;"
                )
                sec_l.addWidget(sec_ic)
                sec_l.addWidget(sec_lbl)
                sec_l.addWidget(cnt_lbl)
                sec_l.addWidget(line, 1)
                inner_layout.addWidget(sec_hdr)

                # Group items within this storage by category
                cats = _STORAGE_CATEGORIES.get(storage, [])
                cat_grouped: dict[str, list] = defaultdict(list)
                for item in items_for_storage:
                    cat_grouped[_categorize_kitchen_item(item["name"], storage)].append(item)

                for cat_name, cat_icon, cat_colour, _kws in cats:
                    cat_items = cat_grouped.get(cat_name, [])
                    if not cat_items:
                        continue

                    # Category sub-header
                    cat_hdr = QWidget()
                    cat_hdr.setStyleSheet("background: transparent;")
                    cat_hdr.setFixedHeight(22)
                    cat_l = QHBoxLayout(cat_hdr)
                    cat_l.setContentsMargins(4, 2, 0, 0)
                    cat_l.setSpacing(5)
                    cat_ic_lbl = QLabel()
                    cat_ic_lbl.setPixmap(qta.icon(cat_icon, color=cat_colour).pixmap(QSize(11, 11)))
                    cat_ic_lbl.setStyleSheet("background: transparent;")
                    cat_name_lbl = QLabel(cat_name)
                    cat_name_lbl.setStyleSheet(
                        f"background: transparent; color: {cat_colour};"
                        " font-size: 10px; font-weight: 700; letter-spacing: 0.5px;"
                    )
                    cat_cnt = QLabel(f"({len(cat_items)})")
                    cat_cnt.setStyleSheet(
                        f"background: transparent; color: {_tm.c('#555555', '#aaaaaa')}; font-size: 10px;"
                    )
                    cat_l.addWidget(cat_ic_lbl)
                    cat_l.addWidget(cat_name_lbl)
                    cat_l.addWidget(cat_cnt)
                    cat_l.addStretch()
                    inner_layout.addWidget(cat_hdr)

                    for item in cat_items:
                        item_row = QWidget()
                        item_row.setStyleSheet("background: transparent;")
                        item_row.setFixedHeight(34)
                        row_l = QHBoxLayout(item_row)
                        row_l.setContentsMargins(4, 0, 0, 0)
                        row_l.setSpacing(8)

                        name_str = item["name"][:28] + ("…" if len(item["name"]) > 28 else "")
                        name_lbl = QLabel(name_str)
                        name_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                        name_lbl.setStyleSheet(
                            f"background: transparent; color: {txt_main}; font-size: 13px; font-weight: 500;"
                        )

                        qty = item.get("quantity")
                        unit = item.get("unit", "")
                        qty_str = ""
                        if qty is not None:
                            try:
                                qty_str = str(int(float(qty))) if float(qty) == int(float(qty)) else str(qty)
                            except Exception:
                                qty_str = str(qty)
                            if unit:
                                qty_str += f" {unit}"
                        qty_lbl = QLabel(qty_str)
                        qty_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        qty_lbl.setStyleSheet(
                            f"background: transparent; color: {txt_sub}; font-size: 11px;"
                        )

                        row_l.addWidget(name_lbl, 1)

                        # Expiry badge for items expiring soon
                        days = _days_until_expiry(item.get("expiry_date") or "")
                        if days is not None:
                            if days < 0:
                                badge_text, badge_col = "Expired", "#ef4444"
                                badge_bg = "rgba(239,68,68,0.15)"
                            elif days <= 3:
                                badge_text = f"{days}d"
                                badge_col, badge_bg = "#f0a500", "rgba(240,165,0,0.15)"
                            else:
                                badge_text = ""
                            if badge_text:
                                exp_lbl = QLabel(badge_text)
                                exp_lbl.setStyleSheet(
                                    f"color:{badge_col};font-size:9px;font-weight:700;"
                                    f"background:{badge_bg};border-radius:4px;padding:1px 5px"
                                )
                                row_l.addWidget(exp_lbl)

                        row_l.addWidget(qty_lbl)
                        inner_layout.addWidget(item_row)

            inner_layout.addStretch()
            scroll.setWidget(inner)
            self._body_layout.addWidget(scroll, 1)

            count_lbl = QLabel(f"{total} item{'s' if total != 1 else ''} in storage")
            count_lbl.setStyleSheet(
                f"background: transparent; color: {_tm.c('#444444', '#999999')}; font-size: 11px;"
            )
            self._body_layout.addWidget(count_lbl)

        else:
            self._body_layout.addStretch()
            ph = QLabel("My Kitchen is empty")
            ph.setObjectName("placeholder-text")
            ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub = QLabel("Add items to track your pantry, fridge & freezer")
            sub.setObjectName("placeholder-sub")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._body_layout.addWidget(ph)
            self._body_layout.addWidget(sub)
            self._body_layout.addStretch()


class MyKitchenView(QWidget):
    def __init__(self, db: Database | None = None, navigate_to=None, trigger_dishy=None, parent=None):
        super().__init__(parent)
        self.setObjectName("view-container")
        self._navigate_to   = navigate_to   or (lambda i: None)
        self._trigger_dishy = trigger_dishy or (lambda t: None)
        self._db = db or get_db()
        self._macro_rings: dict[str, MacroRing] = {}

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)
        self._kitchen_preview: _KitchenPreviewCard | None = None
        self._expiry_card: _ExpiryAlertCard | None = None
        get_broadcaster().goals_changed.connect(self._on_goals_changed)
        get_pantry_broadcaster().pantry_changed.connect(self._on_kitchen_changed)
        self._rebuild_content()

    def _rebuild_content(self):
        self._macro_rings.clear()
        while self._outer.count():
            item = self._outer.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Outer scroll area so the dashboard never crushes vertically
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }"
            f"QScrollBar::handle:vertical {{ background: {_tm.c('#2a2a2a', '#cccccc')}; border-radius: 3px; min-height: 20px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content.setMinimumHeight(760)  # prevents row_b from crushing at small window heights
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 20, 28, 16)
        layout.setSpacing(12)

        layout.addLayout(self._header())
        layout.addLayout(self._stats())

        # Row A — Today's Plan | Recent Recipes (Dishy moved to bottom-left)
        row_a = QHBoxLayout()
        row_a.setSpacing(12)
        plan_card = self._today_plan()
        plan_card.setMinimumHeight(200)
        recent_card = self._recent_recipes()
        recent_card.setMinimumHeight(200)
        row_a.addWidget(plan_card, 1)
        row_a.addWidget(recent_card, 1)
        layout.addLayout(row_a)

        # Compact quick-action strip
        layout.addWidget(self._quick_actions_strip())

        # Expiry alert banner (hidden when nothing is expiring)
        self._expiry_card = _ExpiryAlertCard(self._db, self._navigate_to, self._trigger_dishy)
        layout.addWidget(self._expiry_card)

        # Row B — [Macro Rings + Dishy stacked] | Shopping Preview | Favourites
        row_b = QHBoxLayout()
        row_b.setSpacing(12)

        left_col = QWidget()
        left_col.setStyleSheet("background: transparent;")
        left_col.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_col.setMinimumHeight(280)
        left_vbox = QVBoxLayout(left_col)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.setSpacing(12)
        left_vbox.addWidget(self._macro_card(), 1)
        left_vbox.addWidget(self._dishy_teaser(), 1)

        shopping_card = self._shopping_preview()
        shopping_card.setMinimumHeight(280)
        self._kitchen_preview = _KitchenPreviewCard(self._db, self._navigate_to)
        self._kitchen_preview.setMinimumHeight(280)

        row_b.addWidget(left_col, 5)
        row_b.addWidget(shopping_card, 3)
        row_b.addWidget(self._kitchen_preview, 3)
        layout.addLayout(row_b, 1)

        scroll.setWidget(content)
        self._outer.addWidget(scroll)
        self._refresh_macros()

    def refresh(self):
        self._rebuild_content()

    def apply_theme(self, _mode: str):
        self._rebuild_content()

    # ── Header ─────────────────────────────────────────────────────────────

    def _header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(2)
        left.setContentsMargins(0, 0, 0, 0)
        greeting = QLabel(_greeting())
        greeting.setObjectName("page-title")
        date_lbl = QLabel(_date_str())
        date_lbl.setObjectName("page-date")
        left.addWidget(greeting)
        left.addWidget(date_lbl)
        layout.addLayout(left)
        layout.addStretch()
        return layout

    # ── Stats ───────────────────────────────────────────────────────────────

    def _stats(self) -> QHBoxLayout:
        try:
            saved = self._db.conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
            items = self._db.conn.execute(
                "SELECT COUNT(*) FROM shopping_items WHERE checked=0"
            ).fetchone()[0]
            meals = self._db.conn.execute(
                "SELECT COUNT(*) FROM meal_plans WHERE week_start=?", (_week_start(),)
            ).fetchone()[0]
        except Exception:
            saved = items = meals = 0
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(_stat_card("fa5s.calendar-check", str(meals), "Meals this week", "#4caf8a", lambda: self._navigate_to(2)))
        row.addWidget(_stat_card("fa5s.book-open",       str(saved), "Saved recipes",   "#7c6af7", lambda: self._navigate_to(1)))
        row.addWidget(_stat_card("fa5s.shopping-basket", str(items), "Items in list",   "#f0a500", lambda: self._navigate_to(5)))
        return row

    # ── Today's Plan ────────────────────────────────────────────────────────

    def _today_plan(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(0)

        # ── Header ──
        hdr = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(qta.icon("fa5s.sun", color="#4caf8a").pixmap(QSize(20, 20)))
        ic.setStyleSheet("background: transparent;")
        title = QLabel("TODAY'S PLAN")
        title.setStyleSheet(
            f"background: transparent; color: {_tm.c('#888888', '#666666')};"
            " font-size: 13px; font-weight: 700; letter-spacing: 1px;"
        )
        date_badge = QLabel(datetime.now().strftime("%a %d %b"))
        date_badge.setStyleSheet(
            "background: rgba(255,107,53,0.12); color: #ff6b35;"
            " border-radius: 5px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
        )
        hdr.addWidget(ic)
        hdr.addSpacing(8)
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(date_badge)
        layout.addLayout(hdr)
        layout.addSpacing(10)

        today_name = datetime.now().strftime("%A")
        try:
            rows = self._db.conn.execute(
                "SELECT meal_type, custom_name FROM meal_plans "
                "WHERE week_start=? AND day_of_week=?",
                (_week_start(), today_name)
            ).fetchall()
            meals_today = {r["meal_type"]: r["custom_name"] for r in rows}
        except Exception:
            meals_today = {}

        layout.addStretch(1)
        meal_defs = [
            ("breakfast", "fa5s.egg",            "#ff9a5c", "BREAKFAST"),
            ("lunch",     "fa5s.utensils",       "#34d399", "LUNCH"),
            ("dinner",    "fa5s.concierge-bell", "#60a5fa", "DINNER"),
            ("snack",     "fa5s.apple-alt",      "#f0a500", "SNACK"),
        ]
        for i, (meal_type, icon_name, colour, label) in enumerate(meal_defs):
            layout.addWidget(self._plan_row(label, icon_name, colour, meals_today.get(meal_type, "")))
            if i < len(meal_defs) - 1:
                layout.addSpacing(6)
        layout.addStretch(1)
        return card

    def _plan_row(self, meal: str, icon_name: str, colour: str, meal_name: str) -> QWidget:
        row = QWidget()
        row.setObjectName("meal-slot")
        row.setFixedHeight(48)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 4, 14, 4)
        rl.setSpacing(0)

        # Left colour accent strip
        strip = QWidget()
        strip.setFixedWidth(4)
        strip.setStyleSheet(f"background: {colour}; border-radius: 2px;")
        rl.addWidget(strip)
        rl.addSpacing(12)

        ic = QLabel()
        ic.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(16, 16)))
        ic.setStyleSheet("background: transparent;")
        ic.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        rl.addWidget(ic)
        rl.addSpacing(10)

        info_col = QVBoxLayout()
        info_col.setSpacing(3)
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        type_lbl = QLabel(meal)
        type_lbl.setStyleSheet(
            f"background: transparent; color: {colour};"
            " font-size: 10px; font-weight: 700; letter-spacing: 0.8px;"
        )
        if meal_name:
            val_lbl = QLabel(meal_name[:36])
            val_lbl.setStyleSheet(
                f"background: transparent; color: {_tm.c('#e0e0e0', '#1a1a1a')};"
                " font-size: 13px; font-weight: 600;"
            )
        else:
            val_lbl = QLabel("+ Add meal")
            val_lbl.setStyleSheet(
                f"background: transparent; color: {_tm.c('#383838', '#aaaaaa')}; font-size: 12px;"
            )
        info_col.addWidget(type_lbl)
        info_col.addWidget(val_lbl)
        rl.addLayout(info_col, 1)
        row.mousePressEvent = lambda e: self._navigate_to(2)
        return row

    # ── Recent Recipes ──────────────────────────────────────────────────────

    def _recent_recipes(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(0)

        # ── Header ──
        hdr = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(qta.icon("fa5s.book-open", color="#7c6af7").pixmap(QSize(20, 20)))
        ic.setStyleSheet("background: transparent;")
        title = QLabel("RECENT RECIPES")
        title.setStyleSheet(
            f"background: transparent; color: {_tm.c('#888888', '#666666')};"
            " font-size: 13px; font-weight: 700; letter-spacing: 1px;"
        )
        see_all = QPushButton("See all →")
        see_all.setObjectName("ghost-btn")
        see_all.setFixedHeight(24)
        see_all.clicked.connect(lambda: self._navigate_to(1))
        hdr.addWidget(ic)
        hdr.addSpacing(8)
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(see_all)
        layout.addLayout(hdr)
        layout.addSpacing(10)

        try:
            recipes = self._db.conn.execute(
                "SELECT id, title, ready_mins, is_favourite, data_json "
                "FROM recipes ORDER BY saved_at DESC LIMIT 3"
            ).fetchall()
        except Exception:
            recipes = []

        if recipes:
            layout.addStretch(1)
            for i, recipe in enumerate(recipes):
                layout.addWidget(self._recipe_row(recipe))
                if i < len(recipes) - 1:
                    layout.addSpacing(6)
            layout.addStretch(1)
        else:
            layout.addStretch()
            ph = QLabel("No saved recipes yet")
            ph.setObjectName("placeholder-text")
            ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub = QLabel("Head to Recipes to save your first dish")
            sub.setObjectName("placeholder-sub")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(ph)
            layout.addWidget(sub)
            layout.addStretch()

        return card

    def _recipe_row(self, recipe) -> QWidget:
        row = QWidget()
        row.setObjectName("meal-slot")
        row.setFixedHeight(48)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 0, 14, 0)
        rl.setSpacing(12)
        rl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ic = QLabel()
        ic.setPixmap(qta.icon("fa5s.utensils", color="#7c6af7").pixmap(QSize(16, 16)))
        ic.setStyleSheet("background: transparent;")
        ic.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        info_col = QVBoxLayout()
        info_col.setSpacing(3)
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title_txt = recipe["title"]
        name_lbl = QLabel(title_txt[:44] + ("…" if len(title_txt) > 44 else ""))
        name_lbl.setStyleSheet(
            f"background: transparent; color: {_tm.c('#e0e0e0', '#1a1a1a')}; font-size: 13px; font-weight: 600;"
        )
        tag_str = ""
        try:
            tags = json.loads(recipe["data_json"] or "{}").get("tags", [])
            if tags:
                tag_str = tags[0].title()
        except Exception:
            pass
        sub_parts = []
        if recipe["ready_mins"]:
            sub_parts.append(f"{recipe['ready_mins']} min")
        if tag_str:
            sub_parts.append(tag_str)
        sub_lbl = QLabel("  ·  ".join(sub_parts) if sub_parts else "")
        sub_lbl.setStyleSheet(
            f"background: transparent; color: {_tm.c('#555555', '#888888')}; font-size: 11px;"
        )
        info_col.addWidget(name_lbl)
        info_col.addWidget(sub_lbl)
        fav_lbl = QLabel()
        if recipe["is_favourite"]:
            fav_lbl.setPixmap(qta.icon("fa5s.star", color="#f0a500").pixmap(QSize(13, 13)))
        fav_lbl.setFixedWidth(16)
        fav_lbl.setStyleSheet("background: transparent;")
        fav_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        rl.addWidget(ic)
        rl.addLayout(info_col, 1)
        rl.addWidget(fav_lbl)
        row.mousePressEvent = lambda e: self._navigate_to(1)
        return row

    # ── Dishy Teaser ────────────────────────────────────────────────────────

    def _dishy_teaser(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # Custom header — bigger robot icon + full "AI POWERED" badge
        hdr = QHBoxLayout()
        robot_ic = QLabel()
        robot_ic.setPixmap(qta.icon("fa5s.robot", color="#34d399").pixmap(QSize(22, 22)))
        robot_ic.setStyleSheet("background: transparent;")
        title_lbl = QLabel("DISHY")
        title_lbl.setStyleSheet(
            f"background: transparent; color: {_tm.c('#888888', '#666666')};"
            " font-size: 13px; font-weight: 700; letter-spacing: 1px;"
        )
        badge = QLabel("AI POWERED")
        badge.setStyleSheet(
            "background: rgba(52,211,153,0.15); color: #34d399;"
            " border-radius: 5px; padding: 4px 10px; font-size: 10px; font-weight: 700;"
            " border: 1px solid rgba(52,211,153,0.3);"
        )
        hdr.addWidget(robot_ic)
        hdr.addSpacing(8)
        hdr.addWidget(title_lbl)
        hdr.addStretch()
        hdr.addWidget(badge)
        layout.addLayout(hdr)

        sub_lbl = QLabel("Your AI cooking assistant — ask anything")
        sub_lbl.setStyleSheet(
            f"background: transparent; color: {_tm.c('#555555', '#888888')}; font-size: 13px;"
        )
        layout.addWidget(sub_lbl)
        layout.addStretch(1)

        # 2 prompt chips side by side
        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        for text, icon in _DISHY_CHIPS:
            chip = QPushButton(f"  {text}")
            chip.setIcon(qta.icon(icon, color="#34d399"))
            chip.setIconSize(QSize(14, 14))
            chip.setFixedHeight(42)
            chip.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                f"QPushButton {{"
                f"  background: {_tm.c('#181818', '#f0f0f0')};"
                f"  color: {_tm.c('#c0c0c0', '#1a1a1a')};"
                f"  border: 1px solid {_tm.c('#242424', '#e0e0e0')};"
                f"  border-radius: 9px; font-size: 12px; text-align: left; padding: 0 10px 0 6px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background: {_tm.c('#1d1d1d', '#e8e8e8')};"
                f"  border-color: rgba(52,211,153,0.35);"
                f"  color: {_tm.c('#e0e0e0', '#111111')};"
                f"}}"
                f"QPushButton:pressed {{ background: {_tm.c('#252525', '#dddddd')}; }}"
            )
            chip.clicked.connect(lambda _, t=text: self._on_dishy_chip(t))
            chips_row.addWidget(chip)
        layout.addLayout(chips_row)

        # Inline input — larger
        input_container = QWidget()
        input_container.setObjectName("dishy-input-box")
        input_container.setFixedHeight(46)
        input_container.setStyleSheet(
            f"QWidget#dishy-input-box {{ background: {_tm.c('#161616', '#f0f0f0')}; border-radius: 10px;"
            f" border: 1px solid {_tm.c('#2a2a2a', '#e0e0e0')}; }}"
        )
        ic_layout = QHBoxLayout(input_container)
        ic_layout.setContentsMargins(14, 0, 7, 0)
        ic_layout.setSpacing(6)
        ic_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        mini_input = QLineEdit()
        mini_input.setPlaceholderText("Ask Dishy anything…")
        mini_input.setStyleSheet(
            f"background: transparent; border: none; padding: 0; font-size: 13px;"
            f" color: {_tm.c('#e8e8e8', '#1a1a1a')};"
        )
        send_btn = QPushButton()
        send_btn.setFixedSize(32, 32)
        send_btn.setIcon(qta.icon("fa5s.paper-plane", color="#ffffff"))
        send_btn.setIconSize(QSize(14, 14))
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(
            "QPushButton { background: #34d399; border-radius: 8px; border: none; }"
            "QPushButton:hover { background: #4ae3a8; }"
            "QPushButton:pressed { background: #2ac48a; }"
        )

        def _send_mini():
            text = mini_input.text().strip()
            if text:
                mini_input.clear()
                self._on_dishy_chip(text)

        mini_input.returnPressed.connect(_send_mini)
        send_btn.clicked.connect(_send_mini)
        ic_layout.addWidget(mini_input, 1)
        ic_layout.addWidget(send_btn)
        layout.addStretch(1)
        layout.addWidget(input_container)
        return card

    def _on_dishy_chip(self, text: str):
        self._navigate_to(6)
        self._trigger_dishy(text)

    # ── Quick Actions strip ─────────────────────────────────────────────────

    def _quick_actions_strip(self) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(wrap)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(10)
        for icon_name, label, colour, cb in [
            ("fa5s.search",        "Recipes",      "#7c6af7", lambda: self._navigate_to(1)),
            ("fa5s.calendar-plus", "Meal Planner", "#4caf8a", lambda: self._navigate_to(2)),
            ("fa5s.heartbeat",     "Nutrition",    "#e05c7a", lambda: self._navigate_to(3)),
            ("fa5s.shopping-cart", "Shopping",     "#f0a500", lambda: self._navigate_to(5)),
            ("fa5s.robot",         "Dishy",        "#34d399", lambda: self._navigate_to(6)),
        ]:
            btn = QPushButton()
            btn.setObjectName("quick-action-btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(38)
            btn.clicked.connect(cb)
            bl = QHBoxLayout(btn)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(7)
            bl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            il = QLabel()
            il.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(18, 18)))
            il.setStyleSheet("background: transparent;")
            il.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            tl = QLabel(label)
            tl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            tl.setStyleSheet(
                f"background: transparent; color: {_tm.c('#c0c0c0', '#1a1a1a')}; font-size: 12px; font-weight: 600;"
            )
            bl.addWidget(il)
            bl.addWidget(tl)
            hl.addWidget(btn)
        return wrap

    # ── Macro Rings card ────────────────────────────────────────────────────

    def _macro_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        hdr = _card_header("fa5s.heartbeat", "#e05c7a", "TODAY'S INTAKE")
        nav_btn = QPushButton("Full log →")
        nav_btn.setObjectName("ghost-btn")
        nav_btn.setFixedHeight(22)
        nav_btn.clicked.connect(lambda: self._navigate_to(3))
        hdr.addWidget(nav_btn)
        layout.addLayout(hdr)

        rings_row = QHBoxLayout()
        rings_row.setSpacing(0)
        rings_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        db_goals = get_macro_goals(self._db)
        for key, label, unit, colour in _DASH_MACROS:
            ring = MacroRing(colour, db_goals.get(key, 0.0), unit, size=90)
            self._macro_rings[key] = ring
            cell = QVBoxLayout()
            cell.setSpacing(4)
            cell.setContentsMargins(0, 0, 0, 0)
            cell.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            cell.addWidget(ring, 0, Qt.AlignmentFlag.AlignHCenter)
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"background: transparent; color: {_tm.c('#666666', '#888888')};"
                " font-size: 11px; font-weight: 600;"
            )
            cell.addWidget(lbl)
            w = QWidget()
            w.setStyleSheet("background: transparent;")
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            w.setLayout(cell)
            rings_row.addWidget(w)

        layout.addStretch(1)
        layout.addLayout(rings_row)
        layout.addStretch(1)
        return card

    def _refresh_macros(self):
        # Read from today's meal plan (same source as the Nutrition page since v0.36)
        totals = {k: 0.0 for k in ("kcal", "protein_g", "carbs_g", "fat_g")}
        try:
            slots = self._db.get_today_meal_plan_with_nutrition()
            for slot in slots:
                per_s = json.loads(slot.get("data_json") or "{}").get("nutrition_per_serving", {})
                for k in totals:
                    totals[k] += float(per_s.get(k, 0) or 0)
        except Exception:
            pass
        for key, ring in self._macro_rings.items():
            ring.set_value(totals.get(key, 0.0))

    def _on_goals_changed(self):
        """Update ring goals instantly when the user changes them in Settings."""
        goals = get_macro_goals(self._db)
        for key, ring in self._macro_rings.items():
            ring.set_goal(goals.get(key, 0.0))

    def _on_kitchen_changed(self):
        """Refresh the kitchen preview and expiry banner in-place when any pantry item changes."""
        try:
            if self._kitchen_preview is not None:
                self._kitchen_preview.refresh()
        except RuntimeError:
            pass
        try:
            if self._expiry_card is not None:
                self._expiry_card.refresh()
        except RuntimeError:
            pass

    # ── Shopping Preview ────────────────────────────────────────────────────

    def _scroll_style(self) -> str:
        return (
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { background: transparent; width: 4px; margin: 0; }"
            f"QScrollBar::handle:vertical {{ background: {_tm.c('#2a2a2a', '#cccccc')};"
            " border-radius: 2px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

    def _shopping_preview(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        basket_ic = QLabel()
        basket_ic.setPixmap(qta.icon("fa5s.shopping-basket", color="#f0a500").pixmap(QSize(20, 20)))
        basket_ic.setStyleSheet("background: transparent;")
        title_lbl = QLabel("SHOPPING LIST")
        title_lbl.setStyleSheet(
            f"background: transparent; color: {_tm.c('#888888', '#666666')};"
            " font-size: 13px; font-weight: 700; letter-spacing: 1px;"
        )
        view_btn = QPushButton("View →")
        view_btn.setObjectName("ghost-btn")
        view_btn.setFixedHeight(24)
        view_btn.clicked.connect(lambda: self._navigate_to(5))
        hdr.addWidget(basket_ic)
        hdr.addSpacing(8)
        hdr.addWidget(title_lbl)
        hdr.addStretch()
        hdr.addWidget(view_btn)
        layout.addLayout(hdr)

        try:
            items = self._db.conn.execute(
                "SELECT id, name, quantity, unit, checked FROM shopping_items "
                "WHERE checked=0 ORDER BY added_at DESC"
            ).fetchall()
        except Exception:
            items = []

        if items:
            # Group items by category
            from collections import defaultdict
            cat_map = {c[0]: c for c in CATEGORIES}
            grouped: dict = defaultdict(list)
            for item in items:
                grouped[_categorize(item["name"])].append(item)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setStyleSheet(self._scroll_style())
            inner = QWidget()
            inner_layout = QVBoxLayout(inner)
            inner_layout.setContentsMargins(0, 0, 4, 0)
            inner_layout.setSpacing(3)

            txt_main = _tm.c('#e0e0e0', '#1a1a1a')
            txt_sub  = _tm.c('#666666', '#888888')

            # Render in CATEGORIES order, then any extras
            seen_cats = []
            for cat_name, cat_icon, cat_colour in CATEGORIES:
                if cat_name not in grouped:
                    continue
                seen_cats.append(cat_name)
                cat_items = grouped[cat_name]

                # Category header
                hdr_w = QWidget()
                hdr_w.setStyleSheet("background: transparent;")
                hdr_l = QHBoxLayout(hdr_w)
                hdr_l.setContentsMargins(0, 6, 0, 2)
                hdr_l.setSpacing(6)
                ic_lbl = QLabel()
                ic_lbl.setPixmap(qta.icon(cat_icon, color=cat_colour).pixmap(QSize(13, 13)))
                ic_lbl.setStyleSheet("background: transparent;")
                cat_lbl = QLabel(cat_name.upper())
                cat_lbl.setStyleSheet(
                    f"background: transparent; color: {cat_colour};"
                    " font-size: 10px; font-weight: 700; letter-spacing: 0.8px;"
                )
                cnt_lbl = QLabel(f"({len(cat_items)})")
                cnt_lbl.setStyleSheet(
                    f"background: transparent; color: {_tm.c('#555555', '#aaaaaa')}; font-size: 10px;"
                )
                hdr_l.addWidget(ic_lbl)
                hdr_l.addWidget(cat_lbl)
                hdr_l.addWidget(cnt_lbl)
                hdr_l.addStretch()
                inner_layout.addWidget(hdr_w)

                for item in cat_items:
                    item_row = QWidget()
                    item_row.setStyleSheet("background: transparent;")
                    item_row.setFixedHeight(34)
                    row_l = QHBoxLayout(item_row)
                    row_l.setContentsMargins(4, 0, 0, 0)
                    row_l.setSpacing(8)

                    cb = QCheckBox()
                    cb.setChecked(False)
                    cb.setStyleSheet(
                        "QCheckBox { background: transparent; spacing: 0px; }"
                        "QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px;"
                        f" border: 2px solid {_tm.c('#444444', '#cccccc')}; background: transparent; }}"
                        "QCheckBox::indicator:checked { background: #f0a500; border-color: #f0a500; }"
                    )

                    name_str = item["name"][:28] + ("…" if len(item["name"]) > 28 else "")
                    name_lbl = QLabel(name_str)
                    name_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                    name_lbl.setStyleSheet(
                        f"background: transparent; color: {txt_main}; font-size: 13px; font-weight: 500;"
                    )

                    qty_str = ""
                    if item["quantity"]:
                        qty_str = str(item["quantity"])
                        if item["unit"]:
                            qty_str += f" {item['unit']}"
                    qty_lbl = QLabel(qty_str)
                    qty_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    qty_lbl.setStyleSheet(
                        f"background: transparent; color: {txt_sub}; font-size: 11px;"
                    )

                    item_id = item["id"]

                    def _on_check(checked, iid=item_id, nlbl=name_lbl):
                        try:
                            self._db.conn.execute(
                                "UPDATE shopping_items SET checked=? WHERE id=?",
                                (1 if checked else 0, iid)
                            )
                            self._db.conn.commit()
                        except Exception:
                            pass
                        style_base = f"background: transparent; font-size: 13px; font-weight: 500;"
                        if checked:
                            nlbl.setStyleSheet(
                                style_base + f" color: {_tm.c('#444444', '#aaaaaa')};"
                                " text-decoration: line-through;"
                            )
                        else:
                            nlbl.setStyleSheet(style_base + f" color: {txt_main};")

                    cb.toggled.connect(_on_check)

                    row_l.addWidget(cb)
                    row_l.addWidget(name_lbl, 1)
                    row_l.addWidget(qty_lbl)
                    inner_layout.addWidget(item_row)

            inner_layout.addStretch()
            scroll.setWidget(inner)
            layout.addWidget(scroll, 1)

            count_lbl = QLabel(f"{len(items)} item{'s' if len(items) != 1 else ''} remaining")
            count_lbl.setStyleSheet(
                f"background: transparent; color: {_tm.c('#444444', '#999999')}; font-size: 11px;"
            )
            layout.addWidget(count_lbl)
        else:
            layout.addStretch()
            ph = QLabel("Shopping list is empty")
            ph.setObjectName("placeholder-text")
            ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(ph)
            layout.addStretch()

        return card

