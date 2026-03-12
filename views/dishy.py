import re
import uuid
import random
import qtawesome as qta
from utils.theme import manager as theme_manager
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QSizePolicy, QDialog, QFrame,
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QBrush, QLinearGradient, QPen, QPainterPath

from api.claude_ai import ClaudeAI
from api.dishy_tools import TOOLS, TOOL_STATUS_MESSAGES, summarise_tool_calls
from utils.workers import run_async

_claude = ClaudeAI()

_MAX_HISTORY = 20
_TRIM_TO     = 14

_FONT = (
    'font-family: "SF Pro Display","SF Pro Text",-apple-system,'
    '".AppleSystemUIFont","Helvetica Neue",Arial,sans-serif;'
)


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
    """Green circle with a white robot icon — shown left of assistant bubbles."""
    def __init__(self, size: int = 36, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        # Use 46% of diameter so the glyph sits centred with breathing room
        icon_px = max(int(size * 0.46), 10)
        self._icon = qta.icon("fa5s.robot", color="white").pixmap(QSize(icon_px, icon_px))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        grad = QLinearGradient(0, 0, self._size, self._size)
        grad.setColorAt(0.0, QColor("#42e8ad"))
        grad.setColorAt(1.0, QColor("#1eaf72"))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, self._size, self._size)
        margin = int(self._size * 0.27)
        icon_size = self._size - 2 * margin
        p.drawPixmap(margin, margin, icon_size, icon_size, self._icon)


# ── Custom-painted uniform-radius pill (AA corners) ───────────────────────────

class _PillLabel(QWidget):
    """
    Anti-aliased pill badge. Uses QPainter so corners are smooth.
    Drop-in replacement for a styled QLabel wherever a pill shape is needed.
    """
    def __init__(self, text: str, bg: QColor, border: QColor, text_color: str,
                 radius: int = 12, font_size: int = 12, bold: bool = False,
                 parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._bg     = bg
        self._border = border
        self._r      = radius

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 5, 14, 5)
        lay.setSpacing(0)

        self._lbl = QLabel(text)
        weight = "font-weight: 600;" if bold else ""
        self._lbl.setStyleSheet(
            f"background: transparent; border: none; color: {text_color};"
            f" font-size: {font_size}px; {weight} {_FONT}"
        )
        lay.addWidget(self._lbl)

    def setText(self, text: str):
        self._lbl.setText(text)
        self.adjustSize()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._border)
        pen.setWidthF(2.0)
        p.setPen(pen)
        p.setBrush(QBrush(self._bg))
        s = 1.0
        p.drawRoundedRect(QRectF(s, s, self.width() - 2*s, self.height() - 2*s),
                          self._r, self._r)


# ── Action confirm pill ───────────────────────────────────────────────────────

class ActionSummaryBubble(QWidget):
    """One green pill per tool category — consolidated counts, indented like Dishy bubbles."""

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        vl = QVBoxLayout(self)
        vl.setContentsMargins(46, 4, 0, 4)  # 46px = avatar+gap indent
        vl.setSpacing(4)
        for text in labels:
            hl = QHBoxLayout()
            hl.setContentsMargins(0, 0, 0, 0)
            pill = _PillLabel(
                f"  ✓  {text}",
                bg=QColor(52, 211, 153, 18),
                border=QColor(52, 211, 153, 80),
                text_color="#34d399",
                radius=12, font_size=12, bold=True,
            )
            hl.addWidget(pill)
            hl.addStretch()
            vl.addLayout(hl)


# ── Custom-painted bubble body (anti-aliased corners) ─────────────────────────

