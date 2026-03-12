import json
from datetime import datetime, timedelta
from urllib.parse import urlparse
from utils.theme import manager as theme_manager

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QSizePolicy, QStackedWidget,
    QDialog, QDialogButtonBox, QGridLayout, QComboBox,
    QFrame, QFileDialog, QMessageBox,
)
from PySide6.QtGui import QPixmap, QPainter, QPainterPath
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve

from api.claude_ai import ClaudeAI
from api.google_search import GoogleSearchAPI
from api.recipe_scraper import scrape_recipe
from models.database import Database
from utils.workers import run_async
from widgets.ingredient_row import NutritionIngredientList
from widgets.primary_button import PrimaryButton

_google = GoogleSearchAPI()

# ── Icon / colour / tag palettes ────────────────────────────────────────────

RECIPE_ICONS: list[tuple[str, str]] = [
    ("fa5s.utensils",       "General"),
    ("fa5s.pizza-slice",    "Pizza"),
    ("fa5s.fish",           "Seafood"),
    ("fa5s.drumstick-bite", "Chicken"),
    ("fa5s.hamburger",      "Burger"),
    ("fa5s.leaf",           "Veg"),
    ("fa5s.seedling",       "Plant"),
    ("fa5s.carrot",         "Veg"),
    ("fa5s.apple-alt",      "Healthy"),
    ("fa5s.bacon",          "Breakfast"),
    ("fa5s.egg",            "Eggs"),
    ("fa5s.coffee",         "Coffee"),
    ("fa5s.birthday-cake",  "Baking"),
    ("fa5s.cookie",         "Snacks"),
    ("fa5s.fire",           "BBQ"),
    ("fa5s.pepper-hot",     "Spicy"),
    ("fa5s.mortar-pestle",  "Spices"),
    ("fa5s.bread-slice",    "Bread"),
    ("fa5s.ice-cream",      "Dessert"),
    ("fa5s.blender",        "Smoothie"),
    ("fa5s.lemon",          "Citrus"),
    ("fa5s.cheese",         "Dairy"),
    ("fa5s.hotdog",         "Fast Food"),
    ("fa5s.mug-hot",        "Hot Drink"),
    ("fa5s.snowflake",      "Cold"),
    ("fa5s.wine-glass-alt", "Drinks"),
    ("fa5s.star",           "Special"),
    ("fa5s.heart",          "Favourite"),
    ("fa5s.sun",            "Lunch"),
    ("fa5s.moon",           "Dinner"),
]

RECIPE_COLOURS: list[tuple[str, str]] = [
    ("#ff6b35", "Orange"),
    ("#ef4444", "Red"),
    ("#f59e0b", "Amber"),
    ("#fbbf24", "Yellow"),
    ("#34d399", "Green"),
    ("#10b981", "Emerald"),
    ("#4fc3f7", "Sky"),
    ("#60a5fa", "Blue"),
    ("#a78bfa", "Purple"),
    ("#f472b6", "Pink"),
    ("#fb7185", "Rose"),
    ("#94a3b8", "Slate"),
]

RECIPE_TAGS: list[str] = [
    "Vegetarian", "Vegan", "Gluten-Free", "Dairy-Free",
    "High-Protein", "Low-Carb", "Keto", "Paleo",
    "Quick (< 30 min)", "One-Pot", "Meal-Prep", "Batch Cook",
    "Spicy", "Healthy", "Comfort Food", "Budget-Friendly",
    "Date Night", "Kid-Friendly", "BBQ", "Breakfast",
    "Lunch", "Dinner", "Snack", "Dessert", "Baking",
]

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MEAL_TYPES = ["breakfast", "lunch", "dinner"]


# ── Small helpers ────────────────────────────────────────────────────────────

def _meta_chip(icon_name: str, text: str) -> QWidget:
    w = QWidget()
    w.setStyleSheet(
        f"background-color: {theme_manager.c('#111111', '#f0f0f0')};"
        f" border-radius: 6px; border: 1px solid {theme_manager.c('#1c1c1c', '#dddddd')};"
    )
    row = QHBoxLayout(w)
    row.setContentsMargins(10, 5, 10, 5)
    row.setSpacing(6)
    ic = QLabel()
    ic.setPixmap(qta.icon(icon_name, color=theme_manager.c("#555555", "#777777")).pixmap(QSize(11, 11)))
    ic.setStyleSheet("background: transparent;")
    lbl = QLabel(text)
    lbl.setStyleSheet(f"background: transparent; color: {theme_manager.c('#666666', '#555555')}; font-size: 12px;")
    row.addWidget(ic)
    row.addWidget(lbl)
    return w


def _divider() -> QWidget:
    d = QWidget()
    d.setStyleSheet(f"background-color: {theme_manager.c('#1a1a1a', '#e0e0e0')};")
    d.setFixedHeight(1)
    return d


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("section-label")
    return lbl


