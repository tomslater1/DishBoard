"""
LoginView — pre-app authentication screen.

Shown when no valid Supabase session is found at startup.
Offers email/password sign-in and account creation.
Google and Apple OAuth are placeholders (coming soon).

The login card uses an inner QStackedWidget with 3 pages:
  Page 0 — Main login form (sign in / create account)
  Page 1 — Forgot password
  Page 2 — Email confirmation sent (after sign-up)
"""

from __future__ import annotations

import os

import qtawesome as qta
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFrame, QStackedWidget,
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
        logo_path = get_resource_path("assets/icons/Dishboard-orange.png")
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

        # ── Inner page stack ───────────────────────────────────────────────────
        self._page_stack = QStackedWidget()
        self._page_stack.setStyleSheet("background: transparent;")
        self._page_stack.addWidget(self._build_main_page())    # 0
        self._page_stack.addWidget(self._build_forgot_pw_page())  # 1
        self._page_stack.addWidget(self._build_confirmation_page())  # 2
        card_layout.addWidget(self._page_stack)

        centre_row.addWidget(card)
        centre_row.addStretch()
        root.addLayout(centre_row)
        root.addStretch(3)

        self._is_signup_mode = False
        self._update_tab_style()

    # ── Page 0: main login form ────────────────────────────────────────────────

    def _build_main_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Mode tabs
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
        layout.addWidget(self._mode_pill)

        layout.addSpacing(16)

        # Fields
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
        layout.addWidget(self._email_input)

        layout.addSpacing(8)

        self._pw_input = QLineEdit()
        self._pw_input.setPlaceholderText("Password")
        self._pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_input.setFixedHeight(44)
        self._pw_input.setStyleSheet(field_style)
        self._pw_input.returnPressed.connect(self._on_sign_in)
        layout.addWidget(self._pw_input)

        layout.addSpacing(8)

        # Confirm password (signup only)
        self._pw_confirm_input = QLineEdit()
        self._pw_confirm_input.setPlaceholderText("Confirm password")
        self._pw_confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_confirm_input.setFixedHeight(44)
        self._pw_confirm_input.setStyleSheet(field_style)
        self._pw_confirm_input.returnPressed.connect(self._on_sign_in)
        self._pw_confirm_input.setVisible(False)
        layout.addWidget(self._pw_confirm_input)

        layout.addSpacing(4)

        # Password hint (signup only) + forgot password link (signin only)
        hints_row = QHBoxLayout()
        hints_row.setContentsMargins(0, 0, 0, 0)

        self._pw_hint = QLabel("Minimum 6 characters")
        self._pw_hint.setStyleSheet(
            f"color: {theme_manager.c('#555', '#999')}; font-size: 11px; background: transparent;"
        )
        self._pw_hint.setVisible(False)
        hints_row.addWidget(self._pw_hint)

        hints_row.addStretch()

        self._forgot_pw_link = QPushButton("Forgot password?")
        self._forgot_pw_link.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" color: {theme_manager.c('#555', '#999')}; font-size: 11px; }}"
            "QPushButton:hover { color: #ff6b35; }"
        )
        self._forgot_pw_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._forgot_pw_link.clicked.connect(self._show_forgot_pw)
        hints_row.addWidget(self._forgot_pw_link)

        layout.addLayout(hints_row)

        layout.addSpacing(8)

        # Error label
        self._error_lbl = QLabel("")
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_lbl.setStyleSheet(
            "color: #dc3545; font-size: 12px; background: transparent;"
        )
        self._error_lbl.setVisible(False)
        layout.addWidget(self._error_lbl)

        layout.addSpacing(4)

        # Primary action button
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
        layout.addWidget(self._signin_btn)

        layout.addSpacing(20)

        # Divider
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
        layout.addLayout(div_row)

        layout.addSpacing(16)

        # Google OAuth button — active
        google_style = (
            "QPushButton {"
            f"  background: {theme_manager.c('#1a1a1a', '#f8f8f8')};"
            f"  color: {theme_manager.c('#e0e0e0', '#1a1a1a')};"
            f"  border: 1px solid {theme_manager.c('#2a2a2a', '#dddddd')};"
            "  border-radius: 10px; font-size: 13px; font-weight: 600;"
            "  text-align: center; padding: 0 16px;"
            "}"
            "QPushButton:hover {"
            f"  background: {theme_manager.c('#222222', '#eeeeee')};"
            f"  border-color: {theme_manager.c('#444444', '#bbbbbb')};"
            "}"
            "QPushButton:disabled {"
            f"  background: {theme_manager.c('#141414', '#f3f3f3')};"
            f"  color: {theme_manager.c('#444', '#bbb')};"
            "}"
        )

        self._google_btn = QPushButton("  Sign in with Google")
        self._google_btn.setIcon(qta.icon("fa5b.google", color="#4285f4"))
        self._google_btn.setIconSize(QSize(16, 16))
        self._google_btn.setFixedHeight(46)
        self._google_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._google_btn.setStyleSheet(google_style)
        self._google_btn.clicked.connect(self._on_google)
        layout.addWidget(self._google_btn)

        layout.addSpacing(8)

        # Apple button — still coming soon
        apple_disabled_style = (
            "QPushButton {"
            f"  background: {theme_manager.c('#141414', '#f3f3f3')};"
            f"  color: {theme_manager.c('#444', '#bbb')};"
            f"  border: 1px solid {theme_manager.c('#1e1e1e', '#e5e5e5')};"
            "  border-radius: 10px; font-size: 13px; font-weight: 600;"
            "  text-align: center; padding: 0 16px;"
            "}"
        )
        self._apple_btn = QPushButton("  Sign in with Apple  (coming soon)")
        self._apple_btn.setIcon(qta.icon("fa5b.apple", color=theme_manager.c("#555", "#aaa")))
        self._apple_btn.setIconSize(QSize(16, 16))
        self._apple_btn.setFixedHeight(46)
        self._apple_btn.setEnabled(False)
        self._apple_btn.setToolTip("Coming soon — requires Apple Developer account setup")
        self._apple_btn.setStyleSheet(apple_disabled_style)
        layout.addWidget(self._apple_btn)

        layout.addSpacing(24)

        return page

    # ── Page 1: forgot password ────────────────────────────────────────────────

    def _build_forgot_pw_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("Reset your password")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700;"
            f" color: {theme_manager.c('#f0f0f0', '#1a1a1a')}; background: transparent;"
        )
        layout.addWidget(title)

        layout.addSpacing(8)

        desc = QLabel("Enter your email address and we'll send you a link to reset your password.")
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"font-size: 12px; color: {theme_manager.c('#888', '#666')}; background: transparent;"
        )
        layout.addWidget(desc)

        layout.addSpacing(20)

        field_style = (
            f"QLineEdit {{"
            f"  background: {theme_manager.c('#1a1a1a', '#f7f7f7')};"
            f"  color: {theme_manager.c('#f0f0f0', '#1a1a1a')};"
            f"  border: 1px solid {theme_manager.c('#2a2a2a', '#ddd')};"
            f"  border-radius: 8px; padding: 0 12px; font-size: 13px;"
            f"}}"
            f"QLineEdit:focus {{ border-color: #ff6b35; }}"
        )

        self._reset_email_input = QLineEdit()
        self._reset_email_input.setPlaceholderText("Email address")
        self._reset_email_input.setFixedHeight(44)
        self._reset_email_input.setStyleSheet(field_style)
        self._reset_email_input.returnPressed.connect(self._on_send_reset)
        layout.addWidget(self._reset_email_input)

        layout.addSpacing(8)

        self._reset_feedback_lbl = QLabel("")
        self._reset_feedback_lbl.setWordWrap(True)
        self._reset_feedback_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._reset_feedback_lbl.setStyleSheet("font-size: 12px; background: transparent;")
        self._reset_feedback_lbl.setVisible(False)
        layout.addWidget(self._reset_feedback_lbl)

        layout.addSpacing(4)

        self._send_reset_btn = QPushButton("Send Reset Link")
        self._send_reset_btn.setFixedHeight(46)
        self._send_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_reset_btn.setStyleSheet(
            "QPushButton {"
            "  background: #ff6b35; color: #ffffff;"
            "  border-radius: 10px; font-size: 14px; font-weight: 700; border: none;"
            "}"
            "QPushButton:hover { background: #e05a28; }"
            "QPushButton:disabled { background: #553322; color: #888; }"
        )
        self._send_reset_btn.clicked.connect(self._on_send_reset)
        layout.addWidget(self._send_reset_btn)

        layout.addSpacing(16)

        back_btn = QPushButton("← Back to Sign In")
        back_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" color: {theme_manager.c('#888', '#666')}; font-size: 12px; }}"
            "QPushButton:hover { color: #ff6b35; }"
        )
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(lambda: self._page_stack.setCurrentIndex(0))
        layout.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(24)
        layout.addStretch()

        return page

    # ── Page 2: email confirmation sent ───────────────────────────────────────

    def _build_confirmation_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addSpacing(8)

        check_lbl = QLabel("Account created ✓")
        check_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check_lbl.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #34d399; background: transparent;"
        )
        layout.addWidget(check_lbl)

        layout.addSpacing(12)

        self._confirm_desc_lbl = QLabel(
            "We've sent a confirmation link to your email.\n"
            "Click it to activate your account, then sign in."
        )
        self._confirm_desc_lbl.setWordWrap(True)
        self._confirm_desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._confirm_desc_lbl.setStyleSheet(
            f"font-size: 12px; color: {theme_manager.c('#aaa', '#666')}; background: transparent;"
        )
        layout.addWidget(self._confirm_desc_lbl)

        layout.addSpacing(24)

        self._resend_feedback_lbl = QLabel("")
        self._resend_feedback_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._resend_feedback_lbl.setStyleSheet("font-size: 12px; background: transparent;")
        self._resend_feedback_lbl.setVisible(False)
        layout.addWidget(self._resend_feedback_lbl)

        self._resend_btn = QPushButton("Resend confirmation email")
        self._resend_btn.setFixedHeight(44)
        self._resend_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._resend_btn.setStyleSheet(
            "QPushButton {"
            f"  background: {theme_manager.c('#1a1a1a', '#f3f3f3')};"
            f"  color: {theme_manager.c('#aaa', '#555')};"
            f"  border: 1px solid {theme_manager.c('#2a2a2a', '#ddd')};"
            "  border-radius: 10px; font-size: 13px; font-weight: 600;"
            "}"
            "QPushButton:hover { border-color: #ff6b35; color: #ff6b35; }"
            "QPushButton:disabled { opacity: 0.5; }"
        )
        self._resend_btn.clicked.connect(self._on_resend_confirmation)
        layout.addWidget(self._resend_btn)

        layout.addSpacing(16)

        back_btn2 = QPushButton("← Back to Sign In")
        back_btn2.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" color: {theme_manager.c('#888', '#666')}; font-size: 12px; }}"
            "QPushButton:hover { color: #ff6b35; }"
        )
        back_btn2.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn2.clicked.connect(self._go_back_to_signin)
        layout.addWidget(back_btn2, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(24)
        layout.addStretch()

        return page

    # ── Mode switching ──────────────────────────────────────────────────────────

    def _set_mode(self, signup: bool):
        if self._is_signup_mode == signup:
            return
        self._is_signup_mode = signup
        self._signin_btn.setText("Create Account" if signup else "Sign In")
        self._pw_hint.setVisible(signup)
        self._pw_confirm_input.setVisible(signup)
        self._forgot_pw_link.setVisible(not signup)
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
        # forgot link only visible on sign-in tab
        self._forgot_pw_link.setVisible(not self._is_signup_mode)

    # ── Forgot password ────────────────────────────────────────────────────────

    def _show_forgot_pw(self):
        self._reset_email_input.setText(self._email_input.text().strip())
        self._reset_feedback_lbl.setVisible(False)
        self._send_reset_btn.setEnabled(True)
        self._send_reset_btn.setText("Send Reset Link")
        self._page_stack.setCurrentIndex(1)

    def _on_send_reset(self):
        email = self._reset_email_input.text().strip()
        if not email or "@" not in email:
            self._reset_feedback_lbl.setText("Please enter a valid email address.")
            self._reset_feedback_lbl.setStyleSheet("color: #dc3545; font-size: 12px; background: transparent;")
            self._reset_feedback_lbl.setVisible(True)
            return

        self._send_reset_btn.setEnabled(False)
        self._send_reset_btn.setText("Sending…")
        self._reset_feedback_lbl.setVisible(False)

        from utils.workers import run_async
        from auth.supabase_client import get_client

        def _work():
            client = get_client()
            if client is None:
                raise RuntimeError("no_connection")
            client.auth.reset_password_for_email(email)

        def _done(_):
            self._send_reset_btn.setEnabled(True)
            self._send_reset_btn.setText("Send Reset Link")
            self._reset_feedback_lbl.setText(
                "Check your inbox — we've sent a reset link."
            )
            self._reset_feedback_lbl.setStyleSheet("color: #34d399; font-size: 12px; background: transparent;")
            self._reset_feedback_lbl.setVisible(True)

        def _err(err: str):
            self._send_reset_btn.setEnabled(True)
            self._send_reset_btn.setText("Send Reset Link")
            msg = err.lower()
            if "no_connection" in msg or "supabase" in msg:
                text = "No internet connection. Check your network and try again."
            else:
                text = "Could not send reset email. Please try again."
            self._reset_feedback_lbl.setText(text)
            self._reset_feedback_lbl.setStyleSheet("color: #dc3545; font-size: 12px; background: transparent;")
            self._reset_feedback_lbl.setVisible(True)

        run_async(_work, on_result=_done, on_error=_err)

    # ── Email confirmation ─────────────────────────────────────────────────────

    def _show_email_confirmation(self, email: str):
        """Switch to page 2 after successful sign-up that requires email confirmation."""
        self._pending_confirm_email = email
        desc = (
            f"We've sent a confirmation link to {email}.\n"
            "Click it to activate your account, then sign in."
            if email else
            "We've sent a confirmation link to your email.\n"
            "Click it to activate your account, then sign in."
        )
        self._confirm_desc_lbl.setText(desc)
        self._resend_feedback_lbl.setVisible(False)
        self._resend_btn.setEnabled(True)
        self._resend_btn.setText("Resend confirmation email")
        self._page_stack.setCurrentIndex(2)

    def _on_resend_confirmation(self):
        email = getattr(self, "_pending_confirm_email", "") or self._email_input.text().strip()
        if not email:
            return

        self._resend_btn.setEnabled(False)
        self._resend_btn.setText("Sending…")
        self._resend_feedback_lbl.setVisible(False)

        from utils.workers import run_async
        from auth.supabase_client import get_client

        def _work():
            client = get_client()
            if client is None:
                raise RuntimeError("no_connection")
            client.auth.resend({"type": "signup", "email": email})

        def _done(_):
            self._resend_btn.setEnabled(True)
            self._resend_btn.setText("Resend confirmation email")
            self._resend_feedback_lbl.setText("Sent! Check your inbox.")
            self._resend_feedback_lbl.setStyleSheet("color: #34d399; font-size: 12px; background: transparent;")
            self._resend_feedback_lbl.setVisible(True)

        def _err(_err_str: str):
            self._resend_btn.setEnabled(True)
            self._resend_btn.setText("Resend confirmation email")
            self._resend_feedback_lbl.setText("Could not resend. Please try again.")
            self._resend_feedback_lbl.setStyleSheet("color: #dc3545; font-size: 12px; background: transparent;")
            self._resend_feedback_lbl.setVisible(True)

        run_async(_work, on_result=_done, on_error=_err)

    def _go_back_to_signin(self):
        self._set_mode(False)
        self._page_stack.setCurrentIndex(0)

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
        if self._is_signup_mode:
            confirm = self._pw_confirm_input.text()
            if not confirm:
                self._show_error("Please confirm your password.")
                return
            if pw != confirm:
                self._show_error("Passwords don't match — please check and try again.")
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
                # Sign-up succeeded but email confirmation is required
                self._show_email_confirmation(email)
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
                    "Too many sign-in attempts. Please wait 30 seconds and try again."
                )
            elif "user not found" in msg or ("no user" in msg and "found" in msg):
                self._show_error(
                    "No account found with that email — switching you to Create Account."
                )
                self._set_mode(True)
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
                    "An account with this email already exists — switching you to Sign In."
                )
                self._set_mode(False)
            elif "password" in msg and ("weak" in msg or "short" in msg or "characters" in msg):
                self._show_error("Password is too weak. Use at least 6 characters.")
            elif "network" in msg or "connect" in msg or "timeout" in msg or "unreachable" in msg:
                self._show_error(
                    "Could not connect to DishBoard servers. Check your internet connection."
                )
            elif "invalid_email" in msg or ("email" in msg and "invalid" in msg):
                self._show_error("Please enter a valid email address.")
            else:
                self._show_error(f"Sign-in error: {err.strip().splitlines()[-1][:140]}")

        run_async(_work, on_result=_done, on_error=_err)

    # ── Google OAuth ──────────────────────────────────────────────────────────

    def _on_google(self):
        """Start Google OAuth: open browser → wait for callback → log in."""
        from utils.workers import run_async
        from auth.supabase_client import get_client
        from auth.oauth_server import start_oauth_callback_server, CALLBACK_URL
        import webbrowser
        import secrets

        self._google_btn.setEnabled(False)
        self._google_btn.setText("  Opening browser…")
        self._clear_error()
        oauth_state = secrets.token_urlsafe(24)

        def _work():
            client = get_client()
            if client is None:
                raise RuntimeError("no_connection")
            response = client.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": f"{CALLBACK_URL}?state={oauth_state}",
                    "skip_browser_redirect": True,
                },
            })
            return response.url

        def _opened(url: str):
            if not url:
                self._show_error("Could not get Google sign-in URL. Try again.")
                self._google_btn.setEnabled(True)
                self._google_btn.setText("  Sign in with Google")
                return
            # Start local callback server and open browser
            self._oauth_done_event = start_oauth_callback_server(expected_state=oauth_state)
            webbrowser.open(url)
            self._google_btn.setText("  Waiting for Google…")
            self._oauth_poll_timer.start()

        def _err(err: str):
            self._google_btn.setEnabled(True)
            self._google_btn.setText("  Sign in with Google")
            msg = err.lower()
            if "no_connection" in msg:
                self._show_error("No internet connection. Check your network and try again.")
            else:
                self._show_error("Could not start Google sign-in. Please try again.")

        run_async(_work, on_result=_opened, on_error=_err)

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

        self._google_btn.setEnabled(True)
        self._google_btn.setText("  Sign in with Google")

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
        self._pw_confirm_input.setEnabled(not loading)
        self._signin_tab.setEnabled(not loading)
        self._signup_tab.setEnabled(not loading)
        if loading:
            self._signin_btn.setText("Please wait…")
        else:
            self._signin_btn.setText("Create Account" if self._is_signup_mode else "Sign In")

    def reset(self):
        """Reset the login view to a clean sign-in state — called after sign-out."""
        self._email_input.clear()
        self._pw_input.clear()
        self._pw_confirm_input.clear()
        self._clear_error()
        self._page_stack.setCurrentIndex(0)
        # Force back to sign-in mode without the guard check
        self._is_signup_mode = True   # trick _set_mode into running
        self._set_mode(False)
