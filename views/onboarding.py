"""
OnboardingWizard — full-screen first-run profile setup.

Displayed as index 2 of the root QStackedWidget so the main app is
never visible in the background.  Emits `finished` when done or skipped.

4 steps:
  1. About You         — name, household size
  2. Dietary Needs     — requirements + allergens
  3. Your Lifestyle    — scenario chips
  4. Food Preferences  — cuisines, cooking skill, weekly goal
"""
from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFrame,
)

from models.database import Database
from utils.theme import manager


# ── Data definitions ──────────────────────────────────────────────────────────

_DIETARY = [
    ("vegetarian",  "Vegetarian"),
    ("vegan",       "Vegan"),
    ("gluten_free", "Gluten-Free"),
    ("dairy_free",  "Dairy-Free"),
    ("nut_free",    "Nut-Free"),
    ("halal",       "Halal"),
    ("kosher",      "Kosher"),
    ("keto",        "Keto / Low-carb"),
    ("paleo",       "Paleo"),
    ("low_fodmap",  "Low-FODMAP"),
]

_ALLERGENS = [
    ("shellfish", "Shellfish"),
    ("eggs",      "Eggs"),
    ("soy",       "Soy"),
    ("peanuts",   "Peanuts"),
    ("tree_nuts", "Tree Nuts"),
    ("fish",      "Fish"),
    ("wheat",     "Wheat"),
    ("sesame",    "Sesame"),
]

_SCENARIOS = [
    ("fa5s.layer-group",  "meal_prep",         "I meal prep in batches"),
    ("fa5s.child",        "cooking_for_kids",  "I cook for kids"),
    ("fa5s.heartbeat",    "weight_loss",        "I'm focused on weight loss"),
    ("fa5s.dumbbell",     "muscle_building",   "I'm building muscle"),
    ("fa5s.bolt",         "quick_meals",       "I need quick weeknight meals"),
    ("fa5s.globe",        "adventurous",       "I love trying new cuisines"),
    ("fa5s.piggy-bank",   "budget_cooking",    "I cook on a budget"),
    ("fa5s.leaf",         "healthy_eating",    "I prefer healthy whole foods"),
    ("fa5s.book-open",    "learning_to_cook",  "I'm learning to cook"),
    ("fa5s.utensils",     "dinner_parties",    "I host dinner parties"),
]

_CUISINES = [
    ("italian",        "Italian"),
    ("asian",          "Asian"),
    ("mexican",        "Mexican"),
    ("indian",         "Indian"),
    ("mediterranean",  "Mediterranean"),
    ("american",       "American"),
    ("middle_eastern", "Middle Eastern"),
    ("french",         "French"),
    ("japanese",       "Japanese"),
    ("thai",           "Thai"),
    ("greek",          "Greek"),
    ("spanish",        "Spanish"),
    ("korean",         "Korean"),
    ("british",        "British"),
]

_HOUSEHOLD = [
    ("just_me",    "Just me"),
    ("2_people",   "2 people"),
    ("3_4_people", "3–4 people"),
    ("5_plus",     "5+ people"),
]

_SKILL = [
    ("beginner",     "Beginner"),
    ("intermediate", "Intermediate"),
    ("advanced",     "Advanced"),
]

_GOAL = [
    ("1_2",    "1–2 meals/week"),
    ("3_4",    "3–4 meals/week"),
    ("5_plus", "5+ meals/week"),
]

STEP_TITLES = [
    "About you",
    "Dietary needs",
    "Your cooking style",
    "Your preferences",
]


# ── Style helpers ─────────────────────────────────────────────────────────────

def _chip_on() -> str:
    return (
        "QPushButton {"
        " background: rgba(255,107,53,0.15); color: #ff6b35;"
        " border: 1.5px solid #ff6b35; border-radius: 16px;"
        " font-size: 13px; padding: 6px 16px;"
        "}"
    )


def _chip_off() -> str:
    return (
        f"QPushButton {{"
        f" background: {manager.c('rgba(255,255,255,0.05)', 'rgba(0,0,0,0.05)')};"
        f" color: {manager.c('#999', '#666')};"
        f" border: 1px solid {manager.c('#333', '#ddd')};"
        " border-radius: 16px; font-size: 13px; padding: 6px 16px;"
        f"}}"
        f"QPushButton:hover {{"
        f" border-color: rgba(255,107,53,0.6);"
        f" color: {manager.c('#ddd', '#333')};"
        "}"
    )


