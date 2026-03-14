"""My Kitchen — Pantry, Fridge, and Freezer tracker."""
from __future__ import annotations

from datetime import date

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QDialog, QLineEdit,
    QComboBox, QDateEdit,
)
from PySide6.QtCore import Qt, QSize, QDate, QObject, QTimer, Signal as _Signal


# ── Pantry change broadcaster ─────────────────────────────────────────────────

class _PantryBroadcaster(QObject):
    pantry_changed = _Signal()

_pantry_broadcaster: _PantryBroadcaster | None = None

def get_pantry_broadcaster() -> _PantryBroadcaster:
    global _pantry_broadcaster
    if _pantry_broadcaster is None:
        _pantry_broadcaster = _PantryBroadcaster()
    return _pantry_broadcaster

from utils.theme import manager as theme_manager
from utils.themed_dialog import ThemedMessageBox
from utils.data_service import get_db
from models.database import Database
from widgets.page_scaffold import EmptyStateCard, PageScaffold, PageToolbar, SegmentedTabs, StatStrip, StatusBanner
from widgets.primary_button import PrimaryButton


# ── Helpers ───────────────────────────────────────────────────────────────────

_TABS = [
    ("Pantry",  "#e8924a", "fa5s.box-open"),
    ("Fridge",  "#4fc3f7", "fa5s.thermometer-half"),
    ("Freezer", "#60a5fa", "fa5s.snowflake"),
]

_UNITS = ["g", "kg", "ml", "L", "pack", "tin", "bag", "bunch", "whole", "tbsp", "tsp", "bottle", "jar"]

# ── Per-section categories ─────────────────────────────────────────────────────
# Each entry: (display_name, qtawesome_icon, hex_colour, [keywords])

_PANTRY_CATEGORIES = [
    ("Grains & Pasta",     "fa5s.bread-slice",   "#f0a500",
     ["pasta","rice","noodle","oat","quinoa","couscous","barley","flour","breadcrumb","cereal","granola","cracker","polenta"]),
    ("Tins & Pulses",      "fa5s.box",           "#7c6af7",
     ["tin","canned","can","bean","lentil","chickpea","kidney","cannellini","black bean","butter bean","tomato","passata","stock","broth","coconut milk"]),
    ("Oils & Condiments",  "fa5s.oil-can",       "#ff9a5c",
     ["oil","vinegar","soy","sauce","ketchup","mayo","mayonnaise","mustard","pesto","tahini","miso","sriracha","hot sauce","worcestershire","fish sauce","oyster sauce","hoisin","teriyaki","honey","syrup","jam","marmalade","spread","pickle","chutney"]),
    ("Spices & Herbs",     "fa5s.mortar-pestle", "#34d399",
     ["salt","pepper","spice","seasoning","cumin","paprika","oregano","cinnamon","curry","turmeric","chilli","chili","coriander","basil","thyme","rosemary","bay","garlic powder","onion powder","mixed spice","nutmeg","cardamom","ginger","clove","star anise","herb","dried"]),
    ("Baking",             "fa5s.birthday-cake", "#e05c7a",
     ["baking powder","baking soda","bicarbonate","sugar","icing sugar","cocoa","chocolate chips","vanilla","yeast","gelatin","cornflour","cornstarch","almond flour","self raising","plain flour","bread flour"]),
    ("Nuts & Seeds",       "fa5s.seedling",      "#4caf8a",
     ["nut","almond","cashew","peanut","walnut","pecan","pistachio","macadamia","hazelnut","seed","chia","flax","sunflower","sesame","pumpkin seed","raisin","sultana","dried fruit","cranberry","apricot","date","fig"]),
    ("Snacks & Drinks",    "fa5s.mug-hot",       "#4fc3f7",
     ["biscuit","cookie","crisp","chip","chocolate","candy","sweet","snack","cereal bar","flapjack","popcorn","coffee","tea","hot chocolate","juice","squash","cordial","water","drink"]),
    ("Other",              "fa5s.shopping-basket","#888888", []),
]