class _BubbleWidget(QWidget):
    """
    Bubble background painted via QPainter so corners are truly anti-aliased.
    QSS border-radius uses pixel clipping and is always jagged — this is the fix.
    """
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._is_user = is_user

        is_dark = theme_manager.mode == "dark"
        if is_user:
            self._bg     = QColor(52, 211, 153, 23)    # rgba(52,211,153,0.09)
            self._border = QColor(52, 211, 153, 95)    # ~0.37 — thicker pen needs more opacity
            self._radii  = (18, 18, 5, 18)              # tl, tr, br, bl
            txt_col = "#cef0df" if is_dark else "#1a1a1a"
        else:
            self._bg     = QColor(255, 255, 255, 10) if is_dark else QColor("#f7f7f7")
            self._border = QColor(255, 255, 255, 45) if is_dark else QColor("#d8d8d8")
            self._radii  = (5, 18, 18, 18)
            txt_col = "#d8d8d8" if is_dark else "#1a1a1a"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 11, 18, 11)
        lay.setSpacing(0)

        self._lbl = QLabel(text)
        self._lbl.setWordWrap(True)
        self._lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._lbl.setStyleSheet(
            f"background: transparent; border: none; color: {txt_col};"
            f" font-size: 14px; {_FONT}"
        )
        lay.addWidget(self._lbl)

    def apply_theme(self, mode: str):
        is_dark = mode == "dark"
        if self._is_user:
            txt_col = "#cef0df" if is_dark else "#1a1a1a"
        else:
            self._bg     = QColor(255, 255, 255, 10) if is_dark else QColor("#f7f7f7")
            self._border = QColor(255, 255, 255, 45) if is_dark else QColor("#d8d8d8")
            txt_col = "#d8d8d8" if is_dark else "#1a1a1a"
        self._lbl.setStyleSheet(
            f"background: transparent; border: none; color: {txt_col};"
            f" font-size: 14px; {_FONT}"
        )
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        pen = QPen(self._border)
        pen.setWidthF(2.0)
        p.setPen(pen)
        p.setBrush(QBrush(self._bg))

        # Inset rect by half the pen width so stroke isn't clipped at widget edge
        s = 1.0
        r = QRectF(s, s, self.width() - 2 * s, self.height() - 2 * s)
        tl, tr, br, bl = self._radii

        path = QPainterPath()
        path.moveTo(r.x() + tl, r.y())
        path.lineTo(r.x() + r.width() - tr, r.y())
        path.quadTo(r.x() + r.width(), r.y(),
                    r.x() + r.width(), r.y() + tr)
        path.lineTo(r.x() + r.width(), r.y() + r.height() - br)
        path.quadTo(r.x() + r.width(), r.y() + r.height(),
                    r.x() + r.width() - br, r.y() + r.height())
        path.lineTo(r.x() + bl, r.y() + r.height())
        path.quadTo(r.x(), r.y() + r.height(),
                    r.x(), r.y() + r.height() - bl)
        path.lineTo(r.x(), r.y() + tl)
        path.quadTo(r.x(), r.y(), r.x() + tl, r.y())
        path.closeSubpath()
        p.drawPath(path)


# ── Chat bubbles ──────────────────────────────────────────────────────────────

class MessageBubble(QWidget):
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(10)

        self._bubble = _BubbleWidget(text, is_user)

        if is_user:
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            spacer.setMinimumWidth(80)
            layout.addWidget(spacer, 1)
            layout.addWidget(self._bubble, 3)
        else:
            avatar = _DishyAvatar(36)
            layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
            layout.addWidget(self._bubble, 4)
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            spacer.setMinimumWidth(80)
            layout.addWidget(spacer, 1)

    def apply_theme(self, mode: str):
        self._bubble.apply_theme(mode)


# ── Typing indicator ──────────────────────────────────────────────────────────

