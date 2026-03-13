"""Shopping List — rebuilt from scratch."""
from datetime import datetime
from collections import defaultdict

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QCheckBox, QSizePolicy, QFrame,
    QStackedWidget, QProgressBar,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter, QColor

from utils.theme import manager as theme_manager
from utils.themed_dialog import ThemedMessageBox
from utils.data_service import get_db
from utils.grocery_consolidation import consolidate_rows
from utils.platform_ops import run_apple_script, is_macos, open_path_in_default_app, user_documents_dir
from models.database import Database
from widgets.primary_button import PrimaryButton
from widgets.dishy_main_request_button import DishyMainRequestButton


# ── Category definitions ──────────────────────────────────────────────────────

CATEGORIES = [
    ("Produce",      "fa5s.seedling",        "#34d399"),
    ("Meat & Fish",  "fa5s.drumstick-bite",  "#ff9a5c"),
    ("Dairy & Eggs", "fa5s.egg",             "#f0a500"),
    ("Bakery",       "fa5s.bread-slice",     "#e05c7a"),
    ("Pantry",       "fa5s.box",             "#7c6af7"),
    ("Frozen",       "fa5s.snowflake",       "#4fc3f7"),
    ("Drinks",       "fa5s.mug-hot",         "#4caf8a"),
    ("Snacks",       "fa5s.cookie",          "#ff6b35"),
    ("Other",        "fa5s.shopping-basket", "#888888"),
]

_KEYWORDS = {
    "Produce": [
        "apple","banana","tomato","onion","garlic","pepper","carrot","spinach",
        "lettuce","cucumber","avocado","lemon","lime","orange","potato","sweet potato",
        "mushroom","broccoli","cauliflower","celery","basil","coriander","cilantro",
        "parsley","ginger","courgette","zucchini","aubergine","eggplant","kale",
        "spring onion","shallot","beetroot","radish","asparagus","leek","fennel",
        "pea","corn","sweetcorn","chilli","herb","salad","rocket","arugula",
        "pear","grape","strawberry","raspberry","blueberry","cherry","mango",
        "pineapple","watermelon","melon","peach","plum","apricot","fig",
        "pomegranate","kiwi","papaya","lychee","fresh","vegetable","fruit","veg",
    ],
    "Meat & Fish": [
        "chicken","beef","pork","lamb","fish","salmon","tuna","prawn","shrimp",
        "sausage","bacon","turkey","mince","steak","duck","ham","salami","pepperoni",
        "chorizo","anchovy","cod","haddock","sea bass","trout","mackerel","sardine",
        "crab","lobster","squid","scallop","mussel","clam","oyster","meat","poultry",
        "venison","veal","brisket","ribs","fillet","breast","thigh","drumstick",
        "meatball","burger","lardons","pancetta","prosciutto",
    ],
    "Dairy & Eggs": [
        "milk","cheese","yogurt","yoghurt","butter","cream","egg","feta",
        "mozzarella","parmesan","cheddar","brie","camembert","gouda","ricotta",
        "mascarpone","sour cream","double cream","single cream","custard","ghee",
        "kefir","halloumi","cottage cheese","quark","dairy",
    ],
    "Bakery": [
        "bread","roll","bun","croissant","bagel","sourdough","pitta","pita",
        "tortilla","wrap","naan","flatbread","brioche","crumpet","focaccia",
        "ciabatta","baguette","rye bread","wholemeal",
    ],
    "Pantry": [
        "pasta","rice","noodle","oil","sauce","tin","canned","bean","lentil",
        "chickpea","stock","broth","vinegar","soy","sugar","honey","cumin",
        "paprika","oregano","cinnamon","curry","coconut milk","tomato paste",
        "olive oil","vegetable oil","flour","baking powder","baking soda","vanilla",
        "cocoa","mustard","ketchup","mayo","pesto","tahini","miso","sriracha",
        "dried","seasoning","salt","spice","oat","granola","cereal","nut","almond",
        "cashew","peanut","walnut","pecan","pistachio","seed","raisin","jam",
        "peanut butter","syrup","yeast","breadcrumb","quinoa","couscous","barley",
        "black bean","kidney bean","cannellini",
    ],
    "Frozen": ["frozen"],
    "Drinks": [
        "water","juice","coffee","tea","wine","beer","soda","squash","cordial",
        "smoothie","kombucha","sparkling","lager","ale","champagne","prosecco",
        "cider","whiskey","gin","vodka","rum","drink","beverage","coconut water",
    ],
    "Snacks": [
        "chocolate","biscuit","cookie","crisp","chip","cake","candy","sweet",
        "brownie","flapjack","popcorn","pretzel","snack","bar","muffin",
        "donut","doughnut","pastry","tart","pie","pudding","jelly","gummy",
        "marshmallow",
    ],
}


def _categorize(name: str) -> str:
    n = name.lower()
    for cat, kws in _KEYWORDS.items():
        if any(k in n for k in kws):
            return cat
    return "Other"


# ── Thin progress bar ─────────────────────────────────────────────────────────

class _MiniBar(QWidget):
    def __init__(self, color="#f0a500", parent=None):
        super().__init__(parent)
        self._color = color
        self._pct = 0.0
        self.setFixedHeight(3)

    def set_pct(self, v: float):
        self._pct = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        track = QColor("#1e1e1e") if theme_manager.mode == "dark" else QColor("#e0e0e0")
        p.fillRect(self.rect(), track)
        if self._pct > 0:
            r = self.rect()
            r.setWidth(int(self.width() * self._pct))
            p.fillRect(r, QColor(self._color))
        p.end()


