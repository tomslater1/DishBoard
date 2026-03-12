"""
ReauthDialog — compact sign-in dialog shown when a session expires mid-session.

Appears as a modal over the main window so the user can re-authenticate
without losing their current view state.  On success, emits reauth_successful.
On "Sign Out Instead", emits sign_out_requested so the caller can route to
the full login screen.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QWidget,
)

from utils.theme import manager as theme_manager


class ReauthDialog(QDialog):
    reauth_successful  = Signal()
    sign_out_requested = Signal()

    def __init__(self, email: str = "", parent=None):
        super().__init__(parent)
        self._email = email
        self.setWindowTitle("Session Expired")
        self.setModal(True)
        self.setFixedWidth(380)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("reauth-card")
        card.setStyleSheet(
            f"QWidget#reauth-card {{"
            f"  background: {theme_manager.c('#111111', '#ffffff')};"
            f"  border-radius: 16px;"
            f"  border: 1px solid {theme_manager.c('#2a2a2a', '#e0e0e0')};"
            f"}}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(0)

        # Title
        title = QLabel("Session Expired")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700;"
            f" color: {theme_manager.c('#f0f0f0', '#1a1a1a')}; background: transparent;"
        )
        card_layout.addWidget(title)

        card_layout.addSpacing(8)

        subtitle = QLabel("Please sign in again to continue.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            f"font-size: 12px; color: {theme_manager.c('#888', '#666')}; background: transparent;"
        )
        card_layout.addWidget(subtitle)

        card_layout.addSpacing(24)

        field_style = (
            f"QLineEdit {{"
            f"  background: {theme_manager.c('#1a1a1a', '#f7f7f7')};"
            f"  color: {theme_manager.c('#f0f0f0', '#1a1a1a')};"
            f"  border: 1px solid {theme_manager.c('#2a2a2a', '#ddd')};"
            f"  border-radius: 8px; padding: 0 12px; font-size: 13px;"
            f"}}"
            f"QLineEdit:focus {{ border-color: #ff6b35; }}"
        )

        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("Email address")
        self._email_input.setFixedHeight(44)
        self._email_input.setStyleSheet(field_style)
        self._email_input.setText(self._email)
        self._email_input.returnPressed.connect(self._on_sign_in)
        card_layout.addWidget(self._email_input)

        card_layout.addSpacing(8)

        self._pw_input = QLineEdit()
        self._pw_input.setPlaceholderText("Password")
        self._pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_input.setFixedHeight(44)
        self._pw_input.setStyleSheet(field_style)
        self._pw_input.returnPressed.connect(self._on_sign_in)
        card_layout.addWidget(self._pw_input)

        card_layout.addSpacing(8)

        self._error_lbl = QLabel("")
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_lbl.setStyleSheet(
            "color: #dc3545; font-size: 12px; background: transparent;"
        )
        self._error_lbl.setVisible(False)
        card_layout.addWidget(self._error_lbl)

        card_layout.addSpacing(4)

        self._signin_btn = QPushButton("Sign In")
        self._signin_btn.setFixedHeight(46)
        self._signin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._signin_btn.setStyleSheet(
            "QPushButton {"
            "  background: #ff6b35; color: #ffffff;"
            "  border-radius: 10px; font-size: 14px; font-weight: 700; border: none;"
            "}"
            "QPushButton:hover { background: #e05a28; }"
            "QPushButton:disabled { background: #553322; color: #888; }"
        )
        self._signin_btn.clicked.connect(self._on_sign_in)
        card_layout.addWidget(self._signin_btn)

        card_layout.addSpacing(16)

        signout_btn = QPushButton("Sign Out Instead")
        signout_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" color: {theme_manager.c('#666', '#999')}; font-size: 12px; }}"
            "QPushButton:hover { color: #ff6b35; }"
        )
        signout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        signout_btn.clicked.connect(self._on_sign_out)
        card_layout.addWidget(signout_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        root.addWidget(card)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_sign_in(self):
        email = self._email_input.text().strip()
        pw    = self._pw_input.text()

        if not email or not pw:
            self._error_lbl.setText("Please enter your email and password.")
            self._error_lbl.setVisible(True)
            return

        self._signin_btn.setEnabled(False)
        self._signin_btn.setText("Please wait…")
        self._error_lbl.setVisible(False)

        from utils.workers import run_async
        from auth.supabase_client import get_client

        def _work():
            client = get_client()
            if client is None:
                raise RuntimeError("no_connection")
            return client.auth.sign_in_with_password({"email": email, "password": pw})

        def _done(response):
            self._signin_btn.setEnabled(True)
            self._signin_btn.setText("Sign In")
            if response and response.user and response.session:
                from auth.session_manager import build_session_dict, save_session
                session = build_session_dict(response)
                save_session(session)
                self.reauth_successful.emit()
                self.accept()
            else:
                self._error_lbl.setText("Sign-in failed. Check your email and password.")
                self._error_lbl.setVisible(True)

        def _err(err: str):
            self._signin_btn.setEnabled(True)
            self._signin_btn.setText("Sign In")
            msg = err.lower()
            if "no_connection" in msg:
                text = "No internet connection. Check your network and try again."
            elif "invalid" in msg:
                text = "Incorrect email or password."
            elif "rate limit" in msg or "too many" in msg:
                text = "Too many attempts. Please wait 30 seconds."
            else:
                text = "Sign-in error. Please try again."
            self._error_lbl.setText(text)
            self._error_lbl.setVisible(True)

        run_async(_work, on_result=_done, on_error=_err)

    def _on_sign_out(self):
        from auth.session_manager import clear_session
        clear_session()
        self.sign_out_requested.emit()
        self.reject()
