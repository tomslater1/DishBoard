import json
import warnings
import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QLineEdit, QCheckBox,
    QFrame, QMessageBox, QFileDialog, QStackedWidget,
)
from PySide6.QtCore import Qt, QSize, Signal

from models.database import Database
from utils.theme import manager
from utils.version import APP_VERSION, VERSION_HISTORY


# ── Page: Account ─────────────────────────────────────────────────────────────

class _AccountPage(QWidget):
    sign_in_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._user: dict | None = None
        self._sync_service = None
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        # ── Identity card ──────────────────────────────────────────────────────
        id_card = _card_widget()
        id_layout = QVBoxLayout(id_card)
        id_layout.setSpacing(14)

        id_title = QLabel("Account")
        id_title.setObjectName("card-title")
        id_layout.addWidget(id_title)

        id_layout.addWidget(_make_sep())

        avatar_row = QHBoxLayout()
        avatar_row.setSpacing(14)

        avatar_lbl = QLabel()
        avatar_lbl.setPixmap(
            qta.icon("fa5s.user-circle", color="#ff6b35").pixmap(QSize(40, 40))
        )
        avatar_lbl.setStyleSheet("background: transparent; border: none;")
        avatar_row.addWidget(avatar_lbl)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        self._email_lbl = QLabel("Not signed in")
        self._email_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600;"
            f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        self._status_lbl = QLabel("Using DishBoard locally")
        self._status_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666', '#888')}; background: transparent;"
        )
        info_col.addWidget(self._email_lbl)
        info_col.addWidget(self._status_lbl)
        avatar_row.addLayout(info_col, 1)
        id_layout.addLayout(avatar_row)

        id_layout.addWidget(_make_sep())

        self._signin_btn = QPushButton("Sign in / Create Account")
        self._signin_btn.setFixedHeight(40)
        self._signin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._signin_btn.setStyleSheet(
            "QPushButton {"
            "  background: #ff6b35; color: #ffffff;"
            "  border-radius: 8px; font-size: 13px; font-weight: 700; border: none;"
            "}"
            "QPushButton:hover { background: #e05a28; }"
        )
        self._signin_btn.clicked.connect(self.sign_in_requested.emit)
        id_layout.addWidget(self._signin_btn)
        self._signin_btn.setVisible(False)

        outer.addWidget(id_card)

        # ── Sync card ──────────────────────────────────────────────────────────
        sync_card = _card_widget()
        sync_layout = QVBoxLayout(sync_card)
        sync_layout.setSpacing(14)

        sync_title = QLabel("Cloud Sync")
        sync_title.setObjectName("card-title")
        sync_layout.addWidget(sync_title)

        sync_layout.addWidget(_make_sep())

        sync_row = QHBoxLayout()
        sync_row.setSpacing(16)
        sync_col = QVBoxLayout()
        sync_col.setSpacing(3)

        self._sync_status_lbl = QLabel("Sign in to enable cloud sync")
        self._sync_status_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600;"
            f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        self._sync_sub_lbl = QLabel(
            "Your recipes, meal plans and more will sync across devices."
        )
        self._sync_sub_lbl.setWordWrap(True)
        self._sync_sub_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666', '#888')}; background: transparent;"
        )
        sync_col.addWidget(self._sync_status_lbl)
        sync_col.addWidget(self._sync_sub_lbl)

        self._sync_now_btn = QPushButton("Sync now")
        self._sync_now_btn.setFixedHeight(36)
        self._sync_now_btn.setMinimumWidth(110)
        self._sync_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_now_btn.setEnabled(False)
        self._sync_now_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: rgba(52,211,153,0.1); color: #34d399;"
            "  border: 1px solid rgba(52,211,153,0.35); border-radius: 8px;"
            "  font-size: 13px; font-weight: 600; padding: 0 14px;"
            "}"
            "QPushButton:hover {"
            "  background-color: rgba(52,211,153,0.2); border-color: rgba(52,211,153,0.6);"
            "}"
            "QPushButton:disabled { color: #2a6b52; border-color: rgba(52,211,153,0.15); background-color: rgba(52,211,153,0.04); }"
        )
        self._sync_now_btn.clicked.connect(self._on_sync_now)

        sync_row.addLayout(sync_col, 1)
        sync_row.addWidget(self._sync_now_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        sync_layout.addLayout(sync_row)
        outer.addWidget(sync_card)

        # ── Sign-out card ──────────────────────────────────────────────────────
        so_card = _card_widget()
        so_layout = QVBoxLayout(so_card)
        so_layout.setSpacing(14)

        so_title = QLabel("Sign Out")
        so_title.setObjectName("card-title")
        so_layout.addWidget(so_title)

        so_layout.addWidget(_make_sep())

        so_row = QHBoxLayout()
        so_row.setSpacing(16)
        so_col = QVBoxLayout()
        so_col.setSpacing(3)

        so_name = QLabel("Sign out of DishBoard")
        so_name.setStyleSheet(
            f"font-size: 14px; font-weight: 600;"
            f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        so_sub = QLabel("Your local data stays on this device.")
        so_sub.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666', '#888')}; background: transparent;"
        )
        so_col.addWidget(so_name)
        so_col.addWidget(so_sub)

        self._signout_btn = QPushButton("Sign out")
        self._signout_btn.setFixedHeight(36)
        self._signout_btn.setMinimumWidth(110)
        self._signout_btn.setEnabled(False)
        self._signout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._signout_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: rgba(220,53,69,0.1); color: #dc3545;"
            "  border: 1px solid rgba(220,53,69,0.35); border-radius: 8px;"
            "  font-size: 13px; font-weight: 600; padding: 0 14px;"
            "}"
            "QPushButton:hover {"
            "  background-color: rgba(220,53,69,0.2); border-color: rgba(220,53,69,0.6);"
            "}"
            "QPushButton:disabled { color: #6b2a30; border-color: rgba(220,53,69,0.15); background-color: rgba(220,53,69,0.04); }"
        )
        self._signout_btn.clicked.connect(self._on_sign_out)

        so_row.addLayout(so_col, 1)
        so_row.addWidget(self._signout_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        so_layout.addLayout(so_row)
        outer.addWidget(so_card)

        # ── Powered by DishBoard AI card ──────────────────────────────────────
        ai_card = QWidget()
        ai_card.setStyleSheet(
            "background-color: rgba(52, 211, 153, 0.08);"
            " border: 1px solid rgba(52, 211, 153, 0.35);"
            " border-radius: 12px;"
        )
        ai_layout = QHBoxLayout(ai_card)
        ai_layout.setContentsMargins(16, 14, 16, 14)
        ai_layout.setSpacing(14)

        ai_icon_lbl = QLabel()
        ai_icon_lbl.setPixmap(
            qta.icon("fa5s.robot", color="#34d399").pixmap(QSize(28, 28))
        )
        ai_icon_lbl.setStyleSheet("background: transparent; border: none;")
        ai_layout.addWidget(ai_icon_lbl)

        ai_text = QVBoxLayout()
        ai_text.setSpacing(3)
        ai_title_lbl = QLabel("Powered by DishBoard AI")
        ai_title_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #34d399; background: transparent; border: none;"
        )
        ai_sub_lbl = QLabel(
            "Dishy uses a secure server-side connection — no API key needed. "
            "Your AI requests are authenticated with your DishBoard account and never leave our servers."
        )
        ai_sub_lbl.setWordWrap(True)
        ai_sub_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#888888', '#555555')}; background: transparent; border: none;"
        )
        ai_text.addWidget(ai_title_lbl)
        ai_text.addWidget(ai_sub_lbl)
        ai_layout.addLayout(ai_text, 1)

        outer.addWidget(ai_card)
        outer.addStretch()

    def set_user(self, user: dict | None, sync_service) -> None:
        self._user = user
        self._sync_service = sync_service

        no_account = not user or user.get("offline")

        if user and not user.get("offline"):
            self._email_lbl.setText(user.get("email", "Signed in"))
            self._status_lbl.setText("Signed in")
            self._sync_status_lbl.setText("Live sync enabled")
            self._sync_sub_lbl.setText("Changes sync in real time across all your devices.")
            self._sync_now_btn.setEnabled(sync_service is not None)
            self._signout_btn.setEnabled(True)
            self._signin_btn.setVisible(False)
        elif user and user.get("offline"):
            self._email_lbl.setText(user.get("email", "Offline"))
            self._status_lbl.setText("Offline — syncs when internet is available")
            self._sync_status_lbl.setText("Offline mode")
            self._sync_sub_lbl.setText("Cloud sync will resume when internet is available.")
            self._sync_now_btn.setEnabled(False)
            self._signout_btn.setEnabled(True)
            self._signin_btn.setVisible(False)
        else:
            self._email_lbl.setText("No account")
            self._status_lbl.setText("Using DishBoard locally")
            self._sync_status_lbl.setText("Sign in to enable cloud sync")
            self._sync_sub_lbl.setText("Your recipes, meal plans and more will sync across devices.")
            self._sync_now_btn.setEnabled(False)
            self._signout_btn.setEnabled(False)
            self._signin_btn.setVisible(True)

    def _on_sync_now(self):
        if self._sync_service:
            self._sync_now_btn.setEnabled(False)
            self._sync_status_lbl.setText("Syncing…")

            def _done(pushed, pulled):
                self._sync_status_lbl.setText("Syncing across devices")
                self._sync_now_btn.setEnabled(True)

            self._sync_service.sync_finished.connect(_done)
            self._sync_service.sync_now()

    def _on_sign_out(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Sign out?")
        msg.setText(
            "You will be signed out of DishBoard.\n"
            "Your local data stays on this device."
        )
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok
        )
        msg.button(QMessageBox.StandardButton.Ok).setText("Sign out")
        msg.button(QMessageBox.StandardButton.Cancel).setText("Cancel")
        if msg.exec() != QMessageBox.StandardButton.Ok:
            return

        try:
            from auth.supabase_client import get_client
            client = get_client()
            if client:
                client.auth.sign_out()
        except Exception:
            pass

        try:
            from auth.session_manager import clear_session
            clear_session()
        except Exception:
            pass

        import sys
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QProcess
        QProcess.startDetached(sys.executable, sys.argv)
        QApplication.quit()

    def apply_theme(self, _mode):
        pass


# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_sep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(
        f"color: {manager.c('#252535', '#dddddd')};"
        f" background: {manager.c('#252535', '#dddddd')};"
        " border: none; max-height: 1px;"
    )
    return sep


def _selector_style(active: bool, size: int = 15) -> str:
    if active:
        return (
            f"QPushButton {{"
            f"  background-color: rgba(255,107,53,0.14);"
            f"  color: #ff6b35;"
            f"  border: 2px solid #ff6b35;"
            f"  border-radius: 10px;"
            f"  font-size: {size}px; font-weight: 700;"
            f"}}"
        )
    bg     = manager.c("#0e0e0e", "#f7f7f7")
    fg     = manager.c("#606060", "#555555")
    border = manager.c("#2c2c2c", "#cecece")
    hover  = manager.c("#161616", "#eeeeee")
    return (
        f"QPushButton {{"
        f"  background-color: {bg}; color: {fg};"
        f"  border: 1px solid {border}; border-radius: 10px;"
        f"  font-size: {size}px; font-weight: 500;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background-color: {hover}; border-color: rgba(255,107,53,0.35);"
        f"  color: {manager.c('#909090', '#333333')};"
        f"}}"
    )


def _card_widget() -> QWidget:
    w = QWidget()
    w.setObjectName("card")
    return w


