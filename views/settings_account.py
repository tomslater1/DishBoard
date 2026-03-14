import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit,
)
from PySide6.QtCore import Qt, QSize, Signal

from utils.data_service import get_db
from utils.system_visibility import describe_sync_runtime
from utils.theme import manager
from utils.themed_dialog import ThemedMessageBox
from utils.ui_tokens import (
    primary_button_style as _primary_button_style,
    secondary_button_style as _secondary_button_style,
)
from views.settings_helpers import (
    make_sep as _make_sep,
    card_widget as _card_widget,
)


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


# ── Page: Account ─────────────────────────────────────────────────────────────

class _AccountPage(QWidget):
    sign_in_requested = Signal()
    sign_out_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._user: dict | None = None
        self._sync_service = None
        self._bound_sync_service = None
        self._visibility_service = None
        self._household_controls_enabled = False
        self._db = get_db()
        self._build()

    def set_visibility_service(self, service) -> None:
        if self._visibility_service is service:
            return
        if self._visibility_service is not None:
            try:
                self._visibility_service.snapshot_changed.disconnect(self._on_visibility_changed)
            except Exception:
                pass
        self._visibility_service = service
        if service is not None:
            service.snapshot_changed.connect(self._on_visibility_changed)
        self._refresh_sync_status_card()

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
        self._signin_btn.setStyleSheet(_primary_button_style())
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
        self._session_store_lbl = QLabel("")
        self._session_store_lbl.setWordWrap(True)
        self._session_store_lbl.setStyleSheet(
            f"font-size: 11px; color: {manager.c('#777', '#666')}; background: transparent;"
        )
        sync_col.addWidget(self._session_store_lbl)

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
        self._sync_now_btn.setToolTip("Force a cloud sync now")
        self._sync_now_btn.clicked.connect(self._on_sync_now)

        sync_row.addLayout(sync_col, 1)
        sync_row.addWidget(self._sync_now_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        sync_layout.addLayout(sync_row)
        outer.addWidget(sync_card)

        # ── Household sharing card ────────────────────────────────────────────
        hh_card = _card_widget()
        hh_layout = QVBoxLayout(hh_card)
        hh_layout.setSpacing(12)

        hh_title = QLabel("Shared Household")
        hh_title.setObjectName("card-title")
        hh_layout.addWidget(hh_title)
        hh_layout.addWidget(_make_sep())

        self._hh_status_box = QWidget()
        st_l = QVBoxLayout(self._hh_status_box)
        st_l.setContentsMargins(12, 10, 12, 10)
        st_l.setSpacing(4)

        self._hh_status_lbl = QLabel("Not in a shared household")
        self._hh_status_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {manager.c('#e0e0e0', '#1a1a1a')};"
            " background: transparent;"
        )
        st_l.addWidget(self._hh_status_lbl)

        self._hh_sub_lbl = QLabel(
            "Share recipes, meal plans, shopping, nutrition and kitchen data across family accounts."
        )
        self._hh_sub_lbl.setWordWrap(True)
        self._hh_sub_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666', '#888')}; background: transparent;"
        )
        st_l.addWidget(self._hh_sub_lbl)

        self._hh_code_lbl = QLabel("")
        self._hh_code_lbl.setStyleSheet(
            "font-size: 12px; color: #34d399; background: transparent; border: none; font-weight: 700;"
        )
        self._hh_code_lbl.setVisible(False)
        st_l.addWidget(self._hh_code_lbl)
        hh_layout.addWidget(self._hh_status_box)

        self._hh_hint_lbl = QLabel(
            "Create a household to generate an invite code, or join one using an invite code."
        )
        self._hh_hint_lbl.setWordWrap(True)
        self._hh_hint_lbl.setStyleSheet(
            f"font-size: 11px; color: {manager.c('#6f6f6f', '#7f7f7f')}; background: transparent;"
        )
        hh_layout.addWidget(self._hh_hint_lbl)

        self._hh_create_box = QWidget()
        ct_l = QVBoxLayout(self._hh_create_box)
        ct_l.setContentsMargins(12, 10, 12, 10)
        ct_l.setSpacing(8)
        hh_ctrl_h = 38
        self._hh_create_lbl = QLabel("Create a new household")
        self._hh_create_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {manager.c('#8a8a8a', '#666666')}; background: transparent;"
        )
        ct_l.addWidget(self._hh_create_lbl)
        row_top = QHBoxLayout()
        row_top.setContentsMargins(0, 0, 0, 0)
        row_top.setSpacing(10)
        self._hh_name_input = QLineEdit()
        self._hh_name_input.setPlaceholderText("Household name")
        self._hh_name_input.setFixedHeight(hh_ctrl_h)
        self._hh_create_btn = QPushButton("Create")
        self._hh_create_btn.setFixedHeight(hh_ctrl_h)
        self._hh_create_btn.setFixedWidth(120)
        self._hh_create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hh_create_btn.setToolTip("Start a new shared household")
        self._hh_create_btn.clicked.connect(self._create_household)
        row_top.addWidget(self._hh_name_input, 1)
        row_top.addWidget(self._hh_create_btn)
        ct_l.addLayout(row_top)
        hh_layout.addWidget(self._hh_create_box)

        self._hh_join_box = QWidget()
        jn_l = QVBoxLayout(self._hh_join_box)
        jn_l.setContentsMargins(12, 10, 12, 10)
        jn_l.setSpacing(8)
        self._hh_join_lbl = QLabel("Join with an invite code")
        self._hh_join_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {manager.c('#8a8a8a', '#666666')}; background: transparent;"
        )
        jn_l.addWidget(self._hh_join_lbl)
        row_join = QHBoxLayout()
        row_join.setContentsMargins(0, 0, 0, 0)
        row_join.setSpacing(10)
        self._hh_join_input = QLineEdit()
        self._hh_join_input.setPlaceholderText("Invite code")
        self._hh_join_input.setFixedHeight(hh_ctrl_h)
        self._hh_join_input.setMaxLength(16)
        self._hh_join_input.textChanged.connect(self._on_household_code_changed)
        self._hh_join_btn = QPushButton("Join")
        self._hh_join_btn.setFixedHeight(hh_ctrl_h)
        self._hh_join_btn.setFixedWidth(120)
        self._hh_join_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hh_join_btn.setToolTip("Join someone else's shared household")
        self._hh_join_btn.clicked.connect(self._join_household)
        row_join.addWidget(self._hh_join_input, 1)
        row_join.addWidget(self._hh_join_btn)
        jn_l.addLayout(row_join)
        hh_layout.addWidget(self._hh_join_box)

        # Keep Create/Join visually identical at initial render.
        _hh_action_style = _secondary_button_style()
        self._hh_join_btn.setStyleSheet(_hh_action_style)
        self._hh_create_btn.setStyleSheet(self._hh_join_btn.styleSheet())

        row_leave = QHBoxLayout()
        row_leave.setContentsMargins(0, 4, 0, 0)
        row_leave.setSpacing(8)
        self._hh_leave_btn = QPushButton("Leave Household")
        self._hh_leave_btn.setFixedHeight(hh_ctrl_h)
        self._hh_leave_btn.setMinimumWidth(140)
        self._hh_leave_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hh_leave_btn.setToolTip("Leave the current shared household")
        self._hh_leave_btn.clicked.connect(self._leave_household)
        row_leave.addWidget(self._hh_leave_btn, 0, Qt.AlignmentFlag.AlignLeft)
        row_leave.addStretch()
        hh_layout.addLayout(row_leave)
        outer.addWidget(hh_card)

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

        self._so_name = QLabel("Sign out of DishBoard")
        self._so_name.setStyleSheet(
            f"font-size: 14px; font-weight: 600;"
            f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        self._so_sub = QLabel("Your account data remains safely stored in the cloud.")
        self._so_sub.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666', '#888')}; background: transparent;"
        )
        so_col.addWidget(self._so_name)
        so_col.addWidget(self._so_sub)

        self._signout_btn = QPushButton("Sign out")
        self._signout_btn.setFixedHeight(36)
        self._signout_btn.setMinimumWidth(110)
        self._signout_btn.setEnabled(False)
        self._signout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._signout_btn.setStyleSheet(_danger_button_style())
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
        self._ai_sub_lbl = QLabel(
            "Dishy uses a secure server-side connection — no API key needed. "
            "Your AI requests are authenticated with your DishBoard account and never leave our servers."
        )
        self._ai_sub_lbl.setWordWrap(True)
        self._ai_sub_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#888888', '#555555')}; background: transparent; border: none;"
        )
        ai_text.addWidget(ai_title_lbl)
        ai_text.addWidget(self._ai_sub_lbl)
        ai_layout.addLayout(ai_text, 1)

        outer.addWidget(ai_card)
        outer.addStretch()
        self._set_household_enabled(False)

    def set_user(self, user: dict | None, sync_service) -> None:
        self._user = user
        self._sync_service = sync_service
        self._bind_sync_service(sync_service)

        if user and not user.get("_network_unavailable") and not user.get("offline"):
            self._email_lbl.setText(user.get("email", "Signed in"))
            self._status_lbl.setText("Signed in")
            self._sync_status_lbl.setText("Live sync enabled")
            self._sync_sub_lbl.setText("Changes sync in real time across all your devices.")
            self._sync_now_btn.setEnabled(sync_service is not None)
            self._signout_btn.setEnabled(True)
            self._signin_btn.setVisible(False)
            self._set_household_enabled(True)
        elif user:
            # Signed in but network unavailable at startup
            self._email_lbl.setText(user.get("email", "Signed in"))
            self._status_lbl.setText("Signed in — sync unavailable")
            self._sync_status_lbl.setText("Cloud sync unavailable")
            self._sync_sub_lbl.setText("Sync will resume automatically when internet is available.")
            self._sync_now_btn.setEnabled(False)
            self._signout_btn.setEnabled(True)
            self._signin_btn.setVisible(False)
            self._set_household_enabled(False)
        else:
            self._email_lbl.setText("Not signed in")
            self._status_lbl.setText("Sign in to use DishBoard")
            self._sync_status_lbl.setText("Sign in to enable cloud sync")
            self._sync_sub_lbl.setText("Your recipes, meal plans and more will sync across devices.")
            self._sync_now_btn.setEnabled(False)
            self._signout_btn.setEnabled(False)
            self._signin_btn.setVisible(True)
            self._set_household_enabled(False)

        self._refresh_session_diagnostics()
        self._refresh_sync_status_card()
        self._refresh_household_ui()

    def _on_visibility_changed(self, _snapshot) -> None:
        self._refresh_sync_status_card()

    def _refresh_session_diagnostics(self) -> None:
        try:
            from auth.session_manager import get_session_diagnostics

            diag = get_session_diagnostics()
        except Exception:
            diag = {"status": "unknown", "detail": ""}
        status = str(diag.get("status", "unknown") or "unknown").replace("_", " ")
        backend = str(diag.get("backend", "") or "").strip()
        detail = str(diag.get("detail", "") or "").strip()
        parts = [f"Session storage: {status.title()}"]
        if backend:
            parts.append(f"Backend: {backend}")
        if detail:
            parts.append(detail)
        self._session_store_lbl.setText(" | ".join(parts))

    def _on_sync_now(self):
        if self._sync_service:
            self._sync_now_btn.setEnabled(False)
            self._sync_status_lbl.setText("Syncing…")
            self._sync_service.sync_now()

    def _bind_sync_service(self, sync_service) -> None:
        """Connect sync status slots once per service instance."""
        if self._bound_sync_service is sync_service:
            return
        if self._bound_sync_service is not None:
            try:
                self._bound_sync_service.sync_finished.disconnect(self._on_sync_finished)
            except Exception:
                pass
            try:
                self._bound_sync_service.sync_error.disconnect(self._on_sync_error)
            except Exception:
                pass
            try:
                self._bound_sync_service.runtime_status_changed.disconnect(self._on_sync_runtime_changed)
            except Exception:
                pass

        self._bound_sync_service = sync_service
        if sync_service is None:
            self._refresh_sync_status_card()
            return
        sync_service.sync_finished.connect(self._on_sync_finished)
        sync_service.sync_error.connect(self._on_sync_error)
        runtime_signal = getattr(sync_service, "runtime_status_changed", None)
        if runtime_signal is not None:
            runtime_signal.connect(self._on_sync_runtime_changed)

    def _on_sync_runtime_changed(self, _status: dict) -> None:
        self._refresh_sync_status_card()

    def _on_sync_finished(self, _pushed: int, _pulled: int) -> None:
        if self._user and not self._user.get("_network_unavailable") and not self._user.get("offline"):
            self._sync_now_btn.setEnabled(True)
        self._refresh_sync_status_card()
        self._refresh_household_ui()

    def _on_sync_error(self, _err: str) -> None:
        if self._user and self._sync_service:
            self._sync_now_btn.setEnabled(True)
        self._refresh_sync_status_card()

    def _refresh_sync_status_card(self) -> None:
        if not self._user:
            self._sync_status_lbl.setText("Sign in to enable cloud sync")
            self._sync_sub_lbl.setText("Your recipes, meal plans and more will sync across devices.")
            return
        if self._user.get("_network_unavailable") or self._user.get("offline"):
            self._sync_status_lbl.setText("Cloud sync unavailable")
            self._sync_sub_lbl.setText("Sync will resume automatically when internet is available.")
            return
        runtime = {}
        if self._visibility_service is not None:
            try:
                runtime = self._visibility_service.snapshot().sync_runtime
            except Exception:
                runtime = {}
        if not runtime and self._sync_service is not None and hasattr(self._sync_service, "runtime_status"):
            try:
                runtime = self._sync_service.runtime_status() or {}
            except Exception:
                runtime = {}
        headline, detail = describe_sync_runtime(runtime or {})
        self._sync_status_lbl.setText(headline)
        self._sync_sub_lbl.setText(detail)

    def _set_household_enabled(self, enabled: bool) -> None:
        self._household_controls_enabled = bool(enabled)
        self._refresh_household_ui()

    def _refresh_household_ui(self) -> None:
        from utils.households import status as _hh_status

        st = _hh_status(self._db)
        if st["is_shared"]:
            role = st.get("household_role", "member").capitalize()
            name = st.get("household_name", "") or "Shared Household"
            self._hh_status_lbl.setText(f"{name} ({role})")
            code = st.get("invite_code", "")
            self._hh_code_lbl.setText(f"Invite code: {code}" if code else "")
            self._hh_code_lbl.setVisible(bool(code))
            self._hh_sub_lbl.setText("Shared mode is active. Changes sync to everyone in this household.")
            self._hh_leave_btn.setVisible(True)
        else:
            self._hh_status_lbl.setText("Not in a shared household")
            self._hh_code_lbl.setText("")
            self._hh_code_lbl.setVisible(False)
            self._hh_sub_lbl.setText(
                "Share recipes, meal plans, shopping, nutrition and kitchen data across family accounts."
            )
            self._hh_leave_btn.setVisible(False)

        can_manage_private = self._household_controls_enabled and not st["is_shared"]
        self._hh_name_input.setEnabled(can_manage_private)
        self._hh_create_btn.setEnabled(can_manage_private)
        self._hh_join_input.setEnabled(can_manage_private)
        self._hh_join_btn.setEnabled(
            can_manage_private and bool(self._hh_join_input.text().strip())
        )
        self._hh_leave_btn.setEnabled(self._household_controls_enabled and st["is_shared"])

    def _create_household(self) -> None:
        from utils.households import create_household

        if not self._user:
            return
        name = self._hh_name_input.text().strip() or "My Household"
        ok, msg, _st = create_household(self._db, name=name)
        if ok:
            ThemedMessageBox.information(
                self,
                "Household created",
                "Shared household is active.\nUse the invite code to add family members.",
            )
            if self._sync_service:
                self._sync_service.sync_now()
        else:
            ThemedMessageBox.warning(self, "Could not create household", msg)
        self._refresh_household_ui()

    def _join_household(self) -> None:
        from utils.households import join_household

        if not self._user:
            return
        code = self._hh_join_input.text().strip()
        if not code:
            ThemedMessageBox.information(self, "Join household", "Enter an invite code first.")
            return
        ok, msg, _st = join_household(self._db, invite_code=code)
        if ok:
            self._hh_join_input.clear()
            ThemedMessageBox.information(
                self,
                "Joined household",
                "You are now in shared mode.\nYour app data will sync with this household.",
            )
            if self._sync_service:
                self._sync_service.sync_now()
        else:
            ThemedMessageBox.warning(self, "Could not join household", msg)
        self._refresh_household_ui()

    def _leave_household(self) -> None:
        from utils.households import leave_household

        if not self._user:
            return
        if not ThemedMessageBox.confirm(
            self,
            "Leave household?",
            "You will return to a private account space.\nShared household data will stop syncing.",
            confirm_text="Leave household",
        ):
            return
        ok, msg, _st = leave_household(self._db)
        if ok:
            ThemedMessageBox.information(self, "Household updated", msg)
            if self._sync_service:
                self._sync_service.sync_now()
        else:
            ThemedMessageBox.warning(self, "Could not leave household", msg)
        self._refresh_household_ui()

    def _on_household_code_changed(self, text: str) -> None:
        upper = (text or "").upper()
        if upper != text:
            self._hh_join_input.blockSignals(True)
            self._hh_join_input.setText(upper)
            self._hh_join_input.blockSignals(False)
        self._hh_join_btn.setEnabled(
            self._household_controls_enabled and bool(upper.strip())
        )

    def _on_sign_out(self):
        if not ThemedMessageBox.confirm(
            self,
            "Sign out?",
            "You'll be returned to the login screen.",
            confirm_text="Sign out",
        ):
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

        self.sign_out_requested.emit()

    def apply_theme(self, _mode):
        self._email_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600;"
            f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        self._status_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666', '#888')}; background: transparent;"
        )
        self._sync_status_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600;"
            f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        self._sync_sub_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666', '#888')}; background: transparent;"
        )
        self._session_store_lbl.setStyleSheet(
            f"font-size: 11px; color: {manager.c('#777', '#666')}; background: transparent;"
        )
        self._so_name.setStyleSheet(
            f"font-size: 14px; font-weight: 600;"
            f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        self._so_sub.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666', '#888')}; background: transparent;"
        )
        self._ai_sub_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#888888', '#555555')}; background: transparent; border: none;"
        )
        self._hh_status_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600;"
            f" color: {manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        self._hh_sub_lbl.setStyleSheet(
            f"font-size: 12px; color: {manager.c('#666', '#888')}; background: transparent;"
        )
        self._hh_hint_lbl.setStyleSheet(
            f"font-size: 11px; color: {manager.c('#6f6f6f', '#7f7f7f')}; background: transparent;"
        )
        flat_household_box = "background: transparent; border: none;"
        self._hh_status_box.setStyleSheet(flat_household_box)
        self._hh_create_box.setStyleSheet(flat_household_box)
        self._hh_join_box.setStyleSheet(flat_household_box)
        self._hh_create_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {manager.c('#8a8a8a', '#666666')}; background: transparent;"
        )
        self._hh_join_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {manager.c('#8a8a8a', '#666666')}; background: transparent;"
        )
        hh_input_style = (
            f"QLineEdit {{ background: transparent;"
            f" color: {manager.c('#e8e8e8', '#1a1a1a')};"
            f" border: none; border-bottom: 1px solid {manager.c('#2a2a2a', '#d8cbbd')};"
            " border-radius: 0; padding: 0 4px; }"
            f"QLineEdit:focus {{ background: transparent;"
            " border: none; border-bottom: 1px solid rgba(255,107,53,0.34); }"
        )
        self._hh_name_input.setStyleSheet(
            hh_input_style
        )
        self._hh_join_input.setStyleSheet(hh_input_style)
        self._signin_btn.setStyleSheet(_primary_button_style())
        self._sync_now_btn.setStyleSheet(_secondary_button_style())
        _hh_action_style = _secondary_button_style()
        self._hh_join_btn.setStyleSheet(_hh_action_style)
        self._hh_create_btn.setStyleSheet(self._hh_join_btn.styleSheet())
        self._hh_leave_btn.setStyleSheet(_danger_button_style())
        self._signout_btn.setStyleSheet(_danger_button_style())


# ── Page: Profile ─────────────────────────────────────────────────────────────
