"""
LoginView — pre-app authentication screen.

Shown when no valid Supabase session is found at startup.
Offers email/password, Google OAuth, Apple placeholder, and offline mode.
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
    continue_offline = Signal()       # emits when user chooses no-account mode

    def __init__(self, parent=None):
        super().__init__(parent)
        self._oauth_poll_timer = QTimer(self)
        self._oauth_poll_timer.setInterval(500)
        self._oauth_poll_timer.timeout.connect(self._poll_oauth)
        self._build_ui()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Full-screen dark bg
        self.setStyleSheet(
            f"background: {theme_manager.c('#090909', '#f5f5f5')};"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addStretch(2)

        # Centre column — fixed width card
        centre_row = QHBoxLayout()
        centre_row.setContentsMargins(0, 0, 0, 0)
        centre_row.addStretch()

        card = QWidget()
        card.setFixedWidth(400)
        card.setStyleSheet(
            f"background: {theme_manager.c('#111111', '#ffffff')};"
            " border-radius: 16px;"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(0)

        # Logo + title
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

        tagline = QLabel("Your recipes, everywhere.")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(
            f"font-size: 13px; color: {theme_manager.c('#666', '#888')}; background: transparent;"
        )
        card_layout.addWidget(tagline)

        card_layout.addSpacing(28)

        # ── Mode toggle label ──────────────────────────────────────────────────
        self._mode_lbl = QLabel("Sign in to your account")
        self._mode_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mode_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700;"
            f" color: {theme_manager.c('#e0e0e0', '#1a1a1a')}; background: transparent;"
        )
        card_layout.addWidget(self._mode_lbl)

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
        self._email_input.setPlaceholderText("Email")
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

        card_layout.addSpacing(12)

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

        # ── Sign In button ─────────────────────────────────────────────────────
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

        card_layout.addSpacing(6)

        # ── Toggle: Create Account / Sign In ───────────────────────────────────
        self._toggle_btn = QPushButton("Don't have an account?  Create one →")
        self._toggle_btn.setFixedHeight(32)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" color: {theme_manager.c('#888', '#888')}; font-size: 12px; }}"
            "QPushButton:hover { color: #ff6b35; }"
        )
        self._toggle_btn.clicked.connect(self._toggle_mode)
        card_layout.addWidget(self._toggle_btn, alignment=Qt.AlignmentFlag.AlignCenter)

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

        # ── OAuth buttons ──────────────────────────────────────────────────────
        oauth_style = (
            "QPushButton {"
            f"  background: {theme_manager.c('#1a1a1a', '#f7f7f7')};"
            f"  color: {theme_manager.c('#e0e0e0', '#1a1a1a')};"
            f"  border: 1px solid {theme_manager.c('#2a2a2a', '#ddd')};"
            "  border-radius: 10px; font-size: 13px; font-weight: 600;"
            "  text-align: center; padding: 0 16px;"
            "}"
            "QPushButton:hover {"
            f"  background: {theme_manager.c('#222', '#efefef')};"
            "  border-color: rgba(255,107,53,0.5);"
            "}"
            "QPushButton:disabled {"
            f"  background: {theme_manager.c('#141414', '#f3f3f3')};"
            f"  color: {theme_manager.c('#444', '#bbb')};"
            f"  border-color: {theme_manager.c('#1e1e1e', '#e5e5e5')};"
            "}"
        )

        self._google_btn = QPushButton("  Sign in with Google")
        self._google_btn.setIcon(qta.icon("fa5b.google", color="#4285F4"))
        self._google_btn.setIconSize(QSize(16, 16))
        self._google_btn.setFixedHeight(46)
        self._google_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._google_btn.setStyleSheet(oauth_style)
        self._google_btn.clicked.connect(self._on_google)
        card_layout.addWidget(self._google_btn)

        card_layout.addSpacing(8)

        self._apple_btn = QPushButton("  Sign in with Apple")
        self._apple_btn.setIcon(qta.icon("fa5b.apple", color=theme_manager.c("#555", "#aaa")))
        self._apple_btn.setIconSize(QSize(16, 16))
        self._apple_btn.setFixedHeight(46)
        self._apple_btn.setEnabled(False)
        self._apple_btn.setToolTip("Coming soon — requires Apple Developer account setup")
        self._apple_btn.setStyleSheet(oauth_style)
        card_layout.addWidget(self._apple_btn)

        card_layout.addSpacing(24)

        # ── Continue without account ───────────────────────────────────────────
        offline_btn = QPushButton("Continue without account  →")
        offline_btn.setFixedHeight(32)
        offline_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        offline_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" color: {theme_manager.c('#555', '#aaa')}; font-size: 12px; }}"
            "QPushButton:hover { color: #ff6b35; }"
        )
        offline_btn.clicked.connect(self.continue_offline.emit)
        card_layout.addWidget(offline_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        centre_row.addWidget(card)
        centre_row.addStretch()
        root.addLayout(centre_row)
        root.addStretch(3)

        self._is_signup_mode = False

    # ── Mode toggle ────────────────────────────────────────────────────────────

    def _toggle_mode(self):
        self._is_signup_mode = not self._is_signup_mode
        if self._is_signup_mode:
            self._mode_lbl.setText("Create a new account")
            self._signin_btn.setText("Create Account")
            self._toggle_btn.setText("Already have an account?  Sign in →")
        else:
            self._mode_lbl.setText("Sign in to your account")
            self._signin_btn.setText("Sign In")
            self._toggle_btn.setText("Don't have an account?  Create one →")
        self._clear_error()

    # ── Email / Password auth ─────────────────────────────────────────────────

    def _on_sign_in(self):
        email = self._email_input.text().strip()
        pw    = self._pw_input.text()
        if not email or not pw:
            self._show_error("Please enter your email and password.")
            return

        self._set_loading(True)
        self._clear_error()

        from utils.workers import run_async
        from auth.supabase_client import get_client

        def _work():
            client = get_client()
            if client is None:
                raise RuntimeError(
                    "Supabase is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY to your .env file."
                )
            if self._is_signup_mode:
                return client.auth.sign_up({"email": email, "password": pw})
            else:
                return client.auth.sign_in_with_password({"email": email, "password": pw})

        def _done(response):
            self._set_loading(False)
            if response and response.user:
                from auth.session_manager import build_session_dict, save_session
                session = build_session_dict(response)
                save_session(session)
                self.login_successful.emit(session["user"])
            else:
                if self._is_signup_mode:
                    self._show_error(
                        "Account created! Check your email to confirm, then sign in."
                    )
                else:
                    self._show_error("Sign-in failed. Please check your credentials.")

        def _err(err: str):
            self._set_loading(False)
            msg = err.lower()
            if "rate limit" in msg:
                self._show_error("Too many attempts. Please wait a few minutes and try again.")
            elif "invalid" in msg or "credentials" in msg or ("email" in msg and "password" in msg):
                self._show_error("Incorrect email or password.")
            elif "not confirmed" in msg or "confirm" in msg:
                self._show_error(
                    "Email not confirmed. Check your inbox for a confirmation link."
                )
            elif "already registered" in msg or "already exists" in msg:
                self._show_error("An account with this email already exists. Try signing in.")
            elif "configure" in msg or "supabase" in msg.lower():
                self._show_error(err)
            else:
                self._show_error(f"Error: {err[:120]}")

        run_async(_work, on_result=_done, on_error=_err)

    # ── Google OAuth ──────────────────────────────────────────────────────────

    def _on_google(self):
        from auth.supabase_client import get_client
        client = get_client()
        if client is None:
            self._show_error(
                "Supabase is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY to your .env file."
            )
            return

        self._set_loading(True)
        self._clear_error()

        try:
            from auth.oauth_server import start_oauth_callback_server, CALLBACK_URL
            done_event = start_oauth_callback_server()

            response = client.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {"redirect_to": CALLBACK_URL},
            })
            url = getattr(response, "url", None)
            if not url:
                self._show_error("Could not get Google sign-in URL from Supabase.")
                self._set_loading(False)
                return

            webbrowser.open(url)

            # Store reference so we know which event to poll
            self._oauth_done_event = done_event
            self._oauth_poll_timer.start()

        except Exception as exc:
            self._set_loading(False)
            self._show_error(f"Google sign-in error: {exc}")

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
        self._google_btn.setEnabled(not loading)
        self._email_input.setEnabled(not loading)
        self._pw_input.setEnabled(not loading)
        if loading:
            self._signin_btn.setText("Please wait…")
        else:
            self._signin_btn.setText("Create Account" if self._is_signup_mode else "Sign In")
