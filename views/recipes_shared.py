from datetime import datetime, timedelta
from utils.theme import manager as theme_manager

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QDialog, QComboBox,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtCore import QTimer

from models.database import Database
from views.recipe_catalog import (
    DAYS,
    MEAL_TYPES,
)

# ── Small helpers ────────────────────────────────────────────────────────────

def _meta_chip(icon_name: str, text: str) -> QWidget:
    w = QWidget()
    w.setStyleSheet(
        f"background-color: {theme_manager.c('#14181c', '#f2ebe2')};"
        f" border-radius: 12px; border: 1px solid {theme_manager.c('#2a3037', '#ddd1c4')};"
    )
    row = QHBoxLayout(w)
    row.setContentsMargins(10, 5, 10, 5)
    row.setSpacing(6)
    ic = QLabel()
    ic.setPixmap(qta.icon(icon_name, color=theme_manager.c("#8d867d", "#756d63")).pixmap(QSize(11, 11)))
    ic.setStyleSheet("background: transparent;")
    lbl = QLabel(text)
    lbl.setStyleSheet(f"background: transparent; color: {theme_manager.c('#a39c93', '#7c7368')}; font-size: 12px;")
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
    """Full-width nutrition card with restrained metadata styling."""
    card = QWidget()
    card.setObjectName("stat-card")
    vl = QVBoxLayout(card)
    vl.setContentsMargins(20, 16, 20, 18)
    vl.setSpacing(14)

    # ── Header ──────────────────────────────────────────────────────────────
    hdr_row = QHBoxLayout()
    powered_lbl = QLabel("Nutrition Summary")
    powered_lbl.setStyleSheet(
        f"background: transparent; color: {theme_manager.c('#f1ece5', '#181510')}; font-size: 13px; font-weight: 700;"
    )
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

    # ── Macro tiles — fill full width with restrained, mostly neutral chrome ─
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
            f"background: {theme_manager.c('#14181c', '#f2ebe2')};"
            f" border: 1px solid {theme_manager.c('#2a3037', '#ddd1c4')}; border-radius: 10px;"
        )
        tl = QVBoxLayout(tile)
        tl.setContentsMargins(6, 14, 6, 14)
        tl.setSpacing(5)
        num_lbl = QLabel(f"{round(val)}" if label == "kcal" else f"{round(val, 1)}")
        num_lbl.setStyleSheet(
            f"color: {theme_manager.c('#f1ece5', '#181510')}; font-size: 26px; font-weight: 800;"
            " background: transparent; border: none;"
        )
        lbl_lbl = QLabel(label)
        lbl_lbl.setStyleSheet(
            f"color: {theme_manager.c('#8d867d', '#756d63')}; font-size: 10px; font-weight: 600;"
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
        log_btn.setIcon(qta.icon("fa5s.plus-circle", color="#ff6b35"))
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
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self._build_ui()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        self._drag_pos = None

    def _build_ui(self):
        from PySide6.QtWidgets import QWidget as _QWidget
        tm = theme_manager
        is_dark = tm.mode == "dark"
        text = tm.c("#f0f0f0", "#1a1a1a")
        muted = tm.c("#888888", "#666666")
        input_bg = tm.c("#1a1a1a", "#f5f5f5")
        border = tm.c("#2a2a2a", "#e0e0e0")

        combo_style = (
            f"QComboBox {{ background: {input_bg}; border: 1px solid {border};"
            f" border-radius: 7px; color: {text}; padding: 5px 10px; font-size: 14px; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background: {tm.c('#1a1a1a', '#ffffff')};"
            f" color: {text}; selection-background-color: {tm.c('#2a2a2a', '#e8e8e8')}; }}"
        )
        label_style = f"font-size: 12px; font-weight: 600; color: {muted}; background: transparent;"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        card = _QWidget()
        card.setObjectName("atc-card")
        card.setFixedWidth(360)
        card.setStyleSheet(
            f"QWidget#atc-card {{"
            f"  background: {tm.c('#161616', '#ffffff')};"
            f"  border-radius: 14px;"
            f"  border: 1px solid {border};"
            f"}}"
        )

        layout = QVBoxLayout(card)
        layout.setSpacing(14)
        layout.setContentsMargins(22, 20, 22, 20)

        # Header row with title and X close button
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        hdr_lbl = QLabel("Add to Meal Planner")
        hdr_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {text}; background: transparent;"
        )
        hdr.addWidget(hdr_lbl, 1)
        close_x = QPushButton()
        close_x.setIcon(qta.icon("fa5s.times", color=muted))
        close_x.setIconSize(QSize(13, 13))
        close_x.setFixedSize(28, 28)
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 14px; }}"
            f"QPushButton:hover {{ background: {('rgba(255,255,255,0.08)' if is_dark else 'rgba(0,0,0,0.06)')}; }}"
        )
        close_x.clicked.connect(self.reject)
        hdr.addWidget(close_x, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(hdr)

        recipe_lbl = QLabel(f"\"{self._recipe_title[:36]}\"")
        recipe_lbl.setWordWrap(True)
        recipe_lbl.setStyleSheet(
            f"color: {tm.c('#aaaaaa', '#555555')}; font-size: 13px; background: transparent;"
        )
        layout.addWidget(recipe_lbl)

        # Week
        today = datetime.now().date()
        monday = today - timedelta(days=today.weekday())
        self._week_combo = QComboBox()
        self._week_combo.setStyleSheet(combo_style)
        for i in range(4):
            ws = monday + timedelta(weeks=i)
            label = "This week" if i == 0 else ("Next week" if i == 1 else ws.strftime("%d %b"))
            self._week_combo.addItem(label, ws.isoformat())
        wk_lbl = QLabel("Week")
        wk_lbl.setStyleSheet(label_style)
        layout.addWidget(wk_lbl)
        layout.addWidget(self._week_combo)

        # Day
        self._day_combo = QComboBox()
        self._day_combo.setStyleSheet(combo_style)
        for d in DAYS:
            self._day_combo.addItem(d)
        current_day = today.strftime("%A")
        if current_day in DAYS:
            self._day_combo.setCurrentIndex(DAYS.index(current_day))
        day_lbl = QLabel("Day")
        day_lbl.setStyleSheet(label_style)
        layout.addWidget(day_lbl)
        layout.addWidget(self._day_combo)

        # Meal type
        self._meal_combo = QComboBox()
        self._meal_combo.setStyleSheet(combo_style)
        for m in MEAL_TYPES:
            self._meal_combo.addItem(m.capitalize(), m)
        meal_lbl = QLabel("Meal")
        meal_lbl.setStyleSheet(label_style)
        layout.addWidget(meal_lbl)
        layout.addWidget(self._meal_combo)

        # Buttons
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

        add_btn = QPushButton("Add")
        add_btn.setFixedHeight(38)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            "QPushButton { background: #ff6b35; color: #ffffff; border: none;"
            " border-radius: 9px; font-size: 13px; font-weight: 600; padding: 0 18px; }"
            "QPushButton:hover { background: #e05a28; }"
        )
        add_btn.clicked.connect(self._save)

        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(add_btn)
        layout.addLayout(btn_row)

        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

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


