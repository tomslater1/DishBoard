import os
import warnings
from datetime import datetime
from utils.version import APP_VERSION
import qtawesome as qta
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QStackedWidget, QStatusBar,
)
from PySide6.QtCore import (
    Qt, QSize, QPropertyAnimation, QParallelAnimationGroup,
    QEasingCurve, QAbstractAnimation, Signal,
)
from PySide6.QtGui import QGuiApplication, QPixmap

from models.database import Database
from api.claude_ai import ClaudeAI
from utils.workers import run_async

_BASE_DIR  = os.path.dirname(__file__)
_ICON_PATH = os.path.join(_BASE_DIR, "assets", "icons", "DishBoard-darkicon.png")

from views.my_kitchen import MyKitchenView
from views.my_kitchen_coming_soon import MyKitchenComingSoonView
from views.recipes import RecipesView
from views.meal_planner import MealPlannerView
from views.nutrition import NutritionView
from views.shopping_list import ShoppingListView
from views.dishy import DishyView
from views.help import HelpView
from views.settings import SettingsView
from widgets.dishy_bubble import DishyBubble
from widgets.sync_indicator import SyncIndicator
from api.dishy_tools import DishyActions
from utils.theme import manager as theme_manager

SIDEBAR_EXPANDED = 220
SIDEBAR_COLLAPSED = 64
ACCENT = "#ff6b35"
ICON_COLOUR = "#555555"

NAV_ITEMS = [
    ("fa5s.home",          "Home",           "#ff6b35"),
    ("fa5s.book-open",     "Recipes",        "#7c6af7"),
    ("fa5s.calendar-alt",  "Meal Planner",   "#4caf8a"),
    ("fa5s.heartbeat",     "Nutrition",      "#e05c7a"),
    ("fa5s.box-open",      "My Kitchen",     "#e8924a"),
    ("fa5s.shopping-cart", "Shopping List",  "#f0a500"),
    ("fa5s.robot",         "Dishy",          "#34d399"),
]

class NavButton(QPushButton):
    def __init__(self, icon_name: str, label: str, active_color: str | None = None, parent=None):
        super().__init__(parent)
        self._label = label
        self._icon_name = icon_name
        self._active_color = active_color or ACCENT
        self.setObjectName("nav-btn")
        self.setCheckable(True)
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Per-section colour for checked state (overrides global QSS)
        c = self._active_color
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        self.setStyleSheet(
            f"QPushButton#nav-btn:checked {{"
            f" background-color: rgba({r},{g},{b},0.12);"
            f" color: {c}; font-weight: 600;"
            f" border-left: 2px solid {c}; padding-left: 12px;"
            f"}}"
        )
        self._refresh_icon()
        self.set_expanded(True)
        self.toggled.connect(lambda _: self._refresh_icon())

    def _refresh_icon(self):
        color = self._active_color if self.isChecked() else ICON_COLOUR
        self.setIcon(qta.icon(self._icon_name, color=color))
        self.setIconSize(QSize(17, 17))

    def set_expanded(self, expanded: bool):
        self.setText(f"   {self._label}" if expanded else "")
        self.setToolTip("" if expanded else self._label)


