"""
Floating Dishy chat bubble — appears in the bottom-right of every page.
"""

import re
import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize, QTimer, QEvent, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath

from api.claude_ai import ClaudeAI
from api.dishy_tools import TOOLS, TOOL_STATUS_MESSAGES, summarise_tool_calls
from utils.workers import run_async
from utils.theme import manager as theme_manager

_claude = ClaudeAI()

_MAX_HISTORY = 20   # max history entries before trimming
_TRIM_TO     = 14   # keep this many most-recent entries after trimming

PANEL_W  = 400
PANEL_H  = 520
FAB_SIZE = 54
GAP      = 10
MARGIN   = 20


def _clean(text: str) -> str:
    """Strip markdown formatting from Claude responses."""
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    text = re.sub(r'`([^`\n]+)`', r'\1', text)
    text = re.sub(r'^[\-\*]\s+', '- ', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

PAGE_CONTEXTS = {
    "Home":
        "The user is on Home — the home screen. It shows today's planned meals (breakfast, "
        "lunch, dinner) pulled live from the Meal Planner, a weekly summary, and quick-action "
        "tiles to jump to other sections. Check the live context: if today's meals are planned "
        "but unlogged, sync the nutrition silently. If nothing is planned for today, proactively "
        "offer to set up their day. Reference what's actually showing — be specific, not generic.",

    "Recipes":
        "The user is on the Recipes page. They can browse saved recipes by tag, view full "
        "recipe detail (ingredients, instructions, nutrition card, photo), create new recipes "
        "manually (you look up macros per ingredient in real time as they type), scrape a "
        "recipe from any URL, mark favourites, add to the Meal Planner from the detail view, "
        "and delete recipes. Every recipe must have complete nutrition data — kcal, protein, "
        "carbs, fat, fiber, sugar per serving. Check the live context for their library — "
        "if they ask for recipe ideas, reference what they already have. If they ask you to "
        "create a recipe, save it immediately with save_recipe (include full nutrition).",

    "Meal Planner":
        "The user is on the Meal Planner — a weekly Mon–Sun grid with Breakfast, Lunch, Dinner "
        "slots. Every slot must link to a saved recipe (no free-text custom names). If they ask "
        "you to add a meal, save the recipe first then set the slot. Check the live context for "
        "the current week's plan — reference what's already scheduled. If slots are empty, offer "
        "to fill the week. If they want individual changes, use set_meal_slot. When you set "
        "today's meals, nutrition is logged automatically. Prefer their favourite recipes and "
        "respect dietary preferences when suggesting meals.",

    "Nutrition":
        "The user is on the Nutrition dashboard. It shows six macro rings vs daily goals "
        "(Calories 2000 kcal, Protein 50g, Carbs 260g, Fat 65g, Fiber 30g, Sugar 50g), "
        "today's meal plan with kcal per meal, a weekly bar chart, stat tiles, the food log, "
        "and a Quick Add box. Check the live context immediately: read today's nutrition totals "
        "and the meal plan sync status. If meals are unlogged, call sync_meal_plan_nutrition "
        "right away without asking. Then tell the user exactly where they stand — actual numbers, "
        "how far from each goal, what they still need. Never be vague about nutrition here.",

    "Shopping List":
        "The user is on the Shopping List. They can add items manually, check items off, clear "
        "checked items, and export to Apple Notes. You can add items directly (add_shopping_items) "
        "or generate the full list from the week's meal plan (shopping_list_from_meal_plan). "
        "Check the live context for what's already on the list and what's on the meal plan — "
        "if the list is empty and a meal plan exists, offer to generate it. Help with quantities, "
        "ingredient swaps, and what to prioritise at the shops.",

    "Settings":
        "The user is in Settings. They can toggle dark/light mode, set dietary preferences "
        "(used by you when planning meals — tell them this!), and manage data (export/import "
        "full JSON backup). Help them configure the app. If they set dietary preferences, "
        "confirm you'll use them in future meal planning.",

    "How to use":
        "The user is reading the DishBoard help guide. Walk them through any feature in detail — "
        "you know every part of the app. Be specific: tell them exactly where to click, what "
        "happens, and what you can do on each page. Always mention that you can take actions "
        "directly (save recipes, set meals, build shopping lists, track nutrition) not just advise.",

    "Dishy":        None,  # full-page Dishy — bubble hidden
}

PAGE_GREETINGS = {
    "Home":         "I can see today's plan — want me to sort out meals, log your nutrition, or something else?",
    "Recipes":      "Want a new recipe saved to your library, or looking for one you already have?",
    "Meal Planner": "I can fill your whole week or set individual meals — just tell me what you need.",
    "Nutrition":    "I've got your nutrition data loaded. Want me to log today's meals or tell you where you stand?",
    "Shopping List":"I can build your shopping list from the meal plan or add specific items — what do you need?",
    "Settings":     "Need help with any settings? I can explain what each option does.",
    "How to use":   "Happy to walk you through any part of DishBoard — just ask!",
    "Dishy":        None,
}


_MINI_FONT = ('font-family: "SF Pro Display","SF Pro Text",-apple-system,'
             '".AppleSystemUIFont","Helvetica Neue",Arial,sans-serif;')


# ── Painted pill helper ───────────────────────────────────────────────────────

class _MiniPill(QWidget):
    """Anti-aliased uniform-radius pill for the float panel."""
    def __init__(self, text: str, bg: QColor, border: QColor, text_color: str,
                 radius: int = 13, font_size: int = 13, bold: bool = False,
                 max_width: int = 0, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        if max_width:
            self.setMaximumWidth(max_width)
        self._bg     = bg
        self._border = border
        self._r      = radius

        lay = QHBoxLayout(self)
        lay.setContentsMargins(13, 8, 13, 8)
        lay.setSpacing(0)

        self._lbl = QLabel(text)
        self._lbl.setWordWrap(bool(max_width))
        self._lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        weight = "font-weight: 600;" if bold else ""
        self._lbl.setStyleSheet(
            f"background: transparent; border: none; color: {text_color};"
            f" font-size: {font_size}px; {weight} {_MINI_FONT}"
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


# ── Painted bubble helper ─────────────────────────────────────────────────────

class _MiniPillBubble(QWidget):
    """Anti-aliased asymmetric-corner bubble for the float panel."""
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.setMaximumWidth(PANEL_W - 56)

        is_dark = theme_manager.mode == "dark"
        if is_user:
            self._bg     = QColor(255, 107, 53, 26)   # rgba(255,107,53,0.10)
            self._border = QColor(255, 107, 53, 80)   # ~0.31 — more visible with 2px pen
            self._radii  = (13, 13, 4, 13)
            txt = theme_manager.c('#e8e8e8', '#1a1a1a')
        else:
            self._bg     = QColor(255, 255, 255, 10) if is_dark else QColor("#f7f7f7")
            self._border = QColor(255, 255, 255, 45) if is_dark else QColor("#d0d0d0")
            self._radii  = (4, 13, 13, 13)
            txt = theme_manager.c('#cccccc', '#1a1a1a')

        lay = QVBoxLayout(self)
        lay.setContentsMargins(13, 8, 13, 8)
        lay.setSpacing(0)

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet(
            f"background: transparent; border: none; color: {txt};"
            f" font-size: 13px; {_MINI_FONT}"
        )
        lay.addWidget(lbl)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pen = QPen(self._border)
        pen.setWidthF(2.0)
        p.setPen(pen)
        p.setBrush(QBrush(self._bg))
        s = 1.0
        r = QRectF(s, s, self.width() - 2*s, self.height() - 2*s)
        tl, tr, br, bl = self._radii
        path = QPainterPath()
        path.moveTo(r.x() + tl, r.y())
        path.lineTo(r.x() + r.width() - tr, r.y())
        path.quadTo(r.x() + r.width(), r.y(), r.x() + r.width(), r.y() + tr)
        path.lineTo(r.x() + r.width(), r.y() + r.height() - br)
        path.quadTo(r.x() + r.width(), r.y() + r.height(),
                    r.x() + r.width() - br, r.y() + r.height())
        path.lineTo(r.x() + bl, r.y() + r.height())
        path.quadTo(r.x(), r.y() + r.height(), r.x(), r.y() + r.height() - bl)
        path.lineTo(r.x(), r.y() + tl)
        path.quadTo(r.x(), r.y(), r.x() + tl, r.y())
        path.closeSubpath()
        p.drawPath(path)


class _MiniMessage(QWidget):
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 3, 0, 3)
        bubble = _MiniPillBubble(text, is_user)
        if is_user:
            hl.addStretch()
            hl.addWidget(bubble)
        else:
            hl.addWidget(bubble)
            hl.addStretch()


class _MiniActionSummary(QWidget):
    """One green pill per tool category — shows consolidated counts."""

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 2, 0, 2)
        vl.setSpacing(3)
        for text in labels:
            hl = QHBoxLayout()
            hl.setContentsMargins(0, 0, 0, 0)
            pill = _MiniPill(
                f"✓  {text}",
                bg=QColor(52, 211, 153, 18),
                border=QColor(52, 211, 153, 80),
                text_color="#34d399",
                radius=12, font_size=12, bold=True,
            )
            hl.addWidget(pill)
            hl.addStretch()
            vl.addLayout(hl)


class _MiniTypingIndicator(QWidget):
    """Spinner + live status text for the floating bubble panel."""
    _SPIN = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, parent=None):
        super().__init__(parent)
        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 3, 0, 3)
        self._step   = 0
        self._status = "Thinking..."
        self._pending: list[str] = []

        is_dark = theme_manager.mode == "dark"
        self._pill = _MiniPill(
            f"{self._SPIN[0]}  Thinking...",
            bg=QColor(255, 255, 255, 10) if is_dark else QColor("#f7f7f7"),
            border=QColor(255, 255, 255, 45) if is_dark else QColor("#d0d0d0"),
            text_color="#34d399",
            radius=13, font_size=12,
        )
        self._lbl = self._pill._lbl  # proxy for compat

        hl.addWidget(self._pill)
        hl.addStretch()
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