class DishyNutritionLoadingDialog(QDialog):
    """Blocking themed modal shown while Dishy gathers recipe nutrition."""

    _SPIN = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, host: str, parent=None):
        super().__init__(parent)
        self._host = host or "the web"
        self._step = 0
        self._can_close = False
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(90)

    def _build_ui(self):
        tm = theme_manager
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        card = QWidget()
        card.setObjectName("dishy-nutrition-loading")
        card.setFixedWidth(410)
        card.setStyleSheet(
            f"QWidget#dishy-nutrition-loading {{"
            f" background: {tm.c('#101417', '#fbf6ef')};"
            f" border: 1px solid {tm.c('#20262d', '#e2d7ca')};"
            f" border-radius: 16px;"
            f"}}"
        )

        vl = QVBoxLayout(card)
        vl.setContentsMargins(28, 24, 28, 24)
        vl.setSpacing(12)

        icon = QLabel()
        icon.setPixmap(qta.icon("fa5s.robot", color="#ff6b35").pixmap(QSize(30, 30)))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("background: transparent;")
        vl.addWidget(icon)

        title = QLabel("Dishy Is Gathering Nutrition")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"background: transparent; color: {tm.c('#f1ece5', '#1a140f')};"
            "font-size: 16px; font-weight: 700;"
        )
        vl.addWidget(title)

        sub = QLabel(f"Pulling the recipe from {self._host} and building a cleaner nutrition summary.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"background: transparent; color: {tm.c('#a39c93', '#6f6459')};"
            "font-size: 12px;"
        )
        vl.addWidget(sub)

        self._status = QLabel(f"{self._SPIN[0]}  Working...")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet(
            f"background: {tm.c('rgba(255,107,53,0.10)', 'rgba(255,107,53,0.08)')};"
            "color: #ff6b35;"
            "border: none; border-radius: 10px;"
            "font-size: 12px; font-weight: 700; padding: 9px 12px;"
        )
        vl.addWidget(self._status)

        note = QLabel("This closes automatically as soon as the nutrition is ready.")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
        note.setStyleSheet(
            f"background: transparent; color: {tm.c('#7e776f', '#8a8075')};"
            "font-size: 11px;"
        )
        vl.addWidget(note)

        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

    def _tick(self):
        self._step = (self._step + 1) % len(self._SPIN)
        self._status.setText(f"{self._SPIN[self._step]}  Working...")

    def set_status(self, text: str):
        self._status.setText(f"{self._SPIN[self._step]}  {text}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        # Prevent user-driven close while nutrition gathering is active.
        if not self._can_close:
            event.ignore()
            return
        super().closeEvent(event)

    def allow_close(self):
        try:
            self._timer.stop()
        except Exception:
            pass
        self._can_close = True