_FRIDGE_CATEGORIES = [
    ("Dairy",              "fa5s.cheese",        "#f0c040",
     ["milk","cheese","butter","yoghurt","yogurt","cream","ghee","kefir","sour cream","creme fraiche","double cream","single cream","clotted cream","custard","cheddar","mozzarella","parmesan","feta","brie","camembert","gouda","ricotta","mascarpone","halloumi","cottage cheese","quark","crème fraîche","dairy"]),
    ("Eggs",               "fa5s.egg",           "#f0a500",
     ["egg"]),
    ("Meat & Poultry",     "fa5s.drumstick-bite","#ff9a5c",
     ["chicken","beef","pork","lamb","turkey","duck","venison","veal","mince","steak","brisket","ribs","fillet","breast","thigh","drumstick","meatball","burger","sausage","bacon","ham","salami","chorizo","pepperoni","prosciutto","pancetta","lardons","hot dog","deli"]),
    ("Fish & Seafood",     "fa5s.fish",          "#4fc3f7",
     ["fish","salmon","tuna","cod","haddock","sea bass","trout","mackerel","sardine","anchovy","prawn","shrimp","crab","lobster","squid","scallop","mussel","clam","oyster","seafood","monkfish","halibut","tilapia"]),
    ("Fresh Produce",      "fa5s.carrot",        "#34d399",
     ["lettuce","spinach","kale","rocket","arugula","cucumber","celery","leek","spring onion","herb","basil","coriander","parsley","chive","dill","tarragon","mint","pepper","carrot","broccoli","cauliflower","asparagus","courgette","zucchini","aubergine","eggplant","salad","vegetable","veg","fresh","tofu","tempeh"]),
    ("Dips & Spreads",     "fa5s.jar",           "#e05c7a",
     ["hummus","dip","guacamole","salsa","tzatziki","pate","cream cheese","spread","butter","margarine"]),
    ("Drinks & Juice",     "fa5s.glass-whiskey", "#60a5fa",
     ["juice","smoothie","milk","water","soda","beer","wine","prosecco","cider","kombucha","coconut water","oat milk","almond milk","soy milk","plant milk"]),
    ("Other",              "fa5s.shopping-basket","#888888", []),
]

_FREEZER_CATEGORIES = [
    ("Meat & Poultry",     "fa5s.drumstick-bite","#ff9a5c",
     ["chicken","beef","pork","lamb","turkey","duck","mince","steak","burger","sausage","bacon","ham","meat","poultry"]),
    ("Fish & Seafood",     "fa5s.fish",          "#4fc3f7",
     ["fish","salmon","tuna","cod","haddock","prawn","shrimp","sea bass","fish finger","seafood","monkfish","tilapia","mackerel"]),
    ("Vegetables",         "fa5s.seedling",      "#34d399",
     ["pea","corn","sweetcorn","spinach","broccoli","carrot","bean","edamame","cauliflower","pepper","onion","vegetable","veg","mixed veg"]),
    ("Ready Meals",        "fa5s.utensils",      "#7c6af7",
     ["pizza","ready meal","lasagne","curry","pie","pastry","burrito","wrap","meal","dinner","lunch"]),
    ("Desserts & Ice Cream","fa5s.ice-cream",    "#e05c7a",
     ["ice cream","sorbet","gelato","frozen yogurt","dessert","cheesecake","mousse","lolly","popsicle"]),
    ("Bread & Pastry",     "fa5s.bread-slice",   "#f0a500",
     ["bread","roll","bun","croissant","bagel","pitta","naan","flatbread","pastry","waffle","pancake","tortilla"]),
    ("Other",              "fa5s.shopping-basket","#888888", []),
]

_STORAGE_CATEGORIES = {
    "Pantry":  _PANTRY_CATEGORIES,
    "Fridge":  _FRIDGE_CATEGORIES,
    "Freezer": _FREEZER_CATEGORIES,
}


def _categorize_kitchen_item(name: str, storage: str) -> str:
    cats = _STORAGE_CATEGORIES.get(storage, [])
    n = name.lower()
    for cat_name, _icon, _color, keywords in cats:
        if cat_name == "Other":
            continue
        if any(k in n for k in keywords):
            return cat_name
    return "Other"


