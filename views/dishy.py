import re
import uuid
import random
import qtawesome as qta
from utils.theme import manager as theme_manager
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QScrollArea, QSizePolicy, QDialog, QFrame,
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal

from api.claude_ai import ClaudeAI
from api.dishy_tool_specs import TOOLS
from api.dishy_tools import TOOL_STATUS_MESSAGES, summarise_tool_calls
from utils.service_hub import registry as service_registry
from utils.workers import run_async

_claude = ClaudeAI()

_MAX_HISTORY = 20
_TRIM_TO     = 14

_FONT = (
    'font-family: "Segoe UI","SF Pro Text",-apple-system,'
    '".AppleSystemUIFont","Helvetica Neue",Arial,sans-serif;'
)

DISHY_GREEN = "#ff6b35"


def _clean(text: str) -> str:
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    text = re.sub(r'`([^`\n]+)`', r'\1', text)
    text = re.sub(r'^[\-\*]\s+', '- ', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


DISHY_INTRO = (
    "Hi, I'm Dishy — your cooking assistant inside DishBoard. "
    "Ask me anything: recipe ideas, what to cook with what's in your fridge, "
    "meal plans, substitutions, nutrition. What can I help with today?"
)

QUICK_PROMPTS_POOL = [
    ("What can I make with what I have?",           "fa5s.box-open"),
    ("What can I make with chicken and rice?",      "fa5s.drumstick-bite"),
    ("Give me a 5-day meal plan",                   "fa5s.calendar-alt"),
    ("What's a good substitute for butter?",        "fa5s.exchange-alt"),
    ("Quick high-protein dinner ideas",             "fa5s.fire"),
    ("Easy 30-minute weeknight dinners",            "fa5s.clock"),
    ("Healthy lunch ideas for meal prep",           "fa5s.apple-alt"),
    ("What can I make with pasta and veggies?",     "fa5s.seedling"),
    ("How do I make a creamy pasta sauce?",         "fa5s.mortar-pestle"),
    ("Low-carb dinner options",                     "fa5s.leaf"),
    ("Breakfast ideas that aren't boring",          "fa5s.coffee"),
    ("Best spices for a simple chicken dish",       "fa5s.pepper-hot"),
    ("What pairs well with salmon?",                "fa5s.fish"),
    ("Cheap meals to batch cook for the week",      "fa5s.dollar-sign"),
    ("Give me a simple curry recipe",               "fa5s.utensils"),
    ("Vegan protein sources for dinner",            "fa5s.seedling"),
    ("How do I make my own bread?",                 "fa5s.bread-slice"),
    ("What dessert can I make with eggs and milk?", "fa5s.ice-cream"),
    ("One-pot meals for busy weeknights",           "fa5s.globe"),
]


# ── Avatar ───────────────────────────────────────────────────────────────────

class _DishyAvatar(QWidget):
    """Simple non-painted avatar."""

    def __init__(self, size: int = 36, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        icon_lbl = QLabel()
        icon_px = max(int(size * 0.44), 10)
        icon_lbl.setPixmap(qta.icon("fa5s.robot", color="#ffffff").pixmap(QSize(icon_px, icon_px)))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon_lbl)

        self._icon_lbl = icon_lbl
        self.apply_theme(theme_manager.mode)

    def apply_theme(self, _mode: str):
        r = int(self._size / 2)
        self.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ff8558,stop:1 #e55a2a);"
            f"border: 1px solid {theme_manager.c('rgba(255,107,53,0.42)', 'rgba(255,107,53,0.34)')};"
            f"border-radius: {r}px;"
        )


class ActionSummaryBubble(QWidget):
    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        vl = QVBoxLayout(self)
        vl.setContentsMargins(56, 4, 0, 6)
        vl.setSpacing(5)
        for text in labels:
            hl = QHBoxLayout()
            hl.setContentsMargins(0, 0, 0, 0)
            pill = QLabel(f"✓  {text}")
            pill.setStyleSheet(
                "QLabel {"
                " color: #ff6b35;"
                f" background: {theme_manager.c('rgba(255,107,53,0.12)', 'rgba(255,107,53,0.08)')};"
                " border: 1px solid rgba(255,107,53,0.28);"
                " border-radius: 11px;"
                f" padding: 6px 12px; font-size: 12px; font-weight: 700; {_FONT}"
                "}"
            )
            hl.addWidget(pill)
            hl.addStretch()
            vl.addLayout(hl)


class _BubbleWidget(QWidget):
    """Style-sheet based bubble to avoid custom painting."""

    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self._is_user = is_user
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.setMaximumWidth(760)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 11, 16, 11)
        lay.setSpacing(0)

        self._lbl = QLabel(text)
        self._lbl.setWordWrap(True)
        self._lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._lbl)
        self.apply_theme(theme_manager.mode)

    def apply_theme(self, mode: str):
        is_dark = mode == "dark"
        if self._is_user:
            bg = "rgba(255,107,53,0.16)" if is_dark else "#fff0e8"
            border = "rgba(255,107,53,0.38)" if is_dark else "#f0b399"
            text = "#fff2ec" if is_dark else "#5b2718"
        else:
            bg = "#14181d" if is_dark else "#fffaf4"
            border = "#282e35" if is_dark else "#e1d5c8"
            text = "#ece7e0" if is_dark else "#201a15"
        self.setStyleSheet(
            f"background: {bg}; border: 1px solid {border}; border-radius: 16px;"
        )
        self._lbl.setStyleSheet(
            f"background: transparent; border: none; color: {text}; font-size: 15px; {_FONT}"
        )


