import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt, QSize

from utils.theme import manager as theme_manager


_SECTIONS = [
    {
        "index": 0,
        "icon": "fa5s.home",
        "colour": "#ff6b35",
        "title": "Home",
        "summary": "Your home screen. See today's planned meals, weekly macro progress, and quick links to every part of the app.",
        "features": [
            "Today's meals pulled live from the Meal Planner",
            "Weekly macro rings showing how you're tracking against your goals",
            "Recent recipes and quick-action tiles to jump to any section",
            "Dishy's daily cooking tip",
        ],
        "connects": [
            (2, "fa5s.calendar-alt", "#4caf8a", "Meal Planner"),
            (3, "fa5s.heartbeat",    "#e05c7a", "Nutrition"),
        ],
    },
    {
        "index": 1,
        "icon": "fa5s.book-open",
        "colour": "#7c6af7",
        "title": "Recipes",
        "summary": "Your recipe library. Save recipes by URL, search online, or create from scratch — Dishy fills in the nutrition automatically.",
        "features": [
            "Paste any URL to import a recipe instantly",
            "Search online and save directly from 60 instant results",
            "Create recipes manually — Dishy looks up macros per ingredient as you type",
            "Filter by tag: Breakfast, Lunch, Dinner, High-Protein, Vegetarian, and more",
            "Star favourites — Dishy prefers them when planning your week",
        ],
        "connects": [
            (2, "fa5s.calendar-alt", "#4caf8a", "Meal Planner"),
            (6, "fa5s.robot",        "#34d399", "Dishy"),
        ],
    },
    {
        "index": 2,
        "icon": "fa5s.calendar-alt",
        "colour": "#4caf8a",
        "title": "Meal Planner",
        "summary": "Plan Breakfast, Lunch, and Dinner for every day of the week. Adding a meal to today automatically updates your nutrition.",
        "features": [
            "Click any slot and pick from your saved recipes",
            "Ask Dishy to fill your whole week in one go",
            "Nutrition updates live the moment you plan today's meals",
            "Export the week to Apple Calendar",
        ],
        "connects": [
            (1, "fa5s.book-open",     "#7c6af7", "Recipes"),
            (3, "fa5s.heartbeat",     "#e05c7a", "Nutrition"),
            (5, "fa5s.shopping-cart", "#f0a500", "Shopping List"),
        ],
    },
    {
        "index": 3,
        "icon": "fa5s.heartbeat",
        "colour": "#e05c7a",
        "title": "Nutrition",
        "summary": "A live dashboard that tracks your macros automatically. No manual logging needed — it updates as you plan meals.",
        "features": [
            "Six macro rings vs your daily goals (set your own targets in Settings)",
            "Weekly calorie bar chart and stat tiles",
            "Quick Add: type any food and Dishy logs the macros instantly",
            "Ask Dishy how you're tracking for numbers and tailored advice",
        ],
        "connects": [
            (2, "fa5s.calendar-alt", "#4caf8a", "Meal Planner"),
            (6, "fa5s.robot",        "#34d399", "Dishy"),
        ],
    },
    {
        "index": 4,
        "icon": "fa5s.box-open",
        "colour": "#e8924a",
        "title": "My Kitchen",
        "summary": "Your pantry, fridge, and freezer tracker — coming soon.",
        "features": [
            "See exactly what ingredients you have at home",
            "Get low stock alerts before you run out",
            "Dishy will use your pantry when planning meals",
        ],
        "connects": [],
    },
    {
        "index": 5,
        "icon": "fa5s.shopping-cart",
        "colour": "#f0a500",
        "title": "Shopping List",
        "summary": "Build your grocery list manually or generate it from the week's meal plan. Items are grouped by category so you can shop aisle by aisle.",
        "features": [
            "Generate the full week's ingredients from the Meal Planner in one tap",
            "Items grouped by category — tap any section to expand or collapse",
            "Stats strip shows your total, items left to get, and basket progress",
            "Check off items as you shop, then clear them all at once",
            "Export to Apple Notes for easy phone access",
            "Ask Dishy to add specific items or build your list from scratch",
        ],
        "connects": [
            (2, "fa5s.calendar-alt", "#4caf8a", "Meal Planner"),
            (6, "fa5s.robot",        "#34d399", "Dishy"),
        ],
    },
    {
        "index": 6,
        "icon": "fa5s.robot",
        "colour": "#34d399",
        "title": "Dishy",
        "summary": "Your AI sous-chef. Dishy knows your recipes, plan, nutrition, and shopping list — and takes real actions inside the app.",
        "features": [
            "Create and save a recipe with full nutrition data",
            "Fill your whole week's meal plan or set individual slots",
            "Build your shopping list or add specific items",
            "Track your nutrition and get personalised macro advice",
            "Answer cooking questions, suggest substitutions, scale recipes",
            "Chat from any page using the bubble in the bottom-right corner",
            "Full chat history saved — pick up any previous conversation where you left off",
        ],
        "connects": [
            (1, "fa5s.book-open",     "#7c6af7", "Recipes"),
            (2, "fa5s.calendar-alt",  "#4caf8a", "Meal Planner"),
            (3, "fa5s.heartbeat",     "#e05c7a", "Nutrition"),
            (5, "fa5s.shopping-cart", "#f0a500", "Shopping List"),
        ],
    },
    {
        "index": 8,
        "icon": "fa5s.cog",
        "colour": "#888888",
        "title": "Settings",
        "summary": "Account, theme, nutrition goals, dietary preferences, and data management.",
        "features": [
            "Toggle dark / light mode",
            "Set your own daily calorie and macro targets in Nutrition Goals",
            "Set dietary preferences — Dishy uses these when planning meals",
            "Manage your account and view cloud sync status",
            "Export or import a full backup of all your data",
        ],
        "connects": [
            (3, "fa5s.heartbeat", "#e05c7a", "Nutrition"),
        ],
    },
]


