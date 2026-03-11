"""
LoginView — pre-app authentication screen.

Shown when no valid Supabase session is found at startup.
Offers email/password sign-in and account creation.
Google and Apple OAuth are placeholders (coming soon).
"""

from __future__ import annotations

import os
import webbrowser

import qtawesome as qta
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFrame,
)

from utils.theme import manager as theme_manager


class LoginView(QWidget):
    login_successful = Signal(dict)   # emits user dict on success

    def __init__(self, parent=None):
        super().__init__(parent)
        self._oauth_poll_timer = QTimer(self)
        self._oauth_poll_timer.setInterval(500)
        self._oauth_poll_timer.timeout.connect(self._poll_oauth)
        self._build_ui()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet(
            f"background: {theme_manager.c('#090909', '#f5f5f5')};"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addStretch(2)

        centre_row = QHBoxLayout()
        centre_row.setContentsMargins(0, 0, 0, 0)
        centre_row.addStretch()

        card = QWidget()
        card.setFixedWidth(420)
        card.setStyleSheet(
            f"background: {theme_manager.c('#111111', '#ffffff')};"
            " border-radius: 16px;"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(0)

        # ── Logo + title ───────────────────────────────────────────────────────
        logo_row = QHBoxLayout()
        logo_row.setSpacing(12)
        logo_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        from utils.paths import get_resource_path
        logo_path = get_resource_path(
            "assets/icons/DishBoard-darkicon.png"
            if theme_manager.mode == "dark"
            else "assets/icons/DishBoard-lighticon.png"
        )
        if os.path.exists(logo_path):
            px = QPixmap(logo_path).scaled(
                44, 44,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_lbl = QLabel()
            logo_lbl.setPixmap(px)
            logo_lbl.setStyleSheet("background: transparent;")
            logo_row.addWidget(logo_lbl)

        app_name = QLabel("DishBoard")
        app_name.setStyleSheet(
            f"font-size: 24px; font-weight: 800;"
            f" color: {theme_manager.c('#f0f0f0', '#1a1a1a')}; background: transparent;"
        )
        logo_row.addWidget(app_name)
        card_layout.addLayout(logo_row)

        card_layout.addSpacing(6)

        tagline = QLabel("Your recipes, meal plans, and nutrition — everywhere.")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)
        tagline.setStyleSheet(
            f"font-size: 12px; color: {theme_manager.c('#666', '#888')}; background: transparent;"
        )
        card_layout.addWidget(tagline)

        card_layout.addSpacing(28)

        # ── Mode header ────────────────────────────────────────────────────────
        # A coloured pill that clearly shows whether user is signing in or signing up
        self._mode_pill = QWidget()
        self._mode_pill.setFixedHeight(36)
        pill_layout = QHBoxLayout(self._mode_pill)
        pill_layout.setContentsMargins(0, 0, 0, 0)
        pill_layout.setSpacing(0)

        self._signin_tab = QPushButton("Sign In")
        self._signin_tab.setFixedHeight(36)
        self._signin_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        self._signin_tab.clicked.connect(lambda: self._set_mode(False))

        self._signup_tab = QPushButton("Create Account")
        self._signup_tab.setFixedHeight(36)
        self._signup_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        self._signup_tab.clicked.connect(lambda: self._set_mode(True))

        for btn in (self._signin_tab, self._signup_tab):
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none;"
                f" color: {theme_manager.c('#888', '#888')};"
                " font-size: 13px; font-weight: 600; border-radius: 8px; }"
                "QPushButton:hover { color: #ff6b35; }"
            )

        pill_layout.addWidget(self._signin_tab)
        pill_layout.addWidget(self._signup_tab)
        card_layout.addWidget(self._mode_pill)

        card_layout.addSpacing(16)

        # ── Email / Password fields ────────────────────────────────────────────
        field_style = (
            f"QLineEdit {{"
            f"  background: {theme_manager.c('#1a1a1a', '#f7f7f7')};"
            f"  color: {theme_manager.c('#f0f0f0', '#1a1a1a')};"
            f"  border: 1px solid {theme_manager.c('#2a2a2a', '#ddd')};"
            f"  border-radius: 8px; padding: 0 12px; font-size: 13px;"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border-color: #ff6b35;"
            f"}}"
        )

        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("Email address")
        self._email_input.setFixedHeight(44)
        self._email_input.setStyleSheet(field_style)
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

        card_layout.addSpacing(4)

        # Password hint shown only in signup mode
        self._pw_hint = QLabel("Minimum 6 characters")
        self._pw_hint.setStyleSheet(
            f"color: {theme_manager.c('#555', '#999')}; font-size: 11px; background: transparent;"
        )
        self._pw_hint.setVisible(False)
        card_layout.addWidget(self._pw_hint)

        card_layout.addSpacing(8)

        # ── Error label ────────────────────────────────────────────────────────
        self._error_lbl = QLabel("")
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_lbl.setStyleSheet(
            "color: #dc3545; font-size: 12px; background: transparent;"
        )
        self._error_lbl.setVisible(False)
        card_layout.addWidget(self._error_lbl)

        card_layout.addSpacing(4)

        # ── Primary action button ──────────────────────────────────────────────
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

        card_layout.addSpacing(20)

        # ── Divider ────────────────────────────────────────────────────────────
        div_row = QHBoxLayout()
        div_row.setSpacing(10)
        for _ in range(2):
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet(
                f"color: {theme_manager.c('#2a2a2a', '#ddd')};"
                f" background: {theme_manager.c('#2a2a2a', '#ddd')};"
                " border: none; max-height: 1px;"
            )
            div_row.addWidget(line, 1)
        or_lbl = QLabel("or")
        or_lbl.setStyleSheet(
            f"color: {theme_manager.c('#555', '#aaa')}; font-size: 12px; background: transparent;"
        )
        div_row.insertWidget(1, or_lbl)
        card_layout.addLayout(div_row)

        card_layout.addSpacing(16)

        # ── OAuth buttons — both disabled pending setup ─────────────────────────
        oauth_disabled_style = (
            "QPushButton {"
            f"  background: {theme_manager.c('#141414', '#f3f3f3')};"
            f"  color: {theme_manager.c('#444', '#bbb')};"
            f"  border: 1px solid {theme_manager.c('#1e1e1e', '#e5e5e5')};"
            "  border-radius: 10px; font-size: 13px; font-weight: 600;"
            "  text-align: center; padding: 0 16px;"
            "}"
        )

        self._google_btn = QPushButton("  Sign in with Google  (coming soon)")
        self._google_btn.setIcon(qta.icon("fa5b.google", color="#555555"))
        self._google_btn.setIconSize(QSize(16, 16))
        self._google_btn.setFixedHeight(46)
        self._google_btn.setEnabled(False)
        self._google_btn.setToolTip(
            "Google sign-in is coming soon — use email and password for now"
        )
        self._google_btn.setStyleSheet(oauth_disabled_style)
        card_layout.addWidget(self._google_btn)

        card_layout.addSpacing(8)

        self._apple_btn = QPushButton("  Sign in with Apple  (coming soon)")
        self._apple_btn.setIcon(qta.icon("fa5b.apple", color=theme_manager.c("#555", "#aaa")))
        self._apple_btn.setIconSize(QSize(16, 16))
        self._apple_btn.setFixedHeight(46)
        self._apple_btn.setEnabled(False)
        self._apple_btn.setToolTip("Coming soon — requires Apple Developer account setup")
        self._apple_btn.setStyleSheet(oauth_disabled_style)
        card_layout.addWidget(self._apple_btn)

        card_layout.addSpacing(24)

        centre_row.addWidget(card)
        centre_row.addStretch()
        root.addLayout(centre_row)
        root.addStretch(3)

        self._is_signup_mode = False
        self._update_tab_style()

    # ── Mode switching ──────────────────────────────────────────────────────────

    def _set_mode(self, signup: bool):
        if self._is_signup_mode == signup:
            return
        self._is_signup_mode = signup
        self._signin_btn.setText("Create Account" if signup else "Sign In")
        self._pw_hint.setVisible(signup)
        self._clear_error()
        self._update_tab_style()

    def _update_tab_style(self):
        active = (
            f"QPushButton {{ background: rgba(255,107,53,0.15);"
            f" border: none; color: #ff6b35;"
            f" font-size: 13px; font-weight: 700; border-radius: 8px; }}"
        )
        inactive = (
            f"QPushButton {{ background: transparent; border: none;"
            f" color: {theme_manager.c('#888', '#888')};"
            f" font-size: 13px; font-weight: 600; border-radius: 8px; }}"
            f"QPushButton:hover {{ color: #ff6b35; }}"
        )
        self._signup_tab.setStyleSheet(active if self._is_signup_mode else inactive)
        self._signin_tab.setStyleSheet(inactive if self._is_signup_mode else active)

    # ── Email / Password auth ─────────────────────────────────────────────────

    def _on_sign_in(self):
        email = self._email_input.text().strip()
        pw    = self._pw_input.text()

        if not email:
            self._show_error("Please enter your email address.")
            return
        if "@" not in email or "." not in email.split("@")[-1]:
            self._show_error("Please enter a valid email address.")
            return
        if not pw:
            self._show_error("Please enter your password.")
            return
        if self._is_signup_mode and len(pw) < 6:
            self._show_error("Password must be at least 6 characters.")
            return

        self._set_loading(True)
        self._clear_error()

        from utils.workers import run_async
        from auth.supabase_client import get_client

        is_signup = self._is_signup_mode

        def _work():
            client = get_client()
            if client is None:
                raise RuntimeError("no_connection")
            if is_signup:
                return client.auth.sign_up({"email": email, "password": pw})
            else:
                return client.auth.sign_in_with_password({"email": email, "password": pw})

        def _done(response):
            self._set_loading(False)
            if response and response.user and response.session:
                from auth.session_manager import build_session_dict, save_session
                session = build_session_dict(response)
                save_session(session)
                self.login_successful.emit(session["user"])
            elif response and response.user and not response.session:
                # Sign-up with email confirmation required
                self._show_error(
                    "Account created! Check your email for a confirmation link, then sign in."
                )
            else:
                if is_signup:
                    self._show_error("Could not create account. Please try again.")
                else:
                    self._show_error("Sign-in failed. Check your email and password.")

        def _err(err: str):
            self._set_loading(False)
            msg = err.lower()
            if "no_connection" in msg or "supabase is not configured" in msg:
                self._show_error(
                    "No internet connection. Check your network and try again."
                )
            elif "rate limit" in msg or "too many" in msg:
                self._show_error(
                    "Too many attempts. Please wait a few minutes and try again."
                )
            elif "invalid" in msg and ("login" in msg or "credentials" in msg or "password" in msg):
                self._show_error(
                    "Incorrect email or password. "
                    "Check your details or use 'Create Account' to sign up."
                )
            elif "not confirmed" in msg or "email not confirmed" in msg:
                self._show_error(
                    "Email not confirmed yet. Check your inbox for the confirmation link."
                )
            elif "already registered" in msg or "already exists" in msg or "user_already_exists" in msg:
                self._show_error(
                    "An account with this email already exists — try signing in instead."
                )
            elif "password" in msg and ("weak" in msg or "short" in msg or "characters" in msg):
                self._show_error("Password is too weak. Use at least 6 characters.")
            elif "network" in msg or "connect" in msg or "timeout" in msg or "unreachable" in msg:
                self._show_error(
                    "Could not connect to DishBoard servers. Check your internet connection."
                )
            elif "invalid_email" in msg or ("email" in msg and "invalid" in msg):
                self._show_error("Please enter a valid email address.")
            else:
                # Show the raw error for unrecognised failures so the user can report it
                self._show_error(f"Sign-in error: {err.strip().splitlines()[-1][:140]}")

        run_async(_work, on_result=_done, on_error=_err)

    # ── Google OAuth (stub — kept for future use) ─────────────────────────────

    def _on_google(self):
        pass   # button is disabled; this is never called

    def _poll_oauth(self):
        """Called every 500ms to check if OAuth callback has completed."""
        done_event = getattr(self, "_oauth_done_event", None)
        if done_event is None or not done_event.is_set():
            return

        self._oauth_poll_timer.stop()
        self._set_loading(False)

        from auth.oauth_server import get_received_session, stop_server
        from auth.session_manager import save_session
        session = get_received_session()
        stop_server()

        if session and session.get("user", {}).get("id"):
            save_session(session)
            self.login_successful.emit(session["user"])
        else:
            self._show_error("Google sign-in did not complete. Please try again.")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _show_error(self, msg: str):
        self._error_lbl.setText(msg)
        self._error_lbl.setVisible(True)

    def _clear_error(self):
        self._error_lbl.setText("")
        self._error_lbl.setVisible(False)

    def _set_loading(self, loading: bool):
        self._signin_btn.setEnabled(not loading)
        self._email_input.setEnabled(not loading)
        self._pw_input.setEnabled(not loading)
        self._signin_tab.setEnabled(not loading)
        self._signup_tab.setEnabled(not loading)
        if loading:
            self._signin_btn.setText("Please wait…")
        else:
            self._signin_btn.setText("Create Account" if self._is_signup_mode else "Sign In")