def _sel_on() -> str:
    return (
        "QPushButton {"
        " background: rgba(255,107,53,0.12); color: #ff6b35;"
        " border: 2px solid #ff6b35; border-radius: 10px;"
        " font-size: 14px; font-weight: 600; padding: 10px 22px;"
        "}"
    )


def _sel_off() -> str:
    return (
        f"QPushButton {{"
        f" background: {manager.c('rgba(255,255,255,0.04)', 'rgba(0,0,0,0.04)')};"
        f" color: {manager.c('#999', '#666')};"
        f" border: 1px solid {manager.c('#333', '#ddd')};"
        " border-radius: 10px; font-size: 14px; padding: 10px 22px;"
        f"}}"
        f"QPushButton:hover {{"
        f" border-color: rgba(255,107,53,0.5);"
        f" color: {manager.c('#ddd', '#333')};"
        "}"
    )


def _sub_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: 11px; font-weight: 700; letter-spacing: 1px;"
        f" color: {manager.c('#555', '#aaa')}; background: transparent;"
        f" text-transform: uppercase;"
    )
    return lbl


def _sep_line() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(
        f"color: {manager.c('#222', '#e0e0e0')};"
        f" background: {manager.c('#222', '#e0e0e0')};"
        " border: none; max-height: 1px;"
    )
    return sep


def _chip_rows(options: list[tuple], saved_set: set,
               per_row: int = 5) -> tuple[QWidget, dict]:
    """Build chips in rows of `per_row`. Returns (container, {key: button})."""
    btns: dict[str, QPushButton] = {}
    container = QWidget()
    container.setStyleSheet("background: transparent;")
    vlay = QVBoxLayout(container)
    vlay.setContentsMargins(0, 0, 0, 0)
    vlay.setSpacing(8)

    for row_start in range(0, len(options), per_row):
        row_items = options[row_start: row_start + per_row]
        row_w = QWidget()
        row_w.setStyleSheet("background: transparent;")
        row_l = QHBoxLayout(row_w)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.setSpacing(8)
        row_l.setAlignment(Qt.AlignmentFlag.AlignLeft)
        for key, label in row_items:
            active = key in saved_set
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(active)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_chip_on() if active else _chip_off())
            btn.toggled.connect(
                lambda checked, b=btn: b.setStyleSheet(_chip_on() if checked else _chip_off())
            )
            row_l.addWidget(btn)
            btns[key] = btn
        vlay.addWidget(row_w)
    return container, btns


