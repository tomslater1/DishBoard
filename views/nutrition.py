from datetime import datetime, timedelta
import json
import qtawesome as qta
from utils.theme import manager as theme_manager
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont

from api.claude_ai import ClaudeAI
from models.database import Database
from utils.workers import run_async
from utils.macro_goals import MACRO_SPECS, get_macro_goals, get_broadcaster

_claude = ClaudeAI()

_SECTION_COLOUR = "#e05c7a"


def _week_start() -> str:
    today = datetime.now().date()
    return (today - timedelta(days=today.weekday())).isoformat()


# ------------------------------------------------------------------ MacroRing

class MacroRing(QWidget):
    """Circular arc progress ring drawn with QPainter. Shows value + unit in centre."""

    def __init__(self, colour: str, goal: float, unit: str, size: int = 110, parent=None):
        super().__init__(parent)
        self._colour = colour
        self._goal   = goal
        self._unit   = unit
        self._value  = 0.0
        self.setFixedSize(size, size)

    def set_value(self, value: float):
        self._value = value
        self.update()

    def set_goal(self, goal: float):
        self._goal = goal
        self.update()

    def apply_theme(self, _mode: str):
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h  = self.width(), self.height()
        s     = min(w, h)
        m     = max(6, int(s * 0.09))
        rect  = QRectF(m, m, w - 2 * m, h - 2 * m)
        pen_w = max(5, int(s * 0.088))

        bg_col = QColor(theme_manager.c("#222222", "#e8e8e8"))
        bg_pen = QPen(bg_col)
        bg_pen.setWidth(pen_w)
        bg_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        pct  = min(self._value / self._goal, 1.0) if self._goal else 0.0
        span = int(pct * 360 * 16)
        if span > 0:
            fg_pen = QPen(QColor(self._colour))
            fg_pen.setWidth(pen_w)
            fg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(fg_pen)
            painter.drawArc(rect, 90 * 16, -span)

        cx = w / 2
        cy = h / 2

        val_size = max(10, int(s * 0.22))
        val_str  = str(int(self._value))
        val_font = QFont()
        val_font.setPixelSize(val_size)
        val_font.setWeight(QFont.Weight.Bold)
        painter.setFont(val_font)
        painter.setPen(QColor(theme_manager.c("#f0f0f0", "#1a1a1a")))
        val_rect = QRectF(0, cy - val_size, w, val_size * 1.5)
        painter.drawText(val_rect, Qt.AlignmentFlag.AlignCenter, val_str)

        unit_size = max(6, int(s * 0.11))
        unit_font = QFont()
        unit_font.setPixelSize(unit_size)
        painter.setFont(unit_font)
        painter.setPen(QColor(theme_manager.c("#555555", "#888888")))
        unit_rect = QRectF(0, cy + val_size * 0.4, w, unit_size * 1.6)
        painter.drawText(unit_rect, Qt.AlignmentFlag.AlignCenter, self._unit)

        painter.end()


# ------------------------------------------------------------------ view