class MessageBubble(QWidget):
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self._bubble = _BubbleWidget(text, is_user)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(12)
        if is_user:
            layout.addStretch(1)
            layout.addWidget(self._bubble, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        else:
            self._avatar = _DishyAvatar(38)
            layout.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignTop)
            layout.addWidget(self._bubble, 0, Qt.AlignmentFlag.AlignTop)
            layout.addStretch(1)

    def apply_theme(self, mode: str):
        self._bubble.apply_theme(mode)
        if hasattr(self, "_avatar"):
            self._avatar.apply_theme(mode)


class _TypingIndicator(QWidget):
    """Restored spinner/cube style typing indicator."""

    _SPIN = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._step = 0
        self._status = "Thinking..."
        self._pending: list[str] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(12)
        self._avatar = _DishyAvatar(38)
        layout.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignTop)

        self._lbl = QLabel(f"{self._SPIN[0]}  {self._status}")
        self._lbl.setStyleSheet(
            "QLabel {"
            f"color: {DISHY_GREEN};"
            f"background: {theme_manager.c('#14181d', '#fffaf4')};"
            f"border: 1px solid {theme_manager.c('#282e35', '#e1d5c8')};"
            "border-radius: 14px;"
            f"padding: 8px 12px; font-size: 12px; font-weight: 700; {_FONT}"
            "}"
        )
        layout.addWidget(self._lbl)
        layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(90)

    def _tick(self):
        if self._pending:
            self._status = self._pending.pop()
            self._pending.clear()
        self._step = (self._step + 1) % len(self._SPIN)
        self._lbl.setText(f"{self._SPIN[self._step]}  {self._status}")

    def update_status(self, text: str):
        self._pending.append(text)

    def stop(self):
        self._timer.stop()


# ── Chat History Dialog ───────────────────────────────────────────────────────

