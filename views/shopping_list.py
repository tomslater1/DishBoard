"""Shopping List — rebuilt from scratch."""
import subprocess
from collections import defaultdict

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QCheckBox, QSizePolicy, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter, QColor

from utils.theme import manager as theme_manager
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


# ── Main view ─────────────────────────────────────────────────────────────────

class ShoppingListView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("view-container")
        self._db = Database()
        self._db.connect()
        self._sections: dict[str, _Section] = {}
        self._all_items: list[_Item] = []
        self._ask_dishy_fn = None
        self._sync_fn = None
        self._build_ui()

    def set_ask_dishy(self, fn):
        self._ask_dishy_fn = fn

    def set_sync_fn(self, fn):
        """Called by MainWindow to trigger cloud sync after list mutations."""
        self._sync_fn = fn

    def _build_ui(self):
        self.setMinimumHeight(420)  # prevents the view from collapsing at small window heights
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 24)
        root.setSpacing(0)

        # Header
        self._title_lbl = QLabel("Shopping List")
        self._title_lbl.setObjectName("page-title")
        self._sub_lbl = QLabel("Tap a category to expand · check items off as you shop")
        self._sub_lbl.setObjectName("page-date")
        root.addWidget(self._title_lbl)
        root.addWidget(self._sub_lbl)
        root.addSpacing(20)

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

        root.addWidget(self._stat_bar)
        root.addSpacing(4)

        # Progress bar
        self._bar = _MiniBar("#f0a500", self)
        root.addWidget(self._bar)
        root.addSpacing(20)

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

        self._btn_export = PrimaryButton("  Export to Notes")
        self._btn_export.setIcon(qta.icon("fa5s.share-square", color="#ffffff"))
        self._btn_export.setIconSize(QSize(13, 13))
        self._btn_export.setFixedHeight(38)
        self._btn_export.clicked.connect(self._export)

        self._btn_clear = QPushButton("  Clear checked")
        self._btn_clear.setObjectName("ghost-btn")
        self._btn_clear.setIcon(qta.icon("fa5s.check-double", color="#888888"))
        self._btn_clear.setIconSize(QSize(13, 13))
        self._btn_clear.setFixedHeight(38)
        self._btn_clear.clicked.connect(self._clear_checked)

        ar.addWidget(self._btn_gen)
        ar.addWidget(self._btn_dishy)
        ar.addStretch()
        ar.addWidget(self._btn_export)
        ar.addWidget(self._btn_clear)
        root.addLayout(ar)
        root.addSpacing(14)

        # Add item row
        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self._input = QLineEdit(self)
        self._input.setPlaceholderText("Add an item…")
        self._input.setFixedHeight(38)
        self._input.returnPressed.connect(self._add_item)
        add_btn = PrimaryButton("Add")
        add_btn.setFixedHeight(38)
        add_btn.setFixedWidth(76)
        add_btn.clicked.connect(self._add_item)
        add_row.addWidget(self._input, 1)
        add_row.addWidget(add_btn)
        root.addLayout(add_row)
        root.addSpacing(14)

        # Scroll area
        scroll = QScrollArea(self)
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
        root.addWidget(scroll, 1)

        self._style_chrome()
        theme_manager.theme_changed.connect(self.apply_theme)
        self.load_from_db()

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
        for s in self._sections.values():
            s.apply_theme()
        self._bar.update()

    # ── Data ──────────────────────────────────────────────────────────────────

    def refresh(self):
        self.load_from_db()

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

    def _export(self):
        if not self._all_items:
            QMessageBox.information(self, "Nothing to export", "Your shopping list is empty.")
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
        escaped = content.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            'tell application "Notes"\n'
            '  activate\n'
            '  make new note at default account with properties'
            f' {{name:"Shopping List", body:"{escaped}"}}\n'
            'end tell'
        )
        try:
            result = subprocess.run(["osascript", "-e", script],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())
        except Exception as e:
            QMessageBox.warning(self, "Export failed",
                                f"Could not export to Notes:\n{e}")

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
