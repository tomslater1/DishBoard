import json
import warnings
import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QLineEdit, QCheckBox,
    QComboBox, QFileDialog, QStackedWidget,
)
from PySide6.QtCore import Qt, QSize, Signal

from models.database import Database
from utils.data_service import get_db
from utils.data_validators import sanitize_import_row
from utils.theme import manager
from utils.themed_dialog import ThemedMessageBox
from utils.ai_memory import memory_source_summary
from utils.system_visibility import _age_seconds, describe_snapshot, describe_sync_runtime
from utils.version import APP_VERSION, VERSION_HISTORY
from utils.recipe_health import validate_recipe
from utils.ui_tokens import (
    checkbox_style as _checkbox_style,
    primary_button_style as _primary_button_style,
    secondary_button_style as _secondary_button_style,
    subtle_surface_style as _subtle_surface_style,
)
from views.settings_helpers import (
    make_sep as _make_sep,
    selector_style as _selector_style,
    card_widget as _card_widget,
    refresh_surface_styles as _refresh_surface_styles,
)
from widgets.page_scaffold import PageScaffold, StatusBanner


def _danger_button_style() -> str:
    return (
        "QPushButton {"
        "  background-color: rgba(220,53,69,0.10); color: #dc3545;"
        "  border: 1px solid rgba(220,53,69,0.35); border-radius: 10px;"
        "  font-size: 13px; font-weight: 600; padding: 0 14px;"
        "}"
        "QPushButton:hover {"
        "  background-color: rgba(220,53,69,0.18); border-color: rgba(220,53,69,0.55);"
        "}"
        "QPushButton:disabled { color: #9a5b64; border-color: rgba(220,53,69,0.14); background-color: rgba(220,53,69,0.04); }"
    )


def _subtle_surface_style() -> str:
    return (
        f"background: {manager.c('#14191d', '#fffaf3')};"
        "border: none;"
        "border-radius: 14px;"
    )


# ── Page: Account ─────────────────────────────────────────────────────────────

from views.settings_account import _AccountPage

class _ProfilePage(QWidget):
    """Full editable profile page — mirrors the onboarding wizard fields."""

    def __init__(self, db: Database | None = None, parent=None):
        super().__init__(parent)
        self._db = db or get_db()
        self._sync_fn = None
        self._build()

    def set_sync_fn(self, fn):
        self._sync_fn = fn

    # ── chip / selector helpers (inline so no onboarding import needed) ───────

    @staticmethod
    def _chip_style(active: bool) -> str:
        if active:
            return (
                "QPushButton {"
                " background: rgba(255,107,53,0.15); color: #ff6b35;"
                " border: 1.5px solid #ff6b35; border-radius: 14px;"
                " font-size: 12px; padding: 4px 12px;"
                "}"
            )
        return (
            f"QPushButton {{"
            f" background: {manager.c('rgba(255,255,255,0.04)', 'rgba(0,0,0,0.04)')};"
            f" color: {manager.c('#888', '#666')};"
            f" border: 1px solid {manager.c('#2e2e2e', '#ddd')};"
            " border-radius: 14px; font-size: 12px; padding: 4px 12px;"
            f"}}"
            f"QPushButton:hover {{ border-color: rgba(255,107,53,0.5);"
            f" color: {manager.c('#ccc', '#333')}; }}"
        )

    def _make_chip_btn(self, key: str, label: str, saved_set: set,
                       save_fn) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setChecked(key in saved_set)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._chip_style(key in saved_set))

        def _toggled(checked, b=btn):
            b.setStyleSheet(self._chip_style(checked))
            save_fn()

        btn.toggled.connect(_toggled)
        return btn

    def _make_selector_row(self, options: list[tuple], saved: str,
                           save_fn) -> tuple[QWidget, dict]:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        btns: dict[str, QPushButton] = {}

        def _select(chosen_key: str):
            for k, b in btns.items():
                b.setStyleSheet(self._chip_style(k == chosen_key))
            save_fn()

        for key, label in options:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._chip_style(key == saved))
            btn.clicked.connect(lambda _, k=key: _select(k))
            layout.addWidget(btn)
            btns[key] = btn
        layout.addStretch()
        return container, btns

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        # ── About You card ────────────────────────────────────────────────────
        about_card = _card_widget()
        about_layout = QVBoxLayout(about_card)
        about_layout.setSpacing(14)

        about_title = QLabel("About You")
        about_title.setObjectName("card-title")
        about_layout.addWidget(about_title)

        about_desc = QLabel(
            "Dishy uses this information to personalise every suggestion and response."
        )
        about_desc.setObjectName("card-body")
        about_desc.setWordWrap(True)
        about_layout.addWidget(about_desc)

        about_layout.addWidget(_make_sep())

        name_lbl = QLabel("Your name")
        name_lbl.setObjectName("card-body")
        about_layout.addWidget(name_lbl)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Alex")
        self._name_input.setText(self._db.get_setting("user_name", ""))
        self._name_input.editingFinished.connect(self._save_name)
        about_layout.addWidget(self._name_input)

        about_layout.addWidget(_make_sep())

        hh_lbl = QLabel("Cooking for")
        hh_lbl.setObjectName("card-body")
        about_layout.addWidget(hh_lbl)

        _HOUSEHOLD = [
            ("just_me",    "Just me"),
            ("2_people",   "2 people"),
            ("3_4_people", "3–4 people"),
            ("5_plus",     "5+ people"),
        ]
        saved_hh = self._db.get_setting("user_household_size", "")
        hh_container, self._household_btns = self._make_selector_row(
            _HOUSEHOLD, saved_hh, self._save_household
        )
        about_layout.addWidget(hh_container)

        outer.addWidget(about_card)

        # ── Dietary card ──────────────────────────────────────────────────────
        diet_card = _card_widget()
        diet_layout = QVBoxLayout(diet_card)
        diet_layout.setSpacing(14)

        diet_title = QLabel("Dietary Requirements")
        diet_title.setObjectName("card-title")
        diet_layout.addWidget(diet_title)

        diet_layout.addWidget(_make_sep())

        diet_req_lbl = QLabel("Requirements")
        diet_req_lbl.setObjectName("card-body")
        diet_layout.addWidget(diet_req_lbl)

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
        saved_diet = set(self._db.get_setting("dietary_prefs", "").split(","))
        self._dietary_btns: dict[str, QPushButton] = {}

        diet_flow = QWidget()
        diet_flow.setStyleSheet("background: transparent;")
        diet_flow_layout = QHBoxLayout(diet_flow)
        diet_flow_layout.setContentsMargins(0, 0, 0, 0)
        diet_flow_layout.setSpacing(6)
        for key, label in _DIETARY:
            btn = self._make_chip_btn(key, label, saved_diet, self._save_dietary)
            self._dietary_btns[key] = btn
            diet_flow_layout.addWidget(btn)
        diet_flow_layout.addStretch()
        diet_layout.addWidget(diet_flow)

        # Second row for overflow
        diet_flow2 = QWidget()
        diet_flow2.setStyleSheet("background: transparent;")
        diet_flow2_layout = QHBoxLayout(diet_flow2)
        diet_flow2_layout.setContentsMargins(0, 0, 0, 0)
        diet_flow2_layout.setSpacing(6)
        # Re-do chip layout as two proper rows
        # Clear and rebuild with 5 per row
        for w in [diet_flow, diet_flow2]:
            for i in reversed(range(w.layout().count())):
                item = w.layout().itemAt(i)
                if item.widget():
                    item.widget().setParent(None)
        diet_layout.removeWidget(diet_flow)
        diet_flow.deleteLater()

        rows = [_DIETARY[:5], _DIETARY[5:]]
        for row_items in rows:
            rw = QWidget()
            rw.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(rw)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)
            for key, label in row_items:
                btn = self._make_chip_btn(key, label, saved_diet, self._save_dietary)
                self._dietary_btns[key] = btn
                rl.addWidget(btn)
            rl.addStretch()
            diet_layout.addWidget(rw)

        diet_layout.addWidget(_make_sep())

        allergen_lbl = QLabel("Allergens to always avoid")
        allergen_lbl.setObjectName("card-body")
        diet_layout.addWidget(allergen_lbl)

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
        saved_allergens = set(self._db.get_setting("allergens", "").split(","))
        self._allergen_btns: dict[str, QPushButton] = {}

        allergen_rw = QWidget()
        allergen_rw.setStyleSheet("background: transparent;")
        allergen_rl = QHBoxLayout(allergen_rw)
        allergen_rl.setContentsMargins(0, 0, 0, 0)
        allergen_rl.setSpacing(6)
        for key, label in _ALLERGENS:
            btn = self._make_chip_btn(key, label, saved_allergens, self._save_allergens)
            self._allergen_btns[key] = btn
            allergen_rl.addWidget(btn)
        allergen_rl.addStretch()
        diet_layout.addWidget(allergen_rw)

        outer.addWidget(diet_card)

        # ── Lifestyle card ────────────────────────────────────────────────────
        life_card = _card_widget()
        life_layout = QVBoxLayout(life_card)
        life_layout.setSpacing(14)

        life_title = QLabel("Cooking Lifestyle")
        life_title.setObjectName("card-title")
        life_layout.addWidget(life_title)

        life_layout.addWidget(_make_sep())

        _SCENARIOS = [
            ("meal_prep",        "I meal prep in batches"),
            ("cooking_for_kids", "I cook for kids"),
            ("weight_loss",      "I'm focused on weight loss"),
            ("muscle_building",  "I'm building muscle"),
            ("quick_meals",      "I need quick weeknight meals"),
            ("adventurous",      "I love trying new cuisines"),
            ("budget_cooking",   "I cook on a budget"),
            ("healthy_eating",   "I prefer healthy whole foods"),
            ("learning_to_cook", "I'm learning to cook"),
            ("dinner_parties",   "I host dinner parties"),
        ]
        saved_scenarios = set(self._db.get_setting("lifestyle_scenarios", "").split(","))
        self._scenario_btns: dict[str, QPushButton] = {}

        scenario_rw = QWidget()
        scenario_rw.setStyleSheet("background: transparent;")
        scenario_rl = QHBoxLayout(scenario_rw)
        scenario_rl.setContentsMargins(0, 0, 0, 0)
        scenario_rl.setSpacing(6)
        # 5 per row
        for i, (key, label) in enumerate(_SCENARIOS):
            btn = self._make_chip_btn(key, label, saved_scenarios, self._save_scenarios)
            self._scenario_btns[key] = btn
            if i == 5:
                scenario_rl.addStretch()
                life_layout.addWidget(scenario_rw)
                scenario_rw = QWidget()
                scenario_rw.setStyleSheet("background: transparent;")
                scenario_rl = QHBoxLayout(scenario_rw)
                scenario_rl.setContentsMargins(0, 0, 0, 0)
                scenario_rl.setSpacing(6)
            scenario_rl.addWidget(btn)
        scenario_rl.addStretch()
        life_layout.addWidget(scenario_rw)

        outer.addWidget(life_card)

        # ── Preferences card ──────────────────────────────────────────────────
        pref_card = _card_widget()
        pref_layout = QVBoxLayout(pref_card)
        pref_layout.setSpacing(14)

        pref_title = QLabel("Food Preferences")
        pref_title.setObjectName("card-title")
        pref_layout.addWidget(pref_title)

        pref_layout.addWidget(_make_sep())

        cuisine_lbl = QLabel("Favourite cuisines")
        cuisine_lbl.setObjectName("card-body")
        pref_layout.addWidget(cuisine_lbl)

        _CUISINES_ALL = [
            ("italian",       "Italian"),
            ("asian",         "Asian"),
            ("mexican",       "Mexican"),
            ("indian",        "Indian"),
            ("mediterranean", "Mediterranean"),
            ("american",      "American"),
            ("middle_eastern","Middle Eastern"),
            ("french",        "French"),
            ("japanese",      "Japanese"),
            ("thai",          "Thai"),
            ("greek",         "Greek"),
            ("spanish",       "Spanish"),
            ("korean",        "Korean"),
            ("british",       "British"),
        ]
        saved_cuisines = set(self._db.get_setting("cuisine_preferences", "").split(","))
        self._cuisine_btns: dict[str, QPushButton] = {}

        for row_slice in [_CUISINES_ALL[:7], _CUISINES_ALL[7:]]:
            crw = QWidget()
            crw.setStyleSheet("background: transparent;")
            crl = QHBoxLayout(crw)
            crl.setContentsMargins(0, 0, 0, 0)
            crl.setSpacing(6)
            for key, label in row_slice:
                btn = self._make_chip_btn(key, label, saved_cuisines, self._save_cuisines)
                self._cuisine_btns[key] = btn
                crl.addWidget(btn)
            crl.addStretch()
            pref_layout.addWidget(crw)

        pref_layout.addWidget(_make_sep())

        skill_lbl = QLabel("Cooking skill level")
        skill_lbl.setObjectName("card-body")
        pref_layout.addWidget(skill_lbl)

        saved_skill = self._db.get_setting("cooking_skill", "")
        skill_container, self._skill_btns = self._make_selector_row(
            [("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced")],
            saved_skill, self._save_skill,
        )
        pref_layout.addWidget(skill_container)

        pref_layout.addWidget(_make_sep())

        goal_lbl = QLabel("Weekly home cooking goal")
        goal_lbl.setObjectName("card-body")
        pref_layout.addWidget(goal_lbl)

        saved_goal = self._db.get_setting("weekly_cooking_goal", "")
        goal_container, self._goal_btns = self._make_selector_row(
            [("1_2", "1–2 meals/week"), ("3_4", "3–4 meals/week"), ("5_plus", "5+ meals/week")],
            saved_goal, self._save_goal,
        )
        pref_layout.addWidget(goal_container)

        outer.addWidget(pref_card)
        outer.addStretch()

    # ── Save helpers ──────────────────────────────────────────────────────────

    def _save_household(self):
        chosen = next(
            (k for k, b in self._household_btns.items()
             if "rgba(255,107,53" in b.styleSheet()),
            ""
        )
        self._db.set_setting("user_household_size", chosen)
        if self._sync_fn:
            self._sync_fn()

    def _save_name(self):
        self._db.set_setting("user_name", self._name_input.text().strip())
        if self._sync_fn:
            self._sync_fn()

    def _save_dietary(self):
        selected = ",".join(k for k, b in self._dietary_btns.items() if b.isChecked())
        self._db.set_setting("dietary_prefs", selected)
        if self._sync_fn:
            self._sync_fn()

    def _save_allergens(self):
        selected = ",".join(k for k, b in self._allergen_btns.items() if b.isChecked())
        self._db.set_setting("allergens", selected)
        if self._sync_fn:
            self._sync_fn()

    def _save_scenarios(self):
        selected = ",".join(k for k, b in self._scenario_btns.items() if b.isChecked())
        self._db.set_setting("lifestyle_scenarios", selected)
        if self._sync_fn:
            self._sync_fn()

    def _save_cuisines(self):
        selected = ",".join(k for k, b in self._cuisine_btns.items() if b.isChecked())
        self._db.set_setting("cuisine_preferences", selected)
        if self._sync_fn:
            self._sync_fn()

    def _save_skill(self):
        chosen = next(
            (k for k, b in self._skill_btns.items()
             if "rgba(255,107,53" in b.styleSheet()),
            ""
        )
        self._db.set_setting("cooking_skill", chosen)
        if self._sync_fn:
            self._sync_fn()

    def _save_goal(self):
        chosen = next(
            (k for k, b in self._goal_btns.items()
             if "rgba(255,107,53" in b.styleSheet()),
            ""
        )
        self._db.set_setting("weekly_cooking_goal", chosen)
        if self._sync_fn:
            self._sync_fn()

    def refresh(self):
        """Re-read all profile values from DB and update the UI.

        Called whenever the Profile page is shown, so values set during
        onboarding (which runs after this page is first constructed) are
        always reflected correctly.
        """
        # Name
        self._name_input.setText(self._db.get_setting("user_name", ""))

        # Household selector
        saved_hh = self._db.get_setting("user_household_size", "")
        for k, b in self._household_btns.items():
            b.setStyleSheet(self._chip_style(k == saved_hh))

        # Dietary chips — block signals to avoid partial save mid-refresh
        saved_diet = set(self._db.get_setting("dietary_prefs", "").split(","))
        for k, b in self._dietary_btns.items():
            b.blockSignals(True)
            b.setChecked(k in saved_diet)
            b.blockSignals(False)
            b.setStyleSheet(self._chip_style(k in saved_diet))

        # Allergen chips
        saved_allergens = set(self._db.get_setting("allergens", "").split(","))
        for k, b in self._allergen_btns.items():
            b.blockSignals(True)
            b.setChecked(k in saved_allergens)
            b.blockSignals(False)
            b.setStyleSheet(self._chip_style(k in saved_allergens))

        # Scenario chips
        saved_scenarios = set(self._db.get_setting("lifestyle_scenarios", "").split(","))
        for k, b in self._scenario_btns.items():
            b.blockSignals(True)
            b.setChecked(k in saved_scenarios)
            b.blockSignals(False)
            b.setStyleSheet(self._chip_style(k in saved_scenarios))

        # Cuisine chips
        saved_cuisines = set(self._db.get_setting("cuisine_preferences", "").split(","))
        for k, b in self._cuisine_btns.items():
            b.blockSignals(True)
            b.setChecked(k in saved_cuisines)
            b.blockSignals(False)
            b.setStyleSheet(self._chip_style(k in saved_cuisines))

        # Skill selector
        saved_skill = self._db.get_setting("cooking_skill", "")
        for k, b in self._skill_btns.items():
            b.setStyleSheet(self._chip_style(k == saved_skill))

        # Goal selector
        saved_goal = self._db.get_setting("weekly_cooking_goal", "")
        for k, b in self._goal_btns.items():
            b.setStyleSheet(self._chip_style(k == saved_goal))

    def apply_theme(self, _mode):
        self.refresh()