# ── Individual item row ───────────────────────────────────────────────────────

class _Item(QWidget):
    def __init__(self, text, db_id, checked, source, on_toggle, on_delete, parent):
        super().__init__(parent)
        self.db_id = db_id
        self._source = source
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 10, 0)
        row.setSpacing(10)

        self._chk = QCheckBox(text, self)
        self._chk.setChecked(checked)
        self._chk.toggled.connect(self._on_toggle)
        self._chk.toggled.connect(on_toggle)

        self._badge = QLabel("plan", self)
        self._badge.setFixedHeight(16)
        self._badge.setVisible(source == "meal_plan")

        self._del = QPushButton(self)
        self._del.setIcon(qta.icon("fa5s.trash-alt", color="#555555"))
        self._del.setIconSize(QSize(11, 11))
        self._del.setFixedSize(26, 26)
        self._del.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del.clicked.connect(on_delete)
        self._del.enterEvent = lambda _: self._del.setIcon(qta.icon("fa5s.trash-alt", color="#f0a500"))
        self._del.leaveEvent = lambda _: self._del.setIcon(qta.icon("fa5s.trash-alt", color="#555555"))

        row.addWidget(self._chk, 1)
        row.addWidget(self._badge)
        row.addWidget(self._del)

        self._style(checked)

    def _on_toggle(self, checked):
        self._style(checked)

    def _style(self, checked):
        dark = theme_manager.mode == "dark"
        ind = (
            "QCheckBox{outline:0}"
            "QCheckBox::indicator{width:18px;height:18px;border-radius:9px;border:1.5px solid;image:none}"
            f"QCheckBox::indicator:unchecked{{background:transparent;border-color:{'#444444' if dark else '#bbbbbb'};image:none}}"
            "QCheckBox::indicator:unchecked:hover{background:transparent;border-color:#f0a500;image:none}"
            "QCheckBox::indicator:checked{background:#f0a500;border-color:#f0a500;image:none}"
            "QCheckBox::indicator:checked:hover{background:#ffb822;border-color:#ffb822;image:none}"
        )
        if checked:
            col = "#606060" if dark else "#aaaaaa"
            self._chk.setStyleSheet(
                f"QCheckBox{{color:{col};text-decoration:line-through;font-size:13px}}" + ind
            )
        else:
            col = "#d8d8d8" if dark else "#1a1a1a"
            self._chk.setStyleSheet(
                f"QCheckBox{{color:{col};font-size:13px}}" + ind
            )
        self._del.setStyleSheet("QPushButton{background:transparent;border:none;border-radius:5px}")
        if self._source == "meal_plan":
            bg = "#1e3a2e" if dark else "#e8f5ee"
            self._badge.setStyleSheet(
                f"color:#4caf8a;font-size:9px;font-weight:700;background:{bg};"
                "border-radius:4px;padding:1px 5px"
            )

    def apply_theme(self):
        self._style(self._chk.isChecked())

    def is_checked(self):
        return self._chk.isChecked()

    def item_text(self):
        return self._chk.text()


# ── Collapsible section card ──────────────────────────────────────────────────

class _Section(QWidget):
    def __init__(self, name, icon, color, parent):
        super().__init__(parent)
        self._name = name
        self._icon = icon
        self._color = color
        self._open = True
        self._items: list[_Item] = []
        self._build()
        self._restyle()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Header button
        self._hdr = QPushButton(self)
        self._hdr.setFixedHeight(44)
        self._hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hdr.setFlat(True)
        self._hdr.clicked.connect(self._toggle)

        hl = QHBoxLayout(self._hdr)
        hl.setContentsMargins(14, 0, 14, 0)
        hl.setSpacing(10)

        self._ico = QLabel(self._hdr)
        self._ico.setPixmap(qta.icon(self._icon, color=self._color).pixmap(14, 14))
        self._ico.setStyleSheet("background:transparent")

        self._lbl = QLabel(self._name, self._hdr)
        self._lbl.setStyleSheet(
            f"color:{self._color};font-size:12px;font-weight:700;"
            "letter-spacing:0.5px;background:transparent"
        )

        self._count = QLabel("0", self._hdr)
        self._count.setFixedHeight(20)
        self._count.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._prog_lbl = QLabel("", self._hdr)
        self._prog_lbl.setStyleSheet("font-size:11px;background:transparent")

        self._chev = QLabel(self._hdr)
        self._chev.setStyleSheet("background:transparent")
        self._set_chev(True)

        hl.addWidget(self._ico)
        hl.addWidget(self._lbl)
        hl.addStretch()
        hl.addWidget(self._prog_lbl)
        hl.addWidget(self._count)
        hl.addWidget(self._chev)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        self._sep = sep

        self._body = QWidget(self)
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(0, 4, 0, 8)
        bl.setSpacing(0)
        self._body_layout = bl

        vbox.addWidget(self._hdr)
        vbox.addWidget(self._sep)
        vbox.addWidget(self._body)

    def _set_chev(self, open_):
        name = "fa5s.chevron-down" if open_ else "fa5s.chevron-right"
        col = "#666666" if theme_manager.mode == "dark" else "#aaaaaa"
        self._chev.setPixmap(qta.icon(name, color=col).pixmap(10, 10))

    def _toggle(self):
        self._open = not self._open
        self._body.setVisible(self._open)
        self._sep.setVisible(self._open)
        self._set_chev(self._open)

    def _restyle(self):
        dark = theme_manager.mode == "dark"
        card_bg = "#111111" if dark else "#ffffff"
        sep_col = "#2a2a2a" if dark else "#eeeeee"
        hdr_hover = "#1a1a1a" if dark else "#f8f8f8"
        muted = "#555555" if dark else "#bbbbbb"

        r, g, b = int(self._color[1:3], 16), int(self._color[3:5], 16), int(self._color[5:], 16)
        badge_bg = f"rgba({r},{g},{b},38)" if dark else f"rgba({r},{g},{b},28)"

        self.setStyleSheet(
            f"_Section{{background:{card_bg};border-radius:12px}}"
        )
        self._hdr.setStyleSheet(
            f"QPushButton{{background:transparent;border:none;border-radius:12px}}"
            f"QPushButton:hover{{background:{hdr_hover}}}"
        )
        self._sep.setStyleSheet(f"background:{sep_col};border:none")
        self._body.setStyleSheet("background:transparent")
        self._count.setStyleSheet(
            f"color:{self._color};font-size:11px;font-weight:700;"
            f"background:{badge_bg};border-radius:8px;padding:0 7px"
        )
        self._prog_lbl.setStyleSheet(f"color:{muted};font-size:11px;background:transparent")
        self._set_chev(self._open)

    def add_item(self, item: "_Item"):
        self._items.append(item)
        self._body_layout.addWidget(item)
        self._update_counts()

    def _update_counts(self):
        total = len(self._items)
        done = sum(1 for i in self._items if i.is_checked())
        self._count.setText(str(total))
        self._prog_lbl.setText(f"{done}/{total}" if total else "")

    def update_counts(self):
        self._update_counts()

    def apply_theme(self):
        self._restyle()
        for item in self._items:
            item.apply_theme()

    def all_items(self):
        return self._items