def _days_until_expiry(expiry_str: str) -> int | None:
    if not expiry_str:
        return None
    try:
        exp = date.fromisoformat(expiry_str)
        return (exp - date.today()).days
    except Exception:
        return None


# ── Add Item Dialog ────────────────────────────────────────────────────────────

class _AddItemDialog(QDialog):
    def __init__(self, db: Database, default_storage: str = "Pantry",
                 edit_item: dict | None = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._edit_item = edit_item
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None

        tm = theme_manager
        dark = tm.mode == "dark"
        border = tm.c("#2a2a2a", "#e0e0e0")
        text = tm.c("#f0f0f0", "#1a1a1a")
        muted = tm.c("#888888", "#666666")
        input_bg = tm.c("#1a1a1a", "#f5f5f5")

        title_str = "Edit Item" if edit_item else "Add Item"

        field_style = (
            f"QLineEdit{{background:{input_bg};border:1px solid {border};border-radius:7px;"
            f"color:{text};padding:6px 10px;font-size:14px}}"
            f"QComboBox{{background:{input_bg};border:1px solid {border};border-radius:7px;"
            f"color:{text};padding:5px 10px;font-size:14px}}"
            f"QDateEdit{{background:{input_bg};border:1px solid {border};border-radius:7px;"
            f"color:{text};padding:5px 10px;font-size:14px}}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        card = QWidget()
        card.setObjectName("add-item-card")
        card.setFixedWidth(380)
        card.setStyleSheet(
            f"QWidget#add-item-card {{"
            f"  background: {tm.c('#161616', '#ffffff')};"
            f"  border-radius: 14px;"
            f"  border: 1px solid {border};"
            f"}}"
            + field_style
            + f"QLabel{{background:transparent;color:{text}}}"
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # Header with title and X close button
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        title_lbl = QLabel(title_str)
        title_lbl.setStyleSheet(f"font-size:17px;font-weight:700;color:{text};background:transparent")
        hdr.addWidget(title_lbl, 1)
        close_x = QPushButton()
        close_x.setIcon(qta.icon("fa5s.times", color=muted))
        close_x.setIconSize(QSize(13, 13))
        close_x.setFixedSize(28, 28)
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 14px; }}"
            f"QPushButton:hover {{ background: {'rgba(255,255,255,0.08)' if dark else 'rgba(0,0,0,0.06)'}; }}"
        )
        close_x.clicked.connect(self.reject)
        hdr.addWidget(close_x, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(hdr)

        def _field(label_text, widget):
            row = QVBoxLayout()
            row.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size:12px;font-weight:600;color:{muted};background:transparent")
            row.addWidget(lbl)
            row.addWidget(widget)
            layout.addLayout(row)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Chicken breast")
        _field("Name", self._name_edit)

        qty_row = QHBoxLayout()
        qty_row.setSpacing(8)
        self._qty_edit = QLineEdit()
        self._qty_edit.setPlaceholderText("e.g. 500")
        self._unit_combo = QComboBox()
        self._unit_combo.addItems(_UNITS)
        self._unit_combo.setFixedWidth(80)
        qty_row.addWidget(self._qty_edit, 1)
        qty_row.addWidget(self._unit_combo)
        qty_lbl = QLabel("Quantity & Unit")
        qty_lbl.setStyleSheet(f"font-size:12px;font-weight:600;color:{muted};background:transparent")
        layout.addWidget(qty_lbl)
        layout.addLayout(qty_row)

        self._storage_combo = QComboBox()
        self._storage_combo.addItems(["Pantry", "Fridge", "Freezer"])
        idx = {"Pantry": 0, "Fridge": 1, "Freezer": 2}.get(default_storage, 0)
        self._storage_combo.setCurrentIndex(idx)
        _field("Storage", self._storage_combo)

        self._expiry_check = QPushButton("Set expiry date (optional)")
        self._expiry_check.setCheckable(True)
        self._expiry_check.setStyleSheet(
            f"QPushButton{{background:transparent;border:1px solid {border};border-radius:7px;"
            f"color:{muted};font-size:13px;padding:6px 10px;text-align:left}}"
            f"QPushButton:checked{{color:#e8924a;border-color:#e8924a}}"
        )
        self._expiry_edit = QDateEdit()
        self._expiry_edit.setCalendarPopup(True)
        self._expiry_edit.setDate(QDate.currentDate().addDays(7))
        self._expiry_edit.setVisible(False)
        self._expiry_check.toggled.connect(self._expiry_edit.setVisible)
        layout.addWidget(self._expiry_check)
        layout.addWidget(self._expiry_edit)

        # Custom buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {border};"
            f" border-radius: 9px; color: {muted}; font-size: 13px; padding: 0 18px; }}"
            f"QPushButton:hover {{ background: {tm.c('#1e1e1e', '#f0f0f0')}; }}"
        )
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(38)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(
            "QPushButton { background: #e8924a; color: #ffffff; border: none;"
            " border-radius: 9px; font-size: 13px; font-weight: 600; padding: 0 18px; }"
            "QPushButton:hover { background: #d07838; }"
        )
        save_btn.clicked.connect(self._on_save)

        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

        if edit_item:
            self._name_edit.setText(edit_item.get("name", ""))
            qty = edit_item.get("quantity")
            if qty is not None:
                self._qty_edit.setText(str(qty))
            unit = edit_item.get("unit", "")
            if unit in _UNITS:
                self._unit_combo.setCurrentText(unit)
            storage = edit_item.get("storage", "Pantry")
            self._storage_combo.setCurrentText(storage)
            exp = edit_item.get("expiry_date")
            if exp:
                self._expiry_check.setChecked(True)
                try:
                    d = QDate.fromString(exp, "yyyy-MM-dd")
                    self._expiry_edit.setDate(d)
                except Exception:
                    pass

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        self._drag_pos = None

    def _on_save(self):
        name = self._name_edit.text().strip()
        if not name:
            ThemedMessageBox.warning(self, "Name required", "Please enter a name for this item.")
            return
        qty_text = self._qty_edit.text().strip()
        try:
            qty = float(qty_text) if qty_text else None
        except ValueError:
            qty = None
        unit = self._unit_combo.currentText()
        storage = self._storage_combo.currentText()
        expiry = None
        if self._expiry_check.isChecked():
            expiry = self._expiry_edit.date().toString("yyyy-MM-dd")

        if self._edit_item:
            self._db.update_pantry_item(self._edit_item["id"], qty, unit, expiry)
        else:
            self._db.add_pantry_item(name, qty, unit, storage, expiry)
        self.accept()