# ── Page: Dishy Preferences ───────────────────────────────────────────────────

class _DishyPrefsPage(QWidget):
    def __init__(self, db: Database | None = None, parent=None):
        super().__init__(parent)
        self._db = db or get_db()
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        # ── Chat history card ─────────────────────────────────────────────────
        hist_card = _card_widget()
        hist_layout = QVBoxLayout(hist_card)
        hist_layout.setSpacing(14)

        hist_title = QLabel("Chat History")
        hist_title.setObjectName("card-title")
        hist_layout.addWidget(hist_title)

        hist_desc = QLabel(
            "All your Dishy conversations are saved locally on this device only. "
            "Chat history is never included in backups or exports."
        )
        hist_desc.setObjectName("card-body")
        hist_desc.setWordWrap(True)
        hist_layout.addWidget(hist_desc)

        hist_layout.addWidget(_make_sep())

        clear_row = QHBoxLayout()
        clear_row.setSpacing(16)
        clear_col = QVBoxLayout()
        clear_col.setSpacing(3)
        self._clear_name = QLabel("Clear Dishy Chat History")
        self._clear_name.setStyleSheet(
            f"font-size: 14px; font-weight: 600;"
            f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        self._clear_sub = QLabel("Permanently delete all past conversations with Dishy")
        self._clear_sub.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666666', '#777777')}; background: transparent;"
        )
        clear_col.addWidget(self._clear_name)
        clear_col.addWidget(self._clear_sub)

        clear_btn = QPushButton("Clear History")
        clear_btn.setFixedHeight(36)
        clear_btn.setMinimumWidth(150)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: rgba(220,53,69,0.1); color: #dc3545;"
            "  border: 1px solid rgba(220,53,69,0.35); border-radius: 8px;"
            "  font-size: 13px; font-weight: 600; padding: 0 14px;"
            "}"
            "QPushButton:hover {"
            "  background-color: rgba(220,53,69,0.2);"
            "  border-color: rgba(220,53,69,0.6);"
            "}"
        )
        clear_btn.clicked.connect(self._clear_dishy_history)

        clear_row.addLayout(clear_col, 1)
        clear_row.addWidget(clear_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        hist_layout.addLayout(clear_row)

        outer.addWidget(hist_card)
        outer.addStretch()

    def _clear_dishy_history(self):
        if ThemedMessageBox.confirm(
            self, "Clear Dishy History?",
            "This will permanently delete all your Dishy conversations.\nThis cannot be undone.",
            confirm_text="Yes, clear",
        ):
            self._db.clear_dishy_history()

    def apply_theme(self, _mode):
        self._clear_name.setStyleSheet(
            f"font-size: 14px; font-weight: 600;"
            f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        self._clear_sub.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666666', '#777777')}; background: transparent;"
        )


# ── Page: App Preferences ─────────────────────────────────────────────────────

class _AppPrefsPage(QWidget):
    def __init__(self, db: Database | None = None, parent=None):
        super().__init__(parent)
        self._db = db or get_db()
        self._sync_fn = None
        self._build()

    def set_sync_fn(self, fn):
        self._sync_fn = fn

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        # ── Appearance card ───────────────────────────────────────────────────
        app_card = _card_widget()
        app_layout = QVBoxLayout(app_card)
        app_layout.setSpacing(14)

        app_title = QLabel("Appearance")
        app_title.setObjectName("card-title")
        app_layout.addWidget(app_title)

        app_desc = QLabel("Choose your preferred colour scheme. Changes apply instantly.")
        app_desc.setObjectName("card-body")
        app_desc.setWordWrap(True)
        app_layout.addWidget(app_desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._dark_btn  = QPushButton()
        self._dark_btn.setCheckable(True)
        self._dark_btn.setFixedHeight(80)
        self._dark_btn.setMinimumWidth(160)
        self._dark_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dark_btn.clicked.connect(lambda: self._select_theme("dark"))

        self._light_btn = QPushButton()
        self._light_btn.setCheckable(True)
        self._light_btn.setFixedHeight(80)
        self._light_btn.setMinimumWidth(160)
        self._light_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._light_btn.clicked.connect(lambda: self._select_theme("light"))

        self._update_theme_btns(manager.mode)
        btn_row.addWidget(self._dark_btn)
        btn_row.addWidget(self._light_btn)
        btn_row.addStretch()
        app_layout.addLayout(btn_row)

        outer.addWidget(app_card)

        # ── Planner card ──────────────────────────────────────────────────────
        plan_card = _card_widget()
        plan_layout = QVBoxLayout(plan_card)
        plan_layout.setSpacing(14)

        plan_title = QLabel("Meal Planner")
        plan_title.setObjectName("card-title")
        plan_layout.addWidget(plan_title)

        week_lbl = QLabel("Week starts on")
        week_lbl.setObjectName("card-body")
        plan_layout.addWidget(week_lbl)

        week_row = QHBoxLayout()
        week_row.setSpacing(10)
        self._mon_btn = QPushButton("☽  Monday")
        self._mon_btn.setCheckable(True)
        self._mon_btn.setFixedHeight(44)
        self._mon_btn.setMinimumWidth(120)
        self._mon_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mon_btn.clicked.connect(lambda: self._select_week_day("Monday"))
        self._sun_btn = QPushButton("☀  Sunday")
        self._sun_btn.setCheckable(True)
        self._sun_btn.setFixedHeight(44)
        self._sun_btn.setMinimumWidth(120)
        self._sun_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sun_btn.clicked.connect(lambda: self._select_week_day("Sunday"))
        self._update_week_btns(self._db.get_setting("week_start_day", "Monday"))
        week_row.addWidget(self._mon_btn)
        week_row.addWidget(self._sun_btn)
        week_row.addStretch()
        plan_layout.addLayout(week_row)

        plan_layout.addWidget(_make_sep())

        serv_lbl = QLabel("Default servings for new recipes")
        serv_lbl.setObjectName("card-body")
        plan_layout.addWidget(serv_lbl)

        serv_row = QHBoxLayout()
        serv_row.setSpacing(10)
        self._serv_input = QLineEdit()
        self._serv_input.setFixedWidth(72)
        self._serv_input.setFixedHeight(40)
        self._serv_input.setPlaceholderText("4")
        self._serv_input.setText(self._db.get_setting("default_servings", "4"))
        self._serv_input.editingFinished.connect(self._save_servings)
        serv_lbl2 = QLabel("people")
        serv_lbl2.setObjectName("card-body")
        serv_row.addWidget(self._serv_input)
        serv_row.addWidget(serv_lbl2)
        serv_row.addStretch()
        plan_layout.addLayout(serv_row)

        outer.addWidget(plan_card)
        outer.addStretch()

    def _select_theme(self, mode: str):
        manager.apply(mode)
        self._update_theme_btns(mode)

    def _update_theme_btns(self, mode: str):
        self._dark_btn.setChecked(mode == "dark")
        self._light_btn.setChecked(mode == "light")
        self._dark_btn.setText("☽  Dark" + ("  ✓" if mode == "dark" else ""))
        self._light_btn.setText("☀  Light" + ("  ✓" if mode == "light" else ""))
        self._dark_btn.setStyleSheet(_selector_style(mode == "dark"))
        self._light_btn.setStyleSheet(_selector_style(mode == "light"))

    def _select_week_day(self, day: str):
        self._db.set_setting("week_start_day", day)
        self._update_week_btns(day)
        if self._sync_fn:
            self._sync_fn()

    def _update_week_btns(self, day: str):
        self._mon_btn.setChecked(day == "Monday")
        self._sun_btn.setChecked(day == "Sunday")
        self._mon_btn.setStyleSheet(_selector_style(day == "Monday", size=14))
        self._sun_btn.setStyleSheet(_selector_style(day == "Sunday", size=14))

    def _save_servings(self):
        try:
            val = max(1, int(self._serv_input.text().strip()))
        except ValueError:
            val = 4
        self._serv_input.setText(str(val))
        self._db.set_setting("default_servings", str(val))
        if self._sync_fn:
            self._sync_fn()

    def apply_theme(self, mode: str):
        self._update_theme_btns(mode)
        self._update_week_btns(self._db.get_setting("week_start_day", "Monday"))


# ── Page: Data & Backup ───────────────────────────────────────────────────────

class _DataPage(QWidget):
    def __init__(self, db: Database | None = None, parent=None):
        super().__init__(parent)
        self._db = db or get_db()
        self._refresh_meal_plan = None
        self._refresh_shopping  = None
        self._refresh_recipes   = None
        self._row_labels: list[tuple[QLabel, QLabel]] = []
        self._port_row_labels: list[tuple[QLabel, QLabel]] = []
        self._primary_port_btns: list[QPushButton] = []
        self._secondary_port_btns: list[QPushButton] = []
        self._danger_btns: list[QPushButton] = []
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        # ── Portability card ──────────────────────────────────────────────────
        port_card = _card_widget()
        port_layout = QVBoxLayout(port_card)
        port_layout.setSpacing(14)

        port_title = QLabel("Data Portability")
        port_title.setObjectName("card-title")
        port_layout.addWidget(port_title)

        port_desc = QLabel(
            "Export all your recipes, meal plans, and shopping list to a JSON backup file. "
            "Import a previous backup to restore or merge your data. "
            "Dishy chat history is stored locally only and is never included in backups."
        )
        port_desc.setObjectName("card-body")
        port_desc.setWordWrap(True)
        port_layout.addWidget(port_desc)

        for row_title, row_sub, btn_label, btn_fn, is_primary in [
            ("Export Data", "Save a full backup as a .json file", "Export Backup", self._export, True),
            ("Export Profiles", "Choose a focused export (migration, meal planning, or nutrition only)", "Choose Profile", self._export_profile_picker, False),
            ("Import Data", "Merge a backup file into your current data", "Import Backup", self._import, False),
            ("Trash Bin", "Restore recently deleted recipes, meal slots, shopping or pantry items", "Manage Trash", self._manage_trash, False),
        ]:
            port_layout.addWidget(_make_sep())
            row = QHBoxLayout()
            row.setSpacing(16)
            col = QVBoxLayout()
            col.setSpacing(3)
            t = QLabel(row_title)
            t.setStyleSheet(
                f"font-size: 14px; font-weight: 600;"
                f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
            )
            s = QLabel(row_sub)
            s.setStyleSheet(
                f"font-size: 12px; color: {manager.c('#666666', '#777777')}; background: transparent;"
            )
            self._port_row_labels.append((t, s))
            col.addWidget(t)
            col.addWidget(s)

            btn = QPushButton(btn_label)
            btn.setFixedHeight(36)
            btn.setMinimumWidth(130)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if is_primary:
                btn.setStyleSheet(_primary_button_style())
                self._primary_port_btns.append(btn)
            else:
                btn.setStyleSheet(_secondary_button_style())
                self._secondary_port_btns.append(btn)
            btn.clicked.connect(btn_fn)
            row.addLayout(col, 1)
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
            port_layout.addLayout(row)

        outer.addWidget(port_card)

        # ── Danger zone card ──────────────────────────────────────────────────
        danger_card = _card_widget()
        danger_layout = QVBoxLayout(danger_card)
        danger_layout.setSpacing(10)

        danger_title = QLabel("Clear Data")
        danger_title.setObjectName("card-title")
        danger_layout.addWidget(danger_title)

        danger_desc = QLabel("Permanently remove data from DishBoard. These actions cannot be undone.")
        danger_desc.setObjectName("card-body")
        danger_desc.setWordWrap(True)
        danger_layout.addWidget(danger_desc)

        for label, subtitle, confirm_msg, action in [
            (
                "Clear Meal Plan",
                "Remove all meals from every week",
                "This will delete all planned meals across every week.\nAre you sure?",
                self._clear_meal_plan,
            ),
            (
                "Clear Shopping List",
                "Remove every item from your shopping list",
                "This will delete your entire shopping list.\nAre you sure?",
                self._clear_shopping,
            ),
            (
                "Clear All Recipes",
                "Permanently delete every saved recipe",
                "This will permanently delete ALL your saved recipes.\nThis cannot be undone. Are you sure?",
                self._clear_recipes,
            ),
        ]:
            danger_layout.addWidget(_make_sep())
            row = QHBoxLayout()
            row.setSpacing(16)

            text_col = QVBoxLayout()
            text_col.setSpacing(3)
            name_lbl = QLabel(label)
            name_lbl.setStyleSheet(
                f"font-size: 14px; font-weight: 600;"
                f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
            )
            sub_lbl = QLabel(subtitle)
            sub_lbl.setStyleSheet(
                f"font-size: 12px; color: {manager.c('#666666', '#777777')}; background: transparent;"
            )
            self._row_labels.append((name_lbl, sub_lbl))
            text_col.addWidget(name_lbl)
            text_col.addWidget(sub_lbl)

            btn = QPushButton(label)
            btn.setFixedHeight(36)
            btn.setMinimumWidth(170)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_danger_button_style())
            self._danger_btns.append(btn)
            btn.clicked.connect(
                lambda _, m=confirm_msg, a=action: self._confirm_and_run(m, a)
            )
            row.addLayout(text_col, 1)
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
            danger_layout.addLayout(row)

        outer.addWidget(danger_card)
        outer.addStretch()

    def set_refresh_callbacks(self, meal_plan_fn=None, shopping_fn=None, recipes_fn=None):
        self._refresh_meal_plan = meal_plan_fn
        self._refresh_shopping  = shopping_fn
        self._refresh_recipes   = recipes_fn

    def _confirm_and_run(self, message: str, action):
        if ThemedMessageBox.confirm(
            self, "Are you sure?", message, confirm_text="Yes, delete"
        ):
            action()

    def _clear_meal_plan(self):
        self._db.clear_all_meal_plans()
        if self._refresh_meal_plan:
            self._refresh_meal_plan()

    def _clear_shopping(self):
        self._db.clear_all_shopping_items()
        if self._refresh_shopping:
            self._refresh_shopping()

    def _clear_recipes(self):
        self._db.delete_all_recipes()
        if self._refresh_recipes:
            self._refresh_recipes()

    def _export_profile_picker(self):
        profile = ThemedMessageBox.show_buttons(
            self,
            "Export Profile",
            "Choose the type of backup you want to create.",
            ["Cancel", "Full Backup", "Move to New Device", "Meal Planning Only", "Nutrition Only"],
            kind="question",
        )
        if profile == "Full Backup":
            self._export("full")
        elif profile == "Move to New Device":
            self._export("migration")
        elif profile == "Meal Planning Only":
            self._export("planning")
        elif profile == "Nutrition Only":
            self._export("nutrition")

    def _export(self, profile: str = "full"):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export DishBoard Data", f"dishboard_{profile}_backup.json", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            include_recipes = profile in {"full", "migration", "planning"}
            include_meals = profile in {"full", "migration", "planning"}
            include_shopping = profile in {"full", "migration", "planning"}
            include_pantry = profile in {"full", "migration"}
            include_nutrition = profile in {"full", "migration", "nutrition"}
            include_settings = profile in {"full", "migration", "nutrition"}

            data = {
                "version": 2,
                "profile": profile,
                "recipes": [dict(r) for r in self._db.conn.execute("SELECT * FROM recipes").fetchall()] if include_recipes else [],
                "meal_plans": [dict(r) for r in self._db.conn.execute("SELECT * FROM meal_plans").fetchall()] if include_meals else [],
                "shopping_items": [dict(r) for r in self._db.conn.execute("SELECT * FROM shopping_items").fetchall()] if include_shopping else [],
                "pantry_items": [dict(r) for r in self._db.conn.execute("SELECT * FROM pantry_items").fetchall()] if include_pantry else [],
                "nutrition_logs": [dict(r) for r in self._db.conn.execute("SELECT * FROM nutrition_logs").fetchall()] if include_nutrition else [],
                "settings": [dict(r) for r in self._db.conn.execute("SELECT * FROM settings").fetchall()] if include_settings else [],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            counts = (
                f"{len(data['recipes'])} recipes, "
                f"{len(data['meal_plans'])} meal plan entries, "
                f"{len(data['shopping_items'])} shopping items, "
                f"{len(data['nutrition_logs'])} nutrition logs"
            )
            ThemedMessageBox.information(self, "Export complete", f"Backup saved successfully.\n\n{counts}")
        except Exception as e:
            ThemedMessageBox.critical(self, "Export failed", str(e))

    def _manage_trash(self):
        items = self._db.list_trash_items(limit=20)
        if not items:
            ThemedMessageBox.information(self, "Trash Bin", "Trash Bin is empty.")
            return
        preview_lines = []
        for it in items[:6]:
            payload = it.get("payload") or {}
            label = payload.get("title") or payload.get("name") or payload.get("custom_name") or "Item"
            preview_lines.append(f"• {it.get('entity_type', 'item')}: {str(label)[:48]}")
        choice = ThemedMessageBox.show_buttons(
            self,
            "Trash Bin",
            f"{len(items)} item(s) in Trash.\n\nRecent:\n" + "\n".join(preview_lines),
            ["Cancel", "Restore Most Recent", "Empty Trash"],
            kind="question",
        )
        if choice == "Restore Most Recent":
            restored = self._db.restore_trash_item(int(items[0]["id"]))
            if restored:
                if self._refresh_meal_plan:
                    self._refresh_meal_plan()
                if self._refresh_shopping:
                    self._refresh_shopping()
                if self._refresh_recipes:
                    self._refresh_recipes()
                ThemedMessageBox.information(self, "Trash Bin", "Restored the most recently deleted item.")
            else:
                ThemedMessageBox.warning(self, "Trash Bin", "Could not restore that item.")
        elif choice == "Empty Trash":
            removed = self._db.clear_trash()
            ThemedMessageBox.information(self, "Trash Bin", f"Removed {removed} item(s) from Trash.")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import DishBoard Backup", "", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            ThemedMessageBox.critical(self, "Import failed", f"Could not read file:\n{e}")
            return

        if "recipes" not in data and "meal_plans" not in data:
            ThemedMessageBox.warning(self, "Invalid file", "This doesn't look like a DishBoard backup.")
            return

        if not ThemedMessageBox.confirm(
            self, "Import data?",
            "This will merge the backup into your current data.\n"
            "Existing records will not be overwritten — only new items will be added.\n\nContinue?",
            confirm_text="Yes, import",
        ):
            return

        try:
            imported = {"recipes": 0, "meal_plans": 0, "shopping_items": 0, "pantry_items": 0, "nutrition_logs": 0}

            for r in data.get("recipes", []):
                try:
                    recipe_data = r
                    try:
                        parsed = json.loads(r.get("data_json") or "{}")
                        report = validate_recipe(parsed)
                        if report.get("errors"):
                            continue
                        recipe_data = dict(r)
                        recipe_data["title"] = (report.get("fixed", {}) or parsed).get("title", r.get("title", ""))
                        recipe_data["data_json"] = json.dumps(report.get("fixed", {}) or parsed)
                    except Exception:
                        recipe_data = r
                    recipe_data = sanitize_import_row("recipes", recipe_data)
                    if not recipe_data:
                        continue
                    self._db.conn.execute(
                        "INSERT OR IGNORE INTO recipes "
                        "(source_id, source, title, image_url, summary, servings, ready_mins, data_json, saved_at, is_favourite)"
                        " VALUES (:source_id, :source, :title, :image_url, :summary, :servings, :ready_mins, :data_json, :saved_at, :is_favourite)",
                        {k: recipe_data.get(k) for k in ("source_id","source","title","image_url","summary","servings","ready_mins","data_json","saved_at","is_favourite")}
                    )
                    if self._db.conn.execute("SELECT changes()").fetchone()[0]:
                        imported["recipes"] += 1
                except Exception:
                    pass

            for m in data.get("meal_plans", []):
                try:
                    m = sanitize_import_row("meal_plans", m)
                    if not m:
                        continue
                    self._db.conn.execute(
                        "INSERT OR IGNORE INTO meal_plans "
                        "(day_of_week, meal_type, recipe_id, custom_name, week_start, notes)"
                        " VALUES (:day_of_week, :meal_type, :recipe_id, :custom_name, :week_start, :notes)",
                        {k: m.get(k) for k in ("day_of_week","meal_type","recipe_id","custom_name","week_start","notes")}
                    )
                    if self._db.conn.execute("SELECT changes()").fetchone()[0]:
                        imported["meal_plans"] += 1
                except Exception:
                    pass

            for s in data.get("shopping_items", []):
                try:
                    s = sanitize_import_row("shopping_items", s)
                    if not s:
                        continue
                    self._db.conn.execute(
                        "INSERT INTO shopping_items (name, quantity, unit, checked, source, added_at)"
                        " VALUES (:name, :quantity, :unit, :checked, :source, :added_at)",
                        {k: s.get(k) for k in ("name","quantity","unit","checked","source","added_at")}
                    )
                    imported["shopping_items"] += 1
                except Exception:
                    pass

            for p in data.get("pantry_items", []):
                try:
                    p = sanitize_import_row("pantry_items", p)
                    if not p:
                        continue
                    self._db.conn.execute(
                        "INSERT INTO pantry_items (name, quantity, unit, storage, expiry_date, added_at)"
                        " VALUES (:name, :quantity, :unit, :storage, :expiry_date, :added_at)",
                        {k: p.get(k) for k in ("name", "quantity", "unit", "storage", "expiry_date", "added_at")},
                    )
                    imported["pantry_items"] += 1
                except Exception:
                    pass

            for n in data.get("nutrition_logs", []):
                try:
                    n = sanitize_import_row("nutrition_logs", n)
                    if not n:
                        continue
                    self._db.conn.execute(
                        "INSERT INTO nutrition_logs"
                        " (log_date, food_name, kcal, protein_g, carbs_g, fat_g, fiber_g, sugar_g, logged_at)"
                        " VALUES (:log_date, :food_name, :kcal, :protein_g, :carbs_g, :fat_g, :fiber_g, :sugar_g, :logged_at)",
                        {
                            k: n.get(k)
                            for k in ("log_date", "food_name", "kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "logged_at")
                        },
                    )
                    imported["nutrition_logs"] += 1
                except Exception:
                    pass

            for sv in data.get("settings", []):
                try:
                    self._db.conn.execute(
                        "INSERT OR IGNORE INTO settings (key, value) VALUES (:key, :value)",
                        {"key": sv.get("key"), "value": sv.get("value")}
                    )
                except Exception:
                    pass

            self._db.conn.commit()
            ThemedMessageBox.information(
                self, "Import complete",
                f"Import successful!\n\n"
                f"Added: {imported['recipes']} recipes, "
                f"{imported['meal_plans']} meal plan entries, "
                f"{imported['shopping_items']} shopping items, "
                f"{imported['pantry_items']} pantry items, "
                f"{imported['nutrition_logs']} nutrition logs"
            )
        except Exception as e:
            ThemedMessageBox.critical(self, "Import failed", str(e))

    def apply_theme(self, _mode):
        for name_lbl, sub_lbl in self._port_row_labels + self._row_labels:
            name_lbl.setStyleSheet(
                f"font-size: 14px; font-weight: 600;"
                f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
            )
            sub_lbl.setStyleSheet(
                f"font-size: 12px; color: {manager.c('#666666', '#777777')}; background: transparent;"
            )
        for btn in self._primary_port_btns:
            btn.setStyleSheet(_primary_button_style())
        for btn in self._secondary_port_btns:
            btn.setStyleSheet(_secondary_button_style())
        for btn in self._danger_btns:
            btn.setStyleSheet(_danger_button_style())


# ── Page: Monitoring ──────────────────────────────────────────────────────────

class _MonitoringPage(QWidget):
    """Clean user-facing monitoring page with optional advanced diagnostics."""

    def __init__(self, db: Database | None = None, parent=None):
        super().__init__(parent)
        self._db = db or get_db()
        self._sync_fn = None
        self._sync_service = None
        self._visibility_service = None
        self._advanced_visible = False
        self._metric_values: dict[str, QLabel] = {}
        self._metric_subs: dict[str, QLabel] = {}
        self._metric_cards: list[QWidget] = []
        self._muted_labels: list[QLabel] = []
        self._title_labels: list[QLabel] = []
        self._memory_summary_lbl: QLabel | None = None
        self._build()

    def set_sync_fn(self, fn):
        self._sync_fn = fn

    def set_sync_service(self, service) -> None:
        if self._sync_service is service:
            return
        if self._sync_service is not None and hasattr(self._sync_service, "runtime_status_changed"):
            try:
                self._sync_service.runtime_status_changed.disconnect(self._on_runtime_status_changed)
            except Exception:
                pass
        self._sync_service = service
        if service is not None and hasattr(service, "runtime_status_changed"):
            service.runtime_status_changed.connect(
                self._on_runtime_status_changed, Qt.ConnectionType.QueuedConnection
            )
        self.refresh()

    def set_visibility_service(self, service) -> None:
        if self._visibility_service is service:
            return
        if self._visibility_service is not None:
            try:
                self._visibility_service.snapshot_changed.disconnect(self._on_visibility_snapshot_changed)
            except Exception:
                pass
        self._visibility_service = service
        if service is not None:
            service.snapshot_changed.connect(self._on_visibility_snapshot_changed)
        self.refresh()

    def _on_runtime_status_changed(self, _status: dict) -> None:
        self.refresh()

    def _on_visibility_snapshot_changed(self, _snapshot) -> None:
        self.refresh()

    def _active_user_id(self) -> str:
        return self._db.get_setting("active_user_id", "").strip()

    def _flags_service(self):
        from utils.feature_flags import FeatureFlagService

        uid = self._active_user_id()
        svc = FeatureFlagService(self._db, uid)
        svc.ensure_defaults()
        return svc

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        # Summary card
        top_card = _card_widget()
        top_l = QVBoxLayout(top_card)
        top_l.setSpacing(12)

        title = QLabel("Monitoring")
        title.setObjectName("card-title")
        top_l.addWidget(title)

        desc = QLabel(
            "A simple health view of your data and AI usage. "
            "Advanced diagnostics are hidden by default."
        )
        desc.setObjectName("card-body")
        desc.setWordWrap(True)
        top_l.addWidget(desc)
        top_l.addWidget(_make_sep())

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        top_l.addWidget(self._status_lbl)

        self._runtime_health_lbl = QLabel("")
        self._runtime_health_lbl.setWordWrap(True)
        self._muted_labels.append(self._runtime_health_lbl)
        top_l.addWidget(self._runtime_health_lbl)

        self._analytics_status_lbl = QLabel("")
        self._analytics_status_lbl.setWordWrap(True)
        self._muted_labels.append(self._analytics_status_lbl)
        top_l.addWidget(self._analytics_status_lbl)

        self._severity_summary_lbl = QLabel("")
        self._severity_summary_lbl.setWordWrap(True)
        self._muted_labels.append(self._severity_summary_lbl)
        top_l.addWidget(self._severity_summary_lbl)

        self._attention_reasons_lbl = QLabel("")
        self._attention_reasons_lbl.setWordWrap(True)
        self._muted_labels.append(self._attention_reasons_lbl)
        top_l.addWidget(self._attention_reasons_lbl)

        self._sync_integrity_lbl = QLabel("")
        self._sync_integrity_lbl.setWordWrap(True)
        self._muted_labels.append(self._sync_integrity_lbl)
        top_l.addWidget(self._sync_integrity_lbl)

        self._waste_lbl = QLabel("")
        self._waste_lbl.setWordWrap(True)
        self._muted_labels.append(self._waste_lbl)
        top_l.addWidget(self._waste_lbl)

        metric_row_1 = QHBoxLayout()
        metric_row_1.setSpacing(10)
        for key, name in [
            ("recipes", "Recipes"),
            ("meal_plans", "Planner Slots"),
            ("pantry_items", "Kitchen Items"),
        ]:
            card, v, s = self._make_metric_card(name)
            self._metric_values[key] = v
            self._metric_subs[key] = s
            self._metric_cards.append(card)
            metric_row_1.addWidget(card, 1)
        top_l.addLayout(metric_row_1)

        metric_row_2 = QHBoxLayout()
        metric_row_2.setSpacing(10)
        for key, name in [
            ("ai_usage", "AI Today"),
            ("notifications", "Notifications"),
            ("jobs", "Background Jobs"),
        ]:
            card, v, s = self._make_metric_card(name)
            self._metric_values[key] = v
            self._metric_subs[key] = s
            self._metric_cards.append(card)
            metric_row_2.addWidget(card, 1)
        top_l.addLayout(metric_row_2)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedHeight(34)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setToolTip("Refresh all monitoring metrics")
        self._refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(self._refresh_btn)

        self._mark_read_btn = QPushButton("Mark Alerts Read")
        self._mark_read_btn.setFixedHeight(34)
        self._mark_read_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mark_read_btn.setToolTip("Mark all in-app notifications as read")
        self._mark_read_btn.clicked.connect(self._mark_notifications_read)
        btn_row.addWidget(self._mark_read_btn)

        self._advanced_btn = QPushButton("Advanced")
        self._advanced_btn.setFixedHeight(34)
        self._advanced_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._advanced_btn.setToolTip("Show technical diagnostics")
        self._advanced_btn.clicked.connect(self._toggle_advanced)
        btn_row.addWidget(self._advanced_btn)

        self._repair_btn = QPushButton("Repair Sync")
        self._repair_btn.setFixedHeight(34)
        self._repair_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._repair_btn.setToolTip("Fix orphan links and stale sync records")
        self._repair_btn.clicked.connect(self._run_integrity_repair)
        btn_row.addWidget(self._repair_btn)

        self._scan_btn = QPushButton("Integrity Scan")
        self._scan_btn.setFixedHeight(34)
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.setToolTip("Run a full ghost-data and shape validation scan")
        self._scan_btn.clicked.connect(self._run_integrity_scan)
        btn_row.addWidget(self._scan_btn)

        btn_row.addStretch()
        top_l.addLayout(btn_row)

        top_l.addWidget(_make_sep())
        actions_title = QLabel("Recommended Actions")
        actions_title.setObjectName("card-body")
        top_l.addWidget(actions_title)
        self._recommended_actions_lbl = QLabel("")
        self._recommended_actions_lbl.setWordWrap(True)
        self._muted_labels.append(self._recommended_actions_lbl)
        top_l.addWidget(self._recommended_actions_lbl)

        top_l.addWidget(_make_sep())
        freshness_title = QLabel("Module Freshness")
        freshness_title.setObjectName("card-body")
        top_l.addWidget(freshness_title)
        self._module_freshness_lbl = QLabel("")
        self._module_freshness_lbl.setWordWrap(True)
        self._muted_labels.append(self._module_freshness_lbl)
        top_l.addWidget(self._module_freshness_lbl)

        top_l.addWidget(_make_sep())
        recent_title = QLabel("Recent Changes")
        recent_title.setObjectName("card-body")
        top_l.addWidget(recent_title)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self._module_filter = QComboBox()
        self._module_filter.addItems(["All modules", "System", "Recipes", "Planner", "Shopping", "Pantry", "Nutrition", "Dishy"])
        self._module_filter.currentIndexChanged.connect(self.refresh)
        filter_row.addWidget(self._module_filter)
        self._severity_filter = QComboBox()
        self._severity_filter.addItems(["All severities", "Critical", "Warning", "Info", "Quiet"])
        self._severity_filter.currentIndexChanged.connect(self.refresh)
        filter_row.addWidget(self._severity_filter)
        self._activity_filter = QComboBox()
        self._activity_filter.addItems(["All activity", "Sync", "AI", "Job", "User changes", "Notifications"])
        self._activity_filter.currentIndexChanged.connect(self.refresh)
        filter_row.addWidget(self._activity_filter)
        filter_row.addStretch()
        top_l.addLayout(filter_row)
        self._recent_changes_lbl = QLabel("")
        self._recent_changes_lbl.setWordWrap(True)
        self._muted_labels.append(self._recent_changes_lbl)
        top_l.addWidget(self._recent_changes_lbl)

        top_l.addWidget(_make_sep())
        active_title = QLabel("Active Work")
        active_title.setObjectName("card-body")
        top_l.addWidget(active_title)
        self._active_work_lbl = QLabel("")
        self._active_work_lbl.setWordWrap(True)
        self._muted_labels.append(self._active_work_lbl)
        top_l.addWidget(self._active_work_lbl)
        outer.addWidget(top_card)

        # Controls card
        controls_card = _card_widget()
        controls_l = QVBoxLayout(controls_card)
        controls_l.setSpacing(12)
        controls_title = QLabel("Privacy & Controls")
        controls_title.setObjectName("card-title")
        controls_l.addWidget(controls_title)

        controls_desc = QLabel(
            "Choose what runs in the background. Changes apply immediately."
        )
        controls_desc.setObjectName("card-body")
        controls_desc.setWordWrap(True)
        controls_l.addWidget(controls_desc)
        controls_l.addWidget(_make_sep())

        self._notif_toggle = QCheckBox("In-app notifications")
        self._notif_toggle.toggled.connect(self._on_notif_toggled)
        controls_l.addWidget(self._control_row(
            self._notif_toggle,
            "Get expiry and meal reminders inside DishBoard.",
        ))

        self._analytics_toggle = QCheckBox("Usage analytics")
        self._analytics_toggle.toggled.connect(self._on_analytics_toggled)
        controls_l.addWidget(self._control_row(
            self._analytics_toggle,
            "Helps improve product quality with anonymous event stats.",
        ))

        self._crash_toggle = QCheckBox("Crash reporting")
        self._crash_toggle.toggled.connect(self._on_crash_toggled)
        controls_l.addWidget(self._control_row(
            self._crash_toggle,
            "Sends error traces when something fails.",
        ))

        self._memory_toggle = QCheckBox("Dishy memory context")
        self._memory_toggle.toggled.connect(self._on_memory_toggled)
        controls_l.addWidget(self._control_row(
            self._memory_toggle,
            "Lets Dishy use your recent app context for better answers.",
        ))

        controls_l.addWidget(_make_sep())
        memory_title = QLabel("Dishy Memory")
        memory_title.setObjectName("card-body")
        controls_l.addWidget(memory_title)
        self._memory_summary_lbl = QLabel("")
        self._memory_summary_lbl.setWordWrap(True)
        self._muted_labels.append(self._memory_summary_lbl)
        controls_l.addWidget(self._memory_summary_lbl)
        memory_btn_row = QHBoxLayout()
        memory_btn_row.setSpacing(8)
        self._memory_refresh_btn = QPushButton("Refresh Memory View")
        self._memory_refresh_btn.setFixedHeight(34)
        self._memory_refresh_btn.clicked.connect(self.refresh)
        memory_btn_row.addWidget(self._memory_refresh_btn)
        self._memory_clear_btn = QPushButton("Clear Dishy Chat Memory")
        self._memory_clear_btn.setFixedHeight(34)
        self._memory_clear_btn.clicked.connect(self._clear_dishy_memory)
        memory_btn_row.addWidget(self._memory_clear_btn)
        memory_btn_row.addStretch()
        controls_l.addLayout(memory_btn_row)

        outer.addWidget(controls_card)

        # Advanced card (collapsed by default)
        self._advanced_card = _card_widget()
        adv_l = QVBoxLayout(self._advanced_card)
        adv_l.setSpacing(10)
        adv_title = QLabel("Advanced Diagnostics")
        adv_title.setObjectName("card-title")
        adv_l.addWidget(adv_title)
        adv_l.addWidget(_make_sep())

        self._advanced_summary = QLabel("")
        self._advanced_summary.setWordWrap(True)
        self._muted_labels.append(self._advanced_summary)
        adv_l.addWidget(self._advanced_summary)

        self._remote_flags_btn = QPushButton("Refresh Cloud Flags")
        self._remote_flags_btn.setFixedHeight(34)
        self._remote_flags_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remote_flags_btn.clicked.connect(self._refresh_remote_flags)
        adv_l.addWidget(self._remote_flags_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self._advanced_card.setVisible(False)
        outer.addWidget(self._advanced_card)

        outer.addStretch()
        self.apply_theme(manager.mode)
        self.refresh()

    def _make_metric_card(self, title: str) -> tuple[QWidget, QLabel, QLabel]:
        card = QWidget()
        l = QVBoxLayout(card)
        l.setContentsMargins(12, 10, 12, 10)
        l.setSpacing(4)

        t = QLabel(title)
        t.setStyleSheet(
            f"font-size: 11px; font-weight: 700; letter-spacing: 0.3px;"
            f" color: {manager.c('#8d8d8d', '#6f6f6f')}; background: transparent;"
        )
        self._muted_labels.append(t)
        l.addWidget(t)

        value = QLabel("0")
        value.setStyleSheet(
            f"font-size: 20px; font-weight: 700;"
            f" color: {manager.c('#efefef', '#111111')}; background: transparent;"
        )
        self._title_labels.append(value)
        l.addWidget(value)

        sub = QLabel("")
        sub.setStyleSheet(
            f"font-size: 11px; color: {manager.c('#888888', '#666666')}; background: transparent;"
        )
        self._muted_labels.append(sub)
        l.addWidget(sub)

        return card, value, sub

    def _control_row(self, checkbox: QCheckBox, description: str) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(3)
        l.addWidget(checkbox)
        sub = QLabel(description)
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#777777', '#777777')}; background: transparent;"
        )
        self._muted_labels.append(sub)
        l.addWidget(sub)
        return w

    def _toggle_advanced(self):
        self._advanced_visible = not self._advanced_visible
        self._advanced_card.setVisible(self._advanced_visible)
        self._advanced_btn.setText("Hide Advanced" if self._advanced_visible else "Advanced")

    def _on_notif_toggled(self, checked: bool):
        self._db.set_setting("in_app_notifications_enabled", "1" if checked else "0")
        if self._sync_fn:
            self._sync_fn()

    def _on_analytics_toggled(self, checked: bool):
        self._db.set_setting("telemetry_enabled", "1" if checked else "0")
        self._db.set_setting("posthog_enabled", "1" if checked else "0")
        if self._sync_fn:
            self._sync_fn()

    def _on_crash_toggled(self, checked: bool):
        self._db.set_setting("sentry_enabled", "1" if checked else "0")
        if self._sync_fn:
            self._sync_fn()

    def _on_memory_toggled(self, checked: bool):
        svc = self._flags_service()
        svc.set_user("dishy_memory_context", checked)
        if self._sync_fn:
            self._sync_fn()

    def _clear_dishy_memory(self):
        self._db.clear_dishy_history()
        if self._sync_fn:
            self._sync_fn()
        self.refresh()
        ThemedMessageBox.information(
            self,
            "Dishy chat memory cleared",
            "Saved Dishy chat history was removed. Profile, recipes, planner, pantry, and nutrition data are unchanged.",
        )

    def _refresh_remote_flags(self):
        svc = self._flags_service()
        count, reason = svc.refresh_remote_from_supabase()
        ThemedMessageBox.information(
            self,
            "Cloud flags refreshed",
            f"Cached {count} row(s).\nStatus: {reason}",
        )
        self.refresh()

    def _mark_notifications_read(self):
        from utils.notifications import mark_all_read

        changed = mark_all_read(self._db, self._active_user_id())
        if changed and self._sync_fn:
            self._sync_fn()
        self.refresh()

    def _run_integrity_repair(self):
        handle = None
        if self._visibility_service is not None:
            handle = self._visibility_service.start_work(
                "monitoring.integrity.repair",
                "job",
                "system",
                "Repairing sync integrity",
                "Re-linking meal slots and clearing orphan sync state.",
                timeout_seconds=120,
                attention_reason="job_running",
            )
        try:
            report = self._db.run_sync_integrity_repair()
            if handle is not None:
                handle.finish()
            ThemedMessageBox.information(
                self,
                "Integrity repair complete",
                f"Re-linked meal slots: {report.get('linked_slots', 0)}\n"
                f"Removed orphan slots: {report.get('removed_orphans', 0)}",
            )
            if self._sync_fn:
                self._sync_fn()
            self.refresh()
        except Exception as exc:
            if handle is not None:
                handle.fail(str(exc))
            raise

    def _run_integrity_scan(self):
        handle = None
        if self._visibility_service is not None:
            handle = self._visibility_service.start_work(
                "monitoring.integrity.scan",
                "job",
                "system",
                "Running integrity scan",
                "Scanning sync state and table shapes for consistency issues.",
                timeout_seconds=120,
                attention_reason="job_running",
            )
        try:
            report = self._db.run_integrity_scan()
            if handle is not None:
                handle.finish()
            sync = report.get("sync", {}) or {}
            issues = report.get("table_issues", {}) or {}
            issue_count = int(report.get("issue_count", 0) or 0)
            status = "Healthy" if report.get("healthy") else "Needs attention"
            detail_lines = [
                f"Status: {status}",
                "",
                f"Issue count: {issue_count}",
                f"Pending tombstones: {int(sync.get('pending_tombstones', 0) or 0)}",
                f"Orphan meal slots: {int(sync.get('orphan_meal_slots', 0) or 0)}",
                "",
                "Table checks:",
                f"- Recipes with empty title: {int(issues.get('recipes_empty_title', 0) or 0)}",
                f"- Shopping items with empty name: {int(issues.get('shopping_empty_name', 0) or 0)}",
                f"- Pantry items with empty name: {int(issues.get('pantry_empty_name', 0) or 0)}",
                f"- Nutrition rows missing core fields: {int(issues.get('nutrition_missing_core', 0) or 0)}",
                f"- Dishy chat rows missing core fields: {int(issues.get('dishy_chat_missing_core', 0) or 0)}",
                f"- Meal slots with invalid day/type/week: {int(issues.get('meal_slots_invalid_shape', 0) or 0)}",
                f"- Meal slot duplicate keys: {int(issues.get('meal_slots_duplicate_keys', 0) or 0)}",
            ]
            ThemedMessageBox.information(
                self,
                "Integrity scan report",
                "\n".join(detail_lines),
            )
            self.refresh()
        except Exception as exc:
            if handle is not None:
                handle.fail(str(exc))
            raise

    def refresh(self):
        from utils.ai_limits import get_daily_limit, get_usage, utc_day_str
        from utils.notifications import unread_count
        from utils.startup_health import get_last_health_report
        from utils.telemetry import get_analytics_status
        from urllib.parse import urlparse

        uid = self._active_user_id()
        counts = {
            "recipes": self._db.get_table_count("recipes"),
            "meal_plans": self._db.get_table_count("meal_plans"),
            "pantry_items": self._db.get_table_count("pantry_items"),
            "shopping_items": self._db.get_table_count("shopping_items"),
        }

        # AI usage + notifications
        usage = get_usage(self._db, uid, utc_day_str()) if uid else {"request_count": 0, "blocked_count": 0}
        limit = get_daily_limit(self._db)
        used = int(usage.get("request_count", 0) or 0)
        blocked = int(usage.get("blocked_count", 0) or 0)
        unread = unread_count(self._db, uid)

        # Jobs/telemetry summaries
        jobs = self._db.list_workflow_jobs(limit=20)
        running = sum(1 for j in jobs if str(j.get("status", "")) == "running")
        errored = sum(1 for j in jobs if str(j.get("status", "")) == "error")
        events = self._db.get_telemetry_events(uid, limit=100) if uid else []
        runtime = {}
        if self._sync_service is not None and hasattr(self._sync_service, "runtime_status"):
            try:
                runtime = self._sync_service.runtime_status() or {}
            except Exception:
                runtime = {}
        snapshot = None
        if self._visibility_service is not None:
            try:
                snapshot = self._visibility_service.snapshot()
            except Exception:
                snapshot = None
        startup_report = get_last_health_report(self._db)
        analytics = get_analytics_status(self._db, uid)

        # Headline status
        short_uid = (uid[:8] + "…") if len(uid) > 8 else (uid or "not signed in")
        health = "Healthy"
        summary_line = "System status: Healthy"
        runtime_headline, runtime_detail = describe_sync_runtime(runtime)
        if snapshot is not None:
            headline, detail = describe_snapshot(snapshot)
            health = headline
            summary_line = detail
            runtime_headline, runtime_detail = describe_sync_runtime(snapshot.sync_runtime)
        self._status_lbl.setText(
            f"Account: {short_uid}  |  {health}"
        )
        self._runtime_health_lbl.setText(
            f"{summary_line} · "
            f"Cloud sync: {runtime_headline} · "
            f"startup auto-repair: "
            f"tombstones={int(startup_report.get('invalid_tombstones_removed', 0) or 0)}, "
            f"slots fixed={int(startup_report.get('linked_meal_slots', 0) or 0)}, "
            f"stale slots removed="
            f"{int(startup_report.get('removed_orphan_slots', 0) or 0) + int(startup_report.get('removed_stale_unlinked_slots', 0) or 0)}"
        )
        host = str(analytics.get("host") or "").strip()
        host_label = urlparse(host).netloc or host or "n/a"
        if analytics.get("connected"):
            analytics_state = "Connected"
        elif not analytics.get("enabled"):
            analytics_state = "Disabled in settings"
        elif not analytics.get("posthog_enabled"):
            analytics_state = "PostHog disabled"
        elif not analytics.get("has_api_key"):
            analytics_state = "Missing API key"
        else:
            analytics_state = "Not connected"
        self._analytics_status_lbl.setText(
            f"Analytics: {analytics_state} · host={host_label} · "
            f"last event={analytics.get('last_event_at') or 'none yet'}"
        )
        if snapshot is not None:
            reasons = ", ".join(reason.replace("_", " ") for reason in snapshot.attention_reasons) or "none"
            self._severity_summary_lbl.setText(
                f"Severity: {snapshot.severity.title()} · overall state: {snapshot.overall_state.replace('_', ' ')}"
            )
            self._attention_reasons_lbl.setText(f"Why you're seeing this: {reasons}")
            if snapshot.recommended_actions:
                self._recommended_actions_lbl.setText(
                    " · ".join(action.label for action in snapshot.recommended_actions)
                )
            else:
                self._recommended_actions_lbl.setText("No actions needed right now.")
        else:
            self._severity_summary_lbl.setText("Severity: n/a")
            self._attention_reasons_lbl.setText("Why you're seeing this: unavailable")
            self._recommended_actions_lbl.setText("No actions available.")

        integrity = self._db.get_sync_integrity_report()
        pending_unsynced = sum(int(v or 0) for v in (integrity.get("unsynced_rows") or {}).values())
        self._sync_integrity_lbl.setText(
            f"Sync integrity: tombstones={integrity.get('pending_tombstones', 0)} · "
            f"unsynced rows={pending_unsynced} · "
            f"orphan slots={integrity.get('orphan_meal_slots', 0)}"
        )
        risk = self._db.get_expiry_risk_summary()
        waste_30d = self._db.get_pantry_waste_summary(days=30)
        top_waste = self._db.get_top_wasted_items(days=30, limit=3)
        if top_waste:
            top_line = ", ".join(str(r.get("item_name") or "") for r in top_waste if str(r.get("item_name") or "").strip())
            suggestion = f" · buy less of: {top_line}"
        else:
            suggestion = ""
        self._waste_lbl.setText(
            f"Pantry insights: expired={risk.get('expired', 0)} · "
            f"expiring soon={risk.get('expiring_soon', 0)} · "
            f"at risk value≈£{risk.get('estimated_value_at_risk', 0):.2f} · "
            f"wasted 30d≈£{waste_30d.get('estimated_value', 0):.2f}"
            f"{suggestion}"
        )

        if snapshot is not None:
            freshness_lines = []
            for item in snapshot.module_freshness:
                confidence = " · low confidence" if item.confidence == "weak" else ""
                freshness_lines.append(
                    f"{item.label}: {item.state}{confidence} · {item.detail} · age={item.freshness_age_seconds}s · unsynced={item.unsynced_count}"
                )
            self._module_freshness_lbl.setText("\n".join(freshness_lines[:7]))

            module_filter = self._module_filter.currentText()
            severity_filter = self._severity_filter.currentText().lower().replace(" severities", "").strip()
            activity_filter = self._activity_filter.currentText()
            filtered_digest = []
            for item in snapshot.feed_summary:
                if module_filter != "All modules" and item.module != module_filter.lower():
                    continue
                if severity_filter != "all" and item.severity != severity_filter:
                    continue
                if activity_filter == "Sync" and item.activity_type != "sync":
                    continue
                if activity_filter == "AI" and item.activity_type != "ai":
                    continue
                if activity_filter == "Job" and item.activity_type != "job":
                    continue
                if activity_filter == "User changes" and item.activity_type != "user_change":
                    continue
                if activity_filter == "Notifications" and item.activity_type != "notification":
                    continue
                filtered_digest.append(item)
            recent_lines = []
            for item in filtered_digest[:10]:
                count = f" ×{item.count}" if item.count > 1 else ""
                detail = f" · {item.detail}" if item.detail else ""
                recent_lines.append(f"[{item.severity}] {item.title}{count}{detail}")
            self._recent_changes_lbl.setText("\n".join(recent_lines) or "No matching changes for the current filters.")

            if snapshot.active_work:
                lines = []
                for work in snapshot.active_work[:6]:
                    lines.append(f"{work.title} · {work.detail} · started {_age_seconds(work.started_at)}s ago")
                self._active_work_lbl.setText("\n".join(lines))
            else:
                self._active_work_lbl.setText("No active background work.")
        else:
            self._module_freshness_lbl.setText("Visibility service unavailable.")
            self._recent_changes_lbl.setText("Recent changes will appear once visibility is active.")
            self._active_work_lbl.setText("Active work will appear once visibility is active.")

        self._metric_values["recipes"].setText(str(counts["recipes"]))
        self._metric_subs["recipes"].setText("Saved")
        self._metric_values["meal_plans"].setText(str(counts["meal_plans"]))
        self._metric_subs["meal_plans"].setText("Active slots")
        self._metric_values["pantry_items"].setText(str(counts["pantry_items"]))
        self._metric_subs["pantry_items"].setText("Pantry/Fridge/Freezer")
        self._metric_values["ai_usage"].setText(f"{used}/{limit}")
        self._metric_subs["ai_usage"].setText("Daily requests")
        self._metric_values["notifications"].setText(str(unread))
        self._metric_subs["notifications"].setText("Unread")
        self._metric_values["jobs"].setText(str(max(0, len(jobs) - errored)))
        self._metric_subs["jobs"].setText(f"{errored} errors")

        self._advanced_summary.setText(
            f"Background jobs: total={len(jobs)}, running={running}, errors={errored}\n"
            f"Telemetry events shown (latest): {len(events)}\n"
            f"AI blocked today: {blocked}\n"
            f"Sync resilience: retry_in={int(runtime.get('retry_in_seconds', 0) or 0)}s, circuit_open={bool(runtime.get('circuit_open'))}, "
            f"last_success={runtime.get('last_success_at') or 'n/a'}, "
            f"last_failure={runtime.get('last_failure_at') or 'n/a'}"
        )
        memory = memory_source_summary(self._db)
        if self._memory_summary_lbl:
            counts = memory.get("counts", {})
            self._memory_summary_lbl.setText(
                f"Dishy can currently draw from profile={counts.get('profile', 0)}, recipes={counts.get('recipe', 0)}, "
                f"planner={counts.get('meal_plan', 0)}, pantry={counts.get('pantry', 0)}, shopping={counts.get('shopping', 0)}, "
                f"nutrition={counts.get('nutrition', 0)}, chat snippets={counts.get('chat', 0)} across "
                f"{memory.get('chat_sessions', 0)} saved chat session(s)."
            )

        # Toggle states
        svc = self._flags_service()
        for box, key, parser in [
            (self._notif_toggle, "in_app_notifications_enabled", lambda v: v not in {"0", "false", "off", "no"}),
            (self._analytics_toggle, "telemetry_enabled", lambda v: v not in {"0", "false", "off", "no"}),
            (self._crash_toggle, "sentry_enabled", lambda v: v not in {"0", "false", "off", "no"}),
        ]:
            raw = self._db.get_setting(key, "1").strip().lower()
            box.blockSignals(True)
            box.setChecked(parser(raw))
            box.blockSignals(False)

        self._memory_toggle.blockSignals(True)
        self._memory_toggle.setChecked(svc.is_enabled("dishy_memory_context", default=True))
        self._memory_toggle.blockSignals(False)

    def apply_theme(self, _mode):
        for card in self._metric_cards:
            card.setStyleSheet(_subtle_surface_style())

        self._status_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600;"
            f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        self._advanced_summary.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#777777', '#666666')}; background: transparent;"
        )
        self._runtime_health_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#8a8a8a', '#666666')}; background: transparent;"
        )
        self._analytics_status_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#8a8a8a', '#666666')}; background: transparent;"
        )
        self._sync_integrity_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#8a8a8a', '#666666')}; background: transparent;"
        )
        self._waste_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#8a8a8a', '#666666')}; background: transparent;"
        )

        for lbl in self._title_labels:
            lbl.setStyleSheet(
                f"font-size: 20px; font-weight: 700;"
                f" color: {manager.c('#efefef', '#111111')}; background: transparent;"
            )
        for lbl in self._muted_labels:
            # keep per-label font sizes from initial build, only update color
            css = lbl.styleSheet()
            if "color:" in css:
                # Preserve size/weight; override only color for theme
                css = css.split("color:")[0] + f"color: {manager.c('#888888', '#666666')}; background: transparent;"
                lbl.setStyleSheet(css)

        check_style = _checkbox_style()
        for cb in [self._notif_toggle, self._analytics_toggle, self._crash_toggle, self._memory_toggle]:
            cb.setStyleSheet(check_style)

        self._refresh_btn.setStyleSheet(_primary_button_style())
        secondary_style = _secondary_button_style()
        self._mark_read_btn.setStyleSheet(secondary_style)
        self._advanced_btn.setStyleSheet(secondary_style)
        self._repair_btn.setStyleSheet(secondary_style)
        self._scan_btn.setStyleSheet(secondary_style)
        self._remote_flags_btn.setStyleSheet(secondary_style)

        self.refresh()