def _feature_item(text: str) -> QWidget:
    """A single bullet-point feature row."""
    row = QWidget()
    row.setStyleSheet("background: transparent; border: none;")
    hl = QHBoxLayout(row)
    hl.setContentsMargins(0, 1, 0, 1)
    hl.setSpacing(10)

    dot = QLabel("·")
    dot.setFixedWidth(12)
    dot.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
    dot.setStyleSheet(
        f"color: {theme_manager.c('#555555', '#aaaaaa')}; font-size: 16px;"
        " background: transparent; border: none;"
    )
    hl.addWidget(dot)

    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    lbl.setStyleSheet(
        f"color: {theme_manager.c('#aaaaaa', '#444444')}; font-size: 15px;"
        " background: transparent; border: none;"
    )
    hl.addWidget(lbl, 1)

    return row


def _connects_row(connects: list, navigate_to) -> QWidget:
    row = QWidget()
    row.setStyleSheet("background: transparent; border: none;")
    hl = QHBoxLayout(row)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(6)

    lbl = QLabel("Links with:")
    lbl.setStyleSheet(
        f"color: {theme_manager.c('#666666', '#888888')};"
        " font-size: 13px; background: transparent; border: none;"
    )
    hl.addWidget(lbl)

    for idx, icon_name, colour, title in connects:
        btn = QPushButton()
        btn.setIcon(qta.icon(icon_name, color=colour).pixmap(QSize(11, 11)))
        btn.setIconSize(QSize(11, 11))
        btn.setText(f"  {title}")
        btn.setFixedHeight(24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  color: {colour}; font-size: 12px; font-weight: 500;"
            f"  background: {theme_manager.c('rgba(255,255,255,0.06)', 'rgba(0,0,0,0.04)')};"
            f"  border: 1px solid {theme_manager.c('rgba(255,255,255,0.1)', 'rgba(0,0,0,0.1)')};"
            f"  border-radius: 5px; padding: 0 8px;"
            f"}}"
            f"QPushButton:hover {{ background: {theme_manager.c('rgba(255,255,255,0.12)', 'rgba(0,0,0,0.08)')}; }}"
        )
        _i = idx
        btn.clicked.connect(lambda _, i=_i: navigate_to(i))
        hl.addWidget(btn)

    hl.addStretch()
    return row