class DishyBubble(QWidget):
    """
    Floating chat bubble overlay.  Parent should be the content wrapper.
    Call set_page(name) whenever the active view changes.
    """

    session_expired = Signal(str)   # emits last-known user email

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._open   = False
        self._page   = "Home"
        self._history: list[dict] = []
        self._typing_indicator: _MiniTypingIndicator | None = None

        # Set by MainWindow after construction via setup_actions()
        self._actions      = None   # DishyActions | None
        self._refresh_cb   = None   # callable(list[str]) | None

        self._build_ui()

        parent.installEventFilter(self)
        self.raise_()

    def setup_actions(self, actions, refresh_callback):
        """
        Wire in DishyActions and a refresh callback.
        refresh_callback(view_names: list[str]) is called on the main thread
        after each tool-calling turn so views can reload their data.
        """
        self._actions    = actions
        self._refresh_cb = refresh_callback
        # Update the visual badge so we can confirm wiring at runtime
        self._tools_badge.setText("⚙ tools on")
        self._tools_badge.setStyleSheet(
            "color: #34d399; font-size: 9px; font-weight: 600;"
            " background: transparent; border: none; padding: 0 2px;"
        )

    # ──────────────────────────────────────────── build

    def _build_ui(self):
        self._panel = self._build_panel()
        self._panel.setVisible(False)
        self._panel.setParent(self)

        self._fab = QPushButton(self)
        self._fab.setFixedSize(FAB_SIZE, FAB_SIZE)
        self._fab.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fab.setIcon(qta.icon("fa5s.robot", color="#ffffff"))
        self._fab.setIconSize(QSize(22, 22))
        self._fab.setToolTip("Ask Dishy")
        self._fab.setStyleSheet(
            "QPushButton {"
            "  background: #34d399;"
            "  border-radius: 27px;"
            "  border: 2px solid rgba(255,255,255,0.1);"
            "}"
            "QPushButton:hover { background: #4ae3a8; }"
            "QPushButton:pressed { background: #2ac48a; }"
        )
        self._fab.clicked.connect(self._toggle)

    def _build_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("dishy-panel")
        panel.setFixedSize(PANEL_W, PANEL_H)
        panel.setStyleSheet(
            "QWidget#dishy-panel {"
            f"  background: {theme_manager.c('#0e0e0e', '#ffffff')};"
            "  border-radius: 14px;"
            f"  border: 1.5px solid {theme_manager.c('rgba(255,255,255,0.08)', '#e0e0e0')};"
            "}"
        )

        vl = QVBoxLayout(panel)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # ── Header ─────────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet(
            f"background: {theme_manager.c('qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(52,211,153,0.08),stop:1 rgba(52,211,153,0.03))', 'qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(52,211,153,0.07),stop:1 rgba(52,211,153,0.02))')};"
            " border-radius: 14px 14px 0 0;"
            f" border-bottom: 1px solid {theme_manager.c('rgba(255,255,255,0.07)', '#e4e4e4')};"
        )
        self._panel_header = header
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 0, 10, 0)
        hl.setSpacing(8)

        robot_lbl = QLabel()
        robot_lbl.setPixmap(qta.icon("fa5s.robot", color="#34d399").pixmap(QSize(15, 15)))
        robot_lbl.setStyleSheet("background: transparent; border: none;")

        title_lbl = QLabel("Dishy")
        title_lbl.setStyleSheet(
            f"color: {theme_manager.c('#e0e0e0', '#1a1a1a')}; font-size: 14px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        self._title_lbl = title_lbl

        self._page_badge = QLabel("Home")
        self._page_badge.setStyleSheet(
            "color: #555555; font-size: 10px; font-weight: 600; letter-spacing: 0.5px;"
            f" background: {theme_manager.c('rgba(255,255,255,0.05)', '#f0f0f0')};"
            f" border: 1.5px solid {theme_manager.c('rgba(255,255,255,0.08)', '#e0e0e0')};"
            " border-radius: 5px; padding: 1px 7px;"
        )

        # Actions-enabled badge — updates when setup_actions() is called
        self._tools_badge = QLabel("⚙ tools off")
        self._tools_badge.setStyleSheet(
            "color: #555555; font-size: 9px; font-weight: 600;"
            " background: transparent; border: none; padding: 0 2px;"
        )

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ color: {theme_manager.c('#888888', '#666666')}; font-size: 13px;"
            "  background: transparent; border: none; border-radius: 14px; }"
            f"QPushButton:hover {{ color: {theme_manager.c('#d0d0d0', '#111111')};"
            f" background: {theme_manager.c('#1e1e1e', '#e0e0e0')}; }}"
        )
        self._close_btn = close_btn
        close_btn.clicked.connect(self._close_panel)

        hl.addWidget(robot_lbl)
        hl.addWidget(title_lbl)
        hl.addSpacing(4)
        hl.addWidget(self._page_badge)
        hl.addSpacing(4)
        hl.addWidget(self._tools_badge)
        hl.addStretch()
        hl.addWidget(close_btn)
        vl.addWidget(header)

        # ── Scroll / chat area ──────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 4px; }"
        )

        self._chat_container = QWidget()
        self._chat_container.setStyleSheet("background: transparent;")
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(12, 10, 8, 10)
        self._chat_layout.setSpacing(4)
        self._chat_layout.addStretch()

        self._scroll.setWidget(self._chat_container)
        vl.addWidget(self._scroll, 1)

        # ── Input bar ───────────────────────────────────────────────────────
        input_area = QWidget()
        input_area.setFixedHeight(58)
        input_area.setStyleSheet(
            f"background: {theme_manager.c('#0a0a0a', '#f8f8f8')};"
            " border-radius: 0 0 14px 14px;"
            f" border-top: 1px solid {theme_manager.c('rgba(255,255,255,0.06)', '#e4e4e4')};"
        )
        self._panel_footer = input_area
        il = QHBoxLayout(input_area)
        il.setContentsMargins(10, 9, 10, 9)
        il.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask Dishy something…")
        self._input.setFixedHeight(36)
        self._input.returnPressed.connect(self._send)

        self._send_btn = QPushButton()
        self._send_btn.setFixedSize(36, 36)
        self._send_btn.setIcon(qta.icon("fa5s.paper-plane", color="#ffffff"))
        self._send_btn.setIconSize(QSize(14, 14))
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(
            "QPushButton { background: #34d399; border-radius: 8px; border: none; }"
            "QPushButton:hover { background: #4ae3a8; }"
            f"QPushButton:disabled {{ background: {theme_manager.c('#1a1a1a', '#d5d5d5')}; }}"
        )
        self._send_btn.clicked.connect(self._send)

        il.addWidget(self._input)
        il.addWidget(self._send_btn)
        vl.addWidget(input_area)

        return panel

    # ──────────────────────────────────────────── page context

    def reset_session(self):
        """Clear in-memory history (called on account switch)."""
        self._history.clear()
        self._close_panel()

    def set_page(self, page_name: str):
        self._page = page_name
        if hasattr(self, "_page_badge"):
            self._page_badge.setText(page_name)

        hide = PAGE_GREETINGS.get(page_name) is None
        self.setVisible(not hide)

        if self._open and not hide:
            self._close_panel()

    # ──────────────────────────────────────────── toggle

    def _toggle(self):
        if self._open:
            self._close_panel()
        else:
            self._open_panel()

    def _open_panel(self):
        self._open = True
        self._panel.setVisible(True)
        self._reposition()

        if self._chat_layout.count() == 1:  # only stretch = empty
            greeting = PAGE_GREETINGS.get(self._page, "Hi! How can I help?")
            if greeting:
                self._add_bubble(greeting, is_user=False)

        self._input.setFocus()

    def _close_panel(self):
        self._open = False
        self._panel.setVisible(False)
        self._reposition()
        self._remove_typing_indicator()
        self._history.clear()
        while self._chat_layout.count() > 1:
            item = self._chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ──────────────────────────────────────────── chat

    def _add_bubble(self, text: str, is_user: bool):
        msg = _MiniMessage(text, is_user)
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, msg)
        QTimer.singleShot(40, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def trigger_action(self, prompt: str):
        """Open the panel (if closed) and auto-send a pre-set prompt."""
        if not self._open:
            self._open_panel()
        self._input.setText(prompt)
        QTimer.singleShot(120, self._send)

    def _send(self):
        text = self._input.text().strip()
        if not text:
            return
        self._add_bubble(text, is_user=True)
        self._input.clear()
        self._send_btn.setEnabled(False)

        # Show typing indicator
        self._typing_indicator = _MiniTypingIndicator()
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, self._typing_indicator)
        QTimer.singleShot(40, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

        actions = self._actions
        pending_tool_names: list[str] = []

        page_ctx = PAGE_CONTEXTS.get(self._page, "")
        app_ctx  = actions.get_context_string() if actions is not None else ""

        ctx_parts: list[str] = []
        if page_ctx:
            ctx_parts.append(f"[Page context: {page_ctx}]")
        if app_ctx:
            ctx_parts.append(app_ctx)
        full_msg = "\n\n".join(ctx_parts + [text]) if ctx_parts else text

        # Trim history to avoid very long context windows
        raw_history = list(self._history)
        if len(raw_history) > _MAX_HISTORY:
            raw_history = raw_history[-_TRIM_TO:]
            while raw_history and raw_history[0]["role"] != "user":
                raw_history = raw_history[1:]
        history_snap = raw_history
        self._history.append({"role": "user", "content": text})

        if actions is None:
            # This means setup_actions() was never called — show warning in chat
            self._add_bubble(
                "⚠ Dishy tools are not active. Restart the app to enable recipe saving and meal planning.",
                is_user=False,
            )

        if actions is not None:
            actions.clear_pending()

            def _tool_handler(name: str, inp: dict) -> str:
                # Push a status update to the typing indicator (thread-safe via queue)
                status = TOOL_STATUS_MESSAGES.get(name, "Working...")
                if self._typing_indicator is not None:
                    self._typing_indicator.update_status(status)
                result = actions.execute(name, inp)
                pending_tool_names.append(name)
                return result

            def _chat_fn():
                return _claude.chat_with_tools(full_msg, TOOLS, _tool_handler, history_snap)

            run_async(
                _chat_fn,
                on_result=lambda reply: self._on_reply(reply, pending_tool_names, actions),
                on_error=self._on_error,
            )
        else:
            run_async(
                _claude.chat, full_msg,
                history=history_snap,
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
                    summary = _MiniActionSummary(labels)
                    self._chat_layout.insertWidget(self._chat_layout.count() - 1, summary)

            # Show Dishy's text response (if any)
            cleaned = _clean(reply)
            if cleaned:
                self._history.append({"role": "assistant", "content": cleaned})
                self._add_bubble(cleaned, is_user=False)

            self._send_btn.setEnabled(True)
            QTimer.singleShot(60, lambda: self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            ))
        except Exception:
            pass

        # Trigger view refreshes after current event loop cycle (avoids widget lifecycle crashes)
        if actions is not None and actions.pending_refreshes and self._refresh_cb:
            refreshes = list(actions.pending_refreshes)
            QTimer.singleShot(200, lambda: self._safe_refresh(refreshes))

    def _safe_refresh(self, view_names: list):
        try:
            self._refresh_cb(view_names)
        except Exception:
            pass

    def _on_error(self, err: str):
        self._remove_typing_indicator()
        err_lower = err.lower()
        _is_auth = False
        if "credit balance" in err_lower or "too low" in err_lower:
            msg = "Anthropic credits are out. Top up at console.anthropic.com/settings/billing."
        elif "dishy_not_signed_in" in err_lower:
            msg = "Dishy couldn't connect — tap 'Sign Out Instead' to sign back in."
            _is_auth = True
        elif "authentication" in err_lower or "api_key" in err_lower or "401" in err_lower:
            msg = "Dishy couldn't authenticate — tap 'Sign Out Instead' to sign back in."
            _is_auth = True
        else:
            # Show the actual error so we can diagnose tool-related failures
            short = err.strip().splitlines()[-1] if err.strip() else err
            msg = f"Error: {short[:200]}"
        self._add_bubble(msg, is_user=False)
        self._send_btn.setEnabled(True)
        if _is_auth:
            try:
                from auth.session_manager import load_session
                stored = load_session() or {}
                email = stored.get("user", {}).get("email", "")
            except Exception:
                email = ""
            self.session_expired.emit(email)

    # ──────────────────────────────────────────── positioning

    def _reposition(self):
        pw = self.parent().width()
        ph = self.parent().height()

        if self._open:
            panel_x = pw - PANEL_W - MARGIN
            panel_y = ph - FAB_SIZE - GAP - PANEL_H - MARGIN
            self._panel.move(0, 0)
            self._fab.move(PANEL_W - FAB_SIZE, PANEL_H + GAP)
            self.setGeometry(panel_x, panel_y, PANEL_W, PANEL_H + GAP + FAB_SIZE)
        else:
            self._fab.move(0, 0)
            self.setGeometry(pw - FAB_SIZE - MARGIN, ph - FAB_SIZE - MARGIN,
                             FAB_SIZE, FAB_SIZE)

    # ──────────────────────────────────────────── theme

    def apply_theme(self, mode: str):
        """Update panel colors when theme changes."""
        self._close_panel()  # clear chat; next open rebuilds with new colors
        self._panel.setStyleSheet(
            "QWidget#dishy-panel {"
            f"  background: {theme_manager.c('#0e0e0e', '#ffffff')};"
            "  border-radius: 14px;"
            f"  border: 1.5px solid {theme_manager.c('rgba(255,255,255,0.08)', '#e0e0e0')};"
            "}"
        )
        self._panel_header.setStyleSheet(
            f"background: {theme_manager.c('qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(52,211,153,0.08),stop:1 rgba(52,211,153,0.03))', 'qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(52,211,153,0.07),stop:1 rgba(52,211,153,0.02))')};"
            " border-radius: 14px 14px 0 0;"
            f" border-bottom: 1px solid {theme_manager.c('rgba(255,255,255,0.07)', '#e4e4e4')};"
        )
        self._title_lbl.setStyleSheet(
            f"color: {theme_manager.c('#e0e0e0', '#1a1a1a')}; font-size: 14px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        self._page_badge.setStyleSheet(
            "color: #555555; font-size: 10px; font-weight: 600; letter-spacing: 0.5px;"
            f" background: {theme_manager.c('rgba(255,255,255,0.05)', '#f0f0f0')};"
            f" border: 1.5px solid {theme_manager.c('rgba(255,255,255,0.08)', '#e0e0e0')};"
            " border-radius: 5px; padding: 1px 7px;"
        )
        self._close_btn.setStyleSheet(
            f"QPushButton {{ color: {theme_manager.c('#888888', '#666666')}; font-size: 13px;"
            "  background: transparent; border: none; border-radius: 14px; }"
            f"QPushButton:hover {{ color: {theme_manager.c('#d0d0d0', '#111111')};"
            f" background: {theme_manager.c('#1e1e1e', '#e0e0e0')}; }}"
        )
        self._panel_footer.setStyleSheet(
            f"background: {theme_manager.c('#0a0a0a', '#f8f8f8')};"
            " border-radius: 0 0 14px 14px;"
            f" border-top: 1px solid {theme_manager.c('rgba(255,255,255,0.06)', '#e4e4e4')};"
        )
        self._send_btn.setStyleSheet(
            "QPushButton { background: #34d399; border-radius: 8px; border: none; }"
            "QPushButton:hover { background: #4ae3a8; }"
            f"QPushButton:disabled {{ background: {theme_manager.c('#1a1a1a', '#d5d5d5')}; }}"
        )

    # ──────────────────────────────────────────── event filter

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self._reposition()
        return False