# ── Page: Version History ─────────────────────────────────────────────────────

class _VersionHistoryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._update_fns: list = []
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        card = _card_widget()
        layout = QVBoxLayout(card)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        title = QLabel("Version History")
        title.setObjectName("card-title")
        header_row.addWidget(title)
        header_row.addStretch()
        badge = QLabel(APP_VERSION)
        badge.setStyleSheet(
            "background-color: rgba(255,107,53,0.15); color: #ff6b35;"
            " border: 1px solid rgba(255,107,53,0.4); border-radius: 8px;"
            " font-size: 11px; font-weight: 700; padding: 2px 8px;"
        )
        header_row.addWidget(badge)
        layout.addLayout(header_row)

        desc = QLabel("A full log of every update to DishBoard.")
        desc.setObjectName("card-body")
        layout.addWidget(desc)
        layout.addWidget(_make_sep())
        layout.addSpacing(4)

        for i, entry in enumerate(VERSION_HISTORY):
            is_latest = i == 0

            ver_row = QHBoxLayout()
            ver_row.setSpacing(10)

            ver_lbl = QLabel(entry["version"])
            ver_lbl.setStyleSheet(
                ("font-size: 13px; font-weight: 800; color: #ff6b35; background: transparent;"
                 if is_latest else
                 f"font-size: 13px; font-weight: 700;"
                 f" color: {manager.c('#c0c0c0', '#333333')}; background: transparent;")
            )
            ver_lbl.setFixedWidth(44)
            if not is_latest:
                self._update_fns.append(
                    lambda l=ver_lbl: l.setStyleSheet(
                        f"font-size: 13px; font-weight: 700;"
                        f" color: {manager.c('#c0c0c0', '#333333')}; background: transparent;"
                    )
                )
            ver_row.addWidget(ver_lbl)

            title_lbl = QLabel(entry["title"])
            title_lbl.setStyleSheet(
                f"font-size: 13px; font-weight: 600;"
                f" color: {manager.c('#e8e8e8', '#1a1a1a')}; background: transparent;"
            )
            self._update_fns.append(
                lambda l=title_lbl: l.setStyleSheet(
                    f"font-size: 13px; font-weight: 600;"
                    f" color: {manager.c('#e8e8e8', '#1a1a1a')}; background: transparent;"
                )
            )
            ver_row.addWidget(title_lbl, 1)

            if is_latest:
                new_badge = QLabel("Latest")
                new_badge.setStyleSheet(
                    "background-color: rgba(255,107,53,0.12); color: #ff6b35;"
                    " border: 1px solid rgba(255,107,53,0.3); border-radius: 6px;"
                    " font-size: 10px; font-weight: 700; padding: 1px 7px;"
                )
                ver_row.addWidget(new_badge)

            layout.addLayout(ver_row)

            for change in entry["changes"]:
                bullet_row = QHBoxLayout()
                bullet_row.setContentsMargins(44, 0, 0, 0)
                bullet_row.setSpacing(6)
                dot = QLabel("•")
                dot.setStyleSheet(
                    f"color: {manager.c('#555555', '#aaaaaa')}; background: transparent; font-size: 12px;"
                )
                dot.setFixedWidth(10)
                self._update_fns.append(
                    lambda l=dot: l.setStyleSheet(
                        f"color: {manager.c('#555555', '#aaaaaa')}; background: transparent; font-size: 12px;"
                    )
                )
                text = QLabel(change)
                text.setWordWrap(True)
                text.setStyleSheet(
                    f"font-size: 12px; color: {manager.c('#888888', '#666666')}; background: transparent;"
                )
                self._update_fns.append(
                    lambda l=text: l.setStyleSheet(
                        f"font-size: 12px; color: {manager.c('#888888', '#666666')}; background: transparent;"
                    )
                )
                bullet_row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
                bullet_row.addWidget(text, 1)
                layout.addLayout(bullet_row)

            layout.addSpacing(2)
            if i < len(VERSION_HISTORY) - 1:
                layout.addWidget(_make_sep())
                layout.addSpacing(4)

        outer.addWidget(card)
        outer.addStretch()

    def apply_theme(self, _mode):
        for fn in self._update_fns:
            fn()