# ── Page: Profile ─────────────────────────────────────────────────────────────

class _ProfilePage(QWidget):
    """Full editable profile page — mirrors the onboarding wizard fields."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = Database()
        self._db.connect()
        self._build()

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
                b.setStyleSheet(_selector_style(k == chosen_key))
            save_fn()

        for key, label in options:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_selector_style(key == saved))
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
        self._name_input.editingFinished.connect(
            lambda: self._db.set_setting("user_name", self._name_input.text().strip())
        )
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
        overflow_keys = list(self._dietary_btns.keys())[5:]
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

    def _save_dietary(self):
        selected = ",".join(k for k, b in self._dietary_btns.items() if b.isChecked())
        self._db.set_setting("dietary_prefs", selected)

    def _save_allergens(self):
        selected = ",".join(k for k, b in self._allergen_btns.items() if b.isChecked())
        self._db.set_setting("allergens", selected)

    def _save_scenarios(self):
        selected = ",".join(k for k, b in self._scenario_btns.items() if b.isChecked())
        self._db.set_setting("lifestyle_scenarios", selected)

    def _save_cuisines(self):
        selected = ",".join(k for k, b in self._cuisine_btns.items() if b.isChecked())
        self._db.set_setting("cuisine_preferences", selected)

    def _save_skill(self):
        chosen = next(
            (k for k, b in self._skill_btns.items()
             if "rgba(255,107,53" in b.styleSheet()),
            ""
        )
        self._db.set_setting("cooking_skill", chosen)

    def _save_goal(self):
        chosen = next(
            (k for k, b in self._goal_btns.items()
             if "rgba(255,107,53" in b.styleSheet()),
            ""
        )
        self._db.set_setting("weekly_cooking_goal", chosen)

    def apply_theme(self, _mode):
        pass


# ── Page: Dishy Preferences ───────────────────────────────────────────────────

class _DishyPrefsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = Database()
        self._db.connect()
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
        clear_name = QLabel("Clear Dishy Chat History")
        clear_name.setStyleSheet(
            f"font-size: 14px; font-weight: 600;"
            f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        clear_sub = QLabel("Permanently delete all past conversations with Dishy")
        clear_sub.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666666', '#777777')}; background: transparent;"
        )
        clear_col.addWidget(clear_name)
        clear_col.addWidget(clear_sub)

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
        msg = QMessageBox(self)
        msg.setWindowTitle("Clear Dishy History?")
        msg.setText("This will permanently delete all your Dishy conversations.\nThis cannot be undone.")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok)
        msg.button(QMessageBox.StandardButton.Ok).setText("Yes, clear")
        msg.button(QMessageBox.StandardButton.Cancel).setText("Cancel")
        if msg.exec() == QMessageBox.StandardButton.Ok:
            self._db.clear_dishy_history()

    def apply_theme(self, _mode):
        pass


# ── Page: App Preferences ─────────────────────────────────────────────────────

class _AppPrefsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = Database()
        self._db.connect()
        self._build()

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

    def apply_theme(self, mode: str):
        self._update_theme_btns(mode)
        self._update_week_btns(self._db.get_setting("week_start_day", "Monday"))


# ── Page: Data & Backup ───────────────────────────────────────────────────────

class _DataPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = Database()
        self._db.connect()
        self._refresh_meal_plan = None
        self._refresh_shopping  = None
        self._refresh_recipes   = None
        self._row_labels: list[tuple[QLabel, QLabel]] = []
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
            ("Export Data", "Save a full backup as a .json file", "Export →", self._export, True),
            ("Import Data", "Merge a backup file into your current data", "Import ←", self._import, False),
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
            col.addWidget(t)
            col.addWidget(s)

            btn = QPushButton(btn_label)
            btn.setFixedHeight(36)
            btn.setMinimumWidth(130)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if is_primary:
                btn.setStyleSheet(
                    "QPushButton {"
                    "  background-color: rgba(255,107,53,0.1); color: #ff6b35;"
                    "  border: 1px solid rgba(255,107,53,0.35); border-radius: 8px;"
                    "  font-size: 13px; font-weight: 600; padding: 0 14px;"
                    "}"
                    "QPushButton:hover {"
                    "  background-color: rgba(255,107,53,0.2); border-color: rgba(255,107,53,0.6);"
                    "}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton {"
                    f"  background-color: {manager.c('rgba(255,255,255,0.04)', 'rgba(0,0,0,0.04)')};"
                    f"  color: {manager.c('#888888', '#555555')};"
                    f"  border: 1px solid {manager.c('#2c2c2c', '#cccccc')}; border-radius: 8px;"
                    "  font-size: 13px; font-weight: 600; padding: 0 14px;"
                    "}"
                    "QPushButton:hover {"
                    f"  background-color: {manager.c('rgba(255,255,255,0.08)', 'rgba(0,0,0,0.08)')};"
                    "  border-color: rgba(255,107,53,0.4);"
                    f"  color: {manager.c('#bbbbbb', '#222222')};"
                    "}"
                )
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
            btn.setStyleSheet(
                "QPushButton {"
                "  background-color: rgba(220,53,69,0.1); color: #dc3545;"
                "  border: 1px solid rgba(220,53,69,0.35); border-radius: 8px;"
                "  font-size: 13px; font-weight: 600; padding: 0 14px;"
                "}"
                "QPushButton:hover {"
                "  background-color: rgba(220,53,69,0.2); border-color: rgba(220,53,69,0.6);"
                "}"
            )
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
        msg = QMessageBox(self)
        msg.setWindowTitle("Are you sure?")
        msg.setText(message)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok)
        msg.button(QMessageBox.StandardButton.Ok).setText("Yes, delete")
        msg.button(QMessageBox.StandardButton.Cancel).setText("Cancel")
        if msg.exec() == QMessageBox.StandardButton.Ok:
            action()

    def _clear_meal_plan(self):
        self._db.conn.execute("DELETE FROM meal_plans")
        self._db.conn.commit()
        if self._refresh_meal_plan:
            self._refresh_meal_plan()

    def _clear_shopping(self):
        self._db.conn.execute("DELETE FROM shopping_items")
        self._db.conn.commit()
        if self._refresh_shopping:
            self._refresh_shopping()

    def _clear_recipes(self):
        self._db.conn.execute("DELETE FROM recipes")
        self._db.conn.commit()
        if self._refresh_recipes:
            self._refresh_recipes()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export DishBoard Data", "dishboard_backup.json", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            data = {
                "version": 1,
                "recipes": [dict(r) for r in self._db.conn.execute("SELECT * FROM recipes").fetchall()],
                "meal_plans": [dict(r) for r in self._db.conn.execute("SELECT * FROM meal_plans").fetchall()],
                "shopping_items": [dict(r) for r in self._db.conn.execute("SELECT * FROM shopping_items").fetchall()],
                "settings": [dict(r) for r in self._db.conn.execute("SELECT * FROM settings").fetchall()],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            counts = (
                f"{len(data['recipes'])} recipes, "
                f"{len(data['meal_plans'])} meal plan entries, "
                f"{len(data['shopping_items'])} shopping items"
            )
            msg = QMessageBox(self)
            msg.setWindowTitle("Export complete")
            msg.setText(f"Backup saved successfully.\n\n{counts}")
            msg.setIcon(QMessageBox.Icon.Information)
            msg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

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
            QMessageBox.critical(self, "Import failed", f"Could not read file:\n{e}")
            return

        if "recipes" not in data and "meal_plans" not in data:
            QMessageBox.warning(self, "Invalid file", "This doesn't look like a DishBoard backup.")
            return

        confirm = QMessageBox(self)
        confirm.setWindowTitle("Import data?")
        confirm.setText(
            "This will merge the backup into your current data.\n"
            "Existing records will not be overwritten — only new items will be added.\n\nContinue?"
        )
        confirm.setIcon(QMessageBox.Icon.Question)
        confirm.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok)
        confirm.button(QMessageBox.StandardButton.Ok).setText("Yes, import")
        confirm.button(QMessageBox.StandardButton.Cancel).setText("Cancel")
        if confirm.exec() != QMessageBox.StandardButton.Ok:
            return

        try:
            imported = {"recipes": 0, "meal_plans": 0, "shopping_items": 0}

            for r in data.get("recipes", []):
                try:
                    self._db.conn.execute(
                        "INSERT OR IGNORE INTO recipes "
                        "(source_id, source, title, image_url, summary, servings, ready_mins, data_json, saved_at, is_favourite)"
                        " VALUES (:source_id, :source, :title, :image_url, :summary, :servings, :ready_mins, :data_json, :saved_at, :is_favourite)",
                        {k: r.get(k) for k in ("source_id","source","title","image_url","summary","servings","ready_mins","data_json","saved_at","is_favourite")}
                    )
                    if self._db.conn.execute("SELECT changes()").fetchone()[0]:
                        imported["recipes"] += 1
                except Exception:
                    pass

            for m in data.get("meal_plans", []):
                try:
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
                    self._db.conn.execute(
                        "INSERT INTO shopping_items (name, quantity, unit, checked, source, added_at)"
                        " VALUES (:name, :quantity, :unit, :checked, :source, :added_at)",
                        {k: s.get(k) for k in ("name","quantity","unit","checked","source","added_at")}
                    )
                    imported["shopping_items"] += 1
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
            msg = QMessageBox(self)
            msg.setWindowTitle("Import complete")
            msg.setText(
                f"Import successful!\n\n"
                f"Added: {imported['recipes']} recipes, "
                f"{imported['meal_plans']} meal plan entries, "
                f"{imported['shopping_items']} shopping items"
            )
            msg.setIcon(QMessageBox.Icon.Information)
            msg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))

    def apply_theme(self, _mode):
        for name_lbl, sub_lbl in self._row_labels:
            name_lbl.setStyleSheet(
                f"font-size: 14px; font-weight: 600;"
                f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
            )
            sub_lbl.setStyleSheet(
                f"font-size: 12px; color: {manager.c('#666666', '#777777')}; background: transparent;"
            )


# ── Page: Version History ─────────────────────────────────────────────────────

class _VersionHistoryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
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
            ver_row.addWidget(ver_lbl)

            title_lbl = QLabel(entry["title"])
            title_lbl.setStyleSheet(
                f"font-size: 13px; font-weight: 600;"
                f" color: {manager.c('#e8e8e8', '#1a1a1a')}; background: transparent;"
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
                text = QLabel(change)
                text.setWordWrap(True)
                text.setStyleSheet(
                    f"font-size: 12px; color: {manager.c('#888888', '#666666')}; background: transparent;"
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
        pass


# ── Page: Nutrition Goals ─────────────────────────────────────────────────────

class _NutritionGoalsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = Database()
        self._db.connect()
        self._fields: dict[str, QLineEdit] = {}
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
            "These control the progress rings on the Nutrition page and My Kitchen dashboard."
        )
        desc.setObjectName("card-body")
        desc.setWordWrap(True)
        layout.addWidget(desc)

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
            guide_lbl = QLabel(MACRO_GUIDES[key])
            guide_lbl.setWordWrap(True)
            guide_lbl.setStyleSheet(
                f"font-size: 12px; color: {manager.c('#666666', '#777777')}; background: transparent;"
            )
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
                except ValueError:
                    pass

            field.editingFinished.connect(_save)

            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet(
                f"color: {manager.c('#888888', '#666666')}; background: transparent; font-size: 13px;"
            )

            row_l.addWidget(field)
            row_l.addWidget(unit_lbl)
            layout.addWidget(row_w)

        layout.addWidget(_make_sep())

        # Reset to defaults button
        reset_row = QHBoxLayout()
        reset_btn = QPushButton("Reset to defaults")
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

    def _reset_defaults(self):
        from utils.macro_goals import MACRO_SPECS, set_macro_goal
        for key, _, default, *_ in MACRO_SPECS:
            set_macro_goal(self._db, key, default)
            if key in self._fields:
                self._fields[key].setText(str(int(default)))

    def apply_theme(self, _mode):
        pass


# ── Settings view ─────────────────────────────────────────────────────────────

_NAV_ITEMS = [
    ("fa5s.user-circle",  "Account"),          # index 0
    ("fa5s.id-card",      "Profile"),          # index 1
    ("fa5s.robot",        "Dishy"),             # index 2
    ("fa5s.bullseye",     "Nutrition Goals"),   # index 3
    ("fa5s.sliders-h",    "Preferences"),       # index 4
    ("fa5s.database",     "Data & Backup"),     # index 5
    ("fa5s.list-alt",     "Version History"),   # index 6
]


class SettingsView(QWidget):
    sign_in_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("view-container")
        self._nav_btns: list[QPushButton] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setStyleSheet(
            f"background: {manager.c('#0a0a0a', '#f0f0f0')};"
            f" border-bottom: 1px solid {manager.c('#1c1c1c', '#dddddd')};"
        )
        hdr.setFixedHeight(64)
        self._hdr = hdr
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(32, 0, 32, 0)

        page_title = QLabel("Settings")
        page_title.setObjectName("page-title")
        page_sub = QLabel("Personalise and manage your DishBoard")
        page_sub.setObjectName("page-date")
        hdr_layout.addWidget(page_title)
        hdr_layout.addSpacing(12)
        hdr_layout.addWidget(page_sub)
        hdr_layout.addStretch()
        root.addWidget(hdr)

        # ── Body: nav + content ───────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Left nav strip
        nav = QWidget()
        nav.setFixedWidth(200)
        nav.setStyleSheet(
            f"background: {manager.c('#0d0d0d', '#f8f8f8')};"
            f" border-right: 1px solid {manager.c('#1c1c1c', '#e0e0e0')};"
        )
        self._nav = nav
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(12, 20, 12, 20)
        nav_layout.setSpacing(4)

        for idx, (icon_name, label) in enumerate(_NAV_ITEMS):
            btn = QPushButton(f"  {label}")
            btn.setIcon(qta.icon(icon_name, color=manager.c("#888888", "#666666")))
            btn.setIconSize(QSize(14, 14))
            btn.setFixedHeight(40)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, i=idx: self._select_page(i))
            nav_layout.addWidget(btn)
            self._nav_btns.append(btn)

        nav_layout.addStretch()
        body_layout.addWidget(nav)

        # Right content area: stacked pages each wrapped in a scroll area
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")

        pages = [
            _AccountPage(),            # index 0
            _ProfilePage(),            # index 1
            _DishyPrefsPage(),         # index 2
            _NutritionGoalsPage(),     # index 3
            _AppPrefsPage(),           # index 4
            _DataPage(),               # index 5
            _VersionHistoryPage(),     # index 6
        ]
        self._pages = pages
        self._scroll_areas: list[QScrollArea] = []

        for page in pages:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            scroll.verticalScrollBar().setStyleSheet(
                "QScrollBar:vertical { width: 5px; background: transparent; }"
                f"QScrollBar::handle:vertical {{ background: {manager.c('#2a2a2a', '#cccccc')};"
                " border-radius: 2px; min-height: 20px; }"
                "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            )
            self._scroll_areas.append(scroll)
            inner = QWidget()
            inner.setStyleSheet("background: transparent;")
            inner_layout = QVBoxLayout(inner)
            inner_layout.setContentsMargins(28, 24, 28, 28)
            inner_layout.setSpacing(0)
            inner_layout.addWidget(page)
            scroll.setWidget(inner)
            self._stack.addWidget(scroll)

        body_layout.addWidget(self._stack, 1)
        root.addWidget(body, 1)

        self._select_page(0)

    def _select_page(self, index: int):
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            is_active = i == index
            icon_name, label = _NAV_ITEMS[i]
            icon_color = "#ff6b35" if is_active else manager.c("#888888", "#666666")
            btn.setIcon(qta.icon(icon_name, color=icon_color))
            btn.setChecked(is_active)
            btn.setStyleSheet(
                (
                    "QPushButton {"
                    " background: rgba(255,107,53,0.12); color: #ff6b35;"
                    " border: 1px solid rgba(255,107,53,0.35); border-radius: 8px;"
                    " font-size: 13px; font-weight: 600; text-align: left; padding: 0 12px;"
                    "}"
                ) if is_active else (
                    "QPushButton {"
                    f" background: transparent; color: {manager.c('#888888', '#555555')};"
                    " border: 1px solid transparent; border-radius: 8px;"
                    " font-size: 13px; font-weight: 500; text-align: left; padding: 0 12px;"
                    "}"
                    "QPushButton:hover {"
                    f" background: {manager.c('rgba(255,255,255,0.05)', 'rgba(0,0,0,0.05)')};"
                    f" color: {manager.c('#c0c0c0', '#333333')};"
                    "}"
                )
            )

    # ── Public API (called by MainWindow) ──────────────────────────────────────

    def set_data_management_callbacks(self, meal_plan_fn=None, shopping_fn=None, recipes_fn=None):
        data_page = self._pages[5]   # _DataPage is at index 5
        data_page.set_refresh_callbacks(meal_plan_fn, shopping_fn, recipes_fn)

    def set_account_info(self, user: dict | None, sync_service) -> None:
        """Called by DishBoard.py after login to populate the Account page."""
        account_page = self._pages[0]
        account_page.set_user(user, sync_service)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                account_page.sign_in_requested.disconnect()
            except Exception:
                pass
        account_page.sign_in_requested.connect(self.sign_in_requested.emit)

    def apply_theme(self, mode: str):
        self._hdr.setStyleSheet(
            f"background: {manager.c('#0a0a0a', '#f0f0f0')};"
            f" border-bottom: 1px solid {manager.c('#1c1c1c', '#dddddd')};"
        )
        self._nav.setStyleSheet(
            f"background: {manager.c('#0d0d0d', '#f8f8f8')};"
            f" border-right: 1px solid {manager.c('#1c1c1c', '#e0e0e0')};"
        )
        scrollbar_style = (
            "QScrollBar:vertical { width: 5px; background: transparent; }"
            f"QScrollBar::handle:vertical {{ background: {manager.c('#2a2a2a', '#cccccc')};"
            " border-radius: 2px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        for scroll in self._scroll_areas:
            scroll.verticalScrollBar().setStyleSheet(scrollbar_style)
        for page in self._pages:
            page.apply_theme(mode)
        self._select_page(self._stack.currentIndex())