# ── Storage inference helper ──────────────────────────────────────────────────

_FREEZER_KWS = [
    "frozen", "ice cream", "fish fingers", "fish", "prawns", "mince", "burger",
    "ice", "sorbet", "gelato",
]
_FRIDGE_KWS = [
    "milk", "butter", "cheese", "yoghurt", "yogurt", "cream", "egg", "lettuce",
    "spinach", "kale", "chicken", "beef", "pork", "salmon", "tuna", "ham", "bacon",
    "juice", "tofu", "tempeh", "halloumi", "mozzarella", "cheddar", "brie",
    "feta", "ricotta", "sour cream", "hummus", "dip",
]


def _infer_storage(name: str) -> str:
    n = name.lower()
    if any(k in n for k in _FREEZER_KWS):
        return "Freezer"
    if any(k in n for k in _FRIDGE_KWS):
        return "Fridge"
    return "Pantry"


# ── Live Shop item row ────────────────────────────────────────────────────────

class _LiveItem(QWidget):
    def __init__(self, row_data: dict, on_toggle, parent: QWidget):
        super().__init__(parent)
        self._row = row_data
        self.setMinimumHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(14)

        self._chk = QCheckBox(self)
        self._chk.setChecked(bool(row_data.get("checked", False)))
        self._chk.toggled.connect(on_toggle)
        self._chk.toggled.connect(self._on_style)
        layout.addWidget(self._chk)

        name_lbl = QLabel(row_data["name"], self)
        name_lbl.setStyleSheet("font-size:16px;font-weight:600;background:transparent")
        self._name_lbl = name_lbl

        qty = row_data.get("quantity") or ""
        unit = row_data.get("unit") or ""
        detail = f"{qty} {unit}".strip()
        detail_lbl = QLabel(detail, self)
        detail_lbl.setStyleSheet("font-size:13px;background:transparent")
        detail_lbl.setVisible(bool(detail))
        self._detail_lbl = detail_lbl

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.addWidget(self._name_lbl)
        text_col.addWidget(self._detail_lbl)
        layout.addLayout(text_col, 1)

        self._on_style(self._chk.isChecked())

    def _on_style(self, checked: bool):
        dark = theme_manager.mode == "dark"
        name_col = "#888888" if checked else ("#f0f0f0" if dark else "#1a1a1a")
        detail_col = "#888888" if dark else "#666666"
        strike = "text-decoration:line-through;" if checked else ""
        self._name_lbl.setStyleSheet(
            f"font-size:16px;font-weight:600;background:transparent;color:{name_col};{strike}"
        )
        self._detail_lbl.setStyleSheet(
            f"font-size:13px;background:transparent;color:{detail_col}"
        )
        ind = (
            "QCheckBox{outline:0}"
            "QCheckBox::indicator{width:22px;height:22px;border-radius:11px;border:2px solid;image:none}"
            f"QCheckBox::indicator:unchecked{{background:transparent;border-color:{'#444444' if dark else '#bbbbbb'};image:none}}"
            "QCheckBox::indicator:checked{background:#34d399;border-color:#34d399;image:none}"
        )
        self._chk.setStyleSheet(ind)

    def is_checked(self) -> bool:
        return self._chk.isChecked()

    def set_checked(self, val: bool):
        self._chk.blockSignals(True)
        self._chk.setChecked(val)
        self._chk.blockSignals(False)
        self._on_style(val)

    def apply_theme(self):
        self._on_style(self._chk.isChecked())


