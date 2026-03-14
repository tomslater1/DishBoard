"""
OnboardingWizard - guided first-run profile setup.

Displayed as index 2 of the root QStackedWidget so the main app is never
visible in the background. Emits ``finished`` when done or skipped.

This flow is intentionally input-light: every decision is made with guided
selection cards so the setup feels like part of the product instead of a form.
"""

from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from models.database import Database
from utils.theme import manager


_DIETARY = [
    ("vegetarian", "Vegetarian"),
    ("vegan", "Vegan"),
    ("gluten_free", "Gluten-Free"),
    ("dairy_free", "Dairy-Free"),
    ("nut_free", "Nut-Free"),
    ("halal", "Halal"),
    ("kosher", "Kosher"),
    ("keto", "Keto / Low-carb"),
    ("paleo", "Paleo"),
    ("low_fodmap", "Low-FODMAP"),
]

_ALLERGENS = [
    ("shellfish", "Shellfish"),
    ("eggs", "Eggs"),
    ("soy", "Soy"),
    ("peanuts", "Peanuts"),
    ("tree_nuts", "Tree Nuts"),
    ("fish", "Fish"),
    ("wheat", "Wheat"),
    ("sesame", "Sesame"),
]

_SCENARIOS = [
    ("meal_prep", "Meal Prep", "Cook once and reuse meals through the week.", "fa5s.layer-group"),
    ("cooking_for_kids", "Cooking for Kids", "Bias toward flexible family dinners.", "fa5s.child"),
    ("weight_loss", "Weight Focus", "Prefer lighter meals and clearer nutrition.", "fa5s.heartbeat"),
    ("muscle_building", "High Protein", "Push protein-forward meals and recovery fuel.", "fa5s.dumbbell"),
    ("quick_meals", "Fast Nights", "Prioritise lower-friction weekday cooking.", "fa5s.bolt"),
    ("adventurous", "New Flavours", "Keep the week varied and more exploratory.", "fa5s.globe"),
    ("budget_cooking", "Budget Cooking", "Prefer lower-cost staples and pantry wins.", "fa5s.piggy-bank"),
    ("healthy_eating", "Whole Foods", "Lean toward balanced and less processed meals.", "fa5s.leaf"),
    ("learning_to_cook", "Learning", "Keep recipes more approachable and guided.", "fa5s.book-open"),
    ("dinner_parties", "Hosting", "Leave room for showpiece or shareable dishes.", "fa5s.utensils"),
]

_CUISINES = [
    ("italian", "Italian"),
    ("asian", "Asian"),
    ("mexican", "Mexican"),
    ("indian", "Indian"),
    ("mediterranean", "Mediterranean"),
    ("american", "American"),
    ("middle_eastern", "Middle Eastern"),
    ("french", "French"),
    ("japanese", "Japanese"),
    ("thai", "Thai"),
    ("greek", "Greek"),
    ("spanish", "Spanish"),
    ("korean", "Korean"),
    ("british", "British"),
]

_HOUSEHOLD = [
    ("just_me", "Just Me", "Mostly solo cooking and simpler portion planning.", "fa5s.user"),
    ("2_people", "Two People", "Balanced planning for a pair or couple.", "fa5s.user-friends"),
    ("3_4_people", "3-4 People", "More shared meals and steadier shopping volume.", "fa5s.users"),
    ("5_plus", "5+ People", "Larger batches, more overlap, more coordination.", "fa5s.home"),
]

_SKILL = [
    ("beginner", "Beginner", "Clearer recipes, fewer moving parts.", "fa5s.seedling"),
    ("intermediate", "Intermediate", "A mix of fast wins and proper cooking sessions.", "fa5s.fire"),
    ("advanced", "Advanced", "More ambitious ideas and broader recipe variety.", "fa5s.star"),
]

_GOAL = [
    ("1_2", "1-2 Meals", "Keep planning light and flexible.", "fa5s.calendar-day"),
    ("3_4", "3-4 Meals", "A steady weekly rhythm for home cooking.", "fa5s.calendar-week"),
    ("5_plus", "5+ Meals", "Lean on DishBoard for the full week.", "fa5s.calendar-alt"),
]