# ── Page: Nutrition Goals ─────────────────────────────────────────────────────

class _NutritionGoalsPage(QWidget):
    def __init__(self, db: Database | None = None, parent=None):
        super().__init__(parent)
        self._db = db or get_db()
        self._fields: dict[str, QLineEdit] = {}
        self._macro_worker = None  # prevents Worker GC before signals fire
        self._sync_fn = None
        self._auto_note: "QLabel | None" = None
        self._reset_btn: "QPushButton | None" = None
        self._macro_name_labels: list = []
        self._macro_guide_labels: list = []
        self._macro_unit_labels: list = []
        self._metrics_title_lbl: "QLabel | None" = None
        self._metrics_hint_lbl: "QLabel | None" = None
        self._metrics_status_lbl: "QLabel | None" = None
        self._me_name_lbl: "QLabel | None" = None
        self._me_box: "QWidget | None" = None
        self._pair_box: "QWidget | None" = None
        self._pair_name_lbl: "QLabel | None" = None
        self._body_height_input: "QLineEdit | None" = None
        self._body_weight_input: "QLineEdit | None" = None
        self._pair_name_input: "QLineEdit | None" = None
        self._pair_height_input: "QLineEdit | None" = None
        self._pair_weight_input: "QLineEdit | None" = None
        self._recommend_btn: "QPushButton | None" = None
        self._recommend_pair_btn: "QPushButton | None" = None
        self._build()

    def _build(self):
        from utils.macro_goals import MACRO_SPECS, MACRO_GUIDES, get_macro_goals, set_macro_goal

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        card = _card_widget()
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        title = QLabel("Daily Nutrition Goals")
        title.setObjectName("card-title")
        layout.addWidget(title)

        desc = QLabel(
            "Set your daily targets for each macro. "
            "These control the progress rings on the Nutrition page and Home dashboard."
        )
        desc.setObjectName("card-body")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Dishy AI badge + explanation
        badge_row = QHBoxLayout()
        badge_row.setSpacing(10)
        badge_row.setContentsMargins(0, 4, 0, 0)
        dishy_badge = QLabel("✦ Dishy AI")
        dishy_badge.setStyleSheet(
            "background: rgba(52,211,153,0.12); color: #34d399;"
            " border: 1px solid rgba(52,211,153,0.3); border-radius: 10px;"
            " font-size: 11px; font-weight: 700; padding: 2px 10px;"
        )
        dishy_badge.setFixedHeight(22)
        auto_note = QLabel(
            "Editing Calories, Protein, Carbs, or Fat will intelligently rebalance the other goals "
            "using Dishy AI and your dietary preferences."
        )
        auto_note.setWordWrap(True)
        auto_note.setStyleSheet(
            f"color: {manager.c('#888888', '#777777')}; background: transparent; font-size: 12px;"
        )
        self._auto_note = auto_note
        badge_row.addWidget(dishy_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        badge_row.addWidget(auto_note, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(badge_row)

        layout.addWidget(_make_sep())

        self._metrics_title_lbl = QLabel("Body Metrics")
        self._metrics_title_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        layout.addWidget(self._metrics_title_lbl)

        self._metrics_hint_lbl = QLabel(
            "Add height and weight so Dishy can personalise recommendations and macro targets."
        )
        self._metrics_hint_lbl.setWordWrap(True)
        self._metrics_hint_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666666', '#777777')}; background: transparent;"
        )
        layout.addWidget(self._metrics_hint_lbl)

        self._me_box = QWidget()
        self._me_box.setStyleSheet(_subtle_surface_style())
        me_layout = QVBoxLayout(self._me_box)
        me_layout.setContentsMargins(12, 10, 12, 10)
        me_layout.setSpacing(8)

        me_name = self._db.get_setting("user_name", "").strip() or "You"
        self._me_name_lbl = QLabel(f"{me_name} (Profile 1)")
        self._me_name_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {manager.c('#d8d8d8', '#222222')}; background: transparent;"
        )
        me_layout.addWidget(self._me_name_lbl)

        me_row = QHBoxLayout()
        me_row.setContentsMargins(0, 0, 0, 0)
        me_row.setSpacing(10)
        self._body_height_input = QLineEdit()
        self._body_height_input.setPlaceholderText("Height (cm)")
        self._body_height_input.setFixedHeight(36)
        self._body_height_input.setFixedWidth(130)
        self._body_height_input.editingFinished.connect(self._save_body_metrics)
        self._body_weight_input = QLineEdit()
        self._body_weight_input.setPlaceholderText("Weight (kg)")
        self._body_weight_input.setFixedHeight(36)
        self._body_weight_input.setFixedWidth(130)
        self._body_weight_input.editingFinished.connect(self._save_body_metrics)
        me_row.addWidget(self._body_height_input)
        me_row.addWidget(self._body_weight_input)
        me_row.addStretch()
        me_layout.addLayout(me_row)
        layout.addWidget(self._me_box)

        self._pair_box = QWidget()
        self._pair_box.setStyleSheet(_subtle_surface_style())
        pair_layout = QVBoxLayout(self._pair_box)
        pair_layout.setContentsMargins(12, 10, 12, 10)
        pair_layout.setSpacing(8)

        self._pair_name_lbl = QLabel("Linked account (Profile 2)")
        self._pair_name_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {manager.c('#d8d8d8', '#222222')}; background: transparent;"
        )
        pair_layout.addWidget(self._pair_name_lbl)

        pair_row = QHBoxLayout()
        pair_row.setContentsMargins(0, 0, 0, 0)
        pair_row.setSpacing(10)
        self._pair_name_input = QLineEdit()
        self._pair_name_input.setPlaceholderText("Name")
        self._pair_name_input.setFixedHeight(36)
        self._pair_name_input.setFixedWidth(150)
        self._pair_name_input.editingFinished.connect(self._save_body_metrics)
        self._pair_height_input = QLineEdit()
        self._pair_height_input.setPlaceholderText("Height (cm)")
        self._pair_height_input.setFixedHeight(36)
        self._pair_height_input.setFixedWidth(130)
        self._pair_height_input.editingFinished.connect(self._save_body_metrics)
        self._pair_weight_input = QLineEdit()
        self._pair_weight_input.setPlaceholderText("Weight (kg)")
        self._pair_weight_input.setFixedHeight(36)
        self._pair_weight_input.setFixedWidth(130)
        self._pair_weight_input.editingFinished.connect(self._save_body_metrics)
        pair_row.addWidget(self._pair_name_input)
        pair_row.addWidget(self._pair_height_input)
        pair_row.addWidget(self._pair_weight_input)
        pair_row.addStretch()
        pair_layout.addLayout(pair_row)
        layout.addWidget(self._pair_box)

        rec_row = QHBoxLayout()
        rec_row.setContentsMargins(0, 2, 0, 2)
        rec_row.setSpacing(10)
        self._recommend_btn = QPushButton("Recommend My Goals")
        self._recommend_btn.setFixedHeight(34)
        self._recommend_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._recommend_btn.clicked.connect(lambda: self._recommend_goals_from_metrics(False))
        self._recommend_pair_btn = QPushButton("Recommend Shared Goal")
        self._recommend_pair_btn.setFixedHeight(34)
        self._recommend_pair_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._recommend_pair_btn.clicked.connect(lambda: self._recommend_goals_from_metrics(True))
        rec_row.addWidget(self._recommend_btn)
        rec_row.addWidget(self._recommend_pair_btn)
        rec_row.addStretch()
        layout.addLayout(rec_row)

        self._metrics_status_lbl = QLabel("")
        self._metrics_status_lbl.setWordWrap(True)
        self._metrics_status_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#777777', '#666666')}; background: transparent;"
        )
        layout.addWidget(self._metrics_status_lbl)

        self._load_body_metrics()
        self._refresh_body_metric_visibility()

        goals = get_macro_goals(self._db)

        for key, label, _default, unit, colour in MACRO_SPECS:
            layout.addWidget(_make_sep())

            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 8, 0, 8)
            row_l.setSpacing(14)

            # Colour dot
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {colour}; background: transparent; font-size: 18px;")
            dot.setFixedWidth(22)
            row_l.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)

            # Label + guide hint
            text_col = QVBoxLayout()
            text_col.setSpacing(3)
            name_lbl = QLabel(label)
            name_lbl.setStyleSheet(
                f"font-size: 14px; font-weight: 600;"
                f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
            )
            self._macro_name_labels.append(name_lbl)
            guide_lbl = QLabel(MACRO_GUIDES[key])
            guide_lbl.setWordWrap(True)
            guide_lbl.setStyleSheet(
                f"font-size: 12px; color: {manager.c('#666666', '#777777')}; background: transparent;"
            )
            self._macro_guide_labels.append(guide_lbl)
            text_col.addWidget(name_lbl)
            text_col.addWidget(guide_lbl)
            row_l.addLayout(text_col, 1)

            # Input field + unit label
            field = QLineEdit()
            field.setFixedWidth(90)
            field.setFixedHeight(36)
            field.setAlignment(Qt.AlignmentFlag.AlignRight)
            field.setText(str(int(goals[key])))
            self._fields[key] = field

            def _save(k=key, f=field):
                try:
                    val = max(1.0, float(f.text().strip()))
                    f.setText(str(int(val)))
                    set_macro_goal(self._db, k, val)
                    if self._sync_fn:
                        self._sync_fn()
                except ValueError:
                    pass

            if key in {"kcal", "protein_g", "carbs_g", "fat_g"}:
                field.editingFinished.connect(lambda k=key: self._on_core_macro_edited(k))
            else:
                field.editingFinished.connect(_save)

            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet(
                f"color: {manager.c('#888888', '#666666')}; background: transparent; font-size: 13px;"
            )
            self._macro_unit_labels.append(unit_lbl)

            row_l.addWidget(field)
            row_l.addWidget(unit_lbl)
            layout.addWidget(row_w)

        layout.addWidget(_make_sep())

        # Reset to defaults button
        reset_row = QHBoxLayout()
        self._reset_btn = QPushButton("Reset to defaults")
        reset_btn = self._reset_btn
        reset_btn.setFixedHeight(34)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {manager.c('rgba(255,255,255,0.04)', 'rgba(0,0,0,0.04)')};"
            f"  color: {manager.c('#888888', '#555555')};"
            f"  border: 1px solid {manager.c('#2c2c2c', '#cccccc')}; border-radius: 8px;"
            "  font-size: 12px; font-weight: 600; padding: 0 14px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {manager.c('rgba(255,255,255,0.08)', 'rgba(0,0,0,0.08)')};"
            "  border-color: rgba(255,107,53,0.4);"
            f"  color: {manager.c('#cccccc', '#222222')};"
            f"}}"
        )
        reset_btn.clicked.connect(self._reset_defaults)
        reset_row.addWidget(reset_btn)
        reset_row.addStretch()
        layout.addLayout(reset_row)

        outer.addWidget(card)
        outer.addStretch()

    def _is_household_linked(self) -> bool:
        return bool(str(self._db.get_setting("household_id", "") or "").strip())

    @staticmethod
    def _parse_metric_value(raw: str) -> float | None:
        try:
            val = float((raw or "").strip())
        except Exception:
            return None
        return val if val > 0 else None

    def _load_body_metrics(self) -> None:
        if self._body_height_input:
            self._body_height_input.setText(
                str(self._db.get_setting("body_height_cm", "") or "").strip()
            )
        if self._body_weight_input:
            self._body_weight_input.setText(
                str(self._db.get_setting("body_weight_kg", "") or "").strip()
            )
        if self._pair_name_input:
            self._pair_name_input.setText(
                str(self._db.get_setting("household_user2_name", "") or "").strip()
            )
        if self._pair_height_input:
            self._pair_height_input.setText(
                str(self._db.get_setting("household_user2_height_cm", "") or "").strip()
            )
        if self._pair_weight_input:
            self._pair_weight_input.setText(
                str(self._db.get_setting("household_user2_weight_kg", "") or "").strip()
            )
        if self._me_name_lbl:
            me_name = self._db.get_setting("user_name", "").strip() or "You"
            self._me_name_lbl.setText(f"{me_name} (Profile 1)")
        if self._pair_name_lbl:
            partner = self._db.get_setting("household_user2_name", "").strip() or "Linked account"
            self._pair_name_lbl.setText(f"{partner} (Profile 2)")

    def _save_body_metrics(self) -> None:
        if self._body_height_input:
            self._db.set_setting("body_height_cm", self._body_height_input.text().strip())
        if self._body_weight_input:
            self._db.set_setting("body_weight_kg", self._body_weight_input.text().strip())
        if self._pair_name_input:
            self._db.set_setting("household_user2_name", self._pair_name_input.text().strip())
        if self._pair_height_input:
            self._db.set_setting("household_user2_height_cm", self._pair_height_input.text().strip())
        if self._pair_weight_input:
            self._db.set_setting("household_user2_weight_kg", self._pair_weight_input.text().strip())
        self._load_body_metrics()
        if self._sync_fn:
            self._sync_fn()

    def _refresh_body_metric_visibility(self) -> None:
        linked = self._is_household_linked()
        if self._pair_box:
            self._pair_box.setVisible(linked)
        if self._recommend_pair_btn:
            self._recommend_pair_btn.setVisible(linked)
            self._recommend_pair_btn.setEnabled(linked)

    def _set_recommend_busy(self, busy: bool) -> None:
        if self._recommend_btn:
            self._recommend_btn.setEnabled(not busy)
            self._recommend_btn.setText("Recommending…" if busy else "Recommend My Goals")
        if self._recommend_pair_btn:
            self._recommend_pair_btn.setEnabled((not busy) and self._is_household_linked())
            self._recommend_pair_btn.setText("Recommending…" if busy else "Recommend Shared Goal")

    def _recommend_goals_from_metrics(self, shared: bool) -> None:
        from utils.workers import run_async
        from api.claude_ai import ClaudeAI
        from utils.macro_goals import set_macro_goal

        h1 = self._parse_metric_value(self._body_height_input.text() if self._body_height_input else "")
        w1 = self._parse_metric_value(self._body_weight_input.text() if self._body_weight_input else "")
        if not h1 or not w1:
            ThemedMessageBox.information(
                self,
                "Body metrics required",
                "Enter your height and weight first to get Dishy recommendations.",
            )
            return

        secondary_profile = None
        if shared:
            h2 = self._parse_metric_value(self._pair_height_input.text() if self._pair_height_input else "")
            w2 = self._parse_metric_value(self._pair_weight_input.text() if self._pair_weight_input else "")
            if not h2 or not w2:
                ThemedMessageBox.information(
                    self,
                    "Second profile required",
                    "For a shared recommendation, enter height and weight for Profile 2.",
                )
                return
            secondary_profile = {
                "name": (self._pair_name_input.text() if self._pair_name_input else "").strip() or "Linked account",
                "height_cm": h2,
                "weight_kg": w2,
            }

        # Save entered metrics before computing recommendations.
        self._save_body_metrics()
        self._set_recommend_busy(True)
        self._set_macro_fields_loading(True)
        if self._metrics_status_lbl:
            self._metrics_status_lbl.setText("Dishy is calculating personalised targets…")

        dietary_prefs = self._db.get_setting("dietary_prefs", "")
        ai = ClaudeAI()

        def _done(result: dict):
            self._set_recommend_busy(False)
            self._set_macro_fields_loading(False)
            keys = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g")
            for key in keys:
                try:
                    val = max(1.0, float(result.get(key, 1.0) or 1.0))
                except Exception:
                    val = 1.0
                if key in self._fields:
                    self._fields[key].setText(str(int(val)))
                set_macro_goal(self._db, key, val)
            note = str(result.get("note", "") or "").strip()
            if self._metrics_status_lbl:
                if shared:
                    self._metrics_status_lbl.setText(
                        "Shared daily target updated for both profiles."
                        + (f" {note}" if note else "")
                    )
                else:
                    self._metrics_status_lbl.setText(
                        "Personal daily target updated from your body metrics."
                        + (f" {note}" if note else "")
                    )
            if self._sync_fn:
                self._sync_fn()

        def _error(_err: str):
            self._set_recommend_busy(False)
            self._set_macro_fields_loading(False)
            if self._metrics_status_lbl:
                self._metrics_status_lbl.setText("")
            ThemedMessageBox.warning(
                self,
                "Dishy recommendation failed",
                "Could not calculate recommendations right now. Please try again.",
            )

        self._macro_worker = run_async(
            ai.recommend_goals_from_body_metrics,
            primary_height_cm=h1,
            primary_weight_kg=w1,
            dietary_prefs=dietary_prefs,
            secondary_profile=secondary_profile,
            on_result=_done,
            on_error=_error,
        )

    def _on_core_macro_edited(self, anchor_key: str):
        from utils.macro_goals import set_macro_goal
        from utils.workers import run_async
        from api.claude_ai import ClaudeAI
        anchor_key = str(anchor_key or "").strip()
        if anchor_key not in {"kcal", "protein_g", "carbs_g", "fat_g"}:
            return
        field = self._fields.get(anchor_key)
        if not field:
            return
        try:
            anchor_val = max(1.0, float(field.text().strip()))
        except ValueError:
            return
        field.setText(str(int(anchor_val)))

        core_keys = ("kcal", "protein_g", "carbs_g", "fat_g")
        prev = {k: self._fields[k].text() for k in core_keys}

        # Persist the edited anchor immediately so UI + dashboard update quickly.
        set_macro_goal(self._db, anchor_key, anchor_val)
        if self._sync_fn:
            self._sync_fn()

        current_goals: dict[str, float] = {}
        for key in core_keys:
            if key == anchor_key:
                current_goals[key] = anchor_val
                continue
            try:
                current_goals[key] = max(1.0, float(self._fields[key].text().strip()))
            except Exception:
                current_goals[key] = 1.0

        self._set_macro_fields_loading(True, exclude_key=anchor_key)
        dietary_prefs = self._db.get_setting("dietary_prefs", "")
        ai = ClaudeAI()
        if anchor_key == "kcal":
            self._macro_worker = run_async(
                ai.calculate_macros_from_calories,
                anchor_val,
                dietary_prefs,
                on_result=lambda r, a=anchor_key, v=anchor_val: self._on_core_macros_calculated(a, v, r),
                on_error=lambda _e, p=prev: self._on_core_macros_error(p),
            )
        else:
            self._macro_worker = run_async(
                ai.recalculate_macro_goals,
                anchor_key,
                anchor_val,
                current_goals,
                dietary_prefs,
                on_result=lambda r, a=anchor_key, v=anchor_val: self._on_core_macros_calculated(a, v, r),
                on_error=lambda _e, p=prev: self._on_core_macros_error(p),
            )

    def _set_macro_fields_loading(self, loading: bool, exclude_key: str | None = None):
        for key in ("kcal", "protein_g", "carbs_g", "fat_g"):
            if exclude_key and key == exclude_key:
                continue
            f = self._fields[key]
            f.setReadOnly(loading)
            if loading:
                f.setPlaceholderText("Dishy…")
                f.setText("")
                f.setStyleSheet("color: #888888; font-style: italic;")
            else:
                f.setPlaceholderText("")
                f.setStyleSheet("")

    def _on_core_macros_calculated(self, anchor_key: str, anchor_value: float, result: dict):
        from utils.macro_goals import set_macro_goal
        self._set_macro_fields_loading(False)
        vals = {}
        for key in ("kcal", "protein_g", "carbs_g", "fat_g"):
            try:
                vals[key] = max(1.0, float(result.get(key, 1.0) or 1.0))
            except Exception:
                vals[key] = 1.0

        # Preserve exactly what the user edited.
        vals[anchor_key] = max(1.0, float(anchor_value or 1.0))

        # Keep kcal coherent with the returned macro grams when user edits grams.
        if anchor_key != "kcal":
            vals["kcal"] = max(
                1.0,
                (vals["protein_g"] * 4.0) + (vals["carbs_g"] * 4.0) + (vals["fat_g"] * 9.0),
            )

        for key in ("kcal", "protein_g", "carbs_g", "fat_g"):
            val = max(1.0, float(vals.get(key, 1.0)))
            self._fields[key].setText(str(int(val)))
            set_macro_goal(self._db, key, val)
        if self._sync_fn:
            self._sync_fn()

    def _on_core_macros_error(self, prev: dict):
        from utils.macro_goals import set_macro_goal
        self._set_macro_fields_loading(False)
        for key in ("kcal", "protein_g", "carbs_g", "fat_g"):
            raw = str(prev.get(key, "") or "").strip()
            self._fields[key].setText(raw)
            try:
                set_macro_goal(self._db, key, max(1.0, float(raw)))
            except Exception:
                pass
        ThemedMessageBox.warning(
            self,
            "Dishy recalculation failed",
            "Could not rebalance goals right now. Your previous values were restored.",
        )

    def set_sync_fn(self, fn):
        self._sync_fn = fn

    def refresh(self):
        self._load_body_metrics()
        self._refresh_body_metric_visibility()

    def _reset_defaults(self):
        from utils.macro_goals import MACRO_SPECS, set_macro_goal
        for key, _, default, *_ in MACRO_SPECS:
            set_macro_goal(self._db, key, default)
            if key in self._fields:
                self._fields[key].setText(str(int(default)))
        if self._sync_fn:
            self._sync_fn()

    def apply_theme(self, _mode):
        if self._auto_note:
            self._auto_note.setStyleSheet(
                f"color: {manager.c('#888888', '#777777')}; background: transparent; font-size: 12px;"
            )
        if self._metrics_title_lbl:
            self._metrics_title_lbl.setStyleSheet(
                f"font-size: 13px; font-weight: 700; color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
            )
        if self._metrics_hint_lbl:
            self._metrics_hint_lbl.setStyleSheet(
                f"font-size: 12px; color: {manager.c('#666666', '#777777')}; background: transparent;"
            )
        if self._metrics_status_lbl:
            self._metrics_status_lbl.setStyleSheet(
                f"font-size: 12px; color: {manager.c('#777777', '#666666')}; background: transparent;"
            )
        if self._me_name_lbl:
            self._me_name_lbl.setStyleSheet(
                f"font-size: 12px; font-weight: 700; color: {manager.c('#d8d8d8', '#222222')}; background: transparent;"
            )
        if self._pair_name_lbl:
            self._pair_name_lbl.setStyleSheet(
                f"font-size: 12px; font-weight: 700; color: {manager.c('#d8d8d8', '#222222')}; background: transparent;"
            )
        if self._me_box:
            self._me_box.setStyleSheet(_subtle_surface_style())
        if self._pair_box:
            self._pair_box.setStyleSheet(_subtle_surface_style())
        if self._body_height_input:
            input_style = (
                f"QLineEdit {{ background: {manager.c('#111111', '#ffffff')};"
                f" color: {manager.c('#e8e8e8', '#1a1a1a')};"
                f" border: 1px solid {manager.c('#2a2a2a', '#dcdcdc')}; border-radius: 8px; padding: 0 10px; }}"
                "QLineEdit:focus { border-color: #ff6b35; }"
            )
            self._body_height_input.setStyleSheet(input_style)
            if self._body_weight_input:
                self._body_weight_input.setStyleSheet(input_style)
            if self._pair_name_input:
                self._pair_name_input.setStyleSheet(input_style)
            if self._pair_height_input:
                self._pair_height_input.setStyleSheet(input_style)
            if self._pair_weight_input:
                self._pair_weight_input.setStyleSheet(input_style)
        if self._recommend_btn:
            self._recommend_btn.setStyleSheet(_secondary_button_style())
        if self._recommend_pair_btn:
            self._recommend_pair_btn.setStyleSheet(_secondary_button_style())
        for lbl in self._macro_name_labels:
            lbl.setStyleSheet(
                f"font-size: 14px; font-weight: 600;"
                f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
            )
        for lbl in self._macro_guide_labels:
            lbl.setStyleSheet(
                f"font-size: 12px; color: {manager.c('#666666', '#777777')}; background: transparent;"
            )
        for lbl in self._macro_unit_labels:
            lbl.setStyleSheet(
                f"color: {manager.c('#888888', '#666666')}; background: transparent; font-size: 13px;"
            )
        if self._reset_btn:
            self._reset_btn.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {manager.c('rgba(255,255,255,0.04)', 'rgba(0,0,0,0.04)')};"
                f"  color: {manager.c('#888888', '#555555')};"
                f"  border: 1px solid {manager.c('#2c2c2c', '#cccccc')}; border-radius: 8px;"
                "  font-size: 12px; font-weight: 600; padding: 0 14px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background-color: {manager.c('rgba(255,255,255,0.08)', 'rgba(0,0,0,0.08)')};"
                "  border-color: rgba(255,107,53,0.4);"
                f"  color: {manager.c('#cccccc', '#222222')};"
                f"}}"
            )
        self._refresh_body_metric_visibility()