# ── Live Shop tab ─────────────────────────────────────────────────────────────

class _LiveShopTab(QWidget):
    def __init__(self, db: Database, sync_fn=None, notify_my_kitchen_fn=None,
                 navigate_fn=None, parent: QWidget = None):
        super().__init__(parent)
        self._db = db
        self._sync_fn = sync_fn
        self._notify_my_kitchen_fn = notify_my_kitchen_fn
        self._navigate_fn = navigate_fn
        self._live_items: list[_LiveItem] = []
        self._item_rows: list[dict] = []
        self._live_headers: list[QWidget] = []
        self._build()
        theme_manager.theme_changed.connect(self.apply_theme)

    def _build(self):
        dark = theme_manager.mode == "dark"
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Green header banner — parent=self so no floating window
        banner = QWidget(self)
        banner.setFixedHeight(44)
        banner_bg = "#0d3d2a" if dark else "#d1fae5"
        banner.setStyleSheet(f"background:{banner_bg};border-radius:10px")
        bl = QHBoxLayout(banner)
        bl.setContentsMargins(16, 0, 16, 0)
        banner_lbl = QLabel("Live Shop  •  tick items as you place them in your basket", banner)
        banner_lbl.setStyleSheet("color:#34d399;font-size:13px;font-weight:600;background:transparent")
        bl.addWidget(banner_lbl)
        root.addWidget(banner)
        root.addSpacing(10)

        # Scroll area — parent=self
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;border:none")

        # Content widget — parent=scroll (QScrollArea takes ownership via setWidget)
        self._content = QWidget(scroll)
        self._content.setStyleSheet("background:transparent")
        self._vbox = QVBoxLayout(self._content)
        self._vbox.setContentsMargins(0, 0, 0, 0)
        self._vbox.setSpacing(2)

        self._empty_lbl = QLabel("Your shopping list is empty.", self._content)
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        muted = theme_manager.c("#888888", "#666666")
        self._empty_lbl.setStyleSheet(
            f"color:{muted};font-size:14px;background:transparent;padding:40px"
        )
        self._vbox.addWidget(self._empty_lbl)
        self._vbox.addStretch()
        scroll.setWidget(self._content)
        root.addWidget(scroll, 1)
        root.addSpacing(10)

        # Progress label — parent=self
        self._progress_lbl = QLabel("0 / 0 in basket", self)
        self._progress_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        muted2 = theme_manager.c("#888888", "#666666")
        self._progress_lbl.setStyleSheet(
            f"font-size:13px;color:{muted2};background:transparent"
        )
        root.addWidget(self._progress_lbl)
        root.addSpacing(6)

        # Progress bar — parent=self
        self._progress_bar = QProgressBar(self)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(
            "QProgressBar{border:none;border-radius:3px;"
            f"background:{theme_manager.c('#1e1e1e', '#e0e0e0')};}}"
            "QProgressBar::chunk{background:#34d399;border-radius:3px}"
        )
        root.addWidget(self._progress_bar)
        root.addSpacing(10)

        # Finish shop button — parent=self
        self._finish_btn = QPushButton("  Finish Shop", self)
        self._finish_btn.setFixedHeight(42)
        self._finish_btn.setIcon(qta.icon("fa5s.check-double", color="#ffffff"))
        self._finish_btn.setIconSize(QSize(14, 14))
        self._finish_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._finish_btn.setStyleSheet(
            "QPushButton{background:#34d399;border:none;border-radius:10px;"
            "color:#ffffff;font-size:14px;font-weight:700}"
            "QPushButton:hover{background:#2ebd8a}"
        )
        self._finish_btn.clicked.connect(self._complete_shop)
        root.addWidget(self._finish_btn)

    def _make_category_header(self, cat_name: str, icon_name: str, color: str) -> QWidget:
        """Create a slim category divider header widget."""
        dark = theme_manager.mode == "dark"
        hdr = QWidget(self._content)
        hdr.setFixedHeight(32)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(4, 0, 4, 0)
        hl.setSpacing(8)

        ico_lbl = QLabel(hdr)
        ico_lbl.setPixmap(qta.icon(icon_name, color=color).pixmap(12, 12))
        ico_lbl.setStyleSheet("background:transparent")

        txt_lbl = QLabel(cat_name, hdr)
        txt_lbl.setStyleSheet(
            f"color:{color};font-size:11px;font-weight:700;"
            "letter-spacing:0.5px;background:transparent"
        )

        line = QFrame(hdr)
        line.setFrameShape(QFrame.Shape.HLine)
        sep_col = "#2a2a2a" if dark else "#e8e8e8"
        line.setStyleSheet(f"background:{sep_col};border:none;max-height:1px")

        hl.addWidget(ico_lbl)
        hl.addWidget(txt_lbl)
        hl.addWidget(line, 1)
        return hdr

    def refresh(self):
        # Clear existing live items and category headers
        for w in self._live_items + self._live_headers:
            w.hide()
            self._vbox.removeWidget(w)
            w.deleteLater()
        self._live_items.clear()
        self._live_headers.clear()
        self._item_rows.clear()

        try:
            rows = self._db.get_shopping_items()
        except Exception:
            rows = []

        self._empty_lbl.setVisible(not rows)

        if rows:
            # Group by category preserving CATEGORIES order
            grouped = defaultdict(list)
            for row in rows:
                grouped[_categorize(row["name"])].append(dict(row))

            pos = 0  # insert before the trailing stretch
            for cat_name, icon_name, color in CATEGORIES:
                items = grouped.get(cat_name, [])
                if not items:
                    continue

                hdr = self._make_category_header(cat_name, icon_name, color)
                self._live_headers.append(hdr)
                self._vbox.insertWidget(pos, hdr)
                pos += 1

                for row_d in items:
                    self._item_rows.append(row_d)

                    def _make_toggle(r):
                        def _toggle(checked):
                            self._db.toggle_shopping_item(r["id"], checked)
                            if checked:
                                self._add_to_pantry(r)
                            if self._sync_fn:
                                self._sync_fn()
                            if self._notify_my_kitchen_fn:
                                self._notify_my_kitchen_fn()
                            self._update_progress()
                        return _toggle

                    live_item = _LiveItem(row_d, _make_toggle(row_d), self._content)
                    self._live_items.append(live_item)
                    self._vbox.insertWidget(pos, live_item)
                    pos += 1

        self._update_progress()

    def _add_to_pantry(self, item_row: dict):
        name = item_row.get("name", "")
        if not name:
            return
        qty_raw = item_row.get("quantity", "")
        unit = item_row.get("unit", "") or ""
        try:
            qty = float(qty_raw) if qty_raw else None
        except (ValueError, TypeError):
            qty = None
        storage = _infer_storage(name)
        try:
            self._db.add_pantry_item(name, qty, unit, storage)
        except Exception:
            pass

    def _update_progress(self):
        total = len(self._live_items)
        done = sum(1 for w in self._live_items if w.is_checked())
        self._progress_lbl.setText(f"{done} / {total} in basket")
        self._progress_bar.setMaximum(max(total, 1))
        self._progress_bar.setValue(done)

    def _complete_shop(self):
        for i, w in enumerate(self._live_items):
            if not w.is_checked():
                w.set_checked(True)
                row = self._item_rows[i]
                self._db.toggle_shopping_item(row["id"], True)
                self._add_to_pantry(row)

        total = len(self._live_items)
        if self._notify_my_kitchen_fn:
            self._notify_my_kitchen_fn()
        if self._sync_fn:
            self._sync_fn()

        self._db.clear_checked_shopping_items()
        if self._sync_fn:
            self._sync_fn()

        ThemedMessageBox.information(
            self, "Shop Complete",
            f"{total} item{'s' if total != 1 else ''} added to My Kitchen.\n"
            "Your shopping list has been cleared."
        )
        self.refresh()

        if self._navigate_fn and total > 0:
            self._navigate_fn(4)

    def apply_theme(self, _=None):
        muted = theme_manager.c("#888888", "#666666")
        self._empty_lbl.setStyleSheet(
            f"color:{muted};font-size:14px;background:transparent;padding:40px"
        )
        self._progress_lbl.setStyleSheet(
            f"font-size:13px;color:{muted};background:transparent"
        )
        self._progress_bar.setStyleSheet(
            "QProgressBar{border:none;border-radius:3px;"
            f"background:{theme_manager.c('#1e1e1e', '#e0e0e0')};}}"
            "QProgressBar::chunk{background:#34d399;border-radius:3px}"
        )
        for w in self._live_items:
            w.apply_theme()