def _selector_row(options: list[tuple], saved: str) -> tuple[QWidget, dict]:
    """Exclusive row of selector buttons, all same size, centered."""
    btns: dict[str, QPushButton] = {}
    container = QWidget()
    container.setStyleSheet("background: transparent;")
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(12)
    row.setAlignment(Qt.AlignmentFlag.AlignLeft)

    def _select(chosen: str):
        for k, b in btns.items():
            b.setStyleSheet(_sel_on() if k == chosen else _sel_off())

    for key, label in options:
        btn = QPushButton(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(_sel_on() if key == saved else _sel_off())
        btn.clicked.connect(lambda _, k=key: _select(k))
        row.addWidget(btn)
        btns[key] = btn
    return container, btns


# ── Onboarding wizard ─────────────────────────────────────────────────────────

class OnboardingWizard(QWidget):
    """Full-screen onboarding flow. Add to root QStackedWidget at index 2."""

    finished = Signal()

    STEPS = 4

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self._db = db
        self._step = 0
        self.setStyleSheet(
            f"background: {manager.c('#090909', '#f0f0f0')};"
        )
        self._build_ui()
        self._go_to(0)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar (progress + title) ────────────────────────────────────────
        top_bar = QWidget()
        top_bar.setFixedHeight(72)
        top_bar.setStyleSheet(
            f"background: {manager.c('#0d0d0d', '#fff')};"
            f" border-bottom: 1px solid {manager.c('#1e1e1e', '#e0e0e0')};"
        )
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)

        top_inner = QWidget()
        top_inner.setFixedWidth(600)
        top_inner.setStyleSheet("background: transparent;")
        top_inner_layout = QHBoxLayout(top_inner)
        top_inner_layout.setContentsMargins(0, 0, 0, 0)
        top_inner_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("fa5s.utensils", color="#ff6b35").pixmap(QSize(18, 18)))
        icon_lbl.setStyleSheet("background: transparent;")
        top_inner_layout.addWidget(icon_lbl)

        self._title_lbl = QLabel("About you")
        self._title_lbl.setStyleSheet(
            f"font-size: 17px; font-weight: 700;"
            f" color: {manager.c('#f0f0f0', '#1a1a1a')}; background: transparent;"
        )
        top_inner_layout.addWidget(self._title_lbl)
        top_inner_layout.addStretch()

        # Progress dots
        self._dots: list[QLabel] = []
        for i in range(self.STEPS):
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet("border-radius: 5px;")
            self._dots.append(dot)
            top_inner_layout.addWidget(dot)
            top_inner_layout.addSpacing(4)

        top_layout.addStretch()
        top_layout.addWidget(top_inner)
        top_layout.addStretch()
        root.addWidget(top_bar)

        # ── Scrollable centre column ──────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            f"QScrollBar::handle:vertical {{ background: {manager.c('#2a2a2a', '#ccc')};"
            " border-radius: 2px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_outer = QVBoxLayout(scroll_content)
        scroll_outer.setContentsMargins(0, 0, 0, 0)
        scroll_outer.setSpacing(0)

        # Centre the 600px column
        centre_row = QHBoxLayout()
        centre_row.setContentsMargins(0, 0, 0, 0)
        centre_row.addStretch()

        self._col = QWidget()
        self._col.setFixedWidth(600)
        self._col.setStyleSheet("background: transparent;")
        self._col_layout = QVBoxLayout(self._col)
        self._col_layout.setContentsMargins(0, 48, 0, 48)
        self._col_layout.setSpacing(0)

        # Build steps and add to col
        self._step_widgets = [
            self._build_step1(),
            self._build_step2(),
            self._build_step3(),
            self._build_step4(),
        ]
        for sw in self._step_widgets:
            sw.setVisible(False)
            self._col_layout.addWidget(sw)

        centre_row.addWidget(self._col)
        centre_row.addStretch()
        scroll_outer.addLayout(centre_row)
        scroll_outer.addStretch()

        scroll.setWidget(scroll_content)
        root.addWidget(scroll, 1)

        # ── Bottom bar (back / skip / next) ───────────────────────────────────
        bot_bar = QWidget()
        bot_bar.setFixedHeight(72)
        bot_bar.setStyleSheet(
            f"background: {manager.c('#0d0d0d', '#fff')};"
            f" border-top: 1px solid {manager.c('#1e1e1e', '#e0e0e0')};"
        )
        bot_layout = QHBoxLayout(bot_bar)
        bot_layout.setContentsMargins(0, 0, 0, 0)

        bot_inner = QWidget()
        bot_inner.setFixedWidth(600)
        bot_inner.setStyleSheet("background: transparent;")
        bot_inner_layout = QHBoxLayout(bot_inner)
        bot_inner_layout.setContentsMargins(0, 0, 0, 0)
        bot_inner_layout.setSpacing(12)

        self._back_btn = QPushButton("← Back")
        self._back_btn.setFixedHeight(40)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none;"
            f" color: {manager.c('#666', '#888')}; font-size: 14px; }}"
            "QPushButton:hover { color: #ff6b35; }"
        )
        self._back_btn.clicked.connect(self._on_back)
        bot_inner_layout.addWidget(self._back_btn)
        bot_inner_layout.addStretch()

        self._skip_btn = QPushButton("Skip for now")
        self._skip_btn.setFixedHeight(40)
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none;"
            f" color: {manager.c('#555', '#aaa')}; font-size: 14px; }}"
            "QPushButton:hover { color: #ff6b35; }"
        )
        self._skip_btn.clicked.connect(self._on_skip)
        bot_inner_layout.addWidget(self._skip_btn)
        bot_inner_layout.addSpacing(16)

        self._next_btn = QPushButton("Next  →")
        self._next_btn.setFixedSize(160, 44)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet(
            "QPushButton {"
            " background: #ff6b35; color: #fff;"
            " border-radius: 10px; font-size: 15px; font-weight: 700; border: none;"
            "}"
            "QPushButton:hover { background: #e05a28; }"
        )
        self._next_btn.clicked.connect(self._on_next)
        bot_inner_layout.addWidget(self._next_btn)

        bot_layout.addStretch()
        bot_layout.addWidget(bot_inner)
        bot_layout.addStretch()
        root.addWidget(bot_bar)

    # ── Step builders ─────────────────────────────────────────────────────────

    def _heading(self, emoji: str, title: str, subtitle: str = "") -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(w)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(6)

        emoji_lbl = QLabel(emoji)
        emoji_lbl.setStyleSheet("font-size: 32px; background: transparent;")
        vl.addWidget(emoji_lbl)

        h = QLabel(title)
        h.setStyleSheet(
            f"font-size: 26px; font-weight: 800;"
            f" color: {manager.c('#f0f0f0', '#1a1a1a')}; background: transparent;"
        )
        vl.addWidget(h)

        if subtitle:
            s = QLabel(subtitle)
            s.setWordWrap(True)
            s.setStyleSheet(
                f"font-size: 14px; color: {manager.c('#666', '#888')}; background: transparent;"
            )
            vl.addWidget(s)
        return w

    def _build_step1(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(w)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        vl.addWidget(self._heading("👋", "Welcome to DishBoard",
                                   "Let's personalise your experience. Dishy will use this to tailor every suggestion."))
        vl.addSpacing(36)

        vl.addWidget(_sub_label("Your name"))
        vl.addSpacing(10)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Alex")
        self._name_input.setFixedHeight(48)
        self._name_input.setStyleSheet(
            f"QLineEdit {{"
            f" background: {manager.c('#1a1a1a', '#fff')};"
            f" color: {manager.c('#f0f0f0', '#1a1a1a')};"
            f" border: 1px solid {manager.c('#333', '#ddd')};"
            " border-radius: 10px; padding: 0 16px; font-size: 15px;"
            f"}}"
            "QLineEdit:focus { border-color: #ff6b35; }"
        )
        vl.addWidget(self._name_input)

        vl.addSpacing(32)
        vl.addWidget(_sep_line())
        vl.addSpacing(28)

        vl.addWidget(_sub_label("You're cooking for"))
        vl.addSpacing(12)
        hh_w, self._household_btns = _selector_row(_HOUSEHOLD, "")
        vl.addWidget(hh_w)

        vl.addStretch()
        return w

    def _build_step2(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(w)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        vl.addWidget(self._heading("🥗", "Dietary needs",
                                   "Select everything that applies — Dishy will always respect these."))
        vl.addSpacing(32)

        vl.addWidget(_sub_label("Dietary requirements"))
        vl.addSpacing(12)
        diet_w, self._dietary_btns = _chip_rows(_DIETARY, set(), per_row=5)
        vl.addWidget(diet_w)

        vl.addSpacing(28)
        vl.addWidget(_sep_line())
        vl.addSpacing(24)

        vl.addWidget(_sub_label("Allergens to always avoid"))
        vl.addSpacing(12)
        allergen_w, self._allergen_btns = _chip_rows(_ALLERGENS, set(), per_row=5)
        vl.addWidget(allergen_w)

        vl.addStretch()
        return w

    def _build_step3(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(w)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        vl.addWidget(self._heading("🍳", "Your cooking style",
                                   "Tick everything that sounds like you."))
        vl.addSpacing(28)

        import qtawesome as qta
        self._scenario_btns: dict[str, QPushButton] = {}
        for icon_name, key, label in _SCENARIOS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(14)

            icon_lbl = QLabel()
            icon_lbl.setPixmap(
                qta.icon(icon_name, color=manager.c("#555", "#bbb")).pixmap(QSize(16, 16))
            )
            icon_lbl.setFixedSize(24, 24)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet("background: transparent;")
            row.addWidget(icon_lbl)

            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(38)
            btn.setStyleSheet(_chip_off())
            btn.toggled.connect(
                lambda checked, b=btn: b.setStyleSheet(_chip_on() if checked else _chip_off())
            )
            row.addWidget(btn)
            row.addStretch()
            self._scenario_btns[key] = btn
            vl.addLayout(row)
            vl.addSpacing(6)

        vl.addStretch()
        return w

    def _build_step4(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(w)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        vl.addWidget(self._heading("🌍", "Your preferences",
                                   "Help Dishy recommend the perfect meals for you."))
        vl.addSpacing(28)

        vl.addWidget(_sub_label("Favourite cuisines"))
        vl.addSpacing(12)
        cuisine_w, self._cuisine_btns = _chip_rows(_CUISINES, set(), per_row=5)
        vl.addWidget(cuisine_w)

        vl.addSpacing(28)
        vl.addWidget(_sep_line())
        vl.addSpacing(24)

        vl.addWidget(_sub_label("Cooking skill level"))
        vl.addSpacing(12)
        skill_w, self._skill_btns = _selector_row(_SKILL, "")
        vl.addWidget(skill_w)

        vl.addSpacing(28)
        vl.addWidget(_sep_line())
        vl.addSpacing(24)

        vl.addWidget(_sub_label("Weekly home cooking goal"))
        vl.addSpacing(12)
        goal_w, self._goal_btns = _selector_row(_GOAL, "")
        vl.addWidget(goal_w)

        vl.addStretch()
        return w

    # ── Navigation ────────────────────────────────────────────────────────────

    def _go_to(self, step: int):
        self._step = step

        for i, sw in enumerate(self._step_widgets):
            sw.setVisible(i == step)

        self._title_lbl.setText(STEP_TITLES[step])
        self._back_btn.setVisible(step > 0)

        if step == self.STEPS - 1:
            self._next_btn.setText("Done  ✓")
            self._skip_btn.setVisible(False)
        else:
            self._next_btn.setText("Next  →")
            self._skip_btn.setVisible(True)

        for i, dot in enumerate(self._dots):
            if i < step:
                dot.setStyleSheet(
                    "border-radius: 5px; background: rgba(255,107,53,0.4);"
                )
            elif i == step:
                dot.setStyleSheet(
                    "border-radius: 5px; background: #ff6b35;"
                )
            else:
                dot.setStyleSheet(
                    f"border-radius: 5px; background: {manager.c('#333', '#ccc')};"
                )

    def _on_next(self):
        self._save_step(self._step)
        if self._step < self.STEPS - 1:
            self._go_to(self._step + 1)
        else:
            self._db.set_setting("onboarding_complete", "1")
            self.finished.emit()

    def _on_back(self):
        if self._step > 0:
            self._go_to(self._step - 1)

    def _on_skip(self):
        self._save_step(self._step)
        self._db.set_setting("onboarding_complete", "1")
        self.finished.emit()

    # ── Save helpers ──────────────────────────────────────────────────────────

    def _save_step(self, step: int):
        if step == 0:
            name = self._name_input.text().strip()
            if name:
                self._db.set_setting("user_name", name)
            chosen_hh = self._get_selected_selector(self._household_btns, _HOUSEHOLD)
            if chosen_hh:
                self._db.set_setting("user_household_size", chosen_hh)

        elif step == 1:
            diet = ",".join(k for k, b in self._dietary_btns.items() if b.isChecked())
            self._db.set_setting("dietary_prefs", diet)
            allergens = ",".join(k for k, b in self._allergen_btns.items() if b.isChecked())
            self._db.set_setting("allergens", allergens)

        elif step == 2:
            scenarios = ",".join(k for k, b in self._scenario_btns.items() if b.isChecked())
            self._db.set_setting("lifestyle_scenarios", scenarios)

        elif step == 3:
            cuisines = ",".join(k for k, b in self._cuisine_btns.items() if b.isChecked())
            self._db.set_setting("cuisine_preferences", cuisines)
            chosen_skill = self._get_selected_selector(self._skill_btns, _SKILL)
            if chosen_skill:
                self._db.set_setting("cooking_skill", chosen_skill)
            chosen_goal = self._get_selected_selector(self._goal_btns, _GOAL)
            if chosen_goal:
                self._db.set_setting("weekly_cooking_goal", chosen_goal)

    @staticmethod
    def _get_selected_selector(btns: dict, options: list[tuple]) -> str:
        """Return the key of whichever selector button has the active style."""
        for key, _ in options:
            if key in btns and "rgba(255,107,53" in btns[key].styleSheet():
                return key
        return ""