def _nutrition_summary_card(per_serving: dict, servings, on_log_today=None) -> QWidget:
    """Full-width nutrition card — powered by Dishy."""
    card = QWidget()
    card.setObjectName("stat-card")
    vl = QVBoxLayout(card)
    vl.setContentsMargins(20, 16, 20, 18)
    vl.setSpacing(14)

    # ── Header: "Powered by Dishy" left, serving context right ───────────────
    hdr_row = QHBoxLayout()
    robot_ic = QLabel()
    robot_ic.setPixmap(qta.icon("fa5s.robot", color="#34d399").pixmap(QSize(13, 13)))
    robot_ic.setStyleSheet("background: transparent;")
    powered_lbl = QLabel("Powered by Dishy")
    powered_lbl.setStyleSheet(
        "background: transparent; color: #34d399; font-size: 12px; font-weight: 700;"
    )
    hdr_row.addWidget(robot_ic)
    hdr_row.addSpacing(7)
    hdr_row.addWidget(powered_lbl)
    hdr_row.addStretch()
    is_per_serving = int(servings or 1) > 1
    ctx_txt = f"Per serving  ·  ÷ {servings}" if is_per_serving else "Whole recipe"
    ctx_lbl = QLabel(ctx_txt)
    ctx_lbl.setStyleSheet(
        f"background: transparent; color: {theme_manager.c('#555555', '#888888')}; font-size: 11px;"
    )
    hdr_row.addWidget(ctx_lbl)
    vl.addLayout(hdr_row)

    # ── Macro tiles — fill full width, no borders, coloured tints ────────────
    macros_row = QHBoxLayout()
    macros_row.setSpacing(6)

    def _v(key: str, alt: str = "") -> float:
        v = float(per_serving.get(key, 0) or 0)
        if not v and alt:
            v = float(per_serving.get(alt, 0) or 0)
        return v

    for val, label, colour, bg_d, bg_l in [
        (_v("kcal"),                 "kcal",    "#ff6b35",
         "rgba(255,107,53,0.13)",   "rgba(255,107,53,0.09)"),
        (_v("protein_g", "protein"), "protein", "#4caf8a",
         "rgba(76,175,138,0.13)",   "rgba(76,175,138,0.09)"),
        (_v("fat_g",     "fat"),     "fat",     "#f0a500",
         "rgba(240,165,0,0.13)",    "rgba(240,165,0,0.09)"),
        (_v("carbs_g",   "carbs"),   "carbs",   "#7c6af7",
         "rgba(124,106,247,0.13)",  "rgba(124,106,247,0.09)"),
        (_v("fiber_g",   "fiber"),   "fiber",   "#f06292",
         "rgba(240,98,146,0.13)",   "rgba(240,98,146,0.09)"),
        (_v("sugar_g",   "sugar"),   "sugar",   "#c084fc",
         "rgba(192,132,252,0.13)",  "rgba(192,132,252,0.09)"),
    ]:
        tile = QWidget()
        tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tile.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tile.setStyleSheet(
            f"background: {theme_manager.c(bg_d, bg_l)}; border-radius: 10px; border: none;"
        )
        tl = QVBoxLayout(tile)
        tl.setContentsMargins(6, 14, 6, 14)
        tl.setSpacing(5)
        num_lbl = QLabel(f"{round(val)}" if label == "kcal" else f"{round(val, 1)}")
        num_lbl.setStyleSheet(
            f"color: {colour}; font-size: 26px; font-weight: 800;"
            " background: transparent; border: none;"
        )
        lbl_lbl = QLabel(label)
        lbl_lbl.setStyleSheet(
            f"color: {theme_manager.c('#666666', '#888888')}; font-size: 10px; font-weight: 600;"
            " letter-spacing: 0.5px; background: transparent; border: none;"
        )
        tl.addWidget(num_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        tl.addWidget(lbl_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        macros_row.addWidget(tile, 1)   # stretch=1 so all tiles share width equally

    vl.addLayout(macros_row)

    if on_log_today:
        log_row = QHBoxLayout()
        log_row.addStretch()
        log_btn = QPushButton("  Log to Today")
        log_btn.setObjectName("ghost-btn")
        log_btn.setIcon(qta.icon("fa5s.plus-circle", color="#34d399"))
        log_btn.setIconSize(QSize(12, 12))
        log_btn.setFixedHeight(34)
        log_btn.setToolTip("Log this meal to today's nutrition tracker")
        log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        log_btn.clicked.connect(on_log_today)
        log_row.addWidget(log_btn)
        vl.addLayout(log_row)

    return card


# ── Add-to-Calendar dialog ───────────────────────────────────────────────────

class AddToCalendarDialog(QDialog):
    def __init__(self, recipe_title: str, recipe_id: int, db: Database, parent=None):
        super().__init__(parent)
        self._db = db
        self._recipe_id = recipe_id
        self._recipe_title = recipe_title
        self.setWindowTitle("Add to Meal Planner")
        self.setMinimumWidth(340)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(22, 20, 22, 20)

        title = QLabel(f"Add  \"{self._recipe_title[:36]}\"  to the calendar")
        title.setWordWrap(True)
        title.setStyleSheet("color: #f0f0f0; font-size: 13px; font-weight: 600; background: transparent;")
        layout.addWidget(title)

        # Week
        today = datetime.now().date()
        monday = today - timedelta(days=today.weekday())
        self._week_combo = QComboBox()
        for i in range(4):
            ws = monday + timedelta(weeks=i)
            label = "This week" if i == 0 else ("Next week" if i == 1 else ws.strftime("%d %b"))
            self._week_combo.addItem(label, ws.isoformat())
        layout.addWidget(QLabel("Week"))
        layout.addWidget(self._week_combo)

        # Day
        self._day_combo = QComboBox()
        for d in DAYS:
            self._day_combo.addItem(d)
        current_day = today.strftime("%A")
        if current_day in DAYS:
            self._day_combo.setCurrentIndex(DAYS.index(current_day))
        layout.addWidget(QLabel("Day"))
        layout.addWidget(self._day_combo)

        # Meal type
        self._meal_combo = QComboBox()
        for m in MEAL_TYPES:
            self._meal_combo.addItem(m.capitalize(), m)
        layout.addWidget(QLabel("Meal"))
        layout.addWidget(self._meal_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        week_start = self._week_combo.currentData()
        day = self._day_combo.currentText()
        meal_type = self._meal_combo.currentData()
        self._db.set_meal_slot(
            week_start, day, meal_type,
            custom_name=self._recipe_title,
            recipe_id=self._recipe_id,
        )
        self.accept()


# ── Image helpers ─────────────────────────────────────────────────────────────

def _rounded_top_pixmap(source_path: str, w: int, h: int, radius: int = 11) -> QPixmap:
    """Load, center-crop to w×h, and round only the top two corners."""
    src = QPixmap(source_path).scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    if src.height() > h:
        src = src.copy(0, (src.height() - h) // 2, src.width(), h)
    if src.width() > w:
        src = src.copy((src.width() - w) // 2, 0, w, src.height())
    result = QPixmap(w, h)
    result.fill(Qt.GlobalColor.transparent)
    p = QPainter(result)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.moveTo(radius, 0)
    clip.lineTo(w - radius, 0)
    clip.quadTo(w, 0, w, radius)
    clip.lineTo(w, h)
    clip.lineTo(0, h)
    clip.lineTo(0, radius)
    clip.quadTo(0, 0, radius, 0)
    p.setClipPath(clip)
    p.drawPixmap(0, 0, src)
    p.end()
    return result


def _resolve_photo_path(recipe: dict, data: dict) -> tuple[str, bool]:
    """Return (path_or_url, is_http) for the best available image source.

    Priority:
      1. image_url column — if it's an HTTP URL (e.g. Supabase Storage CDN)
      2. data_json.photo_path — if it's a local file that exists
      3. Empty string (caller shows placeholder icon)
    """
    import os as _os
    image_url = (recipe.get("image_url") or "").strip()
    if image_url.startswith(("http://", "https://")):
        return image_url, True
    photo_path = (data.get("photo_path") or "").strip()
    if photo_path and _os.path.exists(photo_path):
        return photo_path, False
    return "", False


def _cached_image_path(url: str) -> str | None:
    """Return a local cache path for *url*, downloading if needed (blocking).

    Returns None on failure.  Called from a run_async worker — never on the
    main thread.
    """
    import hashlib, os, tempfile
    cache_dir = os.path.join(tempfile.gettempdir(), "dishboard_img_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(
        cache_dir, hashlib.md5(url.encode()).hexdigest() + ".jpg"
    )
    if os.path.exists(cache_file):
        return cache_file
    try:
        import requests
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        with open(cache_file, "wb") as fh:
            fh.write(r.content)
        return cache_file
    except Exception:
        return None


# ── Recipe card (grid view) ───────────────────────────────────────────────────

class RecipeCard(QWidget):
    """Card widget used in the 3-column recipe grid."""

    _GRID_COLS = 3

    def __init__(self, recipe: dict, on_select, on_delete, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(248)

        data = {}
        try:
            data = json.loads(recipe.get("data_json") or "{}")
        except Exception:
            pass

        icon_name   = data.get("icon",        "fa5s.utensils")
        colour      = data.get("colour",      "#ff6b35")
        is_fav      = bool(recipe.get("is_favourite", 0))
        description = data.get("description", "").strip()
        tags        = data.get("tags",        [])
        cook_time   = int(
            data.get("cook_time", 0) or data.get("total_time", 0)
            or recipe.get("ready_mins") or 0
        )
        servings    = str(data.get("servings", "") or recipe.get("servings", "") or "").strip()
        title       = recipe.get("title", "")

        card_bg     = theme_manager.c("#111111", "#ffffff")
        card_border = theme_manager.c("#1e1e1e", "#e5e5e5")
        footer_bg   = theme_manager.c("#0c0c0c", "#f7f7f7")

        self.setObjectName("recipe-card")
        self.setStyleSheet(
            f"#recipe-card {{ background-color: {card_bg}; border-radius: 12px;"
            f" border: 1px solid {card_border}; }}"
            "#recipe-card:hover { border-color: rgba(124,106,247,0.55); }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Banner ────────────────────────────────────────────────────────────
        BANNER_H = 110
        banner = QLabel()
        banner.setFixedHeight(BANNER_H)
        banner.setAlignment(Qt.AlignmentFlag.AlignCenter)

        banner_bg = theme_manager.c("#0d0d0d", "#f0f0f0")
        _placeholder_style = (
            f"background-color: {banner_bg};"
            " border-top-left-radius: 11px; border-top-right-radius: 11px;"
        )

        img_source, is_http = _resolve_photo_path(recipe, data)
        if img_source and not is_http:
            # Local file — load synchronously (fast, already on disk)
            banner.setStyleSheet("background: transparent;")
            px = _rounded_top_pixmap(img_source, 600, BANNER_H, radius=11)
            banner.setPixmap(px)
        elif img_source and is_http:
            # Remote URL — show placeholder first, then load asynchronously
            banner.setStyleSheet(_placeholder_style)
            banner.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(48, 48)))
            self._banner_lbl = banner
            self._load_banner_async(img_source, 600, BANNER_H)
        else:
            banner.setStyleSheet(_placeholder_style)
            banner.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(48, 48)))
        outer.addWidget(banner)

        # thin separator under banner
        sep_top = QWidget()
        sep_top.setFixedHeight(1)
        sep_top.setStyleSheet(f"background: {card_border};")
        outer.addWidget(sep_top)

        # ── Body ──────────────────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 11, 14, 10)
        bl.setSpacing(5)

        title_lbl = QLabel(title)
        title_lbl.setWordWrap(True)
        title_lbl.setMaximumHeight(38)
        title_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 700;"
            f" color: {theme_manager.c('#e0e0e0', '#1a1a1a')};"
            " background: transparent;"
        )
        bl.addWidget(title_lbl)

        if description:
            desc_lbl = QLabel(description[:130] + ("…" if len(description) > 130 else ""))
            desc_lbl.setWordWrap(True)
            desc_lbl.setMaximumHeight(30)
            desc_lbl.setStyleSheet(
                f"font-size: 11px; line-height: 1.4;"
                f" color: {theme_manager.c('#606060', '#888888')};"
                " background: transparent;"
            )
            bl.addWidget(desc_lbl)

        if tags:
            tags_w = QWidget()
            tags_w.setStyleSheet("background: transparent;")
            tr = QHBoxLayout(tags_w)
            tr.setContentsMargins(0, 2, 0, 0)
            tr.setSpacing(4)
            _MEAL_SET = {"Breakfast", "Lunch", "Dinner", "Snack", "Dessert"}
            for tag in tags[:3]:
                is_meal   = tag in _MEAL_SET
                is_dishy  = tag == "Dishy"
                is_online = tag == "Online"
                if is_dishy or is_online:
                    _ic_name = "fa5s.robot"  if is_dishy  else "fa5s.globe"
                    _colour  = "#34d399"     if is_dishy  else "#4fc3f7"
                    _bg      = "rgba(52,211,153,0.12)" if is_dishy else "rgba(79,195,247,0.12)"
                    _label   = "Dishy"       if is_dishy  else "Online"
                    chip_w = QWidget()
                    chip_w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                    chip_w.setStyleSheet(f"background: {_bg}; border-radius: 4px;")
                    chip_hl = QHBoxLayout(chip_w)
                    chip_hl.setContentsMargins(5, 1, 7, 1)
                    chip_hl.setSpacing(3)
                    ic = QLabel()
                    ic.setPixmap(qta.icon(_ic_name, color=_colour).pixmap(QSize(9, 9)))
                    ic.setStyleSheet("background: transparent;")
                    txt = QLabel(_label)
                    txt.setStyleSheet(
                        f"color: {_colour}; font-size: 10px; font-weight: 700;"
                        " background: transparent;"
                    )
                    chip_hl.addWidget(ic)
                    chip_hl.addWidget(txt)
                    tr.addWidget(chip_w)
                else:
                    chip_bg  = "rgba(76,175,138,0.12)" if is_meal else "rgba(255,107,53,0.10)"
                    chip_fg  = "#4caf8a" if is_meal else "#ff6b35"
                    chip_bdr = "rgba(76,175,138,0.3)" if is_meal else "rgba(255,107,53,0.3)"
                    chip = QLabel(tag)
                    chip.setStyleSheet(
                        f"background: {chip_bg}; color: {chip_fg};"
                        f" border: 1px solid {chip_bdr}; border-radius: 4px;"
                        " font-size: 10px; font-weight: 600; padding: 1px 7px;"
                    )
                    tr.addWidget(chip)
            tr.addStretch()
            bl.addWidget(tags_w)

        bl.addStretch()
        outer.addWidget(body, 1)

        # ── Footer ────────────────────────────────────────────────────────────
        sep_bot = QWidget()
        sep_bot.setFixedHeight(1)
        sep_bot.setStyleSheet(f"background: {card_border};")
        outer.addWidget(sep_bot)

        footer = QWidget()
        footer.setStyleSheet(
            f"background: {footer_bg};"
            " border-bottom-left-radius: 11px; border-bottom-right-radius: 11px;"
        )
        footer.setFixedHeight(36)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(12, 0, 10, 0)
        fl.setSpacing(8)

        meta_col = theme_manager.c("#505050", "#aaaaaa")
        meta_style = f"color: {meta_col}; font-size: 11px; background: transparent;"
        if cook_time:
            t_ic = QLabel()
            t_ic.setPixmap(qta.icon("fa5s.clock", color=meta_col).pixmap(QSize(10, 10)))
            t_ic.setStyleSheet("background: transparent;")
            t_lbl = QLabel(f"{cook_time} min")
            t_lbl.setStyleSheet(meta_style)
            fl.addWidget(t_ic)
            fl.addWidget(t_lbl)
        if servings:
            s_ic = QLabel()
            s_ic.setPixmap(qta.icon("fa5s.user-friends", color=meta_col).pixmap(QSize(10, 10)))
            s_ic.setStyleSheet("background: transparent;")
            s_lbl = QLabel(f"Serves {servings}")
            s_lbl.setStyleSheet(meta_style)
            fl.addWidget(s_ic)
            fl.addWidget(s_lbl)
        fl.addStretch()

        fav_lbl = QLabel()
        _star_dim = theme_manager.c("#3a3a3a", "#aaaaaa")
        fav_lbl.setPixmap(
            qta.icon("fa5s.star", color="#fbbf24" if is_fav else _star_dim).pixmap(QSize(12, 12))
        )
        fav_lbl.setStyleSheet("background: transparent;")
        fl.addWidget(fav_lbl)

        _trash_dim = theme_manager.c("#444444", "#aaaaaa")
        del_btn = QPushButton()
        del_btn.setObjectName("delete-btn")
        del_btn.setIcon(qta.icon("fa5s.trash-alt", color=_trash_dim))
        del_btn.setIconSize(QSize(11, 11))
        del_btn.setFixedSize(24, 24)
        del_btn.clicked.connect(on_delete)
        del_btn.enterEvent = lambda _: del_btn.setIcon(qta.icon("fa5s.trash-alt", color="#ef4444"))
        del_btn.leaveEvent = lambda _: del_btn.setIcon(
            qta.icon("fa5s.trash-alt", color=theme_manager.c("#444444", "#aaaaaa"))
        )
        fl.addWidget(del_btn)

        outer.addWidget(footer)

        self.mousePressEvent = lambda e: on_select()

    def _load_banner_async(self, url: str, w: int, h: int) -> None:
        """Download *url* in a background thread and update the banner pixmap."""
        from utils.workers import run_async

        def _work():
            return _cached_image_path(url)

        def _done(cached: str | None):
            if not cached:
                return
            try:
                if not self._banner_lbl or not self._banner_lbl.isVisible():
                    return
                px = _rounded_top_pixmap(cached, w, h, radius=11)
                self._banner_lbl.setStyleSheet("background: transparent;")
                self._banner_lbl.setPixmap(px)
            except Exception:
                pass

        run_async(_work, on_result=_done, on_error=lambda _: None)


# ── Saved-recipe row (legacy — kept for search result detail) ─────────────────

class SavedRecipeRow(QWidget):
    def __init__(self, recipe: dict, on_select, on_delete, parent=None):
        super().__init__(parent)
        self.setObjectName("shopping-item")
        self.setFixedHeight(68)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        data = {}
        try:
            data = json.loads(recipe.get("data_json") or "{}")
        except Exception:
            pass

        icon_name  = data.get("icon", "fa5s.utensils")
        colour     = data.get("colour", "#ff6b35")
        is_fav     = bool(recipe.get("is_favourite", 0))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 14, 0)
        layout.setSpacing(12)

        ic = QLabel()
        ic.setFixedSize(48, 48)
        ic.setStyleSheet(
            f"background-color: {theme_manager.c('#141414', '#f0f0f0')};"
            " border-radius: 8px; background: transparent;"
        )
        img_source, is_http = _resolve_photo_path(recipe, data)
        if img_source and not is_http:
            px = QPixmap(img_source).scaled(
                48, 48,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            if px.width() > 48 or px.height() > 48:
                px = px.copy((px.width() - 48) // 2, (px.height() - 48) // 2, 48, 48)
            ic.setPixmap(px)
        elif img_source and is_http:
            ic.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(22, 22)))
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._ic_lbl = ic
            self._load_thumb_async(img_source)
        else:
            ic.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(22, 22)))
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_txt = recipe.get("title", "")
        name_lbl = QLabel(title_txt[:60] + ("…" if len(title_txt) > 60 else ""))
        name_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#d4d4d4', '#1a1a1a')};"
            " font-size: 13px; font-weight: 500;"
        )
        tags = data.get("tags", [])
        tag_str = "  ·  ".join(tags[:3])
        sub_lbl = QLabel(tag_str or recipe.get("source", ""))
        sub_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#555555', '#888888')};"
            " font-size: 11px;"
        )
        text_col.addWidget(name_lbl)
        text_col.addWidget(sub_lbl)

        fav_lbl = QLabel()
        _star_dim2 = theme_manager.c("#3a3a3a", "#aaaaaa")
        fav_lbl.setPixmap(
            qta.icon("fa5s.star", color="#fbbf24" if is_fav else _star_dim2).pixmap(QSize(13, 13))
        )
        fav_lbl.setStyleSheet("background: transparent;")

        _trash_dim2 = theme_manager.c("#444444", "#aaaaaa")
        del_btn = QPushButton()
        del_btn.setObjectName("delete-btn")
        del_btn.setIcon(qta.icon("fa5s.trash-alt", color=_trash_dim2))
        del_btn.setIconSize(QSize(12, 12))
        del_btn.setFixedSize(26, 26)
        del_btn.clicked.connect(on_delete)
        del_btn.enterEvent = lambda _: del_btn.setIcon(qta.icon("fa5s.trash-alt", color="#ef4444"))
        del_btn.leaveEvent = lambda _: del_btn.setIcon(
            qta.icon("fa5s.trash-alt", color=theme_manager.c("#444444", "#aaaaaa"))
        )

        layout.addWidget(ic)
        layout.addLayout(text_col, 1)
        layout.addWidget(fav_lbl)
        layout.addWidget(del_btn)

        self.mousePressEvent = lambda e: on_select()

    def _load_thumb_async(self, url: str) -> None:
        """Download *url* and update the 48×48 thumbnail icon asynchronously."""
        from utils.workers import run_async

        def _work():
            return _cached_image_path(url)

        def _done(cached: str | None):
            if not cached:
                return
            try:
                if not self._ic_lbl or not self._ic_lbl.isVisible():
                    return
                px = QPixmap(cached).scaled(
                    48, 48,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if px.width() > 48 or px.height() > 48:
                    px = px.copy(
                        (px.width() - 48) // 2,
                        (px.height() - 48) // 2,
                        48, 48,
                    )
                self._ic_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._ic_lbl.setPixmap(px)
            except Exception:
                pass

        run_async(_work, on_result=_done, on_error=lambda _: None)


# ── Search result card ────────────────────────────────────────────────────────

class SearchResultRow(QWidget):
    """Modern card-style search result. Shows title, source domain, snippet
    and a Dishy AI badge indicating macros will be auto-analysed on import."""

    def __init__(self, result: dict, on_select, parent=None):
        super().__init__(parent)
        self._callback = lambda: on_select(result)
        tm = theme_manager

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(86)

        self._normal_bg  = tm.c("#161616", "#ffffff")
        self._hover_bg   = tm.c("#1c1c1c", "#f5f5f5")
        self._normal_bdr = tm.c("#242424", "#e8e8e8")
        self._hover_bdr  = "#ff6b35"
        self._apply_style(hover=False)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(14)

        # Site initial badge
        host = urlparse(result.get("url", "")).netloc.replace("www.", "")
        initial = host[0].upper() if host else "R"
        site_badge = QLabel(initial)
        site_badge.setFixedSize(38, 38)
        site_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        site_badge.setStyleSheet(
            f"background: {tm.c('#242424', '#f0f0f0')};"
            " border-radius: 10px;"
            f" color: {tm.c('#888888', '#999999')};"
            " font-size: 15px; font-weight: 700;"
        )

        # Text column
        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        text_col.setContentsMargins(0, 0, 0, 0)

        title = result.get("title", "")
        title_lbl = QLabel(title[:78] + ("…" if len(title) > 78 else ""))
        title_lbl.setStyleSheet(
            f"background: transparent;"
            f" color: {tm.c('#e8e8e8', '#111111')};"
            " font-size: 13px; font-weight: 600;"
        )

        # Domain + Dishy badge row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        meta_row.setContentsMargins(0, 0, 0, 0)

        host_lbl = QLabel(host)
        host_lbl.setStyleSheet(
            f"background: transparent;"
            f" color: {tm.c('#555555', '#999999')};"
            " font-size: 11px;"
        )

        dishy_badge = QLabel("✦  Dishy macros")
        dishy_badge.setStyleSheet(
            "background: rgba(52,211,153,0.13);"
            " color: #34d399;"
            " font-size: 10px; font-weight: 700;"
            " border-radius: 4px; padding: 2px 7px;"
        )

        meta_row.addWidget(host_lbl)
        meta_row.addWidget(dishy_badge)
        meta_row.addStretch()

        text_col.addWidget(title_lbl)
        text_col.addLayout(meta_row)

        snippet = result.get("snippet", "")
        if snippet:
            snippet_lbl = QLabel(snippet[:110] + ("…" if len(snippet) > 110 else ""))
            snippet_lbl.setStyleSheet(
                f"background: transparent;"
                f" color: {tm.c('#484848', '#999999')};"
                " font-size: 11px;"
            )
            snippet_lbl.setWordWrap(False)
            text_col.addWidget(snippet_lbl)

        # Arrow
        arrow_lbl = QLabel()
        arrow_lbl.setPixmap(
            qta.icon("fa5s.chevron-right", color=tm.c("#444444", "#cccccc")).pixmap(QSize(10, 10))
        )
        arrow_lbl.setStyleSheet("background: transparent;")

        outer.addWidget(site_badge)
        outer.addLayout(text_col, 1)
        outer.addWidget(arrow_lbl)

    def _apply_style(self, hover: bool):
        bg  = self._hover_bg  if hover else self._normal_bg
        bdr = self._hover_bdr if hover else self._normal_bdr
        self.setStyleSheet(
            f"SearchResultRow {{ background: {bg}; border: 1px solid {bdr};"
            " border-radius: 10px; }"
        )

    def enterEvent(self, event):
        self._apply_style(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(hover=False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._callback()
        super().mousePressEvent(event)


# ── Create-recipe form helpers ───────────────────────────────────────────────

class _DynamicList(QWidget):
    """Numbered list of instruction steps with Enter-to-add-next."""

    _FONT = (
        'font-family: "SF Pro Display","SF Pro Text",-apple-system,'
        '".AppleSystemUIFont","Helvetica Neue",Arial,sans-serif;'
    )

    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        self._placeholder = placeholder
        self.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._fields: list[QLineEdit] = []
        self._num_labels: list[QLabel] = []
        self._rm_btns: list[QPushButton] = []

        add_btn = QPushButton("  + Add step")
        add_btn.setObjectName("ghost-btn")
        add_btn.setFixedHeight(40)
        add_btn.clicked.connect(lambda: self._add_field(focus=True))
        self._layout.addWidget(add_btn)
        self._add_btn = add_btn

        self._add_field()  # start with one empty step

    def _renumber(self):
        for i, lbl in enumerate(self._num_labels):
            lbl.setText(f"{i + 1}.")

    def _add_field(self, text: str = "", focus: bool = False):
        step_n = len(self._fields) + 1
        row = QHBoxLayout()
        row.setSpacing(10)

        num_lbl = QLabel(f"{step_n}.")
        num_lbl.setFixedWidth(28)
        num_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        num_lbl.setStyleSheet(
            f"color: #ff6b35; font-size: 15px; font-weight: 700;"
            f" background: transparent; {self._FONT}"
        )
        self._num_labels.append(num_lbl)

        field = QLineEdit()
        field.setPlaceholderText(self._placeholder)
        field.setFixedHeight(44)
        field.setStyleSheet(
            "QLineEdit {"
            f" background: {theme_manager.c('#111111', '#ffffff')};"
            f" color: {theme_manager.c('#d4d4d4', '#1a1a1a')};"
            f" border: 1px solid {theme_manager.c('#1c1c1c', '#d5d5d5')};"
            f" border-radius: 9px; padding: 0 14px; font-size: 14px; {self._FONT}"
            "}"
            "QLineEdit:focus { border-color: rgba(255,107,53,0.5); }"
        )
        if text:
            field.setText(text)
        self._fields.append(field)
        field.returnPressed.connect(lambda f=field: self._on_enter(f))

        rm_btn = QPushButton()
        rm_btn.setObjectName("delete-btn")
        rm_btn.setIcon(qta.icon("fa5s.times", color=theme_manager.c("#555555", "#888888")))
        rm_btn.setIconSize(QSize(11, 11))
        rm_btn.setFixedSize(30, 30)
        rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rm_btn.enterEvent = lambda _, b=rm_btn: b.setIcon(qta.icon("fa5s.times", color="#ef4444"))
        rm_btn.leaveEvent = lambda _, b=rm_btn: b.setIcon(
            qta.icon("fa5s.times", color=theme_manager.c("#555555", "#888888"))
        )
        self._rm_btns.append(rm_btn)

        def _remove(_f=field, _nl=num_lbl, _rb=rm_btn):
            if len(self._fields) <= 1:
                return
            self._fields.remove(_f)
            self._num_labels.remove(_nl)
            if _rb in self._rm_btns:
                self._rm_btns.remove(_rb)
            for i in range(self._layout.count()):
                item = self._layout.itemAt(i)
                if item and item.layout():
                    for j in range(item.layout().count()):
                        w = item.layout().itemAt(j)
                        if w and w.widget() is _f:
                            while item.layout().count():
                                child = item.layout().takeAt(0)
                                if child.widget():
                                    child.widget().deleteLater()
                            self._layout.takeAt(i)
                            break
            self._renumber()

        rm_btn.clicked.connect(_remove)
        row.addWidget(num_lbl)
        row.addWidget(field, 1)
        row.addWidget(rm_btn)
        # insert before the Add button (always last)
        self._layout.insertLayout(self._layout.count() - 1, row)
        if focus:
            field.setFocus()

    def _on_enter(self, field: QLineEdit):
        """If cursor is on the last field and it has content, add the next step."""
        if field is self._fields[-1] and field.text().strip():
            self._add_field(focus=True)

    def apply_theme(self, _mode=None):
        col = theme_manager.c("#555555", "#888888")
        for btn in self._rm_btns:
            btn.setIcon(qta.icon("fa5s.times", color=col))
        # Re-apply input styles
        fg  = theme_manager.c("#d4d4d4", "#1a1a1a")
        bg  = theme_manager.c("#111111", "#ffffff")
        bdr = theme_manager.c("#1c1c1c", "#d5d5d5")
        style = (
            "QLineEdit {"
            f" background: {bg}; color: {fg};"
            f" border: 1px solid {bdr};"
            f" border-radius: 9px; padding: 0 14px; font-size: 14px; {self._FONT}"
            "}"
            "QLineEdit:focus { border-color: rgba(255,107,53,0.5); }"
        )
        for field in self._fields:
            field.setStyleSheet(style)

    def values(self) -> list[str]:
        return [f.text().strip() for f in self._fields if f.text().strip()]

    def set_values(self, items: list[str]):
        """Pre-populate fields (edit mode)."""
        # Remove all rows (layout items that are QHBoxLayout, not the add button)
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
        self._fields.clear()
        self._num_labels.clear()
        self._rm_btns.clear()
        for text in items:
            self._add_field(text=text)
        if not items:
            self._add_field()


class _IconPicker(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._selected = RECIPE_ICONS[0][0]
        self._btns: dict[str, QPushButton] = {}

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)

        for idx, (icon_name, label) in enumerate(RECIPE_ICONS):
            btn = QPushButton()
            btn.setToolTip(label)
            btn.setCheckable(True)
            btn.setFixedSize(36, 36)
            btn.setIcon(qta.icon(icon_name, color="#888888"))
            btn.setIconSize(QSize(16, 16))
            btn.clicked.connect(lambda _, n=icon_name: self._select(n))
            self._btns[icon_name] = btn
            grid.addWidget(btn, idx // 10, idx % 10)

        self._btns[self._selected].setChecked(True)
        self._apply_styles()

    def _apply_styles(self):
        bg  = theme_manager.c("#141414", "#f0f0f0")
        bdr = theme_manager.c("#1e1e1e", "#d5d5d5")
        style = (
            f"QPushButton {{ background-color: {bg}; border-radius: 6px;"
            f" border: 1px solid {bdr}; }}"
            "QPushButton:checked { background-color: rgba(255,107,53,0.18);"
            " border: 1px solid #ff6b35; }"
        )
        for btn in self._btns.values():
            btn.setStyleSheet(style)

    def apply_theme(self, _mode=None):
        self._apply_styles()

    def _select(self, icon_name: str):
        if self._selected in self._btns:
            self._btns[self._selected].setChecked(False)
        self._selected = icon_name
        self._btns[icon_name].setChecked(True)

    def value(self) -> str:
        return self._selected

    def set_value(self, icon_name: str):
        if icon_name in self._btns:
            self._select(icon_name)


class _ColourPicker(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._selected = RECIPE_COLOURS[0][0]
        self._btns: dict[str, QPushButton] = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        for colour, name in RECIPE_COLOURS:
            btn = QPushButton()
            btn.setToolTip(name)
            btn.setCheckable(True)
            btn.setFixedSize(28, 28)
            btn.clicked.connect(lambda _, c=colour: self._select(c))
            self._btns[colour] = btn
            row.addWidget(btn)

        row.addStretch()
        self._btns[self._selected].setChecked(True)
        self._apply_styles()

    def _apply_styles(self):
        checked_border = theme_manager.c("#ffffff", "#222222")
        for colour, btn in self._btns.items():
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {colour}; border-radius: 14px;"
                " border: 2px solid transparent; }"
                f"QPushButton:checked {{ border: 2px solid {checked_border}; }}"
            )

    def apply_theme(self, _mode=None):
        self._apply_styles()

    def _select(self, colour: str):
        if self._selected in self._btns:
            self._btns[self._selected].setChecked(False)
        self._selected = colour
        self._btns[colour].setChecked(True)

    def value(self) -> str:
        return self._selected

    def set_value(self, colour: str):
        if colour in self._btns:
            self._select(colour)


class _TagPicker(QWidget):
    _MEAL_TAGS = ["Breakfast", "Lunch", "Dinner", "Snack", "Dessert"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._active: set[str] = set()
        self._btns: dict[str, QPushButton] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # ── Meal-type tags ────────────────────────────────────────────────
        meal_lbl = QLabel("MEAL TYPE")
        meal_lbl.setStyleSheet(
            "color: #4caf8a; font-size: 10px; font-weight: 700;"
            " letter-spacing: 1.5px; background: transparent;"
        )
        outer.addWidget(meal_lbl)

        meal_row = QHBoxLayout()
        meal_row.setContentsMargins(0, 0, 0, 0)
        meal_row.setSpacing(6)
        for tag in self._MEAL_TAGS:
            btn = QPushButton(tag)
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setStyleSheet(
                "QPushButton { background-color: rgba(76,175,138,0.08); color: #4caf8a;"
                " border-radius: 7px; border: 1px solid rgba(76,175,138,0.3);"
                " font-size: 12px; font-weight: 600; padding: 0 16px; }"
                "QPushButton:checked { background-color: rgba(76,175,138,0.22);"
                " color: #4caf8a; border: 1.5px solid rgba(76,175,138,0.7); }"
                "QPushButton:hover { background-color: rgba(76,175,138,0.15); }"
            )
            btn.clicked.connect(lambda _, t=tag: self._toggle(t))
            self._btns[tag] = btn
            meal_row.addWidget(btn)
        meal_row.addStretch()
        outer.addLayout(meal_row)

        # ── Separator ─────────────────────────────────────────────────────
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {theme_manager.c('#1c1c1c', '#e0e0e0')};")
        outer.addWidget(sep)

        # ── Descriptive tags ──────────────────────────────────────────────
        desc_lbl = QLabel("DESCRIPTIVE TAGS")
        desc_lbl.setStyleSheet(
            f"color: {theme_manager.c('#666666', '#555555')}; font-size: 10px; font-weight: 700;"
            " letter-spacing: 1.5px; background: transparent;"
        )
        outer.addWidget(desc_lbl)

        self._other_tags = [t for t in RECIPE_TAGS if t not in set(self._MEAL_TAGS)]
        flow_widget = QWidget()
        flow_widget.setStyleSheet("background: transparent;")
        flow = QGridLayout(flow_widget)
        flow.setContentsMargins(0, 0, 0, 0)
        flow.setSpacing(6)
        for idx, tag in enumerate(self._other_tags):
            btn = QPushButton(tag)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, t=tag: self._toggle(t))
            self._btns[tag] = btn
            flow.addWidget(btn, idx // 4, idx % 4)
        outer.addWidget(flow_widget)
        self._apply_desc_styles()

    def _apply_desc_styles(self):
        bg  = theme_manager.c("#141414", "#f0f0f0")
        fg  = theme_manager.c("#666666", "#555555")
        bdr = theme_manager.c("#1e1e1e", "#d5d5d5")
        hov = theme_manager.c("#181818", "#e2e2e2")
        hov_fg = theme_manager.c("#888888", "#333333")
        style = (
            f"QPushButton {{ background-color: {bg}; color: {fg}; border-radius: 5px;"
            f" border: 1px solid {bdr}; font-size: 11px; padding: 0 10px; }}"
            "QPushButton:checked { background-color: rgba(255,107,53,0.15);"
            " color: #ff6b35; border: 1px solid rgba(255,107,53,0.4); }"
            f"QPushButton:hover {{ background-color: {hov}; color: {hov_fg}; }}"
        )
        for tag in self._other_tags:
            if tag in self._btns:
                self._btns[tag].setStyleSheet(style)

    def apply_theme(self, _mode=None):
        self._apply_desc_styles()

    def _toggle(self, tag: str):
        if tag in self._active:
            self._active.discard(tag)
            self._btns[tag].setChecked(False)
        else:
            self._active.add(tag)
            self._btns[tag].setChecked(True)

    def values(self) -> list[str]:
        return [t for t in RECIPE_TAGS if t in self._active]

    def set_values(self, tags: list[str]):
        """Pre-select tags (edit mode)."""
        for tag in list(self._active):
            self._btns[tag].setChecked(False)
        self._active.clear()
        for tag in tags:
            if tag in self._btns:
                self._btns[tag].setChecked(True)
                self._active.add(tag)


# ── Create recipe helpers ────────────────────────────────────────────────────


def _card_section_header(icon_name: str, text: str, colour: str) -> QHBoxLayout:
    """Returns a QHBoxLayout row with a coloured icon + uppercase label."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    ic = QLabel()
    ic.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(13, 13)))
    ic.setStyleSheet("background: transparent;")
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {colour}; font-size: 11px; font-weight: 700;"
        " letter-spacing: 1.5px; background: transparent;"
    )
    row.addWidget(ic)
    row.addWidget(lbl)
    row.addStretch()
    return row


class _CollapsibleCard(QWidget):
    """A plan-card style widget whose body can be shown/hidden via a toggle header."""

    def __init__(self, title: str, icon_name: str = "fa5s.palette",
                 colour: str = "#a78bfa", parent=None):
        super().__init__(parent)
        self.setObjectName("plan-card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Clickable header ──────────────────────────────────────────────
        self._hdr_btn = QPushButton()
        self._hdr_btn.setFixedHeight(54)
        self._hdr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hdr_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; }"
            f"QPushButton:hover {{ background: {theme_manager.c('rgba(255,255,255,0.025)', 'rgba(0,0,0,0.025)')};"
            " border-radius: 12px; }"
        )
        self._hdr_btn.clicked.connect(self._toggle)

        hl = QHBoxLayout(self._hdr_btn)
        hl.setContentsMargins(22, 0, 18, 0)
        hl.setSpacing(10)

        ic_lbl = QLabel()
        ic_lbl.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(14, 14)))
        ic_lbl.setStyleSheet("background: transparent;")

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {colour}; font-size: 15px;"
            " font-weight: 600; background: transparent;"
        )

        self._badge_lbl = QLabel("click to expand")
        self._badge_lbl.setStyleSheet(
            f"color: {theme_manager.c('#3a3a3a', '#bbbbbb')}; font-size: 12px; background: transparent;"
        )

        self._chevron = QLabel()
        self._chevron.setPixmap(
            qta.icon("fa5s.chevron-down", color="#555").pixmap(QSize(10, 10))
        )
        self._chevron.setStyleSheet("background: transparent;")

        hl.addWidget(ic_lbl)
        hl.addWidget(title_lbl, 1)
        hl.addWidget(self._badge_lbl)
        hl.addSpacing(4)
        hl.addWidget(self._chevron)

        outer.addWidget(self._hdr_btn)

        # Divider (shown only when expanded)
        self._divider = QWidget()
        self._divider.setFixedHeight(1)
        self._divider.setStyleSheet(
            f"background: {theme_manager.c('#1e1e1e', '#e5e5e5')};"
        )
        self._divider.setVisible(False)
        outer.addWidget(self._divider)

        # Content body (shown when expanded)
        self._body = QWidget()
        self._body.setStyleSheet("background: transparent;")
        self._body.setVisible(False)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(22, 16, 22, 22)
        self._body_layout.setSpacing(14)
        outer.addWidget(self._body)

    def body(self) -> QVBoxLayout:
        return self._body_layout

    def _toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._divider.setVisible(self._expanded)
        self._badge_lbl.setText("" if self._expanded else "click to expand")
        self._chevron.setPixmap(
            qta.icon(
                "fa5s.chevron-up" if self._expanded else "fa5s.chevron-down",
                color="#666"
            ).pixmap(QSize(10, 10))
        )


# ── Create recipe page ────────────────────────────────────────────────────────

class CreateRecipePage(QScrollArea):
    def __init__(self, db: Database, on_saved, on_cancel, parent=None):
        super().__init__(parent)
        self._edit_id: int | None = None
        self._db = db
        self._on_saved = on_saved
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 16, 48)
        layout.setSpacing(0)

        _text_fg   = theme_manager.c("#e8e8e8", "#1a1a1a")
        _muted     = theme_manager.c("#555555", "#888888")
        _input_bg  = theme_manager.c("#0d0d0d", "#fafafa")
        _input_bdr = theme_manager.c("#222222", "#e0e0e0")
        _card_bg   = theme_manager.c("#111111", "#ffffff")

        # ── Top bar ───────────────────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 22)
        top_bar.setSpacing(12)

        cancel_btn = QPushButton("← Cancel")
        cancel_btn.setObjectName("ghost-btn")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setFixedWidth(120)
        cancel_btn.clicked.connect(on_cancel)
        top_bar.addWidget(cancel_btn)
        top_bar.addStretch()

        # Favourite star toggle (top-right)
        self._fav_btn = QPushButton()
        self._fav_btn.setToolTip("Mark as Favourite")
        self._fav_btn.setCheckable(True)
        self._fav_btn.setFixedSize(42, 42)
        self._fav_btn.setIcon(qta.icon("fa5s.star", color=theme_manager.c("#666666", "#999999")))
        self._fav_btn.setIconSize(QSize(18, 18))
        self._fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fav_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; border-radius: 21px; }"
            "QPushButton:hover { background: rgba(251,191,36,0.12); }"
            "QPushButton:checked { background: rgba(251,191,36,0.18); }"
        )
        self._fav_btn.toggled.connect(lambda on: self._fav_btn.setIcon(
            qta.icon("fa5s.star", color="#fbbf24" if on else theme_manager.c("#666666", "#999999"))
        ))
        top_bar.addWidget(self._fav_btn)
        layout.addLayout(top_bar)

        # ── Page heading ──────────────────────────────────────────────────
        self._heading_lbl = QLabel("Create Your Own Recipe")
        self._heading_lbl.setStyleSheet(
            f"color: {theme_manager.c('#f0f0f0', '#0a0a0a')};"
            " font-size: 28px; font-weight: 700; letter-spacing: -0.5px;"
            " background: transparent;"
        )
        layout.addWidget(self._heading_lbl)
        layout.addSpacing(4)

        sub_lbl = QLabel("Fill in the details — ingredients and instructions are the essentials.")
        sub_lbl.setStyleSheet(f"color: {_muted}; font-size: 14px; background: transparent;")
        layout.addWidget(sub_lbl)
        self._sub_lbl = sub_lbl
        layout.addSpacing(24)

        # ── Two-column content ────────────────────────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(20)
        cols.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── LEFT column ──────────────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(16)
        left.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Shared input style used in multiple cards
        _inp_style = (
            "QLineEdit {"
            f" background: {_input_bg}; color: {_text_fg};"
            f" border: 1.5px solid {_input_bdr}; border-radius: 10px; font-size: 15px;"
            " padding: 6px 12px;"
            "}"
            "QLineEdit:focus { border-color: #ff6b35; }"
        )

        # ── Basics card ───────────────────────────────────────────────────
        basics_card = QWidget()
        basics_card.setObjectName("plan-card")
        bc = QVBoxLayout(basics_card)
        bc.setContentsMargins(24, 22, 24, 26)
        bc.setSpacing(14)

        bc.addLayout(_card_section_header("fa5s.pencil-alt", "BASICS", "#ff6b35"))

        _lbl_style = (
            f"color: {_muted}; font-size: 12px; font-weight: 600;"
            " letter-spacing: 0.4px; background: transparent;"
        )

        # Title
        title_lbl = QLabel("Recipe title *")
        title_lbl.setStyleSheet(_lbl_style)
        bc.addWidget(title_lbl)
        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("e.g. Spicy Thai Basil Chicken")
        self._title_input.setFixedHeight(52)
        self._title_input.setStyleSheet(
            "QLineEdit {"
            f" background: {_input_bg}; color: {_text_fg};"
            f" border: 1.5px solid {_input_bdr}; border-radius: 10px;"
            " font-size: 17px; font-weight: 500;"
            "}"
            "QLineEdit:focus { border-color: #ff6b35; }"
        )
        bc.addWidget(self._title_input)

        # Description
        desc_lbl = QLabel("Short description  (optional)")
        desc_lbl.setStyleSheet(_lbl_style)
        bc.addWidget(desc_lbl)
        self._desc_input = QLineEdit()
        self._desc_input.setPlaceholderText("A quick one-liner about this dish…")
        self._desc_input.setFixedHeight(44)
        self._desc_input.setStyleSheet(_inp_style)
        bc.addWidget(self._desc_input)

        # Times row
        times_lbl = QLabel("Time & servings")
        times_lbl.setStyleSheet(_lbl_style)
        bc.addWidget(times_lbl)

        times_row = QHBoxLayout()
        times_row.setSpacing(12)
        for attr, label, ph, icon_n, ic_col in [
            ("_prep_input",  "Prep  (min)", "15", "fa5s.clock",        "#888"),
            ("_cook_input",  "Cook  (min)", "30", "fa5s.fire",         "#ff6b35"),
            ("_serve_input", "Serves",      "4",  "fa5s.user-friends", "#4fc3f7"),
        ]:
            col_w = QWidget()
            col_w.setStyleSheet("background: transparent;")
            col_l = QVBoxLayout(col_w)
            col_l.setContentsMargins(0, 0, 0, 0)
            col_l.setSpacing(6)
            col_hdr = QHBoxLayout()
            col_hdr.setSpacing(5)
            ic_l = QLabel()
            ic_l.setPixmap(qta.icon(icon_n, color=ic_col).pixmap(QSize(11, 11)))
            ic_l.setStyleSheet("background: transparent;")
            lbl_l = QLabel(label)
            lbl_l.setStyleSheet(
                f"color: {_muted}; font-size: 11px; font-weight: 600; background: transparent;"
            )
            col_hdr.addWidget(ic_l)
            col_hdr.addWidget(lbl_l)
            col_hdr.addStretch()
            col_l.addLayout(col_hdr)
            inp = QLineEdit()
            inp.setPlaceholderText(ph)
            inp.setFixedHeight(48)
            inp.setFixedWidth(110)
            inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inp.setStyleSheet(_inp_style)
            setattr(self, attr, inp)
            col_l.addWidget(inp)
            times_row.addWidget(col_w)
        times_row.addStretch()
        bc.addLayout(times_row)

        left.addWidget(basics_card)

        # ── Ingredients card ──────────────────────────────────────────────
        ing_card = QWidget()
        ing_card.setObjectName("plan-card")
        ic_l = QVBoxLayout(ing_card)
        ic_l.setContentsMargins(24, 22, 24, 24)
        ic_l.setSpacing(12)

        ic_l.addLayout(_card_section_header("fa5s.leaf", "INGREDIENTS", "#34d399"))

        ing_hint = QLabel("Type an ingredient name and press ↵ — Dishy looks up the macros for you")
        ing_hint.setWordWrap(True)
        ing_hint.setStyleSheet(f"color: {_muted}; font-size: 13px; background: transparent;")
        self._ing_hint = ing_hint
        ic_l.addWidget(ing_hint)

        self._ingredients = NutritionIngredientList(
            servings_getter=lambda: self._serve_input.text()
        )
        ic_l.addWidget(self._ingredients)

        left.addWidget(ing_card)

        # ── Instructions card ─────────────────────────────────────────────
        inst_card = QWidget()
        inst_card.setObjectName("plan-card")
        inst_l = QVBoxLayout(inst_card)
        inst_l.setContentsMargins(24, 22, 24, 24)
        inst_l.setSpacing(12)

        inst_l.addLayout(_card_section_header("fa5s.list-ol", "INSTRUCTIONS", "#60a5fa"))

        inst_hint = QLabel("Add each step in order — press ↵ after each step to continue")
        inst_hint.setStyleSheet(f"color: {_muted}; font-size: 13px; background: transparent;")
        self._inst_hint = inst_hint
        inst_l.addWidget(inst_hint)

        self._instructions = _DynamicList("Describe this step…")
        inst_l.addWidget(self._instructions)

        left.addWidget(inst_card)

        # ── RIGHT column ─────────────────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(16)
        right.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── Photo card ────────────────────────────────────────────────────
        photo_card = QWidget()
        photo_card.setObjectName("plan-card")
        pc_l = QVBoxLayout(photo_card)
        pc_l.setContentsMargins(20, 20, 20, 20)
        pc_l.setSpacing(12)

        pc_l.addLayout(_card_section_header("fa5s.image", "PHOTO", "#a78bfa"))

        self._photo_path: str = ""
        self._photo_preview = QLabel()
        self._photo_preview.setFixedHeight(180)
        self._photo_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._photo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._photo_preview.setText("No photo selected")
        self._photo_preview.setStyleSheet(
            f"background: {_input_bg};"
            f" border: 1.5px dashed {theme_manager.c('#2a2a2a', '#d5d5d5')};"
            " border-radius: 10px;"
            f" color: {_muted}; font-size: 13px;"
        )
        pc_l.addWidget(self._photo_preview)

        photo_btn_row = QHBoxLayout()
        photo_btn_row.setSpacing(8)
        pick_photo_btn = QPushButton("  Choose Photo")
        pick_photo_btn.setObjectName("ghost-btn")
        pick_photo_btn.setIcon(qta.icon("fa5s.folder-open", color="#888888"))
        pick_photo_btn.setIconSize(QSize(13, 13))
        pick_photo_btn.setFixedHeight(38)
        pick_photo_btn.clicked.connect(self._pick_photo)
        clear_photo_btn = QPushButton("Remove")
        clear_photo_btn.setObjectName("ghost-btn")
        clear_photo_btn.setFixedHeight(38)
        clear_photo_btn.clicked.connect(self._clear_photo)
        photo_btn_row.addWidget(pick_photo_btn, 1)
        photo_btn_row.addWidget(clear_photo_btn)
        pc_l.addLayout(photo_btn_row)

        right.addWidget(photo_card)

        # ── Tags card ─────────────────────────────────────────────────────
        tags_card = QWidget()
        tags_card.setObjectName("plan-card")
        tc_l = QVBoxLayout(tags_card)
        tc_l.setContentsMargins(20, 20, 20, 20)
        tc_l.setSpacing(12)

        tc_l.addLayout(_card_section_header("fa5s.tags", "TAGS", "#f472b6"))

        self._tag_picker = _TagPicker()
        tc_l.addWidget(self._tag_picker)

        right.addWidget(tags_card)

        # ── Appearance card (collapsible) ─────────────────────────────────
        self._appearance_card = _CollapsibleCard(
            title="Appearance",
            icon_name="fa5s.palette",
            colour="#a78bfa",
        )
        self._icon_picker   = _IconPicker()
        self._colour_picker = _ColourPicker()
        ap = self._appearance_card.body()
        icon_lbl = QLabel("Icon")
        icon_lbl.setStyleSheet(_lbl_style)
        ap.addWidget(icon_lbl)
        ap.addWidget(self._icon_picker)
        ap.addSpacing(6)
        colour_lbl = QLabel("Colour")
        colour_lbl.setStyleSheet(_lbl_style)
        ap.addWidget(colour_lbl)
        ap.addWidget(self._colour_picker)

        right.addWidget(self._appearance_card)
        right.addStretch()

        cols.addLayout(left, 58)
        cols.addLayout(right, 42)
        layout.addLayout(cols)
        layout.addSpacing(28)

        # ── Save bar ──────────────────────────────────────────────────────
        sb_l = QHBoxLayout()
        sb_l.setContentsMargins(0, 0, 0, 0)
        sb_l.setSpacing(10)

        self._save_btn_ref = QPushButton("  Save Recipe")
        self._save_btn_ref.setObjectName("ghost-btn")
        self._save_btn_ref.setIcon(qta.icon("fa5s.save", color=theme_manager.c("#888888", "#555555")))
        self._save_btn_ref.setIconSize(QSize(13, 13))
        self._save_btn_ref.setFixedHeight(40)
        self._save_btn_ref.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn_ref.clicked.connect(self._save)

        fav_hint = QLabel()
        fav_hint.setStyleSheet(f"color: {_muted}; font-size: 13px; background: transparent;")
        self._fav_hint_lbl = fav_hint
        self._fav_btn.toggled.connect(lambda on: fav_hint.setText(
            "★  Will be saved as a favourite" if on else ""
        ))

        sb_l.addWidget(self._save_btn_ref)
        sb_l.addWidget(fav_hint)
        sb_l.addStretch()

        layout.addLayout(sb_l)
        self.setWidget(container)

    def apply_theme(self, mode: str = "dark"):
        text_fg   = theme_manager.c("#e8e8e8", "#1a1a1a")
        muted     = theme_manager.c("#555555", "#888888")
        input_bg  = theme_manager.c("#0d0d0d", "#fafafa")
        input_bdr = theme_manager.c("#222222", "#e0e0e0")

        # Heading and sub-labels
        self._heading_lbl.setStyleSheet(
            f"color: {theme_manager.c('#f0f0f0', '#0a0a0a')};"
            " font-size: 28px; font-weight: 700; letter-spacing: -0.5px; background: transparent;"
        )
        _muted_style = f"color: {muted}; font-size: 13px; background: transparent;"
        self._sub_lbl.setStyleSheet(f"color: {muted}; font-size: 14px; background: transparent;")
        self._ing_hint.setStyleSheet(_muted_style)
        self._inst_hint.setStyleSheet(_muted_style)
        self._fav_hint_lbl.setStyleSheet(f"color: {muted}; font-size: 13px; background: transparent;")

        # Fav star icon
        star_color = "#fbbf24" if self._fav_btn.isChecked() else theme_manager.c("#666666", "#999999")
        self._fav_btn.setIcon(qta.icon("fa5s.star", color=star_color))

        # Input fields
        _inp_style = (
            "QLineEdit {"
            f" background: {input_bg}; color: {text_fg};"
            f" border: 1.5px solid {input_bdr}; border-radius: 10px; font-size: 15px;"
            " padding: 6px 12px;"
            "}"
            "QLineEdit:focus { border-color: #ff6b35; }"
        )
        self._title_input.setStyleSheet(
            "QLineEdit {"
            f" background: {input_bg}; color: {text_fg};"
            f" border: 1.5px solid {input_bdr}; border-radius: 10px;"
            " font-size: 17px; font-weight: 500;"
            "}"
            "QLineEdit:focus { border-color: #ff6b35; }"
        )
        for inp in [self._desc_input, self._prep_input, self._cook_input, self._serve_input]:
            inp.setStyleSheet(_inp_style)

        # Photo preview
        self._photo_preview.setStyleSheet(
            f"background: {input_bg};"
            f" border: 1.5px dashed {theme_manager.c('#2a2a2a', '#d5d5d5')};"
            " border-radius: 10px;"
            f" color: {muted}; font-size: 13px;"
        )

        # Sub-widgets
        self._tag_picker.apply_theme(mode)
        self._icon_picker.apply_theme(mode)
        self._colour_picker.apply_theme(mode)
        self._instructions.apply_theme(mode)

    def load_for_edit(self, data: dict, edit_id: int):
        """Pre-populate all fields for editing an existing recipe."""
        self._edit_id = edit_id
        self._heading_lbl.setText("Edit Recipe")
        self._save_btn_ref.setText("  Save Changes")
        self._title_input.setText(data.get("title", ""))
        self._desc_input.setText(data.get("description", ""))
        self._prep_input.setText(str(data.get("prep_time", "") or ""))
        self._cook_input.setText(str(data.get("cook_time", "") or ""))
        self._serve_input.setText(str(data.get("servings", "") or ""))
        self._icon_picker.set_value(data.get("icon", "fa5s.utensils"))
        self._colour_picker.set_value(data.get("colour", "#ff6b35"))
        self._tag_picker.set_values(data.get("tags", []))
        self._instructions.set_values(data.get("instructions", []))
        self._ingredients.set_values(data.get("ingredients", []))
        photo = data.get("photo_path", "")
        self._photo_path = photo
        if photo:
            self._show_photo_preview(photo)
        else:
            self._clear_photo()

    def reset_for_create(self):
        """Reset form back to blank create mode."""
        self._edit_id = None
        self._heading_lbl.setText("Create Your Own Recipe")
        self._save_btn_ref.setText("  Save Recipe")
        self._title_input.clear()
        self._desc_input.clear()
        self._prep_input.clear()
        self._cook_input.clear()
        self._serve_input.clear()
        self._icon_picker.set_value("fa5s.utensils")
        self._colour_picker.set_value("#ff6b35")
        self._tag_picker.set_values([])
        self._instructions.set_values([])
        self._ingredients.set_values([])
        self._fav_btn.setChecked(False)
        self._clear_photo()

    def _pick_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a photo", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
        )
        if path:
            self._photo_path = path
            self._show_photo_preview(path)

    def _clear_photo(self):
        self._photo_path = ""
        self._photo_preview.setPixmap(QPixmap())
        self._photo_preview.setText("No photo")

    def _show_photo_preview(self, path: str):
        px = QPixmap(path)
        if not px.isNull():
            px = px.scaled(
                240, 160,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Centre-crop to 240×160
            if px.width() > 240 or px.height() > 160:
                x = (px.width() - 240) // 2
                y = (px.height() - 160) // 2
                px = px.copy(x, y, 240, 160)
            self._photo_preview.setText("")
            self._photo_preview.setPixmap(px)

    def _save(self):
        title = self._title_input.text().strip()
        if not title:
            self._title_input.setPlaceholderText("← Please enter a title")
            return

        # Duplicate detection — exclude self when editing
        if self._edit_id is not None:
            existing = self._db.conn.execute(
                "SELECT id FROM recipes WHERE LOWER(title)=LOWER(?) AND id!=?",
                (title, self._edit_id)
            ).fetchone()
        else:
            existing = self._db.conn.execute(
                "SELECT id FROM recipes WHERE LOWER(title)=LOWER(?)", (title,)
            ).fetchone()
        if existing:
            msg = QMessageBox(self)
            msg.setWindowTitle("Recipe already exists")
            msg.setText(
                f'A recipe called "{title}" is already saved.\n\n'
                "What would you like to do?"
            )
            msg.setIcon(QMessageBox.Icon.Question)
            save_anyway = msg.addButton("Save anyway", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if msg.clickedButton() is not save_anyway:
                return

        prep  = int(self._prep_input.text() or 0)
        cook  = int(self._cook_input.text() or 0)
        data = {
            "title":        title,
            "description":  self._desc_input.text().strip(),
            "ingredients":  self._ingredients.values(),
            "instructions": self._instructions.values(),
            "prep_time":    prep,
            "cook_time":    cook,
            "total_time":   prep + cook,
            "servings":     self._serve_input.text().strip() or "4",
            "icon":         self._icon_picker.value(),
            "colour":       self._colour_picker.value(),
            "tags":         self._tag_picker.values(),
            "source":       "user_created",
        }
        if self._photo_path:
            data["photo_path"] = self._photo_path

        # Add nutrition data if available
        nutr = self._ingredients.nutrition_data()
        if nutr["ingredients"]:
            data["nutrition_ingredients"] = nutr["ingredients"]
            data["nutrition_total"]       = nutr["total"]
            data["nutrition_per_serving"] = nutr["per_serving"]

        if self._edit_id is not None:
            # Update existing recipe
            self._db.conn.execute(
                "UPDATE recipes SET title=?, ready_mins=?, data_json=? WHERE id=?",
                (title, prep + cook, json.dumps(data), self._edit_id),
            )
            self._db.conn.commit()
            recipe_id = self._edit_id
            self._edit_id = None
            self._heading_lbl.setText("Create Your Own Recipe")
            self._save_btn_ref.setText("  Save Recipe")
        else:
            recipe_id = self._db.save_recipe(
                source_id="",
                source="user_created",
                title=title,
                ready_mins=prep + cook,
                servings=int(self._serve_input.text() or 0),
                data_json=json.dumps(data),
            )
            if self._fav_btn.isChecked():
                self._db.toggle_favourite(recipe_id, True)
        self._on_saved(recipe_id, data)


# ── Main recipes view ─────────────────────────────────────────────────────────

class RecipesView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("view-container")
        self._db = Database()
        self._db.connect()
        self._current_recipe: dict | None = None
        self._current_recipe_db_id: int | None = None
        self._current_recipe_is_fav: bool = False
        self._ask_dishy_fn = None        # set by MainWindow via set_ask_dishy()
        self._nutrition_refresh_fn = None # set by MainWindow via set_nutrition_refresh()
        self._sync_fn = None              # set by MainWindow to trigger cloud sync
        self._claude = ClaudeAI()
        self._build_ui()

    def set_nutrition_refresh(self, fn):
        self._nutrition_refresh_fn = fn

    def set_ask_dishy(self, fn):
        """Called by MainWindow to wire the per-tab Ask Dishy button."""
        self._ask_dishy_fn = fn

    def set_sync_fn(self, fn):
        """Called by MainWindow to trigger cloud sync after recipe saves/deletes."""
        self._sync_fn = fn

    def _trigger_image_upload(self, recipe_id: int, image_url: str) -> None:
        """Fire-and-forget: upload image to Supabase Storage, update DB on success."""
        from utils.image_upload import is_supabase_url, upload_recipe_image
        from auth.supabase_client import get_client, is_online
        if not image_url or is_supabase_url(image_url) or not is_online():
            return
        client = get_client()
        if not client:
            return
        try:
            session = client.auth.get_session()
            user_id = session.session.user.id
        except Exception:
            return

        def _upload():
            return upload_recipe_image(client, str(user_id), recipe_id, image_url)

        def _done(cdn_url):
            if cdn_url:
                try:
                    self._db.conn.execute(
                        "UPDATE recipes SET image_url=? WHERE id=?", (cdn_url, recipe_id)
                    )
                    self._db.conn.commit()
                except Exception:
                    pass

        run_async(_upload, _done)

    def refresh(self):
        """Reload saved recipes — called after Dishy saves a recipe."""
        self._load_saved_recipes()

    def open_by_id(self, recipe_id: int):
        """Navigate directly to a saved recipe's detail view by DB id."""
        try:
            rd = self._db.conn.execute(
                "SELECT * FROM recipes WHERE id=?", (recipe_id,)
            ).fetchone()
            if not rd:
                return
            data = json.loads(rd["data_json"] or "{}")
            data.setdefault("title", rd["title"] or "")
            self._current_recipe = data
            self._current_recipe_db_id = rd["id"]
            self._current_recipe_is_fav = bool(rd["is_favourite"])
            self._came_from_search = False
            is_fav = bool(rd["is_favourite"])
        except Exception:
            return
        # Populate and switch — setCurrentIndex(2) always runs even if populate throws
        try:
            self._populate_detail(data, db_id=rd["id"], is_fav=is_fav)
        except Exception:
            pass
        self._stack.setCurrentIndex(2)

    def apply_theme(self, mode: str = "dark"):
        """Called by MainWindow when the user toggles the colour theme."""
        # Re-apply inline styles (not covered by global QSS)
        self._local_search.setStyleSheet(
            f"QLineEdit {{ background: {theme_manager.c('#111111', '#ffffff')};"
            f" color: {theme_manager.c('#e8e8e8', '#1a1a1a')};"
            f" border: 1px solid {theme_manager.c('#222222', '#e0e0e0')};"
            " border-radius: 6px; padding: 0 10px; font-size: 13px; }"
            f"QLineEdit:focus {{ border-color: #7c6af7; }}"
        )
        self._search_input.setStyleSheet(
            f"QLineEdit {{ background: {theme_manager.c('#111111', '#ffffff')};"
            f" color: {theme_manager.c('#e8e8e8', '#1a1a1a')};"
            f" border: 1px solid {theme_manager.c('#222222', '#e0e0e0')};"
            " border-radius: 9px; padding: 0 14px; font-size: 14px; min-height: 0; }"
            "QLineEdit:focus { border-color: #7c6af7; }"
        )
        self._load_saved_recipes()          # rebuilds RecipeCard widgets with fresh theme colours
        self._create_page.apply_theme(mode) # update create-form inline styles

    def _build_ui(self):
        self.setMinimumHeight(480)  # prevents the view from collapsing at small window heights
        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 36, 36, 10)
        outer.setSpacing(18)

        # Header
        title = QLabel("Recipes")
        title.setObjectName("page-title")
        subtitle = QLabel("Search the web, browse your saved recipes, or create your own")
        subtitle.setObjectName("page-date")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        # Action row
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "e.g. 'chicken tikka masala', 'easy pasta bake'…"
        )
        self._search_input.setFixedHeight(42)
        self._search_input.setStyleSheet(
            f"QLineEdit {{ background: {theme_manager.c('#111111', '#ffffff')};"
            f" color: {theme_manager.c('#e8e8e8', '#1a1a1a')};"
            f" border: 1px solid {theme_manager.c('#222222', '#e0e0e0')};"
            " border-radius: 9px; padding: 0 14px; font-size: 14px; min-height: 0; }"
            "QLineEdit:focus { border-color: #7c6af7; }"
        )
        self._search_input.returnPressed.connect(self._search)

        search_btn = PrimaryButton("Search")
        search_btn.setFixedHeight(42)
        search_btn.clicked.connect(self._search)

        create_btn = QPushButton("  Create Recipe")
        create_btn.setObjectName("ghost-btn")
        create_btn.setIcon(qta.icon("fa5s.plus", color="#888888"))
        create_btn.setIconSize(QSize(12, 12))
        create_btn.setFixedHeight(42)
        create_btn.clicked.connect(self._start_create)

        saved_btn = QPushButton("  Saved")
        saved_btn.setObjectName("ghost-btn")
        saved_btn.setIcon(qta.icon("fa5s.bookmark", color=theme_manager.c("#888888", "#555555")))
        saved_btn.setIconSize(QSize(12, 12))
        saved_btn.setFixedHeight(42)
        saved_btn.clicked.connect(self._show_saved)

        self._ask_dishy_btn = QPushButton("  Ask Dishy")
        self._ask_dishy_btn.setObjectName("ghost-btn")
        self._ask_dishy_btn.setIcon(qta.icon("fa5s.robot", color="#34d399"))
        self._ask_dishy_btn.setIconSize(QSize(12, 12))
        self._ask_dishy_btn.setFixedHeight(42)
        self._ask_dishy_btn.setToolTip("Ask Dishy to create and save a recipe for you")
        self._ask_dishy_btn.clicked.connect(self._ask_dishy_for_recipe)

        action_row.addWidget(self._search_input)
        action_row.addWidget(search_btn)
        action_row.addWidget(create_btn)
        action_row.addWidget(saved_btn)
        action_row.addWidget(self._ask_dishy_btn)
        outer.addLayout(action_row)

        # Status
        self._status = QLabel("")
        self._status.setObjectName("card-body")
        outer.addWidget(self._status)

        # Stack: 0=saved home, 1=search results, 2=detail, 3=create
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_saved_page())    # 0
        self._stack.addWidget(self._build_results_page())  # 1
        self._stack.addWidget(self._build_detail_page())   # 2
        self._stack.addWidget(self._build_create_page())   # 3
        outer.addWidget(self._stack, 1)

        self._load_saved_recipes()

    # ── pages ────────────────────────────────────────────────────────────────

    def _build_saved_page(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(8)

        # ── Local recipe search ───────────────────────────────────────────────
        local_row = QHBoxLayout()
        local_row.setSpacing(8)
        local_row.setContentsMargins(0, 0, 0, 0)

        search_ic = QLabel()
        search_ic.setPixmap(qta.icon("fa5s.search", color=theme_manager.c("#555555", "#888888")).pixmap(QSize(13, 13)))
        search_ic.setStyleSheet("background: transparent;")

        self._local_search = QLineEdit()
        self._local_search.setPlaceholderText("Search saved recipes…")
        self._local_search.setClearButtonEnabled(True)
        self._local_search.setFixedHeight(32)
        self._local_search.setStyleSheet(
            f"QLineEdit {{ background: {theme_manager.c('#111111', '#ffffff')};"
            f" color: {theme_manager.c('#e8e8e8', '#1a1a1a')};"
            f" border: 1px solid {theme_manager.c('#222222', '#e0e0e0')};"
            " border-radius: 6px; padding: 0 10px; font-size: 13px; }"
            "QLineEdit:focus { border-color: #7c6af7; }"
        )
        self._local_search.textChanged.connect(self._load_saved_recipes)

        local_row.addWidget(search_ic)
        local_row.addWidget(self._local_search, 1)
        wl.addLayout(local_row)

        # ── Tag filter bar ────────────────────────────────────────────────────
        self._active_tag: str | None = None
        tag_scroll = QScrollArea()
        tag_scroll.setFixedHeight(40)
        tag_scroll.setWidgetResizable(True)
        tag_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tag_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tag_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._tag_bar_inner = QWidget()
        self._tag_bar_inner.setStyleSheet("background: transparent;")
        self._tag_bar_layout = QHBoxLayout(self._tag_bar_inner)
        self._tag_bar_layout.setContentsMargins(0, 0, 0, 0)
        self._tag_bar_layout.setSpacing(6)
        self._tag_bar_layout.addStretch()
        tag_scroll.setWidget(self._tag_bar_inner)
        self._tag_scroll = tag_scroll
        wl.addWidget(tag_scroll)

        # ── Recipe card grid ──────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._saved_container = QWidget()
        self._saved_container.setStyleSheet("background: transparent;")

        outer_vl = QVBoxLayout(self._saved_container)
        outer_vl.setContentsMargins(0, 4, 0, 20)
        outer_vl.setSpacing(0)

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._saved_layout = QGridLayout(self._grid_widget)
        self._saved_layout.setContentsMargins(0, 0, 4, 0)
        self._saved_layout.setSpacing(14)
        for col in range(RecipeCard._GRID_COLS):
            self._saved_layout.setColumnStretch(col, 1)

        outer_vl.addWidget(self._grid_widget)
        outer_vl.addStretch()

        scroll.setWidget(self._saved_container)
        wl.addWidget(scroll, 1)
        return wrapper

    def _build_results_page(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(10)

        # Header row: back button + result count label
        hdr = QHBoxLayout()
        back_btn = QPushButton("← Back to Saved")
        back_btn.setObjectName("ghost-btn")
        back_btn.setFixedHeight(34)
        back_btn.setFixedWidth(150)
        back_btn.clicked.connect(self._show_saved)
        self._result_count_lbl = QLabel("")
        self._result_count_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#555555', '#999999')};"
            " font-size: 12px;"
        )
        hdr.addWidget(back_btn)
        hdr.addStretch()
        hdr.addWidget(self._result_count_lbl)
        wl.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._results_container = QWidget()
        self._results_container.setStyleSheet("background: transparent;")
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setContentsMargins(0, 0, 8, 0)
        self._results_layout.setSpacing(8)
        self._results_layout.addStretch()
        scroll.setWidget(self._results_container)
        wl.addWidget(scroll, 1)
        return wrapper

    def _build_detail_page(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 12, 36)
        layout.setSpacing(20)

        back_btn = QPushButton("← Back")
        back_btn.setObjectName("ghost-btn")
        back_btn.setFixedHeight(34)
        back_btn.setFixedWidth(120)
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(
            1 if self._came_from_search else 0
        ))
        layout.addWidget(back_btn)

        self._detail_card = QWidget()
        self._detail_card.setObjectName("plan-card")
        self._detail_layout = QVBoxLayout(self._detail_card)
        self._detail_layout.setContentsMargins(28, 24, 28, 28)
        self._detail_layout.setSpacing(18)
        layout.addWidget(self._detail_card)
        layout.addStretch()

        scroll.setWidget(container)
        self._came_from_search = False
        return scroll

    def _build_create_page(self) -> CreateRecipePage:
        self._create_page = CreateRecipePage(
            db=self._db,
            on_saved=self._on_recipe_created,
            on_cancel=self._on_create_cancel,
        )
        return self._create_page

    def _on_create_cancel(self):
        self._create_page.reset_for_create()
        self._stack.setCurrentIndex(0)

    # ── saved recipes ─────────────────────────────────────────────────────────

    def _load_saved_recipes(self):
        while self._saved_layout.count():
            item = self._saved_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            all_recipes = self._db.get_saved_recipes()
        except Exception:
            all_recipes = []

        # ── Rebuild tag filter bar ────────────────────────────────────────────
        # Meal-type chips always pinned; Online/Dishy shown only if any recipe has them
        _MEAL_CHIPS = ["Breakfast", "Lunch", "Dinner", "Snack", "Dessert"]
        _SPECIAL_ORDER = ["Online", "Dishy"]
        recipes_tags_flat: set[str] = set()
        for r in all_recipes:
            try:
                tags = json.loads(r["data_json"] or "{}").get("tags", [])
                recipes_tags_flat.update(tags)
            except Exception:
                pass
        extra_tags = [t for t in _SPECIAL_ORDER if t in recipes_tags_flat]

        # Clear old chips (keep the trailing stretch)
        while self._tag_bar_layout.count() > 1:
            item = self._tag_bar_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._tag_scroll.setFixedHeight(40)
        all_chip = QPushButton("All")
        all_chip.setCheckable(True)
        all_chip.setChecked(self._active_tag is None)
        all_chip.setFixedHeight(28)
        all_chip.setStyleSheet(self._tag_chip_style(self._active_tag is None))
        all_chip.clicked.connect(lambda: self._set_tag_filter(None))
        self._tag_bar_layout.insertWidget(0, all_chip)
        _MEAL_SET = set(_MEAL_CHIPS)
        for idx, tag in enumerate(_MEAL_CHIPS + extra_tags, 1):
            active    = self._active_tag == tag
            is_meal   = tag in _MEAL_SET
            is_dishy  = tag == "Dishy"
            is_online = tag == "Online"
            chip = QPushButton(f"  {tag}" if (is_dishy or is_online) else tag)
            chip.setCheckable(True)
            chip.setChecked(active)
            chip.setFixedHeight(28)
            if is_dishy:
                chip.setIcon(qta.icon("fa5s.robot", color="#34d399"))
                chip.setIconSize(QSize(11, 11))
                chip.setStyleSheet(self._dishy_chip_style(active))
            elif is_online:
                chip.setIcon(qta.icon("fa5s.globe", color="#4fc3f7"))
                chip.setIconSize(QSize(11, 11))
                chip.setStyleSheet(self._online_chip_style(active))
            elif is_meal:
                chip.setStyleSheet(self._meal_chip_style(active))
            else:
                chip.setStyleSheet(self._tag_chip_style(active))
            chip.clicked.connect(lambda _, t=tag: self._set_tag_filter(t))
            self._tag_bar_layout.insertWidget(idx, chip)

        # Visual separator between meal chips and other tags
        if extra_tags:
            sep = QWidget()
            sep.setFixedSize(1, 20)
            sep.setStyleSheet(f"background: {theme_manager.c('#282828', '#cccccc')};")
            self._tag_bar_layout.insertWidget(len(_MEAL_CHIPS) + 1, sep)

        # ── Filter by tag ─────────────────────────────────────────────────────
        if self._active_tag:
            active = self._active_tag
            recipes = []
            for r in all_recipes:
                try:
                    tags = json.loads(r["data_json"] or "{}").get("tags", [])
                    if active in tags:
                        recipes.append(r)
                except Exception:
                    pass
        else:
            recipes = list(all_recipes)

        # ── Filter by local search text ───────────────────────────────────────
        local_q = self._local_search.text().strip().lower()
        if local_q:
            filtered = []
            for r in recipes:
                if local_q in r["title"].lower():
                    filtered.append(r)
                    continue
                try:
                    data = json.loads(r["data_json"] or "{}")
                    haystack = " ".join([
                        " ".join(data.get("tags", [])),
                        data.get("description", ""),
                        " ".join(data.get("ingredients", [])),
                    ]).lower()
                    if local_q in haystack:
                        filtered.append(r)
                except Exception:
                    pass
            recipes = filtered

        if not recipes:
            if local_q:
                msg = f"No recipes match \"{local_q}\""
            elif self._active_tag:
                msg = "No recipes match that tag."
            else:
                msg = "No saved recipes yet.\nSearch the web or create your own!"
            ph = QLabel(msg)
            ph.setObjectName("placeholder-text")
            ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._saved_layout.addWidget(ph, 0, 0, 1, RecipeCard._GRID_COLS)
            self._status.setText("")
            return

        total = len(all_recipes)
        shown = len(recipes)
        if local_q:
            suffix = f" ({shown} match{'es' if shown != 1 else ''})"
        elif self._active_tag and shown != total:
            suffix = f" ({shown} shown)"
        else:
            suffix = ""
        self._status.setText(f"{total} saved recipe{'s' if total != 1 else ''}{suffix}")

        COLS = RecipeCard._GRID_COLS
        for idx, r in enumerate(recipes):
            rec_dict = dict(r)
            recipe_id = rec_dict["id"]

            def _make_select(rd=rec_dict):
                def _open():
                    data = {}
                    try:
                        data = json.loads(rd.get("data_json") or "{}")
                    except Exception:
                        pass
                    data.setdefault("title", rd.get("title", ""))
                    self._current_recipe = data
                    self._current_recipe_db_id = rd["id"]
                    self._current_recipe_is_fav = bool(rd.get("is_favourite", 0))
                    self._came_from_search = False
                    self._populate_detail(data, db_id=rd["id"],
                                          is_fav=bool(rd.get("is_favourite", 0)))
                    self._stack.setCurrentIndex(2)
                return _open

            def _make_delete(rid=recipe_id, rname=rec_dict.get("title", "this recipe")):
                def _del():
                    msg = QMessageBox(self)
                    msg.setWindowTitle("Delete Recipe")
                    msg.setText(f"Delete \"{rname[:50]}\"?")
                    msg.setInformativeText("This cannot be undone.")
                    msg.setIcon(QMessageBox.Icon.Warning)
                    msg.setStandardButtons(
                        QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok
                    )
                    msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
                    msg.button(QMessageBox.StandardButton.Ok).setText("Delete")
                    if msg.exec() == QMessageBox.StandardButton.Ok:
                        self._db.delete_recipe(rid)
                        self._load_saved_recipes()
                        if self._sync_fn:
                            self._sync_fn()
                return _del

            card = RecipeCard(rec_dict, on_select=_make_select(), on_delete=_make_delete())
            self._saved_layout.addWidget(card, idx // COLS, idx % COLS)

    def _tag_chip_style(self, active: bool) -> str:
        if active:
            return (
                "QPushButton { background-color: rgba(255,107,53,0.15); color: #ff6b35;"
                " border-radius: 6px; border: 1px solid rgba(255,107,53,0.4);"
                " font-size: 11px; font-weight: 600; padding: 0 12px; }"
            )
        bg     = theme_manager.c("#141414", "#f0f0f0")
        fg     = theme_manager.c("#666666", "#555555")
        border = theme_manager.c("#1e1e1e", "#cccccc")
        hover  = theme_manager.c("#1e1e1e", "#e4e4e4")
        return (
            f"QPushButton {{ background-color: {bg}; color: {fg};"
            f" border-radius: 6px; border: 1px solid {border};"
            " font-size: 11px; font-weight: 500; padding: 0 12px; }"
            f"QPushButton:hover {{ background-color: {hover}; border-color: rgba(255,107,53,0.3); }}"
        )

    def _meal_chip_style(self, active: bool) -> str:
        """Style for meal-type chips (Breakfast/Lunch/Dinner/Snack/Dessert) — teal accent."""
        if active:
            return (
                "QPushButton { background-color: rgba(76,175,138,0.18); color: #4caf8a;"
                " border-radius: 6px; border: 1px solid rgba(76,175,138,0.5);"
                " font-size: 11px; font-weight: 700; padding: 0 12px; }"
            )
        bg     = theme_manager.c("#0f1a16", "#f0faf5")
        fg     = "#4caf8a"
        border = theme_manager.c("rgba(76,175,138,0.25)", "rgba(76,175,138,0.35)")
        return (
            f"QPushButton {{ background-color: {bg}; color: {fg};"
            f" border-radius: 6px; border: 1px solid {border};"
            " font-size: 11px; font-weight: 600; padding: 0 12px; }"
            "QPushButton:hover { background-color: rgba(76,175,138,0.12); }"
        )

    def _online_chip_style(self, active: bool) -> str:
        """Style for the Online tag chip — sky blue accent."""
        if active:
            return (
                "QPushButton { background-color: rgba(79,195,247,0.2); color: #4fc3f7;"
                " border-radius: 6px; border: 1px solid rgba(79,195,247,0.6);"
                " font-size: 11px; font-weight: 700; padding: 0 10px; }"
            )
        bg     = theme_manager.c("#071b24", "#eaf7fd")
        border = theme_manager.c("rgba(79,195,247,0.3)", "rgba(79,195,247,0.4)")
        return (
            f"QPushButton {{ background-color: {bg}; color: #4fc3f7;"
            f" border-radius: 6px; border: 1px solid {border};"
            " font-size: 11px; font-weight: 600; padding: 0 10px; }"
            "QPushButton:hover { background-color: rgba(79,195,247,0.12); }"
        )

    def _dishy_chip_style(self, active: bool) -> str:
        """Style for the Dishy AI tag chip — Dishy green accent."""
        if active:
            return (
                "QPushButton { background-color: rgba(52,211,153,0.2); color: #34d399;"
                " border-radius: 6px; border: 1px solid rgba(52,211,153,0.6);"
                " font-size: 11px; font-weight: 700; padding: 0 10px; }"
            )
        bg     = theme_manager.c("#0a1f17", "#edfaf4")
        border = theme_manager.c("rgba(52,211,153,0.3)", "rgba(52,211,153,0.4)")
        return (
            f"QPushButton {{ background-color: {bg}; color: #34d399;"
            f" border-radius: 6px; border: 1px solid {border};"
            " font-size: 11px; font-weight: 600; padding: 0 10px; }"
            "QPushButton:hover { background-color: rgba(52,211,153,0.12); }"
        )

    def _set_tag_filter(self, tag: str | None):
        self._active_tag = tag
        self._load_saved_recipes()

    def _start_create(self):
        self._create_page.reset_for_create()
        self._stack.setCurrentIndex(3)

    def _show_saved(self):
        self._load_saved_recipes()
        self._stack.setCurrentIndex(0)

    def _ask_dishy_for_recipe(self):
        if self._ask_dishy_fn:
            self._ask_dishy_fn(
                "Create a recipe for me and save it to my library. "
                "Ask me what kind of recipe I want first — what cuisine, dietary needs, or occasion."
            )

    def showEvent(self, event):
        super().showEvent(event)
        self._load_saved_recipes()

    # ── search ────────────────────────────────────────────────────────────────

    def _search(self):
        query = self._search_input.text().strip()
        if not query:
            return
        self._status.setText("Searching…")
        self._clear_results()
        self._stack.setCurrentIndex(1)
        run_async(
            _google.search_recipes, query,
            on_result=self._on_results,
            on_error=self._on_search_error,
        )

    def _on_results(self, results: list):
        self._clear_results()
        if not results:
            self._status.setText("No results found — try a different search")
            self._stack.setCurrentIndex(0)
            return
        self._stack.setCurrentIndex(1)
        n = len(results)
        self._status.setText(f"{n} recipe{'s' if n != 1 else ''} found — click one to load")
        self._result_count_lbl.setText(f"{n} results")
        for r in results:
            card = SearchResultRow(r, on_select=self._scrape_recipe)
            self._results_layout.insertWidget(self._results_layout.count() - 1, card)

    def _on_search_error(self, _err: str):
        self._status.setText("Search failed — check your connection")
        self._stack.setCurrentIndex(0)

    def _clear_results(self):
        self._result_count_lbl.setText("")
        while self._results_layout.count() > 1:
            item = self._results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ── scrape ────────────────────────────────────────────────────────────────

    def _scrape_recipe(self, result: dict):
        host = urlparse(result.get("url", "")).netloc.replace("www.", "")
        self._status.setText(f"Loading recipe from {host}…")
        run_async(
            scrape_recipe, result["url"],
            on_result=self._on_scraped,
            on_error=self._on_scrape_error,
        )

    def _on_scraped(self, recipe: dict):
        self._current_recipe = recipe
        self._current_recipe_db_id = None
        self._current_recipe_is_fav = False
        self._came_from_search = True
        self._populate_detail(recipe, db_id=None, is_fav=False)
        self._stack.setCurrentIndex(2)
        self._status.setText("Enhancing recipe with Dishy…")
        # Kick off background enrichment — updates the detail view when done
        run_async(
            self._claude.enrich_scraped_recipe, recipe,
            on_result=self._on_enriched,
            on_error=lambda _err: self._status.setText(recipe.get("title", "Recipe loaded")),
        )

    def _on_enriched(self, enrichment: dict):
        """Merge Dishy's enrichment into the current recipe and refresh the detail view."""
        if not enrichment or self._current_recipe is None:
            return
        recipe = dict(self._current_recipe)
        recipe["description"] = enrichment.get("description", "")
        # Preserve existing tags (e.g. from scraper), merge with enriched ones, add Online
        existing_tags = recipe.get("tags", [])
        new_tags = enrichment.get("tags", [])
        merged = list(dict.fromkeys(new_tags + existing_tags))  # dedup, new first
        if "Online" not in merged:
            merged = ["Online"] + merged
        recipe["tags"] = merged
        recipe["icon"]     = enrichment.get("icon",     recipe.get("icon", "fa5s.utensils"))
        recipe["colour"]   = enrichment.get("colour",   recipe.get("colour", "#4fc3f7"))
        if enrichment.get("servings"):
            recipe["servings"] = enrichment["servings"]
        self._current_recipe = recipe
        self._populate_detail(recipe, db_id=self._current_recipe_db_id,
                              is_fav=self._current_recipe_is_fav)
        self._status.setText(recipe.get("title", "Recipe loaded"))

        # Auto-analyze nutrition if not already present
        ingredients = recipe.get("ingredients", [])
        if ingredients and not recipe.get("nutrition_per_serving"):
            servings = int(recipe.get("servings", 1) or 1)
            self._status.setText("Analysing nutrition with Dishy…")
            run_async(
                self._claude.analyze_recipe_nutrition, ingredients, servings,
                on_result=self._on_nutrition_analyzed,
                on_error=lambda _: self._status.setText(recipe.get("title", "Recipe loaded")),
            )

    def _on_scrape_error(self, _err: str):
        self._status.setText("Couldn't load that recipe — try another result")

    def _on_nutrition_analyzed(self, nutrition_data: dict):
        """Merge Dishy's recipe nutrition analysis into the current recipe and refresh."""
        if not self._current_recipe or not nutrition_data:
            return
        recipe = dict(self._current_recipe)
        recipe["nutrition_ingredients"] = nutrition_data.get("ingredients", [])
        recipe["nutrition_total"]       = nutrition_data.get("total", {})
        recipe["nutrition_per_serving"] = nutrition_data.get("per_serving", {})
        self._current_recipe = recipe
        # Persist to DB if recipe is already saved
        if self._current_recipe_db_id is not None:
            try:
                self._db.conn.execute(
                    "UPDATE recipes SET data_json=? WHERE id=?",
                    (json.dumps(recipe), self._current_recipe_db_id),
                )
                self._db.conn.commit()
            except Exception:
                pass
        self._populate_detail(
            recipe,
            db_id=self._current_recipe_db_id,
            is_fav=self._current_recipe_is_fav,
        )
        self._status.setText(recipe.get("title", "Recipe loaded"))

    def _log_recipe_to_today(self, recipe: dict):
        """Log a recipe's per-serving nutrition to today's food log."""
        nutr = recipe.get("nutrition_per_serving") or recipe.get("nutrition_total")
        if not nutr:
            return
        from datetime import datetime as _dt
        from models.database import Database as _DB
        db = _DB()
        db.connect()
        today = _dt.now().strftime("%Y-%m-%d")
        title = recipe.get("title", "Recipe")[:70]

        def _g(key: str, alt: str = "") -> float:
            v = float(nutr.get(key, 0) or 0)
            if not v and alt:
                v = float(nutr.get(alt, 0) or 0)
            return v

        db.add_nutrition_log(
            today, title,
            _g("kcal"),
            _g("protein_g", "protein"),
            _g("carbs_g",   "carbs"),
            _g("fat_g",     "fat"),
            _g("fiber_g",   "fiber"),
            _g("sugar_g",   "sugar"),
        )
        self._status.setText(
            f"Logged \"{title}\" to today's nutrition — "
            f"{round(_g('kcal'))} kcal · {round(_g('protein_g','protein'),1)}g protein"
        )

    # ── detail page ───────────────────────────────────────────────────────────

    def _populate_detail(self, recipe: dict, db_id: int | None, is_fav: bool):
        # Replace _detail_card entirely to guarantee all nested widgets are gone.
        # Manual layout clearing only goes 2 levels deep; ingredients/instructions
        # are 3 levels deep, leaving orphaned QLabels painted on top of the new content.
        parent_widget = self._detail_card.parent()
        parent_layout = parent_widget.layout()
        idx = parent_layout.indexOf(self._detail_card)
        parent_layout.removeWidget(self._detail_card)
        self._detail_card.deleteLater()

        self._detail_card = QWidget()
        self._detail_card.setObjectName("plan-card")
        self._detail_layout = QVBoxLayout(self._detail_card)
        self._detail_layout.setContentsMargins(28, 24, 28, 28)
        self._detail_layout.setSpacing(18)
        parent_layout.insertWidget(idx, self._detail_card)

        colour = recipe.get("colour", "#ff6b35")
        icon_name = recipe.get("icon", "fa5s.utensils")

        # 1. Title row
        title_row = QHBoxLayout()
        recipe_icon = QLabel()
        recipe_icon.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(24, 24)))
        recipe_icon.setStyleSheet("background: transparent;")
        title_lbl = QLabel(recipe.get("title", "Untitled Recipe"))
        title_lbl.setStyleSheet(
            "background: transparent; font-size: 20px; font-weight: 700;"
        )
        title_lbl.setWordWrap(True)
        title_row.addWidget(recipe_icon)
        title_row.addSpacing(10)
        title_row.addWidget(title_lbl, 1)
        self._detail_layout.addLayout(title_row)

        # 2. Meta chips (host, time, servings)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        if recipe.get("host"):
            meta_row.addWidget(_meta_chip("fa5s.globe", recipe["host"]))
        total = recipe.get("total_time") or (
            (recipe.get("prep_time", 0) or 0) + (recipe.get("cook_time", 0) or 0)
        )
        if total:
            meta_row.addWidget(_meta_chip("fa5s.clock", f"{total} min"))
        if recipe.get("yields") or recipe.get("servings"):
            meta_row.addWidget(_meta_chip("fa5s.users",
                                          str(recipe.get("yields") or recipe.get("servings", ""))))
        meta_row.addStretch()
        self._detail_layout.addLayout(meta_row)

        url = recipe.get("url", "")
        if url:
            url_lbl = QLabel(url[:90] + ("…" if len(url) > 90 else ""))
            url_lbl.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#444444', '#888888')}; font-size: 11px;"
            )
            self._detail_layout.addWidget(url_lbl)

        self._detail_layout.addWidget(_divider())

        # 3. Ingredients (moved up — high priority content, bigger text)
        ingredients = recipe.get("ingredients", [])
        nutr_ings   = recipe.get("nutrition_ingredients", [])
        if ingredients:
            self._detail_layout.addWidget(_section_label("INGREDIENTS"))
            ing_wrap = QVBoxLayout()
            ing_wrap.setSpacing(8)
            for i, ing in enumerate(ingredients):
                row = QHBoxLayout()
                row.setSpacing(8)
                dot = QLabel("·")
                dot.setStyleSheet(
                    f"background: transparent; color: {colour};"
                    " font-size: 20px; font-weight: 700;"
                )
                dot.setFixedWidth(16)
                lbl = QLabel(ing)
                lbl.setStyleSheet(
                    f"background: transparent; color: {theme_manager.c('#c0c0c0', '#222222')}; font-size: 15px;"
                )
                lbl.setWordWrap(True)
                row.addWidget(dot)
                row.addWidget(lbl, 1)
                # Inline per-ingredient macro pills when nutrition data is available
                if i < len(nutr_ings):
                    n = nutr_ings[i]
                    kcal_v = float(n.get("kcal", 0) or 0)
                    prot_v = float(n.get("protein_g", n.get("protein", 0)) or 0)
                    carb_v = float(n.get("carbs_g",  n.get("carbs",   0)) or 0)
                    fat_v  = float(n.get("fat_g",    n.get("fat",     0)) or 0)
                    _pill_style = (
                        " border-radius: 4px; font-size: 10px; font-weight: 700;"
                        " padding: 2px 7px; border: none;"
                    )
                    if kcal_v:
                        kl = QLabel(f"{round(kcal_v)} kcal")
                        kl.setStyleSheet(f"background: rgba(255,107,53,0.10); color: #ff6b35;{_pill_style}")
                        row.addWidget(kl)
                    if prot_v:
                        pl2 = QLabel(f"{round(prot_v, 1)}g prot")
                        pl2.setStyleSheet(f"background: rgba(76,175,138,0.10); color: #4caf8a;{_pill_style}")
                        row.addWidget(pl2)
                    if fat_v or carb_v:
                        fc_lbl = QLabel(f"{round(fat_v,1)}g fat · {round(carb_v,1)}g carbs")
                        fc_lbl.setStyleSheet(
                            f"background: transparent; color: {theme_manager.c('#555555','#888888')};"
                            " font-size: 10px;"
                        )
                        row.addWidget(fc_lbl)
                ing_wrap.addLayout(row)
            self._detail_layout.addLayout(ing_wrap)
            self._detail_layout.addWidget(_divider())

        # 4. Instructions (moved up — high priority content, bigger text)
        instructions = recipe.get("instructions", [])
        if instructions:
            self._detail_layout.addWidget(_section_label("INSTRUCTIONS"))
            steps_wrap = QVBoxLayout()
            steps_wrap.setSpacing(16)
            for i, step in enumerate(instructions, 1):
                row = QHBoxLayout()
                row.setSpacing(14)
                row.setAlignment(Qt.AlignmentFlag.AlignTop)
                num = QLabel(str(i))
                num.setAlignment(Qt.AlignmentFlag.AlignCenter)
                num.setFixedSize(32, 32)
                num.setStyleSheet(
                    f"background-color: rgba(255,107,53,0.12); color: {colour};"
                    " font-size: 13px; font-weight: 700; border-radius: 7px;"
                )
                lbl = QLabel(step)
                lbl.setStyleSheet(
                    f"background: transparent; color: {theme_manager.c('#b0b0b0', '#333333')}; font-size: 15px;"
                )
                lbl.setWordWrap(True)
                row.addWidget(num)
                row.addWidget(lbl, 1)
                steps_wrap.addLayout(row)
            self._detail_layout.addLayout(steps_wrap)
            self._detail_layout.addWidget(_divider())

        # 5. Nutrition summary
        nutr_per = recipe.get("nutrition_per_serving") or recipe.get("nutrition_total")
        if nutr_per and (nutr_per.get("kcal", 0) or nutr_per.get("protein_g", 0)
                         or nutr_per.get("protein", 0)):
            servings = recipe.get("servings") or recipe.get("nutrition_data", {}).get("servings", 1)
            _log_cb = lambda r=recipe: self._log_recipe_to_today(r)
            nutr_card = _nutrition_summary_card(nutr_per, servings=servings, on_log_today=_log_cb)
            self._detail_layout.addWidget(nutr_card)
            self._detail_layout.addWidget(_divider())

        # 6. Description
        desc = recipe.get("description", "")
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#888888', '#666666')}; font-size: 13px;"
            )
            desc_lbl.setWordWrap(True)
            self._detail_layout.addWidget(desc_lbl)

        # 7. Tags (moved to bottom)
        tags = recipe.get("tags", [])
        if tags:
            tag_row = QHBoxLayout()
            tag_row.setSpacing(6)
            _MEAL_SET = {"Breakfast", "Lunch", "Dinner", "Snack", "Dessert"}
            for tag in tags[:8]:
                is_dishy  = tag == "Dishy"
                is_online = tag == "Online"
                is_meal   = tag in _MEAL_SET
                if is_dishy or is_online:
                    _ic_name = "fa5s.robot" if is_dishy else "fa5s.globe"
                    _colour  = "#34d399"    if is_dishy else "#4fc3f7"
                    _bg      = "rgba(52,211,153,0.12)" if is_dishy else "rgba(79,195,247,0.12)"
                    _label   = "Dishy"      if is_dishy else "Online"
                    chip_w = QWidget()
                    chip_w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                    chip_w.setStyleSheet(f"background: {_bg}; border-radius: 4px;")
                    chip_hl = QHBoxLayout(chip_w)
                    chip_hl.setContentsMargins(7, 3, 9, 3)
                    chip_hl.setSpacing(4)
                    ic = QLabel()
                    ic.setPixmap(qta.icon(_ic_name, color=_colour).pixmap(QSize(10, 10)))
                    ic.setStyleSheet("background: transparent;")
                    txt = QLabel(_label)
                    txt.setStyleSheet(
                        f"color: {_colour}; font-size: 11px; font-weight: 700;"
                        " background: transparent;"
                    )
                    chip_hl.addWidget(ic)
                    chip_hl.addWidget(txt)
                    tag_row.addWidget(chip_w)
                elif is_meal:
                    chip = QLabel(tag)
                    chip.setStyleSheet(
                        "background: rgba(76,175,138,0.12); color: #4caf8a;"
                        " border: 1px solid rgba(76,175,138,0.3); border-radius: 4px;"
                        " padding: 3px 10px; font-size: 11px; font-weight: 600;"
                    )
                    tag_row.addWidget(chip)
                else:
                    chip = QLabel(tag)
                    chip.setStyleSheet(
                        f"background-color: {theme_manager.c('rgba(255,107,53,0.1)', 'rgba(255,107,53,0.12)')};"
                        " color: #ff6b35; border-radius: 4px; padding: 3px 10px; font-size: 11px;"
                    )
                    tag_row.addWidget(chip)
            tag_row.addStretch()
            self._detail_layout.addLayout(tag_row)

        # 8. Photo banner (moved to bottom, larger)
        photo_path = recipe.get("photo_path", "")
        if photo_path:
            import os as _os
            if _os.path.exists(photo_path):
                px = QPixmap(photo_path)
                if not px.isNull():
                    target_w = 720
                    target_h = 320
                    px = px.scaled(
                        target_w, target_h,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    if px.width() > target_w or px.height() > target_h:
                        x = (px.width()  - target_w) // 2
                        y = (px.height() - target_h) // 2
                        px = px.copy(x, y, target_w, target_h)
                    photo_lbl = QLabel()
                    photo_lbl.setPixmap(px)
                    photo_lbl.setFixedHeight(target_h)
                    photo_lbl.setStyleSheet("border-radius: 10px; background: transparent;")
                    photo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._detail_layout.addWidget(photo_lbl)

        self._detail_layout.addWidget(_divider())

        # 9. Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        # Save / already saved
        self._save_btn = QPushButton("  Save Recipe")
        self._save_btn.setObjectName("ghost-btn")
        self._save_btn.setIcon(qta.icon("fa5s.bookmark", color=theme_manager.c("#888888", "#555555")))
        self._save_btn.setIconSize(QSize(13, 13))
        self._save_btn.setFixedHeight(40)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if db_id is not None:
            self._save_btn.setText("  Saved ✓")
            self._save_btn.setDisabled(True)
        else:
            self._save_btn.clicked.connect(self._save_recipe)

        # Favourite toggle
        self._fav_btn = QPushButton()
        self._fav_btn.setObjectName("ghost-btn")
        self._fav_btn.setFixedHeight(40)
        self._fav_btn.setFixedWidth(44)
        self._fav_btn.setCheckable(True)
        self._fav_btn.setChecked(is_fav)
        self._fav_btn.setToolTip("Toggle favourite")
        self._update_fav_btn(is_fav)
        self._fav_btn.clicked.connect(lambda checked: self._toggle_fav(checked))

        # Add to calendar (only for saved recipes)
        self._cal_btn = QPushButton("  Add to Calendar")
        self._cal_btn.setObjectName("ghost-btn")
        self._cal_btn.setIcon(qta.icon("fa5s.calendar-plus", color="#888888"))
        self._cal_btn.setIconSize(QSize(13, 13))
        self._cal_btn.setFixedHeight(40)
        if db_id is not None:
            self._cal_btn.clicked.connect(lambda: self._add_to_calendar(db_id))
        else:
            self._cal_btn.setDisabled(True)
            self._cal_btn.setToolTip("Save the recipe first to add it to the calendar")

        # Photo button (for saved recipes only)
        if db_id is not None:
            photo_btn = QPushButton("  Photo")
            photo_btn.setObjectName("ghost-btn")
            photo_btn.setIcon(qta.icon("fa5s.image", color="#888888"))
            photo_btn.setIconSize(QSize(14, 14))
            photo_btn.setFixedHeight(40)
            photo_btn.setFixedWidth(100)
            photo_btn.setToolTip("Add or change the recipe photo")
            photo_btn.clicked.connect(lambda: self._change_photo(db_id))
            btn_row.addWidget(photo_btn)

            edit_btn = QPushButton("  Edit")
            edit_btn.setObjectName("ghost-btn")
            edit_btn.setIcon(qta.icon("fa5s.pen", color="#888888"))
            edit_btn.setIconSize(QSize(13, 13))
            edit_btn.setFixedHeight(40)
            edit_btn.setFixedWidth(90)
            edit_btn.setToolTip("Edit this recipe")
            edit_btn.clicked.connect(lambda: self._edit_recipe(db_id))
            btn_row.addWidget(edit_btn)

        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._fav_btn)
        btn_row.addWidget(self._cal_btn)
        btn_row.addStretch()
        self._detail_layout.addLayout(btn_row)

    def _edit_recipe(self, db_id: int):
        try:
            row = self._db.conn.execute(
                "SELECT data_json FROM recipes WHERE id=?", (db_id,)
            ).fetchone()
            if not row:
                return
            data = json.loads(row["data_json"] or "{}")
        except Exception:
            return
        self._create_page.load_for_edit(data, db_id)
        self._stack.setCurrentIndex(3)

    def _update_fav_btn(self, is_fav: bool):
        if is_fav:
            self._fav_btn.setIcon(qta.icon("fa5s.star", color="#fbbf24"))
        else:
            self._fav_btn.setIcon(qta.icon("fa5s.star", color="#444444"))
        self._fav_btn.setIconSize(QSize(15, 15))

    def _toggle_fav(self, checked: bool):
        self._update_fav_btn(checked)
        self._current_recipe_is_fav = checked
        if self._current_recipe_db_id is not None:
            self._db.toggle_favourite(self._current_recipe_db_id, checked)

    def _change_photo(self, db_id: int):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a photo", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
        )
        if not path:
            return
        try:
            row = self._db.conn.execute(
                "SELECT data_json FROM recipes WHERE id=?", (db_id,)
            ).fetchone()
            if not row:
                return
            data = json.loads(row["data_json"] or "{}")
            data["photo_path"] = path
            self._db.conn.execute(
                "UPDATE recipes SET data_json=? WHERE id=?",
                (json.dumps(data), db_id)
            )
            self._db.conn.commit()
            # Refresh detail view so photo appears
            if self._current_recipe is not None:
                self._current_recipe["photo_path"] = path
            self._populate_detail(
                {**data, "photo_path": path},
                db_id=db_id,
                is_fav=bool(self._fav_btn.isChecked()),
            )
        except Exception:
            pass

    def _add_to_calendar(self, db_id: int):
        title = (self._current_recipe or {}).get("title", "Recipe")
        dlg = AddToCalendarDialog(title, db_id, self._db, parent=self)
        if dlg.exec():
            self._cal_btn.setText("  Added ✓")
            self._cal_btn.setDisabled(True)

    # ── save scraped recipe ────────────────────────────────────────────────────

    def _save_recipe(self):
        if not self._current_recipe:
            return
        r = self._current_recipe
        title = r.get("title", "Untitled")

        # Duplicate detection
        existing = self._db.conn.execute(
            "SELECT id FROM recipes WHERE LOWER(title)=LOWER(?)", (title,)
        ).fetchone()
        if existing:
            msg = QMessageBox(self)
            msg.setWindowTitle("Recipe already exists")
            msg.setText(
                f'"{title}" is already in your saved recipes.\n\n'
                "Save another copy anyway?"
            )
            msg.setIcon(QMessageBox.Icon.Question)
            save_anyway = msg.addButton("Save anyway", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if msg.clickedButton() is not save_anyway:
                return

        recipe_id = self._db.save_recipe(
            source_id=r.get("url", ""),
            source="scraped",
            title=title,
            image_url=r.get("image", ""),
            summary="",
            servings=0,
            ready_mins=r.get("total_time", 0) or 0,
            data_json=json.dumps(r),
        )
        self._current_recipe_db_id = recipe_id
        self._save_btn.setText("  Saved ✓")
        self._save_btn.setDisabled(True)
        self._cal_btn.setEnabled(True)
        self._cal_btn.clicked.connect(lambda: self._add_to_calendar(recipe_id))
        self._fav_btn.setEnabled(True)
        self._status.setText(f"Saved: {title}")
        self._trigger_image_upload(recipe_id, r.get("image", ""))

    # ── recipe created from form ───────────────────────────────────────────────

    def _on_recipe_created(self, recipe_id: int, data: dict):
        self._current_recipe = data
        self._current_recipe_db_id = recipe_id
        self._current_recipe_is_fav = False
        self._load_saved_recipes()
        self._came_from_search = False
        self._populate_detail(data, db_id=recipe_id, is_fav=False)
        self._stack.setCurrentIndex(2)
        self._status.setText(f"Created: {data.get('title', '')}")
        if self._sync_fn:
            self._sync_fn()
        self._trigger_image_upload(recipe_id, data.get("photo_path", "") or data.get("image", ""))

        # If nutrition wasn't analyzed at create time, do it now in background
        per_s = data.get("nutrition_per_serving", {})
        if not per_s or not float(per_s.get("kcal", 0) or 0):
            ingreds  = data.get("ingredients", [])
            servings = int(data.get("servings") or 4)
            if ingreds:
                def _analyze():
                    return self._claude.analyze_recipe_nutrition(ingreds, servings)

                def _on_nutr(nutr):
                    if not nutr:
                        return
                    try:
                        row = self._db.conn.execute(
                            "SELECT data_json FROM recipes WHERE id=?", (recipe_id,)
                        ).fetchone()
                        if not row:
                            return
                        d = json.loads(row["data_json"] or "{}")
                        d["nutrition_ingredients"] = nutr.get("ingredients", [])
                        d["nutrition_total"]       = nutr.get("total", {})
                        d["nutrition_per_serving"] = nutr.get("per_serving", {})
                        self._db.conn.execute(
                            "UPDATE recipes SET data_json=? WHERE id=?",
                            (json.dumps(d), recipe_id),
                        )
                        self._db.conn.commit()
                        if self._nutrition_refresh_fn:
                            self._nutrition_refresh_fn()
                    except Exception:
                        pass

                run_async(_analyze, _on_nutr)