# ── Main view ─────────────────────────────────────────────────────────────────

class ShoppingListView(QWidget):
    def __init__(self, db: Database | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("view-container")
        self._db = db or get_db()
        self._sections: dict[str, _Section] = {}
        self._all_items: list[_Item] = []
        self._ask_dishy_fn = None
        self._sync_fn = None
        self._notify_my_kitchen_fn = None
        self._navigate_fn = None
        self._current_tab = "Shopping List"
        self._build_ui()

    def set_ask_dishy(self, fn):
        self._ask_dishy_fn = fn

    def set_sync_fn(self, fn):
        """Called by MainWindow to trigger cloud sync after list mutations."""
        self._sync_fn = fn
        if hasattr(self, "_tab_live_shop"):
            self._tab_live_shop._sync_fn = fn

    def set_notify_my_kitchen_fn(self, fn):
        """Called by MainWindow so Live Shop can refresh My Kitchen after adding items."""
        self._notify_my_kitchen_fn = fn
        if hasattr(self, "_tab_live_shop"):
            self._tab_live_shop._notify_my_kitchen_fn = fn

    def set_navigate_to_fn(self, fn):
        """Called by MainWindow so Finish Shop can navigate to My Kitchen."""
        self._navigate_fn = fn
        if hasattr(self, "_tab_live_shop"):
            self._tab_live_shop._navigate_fn = fn

    def _build_ui(self):
        self.setMinimumHeight(320)  # prevents the view from collapsing at small window heights
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 24)
        root.setSpacing(0)

        # ── Tab bar (top) ────────────────────────────────────────────────────
        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)
        tab_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._tab_btns: dict[str, QPushButton] = {}
        for tab_name in ("Shopping List", "Live Shop"):
            btn = QPushButton(tab_name)
            btn.setFixedHeight(34)
            btn.setCheckable(True)
            btn.setChecked(tab_name == self._current_tab)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, t=tab_name: self._switch_tab(t))
            self._tab_btns[tab_name] = btn
            tab_row.addWidget(btn)
        tab_row.addStretch()
        root.addLayout(tab_row)
        root.addSpacing(16)
        self._style_tabs()

        # ── Tab stack ────────────────────────────────────────────────────────
        self._view_stack = QStackedWidget(self)

        # Tab 0: existing shopping list UI
        self._tab_shopping = QWidget(self._view_stack)
        self._tab_shopping_layout = QVBoxLayout(self._tab_shopping)
        self._tab_shopping_layout.setContentsMargins(0, 0, 0, 0)
        self._tab_shopping_layout.setSpacing(0)
        self._view_stack.addWidget(self._tab_shopping)

        # Tab 1: Live Shop
        self._tab_live_shop = _LiveShopTab(
            self._db, self._sync_fn, self._notify_my_kitchen_fn, self._navigate_fn,
            parent=self._view_stack,
        )
        self._view_stack.addWidget(self._tab_live_shop)

        root.addWidget(self._view_stack, 1)

        # ── Now build the shopping list content into tab 0 ───────────────────
        self._build_shopping_tab()

        theme_manager.theme_changed.connect(self.apply_theme)
        self.load_from_db()

    def _switch_tab(self, tab_name: str):
        self._current_tab = tab_name
        for t, btn in self._tab_btns.items():
            btn.setChecked(t == tab_name)
        self._style_tabs()
        idx = {"Shopping List": 0, "Live Shop": 1}[tab_name]
        self._view_stack.setCurrentIndex(idx)
        if tab_name == "Live Shop":
            self._tab_live_shop.refresh()

    def _style_tabs(self):
        dark = theme_manager.mode == "dark"
        for name, btn in self._tab_btns.items():
            if btn.isChecked():
                btn.setStyleSheet(
                    "QPushButton{background:#f0a500;border:none;border-radius:17px;"
                    "color:#ffffff;font-size:13px;font-weight:600;padding:0 16px}"
                )
            else:
                unchecked_bg = "rgba(255,255,255,0.05)" if dark else "rgba(0,0,0,0.05)"
                unchecked_txt = "#888888" if dark else "#666666"
                border_col = "#2a2a2a" if dark else "#dddddd"
                btn.setStyleSheet(
                    f"QPushButton{{background:{unchecked_bg};border:1px solid {border_col};"
                    f"border-radius:17px;color:{unchecked_txt};font-size:13px;padding:0 16px}}"
                    f"QPushButton:hover{{background:{'rgba(255,255,255,0.08)' if dark else 'rgba(0,0,0,0.08)'}}}"
                )

    def _build_shopping_tab(self):
        """Build the existing shopping list UI into _tab_shopping_layout."""
        sl = self._tab_shopping_layout

        # Header
        self._title_lbl = QLabel("Shopping List")
        self._title_lbl.setObjectName("page-title")
        self._sub_lbl = QLabel("Tap a category to expand · check items off as you shop")
        self._sub_lbl.setObjectName("page-date")
        sl.addWidget(self._title_lbl)
        sl.addWidget(self._sub_lbl)
        sl.addSpacing(20)

        # Stats row
        self._stat_bar = QWidget(self)
        self._stat_bar.setObjectName("stat-bar")
        sb = QHBoxLayout(self._stat_bar)
        sb.setContentsMargins(16, 12, 16, 12)
        sb.setSpacing(0)

        def _chip(val, lbl, col):
            w = QWidget(self._stat_bar)
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(2)
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            n = QLabel(val, w)
            n.setAlignment(Qt.AlignmentFlag.AlignCenter)
            n.setStyleSheet(f"color:{col};font-size:22px;font-weight:700;background:transparent")
            t = QLabel(lbl, w)
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t.setStyleSheet("font-size:11px;font-weight:500;color:#888888;background:transparent")
            v.addWidget(n)
            v.addWidget(t)
            return w, n

        self._w_total, self._n_total = _chip("0", "total", "#f0a500")
        self._w_left,  self._n_left  = _chip("0", "to get", "#34d399")
        self._w_done,  self._n_done  = _chip("0", "in basket", "#7c6af7")
        self._w_cats,  self._n_cats  = _chip("0", "categories", "#4fc3f7")
        for w in (self._w_total, self._w_left, self._w_done, self._w_cats):
            sb.addWidget(w, 1)

        sl.addWidget(self._stat_bar)
        sl.addSpacing(4)

        # Progress bar
        self._bar = _MiniBar("#f0a500", self)
        sl.addWidget(self._bar)
        sl.addSpacing(20)

        # Action row
        ar = QHBoxLayout()
        ar.setSpacing(8)

        # Dishy generate button (green, AI-branded)
        self._btn_gen = DishyMainRequestButton("Generate from Meal Plan", parent=self)
        self._btn_gen.clicked.connect(self._ask_dishy)

        self._btn_dishy = QPushButton("  Ask Dishy")
        self._btn_dishy.setObjectName("ghost-btn")
        self._btn_dishy.setIcon(qta.icon("fa5s.comment-dots", color="#34d399"))
        self._btn_dishy.setIconSize(QSize(13, 13))
        self._btn_dishy.setFixedHeight(38)
        self._btn_dishy.clicked.connect(self._open_dishy_chat)

        export_label = "  Export to Notes" if is_macos() else "  Export List"
        self._btn_export = PrimaryButton(export_label)
        self._btn_export.setIcon(qta.icon("fa5s.share-square", color="#ffffff"))
        self._btn_export.setIconSize(QSize(13, 13))
        self._btn_export.setFixedHeight(38)
        self._btn_export.setToolTip(
            "Export to Apple Notes" if is_macos() else "Export as a text file and open it"
        )
        self._btn_export.clicked.connect(self._export)

        self._btn_clear = QPushButton("  Clear checked")
        self._btn_clear.setObjectName("ghost-btn")
        self._btn_clear.setIcon(qta.icon("fa5s.check-double", color="#888888"))
        self._btn_clear.setIconSize(QSize(13, 13))
        self._btn_clear.setFixedHeight(38)
        self._btn_clear.clicked.connect(self._clear_checked)

        self._btn_consolidate = QPushButton("  Merge Duplicates")
        self._btn_consolidate.setObjectName("ghost-btn")
        self._btn_consolidate.setIcon(qta.icon("fa5s.compress-arrows-alt", color="#4caf8a"))
        self._btn_consolidate.setIconSize(QSize(13, 13))
        self._btn_consolidate.setFixedHeight(38)
        self._btn_consolidate.setToolTip("Merge duplicate list items and keep quantities tidy")
        self._btn_consolidate.clicked.connect(self._smart_consolidate)

        ar.addWidget(self._btn_gen)
        ar.addWidget(self._btn_dishy)
        ar.addStretch()
        ar.addWidget(self._btn_consolidate)
        ar.addWidget(self._btn_export)
        ar.addWidget(self._btn_clear)
        sl.addLayout(ar)
        sl.addSpacing(14)

        # Add item row
        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self._input = QLineEdit(self._tab_shopping)
        self._input.setPlaceholderText("Add an item…")
        self._input.setFixedHeight(38)
        self._input.returnPressed.connect(self._add_item)
        add_btn = PrimaryButton("Add")
        add_btn.setFixedHeight(38)
        add_btn.setFixedWidth(76)
        add_btn.clicked.connect(self._add_item)
        add_row.addWidget(self._input, 1)
        add_row.addWidget(add_btn)
        sl.addLayout(add_row)
        sl.addSpacing(14)

        # Scroll area
        scroll = QScrollArea(self._tab_shopping)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent}")

        self._scroll_contents = QWidget()
        self._scroll_contents.setStyleSheet("background:transparent")
        self._vbox = QVBoxLayout(self._scroll_contents)
        self._vbox.setContentsMargins(0, 0, 0, 0)
        self._vbox.setSpacing(10)

        self._empty = QLabel(
            "Your list is empty.\nGenerate from your meal plan or add items above.",
            self._scroll_contents,
        )
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setObjectName("card-body")
        self._vbox.addWidget(self._empty)
        self._vbox.addStretch()

        scroll.setWidget(self._scroll_contents)
        sl.addWidget(scroll, 1)

        self._style_chrome()

    def _style_chrome(self):
        dark = theme_manager.mode == "dark"
        bg = "#0f0f0f" if dark else "#ffffff"
        border = "#1e1e1e" if dark else "#eeeeee"
        input_col = "#d8d8d8" if dark else "#1a1a1a"
        self._stat_bar.setStyleSheet(
            f"QWidget#stat-bar{{background:{bg};border:1px solid {border};border-radius:12px}}"
        )
        self._input.setStyleSheet(
            f"QLineEdit{{background:{'#111111' if dark else '#f5f5f5'};"
            f"border:1px solid {border};border-radius:8px;"
            f"color:{input_col};font-size:14px;padding:0 12px}}"
        )

    def apply_theme(self, _=None):
        self._style_chrome()
        self._style_tabs()
        for s in self._sections.values():
            s.apply_theme()
        self._bar.update()

    # ── Data ──────────────────────────────────────────────────────────────────

    def refresh(self):
        self.load_from_db()
        if hasattr(self, "_tab_live_shop") and self._current_tab == "Live Shop":
            self._tab_live_shop.refresh()

    def load_from_db(self):
        # Clear existing sections from layout (index 0 is _empty, last is stretch)
        for sec in self._sections.values():
            sec.hide()
            self._vbox.removeWidget(sec)
            sec.deleteLater()
        self._sections.clear()
        self._all_items.clear()

        try:
            rows = self._db.get_shopping_items()
        except Exception:
            rows = []

        self._empty.setVisible(not rows)

        if rows:
            grouped = defaultdict(list)
            for row in rows:
                grouped[_categorize(row["name"])].append(row)

            pos = 1  # after _empty widget
            for cat_name, icon, color in CATEGORIES:
                items = grouped.get(cat_name, [])
                if not items:
                    continue

                sec = _Section(cat_name, icon, color, self._scroll_contents)
                self._sections[cat_name] = sec

                for row in items:
                    source = row["source"] if "source" in row.keys() else None
                    item = _Item(
                        text=row["name"],
                        db_id=row["id"],
                        checked=bool(row["checked"]),
                        source=source,
                        on_toggle=lambda c, _id=row["id"], _sec=sec: (
                            self._db.toggle_shopping_item(_id, c),
                            _sec.update_counts(),
                            self._update_stats(),
                            self._sync_fn() if self._sync_fn else None,
                        ),
                        on_delete=lambda _checked=False, _row=row: self._delete(
                            _row["id"]
                        ),
                        parent=sec,
                    )
                    sec.add_item(item)
                    self._all_items.append(item)

                self._vbox.insertWidget(pos, sec)
                pos += 1

        self._update_stats()

    def _update_stats(self):
        total = len(self._all_items)
        done = sum(1 for i in self._all_items if i.is_checked())
        left = total - done
        cats = len(self._sections)
        self._n_total.setText(str(total))
        self._n_left.setText(str(left))
        self._n_done.setText(str(done))
        self._n_cats.setText(str(cats))
        self._bar.set_pct(done / total if total else 0.0)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _add_item(self):
        text = self._input.text().strip()
        if not text:
            return
        try:
            self._db.add_shopping_item(text)
        except Exception:
            pass
        self._input.clear()
        self.load_from_db()
        if self._sync_fn:
            self._sync_fn()

    def _delete(self, db_id: int):
        try:
            self._db.delete_shopping_item(db_id)
        except Exception:
            pass
        self.load_from_db()
        if self._sync_fn:
            self._sync_fn()

    def _clear_checked(self):
        try:
            self._db.clear_checked_shopping_items()
        except Exception:
            pass
        self.load_from_db()
        if self._sync_fn:
            self._sync_fn()

    def _smart_consolidate(self):
        try:
            rows = [dict(r) for r in self._db.get_shopping_items()]
        except Exception:
            rows = []
        if len(rows) < 2:
            ThemedMessageBox.information(self, "Merge Duplicates", "Add at least two items before running this.")
            return

        merged_rows, stats = consolidate_rows(rows)
        if stats.get("merged_rows", 0) <= 0:
            ThemedMessageBox.information(
                self,
                "Merge Duplicates",
                "No duplicates were found in your current list.",
            )
            return

        # Replace list with consolidated rows.
        try:
            self._db.clear_all_shopping_items()
            for row in merged_rows:
                item_id = self._db.add_shopping_item(
                    row.get("name", ""),
                    quantity=str(row.get("quantity") or ""),
                    unit=str(row.get("unit") or ""),
                    source=str(row.get("source") or "manual"),
                )
                if item_id and int(row.get("checked") or 0):
                    self._db.toggle_shopping_item(item_id, True)
        except Exception as exc:
            ThemedMessageBox.warning(self, "Merge Duplicates failed", str(exc))
            return

        self.load_from_db()
        if self._sync_fn:
            self._sync_fn()
        ThemedMessageBox.information(
            self,
            "Merge complete",
            f"Merged {stats['merged_rows']} duplicate item(s).\n"
            f"List size: {stats['input_rows']} → {stats['output_rows']}.",
        )

    def _export(self):
        if not self._all_items:
            ThemedMessageBox.information(self, "Nothing to export", "Your shopping list is empty.")
            return

        grouped: dict[str, list] = defaultdict(list)
        for item in self._all_items:
            grouped[_categorize(item.item_text())].append(item)

        lines = ["Shopping List", ""]
        for cat_name, _, _ in CATEGORIES:
            items = grouped.get(cat_name, [])
            if not items:
                continue
            lines.append(f"── {cat_name} ──")
            for item in items:
                lines.append(("✓ " if item.is_checked() else "• ") + item.item_text())
            lines.append("")

        content = "\n".join(lines).rstrip()
        if is_macos():
            escaped = content.replace("\\", "\\\\").replace('"', '\\"')
            script = (
                'tell application "Notes"\n'
                '  activate\n'
                '  make new note at default account with properties'
                f' {{name:"Shopping List", body:"{escaped}"}}\n'
                'end tell'
            )
            ok, err = run_apple_script(script)
            if not ok:
                ThemedMessageBox.warning(self, "Export failed", f"Could not export to Notes:\n{err}")
            return

        # Windows/Linux fallback: write a plain text export and open it.
        docs = user_documents_dir()
        docs.mkdir(parents=True, exist_ok=True)
        fname = f"DishBoard_Shopping_List_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        out_path = docs / fname
        try:
            out_path.write_text(content, encoding="utf-8")
        except Exception as exc:
            ThemedMessageBox.warning(self, "Export failed", f"Could not write export file:\n{exc}")
            return
        ok, err = open_path_in_default_app(str(out_path))
        if not ok:
            ThemedMessageBox.warning(
                self,
                "Export complete",
                f"Saved to:\n{out_path}\n\nCould not auto-open file:\n{err}",
            )
            return
        ThemedMessageBox.information(
            self,
            "Export complete",
            f"Saved shopping list to:\n{out_path}",
        )

    def _ask_dishy(self):
        """Generate shopping list from meal plan via Dishy AI."""
        if self._ask_dishy_fn:
            self._ask_dishy_fn(
                "Build my shopping list from this week's meal plan — "
                "add all the ingredients from my planned meals and let me know what you've added."
            )

    def _open_dishy_chat(self):
        """Open Dishy for general shopping list help."""
        if self._ask_dishy_fn:
            self._ask_dishy_fn("")

    def _generate(self):
        from datetime import datetime, timedelta
        import json
        today = datetime.now().date()
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        try:
            rows = self._db.get_meal_plan(week_start)
        except Exception:
            return
        seen: set[str] = set()
        for row in rows:
            if row["recipe_id"]:
                try:
                    r = self._db.conn.execute(
                        "SELECT data_json FROM recipes WHERE id=?", (row["recipe_id"],)
                    ).fetchone()
                    if r and r["data_json"]:
                        for ing in json.loads(r["data_json"]).get("ingredients", []):
                            if ing and ing not in seen:
                                seen.add(ing)
                                self._db.add_shopping_item(ing, source="meal_plan")
                        continue
                except Exception:
                    pass
            if row["custom_name"] and row["custom_name"] not in seen:
                seen.add(row["custom_name"])
                self._db.add_shopping_item(row["custom_name"], source="meal_plan")
        self.load_from_db()