_STEP_META = [
    {
        "eyebrow": "Profile setup",
        "title": "Shape the way DishBoard plans with you.",
        "subtitle": "Start with your kitchen size and the type of week you are cooking for.",
    },
    {
        "eyebrow": "Food guardrails",
        "title": "Set the rules Dishy should always respect.",
        "subtitle": "Pick any dietary needs or allergens that matter. Leave the rest blank.",
    },
    {
        "eyebrow": "Cooking rhythm",
        "title": "Tell DishBoard what real life looks like.",
        "subtitle": "These signals help shape recipe style, pacing, and planning suggestions.",
    },
    {
        "eyebrow": "Taste profile",
        "title": "Tune recommendations to your flavour and pace.",
        "subtitle": "Choose the cuisines, skill level, and weekly cooking volume you want the app to bias toward.",
    },
]


def _read_csv_setting(db: Database, key: str) -> set[str]:
    return {item for item in str(db.get_setting(key, "") or "").split(",") if item}


def _label_for(options: list[tuple], key: str, fallback: str = "Not set yet") -> str:
    for entry in options:
        if entry[0] == key:
            return entry[1]
    return fallback


class _ChoiceCard(QFrame):
    clicked = Signal(str)

    def __init__(
        self,
        key: str,
        title: str,
        subtitle: str = "",
        *,
        icon_name: str = "",
        compact: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._key = key
        self._icon_name = icon_name
        self._compact = compact
        self._checked = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("onboarding-choice-card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8 if not compact else 6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)

        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(28 if compact else 34, 28 if compact else 34)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet("background: transparent;")
        top.addWidget(self._icon_lbl, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(3)

        self._title_lbl = QLabel(title)
        self._title_lbl.setWordWrap(True)
        text_col.addWidget(self._title_lbl)

        self._subtitle_lbl = QLabel(subtitle)
        self._subtitle_lbl.setWordWrap(True)
        self._subtitle_lbl.setVisible(bool(subtitle))
        text_col.addWidget(self._subtitle_lbl)

        top.addLayout(text_col, 1)
        layout.addLayout(top)

        self.setMinimumHeight(76 if compact else 104)
        self._apply_style()

    def key(self) -> str:
        return self._key

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool) -> None:
        checked = bool(checked)
        if self._checked == checked:
            return
        self._checked = checked
        self._apply_style()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(event)

    def _apply_style(self) -> None:
        icon_color = "#ff6b35" if self._checked else manager.c("#8c867e", "#8b8176")
        card_bg = "rgba(255,107,53,0.12)" if self._checked else manager.c("#171a1f", "#fffaf4")
        border = "rgba(255,107,53,0.52)" if self._checked else manager.c("#2b3036", "#ddd2c5")
        title_color = "#ff6b35" if self._checked else manager.c("#f2eee8", "#181510")
        subtitle_color = manager.c("#d2b7a8", "#826f61") if self._checked else manager.c("#8c867e", "#8b8176")
        icon_name = self._icon_name or "fa5s.check-circle"
        size = 16 if self._compact else 18
        self._icon_lbl.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(QSize(size, size)))
        self.setStyleSheet(
            "QFrame#onboarding-choice-card {"
            f" background: {card_bg};"
            f" border: 1px solid {border};"
            " border-radius: 16px;"
            "}"
            "QFrame#onboarding-choice-card:hover {"
            " border-color: rgba(255,107,53,0.42);"
            "}"
        )
        self._title_lbl.setStyleSheet(
            f"color: {title_color};"
            f" font-size: {12 if self._compact else 14}px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        self._subtitle_lbl.setStyleSheet(
            f"color: {subtitle_color};"
            f" font-size: {11 if self._compact else 12}px; line-height: 1.45;"
            " background: transparent; border: none;"
        )


class OnboardingWizard(QWidget):
    """Full-screen onboarding flow. Add to root QStackedWidget at index 2."""

    finished = Signal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self._db = db
        self._step = 0
        self._profile_name = str(self._db.get_setting("user_name", "") or "").strip()

        self._household_cards: dict[str, _ChoiceCard] = {}
        self._dietary_cards: dict[str, _ChoiceCard] = {}
        self._allergen_cards: dict[str, _ChoiceCard] = {}
        self._scenario_cards: dict[str, _ChoiceCard] = {}
        self._cuisine_cards: dict[str, _ChoiceCard] = {}
        self._skill_cards: dict[str, _ChoiceCard] = {}
        self._goal_cards: dict[str, _ChoiceCard] = {}

        self.setObjectName("onboarding-root")
        self.setStyleSheet(f"background: {manager.c('#111317', '#f6f1ea')};")
        self._build_ui()
        self._go_to(0)
        self._refresh_profile_snapshot()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { width: 6px; background: transparent; margin: 0; }"
            f"QScrollBar::handle:vertical {{ background: {manager.c('#2b3036', '#cfc2b5')}; border-radius: 3px; min-height: 24px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(36, 32, 36, 32)
        content_layout.setSpacing(0)

        shell_row = QHBoxLayout()
        shell_row.setContentsMargins(0, 0, 0, 0)
        shell_row.addStretch()

        shell = QWidget()
        shell.setMaximumWidth(1180)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(22)

        shell_layout.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(22)
        body.addWidget(self._build_profile_panel())
        body.addWidget(self._build_step_panel(), 1)

        shell_layout.addLayout(body)
        shell_row.addWidget(shell)
        shell_row.addStretch()

        content_layout.addLayout(shell_row)
        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_header(self) -> QWidget:
        card = QFrame()
        card.setStyleSheet(
            f"background: {manager.c('#171a1f', '#fffaf4')};"
            f"border: 1px solid {manager.c('#2b3036', '#ddd2c5')};"
            "border-radius: 22px;"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(16)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(14)

        badge = QLabel("First-run setup")
        badge.setStyleSheet(
            "background: rgba(255,107,53,0.14); color: #ff6b35;"
            "border: 1px solid rgba(255,107,53,0.32); border-radius: 11px;"
            "padding: 5px 10px; font-size: 11px; font-weight: 700;"
        )
        top.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

        top.addStretch()

        brand = QLabel()
        brand.setPixmap(qta.icon("fa5s.utensils", color="#ff6b35").pixmap(QSize(18, 18)))
        top.addWidget(brand, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(top)

        title = QLabel("Build a profile that feels like the rest of the app.")
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color: {manager.c('#f2eee8', '#181510')};"
            "font-size: 30px; font-weight: 800; line-height: 1.15; background: transparent;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "This setup now behaves like a guided planning session: choose the signals that matter, "
            "skip the form-filling, and move straight into a DishBoard that already understands your week."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color: {manager.c('#8c867e', '#7b7268')};"
            "font-size: 14px; line-height: 1.55; background: transparent;"
        )
        layout.addWidget(subtitle)

        self._progress_row = QHBoxLayout()
        self._progress_row.setContentsMargins(0, 6, 0, 0)
        self._progress_row.setSpacing(8)
        self._progress_bars: list[QFrame] = []
        for _ in _STEP_META:
            bar = QFrame()
            bar.setFixedHeight(8)
            bar.setStyleSheet("border-radius: 4px;")
            self._progress_bars.append(bar)
            self._progress_row.addWidget(bar, 1)
        layout.addLayout(self._progress_row)
        return card

    def _build_profile_panel(self) -> QWidget:
        card = QFrame()
        card.setFixedWidth(340)
        card.setStyleSheet(
            f"background: {manager.c('#171a1f', '#fffaf4')};"
            f"border: 1px solid {manager.c('#2b3036', '#ddd2c5')};"
            "border-radius: 22px;"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        icon_wrap = QLabel()
        icon_wrap.setPixmap(qta.icon("fa5s.robot", color="#ff6b35").pixmap(QSize(26, 26)))
        icon_wrap.setStyleSheet(
            "background: rgba(255,107,53,0.12); border: 1px solid rgba(255,107,53,0.28);"
            "border-radius: 16px; padding: 12px;"
        )
        icon_wrap.setFixedSize(52, 52)
        icon_wrap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_wrap, 0, Qt.AlignmentFlag.AlignLeft)

        intro = QLabel("Your setup snapshot")
        intro.setStyleSheet(
            f"color: {manager.c('#f2eee8', '#181510')}; font-size: 21px; font-weight: 800; background: transparent;"
        )
        layout.addWidget(intro)

        blurb = QLabel(
            "Each choice here changes how DishBoard plans, searches, and recommends. "
            "Nothing is locked in - you can refine it later in Settings."
        )
        blurb.setWordWrap(True)
        blurb.setStyleSheet(
            f"color: {manager.c('#8c867e', '#7b7268')}; font-size: 13px; line-height: 1.55; background: transparent;"
        )
        layout.addWidget(blurb)

        highlights = [
            ("fa5s.calendar-alt", "Weekly plans will feel more relevant from the first screen."),
            ("fa5s.book-open", "Recipe search and Dishy prompts will start with better defaults."),
            ("fa5s.shopping-basket", "Shopping and kitchen suggestions will stay aligned with your real routine."),
        ]
        for icon_name, text in highlights:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(10)
            icon = QLabel()
            icon.setPixmap(qta.icon(icon_name, color="#ff6b35").pixmap(QSize(14, 14)))
            icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            icon.setStyleSheet("background: transparent;")
            row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

            label = QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet(
                f"color: {manager.c('#c4b9af', '#6f665d')}; font-size: 12px; line-height: 1.5; background: transparent;"
            )
            row.addWidget(label, 1)
            layout.addLayout(row)

        snapshot = QFrame()
        snapshot.setStyleSheet(
            f"background: {manager.c('#13161a', '#f4ede4')};"
            f"border: 1px solid {manager.c('#2b3036', '#ddd2c5')};"
            "border-radius: 18px;"
        )
        snap_layout = QVBoxLayout(snapshot)
        snap_layout.setContentsMargins(16, 16, 16, 16)
        snap_layout.setSpacing(12)

        snap_title = QLabel("Current profile")
        snap_title.setStyleSheet(
            f"color: {manager.c('#f2eee8', '#181510')}; font-size: 13px; font-weight: 700; background: transparent;"
        )
        snap_layout.addWidget(snap_title)

        self._snapshot_rows: dict[str, QLabel] = {}
        for key, label_text in [
            ("name", "Display name"),
            ("household", "Household"),
            ("focus", "Cooking rhythm"),
            ("flavour", "Taste profile"),
        ]:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(10)

            label = QLabel(label_text)
            label.setStyleSheet(
                f"color: {manager.c('#8c867e', '#867c72')}; font-size: 11px; font-weight: 700; background: transparent;"
            )
            row.addWidget(label)
            row.addStretch()

            value = QLabel("Not set yet")
            value.setStyleSheet(
                f"color: {manager.c('#f2eee8', '#181510')}; font-size: 12px; font-weight: 600; background: transparent;"
            )
            row.addWidget(value)
            snap_layout.addLayout(row)
            self._snapshot_rows[key] = value

        layout.addWidget(snapshot)
        layout.addStretch()
        return card

    def _build_step_panel(self) -> QWidget:
        card = QFrame()
        card.setStyleSheet(
            f"background: {manager.c('#171a1f', '#fffaf4')};"
            f"border: 1px solid {manager.c('#2b3036', '#ddd2c5')};"
            "border-radius: 22px;"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(18)

        self._step_badge = QLabel()
        self._step_badge.setStyleSheet(
            "background: rgba(255,107,53,0.14); color: #ff6b35;"
            "border: 1px solid rgba(255,107,53,0.28); border-radius: 11px;"
            "padding: 5px 10px; font-size: 11px; font-weight: 700;"
        )
        layout.addWidget(self._step_badge, 0, Qt.AlignmentFlag.AlignLeft)

        self._step_title_lbl = QLabel()
        self._step_title_lbl.setWordWrap(True)
        self._step_title_lbl.setStyleSheet(
            f"color: {manager.c('#f2eee8', '#181510')}; font-size: 26px; font-weight: 800; line-height: 1.15; background: transparent;"
        )
        layout.addWidget(self._step_title_lbl)

        self._step_subtitle_lbl = QLabel()
        self._step_subtitle_lbl.setWordWrap(True)
        self._step_subtitle_lbl.setStyleSheet(
            f"color: {manager.c('#8c867e', '#7b7268')}; font-size: 14px; line-height: 1.55; background: transparent;"
        )
        layout.addWidget(self._step_subtitle_lbl)

        self._step_container = QVBoxLayout()
        self._step_container.setContentsMargins(0, 6, 0, 0)
        self._step_container.setSpacing(0)
        layout.addLayout(self._step_container, 1)

        self._step_widgets = [
            self._build_step_one(),
            self._build_step_two(),
            self._build_step_three(),
            self._build_step_four(),
        ]
        for widget in self._step_widgets:
            widget.setVisible(False)
            self._step_container.addWidget(widget)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 18, 0, 0)
        footer.setSpacing(12)

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedHeight(42)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(
            f"QPushButton {{ background: {manager.c('#13161a', '#f4ede4')}; color: {manager.c('#a39d95', '#71685d')};"
            f" border: 1px solid {manager.c('#2b3036', '#ddd2c5')}; border-radius: 12px; padding: 0 18px; font-size: 13px; font-weight: 600; }}"
            "QPushButton:hover { border-color: rgba(255,107,53,0.32); color: #ff6b35; }"
        )
        self._back_btn.clicked.connect(self._on_back)
        footer.addWidget(self._back_btn)

        footer.addStretch()

        self._skip_btn = QPushButton("Skip setup")
        self._skip_btn.setFixedHeight(42)
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #ff6b35; border: none; font-size: 13px; font-weight: 700; padding: 0 8px; }"
            "QPushButton:hover { color: #ff7a48; }"
        )
        self._skip_btn.clicked.connect(self._on_skip)
        footer.addWidget(self._skip_btn)

        self._next_btn = QPushButton("Next")
        self._next_btn.setFixedSize(168, 44)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet(
            "QPushButton { background: #ff6b35; color: #fff7f1; border: 1px solid rgba(255,107,53,0.42);"
            " border-radius: 12px; font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background: #ff7a48; border-color: rgba(255,107,53,0.62); }"
        )
        self._next_btn.clicked.connect(self._on_next)
        footer.addWidget(self._next_btn)

        layout.addLayout(footer)
        return card

    def _build_step_one(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        info = QFrame()
        info.setStyleSheet(
            f"background: {manager.c('#13161a', '#f4ede4')}; border: 1px solid {manager.c('#2b3036', '#ddd2c5')}; border-radius: 18px;"
        )
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(18, 16, 18, 16)
        info_layout.setSpacing(10)

        title = QLabel("No typing required here.")
        title.setStyleSheet(
            f"color: {manager.c('#f2eee8', '#181510')}; font-size: 15px; font-weight: 700; background: transparent;"
        )
        info_layout.addWidget(title)

        text = QLabel(
            "We are intentionally keeping onboarding selection-based. "
            "If you want a custom display name later, you can add it in Settings without interrupting setup."
        )
        text.setWordWrap(True)
        text.setStyleSheet(
            f"color: {manager.c('#8c867e', '#7b7268')}; font-size: 12px; line-height: 1.55; background: transparent;"
        )
        info_layout.addWidget(text)

        self._identity_lbl = QLabel()
        self._identity_lbl.setWordWrap(True)
        self._identity_lbl.setStyleSheet(
            "background: rgba(255,107,53,0.12); color: #ff6b35; border: 1px solid rgba(255,107,53,0.22);"
            "border-radius: 12px; padding: 10px 12px; font-size: 12px; font-weight: 600;"
        )
        info_layout.addWidget(self._identity_lbl)
        layout.addWidget(info)

        layout.addWidget(self._section_label("Who are you cooking for this week?"))
        saved = str(self._db.get_setting("user_household_size", "") or "").strip()
        layout.addWidget(self._build_card_grid(_HOUSEHOLD, self._household_cards, saved, columns=2, compact=False))
        layout.addStretch()
        return wrapper

    def _build_step_two(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        layout.addWidget(self._section_label("Dietary needs"))
        layout.addWidget(
            self._build_card_grid(
                [(key, label, "", "fa5s.leaf") for key, label in _DIETARY],
                self._dietary_cards,
                _read_csv_setting(self._db, "dietary_prefs"),
                columns=3,
                compact=True,
                multi=True,
            )
        )

        layout.addWidget(self._section_label("Always avoid"))
        layout.addWidget(
            self._build_card_grid(
                [(key, label, "", "fa5s.exclamation-triangle") for key, label in _ALLERGENS],
                self._allergen_cards,
                _read_csv_setting(self._db, "allergens"),
                columns=3,
                compact=True,
                multi=True,
            )
        )
        layout.addStretch()
        return wrapper

    def _build_step_three(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        layout.addWidget(self._section_label("What should the app bias toward?"))
        saved = _read_csv_setting(self._db, "lifestyle_scenarios")
        layout.addWidget(self._build_card_grid(_SCENARIOS, self._scenario_cards, saved, columns=2, compact=False, multi=True))
        layout.addStretch()
        return wrapper

    def _build_step_four(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        layout.addWidget(self._section_label("Favourite cuisines"))
        layout.addWidget(
            self._build_card_grid(
                [(key, label, "", "fa5s.globe") for key, label in _CUISINES],
                self._cuisine_cards,
                _read_csv_setting(self._db, "cuisine_preferences"),
                columns=3,
                compact=True,
                multi=True,
            )
        )

        layout.addWidget(self._section_label("Cooking skill"))
        layout.addWidget(
            self._build_card_grid(
                _SKILL,
                self._skill_cards,
                str(self._db.get_setting("cooking_skill", "") or "").strip(),
                columns=3,
                compact=False,
            )
        )

        layout.addWidget(self._section_label("Meals you want to cook each week"))
        layout.addWidget(
            self._build_card_grid(
                _GOAL,
                self._goal_cards,
                str(self._db.get_setting("weekly_cooking_goal", "") or "").strip(),
                columns=3,
                compact=False,
            )
        )
        layout.addStretch()
        return wrapper

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {manager.c('#f2eee8', '#181510')}; font-size: 14px; font-weight: 700; background: transparent;"
        )
        return label

    def _build_card_grid(
        self,
        options: list[tuple],
        bucket: dict[str, _ChoiceCard],
        saved,
        *,
        columns: int,
        compact: bool,
        multi: bool = False,
    ) -> QWidget:
        selected = set(saved) if multi else {saved} if saved else set()
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        for idx, entry in enumerate(options):
            key, title = entry[0], entry[1]
            subtitle = entry[2] if len(entry) > 2 else ""
            icon_name = entry[3] if len(entry) > 3 else ""
            card = _ChoiceCard(key, title, subtitle, icon_name=icon_name, compact=compact)
            card.set_checked(key in selected)
            if multi:
                card.clicked.connect(lambda selected_key, cards=bucket: self._toggle_multi(cards, selected_key))
            else:
                card.clicked.connect(lambda selected_key, cards=bucket: self._set_single(cards, selected_key))
            bucket[key] = card
            row = idx // max(1, columns)
            col = idx % max(1, columns)
            grid.addWidget(card, row, col)

        for col in range(columns):
            grid.setColumnStretch(col, 1)
        return container

    def _toggle_multi(self, cards: dict[str, _ChoiceCard], key: str) -> None:
        card = cards.get(key)
        if card is None:
            return
        card.set_checked(not card.is_checked())
        self._refresh_profile_snapshot()

    def _set_single(self, cards: dict[str, _ChoiceCard], key: str) -> None:
        for name, card in cards.items():
            card.set_checked(name == key)
        self._refresh_profile_snapshot()

    def _selected_single(self, cards: dict[str, _ChoiceCard]) -> str:
        for key, card in cards.items():
            if card.is_checked():
                return key
        return ""

    def _selected_multi(self, cards: dict[str, _ChoiceCard]) -> list[str]:
        return [key for key, card in cards.items() if card.is_checked()]

    def _refresh_profile_snapshot(self) -> None:
        name_value = self._profile_name or "Add later in Settings"
        self._snapshot_rows["name"].setText(name_value)

        household = _label_for(_HOUSEHOLD, self._selected_single(self._household_cards))
        self._snapshot_rows["household"].setText(household)

        focus_items = self._selected_multi(self._scenario_cards)
        if focus_items:
            focus_text = ", ".join(_label_for(_SCENARIOS, key) for key in focus_items[:2])
            if len(focus_items) > 2:
                focus_text += f" +{len(focus_items) - 2}"
        else:
            focus_text = "Not set yet"
        self._snapshot_rows["focus"].setText(focus_text)

        cuisines = self._selected_multi(self._cuisine_cards)
        if cuisines:
            flavour = ", ".join(_label_for(_CUISINES, key) for key in cuisines[:2])
            if len(cuisines) > 2:
                flavour += f" +{len(cuisines) - 2}"
        else:
            flavour = "Not set yet"
        self._snapshot_rows["flavour"].setText(flavour)

        if self._profile_name:
            identity_text = f"Display name ready: {self._profile_name}"
        else:
            identity_text = "Display name will stay open until you set one in Settings."
        self._identity_lbl.setText(identity_text)

    def _go_to(self, step: int) -> None:
        self._step = max(0, min(step, len(_STEP_META) - 1))
        meta = _STEP_META[self._step]

        for idx, widget in enumerate(self._step_widgets):
            widget.setVisible(idx == self._step)

        self._step_badge.setText(f"{meta['eyebrow']}  |  Step {self._step + 1} of {len(_STEP_META)}")
        self._step_title_lbl.setText(meta["title"])
        self._step_subtitle_lbl.setText(meta["subtitle"])

        for idx, bar in enumerate(self._progress_bars):
            if idx < self._step:
                bar.setStyleSheet("background: rgba(255,107,53,0.36); border-radius: 4px;")
            elif idx == self._step:
                bar.setStyleSheet("background: #ff6b35; border-radius: 4px;")
            else:
                bar.setStyleSheet(f"background: {manager.c('#2b3036', '#ddd2c5')}; border-radius: 4px;")

        self._back_btn.setVisible(self._step > 0)
        is_last = self._step == len(_STEP_META) - 1
        self._next_btn.setText("Finish setup" if is_last else "Next")

    def _persist_all(self) -> None:
        if self._profile_name:
            self._db.set_setting("user_name", self._profile_name)

        self._db.set_setting("user_household_size", self._selected_single(self._household_cards))
        self._db.set_setting("dietary_prefs", ",".join(self._selected_multi(self._dietary_cards)))
        self._db.set_setting("allergens", ",".join(self._selected_multi(self._allergen_cards)))
        self._db.set_setting("lifestyle_scenarios", ",".join(self._selected_multi(self._scenario_cards)))
        self._db.set_setting("cuisine_preferences", ",".join(self._selected_multi(self._cuisine_cards)))
        self._db.set_setting("cooking_skill", self._selected_single(self._skill_cards))
        self._db.set_setting("weekly_cooking_goal", self._selected_single(self._goal_cards))

    def _on_next(self) -> None:
        self._persist_all()
        if self._step < len(_STEP_META) - 1:
            self._go_to(self._step + 1)
            return
        self._db.set_setting("onboarding_complete", "1")
        self.finished.emit()

    def _on_back(self) -> None:
        self._persist_all()
        if self._step > 0:
            self._go_to(self._step - 1)

    def _on_skip(self) -> None:
        self._persist_all()
        self._db.set_setting("onboarding_complete", "1")
        self.finished.emit()
