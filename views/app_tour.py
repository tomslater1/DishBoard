"""
AppTourOverlay - refreshed guided tour for first-run users.

Displayed as a floating overlay parented to MainWindow. The copy is curated
instead of generated live so the tour stays concise, visible, and coherent.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import qtawesome as qta

from utils.theme import manager as theme_manager


_STEPS: list[dict] = [
    {
        "id": "welcome",
        "view_index": None,
        "target_key": None,
        "arrow_side": None,
        "bubble_anchor": "center",
        "eyebrow": "Guided tour",
        "title": "DishBoard now opens like a full kitchen workflow.",
        "body": "This short walkthrough shows how planning, recipes, shopping, and Dishy now connect in one calmer flow.",
        "highlights": [
            "Home gives you the operational snapshot.",
            "Each section has a clearer role.",
            "Dishy can act across the whole system.",
        ],
        "cta": "Start on Home, then move wherever tonight's cooking problem actually lives.",
    },
    {
        "id": "sidebar",
        "view_index": 0,
        "target_key": "sidebar_nav_area",
        "arrow_side": "right",
        "bubble_anchor": "right",
        "eyebrow": "Navigation",
        "title": "The sidebar is the control rail for the whole app.",
        "body": "Main workspaces stay in the upper stack, while Help and Settings stay parked below for slower tasks.",
        "highlights": [
            "Home, Recipes, Planner, Nutrition.",
            "My Kitchen, Shopping, Dishy chat.",
            "Help and Settings stay at the base.",
        ],
        "cta": "Use it like an operations board, not a menu maze.",
    },
    {
        "id": "home",
        "view_index": 0,
        "target_key": "content_area",
        "arrow_side": None,
        "bubble_anchor": "content_top",
        "eyebrow": "Home",
        "title": "Home is now the daily readout, not just a landing page.",
        "body": "It pulls together today's plan, recipe momentum, quick actions, and the current state of shopping and nutrition.",
        "highlights": [
            "See today's meals immediately.",
            "Pick up recent recipe work faster.",
            "Jump into the next action without hunting.",
        ],
        "cta": "If you only open one screen first, open this one.",
    },
    {
        "id": "recipes",
        "view_index": 1,
        "target_key": "content_area",
        "arrow_side": None,
        "bubble_anchor": "content_top",
        "eyebrow": "Recipes",
        "title": "Recipes are the source of truth for what you cook.",
        "body": "Bring in recipes from the web, create your own, or let Dishy help shape them into something worth reusing.",
        "highlights": [
            "Import from URLs quickly.",
            "Save originals or Dishy-built versions.",
            "Keep nutrition and tags close to the recipe.",
        ],
        "cta": "A stronger library makes every later step faster.",
    },
    {
        "id": "meal_planner",
        "view_index": 2,
        "target_key": "content_area",
        "arrow_side": None,
        "bubble_anchor": "content_top",
        "eyebrow": "Meal planner",
        "title": "The planner is where the week turns into an actual schedule.",
        "body": "Build the grid yourself or let Dishy fill it with better defaults based on your profile, pantry, and saved recipes.",
        "highlights": [
            "Work day by day or fill the week.",
            "Keep leftovers and intent visible.",
            "Push the rest of the app from here.",
        ],
        "cta": "Once the planner is real, the rest of DishBoard can react properly.",
    },
    {
        "id": "nutrition",
        "view_index": 3,
        "target_key": "content_area",
        "arrow_side": None,
        "bubble_anchor": "content_top",
        "eyebrow": "Nutrition",
        "title": "Nutrition reads like a dashboard now, not a chore log.",
        "body": "Planned intake, logged intake, coaching, and weekly trends sit together so you can understand the day without extra admin.",
        "highlights": [
            "Macro rings show the current day.",
            "Quick add covers real consumption.",
            "Weekly trends stay visible in context.",
        ],
        "cta": "Treat it like feedback on the plan, not a separate system.",
    },
    {
        "id": "my_kitchen",
        "view_index": 4,
        "target_key": "content_area",
        "arrow_side": None,
        "bubble_anchor": "content_top",
        "eyebrow": "My Kitchen",
        "title": "My Kitchen is the stock picture DishBoard plans against.",
        "body": "Pantry, fridge, and freezer items live here so recipe and planning decisions can react to what is already in the house.",
        "highlights": [
            "Track where ingredients actually live.",
            "Catch low-stock and use-up moments faster.",
            "Give Dishy better pantry context.",
        ],
        "cta": "Even a partial kitchen list makes planning smarter.",
    },
    {
        "id": "shopping",
        "view_index": 5,
        "target_key": "content_area",
        "arrow_side": None,
        "bubble_anchor": "content_top",
        "eyebrow": "Shopping",
        "title": "Shopping now feels downstream from the plan, which is exactly right.",
        "body": "Generate a working grocery list from the week, keep duplicates consolidated, and move bought items back into the kitchen flow.",
        "highlights": [
            "Build lists from the planner.",
            "Keep categories cleaner and easier to shop.",
            "Close the loop back into My Kitchen.",
        ],
        "cta": "This section works best after the planner has shape.",
    },
    {
        "id": "dishy",
        "view_index": 6,
        "target_key": "content_area",
        "arrow_side": None,
        "bubble_anchor": "content_top",
        "eyebrow": "Dishy",
        "title": "Dishy is the action layer across the whole product.",
        "body": "Use the full chat when you want to plan, build, search, or clean up multiple parts of the app without bouncing between screens.",
        "highlights": [
            "Ask for recipes or a full week plan.",
            "Let Dishy update lists and slots.",
            "Keep longer cooking conversations in one place.",
        ],
        "cta": "Open this when the problem spans more than one page.",
    },
    {
        "id": "settings",
        "view_index": None,
        "target_key": "help_settings_area",
        "arrow_side": "top",
        "bubble_anchor": "bottom_right",
        "eyebrow": "Help and settings",
        "title": "The lower sidebar handles slower maintenance work.",
        "body": "Settings is where you refine profile, sync, and account behaviour. Help is where the product explains itself when you want deeper guidance.",
        "highlights": [
            "Adjust profile and app behaviour.",
            "Check data and sync status.",
            "Use Help for a slower walkthrough.",
        ],
        "cta": "Come here when you are tuning the system, not cooking inside it.",
    },
    {
        "id": "complete",
        "view_index": None,
        "target_key": None,
        "arrow_side": None,
        "bubble_anchor": "center",
        "eyebrow": "Ready",
        "title": "You have the full map now.",
        "body": "The cleanest next move is usually one of three things: add a recipe, shape the week, or ask Dishy to do the first heavy lift for you.",
        "highlights": [
            "Save a recipe you actually use.",
            "Block out the next few dinners.",
            "Ask Dishy for the first draft.",
        ],
        "cta": "The app feels best once something real is on the planner.",
    },
]


class _TourBubble(QWidget):
    next_clicked = Signal()
    back_clicked = Signal()
    skip_clicked = Signal()

    BUBBLE_W = 520

    def __init__(self, total_steps: int, parent: QWidget):
        super().__init__(parent)
        self._total = total_steps
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._setup_ui()
        self.apply_theme(theme_manager.mode)

    def _setup_ui(self) -> None:
        self.setFixedWidth(self.BUBBLE_W)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._card = QWidget(self)
        self._card.setObjectName("tour-bubble-card")
        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)

        self._eyebrow_lbl = QLabel()
        self._eyebrow_lbl.setObjectName("tour-eyebrow")
        top.addWidget(self._eyebrow_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        top.addStretch()

        self._step_lbl = QLabel()
        self._step_lbl.setObjectName("tour-step")
        top.addWidget(self._step_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(top)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)

        self._avatar = QLabel()
        self._avatar.setFixedSize(42, 42)
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar.setStyleSheet("background: transparent;")
        self._avatar.setPixmap(qta.icon("fa5s.robot", color="#ff6b35").pixmap(QSize(20, 20)))
        title_row.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignTop)

        self._title_lbl = QLabel()
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setFixedWidth(self.BUBBLE_W - 102)
        self._title_lbl.setObjectName("tour-title")
        title_row.addWidget(self._title_lbl, 1)
        layout.addLayout(title_row)

        self._body_lbl = QLabel()
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setFixedWidth(self.BUBBLE_W - 48)
        self._body_lbl.setObjectName("tour-body")
        layout.addWidget(self._body_lbl)

        self._highlight_rows: list[QLabel] = []
        for _ in range(3):
            row = QLabel()
            row.setWordWrap(True)
            row.setFixedWidth(self.BUBBLE_W - 48)
            row.setObjectName("tour-highlight")
            self._highlight_rows.append(row)
            layout.addWidget(row)

        self._cta_box = QLabel()
        self._cta_box.setWordWrap(True)
        self._cta_box.setFixedWidth(self.BUBBLE_W - 48)
        self._cta_box.setObjectName("tour-cta")
        layout.addWidget(self._cta_box)

        dots_row = QHBoxLayout()
        dots_row.setContentsMargins(0, 2, 0, 0)
        dots_row.setSpacing(6)
        self._dots: list[QLabel] = []
        for _ in range(self._total):
            dot = QLabel()
            dot.setFixedSize(18, 6)
            dot.setStyleSheet("border-radius: 3px;")
            self._dots.append(dot)
            dots_row.addWidget(dot)
        dots_row.addStretch()
        layout.addLayout(dots_row)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 4, 0, 0)
        buttons.setSpacing(10)

        self._skip_btn = QPushButton("Close tour")
        self._skip_btn.clicked.connect(self.skip_clicked)
        buttons.addWidget(self._skip_btn)

        buttons.addStretch()

        self._back_btn = QPushButton("Back")
        self._back_btn.clicked.connect(self.back_clicked)
        buttons.addWidget(self._back_btn)

        self._next_btn = QPushButton("Next")
        self._next_btn.clicked.connect(self.next_clicked)
        buttons.addWidget(self._next_btn)

        layout.addLayout(buttons)
        outer.addWidget(self._card)

    def set_step(self, idx: int, step: dict, is_last: bool) -> None:
        self._eyebrow_lbl.setText(step["eyebrow"])
        self._step_lbl.setText(f"Step {idx + 1} of {self._total}")
        self._title_lbl.setText(step["title"])
        self._body_lbl.setText(step["body"])

        highlights = step.get("highlights") or []
        for row_idx, label in enumerate(self._highlight_rows):
            if row_idx < len(highlights):
                label.setText(f"- {highlights[row_idx]}")
                label.setVisible(True)
            else:
                label.setVisible(False)

        self._cta_box.setText(f"Try this next: {step['cta']}")
        self._back_btn.setVisible(idx > 0)
        self._next_btn.setText("Start cooking" if is_last else "Next")

        for dot_idx, dot in enumerate(self._dots):
            if dot_idx < idx:
                dot.setProperty("state", "done")
            elif dot_idx == idx:
                dot.setProperty("state", "active")
            else:
                dot.setProperty("state", "idle")
            self._apply_dot_style(dot)

        self.adjustSize()

    def _apply_dot_style(self, dot: QLabel) -> None:
        state = str(dot.property("state") or "idle")
        if state == "active":
            color = "#ff6b35"
        elif state == "done":
            color = "rgba(255,107,53,0.34)"
        else:
            color = theme_manager.c("#2b3036", "#d8ccbf")
        dot.setStyleSheet(f"background: {color}; border-radius: 3px;")

    def apply_theme(self, mode: str) -> None:
        dark = mode == "dark"
        card_bg = "rgba(17,19,23,0.98)" if dark else "rgba(255,250,244,0.98)"
        border = "rgba(255,107,53,0.28)" if dark else "rgba(255,107,53,0.34)"
        title_col = theme_manager.c("#f2eee8", "#181510")
        body_col = theme_manager.c("#c6beb5", "#6d645b")
        hint_bg = "rgba(255,107,53,0.10)"
        hint_border = "rgba(255,107,53,0.22)"

        self._card.setStyleSheet(
            f"QWidget#tour-bubble-card {{ background: {card_bg}; border: 1px solid {border}; border-radius: 20px; }}"
        )
        self._eyebrow_lbl.setStyleSheet(
            "background: rgba(255,107,53,0.14); color: #ff6b35; border: 1px solid rgba(255,107,53,0.28);"
            "border-radius: 11px; padding: 4px 10px; font-size: 11px; font-weight: 700;"
        )
        self._step_lbl.setStyleSheet(
            f"color: {theme_manager.c('#8c867e', '#867c72')}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        self._title_lbl.setStyleSheet(
            f"color: {title_col}; font-size: 22px; font-weight: 800; line-height: 1.15; background: transparent;"
        )
        self._body_lbl.setStyleSheet(
            f"color: {body_col}; font-size: 13px; line-height: 1.55; background: transparent;"
        )
        for label in self._highlight_rows:
            label.setStyleSheet(
                f"color: {title_col}; font-size: 12px; font-weight: 600; line-height: 1.5; background: transparent;"
            )
        self._cta_box.setStyleSheet(
            f"background: {hint_bg}; color: {title_col}; border: 1px solid {hint_border};"
            "border-radius: 14px; padding: 10px 12px; font-size: 12px; font-weight: 600; line-height: 1.5;"
        )
        self._skip_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #ff6b35; border: none; font-size: 12px; font-weight: 700; padding: 4px 2px; }"
            "QPushButton:hover { color: #ff7a48; }"
        )
        self._back_btn.setStyleSheet(
            f"QPushButton {{ background: {theme_manager.c('#13161a', '#f4ede4')}; color: {theme_manager.c('#a39d95', '#71685d')};"
            f" border: 1px solid {theme_manager.c('#2b3036', '#ddd2c5')}; border-radius: 10px; padding: 8px 18px; font-size: 13px; font-weight: 600; }}"
            "QPushButton:hover { border-color: rgba(255,107,53,0.28); color: #ff6b35; }"
        )
        self._next_btn.setStyleSheet(
            "QPushButton { background: #ff6b35; color: #fff7f1; border: 1px solid rgba(255,107,53,0.42);"
            " border-radius: 10px; padding: 8px 20px; font-size: 13px; font-weight: 700; }"
            "QPushButton:hover { background: #ff7a48; border-color: rgba(255,107,53,0.62); }"
        )
        for dot in self._dots:
            self._apply_dot_style(dot)


class AppTourOverlay(QWidget):
    finished = Signal()

    def __init__(self, main_window, db):
        super().__init__(main_window)
        self._mw = main_window
        self._db = db
        self._step_idx = 0
        self._spotlight_rect: QRect | None = None
        self._arrow_side: str | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

        self._bubble = _TourBubble(len(_STEPS), self)
        self._bubble.next_clicked.connect(self._on_next)
        self._bubble.back_clicked.connect(self._on_back)
        self._bubble.skip_clicked.connect(self._on_skip)

        theme_manager.theme_changed.connect(self.apply_theme)
        self.apply_theme(theme_manager.mode)

    def start(self) -> None:
        self._resize_to_parent()
        self.show()
        self.raise_()
        self._go_to_step(0)

    def _go_to_step(self, idx: int) -> None:
        if idx < 0 or idx >= len(_STEPS):
            return
        self._step_idx = idx
        step = _STEPS[idx]

        if step["view_index"] is not None:
            try:
                self._mw._on_nav_clicked(step["view_index"])
            except Exception:
                pass

        target_key = step.get("target_key")
        self._spotlight_rect = self._get_spotlight_rect(target_key) if target_key else None
        self._arrow_side = step.get("arrow_side")

        self._bubble.set_step(idx, step, idx == len(_STEPS) - 1)
        self._position_bubble(step["bubble_anchor"])
        self.update()

    def _on_next(self) -> None:
        if self._step_idx >= len(_STEPS) - 1:
            self.finished.emit()
            self.hide()
            return
        self._go_to_step(self._step_idx + 1)

    def _on_back(self) -> None:
        if self._step_idx > 0:
            self._go_to_step(self._step_idx - 1)

    def _on_skip(self) -> None:
        self.finished.emit()
        self.hide()

    def _get_spotlight_rect(self, target_key: str | None) -> QRect | None:
        if not target_key:
            return None
        try:
            widget = self._mw.tour_targets.get(target_key)
            if widget is None or not widget.isVisible():
                return None
            top_left = widget.mapTo(self, QPoint(0, 0))
            return QRect(top_left.x(), top_left.y(), widget.width(), widget.height())
        except Exception:
            return None

    def _position_bubble(self, anchor: str) -> None:
        self._bubble.adjustSize()

        width = self.width()
        height = self.height()
        bubble_w = self._bubble.width()
        bubble_h = self._bubble.height()
        margin = 28

        if anchor == "center":
            x = (width - bubble_w) // 2
            y = (height - bubble_h) // 2
        elif anchor == "right":
            spot = self._spotlight_rect
            if spot:
                x = min(spot.right() + margin, width - bubble_w - margin)
                y = min(max(spot.top(), margin), height - bubble_h - margin)
            else:
                x = width - bubble_w - margin
                y = margin
        elif anchor == "content_top":
            spot = self._spotlight_rect
            if spot:
                x = max(spot.left() + margin, spot.right() - bubble_w - margin)
                y = min(spot.top() + margin + 18, height - bubble_h - margin)
            else:
                x = width - bubble_w - margin
                y = margin
        elif anchor == "bottom_right":
            x = width - bubble_w - margin
            y = height - bubble_h - margin - 34
        else:
            x = (width - bubble_w) // 2
            y = height - bubble_h - margin

        self._bubble.move(max(0, x), max(0, y))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        overlay = QColor(0, 0, 0, 168 if theme_manager.mode == "dark" else 140)

        if self._spotlight_rect and not self._spotlight_rect.isEmpty():
            pad = 14
            spot = self._spotlight_rect.adjusted(-pad, -pad, pad, pad)

            full = QPainterPath()
            full.addRect(QRectF(self.rect()))

            hole = QPainterPath()
            hole.addRoundedRect(QRectF(spot), 12, 12)
            painter.fillPath(full.subtracted(hole), overlay)

            painter.setPen(QPen(QColor(255, 107, 53, 230), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(spot.adjusted(-2, -2, 2, 2)), 14, 14)

            if self._arrow_side:
                self._paint_arrow(painter, spot)
        else:
            painter.fillRect(self.rect(), overlay)

        painter.end()

    def _paint_arrow(self, painter: QPainter, spot: QRect) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        fill = QColor(255, 107, 53, 220)
        size = 10

        if self._arrow_side == "right":
            cx, cy = spot.left() - 1, spot.center().y()
            path = QPainterPath()
            path.moveTo(cx, cy)
            path.lineTo(cx - 18, cy - size)
            path.lineTo(cx - 18, cy + size)
            path.closeSubpath()
            painter.fillPath(path, fill)
        elif self._arrow_side == "left":
            cx, cy = spot.right() + 1, spot.center().y()
            path = QPainterPath()
            path.moveTo(cx, cy)
            path.lineTo(cx + 18, cy - size)
            path.lineTo(cx + 18, cy + size)
            path.closeSubpath()
            painter.fillPath(path, fill)
        elif self._arrow_side == "top":
            cx = spot.center().x()
            cy = spot.bottom() + 1
            path = QPainterPath()
            path.moveTo(cx, cy)
            path.lineTo(cx - size, cy + 18)
            path.lineTo(cx + size, cy + 18)
            path.closeSubpath()
            painter.fillPath(path, fill)
        elif self._arrow_side == "bottom":
            cx = spot.center().x()
            cy = spot.top() - 1
            path = QPainterPath()
            path.moveTo(cx, cy)
            path.lineTo(cx - size, cy - 18)
            path.lineTo(cx + size, cy - 18)
            path.closeSubpath()
            painter.fillPath(path, fill)

    def _resize_to_parent(self) -> None:
        if self._mw:
            self.resize(self._mw.width(), self._mw.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        step = _STEPS[self._step_idx]
        target_key = step.get("target_key")
        self._spotlight_rect = self._get_spotlight_rect(target_key) if target_key else None
        self._position_bubble(step["bubble_anchor"])
        self.update()

    def apply_theme(self, mode: str) -> None:
        self._bubble.apply_theme(mode)
        self.update()