class _TypingIndicator(QWidget):
    """Spinner + live status text, shown while Dishy is working."""
    _SPIN = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(10)
        avatar = _DishyAvatar(36)
        self._step   = 0
        self._status = "Thinking..."
        self._pending: list[str] = []

        is_dark = theme_manager.mode == "dark"
        self._pill = _PillLabel(
            f"{self._SPIN[0]}  Thinking...",
            bg=QColor(255, 255, 255, 10) if is_dark else QColor("#f7f7f7"),
            border=QColor(255, 255, 255, 45) if is_dark else QColor("#d8d8d8"),
            text_color="#34d399",
            radius=18, font_size=13,
        )
        # Proxy for _tick() compatibility
        self._lbl = self._pill._lbl

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._pill)
        layout.addWidget(spacer)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(80)

    def _tick(self):
        if self._pending:
            self._status = self._pending.pop()
            self._pending.clear()
        self._step = (self._step + 1) % len(self._SPIN)
        self._pill.setText(f"{self._SPIN[self._step]}  {self._status}")

    def update_status(self, text: str):
        """Thread-safe: append to queue; main-thread timer picks it up."""
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
        self._build_ui()

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
        self._build_ui()

    def set_sync_fn(self, fn):
        self._sync_fn = fn

    def setup_actions(self, actions, refresh_callback):
        self._actions    = actions
        self._refresh_cb = refresh_callback

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())

        # Resume banner — hidden by default, shown by _check_resume_session()
        self._resume_bar = self._build_resume_bar()
        self._resume_bar.setVisible(False)
        outer.addWidget(self._resume_bar)

        # ── Chat scroll area ──────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._scroll.verticalScrollBar().setStyleSheet(
            "QScrollBar:vertical { width: 5px; background: transparent; }"
            f"QScrollBar::handle:vertical {{ background: {theme_manager.c('#2a2a2a', '#cccccc')};"
            " border-radius: 2px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self._chat_container = QWidget()
        self._chat_container.setStyleSheet(
            f"background: {theme_manager.c('#0b0b0b', '#f6f6f6')};"
        )
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(24, 16, 24, 16)
        self._chat_layout.setSpacing(2)
        self._chat_layout.addStretch()

        self._scroll.setWidget(self._chat_container)
        outer.addWidget(self._scroll, 1)

        # Greeting bubble
        self._add_bubble(DISHY_INTRO, is_user=False)

        # ── Quick-prompt chips (horizontal scroll) ────────────────────────────
        self._quick_wrapper = QWidget()
        self._quick_wrapper.setStyleSheet(
            f"background: {theme_manager.c('rgba(255,255,255,0.02)', 'rgba(0,0,0,0.015)')};"
            f" border-top: 1px solid {theme_manager.c('rgba(255,255,255,0.06)', 'rgba(0,0,0,0.06)')};"
        )
        qw_layout = QVBoxLayout(self._quick_wrapper)
        qw_layout.setContentsMargins(20, 8, 20, 10)
        qw_layout.setSpacing(6)

        # "Try asking" row with refresh chips button
        hint_row = QHBoxLayout()
        hint_row.setContentsMargins(0, 0, 0, 0)
        hint_row.setSpacing(6)
        hint_lbl = QLabel("Try asking")
        hint_lbl.setStyleSheet(
            f"color: {theme_manager.c('#555555', '#999999')}; font-size: 11px; font-weight: 500;"
            f" {_FONT} background: transparent;"
        )
        self._hint_lbl = hint_lbl
        hint_row.addWidget(hint_lbl)
        hint_row.addStretch()
        refresh_chips_btn = QPushButton()
        refresh_chips_btn.setIcon(qta.icon("fa5s.sync-alt", color=theme_manager.c("#484848", "#aaaaaa")))
        refresh_chips_btn.setIconSize(QSize(10, 10))
        refresh_chips_btn.setFixedSize(22, 22)
        refresh_chips_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_chips_btn.setToolTip("Refresh suggestions")
        refresh_chips_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; border-radius: 11px; }"
            f"QPushButton:hover {{ background: {theme_manager.c('rgba(255,255,255,0.06)', 'rgba(0,0,0,0.06)')}; }}"
        )
        refresh_chips_btn.clicked.connect(self._rebuild_quick_prompts)
        hint_row.addWidget(refresh_chips_btn)
        qw_layout.addLayout(hint_row)

        self._quick_scroll = QScrollArea()
        self._quick_scroll.setFixedHeight(44)
        self._quick_scroll.setWidgetResizable(True)
        self._quick_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._quick_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._quick_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._chips_widget = QWidget()
        self._chips_widget.setStyleSheet("background: transparent;")
        self._chips_layout = QHBoxLayout(self._chips_widget)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(8)
        self._chips_layout.addStretch()

        self._quick_scroll.setWidget(self._chips_widget)
        qw_layout.addWidget(self._quick_scroll)
        self._quick_widget = self._quick_wrapper  # alias for external code
        outer.addWidget(self._quick_wrapper)
        self._rebuild_quick_prompts()

        # ── Input bar ─────────────────────────────────────────────────────────
        outer.addWidget(self._build_input_bar())

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setObjectName("dishy-header")
        hdr.setFixedHeight(64)
        hdr.setStyleSheet(
            "QWidget#dishy-header {"
            f" background: {theme_manager.c('qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(52,211,153,0.09),stop:1 rgba(52,211,153,0.03))', 'qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(52,211,153,0.08),stop:1 rgba(52,211,153,0.02))')};"
            f" border-bottom: 1px solid {theme_manager.c('rgba(52,211,153,0.15)', 'rgba(52,211,153,0.20)')};"
            "}"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(24, 0, 20, 0)
        hl.setSpacing(12)

        avatar = _DishyAvatar(40)
        hl.addWidget(avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        # Title column — wrapped in a widget so AlignVCenter applies properly
        title_widget = QWidget()
        title_widget.setStyleSheet("background: transparent;")
        title_col = QVBoxLayout(title_widget)
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)
        title_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title = QLabel("Dishy")
        title.setStyleSheet(
            f"color: {theme_manager.c('#f0f0f0', '#1a1a1a')};"
            f" font-size: 16px; font-weight: 700; {_FONT} background: transparent;"
        )
        sub = QLabel("Powered by Claude · Your cooking assistant")
        sub.setStyleSheet(
            f"color: {theme_manager.c('rgba(52,211,153,0.80)', 'rgba(16,140,80,0.75)')}; font-size: 11px;"
            f" font-weight: 500; {_FONT} background: transparent;"
        )
        title_col.addWidget(title)
        title_col.addWidget(sub)
        hl.addWidget(title_widget, 0, Qt.AlignmentFlag.AlignVCenter)
        hl.addStretch()

        # History button — prominent green outlined style
        hist_btn = QPushButton("  History")
        hist_btn.setIcon(qta.icon("fa5s.history", color="#34d399"))
        hist_btn.setIconSize(QSize(13, 13))
        hist_btn.setFixedHeight(36)
        hist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hist_btn.setStyleSheet(
            "QPushButton {"
            " background: rgba(52,211,153,0.07); color: #34d399;"
            " border: 1.5px solid rgba(52,211,153,0.30); border-radius: 10px;"
            f" font-size: 12px; font-weight: 600; padding: 0 14px; {_FONT}"
            " }"
            "QPushButton:hover { background: rgba(52,211,153,0.14); border-color: rgba(52,211,153,0.55); }"
        )
        hist_btn.clicked.connect(self._open_history)
        hl.addWidget(hist_btn)

        # New chat button
        new_btn = QPushButton("  New chat")
        new_btn.setIcon(qta.icon("fa5s.plus", color="#888888"))
        new_btn.setIconSize(QSize(12, 12))
        new_btn.setFixedHeight(36)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(
            "QPushButton { background: transparent;"
            f" border: 1.5px solid {theme_manager.c('rgba(255,255,255,0.12)', 'rgba(0,0,0,0.12)')};"
            f" color: {theme_manager.c('#888888', '#666666')};"
            f" border-radius: 10px; padding: 0 14px; font-size: 12px; {_FONT}"
            " }"
            "QPushButton:hover { background: rgba(128,128,128,0.08); }"
        )
        new_btn.clicked.connect(self._clear_chat)
        hl.addWidget(new_btn)

        self._hdr = hdr
        return hdr

    def _build_resume_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(
            "background: rgba(52,211,153,0.08);"
            " border-bottom: 1px solid rgba(52,211,153,0.2);"
        )
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(28, 8, 20, 8)
        hl.setSpacing(12)

        av = _DishyAvatar(22)
        hl.addWidget(av, 0, Qt.AlignmentFlag.AlignVCenter)

        lbl = QLabel("Continue where you left off?")
        lbl.setStyleSheet(
            f"color: {theme_manager.c('#c8c8c8', '#444444')};"
            f" font-size: 12px; {_FONT} background: transparent;"
        )
        hl.addWidget(lbl)
        hl.addStretch()

        resume_btn = QPushButton("Resume")
        resume_btn.setObjectName("resume-btn")
        resume_btn.setFixedHeight(28)
        resume_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        resume_btn.setStyleSheet(
            "QPushButton#resume-btn {"
            " background: rgba(52,211,153,0.15); color: #34d399;"
            " border: 1px solid rgba(52,211,153,0.35); border-radius: 7px;"
            f" font-size: 12px; font-weight: 600; padding: 0 14px; {_FONT} }}"
            "QPushButton#resume-btn:hover { background: rgba(52,211,153,0.25); }"
        )
        resume_btn.clicked.connect(self._do_resume)
        hl.addWidget(resume_btn)

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.setFixedHeight(28)
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.setStyleSheet(
            f"background: transparent; color: {theme_manager.c('#666666', '#999999')};"
            f" border: none; font-size: 12px; padding: 0 10px; {_FONT}"
        )
        dismiss_btn.clicked.connect(lambda: bar.setVisible(False))
        hl.addWidget(dismiss_btn)

        bar.setFixedHeight(44)
        # Store the session_id this bar points to — set when populated
        bar._session_id = None
        bar._session_rows = None
        return bar

    def _build_input_bar(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet(
            f"background: {theme_manager.c('#0b0b0b', '#f6f6f6')};"
            f" border-top: 1px solid {theme_manager.c('rgba(255,255,255,0.06)', 'rgba(0,0,0,0.06)')};"
        )
        cl = QVBoxLayout(container)
        cl.setContentsMargins(20, 12, 20, 14)
        cl.setSpacing(0)

        # The pill input row
        pill = QWidget()
        pill.setObjectName("input-pill")
        pill.setStyleSheet(
            "QWidget#input-pill {"
            f" background: {theme_manager.c('rgba(255,255,255,0.04)', '#ffffff')};"
            " border: 2.5px solid rgba(52,211,153,0.42);"
            " border-radius: 999px;"
            "}"
        )
        pill_layout = QHBoxLayout(pill)
        pill_layout.setContentsMargins(20, 7, 7, 7)
        pill_layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask Dishy anything about food, recipes, or cooking…")
        self._input.setFrame(False)
        self._input.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._input.setStyleSheet(
            "QLineEdit {"
            " background: transparent; border: none;"
            f" color: {theme_manager.c('#f0f0f0', '#1a1a1a')};"
            f" font-size: 14px; {_FONT}"
            " padding: 0;"
            "}"
            "QLineEdit::placeholder {"
            f" color: {theme_manager.c('#4e4e4e', '#aaaaaa')};"
            "}"
        )
        self._input.setMinimumHeight(40)
        self._input.setClearButtonEnabled(True)
        self._input.returnPressed.connect(self._send)
        pill_layout.addWidget(self._input, 1)

        self._send_btn = QPushButton()
        self._send_btn.setObjectName("send-btn")
        self._send_btn.setFixedSize(42, 42)
        self._send_btn.setIcon(qta.icon("fa5s.arrow-up", color="white"))
        self._send_btn.setIconSize(QSize(15, 15))
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(
            "QPushButton#send-btn {"
            " background: #34d399; border-radius: 21px; border: none;"
            "}"
            "QPushButton#send-btn:hover { background: #2ec48d; }"
            "QPushButton#send-btn:disabled { background: #2a4a3e; }"
        )
        self._send_btn.clicked.connect(self._send)
        pill_layout.addWidget(self._send_btn)

        pill.setFixedHeight(58)
        cl.addWidget(pill)
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

        sampled = random.sample(QUICK_PROMPTS_POOL, min(6, len(QUICK_PROMPTS_POOL)))
        for text, icon_name in sampled:
            chip = QPushButton(f" {text} ")
            chip.setIcon(qta.icon(icon_name, color="#34d399"))
            chip.setIconSize(QSize(13, 13))
            chip.setFixedHeight(34)
            chip.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                "QPushButton {"
                f" background: {theme_manager.c('rgba(52,211,153,0.06)', 'rgba(52,211,153,0.08)')};"
                " border: 2px solid rgba(52,211,153,0.38);"
                " border-radius: 999px;"
                " color: #34d399;"
                f" font-size: 12px; font-weight: 500; {_FONT} padding: 0 14px;"
                "}"
                "QPushButton:hover {"
                f" background: {theme_manager.c('rgba(52,211,153,0.12)', 'rgba(52,211,153,0.14)')};"
                " border-color: rgba(52,211,153,0.60);"
                "}"
                "QPushButton:focus { outline: none; }"
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

        QTimer.singleShot(80, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    # ── Chat helpers ──────────────────────────────────────────────────────────

    def _add_bubble(self, text: str, is_user: bool):
        bubble = MessageBubble(text, is_user)
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def _send(self):
        self._send_text(self._input.text().strip())

    def _send_text(self, text: str):
        if not text:
            return
        self._resume_bar.setVisible(False)
        self._quick_wrapper.setVisible(False)

        self._add_bubble(text, is_user=True)
        self._input.clear()

        # Disable send during generation
        self._send_btn.setEnabled(False)
        self._send_btn.setIcon(qta.icon("fa5s.ellipsis-h", color="white"))

        # Persist user message
        if self._db:
            self._db.save_dishy_message(self._session_id, "user", text)
            if self._sync_fn:
                self._sync_fn()

        # Typing indicator
        self._typing_indicator = _TypingIndicator()
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, self._typing_indicator)
        QTimer.singleShot(40, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

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
        full_msg = f"{app_ctx}\n\n{text}" if app_ctx else text

        if actions is not None:
            actions.clear_pending()

            def _tool_handler(name: str, inp: dict) -> str:
                # Push status update to the typing indicator (thread-safe via queue)
                status = TOOL_STATUS_MESSAGES.get(name, "Working...")
                if self._typing_indicator is not None:
                    self._typing_indicator.update_status(status)
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
            QTimer.singleShot(60, lambda: self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            ))
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
            self._remove_typing_indicator()
            err_lower = err.lower()
            _is_auth = False
            if "credit balance" in err_lower or "too low" in err_lower:
                msg = "Anthropic credits are out. Top up at console.anthropic.com/settings/billing."
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

    def apply_theme(self, mode: str):
        self._hdr.setStyleSheet(
            "QWidget#dishy-header {"
            f" background: {theme_manager.c('qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(52,211,153,0.09),stop:1 rgba(52,211,153,0.03))', 'qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(52,211,153,0.08),stop:1 rgba(52,211,153,0.02))')};"
            f" border-bottom: 1px solid {theme_manager.c('rgba(52,211,153,0.15)', 'rgba(52,211,153,0.20)')};"
            "}"
        )
        self._scroll.verticalScrollBar().setStyleSheet(
            "QScrollBar:vertical { width: 5px; background: transparent; }"
            f"QScrollBar::handle:vertical {{ background: {theme_manager.c('#2a2a2a', '#cccccc')};"
            " border-radius: 2px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self._chat_container.setStyleSheet(
            f"background: {theme_manager.c('#0b0b0b', '#f6f6f6')};"
        )
        self._quick_wrapper.setStyleSheet(
            f"background: {theme_manager.c('rgba(255,255,255,0.02)', 'rgba(0,0,0,0.015)')};"
            f" border-top: 1px solid {theme_manager.c('rgba(255,255,255,0.06)', 'rgba(0,0,0,0.06)')};"
        )
        self._hint_lbl.setStyleSheet(
            f"color: {theme_manager.c('#555555', '#999999')}; font-size: 11px; font-weight: 500;"
            f" {_FONT} background: transparent;"
        )
        self._input_container.setStyleSheet(
            f"background: {theme_manager.c('#0b0b0b', '#f6f6f6')};"
            f" border-top: 1px solid {theme_manager.c('rgba(255,255,255,0.06)', 'rgba(0,0,0,0.06)')};"
        )
        self._input_pill.setStyleSheet(
            "QWidget#input-pill {"
            f" background: {theme_manager.c('rgba(255,255,255,0.04)', '#ffffff')};"
            " border: 2.5px solid rgba(52,211,153,0.42);"
            " border-radius: 999px;"
            "}"
        )
        self._input.setStyleSheet(
            "QLineEdit {"
            " background: transparent; border: none;"
            f" color: {theme_manager.c('#f0f0f0', '#1a1a1a')};"
            f" font-size: 14px; {_FONT}"
            " padding: 0;"
            "}"
            "QLineEdit::placeholder {"
            f" color: {theme_manager.c('#4e4e4e', '#aaaaaa')};"
            "}"
        )
        self._rebuild_quick_prompts()
        # Re-theme existing bubbles without clearing the conversation
        for i in range(self._chat_layout.count()):
            widget = self._chat_layout.itemAt(i).widget()
            if isinstance(widget, MessageBubble):
                widget.apply_theme(mode)