class NutritionView(QWidget):
    def __init__(self, navigate_to=None, parent=None):
        super().__init__(parent)
        self.setObjectName("view-container")
        self._navigate_to   = navigate_to or (lambda i: None)
        self._db = Database()
        self._db.connect()

        # Instance refs to dynamic widgets (refreshed on each _rebuild_content)
        self._rings:            dict[str, MacroRing] = {}
        self._log_rows_layout:  QVBoxLayout | None   = None
        self._empty_log_lbl:    QLabel | None        = None
        self._quick_input:      QLineEdit | None     = None
        self._quick_add_btn:    QPushButton | None   = None
        self._quick_status:     QLabel | None        = None
        self._quick_detail:     QWidget | None       = None
        self._qd_name:          QLabel | None        = None
        self._qd_serving:       QLabel | None        = None
        self._qd_note:          QLabel | None        = None
        self._qd_macros_row:    QHBoxLayout | None   = None
        self._selected_food:    dict | None          = None

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)
        get_broadcaster().goals_changed.connect(self._rebuild_content)
        self._rebuild_content()

    # ── Build ────────────────────────────────────────────────────────────────

    def _rebuild_content(self):
        self._rings.clear()
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
            f"QScrollBar::handle:vertical {{ background: {theme_manager.c('#2a2a2a', '#cccccc')}; border-radius: 3px; min-height: 20px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content.setMinimumHeight(780)  # prevents row_b from crushing at small window heights
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 20, 28, 16)
        layout.setSpacing(12)

        layout.addLayout(self._build_header())
        layout.addLayout(self._build_stat_row())

        # Row A — rings (wider) | today's plan
        row_a = QHBoxLayout()
        row_a.setSpacing(12)
        rings_card = self._build_rings_card()
        rings_card.setMinimumHeight(200)
        plan_card = self._build_todays_plan_card()
        plan_card.setMinimumHeight(200)
        row_a.addWidget(rings_card, 3)
        row_a.addWidget(plan_card, 2)
        layout.addLayout(row_a)

        # Row B — food log | weekly chart | right column (quick add + recently logged)
        row_b = QHBoxLayout()
        row_b.setSpacing(12)
        log_card = self._build_log_card()
        log_card.setMinimumHeight(260)
        weekly_card = self._build_weekly_card()
        weekly_card.setMinimumHeight(260)
        row_b.addWidget(log_card, 5)
        row_b.addWidget(weekly_card, 4)

        right_col = QWidget()
        right_col.setStyleSheet("background: transparent;")
        right_col.setMinimumHeight(260)
        right_col_layout = QVBoxLayout(right_col)
        right_col_layout.setContentsMargins(0, 0, 0, 0)
        right_col_layout.setSpacing(12)
        right_col_layout.addWidget(self._build_quick_add_card(), 3)
        right_col_layout.addWidget(self._build_recent_foods_card(), 2)
        row_b.addWidget(right_col, 4)

        layout.addLayout(row_b, 1)

        scroll.setWidget(content)
        self._outer.addWidget(scroll)
        self._refresh_log()

    # ── Header ───────────────────────────────────────────────────────────────

    def _build_header(self) -> QHBoxLayout:
        hl = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(2)
        left.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Nutrition")
        title.setObjectName("page-title")
        date_lbl = QLabel(datetime.now().strftime("%A, %d %B %Y"))
        date_lbl.setObjectName("page-date")
        left.addWidget(title)
        left.addWidget(date_lbl)
        hl.addLayout(left)
        hl.addStretch()
        robot_ic = QLabel()
        robot_ic.setPixmap(qta.icon("fa5s.robot", color="#34d399").pixmap(QSize(14, 14)))
        robot_ic.setStyleSheet("background: transparent;")
        badge_lbl = QLabel("Powered by Dishy")
        badge_lbl.setStyleSheet(
            "background: rgba(52,211,153,0.12); color: #34d399;"
            " border-radius: 6px; padding: 5px 14px;"
            " font-size: 12px; font-weight: 700;"
            " border: 1px solid rgba(52,211,153,0.25);"
        )
        hl.addWidget(robot_ic)
        hl.addSpacing(7)
        hl.addWidget(badge_lbl)
        return hl

    # ── Stat tiles ───────────────────────────────────────────────────────────

    def _build_stat_row(self) -> QHBoxLayout:
        today_str = datetime.now().strftime("%Y-%m-%d")
        # Totals for today come from the meal plan (same source as Today's Log)
        slots  = self._db.get_today_meal_plan_with_nutrition()
        goals  = get_macro_goals(self._db)
        totals = {k: 0.0 for k in goals}
        for slot in slots:
            per_s = json.loads(slot.get("data_json") or "{}").get("nutrition_per_serving", {})
            for k in totals:
                totals[k] += float(per_s.get(k, 0) or 0)

        week_data   = self._db.get_nutrition_totals_for_range(_week_start(), today_str)
        week_days   = max(week_data["days"], 1)
        week_avg    = week_data["kcal"] / week_days

        month_start = datetime.now().strftime("%Y-%m-01")
        month_data  = self._db.get_nutrition_totals_for_range(month_start, today_str)

        def _tile(icon_name: str, value: str, label: str, colour: str) -> QWidget:
            tile = QWidget()
            tile.setObjectName("stat-card")
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            hl2 = QHBoxLayout(tile)
            hl2.setContentsMargins(16, 10, 16, 10)
            hl2.setSpacing(10)
            ic = QLabel()
            ic.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(18, 18)))
            ic.setStyleSheet("background: transparent;")
            ic.setFixedSize(18, 18)
            vl = QVBoxLayout()
            vl.setSpacing(1)
            v_lbl = QLabel(value)
            v_lbl.setObjectName("stat-value")
            l_lbl = QLabel(label)
            l_lbl.setObjectName("stat-label")
            vl.addWidget(v_lbl)
            vl.addWidget(l_lbl)
            hl2.addWidget(ic)
            hl2.addLayout(vl)
            hl2.addStretch()
            return tile

        hl = QHBoxLayout()
        hl.setSpacing(12)
        hl.addWidget(_tile(
            "fa5s.fire",
            f"{int(totals['kcal'])} / {int(goals['kcal'])} kcal",
            "Calories today",
            "#ff6b35",
        ))
        hl.addWidget(_tile(
            "fa5s.dumbbell",
            f"{totals['protein_g']:.0f}g / {int(goals['protein_g'])}g",
            "Protein today",
            "#4fc3f7",
        ))
        hl.addWidget(_tile(
            "fa5s.chart-line",
            f"{int(week_avg)} kcal / day",
            "This week average",
            "#aed581",
        ))
        days_lbl = month_data["days"]
        hl.addWidget(_tile(
            "fa5s.calendar-check",
            f"{days_lbl} day{'s' if days_lbl != 1 else ''}",
            "Logged this month",
            "#c084fc",
        ))
        return hl

    # ── Today's intake rings ─────────────────────────────────────────────────

    def _build_rings_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(qta.icon("fa5s.chart-pie", color=_SECTION_COLOUR).pixmap(QSize(14, 14)))
        ic.setStyleSheet("background: transparent;")
        hdr_lbl = QLabel("TODAY'S INTAKE")
        hdr_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#888888', '#666666')};"
            " font-size: 13px; font-weight: 700; letter-spacing: 1px;"
        )
        today_badge = QLabel(datetime.now().strftime("%a %d %b"))
        today_badge.setStyleSheet(
            "background: rgba(224,92,122,0.12); color: #e05c7a;"
            " border-radius: 5px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
        )
        hdr.addWidget(ic)
        hdr.addSpacing(6)
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        hdr.addWidget(today_badge)
        layout.addLayout(hdr)

        # Rings — 2 rows of 3 for larger size
        def _make_ring_cell(key, label, goal, unit, colour):
            ring = MacroRing(colour, goal, unit, size=110)
            self._rings[key] = ring

            col = QVBoxLayout()
            col.setSpacing(5)
            col.setContentsMargins(0, 0, 0, 0)
            col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(ring, 0, Qt.AlignmentFlag.AlignHCenter)

            name_lbl = QLabel(label)
            name_lbl.setStyleSheet(
                f"background: transparent; color: {colour}; font-size: 12px; font-weight: 700;"
            )
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(name_lbl)

            goal_lbl = QLabel(f"/ {int(goal)} {unit}")
            goal_lbl.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#555555', '#888888')}; font-size: 10px;"
            )
            goal_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(goal_lbl)

            w = QWidget()
            w.setStyleSheet("background: transparent;")
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            w.setLayout(col)
            return w

        db_goals = get_macro_goals(self._db)
        for row_start in (0, 3):
            row_hl = QHBoxLayout()
            row_hl.setSpacing(0)
            for key, label, _default, unit, colour in MACRO_SPECS[row_start:row_start + 3]:
                row_hl.addWidget(_make_ring_cell(key, label, db_goals[key], unit, colour))
            layout.addLayout(row_hl)
            if row_start == 0:
                layout.addSpacing(8)

        return card

    # ── Today's plan (from meal planner) ─────────────────────────────────────

    def _build_todays_plan_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(qta.icon("fa5s.utensils", color="#4caf8a").pixmap(QSize(14, 14)))
        ic.setStyleSheet("background: transparent;")
        hdr_lbl = QLabel("TODAY'S PLAN")
        hdr_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#888888', '#666666')};"
            " font-size: 13px; font-weight: 700; letter-spacing: 1px;"
        )
        edit_btn = QPushButton("Edit →")
        edit_btn.setObjectName("ghost-btn")
        edit_btn.setFixedHeight(22)
        edit_btn.clicked.connect(lambda: self._navigate_to(2))
        hdr.addWidget(ic)
        hdr.addSpacing(6)
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        hdr.addWidget(edit_btn)
        layout.addLayout(hdr)

        today_name = datetime.now().strftime("%A")
        try:
            rows = self._db.conn.execute(
                "SELECT meal_type, custom_name, recipe_id FROM meal_plans "
                "WHERE week_start=? AND day_of_week=?",
                (_week_start(), today_name),
            ).fetchall()
            meals_today = {r["meal_type"]: r for r in rows}
        except Exception:
            meals_today = {}

        meal_defs = [
            ("breakfast", "fa5s.egg",            "Breakfast", "#ff9a5c"),
            ("lunch",     "fa5s.utensils",       "Lunch",     "#34d399"),
            ("dinner",    "fa5s.concierge-bell", "Dinner",    "#60a5fa"),
        ]

        total_plan_kcal = 0.0
        layout.addStretch(1)
        for meal_type, icon_name, label, colour in meal_defs:
            meal_widget, kcal = self._build_plan_row(meal_type, icon_name, label, colour, meals_today)
            total_plan_kcal += kcal
            layout.addWidget(meal_widget)
            layout.addSpacing(3)
        layout.addStretch(1)

        if total_plan_kcal > 0:
            total_lbl = QLabel(f"≈ {int(total_plan_kcal)} kcal planned today")
            total_lbl.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#555555', '#888888')}; font-size: 11px;"
            )
            layout.addWidget(total_lbl)

        return card

    def _build_plan_row(self, meal_type, icon_name, label, colour, meals_today):
        """Returns (QWidget, kcal_float)."""
        meal_data = meals_today.get(meal_type)
        meal_name = meal_data["custom_name"] if meal_data else ""
        recipe_id = meal_data["recipe_id"] if meal_data else None

        kcal = 0.0
        kcal_str = ""
        if recipe_id:
            try:
                rec = self._db.conn.execute(
                    "SELECT data_json FROM recipes WHERE id=?", (recipe_id,)
                ).fetchone()
                if rec:
                    dj    = json.loads(rec["data_json"] or "{}")
                    per_s = dj.get("nutrition_per_serving", {})
                    kcal  = float(per_s.get("kcal", 0) or 0)
                    if kcal > 0:
                        kcal_str = f"{int(kcal)} kcal"
            except Exception:
                pass

        row = QWidget()
        row.setObjectName("meal-slot")
        row.setFixedHeight(56)
        outer_hl = QHBoxLayout(row)
        outer_hl.setContentsMargins(0, 0, 0, 0)
        outer_hl.setSpacing(0)

        # Left accent strip (matches meal planner)
        strip = QWidget()
        strip.setFixedWidth(4)
        strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        strip.setStyleSheet(f"background: {colour}; border-radius: 2px;")
        outer_hl.addWidget(strip)

        rl = QHBoxLayout()
        rl.setContentsMargins(12, 0, 12, 0)
        rl.setSpacing(10)
        rl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        ic = QLabel()
        ic.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(14, 14)))
        ic.setStyleSheet("background: transparent;")
        ic.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        type_lbl = QLabel(label.upper())
        type_lbl.setStyleSheet(
            f"background: transparent; color: {colour};"
            " font-size: 10px; font-weight: 700; letter-spacing: 0.8px;"
        )
        if meal_name:
            val_lbl = QLabel(meal_name[:32] + ("…" if len(meal_name) > 32 else ""))
            val_lbl.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#e0e0e0', '#1a1a1a')};"
                " font-size: 12px; font-weight: 600;"
            )
        else:
            val_lbl = QLabel("Not planned")
            val_lbl.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#333333', '#bbbbbb')}; font-size: 12px;"
            )

        info_col.addWidget(type_lbl)
        info_col.addWidget(val_lbl)
        rl.addWidget(ic)
        rl.addLayout(info_col, 1)

        if kcal_str:
            kcal_lbl = QLabel(kcal_str)
            r, g, b = int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)
            kcal_lbl.setStyleSheet(
                f"background: rgba({r},{g},{b},0.13); color: {colour};"
                " border-radius: 4px; padding: 2px 7px; font-size: 11px; font-weight: 600;"
            )
            rl.addWidget(kcal_lbl)

        outer_hl.addLayout(rl, 1)
        return row, kcal

    # ── Today's food log ─────────────────────────────────────────────────────

    def _build_log_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(qta.icon("fa5s.clipboard-list", color=_SECTION_COLOUR).pixmap(QSize(14, 14)))
        ic.setStyleSheet("background: transparent;")
        hdr_lbl = QLabel("TODAY'S LOG")
        hdr_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#888888', '#666666')};"
            " font-size: 13px; font-weight: 700; letter-spacing: 1px;"
        )
        hdr.addWidget(ic)
        hdr.addSpacing(6)
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        layout.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { background: transparent; width: 4px; margin: 0; }"
            f"QScrollBar::handle:vertical {{ background: {theme_manager.c('#2a2a2a', '#cccccc')};"
            " border-radius: 2px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self._log_rows_container = QWidget()
        self._log_rows_container.setStyleSheet("background: transparent;")
        self._log_rows_layout = QVBoxLayout(self._log_rows_container)
        self._log_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._log_rows_layout.setSpacing(4)
        self._log_rows_layout.addStretch()
        scroll.setWidget(self._log_rows_container)
        layout.addWidget(scroll, 1)

        self._empty_log_lbl = QLabel("Nothing planned for today — edit your meal plan to see nutrition here →")
        self._empty_log_lbl.setObjectName("card-body")
        self._empty_log_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_log_lbl.setWordWrap(True)
        layout.addWidget(self._empty_log_lbl)

        return card

    # ── Weekly bar chart ─────────────────────────────────────────────────────

    def _build_weekly_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(qta.icon("fa5s.chart-bar", color="#4fc3f7").pixmap(QSize(14, 14)))
        ic.setStyleSheet("background: transparent;")
        hdr_lbl = QLabel("THIS WEEK")
        hdr_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#888888', '#666666')};"
            " font-size: 13px; font-weight: 700; letter-spacing: 1px;"
        )
        hdr.addWidget(ic)
        hdr.addSpacing(6)
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        layout.addLayout(hdr)

        # Compute Mon–Sun kcal
        today   = datetime.now().date()
        monday  = today - timedelta(days=today.weekday())
        days_data = []
        max_kcal  = 500.0  # floor so empty week still has proportions
        GOAL_KCAL = get_macro_goals(self._db).get("kcal", 2000.0)

        for i in range(7):
            d     = monday + timedelta(days=i)
            d_str = d.isoformat()
            if d == today:
                # Today: sum from meal plan (mirrors Today's Log)
                try:
                    plan_slots = self._db.get_today_meal_plan_with_nutrition()
                    kcal = sum(
                        float(json.loads(s.get("data_json") or "{}").get(
                            "nutrition_per_serving", {}).get("kcal", 0) or 0)
                        for s in plan_slots
                    )
                except Exception:
                    kcal = 0.0
            else:
                # Past / future days: use nutrition_logs history
                try:
                    db_row = self._db.conn.execute(
                        "SELECT SUM(kcal) AS total FROM nutrition_logs WHERE log_date=?", (d_str,)
                    ).fetchone()
                    kcal = float(db_row["total"] or 0)
                except Exception:
                    kcal = 0.0
            days_data.append((d.strftime("%a"), d.day, kcal, d == today))
            if kcal > max_kcal:
                max_kcal = kcal

        # Make sure the goal line fits within the chart when goal < max
        chart_max = max(max_kcal, GOAL_KCAL)

        # Bars
        CHART_H = 100
        layout.addStretch(1)
        bars_row = QHBoxLayout()
        bars_row.setSpacing(4)

        for day_label, day_num, kcal, is_today in days_data:
            col_widget = QWidget()
            col_widget.setStyleSheet("background: transparent;")
            col_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            col_layout = QVBoxLayout(col_widget)
            col_layout.setContentsMargins(0, 0, 0, 0)
            col_layout.setSpacing(2)
            col_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

            # kcal value above bar (only if > 0)
            kcal_lbl = QLabel(str(int(kcal)) if kcal > 0 else "—")
            kcal_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            kcal_colour = "#e05c7a" if (is_today and kcal > 0) else theme_manager.c("#555555", "#999999")
            kcal_lbl.setStyleSheet(
                f"background: transparent; color: {kcal_colour};"
                f" font-size: {'10px; font-weight: 700' if is_today else '9px'};"
            )
            col_layout.addWidget(kcal_lbl)

            # Bar region — bottom-anchored via spacer
            bar_region = QWidget()
            bar_region.setFixedHeight(CHART_H)
            bar_region.setStyleSheet("background: transparent;")
            br_layout = QVBoxLayout(bar_region)
            br_layout.setContentsMargins(3, 0, 3, 0)
            br_layout.setSpacing(0)

            pct   = min(kcal / chart_max, 1.0) if kcal > 0 else 0.0
            bar_h = max(3, int(pct * CHART_H)) if kcal > 0 else 3
            spacer_widget = QWidget()
            spacer_widget.setFixedHeight(CHART_H - bar_h)
            spacer_widget.setStyleSheet("background: transparent;")
            br_layout.addWidget(spacer_widget)

            bar_colour = "#e05c7a" if is_today else (
                "#4fc3f7" if kcal >= GOAL_KCAL else theme_manager.c("#2a2a2a", "#d0d0e0")
            )
            bar = QWidget()
            bar.setFixedHeight(bar_h)
            bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            bar.setStyleSheet(f"background: {bar_colour}; border-radius: 3px;")
            br_layout.addWidget(bar)
            col_layout.addWidget(bar_region)

            # Day label + date number
            today_colour = "#e05c7a" if is_today else theme_manager.c("#555555", "#888888")
            day_lbl = QLabel(day_label)
            day_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            day_lbl.setStyleSheet(
                f"background: transparent; color: {today_colour};"
                f" font-size: 10px; font-weight: {'700' if is_today else '500'};"
            )
            col_layout.addWidget(day_lbl)

            num_lbl = QLabel(str(day_num))
            num_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            num_lbl.setStyleSheet(
                f"background: transparent; color: {today_colour};"
                f" font-size: 9px; font-weight: {'700' if is_today else '400'};"
            )
            col_layout.addWidget(num_lbl)

            bars_row.addWidget(col_widget)

        layout.addLayout(bars_row)
        layout.addStretch(1)

        # Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sep.setStyleSheet(f"background: {theme_manager.c('#1e1e1e', '#eeeeee')};")
        layout.addWidget(sep)

        # Week summary — total, avg vs goal, days logged
        today_str  = datetime.now().strftime("%Y-%m-%d")
        week_data  = self._db.get_nutrition_totals_for_range(_week_start(), today_str)
        days_logged = week_data.get("days", 0)
        total_kcal  = week_data.get("kcal", 0.0)
        avg_kcal    = total_kcal / max(days_logged, 1)
        diff        = avg_kcal - GOAL_KCAL

        summary_row = QHBoxLayout()
        summary_row.setSpacing(0)

        for val_str, lbl_str, colour in [
            (f"{int(total_kcal):,}", "week total", "#ff6b35"),
            (f"{int(avg_kcal)}/day",  "avg kcal",   "#4fc3f7"),
            (f"{days_logged}/7",      "days logged", "#aed581"),
        ]:
            vl = QVBoxLayout()
            vl.setSpacing(1)
            v_lbl = QLabel(val_str)
            v_lbl.setStyleSheet(
                f"background: transparent; color: {colour}; font-size: 13px; font-weight: 700;"
            )
            l_lbl = QLabel(lbl_str)
            l_lbl.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#555555', '#888888')}; font-size: 10px;"
            )
            vl.addWidget(v_lbl)
            vl.addWidget(l_lbl)
            cell = QWidget()
            cell.setStyleSheet("background: transparent;")
            cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            cell.setLayout(vl)
            summary_row.addWidget(cell)

        layout.addLayout(summary_row)

        # Goal vs avg indicator
        if days_logged > 0:
            arrow = "▲" if diff >= 0 else "▼"
            diff_colour = "#e05c7a" if diff > 100 else ("#4fc3f7" if diff < -50 else "#aed581")
            goal_lbl = QLabel(
                f"{arrow} {abs(int(diff))} kcal {'above' if diff >= 0 else 'under'} daily goal ({int(GOAL_KCAL):,})"
            )
            goal_lbl.setStyleSheet(
                f"background: transparent; color: {diff_colour}; font-size: 10px; font-weight: 600;"
            )
            layout.addWidget(goal_lbl)

        return card

    # ── Quick Add ────────────────────────────────────────────────────────────

    def _build_quick_add_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        robot_ic = QLabel()
        robot_ic.setPixmap(qta.icon("fa5s.robot", color="#34d399").pixmap(QSize(14, 14)))
        robot_ic.setStyleSheet("background: transparent;")
        hdr_lbl = QLabel("QUICK ADD")
        hdr_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#888888', '#666666')};"
            " font-size: 13px; font-weight: 700; letter-spacing: 1px;"
        )
        ai_badge = QLabel("AI")
        ai_badge.setStyleSheet(
            "background: rgba(52,211,153,0.15); color: #34d399;"
            " border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: 700;"
            " border: 1px solid rgba(52,211,153,0.3);"
        )
        hdr.addWidget(robot_ic)
        hdr.addSpacing(6)
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        hdr.addWidget(ai_badge)
        layout.addLayout(hdr)

        sub_lbl = QLabel("Log food not in your plan\nDishy works out the macros")
        sub_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#555555', '#888888')}; font-size: 12px;"
        )
        layout.addWidget(sub_lbl)

        # Input row
        input_container = QWidget()
        input_container.setObjectName("dishy-input-box")
        input_container.setFixedHeight(42)
        input_container.setStyleSheet(
            f"QWidget#dishy-input-box {{ background: {theme_manager.c('#161616', '#f0f0f0')};"
            f" border-radius: 10px; border: 1px solid {theme_manager.c('#2a2a2a', '#e0e0e0')}; }}"
        )
        ic_layout = QHBoxLayout(input_container)
        ic_layout.setContentsMargins(12, 0, 6, 0)
        ic_layout.setSpacing(6)
        ic_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._quick_input = QLineEdit()
        self._quick_input.setPlaceholderText("e.g. 2 eggs, bowl of oats…")
        self._quick_input.setStyleSheet(
            f"background: transparent; border: none; padding: 0; font-size: 12px;"
            f" color: {theme_manager.c('#e8e8e8', '#1a1a1a')};"
        )
        send_btn = QPushButton()
        send_btn.setFixedSize(30, 30)
        send_btn.setIcon(qta.icon("fa5s.paper-plane", color="#ffffff"))
        send_btn.setIconSize(QSize(12, 12))
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(
            "QPushButton { background: #34d399; border-radius: 7px; border: none; }"
            "QPushButton:hover { background: #4ae3a8; }"
            "QPushButton:pressed { background: #2ac48a; }"
        )
        self._quick_add_btn = send_btn
        self._quick_input.returnPressed.connect(self._quick_search)
        send_btn.clicked.connect(self._quick_search)
        ic_layout.addWidget(self._quick_input, 1)
        ic_layout.addWidget(send_btn)
        layout.addWidget(input_container)

        # Status + result
        self._quick_status = QLabel("")
        self._quick_status.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#555555', '#888888')};"
            " font-size: 11px; font-style: italic;"
        )
        self._quick_status.setWordWrap(True)
        layout.addWidget(self._quick_status)

        self._quick_detail = self._build_quick_detail()
        self._quick_detail.setVisible(False)
        layout.addWidget(self._quick_detail)

        layout.addStretch(1)

        return card

    def _build_quick_detail(self) -> QWidget:
        """Inline result panel inside the Quick Add card."""
        panel = QWidget()
        panel.setObjectName("plan-card")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        name_row = QHBoxLayout()
        self._qd_name = QLabel("")
        self._qd_name.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#e0e0e0', '#1a1a1a')};"
            " font-size: 13px; font-weight: 700;"
        )
        self._qd_serving = QLabel("")
        self._qd_serving.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#555555', '#888888')}; font-size: 11px;"
        )
        name_row.addWidget(self._qd_name, 1)
        name_row.addWidget(self._qd_serving)
        layout.addLayout(name_row)

        self._qd_macros_row = QHBoxLayout()
        self._qd_macros_row.setSpacing(6)
        layout.addLayout(self._qd_macros_row)

        self._qd_note = QLabel("")
        self._qd_note.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#444444', '#999999')};"
            " font-size: 10px; font-style: italic;"
        )
        self._qd_note.setWordWrap(True)
        self._qd_note.setVisible(False)
        layout.addWidget(self._qd_note)

        add_row = QHBoxLayout()
        add_row.addStretch()
        add_btn = QPushButton("  + Add to today")
        add_btn.setFixedHeight(32)
        add_btn.setMinimumWidth(130)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            "QPushButton { background: #34d399; color: #0a0a0a; border-radius: 7px;"
            "  border: none; font-size: 12px; font-weight: 700; padding: 0 14px; }"
            "QPushButton:hover { background: #4ae3a8; }"
        )
        add_btn.clicked.connect(self._add_to_today)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        return panel

    # ── Recently logged ──────────────────────────────────────────────────────

    def _build_recent_foods_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(6)

        hdr = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(qta.icon("fa5s.history", color="#c084fc").pixmap(QSize(13, 13)))
        ic.setStyleSheet("background: transparent;")
        hdr_lbl = QLabel("RECENTLY LOGGED")
        hdr_lbl.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#888888', '#666666')};"
            " font-size: 13px; font-weight: 700; letter-spacing: 1px;"
        )
        re_badge = QLabel("Re-add →")
        re_badge.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#444444', '#aaaaaa')};"
            " font-size: 10px;"
        )
        hdr.addWidget(ic)
        hdr.addSpacing(6)
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        hdr.addWidget(re_badge)
        layout.addLayout(hdr)

        today_str = datetime.now().strftime("%Y-%m-%d")
        try:
            rows = self._db.conn.execute(
                "SELECT food_name, AVG(kcal) AS kcal, AVG(protein_g) AS protein_g,"
                " AVG(carbs_g) AS carbs_g, AVG(fat_g) AS fat_g,"
                " AVG(fiber_g) AS fiber_g, AVG(sugar_g) AS sugar_g"
                " FROM nutrition_logs"
                " WHERE log_date != ?"
                " GROUP BY lower(food_name)"
                " ORDER BY MAX(logged_at) DESC LIMIT 5",
                (today_str,),
            ).fetchall()
        except Exception:
            rows = []

        if not rows:
            empty = QLabel("No previous foods logged yet")
            empty.setStyleSheet(
                f"background: transparent; color: {theme_manager.c('#333333', '#bbbbbb')};"
                " font-size: 11px;"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty)
            layout.addStretch(1)
        else:
            for row in rows:
                layout.addWidget(self._build_recent_food_row(row))
            layout.addStretch(1)

        return card

    def _build_recent_food_row(self, entry) -> QWidget:
        row = QWidget()
        row.setObjectName("shopping-item")
        row.setFixedHeight(44)
        hl = QHBoxLayout(row)
        hl.setContentsMargins(12, 0, 8, 0)
        hl.setSpacing(8)
        hl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        name = entry["food_name"]
        name_lbl = QLabel(name[:28] + ("…" if len(name) > 28 else ""))
        name_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px;"
            f" color: {theme_manager.c('#c0c0c0', '#333333')};"
        )

        kcal_lbl = QLabel(f"{float(entry['kcal'] or 0):.0f} kcal")
        kcal_lbl.setStyleSheet(
            "background: transparent; color: #ff6b35; font-size: 10px; font-weight: 600;"
        )

        add_btn = QPushButton("+")
        add_btn.setFixedSize(28, 28)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            "QPushButton { background: rgba(192,132,252,0.15); color: #c084fc;"
            " border: 1px solid rgba(192,132,252,0.35); border-radius: 6px;"
            " font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background: rgba(192,132,252,0.3); }"
        )
        food_data = {k: entry[k] for k in ("food_name", "kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g")}
        add_btn.clicked.connect(lambda _, d=food_data: self._readd_food(d))

        hl.addWidget(name_lbl, 1)
        hl.addWidget(kcal_lbl)
        hl.addWidget(add_btn)
        return row

    def _readd_food(self, data: dict):
        today = datetime.now().strftime("%Y-%m-%d")
        self._db.add_nutrition_log(
            today,
            data.get("food_name", "Unknown")[:80],
            float(data.get("kcal", 0)),
            float(data.get("protein_g", 0)),
            float(data.get("carbs_g", 0)),
            float(data.get("fat_g", 0)),
            float(data.get("fiber_g", 0)),
            float(data.get("sugar_g", 0)),
        )
        self._refresh_log()

    # ── Actions ──────────────────────────────────────────────────────────────

    def _quick_search(self):
        query = self._quick_input.text().strip() if self._quick_input else ""
        if not query:
            return
        if self._quick_status:
            self._quick_status.setText("Asking Dishy…")
        if self._quick_detail:
            self._quick_detail.setVisible(False)
        if self._quick_add_btn:
            self._quick_add_btn.setEnabled(False)
        run_async(
            _claude.lookup_nutrition, query,
            on_result=self._on_quick_result,
            on_error=self._on_quick_error,
        )

    def _on_quick_result(self, data: dict):
        self._selected_food = data
        if self._quick_add_btn:
            self._quick_add_btn.setEnabled(True)

        name    = data.get("food_name", "Unknown")
        serving = data.get("serving", "")
        note    = data.get("note", "")
        kcal    = float(data.get("kcal",      0))
        prot    = float(data.get("protein_g", 0))
        carb    = float(data.get("carbs_g",   0))
        fat     = float(data.get("fat_g",     0))

        if self._qd_name:
            self._qd_name.setText(name[:40])
        if self._qd_serving:
            self._qd_serving.setText(serving)
        if self._qd_note:
            self._qd_note.setText(note)
            self._qd_note.setVisible(bool(note))

        if self._qd_macros_row:
            while self._qd_macros_row.count():
                item = self._qd_macros_row.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            for val, label, colour in [
                (kcal, "kcal",    "#ff6b35"),
                (prot, "protein", "#4fc3f7"),
                (carb, "carbs",   "#aed581"),
                (fat,  "fat",     "#ffb74d"),
            ]:
                r, g, b = int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)
                tile = QWidget()
                tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                tile.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                tile.setStyleSheet(
                    f"background: rgba({r},{g},{b},0.10); border-radius: 7px; border: none;"
                )
                tl = QVBoxLayout(tile)
                tl.setContentsMargins(4, 8, 4, 8)
                tl.setSpacing(2)
                v_lbl = QLabel(f"{round(val)}" if label == "kcal" else f"{round(val, 1)}")
                v_lbl.setStyleSheet(
                    f"color: {colour}; font-size: 16px; font-weight: 800;"
                    " background: transparent; border: none;"
                )
                l_lbl = QLabel(label)
                l_lbl.setStyleSheet(
                    f"color: {theme_manager.c('#666666', '#888888')}; font-size: 9px; font-weight: 600;"
                    " background: transparent; border: none;"
                )
                tl.addWidget(v_lbl, 0, Qt.AlignmentFlag.AlignCenter)
                tl.addWidget(l_lbl, 0, Qt.AlignmentFlag.AlignCenter)
                self._qd_macros_row.addWidget(tile, 1)

        if self._quick_status:
            self._quick_status.setText(
                f"Dishy estimates — {serving}" if serving else "Estimated values from Dishy"
            )
        if self._quick_detail:
            self._quick_detail.setVisible(True)

    def _on_quick_error(self, err: str):
        if self._quick_add_btn:
            self._quick_add_btn.setEnabled(True)
        msg = "Lookup failed — check your connection or API key"
        e = err.lower()
        if "credit" in e or "too low" in e:
            msg = "Anthropic credits low — top up at console.anthropic.com"
        elif "auth" in e or "401" in e:
            msg = "Invalid API key — check Settings"
        if self._quick_status:
            self._quick_status.setText(msg)

    def _add_to_today(self):
        if not self._selected_food:
            return
        data = self._selected_food
        today = datetime.now().strftime("%Y-%m-%d")
        self._db.add_nutrition_log(
            today,
            data.get("food_name", "Unknown")[:80],
            float(data.get("kcal",      0)),
            float(data.get("protein_g", 0)),
            float(data.get("carbs_g",   0)),
            float(data.get("fat_g",     0)),
            float(data.get("fiber_g",   0)),
            float(data.get("sugar_g",   0)),
        )
        if self._quick_input:
            self._quick_input.clear()
        if self._quick_detail:
            self._quick_detail.setVisible(False)
        added_name = data.get("food_name", "")
        if self._quick_status:
            self._quick_status.setText(f"Added '{added_name}' to today's log")
        self._selected_food = None
        self._refresh_log()

    # ── Refresh ──────────────────────────────────────────────────────────────

    def _refresh_log(self):
        if self._log_rows_layout is None:
            return

        # Clear existing rows (keep the trailing stretch)
        while self._log_rows_layout.count() > 1:
            item = self._log_rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Read directly from today's meal plan (not nutrition_logs)
        slots  = self._db.get_today_meal_plan_with_nutrition()
        totals = {k: 0.0 for k, *_ in MACRO_SPECS}

        for slot in slots:
            name = (slot.get("custom_name") or "").strip()
            if not name:
                continue
            dj    = json.loads(slot.get("data_json") or "{}")
            per_s = dj.get("nutrition_per_serving", {})
            entry = {
                "food_name": name,
                "kcal":      float(per_s.get("kcal",      0) or 0),
                "protein_g": float(per_s.get("protein_g", 0) or 0),
                "carbs_g":   float(per_s.get("carbs_g",   0) or 0),
                "fat_g":     float(per_s.get("fat_g",     0) or 0),
                "fiber_g":   float(per_s.get("fiber_g",   0) or 0),
                "sugar_g":   float(per_s.get("sugar_g",   0) or 0),
                "_meal_type": slot.get("meal_type", ""),
            }
            for k in totals:
                totals[k] += entry[k]
            self._log_rows_layout.insertWidget(
                self._log_rows_layout.count() - 1,
                self._build_log_row(entry),
            )

        for key, ring in self._rings.items():
            ring.set_value(totals[key])

        if self._empty_log_lbl:
            self._empty_log_lbl.setVisible(len(slots) == 0)

    def _build_log_row(self, entry) -> QWidget:
        row = QWidget()
        row.setObjectName("shopping-item")
        row.setMinimumHeight(68)
        hl = QHBoxLayout(row)
        hl.setContentsMargins(14, 10, 10, 10)
        hl.setSpacing(10)

        name = entry["food_name"]
        left_col = QVBoxLayout()
        left_col.setSpacing(6)
        left_col.setContentsMargins(0, 0, 0, 0)

        name_lbl = QLabel(name[:42] + ("…" if len(name) > 42 else ""))
        name_lbl.setStyleSheet(
            f"background: transparent; font-size: 13px; font-weight: 600;"
            f" color: {theme_manager.c('#d8d8d8', '#1a1a1a')};"
        )
        left_col.addWidget(name_lbl)

        # Full macro pills row
        pills_row = QHBoxLayout()
        pills_row.setSpacing(5)
        pills_row.setContentsMargins(0, 0, 0, 0)
        for val, lbl_text, colour in [
            (entry["kcal"],      "kcal", "#ff6b35"),
            (entry["protein_g"], "P",    "#4fc3f7"),
            (entry["carbs_g"],   "C",    "#aed581"),
            (entry["fat_g"],     "F",    "#ffb74d"),
        ]:
            r, g, b = int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)
            pill = QLabel(f"{float(val or 0):.0f}{lbl_text}")
            pill.setStyleSheet(
                f"background: rgba({r},{g},{b},0.13); color: {colour};"
                " border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: 700;"
            )
            pills_row.addWidget(pill)
        pills_row.addStretch()
        left_col.addLayout(pills_row)

        meal_type = entry.get("_meal_type", "")
        del_btn = QPushButton()
        del_btn.setObjectName("delete-btn")
        del_btn.setIcon(qta.icon("fa5s.times", color="#555555"))
        del_btn.setIconSize(QSize(9, 9))
        del_btn.setFixedSize(24, 24)
        del_btn.setToolTip("Remove from today's meal plan")
        del_btn.clicked.connect(
            lambda _, mt=meal_type: self._clear_meal_slot_for_today(mt)
        )

        hl.addLayout(left_col, 1)
        hl.addWidget(del_btn, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _clear_meal_slot_for_today(self, meal_type: str):
        """Remove a meal slot from today's plan (reflects instantly in Today's Log)."""
        from datetime import date, timedelta
        today      = date.today()
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        day_name   = today.strftime("%A")
        self._db.clear_meal_slot(week_start, day_name, meal_type)
        self._refresh_log()

    # ── Public API ───────────────────────────────────────────────────────────

    def showEvent(self, event):
        """Auto-refresh every time the user navigates to this page."""
        super().showEvent(event)
        self._rebuild_content()

    def refresh(self):
        self._rebuild_content()

    def apply_theme(self, _mode: str):
        self._rebuild_content()