class MainWindow(QMainWindow):
    sign_in_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DishBoard")
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)
        self._sidebar_expanded = True
        self._nav_history: list[int] = []
        self._cloud_sync_service = None   # set by set_sync_service() after login
        self._db = Database()
        self._db.connect()
        self._claude = ClaudeAI()
        self._centre_on_screen()
        self._build_ui()
        self._load_sidebar_extras()

    def _centre_on_screen(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move((screen.width() - 1200) // 2, (screen.height() - 800) // 2)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._sidebar_widget = self._build_sidebar()
        root.addWidget(self._sidebar_widget)
        root.addWidget(self._build_content_wrapper())

        status = QStatusBar()
        status.showMessage("DishBoard by Tom Slater")
        self.setStatusBar(status)

    # ---------------------------------------------------------------- sidebar

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(SIDEBAR_EXPANDED)
        sidebar.setMaximumWidth(SIDEBAR_EXPANDED)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(0)

        # Header: toggle row + large centred logo + app name
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        h_vlay = QVBoxLayout(header)
        h_vlay.setContentsMargins(0, 8, 0, 8)
        h_vlay.setSpacing(0)

        # Top row: toggle button aligned right
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 10, 0)
        toggle_row.setSpacing(0)
        toggle_row.addStretch()
        toggle_btn = QPushButton()
        toggle_btn.setObjectName("toggle-btn")
        toggle_btn.setIcon(qta.icon("fa5s.bars", color=ICON_COLOUR))
        toggle_btn.setIconSize(QSize(15, 15))
        toggle_btn.setFixedSize(32, 32)
        toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle_btn.clicked.connect(self._toggle_sidebar)
        toggle_row.addWidget(toggle_btn)
        h_vlay.addLayout(toggle_row)

        h_vlay.addSpacing(6)

        # Large logo — centred in its own row
        self._logo_icon_lbl = QLabel()
        self._logo_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        _icon_src = os.path.join(_BASE_DIR, "assets", "icons", "Dishboard-orange.png")
        if os.path.exists(_icon_src):
            px = QPixmap(_icon_src).scaled(
                72, 72,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._logo_icon_lbl.setPixmap(px)
        self._logo_icon_lbl.setStyleSheet("background: transparent;")
        self._logo_icon_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logo_icon_lbl.mousePressEvent = lambda _e: self._on_nav_clicked(0)
        h_vlay.addWidget(self._logo_icon_lbl)

        h_vlay.addSpacing(8)

        # App name below the logo, centred
        self._logo_lbl = QLabel("DishBoard")
        self._logo_lbl.setObjectName("app-logo-label")
        self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._logo_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logo_lbl.mousePressEvent = lambda _e: self._on_nav_clicked(0)
        h_vlay.addWidget(self._logo_lbl)

        h_vlay.addSpacing(10)
        layout.addWidget(header)

        accent_line = QWidget()
        accent_line.setObjectName("sidebar-accent")
        accent_line.setFixedHeight(2)
        layout.addSpacing(2)
        layout.addWidget(accent_line)
        layout.addSpacing(10)

        div = QWidget()
        div.setObjectName("sidebar-divider")
        div.setFixedHeight(1)
        layout.addWidget(div)
        layout.addSpacing(10)

        nav_lbl = QLabel("NAVIGATE")
        nav_lbl.setObjectName("sidebar-section-label")
        layout.addWidget(nav_lbl)
        layout.addSpacing(6)

        self._nav_buttons: list[NavButton] = []
        for i, (icon_name, label, active_color) in enumerate(NAV_ITEMS):
            btn = NavButton(icon_name, label, active_color)
            btn.clicked.connect(lambda _, idx=i: self._on_nav_clicked(idx))
            layout.addWidget(btn)
            layout.addSpacing(4)
            self._nav_buttons.append(btn)

        layout.addSpacing(12)

        # ── Sidebar extras (tip + recent recipes) ────────────────────────────
        extras_div = QWidget()
        extras_div.setObjectName("sidebar-divider")
        extras_div.setFixedHeight(1)
        layout.addWidget(extras_div)
        layout.addSpacing(8)

        self._sidebar_extras = self._build_sidebar_extras()
        layout.addWidget(self._sidebar_extras)

        layout.addStretch()

        # Sync status indicator — hidden until user is logged in
        self._sync_indicator = SyncIndicator()
        self._sync_indicator.setVisible(False)
        layout.addWidget(self._sync_indicator)

        bottom_div = QWidget()
        bottom_div.setObjectName("sidebar-divider")
        bottom_div.setFixedHeight(1)
        layout.addWidget(bottom_div)
        layout.addSpacing(6)

        self._guide_btn = NavButton("fa5s.question-circle", "How to use")
        self._guide_btn.clicked.connect(self._on_guide_clicked)
        layout.addWidget(self._guide_btn)

        self._settings_btn = NavButton("fa5s.cog", "Settings")
        self._settings_btn.clicked.connect(self._on_settings_clicked)
        layout.addWidget(self._settings_btn)

        layout.addSpacing(6)

        bottom_div2 = QWidget()
        bottom_div2.setObjectName("sidebar-divider")
        bottom_div2.setFixedHeight(1)
        layout.addWidget(bottom_div2)
        layout.addSpacing(10)

        now = datetime.now()
        self._sidebar_date_lbl = QLabel(now.strftime("%a, %d %b %Y"))
        self._sidebar_date_lbl.setObjectName("sidebar-date-lbl")
        layout.addWidget(self._sidebar_date_lbl)

        # Compact date shown only when sidebar is collapsed (icon-only mode)
        self._sidebar_date_compact = QLabel(now.strftime("%d\n%b").upper())
        self._sidebar_date_compact.setObjectName("sidebar-date-lbl")
        self._sidebar_date_compact.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sidebar_date_compact.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {theme_manager.c('#888888', '#666666')};"
            " line-height: 1.3; background: transparent; padding: 0;"
        )
        self._sidebar_date_compact.setVisible(False)
        layout.addWidget(self._sidebar_date_compact)
        layout.addSpacing(4)

        self._version_lbl = QLabel("DishBoard by Tom Slater")
        self._version_lbl.setObjectName("sidebar-version-lbl")
        layout.addWidget(self._version_lbl)
        layout.addSpacing(2)
        self._ver_num_lbl = QLabel(APP_VERSION)
        self._ver_num_lbl.setObjectName("sidebar-version-lbl")
        layout.addWidget(self._ver_num_lbl)
        layout.addSpacing(8)

        self._nav_buttons[0].setChecked(True)
        return sidebar

    # --------------------------------------------------------- sidebar extras

    def _build_sidebar_extras(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(container)
        vl.setContentsMargins(10, 0, 10, 0)
        vl.setSpacing(10)

        # ── Dishy's Tip card ──────────────────────────────────────────────
        tip_card = QWidget()
        tip_card.setStyleSheet(
            "background-color: rgba(52,211,153,0.06); border-radius: 8px;"
            " border: 1px solid rgba(52,211,153,0.15);"
        )
        tip_layout = QVBoxLayout(tip_card)
        tip_layout.setContentsMargins(10, 8, 10, 8)
        tip_layout.setSpacing(4)

        tip_hdr = QHBoxLayout()
        tip_hdr.setSpacing(5)
        robot_lbl = QLabel()
        robot_lbl.setPixmap(qta.icon("fa5s.robot", color="#34d399").pixmap(QSize(11, 11)))
        robot_lbl.setStyleSheet("background: transparent; border: none;")
        tip_title = QLabel("Dishy's Tip")
        tip_title.setStyleSheet(
            "background: transparent; border: none; color: #34d399;"
            " font-size: 10px; font-weight: 700; letter-spacing: 0.5px;"
        )
        tip_hdr.addWidget(robot_lbl)
        tip_hdr.addWidget(tip_title)
        tip_hdr.addStretch()
        tip_layout.addLayout(tip_hdr)

        self._tip_lbl = QLabel("Loading tip…")
        self._tip_lbl.setWordWrap(True)
        self._tip_lbl.setStyleSheet(
            f"background: transparent; border: none;"
            f" color: {theme_manager.c('#888888', '#666666')}; font-size: 13px; line-height: 1.4;"
        )
        tip_layout.addWidget(self._tip_lbl)
        vl.addWidget(tip_card)

        return container

    def _load_sidebar_extras(self):
        self._refresh_daily_tip()

    def _refresh_daily_tip(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if (self._db.get_setting("daily_tip_date") == today
                and self._db.get_setting("daily_tip")):
            self._tip_lbl.setText(self._db.get_setting("daily_tip"))
            return
        self._tip_lbl.setText("Loading tip…")
        run_async(
            self._claude.daily_tip,
            on_result=self._on_tip_result,
            on_error=self._on_tip_error,
        )

    def _on_tip_error(self, err: str):
        if "credit balance" in err.lower() or "too low" in err.lower():
            self._tip_lbl.setText("Add Anthropic credits to get daily tips.")
        else:
            self._tip_lbl.setText("Tip unavailable.")

    def _on_tip_result(self, tip: str):
        today = datetime.now().strftime("%Y-%m-%d")
        self._db.set_setting("daily_tip", tip)
        self._db.set_setting("daily_tip_date", today)
        self._tip_lbl.setText(tip)


    # ------------------------------------------------------------- content

    def _build_content_wrapper(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("content-area")
        vl = QVBoxLayout(wrapper)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # Back-navigation bar — hidden until there is history
        self._back_bar = QWidget()
        self._back_bar.setObjectName("back-bar")
        self._back_bar.setStyleSheet(
            f"background-color: {theme_manager.c('#0a0a0a', '#ebebeb')};"
            f" border-bottom: 1px solid {theme_manager.c('#161616', '#cccccc')};"
        )
        self._back_bar.setFixedHeight(62)
        bl = QHBoxLayout(self._back_bar)
        bl.setContentsMargins(14, 0, 14, 0)
        bl.setSpacing(0)

        self._back_btn = QPushButton()
        self._back_btn.setObjectName("ghost-btn")
        self._back_btn.setIcon(qta.icon("fa5s.arrow-left", color="#888888"))
        self._back_btn.setIconSize(QSize(14, 14))
        self._back_btn.setText("   Back")
        self._back_btn.setFixedHeight(38)
        self._back_btn.setMinimumWidth(90)
        self._back_btn.clicked.connect(self._go_back)

        bl.addWidget(self._back_btn)
        bl.addStretch()
        self._back_bar.setVisible(False)
        vl.addWidget(self._back_bar)

        # Pages
        self._stack = QStackedWidget()
        self._shopping_view      = ShoppingListView()
        self._settings_view      = SettingsView()
        self._recipes_view       = RecipesView()
        self._meal_planner_view  = MealPlannerView(
            navigate_to=self._on_nav_clicked,
            shopping_view=self._shopping_view,
        )
        self._dishy_view     = DishyView(db=self._db)
        self._nutrition_view = NutritionView(navigate_to=self._on_nav_clicked)
        views = [
            MyKitchenView(navigate_to=self._on_nav_clicked,
                          trigger_dishy=self._trigger_dishy_prompt),  # 0
            self._recipes_view,                                  # 1
            self._meal_planner_view,                             # 2
            self._nutrition_view,                                # 3
            MyKitchenComingSoonView(),                           # 4
            self._shopping_view,                                 # 5
            self._dishy_view,                                    # 6
            HelpView(navigate_to=self._on_nav_clicked),          # 7
            self._settings_view,                                 # 8
        ]
        for view in views:
            self._stack.addWidget(view)

        # Wire meal planner + recipes → instant nutrition refresh on explicit saves
        self._meal_planner_view.set_nutrition_refresh(self._nutrition_view.refresh)
        self._recipes_view.set_nutrition_refresh(self._nutrition_view.refresh)

        # Wire cloud sync callbacks — views call these after every data mutation
        self._meal_planner_view.set_sync_fn(self._trigger_cloud_sync)
        self._recipes_view.set_sync_fn(self._trigger_cloud_sync)
        self._shopping_view.set_sync_fn(self._trigger_cloud_sync)
        self._dishy_view.set_sync_fn(self._trigger_cloud_sync)
        self._settings_view.set_sync_fn(self._trigger_cloud_sync)


        # Wire Settings data management buttons so clearing a section also refreshes the view
        self._settings_view.set_data_management_callbacks(
            meal_plan_fn=self._meal_planner_view.refresh,
            shopping_fn=self._shopping_view.refresh,
            recipes_fn=self._recipes_view.refresh,
        )

        vl.addWidget(self._stack, 1)

        # Floating Dishy chat bubble — parented to the wrapper, auto-repositions
        self._dishy_bubble = DishyBubble(wrapper)
        self._dishy_bubble.raise_()

        # Wire Dishy tool-calling: actions executor + cross-view refresh
        _db = Database()
        _db.connect()
        _actions = DishyActions(_db)
        self._dishy_bubble.setup_actions(_actions, self._on_dishy_refresh)
        self._dishy_view.setup_actions(_actions, self._on_dishy_refresh)

        # Give each view a reference to the bubble's trigger_action so their
        # per-tab "Ask Dishy" buttons can open the panel with a pre-set prompt.
        self._recipes_view.set_ask_dishy(self._dishy_bubble.trigger_action)
        self._meal_planner_view.set_ask_dishy(self._dishy_bubble.trigger_action)
        self._shopping_view.set_ask_dishy(self._dishy_bubble.trigger_action)

        # Wire theme changes so every view can update itself
        theme_manager.theme_changed.connect(self._on_theme_changed)

        return wrapper

    # --------------------------------------------------------------- navigation

    _PAGE_NAMES = ["Home", "Recipes", "Meal Planner",
                   "Nutrition", "My Kitchen", "Shopping List", "Dishy", "How to use", "Settings"]

    def _on_nav_clicked(self, index: int):
        current = self._stack.currentIndex()
        if current != index:
            self._nav_history.append(current)
            self._back_bar.setVisible(True)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
        self._guide_btn.setChecked(False)
        self._settings_btn.setChecked(False)
        self._stack.setCurrentIndex(index)
        self._dishy_bubble.set_page(self._PAGE_NAMES[index])
        # Refresh the view being shown so it always has up-to-date data
        view = self._stack.widget(index)
        if hasattr(view, "refresh"):
            try:
                view.refresh()
            except Exception:
                pass

    def _on_guide_clicked(self):
        current = self._stack.currentIndex()
        if current != 7:
            self._nav_history.append(current)
            self._back_bar.setVisible(True)
        for btn in self._nav_buttons:
            btn.setChecked(False)
        self._guide_btn.setChecked(True)
        self._settings_btn.setChecked(False)
        self._stack.setCurrentIndex(7)
        self._dishy_bubble.set_page("How to use")

    def _on_settings_clicked(self):
        current = self._stack.currentIndex()
        if current != 8:
            self._nav_history.append(current)
            self._back_bar.setVisible(True)
        for btn in self._nav_buttons:
            btn.setChecked(False)
        self._guide_btn.setChecked(False)
        self._settings_btn.setChecked(True)
        self._stack.setCurrentIndex(8)
        self._dishy_bubble.set_page("Settings")

    def _go_back(self):
        if not self._nav_history:
            return
        prev = self._nav_history.pop()
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == prev)
        self._guide_btn.setChecked(prev == 7)
        self._settings_btn.setChecked(prev == 8)
        self._stack.setCurrentIndex(prev)
        self._back_bar.setVisible(bool(self._nav_history))
        self._dishy_bubble.set_page(self._PAGE_NAMES[prev])

    def _toggle_sidebar(self):
        expanded = self._sidebar_expanded
        start_w = SIDEBAR_EXPANDED if expanded else SIDEBAR_COLLAPSED
        end_w   = SIDEBAR_COLLAPSED if expanded else SIDEBAR_EXPANDED

        if expanded:
            # Collapsing — hide expanded labels, show compact date
            for btn in self._nav_buttons:
                btn.set_expanded(False)
            self._guide_btn.set_expanded(False)
            self._settings_btn.set_expanded(False)
            self._logo_lbl.setVisible(False)
            self._logo_icon_lbl.setVisible(False)
            self._sidebar_date_lbl.setVisible(False)
            self._version_lbl.setVisible(False)
            self._ver_num_lbl.setVisible(False)
            self._sidebar_date_compact.setVisible(True)
            self._sidebar_extras.setVisible(False)
            self._sync_indicator.set_expanded(False)
        grp = QParallelAnimationGroup(self)
        for prop in (b"minimumWidth", b"maximumWidth"):
            anim = QPropertyAnimation(self._sidebar_widget, prop)
            anim.setDuration(220)
            anim.setStartValue(start_w)
            anim.setEndValue(end_w)
            anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            grp.addAnimation(anim)

        if not expanded:
            def _on_expand_done():
                for btn in self._nav_buttons:
                    btn.set_expanded(True)
                self._guide_btn.set_expanded(True)
                self._settings_btn.set_expanded(True)
                self._logo_lbl.setVisible(True)
                self._logo_icon_lbl.setVisible(True)
                self._sidebar_date_lbl.setVisible(True)
                self._version_lbl.setVisible(True)
                self._ver_num_lbl.setVisible(True)
                self._sidebar_date_compact.setVisible(False)
                self._sidebar_extras.setVisible(True)
                self._sync_indicator.set_expanded(True)
            grp.finished.connect(_on_expand_done)

        grp.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._sidebar_expanded = not expanded

    def _trigger_dishy_prompt(self, text: str):
        """Navigate to DishyView and auto-send a prompt (called from Home)."""
        self._on_nav_clicked(6)
        self._dishy_view.trigger_prompt(text)

    # --------------------------------------------------------------- Dishy refresh

    def _on_dishy_refresh(self, view_names: list):
        """Called on the main thread after Dishy tool calls complete."""
        try:
            if "recipes" in view_names:
                self._recipes_view.refresh()
        except Exception:
            pass
        try:
            if "meal_planner" in view_names:
                self._meal_planner_view.refresh()
        except Exception:
            pass
        try:
            if "shopping_list" in view_names:
                self._shopping_view.refresh()
        except Exception:
            pass
        try:
            if "nutrition" in view_names:
                self._nutrition_view.refresh()
        except Exception:
            pass
        # Always refresh Home so stats/cards reflect any Dishy changes
        try:
            home_view = self._stack.widget(0)
            if hasattr(home_view, "refresh"):
                home_view.refresh()
        except Exception:
            pass
        # Push data changes to cloud immediately
        self._trigger_cloud_sync()

    # --------------------------------------------------------------- theme

    def _on_theme_changed(self, mode: str):
        """Notify every view that supports live theme updates."""
        self._back_bar.setStyleSheet(
            f"background-color: {theme_manager.c('#0a0a0a', '#ebebeb')};"
            f" border-bottom: 1px solid {theme_manager.c('#161616', '#cccccc')};"
        )
        self._sidebar_date_compact.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {theme_manager.c('#888888', '#666666')};"
            " line-height: 1.3; background: transparent; padding: 0;"
        )
        self._tip_lbl.setStyleSheet(
            f"background: transparent; border: none;"
            f" color: {theme_manager.c('#888888', '#666666')}; font-size: 13px; line-height: 1.4;"
        )
        for i in range(self._stack.count()):
            view = self._stack.widget(i)
            if hasattr(view, "apply_theme"):
                view.apply_theme(mode)
        self._dishy_bubble.apply_theme(mode)

    # ── Cloud sync public API ─────────────────────────────────────────────────

    def _trigger_cloud_sync(self) -> None:
        """Trigger an immediate cloud sync after any data mutation. Safe if not logged in."""
        try:
            if self._cloud_sync_service is not None:
                self._cloud_sync_service.sync_now()
        except Exception:
            pass

    def set_sync_service(self, service) -> None:
        """Wire a CloudSyncBackgroundService to the sidebar sync indicator."""
        self._cloud_sync_service = service
        self._sync_indicator.setVisible(True)
        self._sync_indicator.set_state("syncing")
        service.sync_started.connect(
            lambda: self._sync_indicator.set_state("syncing")
        )
        # Always show "live" after a successful sync — the app uses Supabase cloud
        service.sync_finished.connect(
            lambda _p, _r: self._sync_indicator.set_state("live")
        )
        service.sync_error.connect(
            lambda _e: self._sync_indicator.set_state("error")
        )
        service.realtime_connected.connect(self._on_realtime_connected)
        service.realtime_disconnected.connect(self._on_realtime_disconnected)
        service.remote_change_received.connect(self._on_remote_change_received)

    def _on_realtime_connected(self) -> None:
        self._sync_indicator.set_state("live")

    def _on_realtime_disconnected(self) -> None:
        # Keep showing live — Supabase cloud connection is still active via polling
        pass

    def _on_remote_change_received(self, table: str) -> None:
        """Refresh the relevant view after a remote Realtime change (no cloud push)."""
        name_map = {
            "recipes":        "recipes",
            "meal_plans":     "meal_planner",
            "shopping_items": "shopping_list",
            "nutrition_logs": "nutrition",
        }
        view_name = name_map.get(table)
        try:
            if view_name == "recipes":
                self._recipes_view.refresh()
            elif view_name == "meal_planner":
                self._meal_planner_view.refresh()
            elif view_name == "shopping_list":
                self._shopping_view.refresh()
            elif view_name == "nutrition":
                self._nutrition_view.refresh()
        except Exception:
            pass
        # Always refresh Home
        try:
            home_view = self._stack.widget(0)
            if hasattr(home_view, "refresh"):
                home_view.refresh()
        except Exception:
            pass

    def set_offline_mode(self) -> None:
        """Legacy alias — calls set_sync_unavailable."""
        self.set_sync_unavailable()

    def set_sync_unavailable(self) -> None:
        """Show a sync-unavailable indicator (network down, still signed in)."""
        self._sync_indicator.setVisible(True)
        self._sync_indicator.set_state("offline")

    def set_account_user(self, user: dict | None, sync_service) -> None:
        """Pass account info to the Settings > Account page."""
        self._settings_view.set_account_info(user, sync_service)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                self._settings_view.sign_in_requested.disconnect()
            except Exception:
                pass
        self._settings_view.sign_in_requested.connect(self.sign_in_requested.emit)

    # ── Tour target widgets ────────────────────────────────────────────────────

    @property
    def tour_targets(self) -> dict:
        """Return a dict of named widgets for the app tour spotlight system."""
        # nav_container: the widget that holds all nav buttons
        nav_container = self._sidebar_widget
        # help_settings_area: the guide + settings buttons container area
        # We expose the guide button widget itself as the anchor
        help_settings_area = self._guide_btn
        # content_area: the inner QStackedWidget (main content)
        content_area = self._stack
        return {
            "sidebar_nav_area": nav_container,
            "help_settings_area": help_settings_area,
            "content_area": content_area,
        }