class ChatHistoryDialog(QDialog):
    """Modal dialog showing all past Dishy chat sessions."""
    session_selected = Signal(str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self.setWindowTitle("Dishy Chat History")
        self.setMinimumSize(540, 500)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self._drag_pos = None
        self._build_ui()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        self._drag_pos = None

    def _build_ui(self):
        is_dark = theme_manager.mode == "dark"
        bg      = "#0e0e0e" if is_dark else "#f5f5f5"
        text    = "#f0f0f0" if is_dark else "#1a1a1a"
        muted   = "#888888" if is_dark else "#666666"
        border  = "#252525" if is_dark else "#e0e0e0"
        card    = "#161616" if is_dark else "#ffffff"

        self.setStyleSheet(f"""
            QDialog {{ background: {bg}; }}
            QLabel  {{ color: {text}; background: transparent; }}
            QScrollArea {{ border: none; background: transparent; }}
            QPushButton#open-btn {{
                background: rgba(52,211,153,0.12); color: #34d399;
                border: 1px solid rgba(52,211,153,0.3); border-radius: 8px;
                font-size: 12px; font-weight: 600; padding: 5px 16px;
            }}
            QPushButton#open-btn:hover {{ background: rgba(52,211,153,0.22); }}
            QPushButton#del-btn {{
                background: rgba(255,70,70,0.08); color: #ff6060;
                border: 1px solid rgba(255,70,70,0.22); border-radius: 8px;
                font-size: 12px; padding: 5px 12px;
            }}
            QPushButton#del-btn:hover {{ background: rgba(255,70,70,0.18); }}
            QPushButton#close-btn {{
                background: transparent; color: {muted};
                border: 1px solid {border}; border-radius: 8px;
                font-size: 13px; padding: 8px 22px;
            }}
            QPushButton#close-btn:hover {{ background: rgba(128,128,128,0.1); }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)

        # Header
        hdr = QHBoxLayout()
        hdr.setSpacing(12)
        av = _DishyAvatar(32)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        t = QLabel("Chat History")
        t.setStyleSheet(f"font-size: 18px; font-weight: 700; {_FONT}")
        sub = QLabel("Stored locally only — not included in backups")
        sub.setStyleSheet(f"font-size: 12px; color: {muted}; {_FONT}")
        title_col.addWidget(t)
        title_col.addWidget(sub)
        hdr.addWidget(av, 0, Qt.AlignmentFlag.AlignVCenter)
        hdr.addLayout(title_col)
        hdr.addStretch()

        close_x = QPushButton()
        close_x.setIcon(qta.icon("fa5s.times", color=muted))
        close_x.setIconSize(QSize(13, 13))
        close_x.setFixedSize(30, 30)
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 15px; }}"
            f"QPushButton:hover {{ background: {('rgba(255,255,255,0.08)' if is_dark else 'rgba(0,0,0,0.06)')}; }}"
        )
        close_x.clicked.connect(self.reject)
        hdr.addWidget(close_x, 0, Qt.AlignmentFlag.AlignVCenter)

        outer.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {border};")
        outer.addWidget(sep)

        # Session list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 0, 4, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()
        scroll.setWidget(self._container)
        outer.addWidget(scroll, 1)

        self._card_bg    = card
        self._border_col = border
        self._text_col   = text
        self._muted_col  = muted
        self._populate()

        close_btn = QPushButton("Close")
        close_btn.setObjectName("close-btn")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        outer.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)

    def _populate(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._db:
            self._list_layout.insertWidget(0, QLabel("No chat history available."))
            return

        sessions = self._db.get_dishy_sessions_summary()
        if not sessions:
            lbl = QLabel("No past conversations yet — start chatting with Dishy!")
            lbl.setStyleSheet(f"color: {self._muted_col}; font-size: 14px; {_FONT}")
            self._list_layout.insertWidget(0, lbl)
            return

        for i, s in enumerate(sessions):
            card = QWidget()
            card.setStyleSheet(
                f"background: {self._card_bg}; border-radius: 12px;"
                f" border: 1px solid {self._border_col};"
            )
            cl = QHBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 14)
            cl.setSpacing(12)

            info = QVBoxLayout()
            info.setSpacing(4)
            preview = s["first_message"][:72] + ("…" if len(s["first_message"]) > 72 else "")
            p_lbl = QLabel(preview)
            p_lbl.setStyleSheet(
                f"font-size: 14px; font-weight: 600; color: {self._text_col}; {_FONT}"
            )
            d_lbl = QLabel(f"{s['date']}  ·  {s['message_count']} messages")
            d_lbl.setStyleSheet(f"font-size: 12px; color: {self._muted_col}; {_FONT}")
            info.addWidget(p_lbl)
            info.addWidget(d_lbl)

            sid = s["session_id"]
            open_btn = QPushButton("Open")
            open_btn.setObjectName("open-btn")
            open_btn.setFixedHeight(32)
            open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            open_btn.clicked.connect(lambda _, s=sid: self._open_session(s))

            del_btn = QPushButton("Delete")
            del_btn.setObjectName("del-btn")
            del_btn.setFixedHeight(32)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.clicked.connect(lambda _, s=sid: self._delete_session(s))

            cl.addLayout(info, 1)
            cl.addWidget(open_btn)
            cl.addWidget(del_btn)
            self._list_layout.insertWidget(i, card)

    def _open_session(self, session_id: str):
        self.session_selected.emit(session_id)
        self.accept()

    def _delete_session(self, session_id: str):
        if self._db:
            self._db.delete_dishy_session(session_id)
        self._populate()


# ── Auto-growing text input ───────────────────────────────────────────────────

class _AutoGrowTextEdit(QPlainTextEdit):
    """QPlainTextEdit that wraps text. Enter sends; Shift+Enter inserts newline."""

    send_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.send_requested.emit()
        else:
            super().keyPressEvent(event)


# ── Main DishyView ────────────────────────────────────────────────────────────

class DishyView(QWidget):
    session_expired = Signal(str)   # emits last-known user email

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.setObjectName("view-container")
        self._db          = db
        self._history:    list[dict] = []
        self._session_id: str = str(uuid.uuid4())
        self._typing_indicator: _TypingIndicator | None = None
        self._actions     = None
        self._refresh_cb  = None
        self._worker      = None
        self._first_show  = True
        self._resume_bar  = None
        self._sync_fn     = None
        self._visibility_work = None
        self._build_ui()

    def set_sync_fn(self, fn):
        self._sync_fn = fn

    @staticmethod
    def _visibility_service():
        return service_registry.get("visibility")

    def setup_actions(self, actions, refresh_callback):
        self._actions    = actions
        self._refresh_cb = refresh_callback

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setStyleSheet(f"background: {theme_manager.c('#101417', '#f6f2ed')};")

        outer.addWidget(self._build_header())

        # Resume banner — hidden by default, shown by _check_resume_session()
        self._resume_bar = self._build_resume_bar()
        self._resume_bar.setVisible(False)
        outer.addWidget(self._resume_bar)

        # ── Chat scroll area ──────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._chat_container = QWidget()
        self._chat_container.setObjectName("dishy-chat-canvas")
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(28, 20, 28, 22)
        self._chat_layout.setSpacing(4)
        self._chat_layout.addStretch()

        self._scroll.setWidget(self._chat_container)
        outer.addWidget(self._scroll, 1)
        self._apply_scroll_style()

        # Greeting bubble
        self._add_bubble(DISHY_INTRO, is_user=False)

        # ── Quick-prompt chips (horizontal scroll) ────────────────────────────
        self._quick_wrapper = QWidget()
        self._quick_wrapper.setObjectName("dishy-quick-wrapper")
        qw_layout = QVBoxLayout(self._quick_wrapper)
        qw_layout.setContentsMargins(22, 10, 22, 12)
        qw_layout.setSpacing(8)

        # "Quick starts" row with refresh chips button
        hint_row = QHBoxLayout()
        hint_row.setContentsMargins(0, 0, 0, 0)
        hint_row.setSpacing(8)
        hint_lbl = QLabel("Quick starts")
        self._hint_lbl = hint_lbl
        hint_row.addWidget(hint_lbl)
        hint_row.addStretch()
        self._refresh_chips_btn = QPushButton("Refresh")
        self._refresh_chips_btn.setIcon(qta.icon("fa5s.sync-alt", color=DISHY_GREEN))
        self._refresh_chips_btn.setIconSize(QSize(11, 11))
        self._refresh_chips_btn.setFixedHeight(30)
        self._refresh_chips_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_chips_btn.setToolTip("Refresh suggestions")
        self._refresh_chips_btn.clicked.connect(self._rebuild_quick_prompts)
        self._refresh_chips_btn.hide()
        qw_layout.addLayout(hint_row)

        self._quick_scroll = QScrollArea()
        self._quick_scroll.setFixedHeight(48)
        self._quick_scroll.setWidgetResizable(True)
        self._quick_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._quick_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._quick_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._chips_widget = QWidget()
        self._chips_widget.setStyleSheet("background: transparent;")
        self._chips_layout = QHBoxLayout(self._chips_widget)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(10)
        self._chips_layout.addStretch()

        self._quick_scroll.setWidget(self._chips_widget)
        qw_layout.addWidget(self._quick_scroll)
        self._quick_widget = self._quick_wrapper  # alias for external code
        outer.addWidget(self._quick_wrapper)
        self._rebuild_quick_prompts()

        # ── Input bar ─────────────────────────────────────────────────────────
        outer.addWidget(self._build_input_bar())
        self.apply_theme(theme_manager.mode)

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setObjectName("dishy-header")
        hdr.setFixedHeight(74)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(24, 0, 24, 0)
        hl.setSpacing(14)

        avatar = _DishyAvatar(44)
        hl.addWidget(avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        title_widget = QWidget()
        title_widget.setStyleSheet("background: transparent;")
        title_col = QVBoxLayout(title_widget)
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(3)
        title_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title = QLabel("Dishy")
        self._hdr_title = title
        sub = QLabel("A dedicated workspace for planning, recipes, and food questions")
        self._hdr_sub = sub
        title_col.addWidget(title)
        title_col.addWidget(sub)
        hl.addWidget(title_widget, 0, Qt.AlignmentFlag.AlignVCenter)
        hl.addStretch()

        hist_btn = QPushButton("  History")
        hist_btn.setIcon(qta.icon("fa5s.history", color=DISHY_GREEN))
        hist_btn.setIconSize(QSize(13, 13))
        hist_btn.setFixedHeight(38)
        hist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hist_btn.clicked.connect(self._open_history)
        hl.addWidget(hist_btn)
        self._hist_btn = hist_btn

        new_btn = QPushButton("  New chat")
        new_btn.setIcon(qta.icon("fa5s.plus", color=theme_manager.c("#9fb0c9", "#6d8098")))
        new_btn.setIconSize(QSize(12, 12))
        new_btn.setFixedHeight(38)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self._clear_chat)
        hl.addWidget(new_btn)
        self._new_btn = new_btn

        self._hdr = hdr
        return hdr

    def _build_resume_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("dishy-resume-bar")
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(28, 10, 20, 10)
        hl.setSpacing(12)

        av = _DishyAvatar(24)
        hl.addWidget(av, 0, Qt.AlignmentFlag.AlignVCenter)

        lbl = QLabel("Continue where you left off?")
        self._resume_lbl = lbl
        hl.addWidget(lbl)
        hl.addStretch()

        resume_btn = QPushButton("Resume")
        resume_btn.setObjectName("resume-btn")
        resume_btn.setFixedHeight(30)
        resume_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        resume_btn.clicked.connect(self._do_resume)
        hl.addWidget(resume_btn)
        self._resume_btn = resume_btn

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.setFixedHeight(30)
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.clicked.connect(lambda: bar.setVisible(False))
        hl.addWidget(dismiss_btn)
        self._dismiss_resume_btn = dismiss_btn

        bar.setFixedHeight(50)
        # Store the session_id this bar points to — set when populated
        bar._session_id = None
        bar._session_rows = None
        return bar

    def _build_input_bar(self) -> QWidget:
        container = QWidget()
        container.setObjectName("dishy-input-wrap")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(22, 12, 22, 14)
        cl.setSpacing(8)

        # The pill input row
        pill = QWidget()
        pill.setObjectName("input-pill")
        pill_layout = QHBoxLayout(pill)
        pill_layout.setContentsMargins(18, 10, 10, 10)
        pill_layout.setSpacing(10)

        self._input = _AutoGrowTextEdit()
        self._input.setPlaceholderText("Ask Dishy anything about food, recipes, or cooking…")
        self._input.send_requested.connect(self._send)
        pill_layout.addWidget(self._input, 1)

        self._send_btn = QPushButton()
        self._send_btn.setObjectName("send-btn")
        self._send_btn.setFixedSize(44, 44)
        self._send_btn.setIcon(qta.icon("fa5s.arrow-up", color="white"))
        self._send_btn.setIconSize(QSize(16, 16))
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.clicked.connect(self._send)
        pill_layout.addWidget(self._send_btn)

        # Auto-grow: resize both input and pill on every content change
        _INPUT_MIN = 38
        _INPUT_MAX = 200

        def _resize_input():
            doc = self._input.document()
            doc.setTextWidth(self._input.viewport().width() or 300)
            h = max(_INPUT_MIN, min(int(doc.size().height()) + 10, _INPUT_MAX))
            self._input.setFixedHeight(h)
            pill.setFixedHeight(h + 24)

        self._input.document().contentsChanged.connect(_resize_input)
        _resize_input()  # set initial size

        cl.addWidget(pill)

        tip = QLabel("Enter to send · Shift+Enter for a new line")
        tip.setObjectName("dishy-input-tip")
        self._input_tip = tip
        cl.addWidget(tip)
        self._input_container = container
        self._input_pill = pill
        return container

    # ── Quick prompts ─────────────────────────────────────────────────────────

    def _rebuild_quick_prompts(self):
        # Clear existing chips (but keep the trailing stretch)
        while self._chips_layout.count() > 1:
            item = self._chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sampled = random.sample(QUICK_PROMPTS_POOL, min(4, len(QUICK_PROMPTS_POOL)))
        for text, icon_name in sampled:
            chip = QPushButton(f" {text} ")
            chip.setIcon(qta.icon(icon_name, color=DISHY_GREEN))
            chip.setIconSize(QSize(14, 14))
            chip.setFixedHeight(36)
            chip.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                "QPushButton {"
                f" background: {theme_manager.c('#14181d', '#f2ebe2')};"
                f" border: 1px solid {theme_manager.c('#282e35', '#ddd1c4')};"
                " border-radius: 999px;"
                f" color: {theme_manager.c('#a39c93', '#7c7368')};"
                f" font-size: 12px; font-weight: 600; {_FONT} padding: 0 14px;"
                "}"
                "QPushButton:hover {"
                f" background: {theme_manager.c('#181d22', '#ede2d6')};"
                " border-color: rgba(255,107,53,0.20);"
                f" color: {theme_manager.c('#f1ece5', '#201913')};"
                "}"
            )
            chip.clicked.connect(lambda _, t=text: self._send_text(t))
            self._chips_layout.insertWidget(self._chips_layout.count() - 1, chip)

    # ── Show / resume ─────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        # Rebuild chips on every open
        if self._quick_wrapper.isVisible():
            self._rebuild_quick_prompts()
        # Check for a resumable session on very first open
        if self._first_show:
            self._first_show = False
            self._check_resume_session()

    def _check_resume_session(self):
        if not self._db:
            return
        result = self._db.get_latest_dishy_session()
        if result:
            sid, rows = result
            # Only offer resume if there's actual user content
            user_rows = [r for r in rows if r["role"] == "user"]
            if user_rows:
                self._resume_bar._session_id   = sid
                self._resume_bar._session_rows = rows
                self._resume_bar.setVisible(True)

    def _do_resume(self):
        sid  = self._resume_bar._session_id
        rows = self._resume_bar._session_rows
        self._resume_bar.setVisible(False)
        if sid and rows:
            self._load_session_rows(sid, rows)

    # ── History ───────────────────────────────────────────────────────────────

    def _open_history(self):
        dlg = ChatHistoryDialog(self._db, self)
        dlg.session_selected.connect(self._load_session)
        dlg.exec()

    def _load_session(self, session_id: str):
        """Load a past session from the history dialog."""
        if not self._db:
            return
        rows = self._db.get_dishy_session(session_id)
        if not rows:
            return
        self._clear_chat_display()
        self._load_session_rows(session_id, rows)

    def _load_session_rows(self, session_id: str, rows):
        """Populate the chat display with a given session's rows."""
        self._clear_chat_display()
        self._session_id = session_id
        self._history.clear()
        self._quick_wrapper.setVisible(False)
        self._resume_bar.setVisible(False)

        for row in rows:
            role    = row["role"]
            content = row["content"]
            tools   = [t for t in (row["tool_names"] or "").split(",") if t]
            if role == "user":
                self._add_bubble(content, is_user=True)
                self._history.append({"role": "user", "content": content})
            else:
                if tools:
                    labels = summarise_tool_calls(tools)
                    if labels:
                        summary = ActionSummaryBubble(labels)
                        self._chat_layout.insertWidget(self._chat_layout.count() - 1, summary)
                self._add_bubble(content, is_user=False)
                self._history.append({"role": "assistant", "content": content})

        self._queue_scroll_to_bottom(80)

    # ── Chat helpers ──────────────────────────────────────────────────────────

    def _add_bubble(self, text: str, is_user: bool):
        bubble = MessageBubble(text, is_user)
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
        self._chat_container.updateGeometry()
        self._chat_container.update()
        self._scroll.viewport().update()
        self._queue_scroll_to_bottom(50)

    def _queue_scroll_to_bottom(self, delay_ms: int = 0) -> None:
        def _scroll():
            try:
                bar = self._scroll.verticalScrollBar()
                bar.setValue(bar.maximum())
            except RuntimeError:
                pass

        QTimer.singleShot(delay_ms, _scroll)

    def _send(self):
        self._send_text(self._input.toPlainText().strip())

    def _send_text(self, text: str):
        if not text:
            return
        self._resume_bar.setVisible(False)
        self._quick_wrapper.setVisible(False)

        self._add_bubble(text, is_user=True)
        self._input.clear()

        # Disable send during generation
        self._send_btn.setEnabled(False)
        self._send_btn.setIcon(qta.icon("fa5s.circle-notch", color="white"))

        # Persist user message
        if self._db:
            self._db.save_dishy_message(self._session_id, "user", text)
            if self._sync_fn:
                self._sync_fn()

        # Typing indicator
        self._typing_indicator = _TypingIndicator()
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, self._typing_indicator)
        self._queue_scroll_to_bottom(40)

        # Trim history
        raw_history = list(self._history)
        if len(raw_history) > _MAX_HISTORY:
            raw_history = raw_history[-_TRIM_TO:]
            while raw_history and raw_history[0]["role"] != "user":
                raw_history = raw_history[1:]
        history_snapshot = raw_history
        self._history.append({"role": "user", "content": text})

        actions = self._actions
        pending_tool_names: list[str] = []

        app_ctx  = actions.get_context_string() if actions is not None else ""
        memory_ctx = actions.get_memory_context(text) if actions is not None else ""

        ctx_parts: list[str] = []
        if app_ctx:
            ctx_parts.append(app_ctx)
        if memory_ctx:
            ctx_parts.append(memory_ctx)
        full_msg = "\n\n".join(ctx_parts + [text]) if ctx_parts else text

        if actions is not None:
            actions.clear_pending()
            vis = self._visibility_service()
            if vis is not None:
                self._visibility_work = vis.start_work(
                    "dishy.view.chat",
                    "ai",
                    "dishy",
                    "Dishy is replying",
                    "Working through your latest request.",
                    timeout_seconds=180,
                    attention_reason="ai_in_progress",
                )

            def _tool_handler(name: str, inp: dict) -> str:
                # Push status update to the typing indicator (thread-safe via queue)
                status = TOOL_STATUS_MESSAGES.get(name, "Working...")
                if self._typing_indicator is not None:
                    self._typing_indicator.update_status(status)
                if self._visibility_work is not None:
                    self._visibility_work.update(status)
                result = actions.execute(name, inp)
                pending_tool_names.append(name)
                return result

            def _chat_fn():
                return _claude.chat_with_tools(full_msg, TOOLS, _tool_handler, history_snapshot)

            self._worker = run_async(
                _chat_fn,
                on_result=lambda reply: self._on_reply(reply, pending_tool_names, actions),
                on_error=self._on_error,
            )
        else:
            vis = self._visibility_service()
            if vis is not None:
                self._visibility_work = vis.start_work(
                    "dishy.view.chat",
                    "ai",
                    "dishy",
                    "Dishy is replying",
                    "Working through your latest request.",
                    timeout_seconds=180,
                    attention_reason="ai_in_progress",
                )
            self._worker = run_async(
                _claude.chat, full_msg,
                history=history_snapshot,
                on_result=lambda reply: self._on_reply(reply, [], None),
                on_error=self._on_error,
            )

    def _remove_typing_indicator(self):
        if self._typing_indicator is not None:
            try:
                self._typing_indicator.stop()
                self._typing_indicator.deleteLater()
            except Exception:
                pass
            self._typing_indicator = None

    def _on_reply(self, reply: str, tool_names: list, actions):
        try:
            if self._visibility_work is not None:
                self._visibility_work.finish()
                self._visibility_work = None
            self._remove_typing_indicator()
            # Show one consolidated pill per tool category
            if tool_names:
                labels = summarise_tool_calls(tool_names)
                if labels:
                    summary = ActionSummaryBubble(labels)
                    self._chat_layout.insertWidget(self._chat_layout.count() - 1, summary)
            cleaned = _clean(reply)
            if cleaned:
                self._history.append({"role": "assistant", "content": cleaned})
                self._add_bubble(cleaned, is_user=False)
                if self._db:
                    self._db.save_dishy_message(
                        self._session_id, "assistant", cleaned,
                        ",".join(tool_names),
                    )
                    if self._sync_fn:
                        self._sync_fn()
            self._send_btn.setEnabled(True)
            self._send_btn.setIcon(qta.icon("fa5s.arrow-up", color="white"))
            self._queue_scroll_to_bottom(60)
        except Exception:
            pass

        if actions is not None and actions.pending_refreshes and self._refresh_cb:
            refreshes = list(actions.pending_refreshes)
            QTimer.singleShot(200, lambda: self._safe_refresh(refreshes))

    def _safe_refresh(self, view_names: list):
        try:
            self._refresh_cb(view_names)
        except Exception:
            pass

    def _on_error(self, err: str):
        try:
            if self._visibility_work is not None:
                self._visibility_work.fail(err)
                self._visibility_work = None
            self._remove_typing_indicator()
            err_lower = err.lower()
            _is_auth = False
            if "credit balance" in err_lower or "too low" in err_lower:
                msg = "Anthropic credits are out. Top up at console.anthropic.com/settings/billing."
            elif "overloaded" in err_lower or "529" in err_lower:
                msg = "Dishy's AI is a little busy right now — please try again in a moment."
            elif "dishy_rate_limited" in err_lower or "daily ai request limit" in err_lower:
                msg = "Daily AI limit reached (50/day). Try again tomorrow."
            elif "ai usage metering unavailable" in err_lower:
                msg = "Dishy is temporarily unavailable due to AI usage metering. Try again in a moment."
            elif "dishy_not_signed_in" in err_lower:
                msg = "Dishy couldn't connect — your session may have expired. Signing you back in…"
                _is_auth = True
            elif "authentication" in err_lower or "api_key" in err_lower or "401" in err_lower:
                msg = "Dishy couldn't authenticate — your session may have expired. Signing you back in…"
                _is_auth = True
            else:
                short = err.strip().splitlines()[-1] if err.strip() else err
                msg = f"Error: {short[:200]}"
            self._add_bubble(msg, is_user=False)
            self._send_btn.setEnabled(True)
            self._send_btn.setIcon(qta.icon("fa5s.arrow-up", color="white"))
            if _is_auth:
                try:
                    from auth.session_manager import load_session
                    stored = load_session() or {}
                    email = stored.get("user", {}).get("email", "")
                except Exception:
                    email = ""
                self.session_expired.emit(email)
        except Exception:
            pass

    def _clear_chat_display(self):
        """Remove all bubble widgets from the chat layout (but keep the trailing stretch)."""
        self._remove_typing_indicator()
        while self._chat_layout.count() > 1:
            item = self._chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_chat(self):
        self._clear_chat_display()
        self._history.clear()
        self._session_id = str(uuid.uuid4())
        self._resume_bar.setVisible(False)
        self._rebuild_quick_prompts()
        self._quick_wrapper.setVisible(True)
        self._add_bubble(DISHY_INTRO, is_user=False)

    # ── External entry points ─────────────────────────────────────────────────

    def reset_session(self):
        """Clear in-memory history and start a fresh session (called on account switch)."""
        self._clear_chat()

    def trigger_prompt(self, text: str):
        """Navigate here and auto-send a prompt (called from Dashboard chips)."""
        self._send_text(text)

    def activate_chat(self, prompt: str = "") -> None:
        """Palette-safe entrypoint for opening Dishy ready to type."""
        if prompt:
            self._quick_wrapper.setVisible(False)
            self._input.setPlainText(prompt)
        QTimer.singleShot(0, lambda: self._input.setFocus(Qt.FocusReason.ShortcutFocusReason))

    def open_session(self, session_id: str) -> bool:
        """Open a saved Dishy session by id."""
        if not self._db:
            return False
        rows = self._db.get_dishy_session(session_id)
        if not rows:
            return False
        self._load_session_rows(session_id, rows)
        return True

    def _apply_scroll_style(self):
        self._scroll.verticalScrollBar().setStyleSheet(
            "QScrollBar:vertical { width: 6px; background: transparent; margin: 4px 0; }"
            f"QScrollBar::handle:vertical {{ background: {theme_manager.c('#33445d', '#b9c7d9')};"
            " border-radius: 3px; min-height: 24px; }"
            f"QScrollBar::handle:vertical:hover {{ background: {theme_manager.c('#48607f', '#9fb0c6')}; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

    def _style_header(self):
        self._hdr.setStyleSheet(
            "QWidget#dishy-header {"
            f" background: {theme_manager.c('#101417', '#f6f2ed')};"
            f" border-bottom: 1px solid {theme_manager.c('#20262d', '#ddd2c6')};"
            "}"
        )
        self._hdr_title.setStyleSheet(
            f"color: {theme_manager.c('#f1ede7', '#17130f')};"
            f" font-size: 22px; font-weight: 760; letter-spacing: -0.2px; {_FONT}"
        )
        self._hdr_sub.setStyleSheet(
            f"color: {theme_manager.c('#8e978f', '#756d63')};"
            f" font-size: 12px; font-weight: 600; {_FONT}"
        )
        self._hist_btn.setStyleSheet(
            "QPushButton {"
            f" background: {theme_manager.c('#14181d', '#f2ebe2')};"
            f" color: {theme_manager.c('#8d867d', '#756d63')};"
            f" border: 1px solid {theme_manager.c('#282e35', '#ddd1c4')}; border-radius: 11px;"
            f" padding: 0 14px; font-size: 12px; font-weight: 700; {_FONT}"
            "}"
            "QPushButton:hover {"
            f" background: {theme_manager.c('#181d22', '#ede2d6')};"
            f" border-color: {theme_manager.c('#353b44', '#d0c2b4')};"
            "}"
        )
        self._new_btn.setIcon(qta.icon("fa5s.plus", color=theme_manager.c("#8e978f", "#756d63")))
        self._new_btn.setStyleSheet(
            "QPushButton {"
            f" background: {theme_manager.c('#14181d', '#f2ebe2')};"
            f" color: {theme_manager.c('#b0aaa2', '#6a6259')};"
            f" border: 1px solid {theme_manager.c('#282e35', '#ddd1c4')}; border-radius: 11px;"
            f" padding: 0 14px; font-size: 12px; font-weight: 700; {_FONT}"
            "}"
            "QPushButton:hover {"
            f" background: {theme_manager.c('#181d22', '#ede2d6')};"
            f" color: {theme_manager.c('#efe9e0', '#241d18')};"
            "}"
        )

    def _style_resume_bar(self):
        self._resume_bar.setStyleSheet(
            "QWidget#dishy-resume-bar {"
            f" background: {theme_manager.c('rgba(255,107,53,0.06)', 'rgba(255,107,53,0.04)')};"
            f" border-bottom: 1px solid {theme_manager.c('rgba(255,107,53,0.16)', 'rgba(255,107,53,0.14)')};"
            "}"
        )
        self._resume_lbl.setStyleSheet(
            "background: transparent; border: none;"
            f"color: {theme_manager.c('#d8d0c7', '#4f4337')};"
            f" font-size: 12px; font-weight: 600; {_FONT}"
        )
        self._resume_btn.setStyleSheet(
            "QPushButton {"
            " background: rgba(255,107,53,0.14); color: #ff6b35;"
            " border: 1px solid rgba(255,107,53,0.30); border-radius: 8px;"
            f" font-size: 12px; font-weight: 700; padding: 0 14px; {_FONT}"
            "}"
            "QPushButton:hover { background: rgba(255,107,53,0.22); }"
        )
        self._dismiss_resume_btn.setStyleSheet(
            "QPushButton {"
            " background: transparent; border: none;"
            f" color: {theme_manager.c('#8f877d', '#7b7066')};"
            f" border: none; font-size: 12px; font-weight: 600; {_FONT}"
            "}"
            "QPushButton:hover { color: #ff6b35; }"
        )

    def _style_input(self):
        self._input_container.setStyleSheet(
            "QWidget#dishy-input-wrap {"
            f" background: {theme_manager.c('#101417', '#f6f2ed')};"
            f" border-top: 1px solid {theme_manager.c('#20262d', '#ddd2c6')};"
            "}"
        )
        self._input_pill.setStyleSheet(
            "QWidget#input-pill {"
            f" background: {theme_manager.c('#151a1f', '#ffffff')};"
            f" border: 1.2px solid {theme_manager.c('#273038', '#ddd2c6')};"
            " border-radius: 24px;"
            "}"
        )
        self._input.setStyleSheet(
            "QPlainTextEdit {"
            " background: transparent; border: none;"
            f" color: {theme_manager.c('#efebe5', '#17130f')};"
            f" font-size: 15px; {_FONT}"
            " padding: 4px 0;"
            "}"
            "QPlainTextEdit::placeholder {"
            f" color: {theme_manager.c('#7f877f', '#90857a')};"
            "}"
        )
        self._send_btn.setStyleSheet(
            "QPushButton#send-btn { background: #ff6b35; border-radius: 22px; border: none; }"
            "QPushButton#send-btn:hover { background: #f06a38; }"
            f"QPushButton#send-btn:disabled {{ background: {theme_manager.c('#533124', '#d8c3b6')}; }}"
        )
        self._input_tip.setStyleSheet(
            f"color: {theme_manager.c('#70786f', '#8a8176')}; font-size: 11px; font-weight: 600; {_FONT}"
        )

    def _style_quick(self):
        self._chat_container.setStyleSheet(
            f"QWidget#dishy-chat-canvas {{ background: {theme_manager.c('#101417', '#f6f2ed')}; }}"
        )
        self._quick_wrapper.setStyleSheet(
            "QWidget#dishy-quick-wrapper {"
            f" background: {theme_manager.c('rgba(16,20,23,0.96)', 'rgba(255,250,245,0.96)')};"
            f" border-top: 1px solid {theme_manager.c('#20262d', '#ddd2c6')};"
            "}"
        )
        self._hint_lbl.setStyleSheet(
            f"color: {theme_manager.c('#7e877e', '#8a8176')}; font-size: 11px; font-weight: 700; {_FONT}"
        )
        self._refresh_chips_btn.setStyleSheet(
            "QPushButton {"
            f" background: {theme_manager.c('#14181d', '#f2ebe2')};"
            f" color: {theme_manager.c('#8d867d', '#756d63')};"
            f" border: 1px solid {theme_manager.c('#282e35', '#ddd1c4')}; border-radius: 9px;"
            f" padding: 0 10px; font-size: 11px; font-weight: 700; {_FONT}"
            "}"
            "QPushButton:hover { background: rgba(255,107,53,0.08); border-color: rgba(255,107,53,0.22); }"
        )

    def apply_theme(self, mode: str):
        self.setStyleSheet(f"background: {theme_manager.c('#101417', '#f6f2ed')};")
        self._apply_scroll_style()
        self._style_header()
        self._style_resume_bar()
        self._style_quick()
        self._style_input()
        self._rebuild_quick_prompts()
        # Re-theme existing bubbles without clearing the conversation
        for i in range(self._chat_layout.count()):
            widget = self._chat_layout.itemAt(i).widget()
            if isinstance(widget, MessageBubble):
                widget.apply_theme(mode)