# ── Settings view ─────────────────────────────────────────────────────────────

_NAV_ITEMS = [
    ("preferences", "everyday", "fa5s.sliders-h", "Preferences"),
    ("nutrition", "everyday", "fa5s.bullseye", "Nutrition Goals"),
    ("profile", "everyday", "fa5s.id-card", "Profile"),
    ("account", "everyday", "fa5s.user-circle", "Account"),
    ("dishy", "everyday", "fa5s.robot", "Dishy"),
    ("data", "advanced", "fa5s.database", "Data & Backup"),
    ("monitoring", "advanced", "fa5s.chart-line", "Monitoring"),
    ("history", "advanced", "fa5s.list-alt", "Version History"),
]


class SettingsView(QWidget):
    sign_in_requested = Signal()
    sign_out_requested = Signal()

    def __init__(self, db: Database | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("view-container")
        self._db = db or get_db()
        self._nav_btns: list[QPushButton] = []
        self._group_labels: list[QLabel] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scaffold = PageScaffold(
            "Settings",
            "Start with Preferences, Nutrition Goals, Profile, and Account. Backup and diagnostics stay available lower down when you need them.",
            eyebrow="Preferences",
            parent=self,
            quiet_header=True,
        )
        self._scaffold = scaffold
        root.addWidget(scaffold)
        scaffold.set_banner(
            StatusBanner(
                "Everyday settings come first. Advanced tools stay available in a separate section so the page is easier to scan.",
                "system",
                scaffold,
            )
        )

        shell = QWidget()
        shell.setStyleSheet(self._shell_style())
        self._shell = shell
        body_layout = QHBoxLayout(shell)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        nav = QWidget()
        nav.setFixedWidth(228)
        nav.setStyleSheet(self._nav_style())
        self._nav = nav
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(14, 18, 14, 18)
        nav_layout.setSpacing(6)

        current_group = None
        for idx, (key, group, icon_name, label) in enumerate(_NAV_ITEMS):
            if group != current_group:
                if current_group is not None:
                    nav_layout.addSpacing(10)
                    nav_layout.addWidget(_make_sep())
                    nav_layout.addSpacing(10)
                group_label = QLabel("Everyday" if group == "everyday" else "Advanced")
                group_label.setStyleSheet(self._group_label_style())
                nav_layout.addWidget(group_label)
                self._group_labels.append(group_label)
                current_group = group
            btn = QPushButton(f"  {label}")
            btn.setIcon(qta.icon(icon_name, color=manager.c("#888888", "#666666")))
            btn.setIconSize(QSize(14, 14))
            btn.setFixedHeight(42)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, i=idx: self._select_page(i))
            nav_layout.addWidget(btn)
            self._nav_btns.append(btn)

        nav_layout.addStretch()
        body_layout.addWidget(nav)

        content = QWidget()
        content.setStyleSheet(self._content_panel_style())
        self._content_panel = content
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")

        page_defs = [
            ("preferences", _AppPrefsPage(db=self._db)),
            ("nutrition", _NutritionGoalsPage(db=self._db)),
            ("profile", _ProfilePage(db=self._db)),
            ("account", _AccountPage()),
            ("dishy", _DishyPrefsPage(db=self._db)),
            ("data", _DataPage(db=self._db)),
            ("monitoring", _MonitoringPage(db=self._db)),
            ("history", _VersionHistoryPage()),
        ]
        self._pages = [page for _, page in page_defs]
        self._page_keys = [key for key, _ in page_defs]
        self._page_index_by_key = {key: idx for idx, key in enumerate(self._page_keys)}
        self._page_by_key = {key: page for key, page in page_defs}
        self._scroll_areas: list[QScrollArea] = []

        for _key, page in page_defs:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            scroll.verticalScrollBar().setStyleSheet(self._scrollbar_style())
            self._scroll_areas.append(scroll)
            inner = QWidget()
            inner.setStyleSheet("background: transparent;")
            inner_layout = QVBoxLayout(inner)
            inner_layout.setContentsMargins(32, 28, 32, 32)
            inner_layout.setSpacing(0)
            inner_layout.addWidget(page)
            scroll.setWidget(inner)
            self._stack.addWidget(scroll)

        content_layout.addWidget(self._stack, 1)
        body_layout.addWidget(content, 1)
        scaffold.body_layout().addWidget(shell, 1)

        self._select_page(0)

    def _shell_style(self) -> str:
        return (
            f"background: {manager.c('#0f1215', '#fbf6ef')};"
            " border: none;"
            " border-radius: 18px;"
        )

    def _nav_style(self) -> str:
        return (
            f"background: {manager.c('#111418', '#f8f1e7')};"
            f" border-right: 1px solid {manager.c('rgba(255,255,255,0.04)', 'rgba(0,0,0,0.05)')};"
            " border-top-left-radius: 18px; border-bottom-left-radius: 18px;"
        )

    def _content_panel_style(self) -> str:
        return (
            f"background: {manager.c('#12161b', '#fffdf9')};"
            " border-top-right-radius: 18px; border-bottom-right-radius: 18px;"
        )

    def _group_label_style(self) -> str:
        return (
            f"color: {manager.c('#817a72', '#8b8176')};"
            " font-size: 11px; font-weight: 700; letter-spacing: 1.3px;"
            " text-transform: uppercase; background: transparent;"
        )

    def _scrollbar_style(self) -> str:
        return (
            "QScrollBar:vertical { width: 5px; background: transparent; }"
            f"QScrollBar::handle:vertical {{ background: {manager.c('#3a414a', '#cdbfae')};"
            " border-radius: 2px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

    def _nav_button_style(self, active: bool) -> str:
        if active:
            return (
                "QPushButton {"
                f" background: {manager.c('rgba(255,107,53,0.10)', 'rgba(255,107,53,0.08)')};"
                f" color: {manager.c('#f0ebe5', '#271d15')};"
                " border: none; border-radius: 10px;"
                " font-size: 13px; font-weight: 600;"
                " text-align: left; padding: 0 12px;"
                "}"
            )
        return (
            "QPushButton {"
            f" background: transparent; color: {manager.c('#999188', '#6a6158')};"
            " border: none; border-radius: 8px;"
            " font-size: 13px; font-weight: 500; text-align: left; padding: 0 12px;"
            "}"
            "QPushButton:hover {"
            f" background: {manager.c('rgba(255,255,255,0.04)', 'rgba(255,107,53,0.05)')};"
            f" color: {manager.c('#ebe4dc', '#221d18')};"
            "}"
        )

    def _select_page(self, index: int):
        self._stack.setCurrentIndex(index)
        if hasattr(self._pages[index], "refresh"):
            try:
                self._pages[index].refresh()
            except Exception:
                pass
        for i, btn in enumerate(self._nav_btns):
            is_active = i == index
            _key, _group, icon_name, _label = _NAV_ITEMS[i]
            icon_color = manager.c("#ff7a47", "#d75a27") if is_active else manager.c("#93887d", "#6b635a")
            btn.setIcon(qta.icon(icon_name, color=icon_color))
            btn.setChecked(is_active)
            btn.setStyleSheet(self._nav_button_style(is_active))

    def show_root_page(self):
        """Return Settings to its default everyday section."""
        self._select_page(0)

    def activate_settings(self, section: str = "preferences") -> None:
        """Palette-safe entrypoint for section-aware settings navigation."""
        index = self._page_index_by_key.get(str(section or "").strip(), 0)
        self._select_page(index)

    def palette_sections(self) -> list[dict]:
        return [
            {"key": key, "label": label, "group": group}
            for key, group, _icon_name, label in _NAV_ITEMS
        ]

    # ── Public API (called by MainWindow) ──────────────────────────────────────

    def set_sync_fn(self, fn) -> None:
        """Wire cloud sync trigger to all sub-pages that save data."""
        for page in self._pages:
            if hasattr(page, "set_sync_fn"):
                page.set_sync_fn(fn)

    def set_visibility_service(self, service) -> None:
        for page in self._pages:
            if hasattr(page, "set_visibility_service"):
                page.set_visibility_service(service)

    def set_data_management_callbacks(self, meal_plan_fn=None, shopping_fn=None, recipes_fn=None):
        data_page = self._page_by_key["data"]
        data_page.set_refresh_callbacks(meal_plan_fn, shopping_fn, recipes_fn)

    def set_account_info(self, user: dict | None, sync_service) -> None:
        """Called by DishBoard.py after login to populate the Account page."""
        account_page = self._page_by_key["account"]
        monitoring_page = self._page_by_key["monitoring"]
        account_page.set_user(user, sync_service)
        if hasattr(monitoring_page, "set_sync_service"):
            monitoring_page.set_sync_service(sync_service)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                account_page.sign_in_requested.disconnect()
            except Exception:
                pass
        account_page.sign_in_requested.connect(self.sign_in_requested.emit)
        account_page.sign_out_requested.connect(self.sign_out_requested.emit)

    def apply_theme(self, mode: str):
        _refresh_surface_styles(self)
        self._shell.setStyleSheet(self._shell_style())
        self._nav.setStyleSheet(self._nav_style())
        self._content_panel.setStyleSheet(self._content_panel_style())
        for label in self._group_labels:
            label.setStyleSheet(self._group_label_style())
        scrollbar_style = self._scrollbar_style()
        for scroll in self._scroll_areas:
            scroll.verticalScrollBar().setStyleSheet(scrollbar_style)
        for page in self._pages:
            page.apply_theme(mode)
        self._select_page(self._stack.currentIndex())