def _section_card(section: dict, navigate_to) -> QWidget:
    card = QWidget()
    card.setObjectName("help-card")
    card.setStyleSheet(
        "QWidget#help-card {"
        f"  background: {theme_manager.c('#111111', '#ffffff')};"
        "  border-radius: 14px;"
        f"  border: 1px solid {theme_manager.c('#1e1e1e', '#e0e0e0')};"
        "}"
    )
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    vl = QVBoxLayout(card)
    vl.setContentsMargins(22, 18, 22, 18)
    vl.setSpacing(12)

    # ── Header: icon + title + Open button ──────────────────────────────────
    header = QHBoxLayout()
    header.setSpacing(10)

    icon_bg = QWidget()
    icon_bg.setFixedSize(34, 34)
    icon_bg.setStyleSheet(
        f"background: {theme_manager.c('rgba(255,255,255,0.05)', 'rgba(0,0,0,0.05)')};"
        f" border-radius: 8px; border: 1px solid {theme_manager.c('rgba(255,255,255,0.08)', 'rgba(0,0,0,0.08)')};"
    )
    icon_bg_l = QHBoxLayout(icon_bg)
    icon_bg_l.setContentsMargins(0, 0, 0, 0)
    icon_lbl = QLabel()
    icon_lbl.setPixmap(
        qta.icon(section["icon"], color=section["colour"]).pixmap(QSize(16, 16))
    )
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon_lbl.setStyleSheet("background: transparent; border: none;")
    icon_bg_l.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)

    title_lbl = QLabel(section["title"])
    title_lbl.setStyleSheet(
        f"color: {section['colour']}; font-size: 17px; font-weight: 700;"
        " background: transparent; border: none;"
    )

    go_btn = QPushButton("Open  →")
    go_btn.setFixedHeight(30)
    go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    go_btn.setStyleSheet(
        f"QPushButton {{"
        f"  color: {section['colour']}; font-size: 13px; font-weight: 600;"
        f"  background: transparent;"
        f"  border: 1px solid {theme_manager.c('rgba(255,255,255,0.12)', 'rgba(0,0,0,0.12)')};"
        f"  border-radius: 7px; padding: 0 14px;"
        f"}}"
        f"QPushButton:hover {{ background: {theme_manager.c('rgba(255,255,255,0.07)', 'rgba(0,0,0,0.05)')}; }}"
    )
    idx = section["index"]
    go_btn.clicked.connect(lambda: navigate_to(idx))

    header.addWidget(icon_bg)
    header.addWidget(title_lbl)
    header.addStretch()
    header.addWidget(go_btn)
    vl.addLayout(header)

    # ── Summary ──────────────────────────────────────────────────────────────
    summary_lbl = QLabel(section["summary"])
    summary_lbl.setWordWrap(True)
    summary_lbl.setStyleSheet(
        f"color: {theme_manager.c('#c0c0c0', '#333333')}; font-size: 15px;"
        " background: transparent; border: none;"
    )
    vl.addWidget(summary_lbl)

    # ── Divider ───────────────────────────────────────────────────────────────
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(
        f"color: {theme_manager.c('#1e1e1e', '#e8e8e8')};"
        f" background: {theme_manager.c('#1e1e1e', '#e8e8e8')};"
        " border: none; max-height: 1px;"
    )
    vl.addWidget(sep)

    # ── Feature list ─────────────────────────────────────────────────────────
    if section.get("features"):
        features_widget = QWidget()
        features_widget.setStyleSheet("background: transparent; border: none;")
        fvl = QVBoxLayout(features_widget)
        fvl.setContentsMargins(4, 0, 0, 0)
        fvl.setSpacing(4)
        for feat in section["features"]:
            fvl.addWidget(_feature_item(feat))
        vl.addWidget(features_widget)

    # ── Links with ────────────────────────────────────────────────────────────
    if section.get("connects"):
        vl.addWidget(_connects_row(section["connects"], navigate_to))

    return card