# ── Per-item row widget ────────────────────────────────────────────────────────

class _PantryItemRow(QWidget):
    def __init__(self, item: dict, db: Database, trigger_sync, on_refresh, parent=None):
        super().__init__(parent)
        self._item = item
        self._db = db
        self._trigger_sync = trigger_sync
        self._on_refresh = on_refresh
        self._highlighted = False
        self.setFixedHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._build()

    def _build(self):
        dark = theme_manager.mode == "dark"
        text_col = "#f0f0f0" if dark else "#1a1a1a"
        muted_col = "#888888" if dark else "#666666"

        if self.layout():
            QWidget().setLayout(self.layout())

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 10, 0)
        row.setSpacing(10)

        # Name
        name_lbl = QLabel(self._item["name"])
        name_lbl.setStyleSheet(f"color:{text_col};font-size:15px;font-weight:500;background:transparent")
        row.addWidget(name_lbl, 1)

        # Qty + unit
        qty = self._item.get("quantity")
        unit = self._item.get("unit", "")
        if qty is not None:
            qty_str = str(int(qty)) if qty == int(qty) else str(qty)
            qty_lbl = QLabel(f"{qty_str} {unit}".strip())
        else:
            qty_lbl = QLabel(unit or "")
        qty_lbl.setStyleSheet(f"color:{muted_col};font-size:13px;background:transparent")
        row.addWidget(qty_lbl)

        # Expiry badge
        days = _days_until_expiry(self._item.get("expiry_date") or "")
        if days is not None:
            if days < 0:
                badge_text = "Expired"
                badge_col = "#ef4444"
                badge_bg = "rgba(239,68,68,0.15)"
            elif days <= 3:
                badge_text = f"{days}d left"
                badge_col = "#f0a500"
                badge_bg = "rgba(240,165,0,0.15)"
            else:
                badge_text = ""
                badge_bg = ""
                badge_col = ""
            if badge_text:
                exp_lbl = QLabel(badge_text)
                exp_lbl.setStyleSheet(
                    f"color:{badge_col};font-size:10px;font-weight:700;"
                    f"background:{badge_bg};border-radius:5px;padding:2px 7px"
                )
                row.addWidget(exp_lbl)

        # Edit button
        edit_btn = QPushButton()
        edit_btn.setIcon(qta.icon("fa5s.pencil-alt", color="#555555"))
        edit_btn.setIconSize(QSize(11, 11))
        edit_btn.setFixedSize(28, 28)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;border-radius:5px}"
            "QPushButton:hover{background:rgba(255,255,255,0.07)}"
        )
        edit_btn.clicked.connect(self._on_edit)
        row.addWidget(edit_btn)

        # Delete button
        del_btn = QPushButton()
        del_btn.setIcon(qta.icon("fa5s.times", color="#555555"))
        del_btn.setIconSize(QSize(11, 11))
        del_btn.setFixedSize(28, 28)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;border-radius:5px}"
            "QPushButton:hover{background:rgba(239,68,68,0.12)}"
        )
        del_btn.clicked.connect(self._on_delete)
        del_btn.enterEvent = lambda _: del_btn.setIcon(qta.icon("fa5s.times", color="#ef4444"))
        del_btn.leaveEvent = lambda _: del_btn.setIcon(qta.icon("fa5s.times", color="#555555"))
        row.addWidget(del_btn)

        self._apply_highlight_style()

    def _on_edit(self):
        dlg = _AddItemDialog(self._db, self._item.get("storage", "Pantry"),
                             edit_item=self._item, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            get_pantry_broadcaster().pantry_changed.emit()
            if self._trigger_sync:
                self._trigger_sync()
            if self._on_refresh:
                self._on_refresh()

    def _on_delete(self):
        self._db.delete_pantry_item(self._item["id"])
        get_pantry_broadcaster().pantry_changed.emit()
        if self._trigger_sync:
            self._trigger_sync()
        if self._on_refresh:
            self._on_refresh()

    def highlight_temporarily(self, duration_ms: int = 1800):
        self._highlighted = True
        self._apply_highlight_style()
        QTimer.singleShot(duration_ms, self._clear_highlight)

    def _clear_highlight(self):
        self._highlighted = False
        self._apply_highlight_style()

    def _apply_highlight_style(self):
        self.setStyleSheet(
            (
                f"background:{theme_manager.c('rgba(255,107,53,0.10)', 'rgba(255,107,53,0.08)')};"
                "border-radius:8px;"
            ) if self._highlighted else "background:transparent; border-radius:8px;"
        )


# ── Panel for one storage section ─────────────────────────────────────────────

class _StoragePanel(QWidget):
    def __init__(self, storage: str, db: Database, trigger_sync, on_refresh, parent=None):
        super().__init__(parent)
        self._storage = storage
        self._db = db
        self._trigger_sync = trigger_sync
        self._on_refresh = on_refresh
        self._rows: list[_PantryItemRow] = []
        self._headers: list[QWidget] = []
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;border:none")
        self._scroll = scroll

        # parent=scroll so it's owned — never a floating window
        self._content = QWidget(scroll)
        self._content.setStyleSheet("background:transparent")
        self._vbox = QVBoxLayout(self._content)
        self._vbox.setContentsMargins(0, 4, 0, 8)
        self._vbox.setSpacing(0)

        self._empty_lbl = EmptyStateCard(
            f"Nothing in your {self._storage} yet",
            "Use Add Item to start building a cleaner live inventory for Dishy.",
            icon=self._storage[0],
            parent=self._content,
        )
        self._vbox.addWidget(self._empty_lbl)
        self._vbox.addStretch()

        scroll.setWidget(self._content)
        vbox.addWidget(scroll)

    def _make_category_header(self, cat_name: str, icon_name: str, color: str) -> QWidget:
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

    def load(self):
        # Clear existing rows and category headers
        for w in self._rows + self._headers:
            w.hide()
            self._vbox.removeWidget(w)
            w.deleteLater()
        self._rows.clear()
        self._headers.clear()

        items = self._db.get_pantry_items(self._storage)
        self._empty_lbl.setVisible(not items)

        if items:
            # Group by per-section category
            from collections import defaultdict as _dd
            cats = _STORAGE_CATEGORIES.get(self._storage, [])
            grouped: dict[str, list] = _dd(list)
            for item in items:
                grouped[_categorize_kitchen_item(item["name"], self._storage)].append(item)

            pos = 1  # after _empty_lbl, before stretch
            for cat_name, icon_name, color, _kws in cats:
                cat_items = grouped.get(cat_name, [])
                if not cat_items:
                    continue

                hdr = self._make_category_header(cat_name, icon_name, color)
                self._headers.append(hdr)
                self._vbox.insertWidget(pos, hdr)
                pos += 1

                for item in cat_items:
                    row = _PantryItemRow(
                        item, self._db, self._trigger_sync, self._on_refresh, self._content
                    )
                    self._rows.append(row)
                    self._vbox.insertWidget(pos, row)
                    pos += 1

    def item_count(self) -> int:
        return len(self._rows)

    def expiring_count(self) -> int:
        count = 0
        for item in self._db.get_pantry_items(self._storage):
            d = _days_until_expiry(item.get("expiry_date") or "")
            if d is not None and d <= 3:
                count += 1
        return count

    def focus_item(self, item_id: int) -> bool:
        for row in self._rows:
            if int(row._item.get("id") or 0) != int(item_id):
                continue
            self._scroll.ensureWidgetVisible(row, 0, 80)
            row.highlight_temporarily()
            return True
        return False


# ── Main view ─────────────────────────────────────────────────────────────────

class MyKitchenStorageView(QWidget):
    def __init__(self, db: Database = None, trigger_sync=None,
                 ask_dishy_fn=None, navigate_to=None, parent=None):
        super().__init__(parent)
        self.setObjectName("view-container")
        self._db = db or get_db()
        self._trigger_sync = trigger_sync
        self._ask_dishy_fn = ask_dishy_fn
        self._navigate_to = navigate_to
        self._panels: dict[str, _StoragePanel] = {}
        self._current_tab = "Pantry"
        self._tab_buttons: dict[str, QPushButton] = {}
        self._build_ui()
        theme_manager.theme_changed.connect(self.apply_theme)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scaffold = PageScaffold(
            "My Kitchen",
            "Keep Pantry, Fridge, and Freezer organised so Dishy can plan around what you already have.",
            eyebrow="Food Operations",
            parent=self,
            quiet_header=True,
        )
        root.addWidget(self._scaffold)

        self._add_btn = PrimaryButton("  Add Item")
        self._add_btn.setIcon(qta.icon("fa5s.plus", color="#ffffff"))
        self._add_btn.setIconSize(QSize(12, 12))
        self._add_btn.clicked.connect(self._on_add_item)
        self._scaffold.set_header_action(self._add_btn)

        toolbar = PageToolbar(self._scaffold)
        self._tabs = SegmentedTabs([(storage, storage) for storage, _color, _icon in _TABS], self._scaffold)
        self._tabs.tab_changed.connect(self._switch_tab)
        toolbar.add_left(self._tabs)
        self._scaffold.set_toolbar(toolbar)

        self._kitchen_banner = StatusBanner(
            "This stock view powers pantry-aware planning, shopping overlap checks, and waste-reduction suggestions.",
            "system",
            self._scaffold,
        )
        self._scaffold.set_banner(self._kitchen_banner)

        self._stat_bar = StatStrip(self._scaffold, density="compact", max_visible=5)
        self._n_total = self._stat_bar.add_stat("total", "0", "Total items", "#e8924a")["value"]
        self._n_expiring = self._stat_bar.add_stat("expiring", "0", "Expiring soon", "#f0a500")["value"]
        self._n_pantry = self._stat_bar.add_stat("pantry", "0", "In pantry", "#e8924a")["value"]
        self._n_fridge = self._stat_bar.add_stat("fridge", "0", "In fridge", "#4fc3f7")["value"]
        self._n_freezer = self._stat_bar.add_stat("freezer", "0", "In freezer", "#60a5fa")["value"]
        self._scaffold.set_stats(self._stat_bar)

        # ── Stacked content ───────────────────────────────────────────────────
        from PySide6.QtWidgets import QStackedWidget
        self._stack = QStackedWidget()
        for storage, color, icon_name in _TABS:
            panel = _StoragePanel(storage, self._db, self._trigger_sync, self.refresh)
            self._panels[storage] = panel
            self._stack.addWidget(panel)
        self._stack.setCurrentIndex(0)
        self._tabs.set_current(self._current_tab)
        self._scaffold.body_layout().addWidget(self._stack, 1)

    def _switch_tab(self, storage: str):
        self._current_tab = storage
        if self._tabs.current_key() != storage:
            self._tabs.set_current(storage)
        idx = {"Pantry": 0, "Fridge": 1, "Freezer": 2}[storage]
        self._stack.setCurrentIndex(idx)
        self._kitchen_banner.set_variant("system")
        self._kitchen_banner.set_text(
            f"{storage} shows what you currently have there, so Dishy can avoid duplicate shopping and make better meal suggestions."
        )

    def show_root_page(self):
        """Return My Kitchen to its default Pantry tab."""
        self._switch_tab("Pantry")

    def _on_add_item(self):
        if self._open_add_item_dialog(self._current_tab):
            get_pantry_broadcaster().pantry_changed.emit()
            if self._trigger_sync:
                self._trigger_sync()
            self.refresh()

    def activate_storage(self, storage: str = "Pantry") -> None:
        """Palette-safe entrypoint for a specific storage tab."""
        self._switch_tab(storage if storage in {"Pantry", "Fridge", "Freezer"} else "Pantry")

    def activate_add_item(self, storage: str = "Pantry") -> None:
        """Palette-safe entrypoint for adding a pantry item."""
        self.activate_storage(storage)
        QTimer.singleShot(0, lambda: self._on_add_item())

    def focus_item(self, item_id: int) -> bool:
        items = self._db.get_pantry_items()
        target = next((item for item in items if int(item.get("id") or 0) == int(item_id)), None)
        if not target:
            return False
        storage = str(target.get("storage") or "Pantry")
        self.activate_storage(storage)
        self.refresh()
        panel = self._panels.get(storage)
        return bool(panel and panel.focus_item(item_id))

    def save_item_from_palette(
        self,
        name: str,
        quantity=None,
        unit: str = "",
        storage: str = "Pantry",
        expiry_date: str | None = None,
    ) -> int:
        item_id = self._db.add_pantry_item(name, quantity, unit, storage, expiry_date)
        get_pantry_broadcaster().pantry_changed.emit()
        if self._trigger_sync:
            self._trigger_sync()
        self.refresh()
        return int(item_id or 0)

    def _open_add_item_dialog(self, storage: str) -> bool:
        dlg = _AddItemDialog(self._db, storage, parent=self)
        return dlg.exec() == QDialog.DialogCode.Accepted

    def refresh(self):
        self._load()

    def _load(self):
        all_items = self._db.get_pantry_items()
        total = len(all_items)
        expiring = 0
        for item in all_items:
            d = _days_until_expiry(item.get("expiry_date") or "")
            if d is not None and d <= 3:
                expiring += 1

        pantry_count  = sum(1 for i in all_items if i.get("storage") == "Pantry")
        fridge_count  = sum(1 for i in all_items if i.get("storage") == "Fridge")
        freezer_count = sum(1 for i in all_items if i.get("storage") == "Freezer")

        self._n_total.setText(str(total))
        self._n_expiring.setText(str(expiring))
        self._n_pantry.setText(str(pantry_count))
        self._n_fridge.setText(str(fridge_count))
        self._n_freezer.setText(str(freezer_count))

        for panel in self._panels.values():
            panel.load()

    def apply_theme(self, _mode=None):
        for panel in self._panels.values():
            panel.load()