class HelpView(QWidget):
    def __init__(self, navigate_to, parent=None):
        super().__init__(parent)
        self.setObjectName("view-container")
        self._navigate_to = navigate_to
        self._build_ui()

    def _build_ui(self):
        if self.layout():
            while self.layout().count():
                item = self.layout().takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            outer = self.layout()
        else:
            outer = QVBoxLayout(self)

        outer.setContentsMargins(36, 36, 36, 36)
        outer.setSpacing(0)

        title = QLabel("How to use DishBoard")
        title.setObjectName("page-title")
        outer.addWidget(title)
        outer.addSpacing(6)

        subtitle = QLabel(
            "DishBoard is one connected system — your recipes, meal plan, nutrition, and shopping "
            "list all talk to each other automatically. Dishy is the AI layer that ties it all together."
        )
        subtitle.setObjectName("page-date")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        outer.addSpacing(24)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 12, 0)
        vl.setSpacing(14)

        for section in _SECTIONS:
            vl.addWidget(_section_card(section, self._navigate_to))

        vl.addSpacing(8)

        # ── The loop tip ──────────────────────────────────────────────────────
        tip_card = QWidget()
        tip_card.setStyleSheet(
            f"background: {theme_manager.c('rgba(52,211,153,0.07)', 'rgba(52,211,153,0.06)')};"
            f" border: 1px solid {theme_manager.c('rgba(52,211,153,0.2)', 'rgba(52,211,153,0.25)')};"
            " border-radius: 12px;"
        )
        tip_vl = QVBoxLayout(tip_card)
        tip_vl.setContentsMargins(18, 14, 18, 14)
        tip_vl.setSpacing(10)

        tip_header = QHBoxLayout()
        tip_header.setSpacing(10)
        tip_icon = QLabel()
        tip_icon.setPixmap(qta.icon("fa5s.sync-alt", color="#34d399").pixmap(QSize(14, 14)))
        tip_icon.setFixedSize(18, 18)
        tip_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip_icon.setStyleSheet("background: transparent; border: none;")
        tip_title = QLabel("The DishBoard loop")
        tip_title.setStyleSheet(
            "color: #34d399; font-size: 15px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        tip_header.addWidget(tip_icon)
        tip_header.addWidget(tip_title)
        tip_header.addStretch()
        tip_vl.addLayout(tip_header)

        steps = [
            ("1. Recipes", "Save or create recipes with Dishy — macros are calculated automatically."),
            ("2. Meal Planner", "Add recipes to your week. Nutrition logs itself the moment you plan today's meals."),
            ("3. Shopping List", "Generate your grocery list from the meal plan in one tap. Dishy can do this too."),
            ("4. Nutrition", "Check your dashboard — rings and stats update live as your plan changes."),
            ("Dishy throughout", "Ask Dishy anything at any step. It knows your data and takes real actions inside the app."),
        ]

        _muted = theme_manager.c("#888888", "#555555")
        _text  = theme_manager.c("#bbbbbb", "#333333")

        for step_title, step_body in steps:
            step_row = QHBoxLayout()
            step_row.setSpacing(8)
            step_row.setContentsMargins(0, 0, 0, 0)

            t_lbl = QLabel(step_title)
            t_lbl.setFixedWidth(145)
            t_lbl.setStyleSheet(
                f"color: #34d399; font-size: 14px; font-weight: 600;"
                " background: transparent; border: none;"
            )
            b_lbl = QLabel(step_body)
            b_lbl.setWordWrap(True)
            b_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            b_lbl.setStyleSheet(
                f"color: {_text}; font-size: 14px; background: transparent; border: none;"
            )
            step_row.addWidget(t_lbl)
            step_row.addWidget(b_lbl, 1)
            tip_vl.addLayout(step_row)

        vl.addWidget(tip_card)
        vl.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

    def apply_theme(self, _mode: str):
        self._build_ui()
