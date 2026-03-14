import json
import os
import sys
import warnings
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from utils.version import APP_VERSION
import qtawesome as qta
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QStackedWidget, QStatusBar, QApplication,
)
from PySide6.QtCore import (
    Qt, QSize, QPropertyAnimation, QParallelAnimationGroup,
    QEasingCurve, QAbstractAnimation, QTimer, Signal, Property,
)
from PySide6.QtGui import QGuiApplication, QKeySequence, QPixmap, QShortcut

from models.database import Database
from utils.data_service import get_db

_BASE_DIR  = os.path.dirname(__file__)
_ICON_PATH = os.path.join(_BASE_DIR, "assets", "icons", "DishBoard-darkicon.png")

from views.my_kitchen import MyKitchenView
from views.my_kitchen_storage import MyKitchenStorageView
from views.recipes import RecipesView
from views.meal_planner import MealPlannerView
from views.nutrition import NutritionView
from views.shopping_list import ShoppingListView
from views.dishy import DishyView
from views.help import HelpView
from views.settings import SettingsView
from widgets.dishy_bubble import DishyBubble
from widgets.command_palette import (
    CommandPaletteDialog,
    PaletteEntry,
    PaletteField,
    QuickAddForm,
    rank_entries,
)
from widgets.sync_indicator import SyncIndicator
from api.dishy_tools import DishyActions
from utils.animation import slide_in_widget
from utils.recipe_search import filter_and_rank_saved_recipes
from utils.service_hub import registry as service_registry
from utils.system_visibility import SystemVisibilityService
from utils.theme import manager as theme_manager

SIDEBAR_EXPANDED = 220
SIDEBAR_COLLAPSED = 64
ACCENT = "#ff6b35"


def _inactive_icon_color() -> str:
    return theme_manager.c("#98938c", "#665f58")

NAV_ITEMS = [
    ("fa5s.home",          "Home",           ACCENT),
    ("fa5s.book-open",     "Recipes",        ACCENT),
    ("fa5s.calendar-alt",  "Meal Planner",   ACCENT),
    ("fa5s.heartbeat",     "Nutrition",      ACCENT),
    ("fa5s.box-open",      "My Kitchen",     ACCENT),
    ("fa5s.shopping-cart", "Shopping List",  ACCENT),
    ("fa5s.robot",         "Dishy",          ACCENT),
]

class NavButton(QPushButton):
    def __init__(self, icon_name: str, label: str, active_color: str | None = None, parent=None):
        super().__init__(parent)
        self._label = label
        self._icon_name = icon_name
        self._active_color = active_color or ACCENT
        self._icon_px = 16
        self._icon_anim: QPropertyAnimation | None = None
        self.setObjectName("nav-btn")
        self.setCheckable(True)
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Per-section colour for checked state (overrides global QSS)
        c = self._active_color
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        self.setStyleSheet(
            f"QPushButton#nav-btn:checked {{"
            f" background-color: rgba({r},{g},{b},0.10);"
            f" color: {c}; font-weight: 600;"
            f" border-left: 2px solid {c}; padding-left: 14px;"
            f"}}"
        )
        self._refresh_icon()
        self.set_expanded(True)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool):
        self._refresh_icon()
        self._animate_icon_size(17 if checked else 16)

    def _get_icon_px(self) -> int:
        return int(self._icon_px)

    def _set_icon_px(self, px: int):
        self._icon_px = max(14, min(20, int(px)))
        self.setIconSize(QSize(self._icon_px, self._icon_px))

    iconPx = Property(int, _get_icon_px, _set_icon_px)

    def _animate_icon_size(self, target: int):
        start = self._get_icon_px()
        target = int(target)
        if start == target:
            return
        if self._icon_anim is not None:
            try:
                self._icon_anim.stop()
            except Exception:
                pass
        anim = QPropertyAnimation(self, b"iconPx", self)
        anim.setDuration(130)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._icon_anim = anim
        anim.finished.connect(lambda: setattr(self, "_icon_anim", None))
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _refresh_icon(self):
        color = self._active_color if self.isChecked() else _inactive_icon_color()
        self.setIcon(qta.icon(self._icon_name, color=color))
        self.setIconSize(QSize(self._icon_px, self._icon_px))

    def enterEvent(self, event):
        super().enterEvent(event)
        self._animate_icon_size(18 if self.isChecked() else 17)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._animate_icon_size(17 if self.isChecked() else 16)

    def set_expanded(self, expanded: bool):
        self.setText(f"   {self._label}" if expanded else "")
        self.setToolTip("" if expanded else self._label)


class MainWindow(QMainWindow):
    sign_in_requested = Signal()
    sign_out_requested = Signal()
    session_expired   = Signal(str)   # emits user email when Dishy session expires

    def __init__(self, db: Database | None = None):
        super().__init__()
        self.setWindowTitle("DishBoard")
        self.resize(1200, 800)
        self.setMinimumSize(780, 520)
        self._sidebar_expanded = True
        self._auto_collapsed = False      # True when sidebar was collapsed by window resize
        self._in_resize_toggle = False    # guard against re-entrant toggle during resize
        self._nav_history: list[int] = []
        self._cloud_sync_service = None   # set by set_sync_service() after login
        self._meal_deduction_service = None
        self._page_anim = None
        self._db = db or get_db()
        self._palette_command_entries: list[PaletteEntry] = []
        self._palette_quick_add_entries: list[PaletteEntry] = []
        self._last_palette_query = ""
        self._palette_shortcuts: list[QShortcut] = []
        self._visibility_service = SystemVisibilityService(self._db, parent=self)
        service_registry.register("visibility", self._visibility_service)
        self._centre_on_screen()
        self._build_ui()

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
        self._content_wrapper = self._build_content_wrapper()
        root.addWidget(self._content_wrapper)

        status = QStatusBar()
        status.showMessage("DishBoard by Tom Slater")
        self.setStatusBar(status)
        self._build_command_palette()
        self._setup_command_palette_shortcuts()

    # ---------------------------------------------------------------- sidebar

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(SIDEBAR_EXPANDED)
        sidebar.setMaximumWidth(SIDEBAR_EXPANDED)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(0)

        # Store icon path for use during collapse/expand
        self._icon_src_path = os.path.join(_BASE_DIR, "assets", "icons", "Dishboard-orange.png")

        # Header: toggle row + logo + app name
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        h_vlay = QVBoxLayout(header)
        h_vlay.setContentsMargins(0, 6, 0, 6)
        h_vlay.setSpacing(0)

        # Top row: toggle button aligned right
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 10, 0)
        toggle_row.setSpacing(0)
        toggle_row.addStretch()
        self._toggle_btn = QPushButton()
        self._toggle_btn.setObjectName("toggle-btn")
        self._toggle_btn.setIcon(qta.icon("fa5s.bars", color=_inactive_icon_color()))
        self._toggle_btn.setIconSize(QSize(15, 15))
        self._toggle_btn.setFixedSize(32, 32)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_sidebar)
        toggle_row.addWidget(self._toggle_btn)
        h_vlay.addLayout(toggle_row)

        h_vlay.addSpacing(4)

        # Logo icon — always visible; scaled down when collapsed
        self._logo_icon_lbl = QLabel()
        self._logo_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        if os.path.exists(self._icon_src_path):
            px = QPixmap(self._icon_src_path).scaled(
                52, 52,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._logo_icon_lbl.setPixmap(px)
        self._logo_icon_lbl.setStyleSheet("background: transparent;")
        self._logo_icon_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logo_icon_lbl.mousePressEvent = lambda _e: self._on_nav_clicked(0)
        h_vlay.addWidget(self._logo_icon_lbl)

        h_vlay.addSpacing(5)

        # App name below the logo, centred
        self._logo_lbl = QLabel("DishBoard")
        self._logo_lbl.setObjectName("app-logo-label")
        self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._logo_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logo_lbl.mousePressEvent = lambda _e: self._on_nav_clicked(0)
        h_vlay.addWidget(self._logo_lbl)

        h_vlay.addSpacing(8)
        layout.addWidget(header)

        accent_line = QWidget()
        accent_line.setObjectName("sidebar-accent")
        accent_line.setFixedHeight(2)
        layout.addSpacing(2)
        layout.addWidget(accent_line)
        layout.addSpacing(8)

        div = QWidget()
        div.setObjectName("sidebar-divider")
        div.setFixedHeight(1)
        layout.addWidget(div)
        layout.addSpacing(8)

        self._nav_buttons: list[NavButton] = []
        for i, (icon_name, label, active_color) in enumerate(NAV_ITEMS):
            btn = NavButton(icon_name, label, active_color)
            btn.clicked.connect(lambda _, idx=i: self._on_nav_clicked(idx))
            layout.addWidget(btn)
            layout.addSpacing(4)
            self._nav_buttons.append(btn)

        layout.addSpacing(8)
        layout.addStretch()

        # Sync status indicator kept off-layout; sync still runs, but the sidebar no longer shows it.
        self._sync_indicator = SyncIndicator()
        self._sync_indicator.setVisible(False)

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
        self._back_bar.setStyleSheet(self._back_bar_style())
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
        self._back_btn.setStyleSheet(self._back_btn_style())
        self._back_btn.clicked.connect(self._go_back)

        bl.addWidget(self._back_btn)
        bl.addStretch()
        self._back_bar.setVisible(False)
        vl.addWidget(self._back_bar)

        # Pages
        self._stack = QStackedWidget()
        self._shopping_view      = ShoppingListView(db=self._db)
        self._settings_view      = SettingsView(db=self._db)
        self._recipes_view       = RecipesView(db=self._db)
        self._meal_planner_view  = MealPlannerView(
            navigate_to=self._on_nav_clicked,
            shopping_view=self._shopping_view,
            db=self._db,
        )
        self._dishy_view     = DishyView(db=self._db)
        self._nutrition_view = NutritionView(navigate_to=self._on_nav_clicked, db=self._db)
        self._my_kitchen_storage_view = MyKitchenStorageView(
            db=self._db,
            trigger_sync=self._trigger_cloud_sync,
            ask_dishy_fn=None,  # wired after bubble is created
            navigate_to=self._on_nav_clicked,
        )
        views = [
            MyKitchenView(db=self._db,
                          navigate_to=self._on_nav_clicked,
                          trigger_dishy=self._trigger_dishy_prompt),  # 0
            self._recipes_view,                                  # 1
            self._meal_planner_view,                             # 2
            self._nutrition_view,                                # 3
            self._my_kitchen_storage_view,                       # 4
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
        self._settings_view.set_visibility_service(self._visibility_service)

        # Wire Shopping List Live Shop → My Kitchen refresh + navigation
        self._shopping_view.set_notify_my_kitchen_fn(
            lambda: self._my_kitchen_storage_view.refresh()
        )
        self._shopping_view.set_navigate_to_fn(self._on_nav_clicked)

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
        _actions = DishyActions(self._db)
        self._dishy_bubble.setup_actions(_actions, self._on_dishy_refresh)
        self._dishy_view.setup_actions(_actions, self._on_dishy_refresh)

        # Propagate session-expiry events upward so DishBoard.py can show ReauthDialog
        self._dishy_bubble.session_expired.connect(self.session_expired)
        self._dishy_view.session_expired.connect(self.session_expired)

        # Give each view a reference to the bubble's trigger_action so their
        # per-tab "Ask Dishy" buttons can open the panel with a pre-set prompt.
        self._recipes_view.set_ask_dishy(self._dishy_bubble.trigger_action)
        self._meal_planner_view.set_ask_dishy(self._dishy_bubble.trigger_action)
        self._shopping_view.set_ask_dishy(self._dishy_bubble.trigger_action)
        # Wire My Kitchen's Ask Dishy button (bubble not available at view creation time)
        self._my_kitchen_storage_view._ask_dishy_fn = self._dishy_bubble.trigger_action

        # Wire theme changes so every view can update itself
        theme_manager.theme_changed.connect(self._on_theme_changed)
        return wrapper

    def _build_command_palette(self) -> None:
        self._command_palette = CommandPaletteDialog(self)
        self._command_palette.query_changed.connect(self._refresh_palette_results)
        self._command_palette.entry_activated.connect(self._on_palette_entry_activated)
        self._command_palette.form_action_requested.connect(self._on_palette_form_action)
        self._command_palette.form_field_changed.connect(self._on_palette_form_field_changed)
        self._palette_command_entries = self._create_palette_command_entries()
        self._palette_quick_add_entries = self._create_palette_quick_add_entries()
        self._refresh_palette_results("")

    def _setup_command_palette_shortcuts(self) -> None:
        sequence = "Meta+K" if sys.platform == "darwin" else "Ctrl+K"
        shortcut = QShortcut(QKeySequence(sequence), self)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(self.open_command_palette)
        self._palette_shortcuts = [shortcut]

    def _create_palette_command_entries(self) -> list[PaletteEntry]:
        return [
            PaletteEntry(
                "go_home",
                "command",
                "Go Home",
                "Return to the operations home screen.",
                "Commands",
                ("dashboard", "home"),
                10,
            ),
            PaletteEntry(
                "open_recipes",
                "command",
                "Open Recipes",
                "Open your saved recipe workspace.",
                "Commands",
                ("library", "saved recipes"),
                10,
            ),
            PaletteEntry(
                "search_recipes",
                "command",
                "Search Recipes",
                "Open Recipes and focus the global recipe search bar.",
                "Commands",
                ("find recipe", "recipe search", "discover"),
                20,
            ),
            PaletteEntry(
                "create_recipe",
                "command",
                "Create Recipe",
                "Start a new recipe in the editor.",
                "Commands",
                ("new recipe", "add recipe"),
                30,
            ),
            PaletteEntry(
                "open_meal_planner",
                "command",
                "Open Meal Planner",
                "Jump to the current week's planner.",
                "Commands",
                ("planner", "weekly plan"),
                10,
            ),
            PaletteEntry(
                "open_nutrition",
                "command",
                "Open Nutrition",
                "Open today's nutrition dashboard.",
                "Commands",
                ("macros", "nutrition dashboard"),
                10,
            ),
            PaletteEntry(
                "open_my_kitchen",
                "command",
                "Open My Kitchen",
                "Open the Pantry, Fridge, and Freezer tracker.",
                "Commands",
                ("pantry", "fridge", "freezer", "stock"),
                10,
            ),
            PaletteEntry(
                "open_shopping_list",
                "command",
                "Open Shopping List",
                "Open the editable shopping list.",
                "Commands",
                ("groceries", "shopping"),
                10,
            ),
            PaletteEntry(
                "open_dishy",
                "command",
                "Open Dishy",
                "Open the Dishy workspace.",
                "Commands",
                ("assistant", "copilot", "chat"),
                10,
            ),
            PaletteEntry(
                "ask_dishy",
                "command",
                "Ask Dishy",
                "Open Dishy ready to type a prompt.",
                "Commands",
                ("chat", "ask ai", "prompt"),
                20,
            ),
            PaletteEntry(
                "open_help",
                "command",
                "Open Help",
                "Open the how-to-use guide.",
                "Commands",
                ("guide", "how to use", "help"),
                10,
            ),
            PaletteEntry(
                "open_settings",
                "command",
                "Open Settings",
                "Open app preferences and account settings.",
                "Commands",
                ("preferences", "account", "settings"),
                20,
            ),
        ]

    def _create_palette_quick_add_entries(self) -> list[PaletteEntry]:
        return [
            PaletteEntry(
                "add_pantry_item",
                "quick_add",
                "Add Pantry Item",
                "Add stock directly without opening the full My Kitchen dialog.",
                "Quick Add",
                ("pantry", "fridge", "freezer", "stock"),
                10,
            ),
            PaletteEntry(
                "add_shopping_item",
                "quick_add",
                "Add Shopping Item",
                "Add to the shopping list from one lightweight form.",
                "Quick Add",
                ("shopping", "groceries", "list"),
                20,
            ),
            PaletteEntry(
                "log_nutrition",
                "quick_add",
                "Log Nutrition",
                "Estimate a food item with Dishy, then confirm before saving.",
                "Quick Add",
                ("nutrition", "food", "macros", "log"),
                30,
            ),
            PaletteEntry(
                "plan_meal",
                "quick_add",
                "Plan Meal",
                "Choose a day, meal slot, and saved recipe for the active week.",
                "Quick Add",
                ("meal", "planner", "slot", "week"),
                40,
            ),
        ]

    def _load_palette_recents(self) -> list[PaletteEntry]:
        raw = self._db.get_setting("command_palette_recents", "[]")
        try:
            items = json.loads(raw or "[]")
        except Exception:
            items = []
        entries: list[PaletteEntry] = []
        for item in items[:8]:
            if not isinstance(item, dict):
                continue
            entry_id = str(item.get("id") or "").strip()
            kind = str(item.get("kind") or "").strip()
            if not entry_id or not kind:
                continue
            entries.append(
                PaletteEntry(
                    entry_id,
                    kind,
                    self._palette_display_text(item.get("title") or ""),
                    self._palette_display_text(item.get("subtitle") or ""),
                    "Recent",
                    tuple(item.get("keywords") or ()),
                    int(item.get("sort_priority", 0) or 0),
                    dict(item.get("payload") or {}),
                    recent=True,
                )
            )
        return entries

    def _record_palette_recent(self, entry: PaletteEntry) -> None:
        current = self._load_palette_recents()
        payload = [
            {
                "id": item.id,
                "kind": item.kind,
                "title": self._palette_display_text(item.title),
                "subtitle": self._palette_display_text(item.subtitle),
                "keywords": list(item.keywords),
                "sort_priority": item.sort_priority,
                "payload": dict(item.payload or {}),
            }
            for item in current
            if not (item.id == entry.id and item.kind == entry.kind)
        ]
        payload.insert(
            0,
            {
                "id": entry.id,
                "kind": entry.kind,
                "title": self._palette_display_text(entry.title),
                "subtitle": self._palette_display_text(entry.subtitle),
                "keywords": list(entry.keywords),
                "sort_priority": entry.sort_priority,
                "payload": dict(entry.payload or {}),
            },
        )
        self._db.set_setting("command_palette_recents", json.dumps(payload[:8]))
        self._trigger_cloud_sync()

    def _current_palette_week_start(self) -> str:
        try:
            return self._meal_planner_view.current_week_start_iso()
        except Exception:
            today = datetime.now().date()
            return (today - timedelta(days=today.weekday())).isoformat()

    def _search_settings_entries(self, query: str) -> list[PaletteEntry]:
        entries = [
            PaletteEntry(
                f"settings:{section['key']}",
                "settings_section",
                section["label"],
                "Open this section in Settings.",
                "Settings",
                ("settings", section["group"], section["label"]),
                40,
                {"section": section["key"]},
            )
            for section in self._settings_view.palette_sections()
        ]
        return rank_entries(entries, query)

    def _palette_display_text(self, text: str) -> str:
        return " ".join(str(text or "").replace("_", " ").split())

    def _search_recipe_entries(self, query: str) -> list[PaletteEntry]:
        try:
            rows = self._db.get_saved_recipes()
        except Exception:
            rows = []
        results = filter_and_rank_saved_recipes(rows, query)[:8]
        entries: list[PaletteEntry] = []
        for row in results:
            data = dict(row)
            try:
                recipe_data = json.loads(data.get("data_json") or "{}")
            except Exception:
                recipe_data = {}
            tags = ", ".join(
                self._palette_display_text(tag)
                for tag in (recipe_data.get("tags") or [])[:3]
                if str(tag or "").strip()
            )
            subtitle = tags or "Saved recipe"
            entries.append(
                PaletteEntry(
                    f"recipe:{data['id']}",
                    "recipe",
                    self._palette_display_text(data.get("title") or ""),
                    subtitle,
                    "Recipes",
                    tuple(recipe_data.get("tags") or ()),
                    10,
                    {"recipe_id": int(data["id"])},
                )
            )
        return entries

    def _simple_entity_entries(
        self,
        *,
        query: str,
        rows: list[dict],
        kind: str,
        group: str,
        title_key: str,
        subtitle_fn,
        payload_fn,
        keywords_fn=None,
        limit: int = 8,
    ) -> list[PaletteEntry]:
        normalized = " ".join(str(query or "").lower().split())
        entries: list[PaletteEntry] = []
        for row in rows:
            title = str(row.get(title_key) or "").strip()
            if not title:
                continue
            subtitle = subtitle_fn(row)
            keywords = tuple(keywords_fn(row) if keywords_fn else ())
            entry = PaletteEntry(
                f"{kind}:{row.get('id')}",
                kind,
                title,
                subtitle,
                group,
                keywords,
                50,
                payload_fn(row),
            )
            if normalized and not rank_entries([entry], normalized):
                continue
            entries.append(entry)
        return rank_entries(entries, query)[:limit]

    def _search_pantry_entries(self, query: str) -> list[PaletteEntry]:
        rows = self._db.get_pantry_items()
        return self._simple_entity_entries(
            query=query,
            rows=rows,
            kind="pantry_item",
            group="My Kitchen",
            title_key="name",
            subtitle_fn=lambda row: f"{row.get('storage', 'Pantry')} · {str(row.get('quantity') or '').strip()} {str(row.get('unit') or '').strip()}".strip(" ·"),
            payload_fn=lambda row: {"item_id": int(row.get("id") or 0)},
            keywords_fn=lambda row: (row.get("storage", ""), row.get("unit", "")),
        )

    def _search_shopping_entries(self, query: str) -> list[PaletteEntry]:
        rows = [dict(row) for row in self._db.get_shopping_items()]
        return self._simple_entity_entries(
            query=query,
            rows=rows,
            kind="shopping_item",
            group="Shopping",
            title_key="name",
            subtitle_fn=lambda row: f"{str(row.get('quantity') or '').strip()} {str(row.get('unit') or '').strip()}".strip() or "Shopping item",
            payload_fn=lambda row: {"item_id": int(row.get("id") or 0)},
            keywords_fn=lambda row: (row.get("source", ""),),
        )

    def _search_meal_slot_entries(self, query: str) -> list[PaletteEntry]:
        week_start = self._current_palette_week_start()
        try:
            rows = [dict(row) for row in self._db.get_meal_plan(week_start)]
        except Exception:
            rows = []
        rows = [row for row in rows if str(row.get("custom_name") or "").strip()]
        entries: list[PaletteEntry] = []
        for row in rows:
            entries.append(
                PaletteEntry(
                    f"meal_slot:{row.get('id')}",
                    "meal_slot",
                    self._palette_display_text(row.get("custom_name") or ""),
                    f"{self._palette_display_text(row.get('day_of_week', ''))} · {str(row.get('meal_type') or '').capitalize()}",
                    "Meal Planner",
                    (row.get("day_of_week", ""), row.get("meal_type", ""), week_start),
                    30,
                    {
                        "day": str(row.get("day_of_week") or ""),
                        "meal_type": str(row.get("meal_type") or ""),
                        "week_start": week_start,
                        "recipe_id": int(row.get("recipe_id") or 0) or None,
                    },
                )
            )
        return rank_entries(entries, query)[:8]

    def _search_dishy_entries(self, query: str) -> list[PaletteEntry]:
        entries: list[PaletteEntry] = []
        for session in self._db.get_dishy_sessions_summary()[:12]:
            preview = str(session.get("first_message") or "").strip()
            entries.append(
                PaletteEntry(
                    f"dishy_session:{session['session_id']}",
                    "dishy_session",
                    preview[:70] + ("…" if len(preview) > 70 else ""),
                    f"{session.get('date', '')} · {session.get('message_count', 0)} messages",
                    "Dishy",
                    ("dishy", "session", preview),
                    60,
                    {"session_id": session["session_id"]},
                )
            )
        return rank_entries(entries, query)[:6]

    def _build_palette_entries(self, query: str) -> list[PaletteEntry]:
        query = str(query or "").strip()
        if not query:
            entries = [*self._load_palette_recents(), *self._palette_quick_add_entries, *self._palette_command_entries]
            return rank_entries(entries, "")

        ranked: list[PaletteEntry] = []
        ranked.extend(rank_entries([*self._palette_quick_add_entries, *self._palette_command_entries], query))
        ranked.extend(self._search_recipe_entries(query))
        ranked.extend(self._search_pantry_entries(query))
        ranked.extend(self._search_shopping_entries(query))
        ranked.extend(self._search_meal_slot_entries(query))
        ranked.extend(self._search_settings_entries(query))
        ranked.extend(self._search_dishy_entries(query))
        deduped: list[PaletteEntry] = []
        seen: set[tuple[str, str]] = set()
        for entry in ranked:
            key = (entry.kind, entry.id)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(entry)
        return deduped[:24]

    def _refresh_palette_results(self, query: str) -> None:
        self._last_palette_query = str(query or "")
        self._command_palette.set_entries(self._build_palette_entries(query))

    def _quick_add_form(self, form_id: str, *, values: dict | None = None) -> QuickAddForm:
        values = dict(values or {})
        if form_id == "add_pantry_item":
            return QuickAddForm(
                id=form_id,
                title="Add Pantry Item",
                subtitle="Add stock directly from the command panel.",
                primary_label="Add Item",
                helper_text="Name is required. Expiry should use YYYY-MM-DD if you enter one.",
                fields=(
                    PaletteField("name", "Name", "e.g. Chicken breast", required=True, default=values.get("name", "")),
                    PaletteField("quantity", "Quantity", "e.g. 500", field_type="number", default=values.get("quantity", "")),
                    PaletteField("unit", "Unit", "e.g. g", default=values.get("unit", "")),
                    PaletteField(
                        "storage",
                        "Storage",
                        field_type="choice",
                        options=(("Pantry", "Pantry"), ("Fridge", "Fridge"), ("Freezer", "Freezer")),
                        default=values.get("storage", "Pantry"),
                    ),
                    PaletteField("expiry_date", "Expiry", "YYYY-MM-DD (optional)", default=values.get("expiry_date", "")),
                ),
            )
        if form_id == "add_shopping_item":
            return QuickAddForm(
                id=form_id,
                title="Add Shopping Item",
                subtitle="Capture groceries without leaving the command panel.",
                primary_label="Add Item",
                helper_text="Name is required.",
                fields=(
                    PaletteField("name", "Name", "e.g. Greek yogurt", required=True, default=values.get("name", "")),
                    PaletteField("quantity", "Quantity", "e.g. 2", field_type="number", default=values.get("quantity", "")),
                    PaletteField("unit", "Unit", "e.g. tubs", default=values.get("unit", "")),
                ),
            )
        if form_id == "log_nutrition":
            return QuickAddForm(
                id=form_id,
                title="Log Nutrition",
                subtitle="Estimate a food item with Dishy, then confirm before saving it.",
                primary_label="Lookup",
                helper_text="Describe the food naturally, for example “2 eggs and toast”.",
                fields=(
                    PaletteField("query", "Food", "e.g. 2 eggs, bowl of oats", required=True, default=values.get("query", "")),
                ),
            )
        if form_id == "plan_meal":
            return QuickAddForm(
                id=form_id,
                title="Plan Meal",
                subtitle="Choose a day, meal slot, and saved recipe for the active week.",
                primary_label="Save Meal",
                helper_text="Recipe search uses your saved recipes and picks the best match.",
                fields=(
                    PaletteField(
                        "day",
                        "Day",
                        field_type="choice",
                        options=tuple((day, day) for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")),
                        default=values.get("day", datetime.now().strftime("%A")),
                    ),
                    PaletteField(
                        "meal_type",
                        "Meal",
                        field_type="choice",
                        options=(("Breakfast", "breakfast"), ("Lunch", "lunch"), ("Dinner", "dinner"), ("Snack", "snack")),
                        default=values.get("meal_type", "dinner"),
                    ),
                    PaletteField(
                        "recipe_query",
                        "Recipe",
                        "Start typing a saved recipe",
                        field_type="recipe_search",
                        required=True,
                        default=values.get("recipe_query", ""),
                    ),
                ),
            )
        raise ValueError(f"Unknown quick-add form: {form_id}")

    def _show_quick_add_form(self, form_id: str, *, values: dict | None = None) -> None:
        self._command_palette.show_quick_add(self._quick_add_form(form_id, values=values))
        if form_id == "plan_meal":
            seed_query = str((values or {}).get("recipe_query") or "")
            if seed_query:
                self._update_palette_recipe_suggestions(seed_query)

    def _show_log_nutrition_preview(self, data: dict, *, original_query: str) -> None:
        rows = (
            ("Food", str(data.get("food_name") or "Unknown")),
            ("Serving", str(data.get("serving") or "Estimated serving")),
            ("Calories", f"{float(data.get('kcal', 0)):.0f} kcal"),
            (
                "Macros",
                f"P {float(data.get('protein_g', 0)):.1f}g · C {float(data.get('carbs_g', 0)):.1f}g · F {float(data.get('fat_g', 0)):.1f}g",
            ),
        )
        self._command_palette.show_quick_add(
            QuickAddForm(
                id="log_nutrition",
                title="Confirm Nutrition Log",
                subtitle="Review Dishy’s estimate before saving it to today.",
                primary_label="Save Log",
                helper_text="This uses the same Dishy estimation flow as the Nutrition page.",
                preview_rows=rows,
                preview_payload={"nutrition": dict(data or {}), "query": original_query},
                mode="preview",
            )
        )

    def _resolve_recipe_match(self, query: str):
        try:
            rows = self._db.get_saved_recipes()
        except Exception:
            rows = []
        matches = filter_and_rank_saved_recipes(rows, query)
        return matches[0] if matches else None

    def _palette_recipe_suggestions(self, query: str) -> list[dict]:
        try:
            rows = self._db.get_saved_recipes()
        except Exception:
            rows = []
        query = str(query or "").strip()
        if not query:
            return []
        matches = filter_and_rank_saved_recipes(rows, query) if query else list(rows)
        suggestions: list[dict] = []
        for row in matches[:5]:
            data = dict(row)
            title = self._palette_display_text(data.get("title") or "")
            if query and not self._recipe_suggestion_matches(title, query):
                continue
            try:
                recipe_data = json.loads(data.get("data_json") or "{}")
            except Exception:
                recipe_data = {}
            tags = ", ".join(
                self._palette_display_text(tag)
                for tag in (recipe_data.get("tags") or [])[:2]
                if str(tag or "").strip()
            )
            suggestions.append(
                {
                    "id": int(data.get("id") or 0),
                    "title": title,
                    "subtitle": tags or "Saved recipe",
                }
            )
            if len(suggestions) >= 5:
                break
        return suggestions

    def _recipe_suggestion_matches(self, title: str, query: str) -> bool:
        query = " ".join(str(query or "").lower().split())
        title = " ".join(str(title or "").lower().split())
        if not query:
            return True
        if query in title:
            return True
        title_words = title.split()
        if any(word.startswith(query) for word in title_words):
            return True
        query_words = query.split()
        if query_words and all(
            any(
                qword in word
                or word.startswith(qword)
                or SequenceMatcher(None, qword, word).ratio() >= 0.72
                for word in title_words
            )
            for qword in query_words
        ):
            return True
        return max((SequenceMatcher(None, query, word).ratio() for word in title_words), default=0.0) >= 0.72

    def _update_palette_recipe_suggestions(self, query: str) -> None:
        self._command_palette.set_field_suggestions(
            "recipe_query",
            self._palette_recipe_suggestions(query),
        )

    def _on_palette_form_field_changed(self, form_id: str, field_key: str, value: str) -> None:
        if form_id == "plan_meal" and field_key == "recipe_query":
            self._update_palette_recipe_suggestions(value)

    def _on_palette_entry_activated(self, entry: PaletteEntry) -> None:
        if entry.kind == "quick_add":
            self._show_quick_add_form(entry.id)
            return
        self._command_palette.hide()
        QTimer.singleShot(0, lambda e=entry: self._execute_palette_entry(e))

    def _execute_palette_entry(self, entry: PaletteEntry) -> bool:
        handled = False
        if entry.kind == "command":
            handled = self._execute_command_entry(entry.id)
        elif entry.kind == "recipe":
            recipe_id = int(entry.payload.get("recipe_id") or 0)
            if recipe_id:
                self._on_nav_clicked(1)
                self._recipes_view.open_by_id(recipe_id)
                handled = True
        elif entry.kind == "pantry_item":
            item_id = int(entry.payload.get("item_id") or 0)
            self._on_nav_clicked(4)
            handled = self._my_kitchen_storage_view.focus_item(item_id)
        elif entry.kind == "shopping_item":
            item_id = int(entry.payload.get("item_id") or 0)
            self._on_nav_clicked(5)
            handled = self._shopping_view.focus_item(item_id)
        elif entry.kind == "meal_slot":
            self._on_nav_clicked(2)
            handled = self._meal_planner_view.open_meal_slot(
                str(entry.payload.get("day") or ""),
                str(entry.payload.get("meal_type") or ""),
            )
        elif entry.kind == "settings_section":
            self._on_settings_clicked()
            self._settings_view.activate_settings(str(entry.payload.get("section") or "preferences"))
            handled = True
        elif entry.kind == "dishy_session":
            self._on_nav_clicked(6)
            handled = self._dishy_view.open_session(str(entry.payload.get("session_id") or ""))
        if handled:
            self._record_palette_recent(entry)
        return handled

    def _execute_command_entry(self, command_id: str) -> bool:
        mapping = {
            "go_home": self.go_home,
            "open_recipes": self._open_recipes_saved,
            "search_recipes": self._open_recipes_search,
            "create_recipe": self._open_recipe_create,
            "open_meal_planner": self._open_meal_planner,
            "open_nutrition": self._open_nutrition,
            "open_my_kitchen": self._open_my_kitchen,
            "open_shopping_list": self._open_shopping_list,
            "open_dishy": self._open_dishy,
            "ask_dishy": self._open_dishy_chat,
            "open_help": self._on_guide_clicked,
            "open_settings": self._open_settings,
        }
        handler = mapping.get(command_id)
        if handler is None:
            return False
        handler()
        entry = next((item for item in self._palette_command_entries if item.id == command_id), None)
        if entry is not None:
            self._record_palette_recent(entry)
        return True

    def _on_palette_form_action(self, form_id: str, action: str, values: dict) -> None:
        if action != "primary":
            self._command_palette.clear_form()
            self._refresh_palette_results(self._last_palette_query)
            return

        if form_id == "add_pantry_item":
            name = str(values.get("name") or "").strip()
            if not name:
                self._command_palette.update_form_message("Name is required.", is_error=True)
                return
            qty_raw = str(values.get("quantity") or "").strip()
            try:
                quantity = float(qty_raw) if qty_raw else None
            except ValueError:
                self._command_palette.update_form_message("Quantity must be a number.", is_error=True)
                return
            expiry = str(values.get("expiry_date") or "").strip() or None
            if expiry:
                try:
                    datetime.fromisoformat(expiry)
                except ValueError:
                    self._command_palette.update_form_message("Expiry must use YYYY-MM-DD.", is_error=True)
                    return
            item_id = self._my_kitchen_storage_view.save_item_from_palette(
                name=name,
                quantity=quantity,
                unit=str(values.get("unit") or "").strip(),
                storage=str(values.get("storage") or "Pantry"),
                expiry_date=expiry,
            )
            self._command_palette.hide()
            self._on_nav_clicked(4)
            self._my_kitchen_storage_view.focus_item(item_id)
            self._record_palette_recent(next(item for item in self._palette_quick_add_entries if item.id == form_id))
            return

        if form_id == "add_shopping_item":
            name = str(values.get("name") or "").strip()
            if not name:
                self._command_palette.update_form_message("Name is required.", is_error=True)
                return
            item_id = self._shopping_view.save_item_from_palette(
                name=name,
                quantity=str(values.get("quantity") or "").strip(),
                unit=str(values.get("unit") or "").strip(),
            )
            self._command_palette.hide()
            self._on_nav_clicked(5)
            self._shopping_view.focus_item(item_id)
            self._record_palette_recent(next(item for item in self._palette_quick_add_entries if item.id == form_id))
            return

        if form_id == "log_nutrition":
            preview_payload = dict(values.get("_preview_payload") or {})
            if preview_payload:
                nutrition = dict(preview_payload.get("nutrition") or {})
                if not self._nutrition_view.save_estimate_to_today(nutrition):
                    self._command_palette.update_form_message("Could not save this nutrition estimate.", is_error=True)
                    return
                self._trigger_cloud_sync()
                self._command_palette.hide()
                self._on_nav_clicked(3)
                self._record_palette_recent(next(item for item in self._palette_quick_add_entries if item.id == form_id))
                return
            query = str(values.get("query") or "").strip()
            if not query:
                self._command_palette.update_form_message("Food query is required.", is_error=True)
                return
            self._command_palette.set_form_pending(True)
            self._command_palette.update_form_message("Asking Dishy for an estimate…")
            self._nutrition_view.request_quick_estimate(
                query,
                on_result=lambda data, q=query: self._on_palette_nutrition_lookup_result(q, data),
                on_error=self._on_palette_nutrition_lookup_error,
            )
            return

        if form_id == "plan_meal":
            selected_recipe_id = int(values.get("recipe_query_selected_id") or 0)
            recipe_row = None
            if selected_recipe_id:
                recipe_row = next(
                    (row for row in self._db.get_saved_recipes() if int(row["id"]) == selected_recipe_id),
                    None,
                )
            recipe_query = str(values.get("recipe_query") or "").strip()
            if recipe_row is None and recipe_query:
                recipe_row = self._resolve_recipe_match(recipe_query)
            if recipe_row is None:
                self._command_palette.update_form_message("No saved recipe matched that search.", is_error=True)
                return
            day = str(values.get("day") or "").strip()
            meal_type = str(values.get("meal_type") or "").strip().lower()
            if not self._meal_planner_view.save_meal_slot_from_palette(day, meal_type, int(recipe_row["id"])):
                self._command_palette.update_form_message("Could not save that meal slot.", is_error=True)
                return
            self._command_palette.hide()
            self._on_nav_clicked(2)
            self._meal_planner_view.open_meal_slot(day, meal_type)
            self._record_palette_recent(next(item for item in self._palette_quick_add_entries if item.id == form_id))
            return

    def _on_palette_nutrition_lookup_result(self, query: str, data: dict) -> None:
        self._command_palette.set_form_pending(False)
        self._show_log_nutrition_preview(data, original_query=query)

    def _on_palette_nutrition_lookup_error(self, err: str) -> None:
        self._command_palette.set_form_pending(False)
        msg = "Lookup failed — check your connection or API key."
        err_lower = str(err or "").lower()
        if "credit" in err_lower or "too low" in err_lower:
            msg = "Anthropic credits are low — top up before using nutrition lookup."
        elif "401" in err_lower or "auth" in err_lower:
            msg = "Nutrition lookup could not authenticate — check your API key."
        self._command_palette.update_form_message(msg, is_error=True)

    def _open_recipes_saved(self) -> None:
        self._on_nav_clicked(1)
        self._recipes_view.activate_saved_recipes()

    def _open_recipes_search(self) -> None:
        self._on_nav_clicked(1)
        self._recipes_view.activate_recipe_search()

    def _open_recipe_create(self) -> None:
        self._on_nav_clicked(1)
        self._recipes_view.activate_create_recipe()

    def _open_meal_planner(self) -> None:
        self._on_nav_clicked(2)
        self._meal_planner_view.activate_planner()

    def _open_nutrition(self) -> None:
        self._on_nav_clicked(3)

    def _open_my_kitchen(self) -> None:
        self._on_nav_clicked(4)
        self._my_kitchen_storage_view.activate_storage()

    def _open_shopping_list(self) -> None:
        self._on_nav_clicked(5)
        self._shopping_view.activate_shopping_list()

    def _open_dishy(self) -> None:
        self._on_nav_clicked(6)

    def _open_dishy_chat(self) -> None:
        self._on_nav_clicked(6)
        self._dishy_view.activate_chat()

    def _open_settings(self) -> None:
        self._on_settings_clicked()
        self._settings_view.activate_settings()

    # --------------------------------------------------------------- navigation

    _PAGE_NAMES = ["Home", "Recipes", "Meal Planner",
                   "Nutrition", "My Kitchen", "Shopping List", "Dishy", "How to use", "Settings"]

    def _back_bar_style(self) -> str:
        return (
            f"background-color: {theme_manager.c('#101214', '#f6f1eb')};"
            " border-bottom: none;"
        )

    def _back_btn_style(self) -> str:
        return (
            "QPushButton {"
            " background: transparent;"
            " border: none;"
            f" color: {theme_manager.c('#a39c93', '#6c6258')};"
            " font-size: 13px; font-weight: 600; text-align: left; padding: 0 8px;"
            "}"
            "QPushButton:hover {"
            f" color: {theme_manager.c('#ece6de', '#241c15')};"
            "}"
        )

    def _prepare_page_for_sidebar_navigation(self, index: int) -> None:
        view = self._stack.widget(index)
        if view is None or not hasattr(view, "show_root_page"):
            return
        try:
            view.show_root_page()
        except Exception:
            pass

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
        self._prepare_page_for_sidebar_navigation(index)
        self._dishy_bubble.set_page(self._PAGE_NAMES[index])
        self._animate_current_page()
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
        self._prepare_page_for_sidebar_navigation(7)
        self._dishy_bubble.set_page("How to use")
        self._animate_current_page()
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
        self._prepare_page_for_sidebar_navigation(8)
        self._dishy_bubble.set_page("Settings")
        self._animate_current_page()
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
        self._animate_current_page()
    def _animate_current_page(self):
        """Slide-in transition without QGraphics effects (paint-stable)."""
        view = self._stack.currentWidget()
        if view is None:
            return
        self._page_anim = slide_in_widget(view, offset_px=18, duration_ms=170)

    def _toggle_sidebar(self):
        expanded = self._sidebar_expanded
        start_w = SIDEBAR_EXPANDED if expanded else SIDEBAR_COLLAPSED
        end_w   = SIDEBAR_COLLAPSED if expanded else SIDEBAR_EXPANDED

        if expanded:
            # Collapsing — hide labels, show small logo icon + compact date
            for btn in self._nav_buttons:
                btn.set_expanded(False)
            self._guide_btn.set_expanded(False)
            self._settings_btn.set_expanded(False)
            self._logo_lbl.setVisible(False)
            # Shrink logo icon to fit the collapsed 64px sidebar
            if os.path.exists(self._icon_src_path):
                px_small = QPixmap(self._icon_src_path).scaled(
                    30, 30,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._logo_icon_lbl.setPixmap(px_small)
            self._sidebar_date_lbl.setVisible(False)
            self._version_lbl.setVisible(False)
            self._ver_num_lbl.setVisible(False)
            self._sidebar_date_compact.setVisible(True)
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
                # Restore full logo icon size
                if os.path.exists(self._icon_src_path):
                    px_big = QPixmap(self._icon_src_path).scaled(
                        52, 52,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._logo_icon_lbl.setPixmap(px_big)
                self._sidebar_date_lbl.setVisible(True)
                self._version_lbl.setVisible(True)
                self._ver_num_lbl.setVisible(True)
                self._sidebar_date_compact.setVisible(False)
                self._sync_indicator.set_expanded(True)
            grp.finished.connect(_on_expand_done)

        grp.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._sidebar_expanded = not expanded

    def resizeEvent(self, event):
        """Auto-collapse sidebar when window is narrow; re-expand when wide again."""
        super().resizeEvent(event)
        if self._in_resize_toggle:
            return
        w = event.size().width()
        if w < 940 and self._sidebar_expanded:
            self._in_resize_toggle = True
            self._auto_collapsed = True
            self._toggle_sidebar()
            self._in_resize_toggle = False
        elif w >= 1060 and not self._sidebar_expanded and self._auto_collapsed:
            self._in_resize_toggle = True
            self._auto_collapsed = False
            self._toggle_sidebar()
            self._in_resize_toggle = False
        if hasattr(self, "_command_palette") and self._command_palette.isVisible():
            self._command_palette.reposition()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "_command_palette") and self._command_palette.isVisible():
            self._command_palette.reposition()

    def open_command_palette(self) -> None:
        modal = QApplication.activeModalWidget()
        if modal is not None and modal is not self._command_palette:
            return
        self._refresh_palette_results("")
        self._command_palette.show_palette("")

    def run_command_palette_entry(self, entry_id: str, query: str = "") -> bool:
        entry = next((item for item in self._build_palette_entries(query) if item.id == entry_id), None)
        if entry is None:
            return False
        if entry.kind == "quick_add":
            self._show_quick_add_form(entry.id)
            return True
        return self._execute_palette_entry(entry)

    def run_command_palette_command(self, command_id: str) -> bool:
        return self.run_command_palette_entry(command_id)

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
        try:
            if "my_kitchen" in view_names:
                self._my_kitchen_storage_view.refresh()
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
        self._back_bar.setStyleSheet(self._back_bar_style())
        self._back_btn.setStyleSheet(self._back_btn_style())
        self._sidebar_date_compact.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {theme_manager.c('#888888', '#666666')};"
            " line-height: 1.3; background: transparent; padding: 0;"
        )
        self._toggle_btn.setIcon(qta.icon("fa5s.bars", color=_inactive_icon_color()))
        for btn in [*self._nav_buttons, self._guide_btn, self._settings_btn]:
            btn._refresh_icon()
        for i in range(self._stack.count()):
            view = self._stack.widget(i)
            if hasattr(view, "apply_theme"):
                view.apply_theme(mode)
        self._dishy_bubble.apply_theme(mode)
        if hasattr(self, "_command_palette"):
            self._command_palette.apply_theme()

    # ── Cloud sync public API ─────────────────────────────────────────────────

    def _trigger_cloud_sync(self) -> None:
        """Trigger an immediate cloud sync after any data mutation. Safe if not logged in."""
        try:
            self._visibility_service.refresh()
            if self._cloud_sync_service is not None:
                self._cloud_sync_service.sync_now()
        except Exception:
            pass

    def set_sync_service(self, service) -> None:
        """Wire a CloudSyncBackgroundService without exposing sidebar sync chrome."""
        self._cloud_sync_service = service
        self._visibility_service.bind_sync_service(service)
        self._sync_indicator.setVisible(False)
        self._sync_indicator.set_state("syncing")
        service.sync_started.connect(
            lambda: self._sync_indicator.set_state("syncing")
        )
        # Always show "live" after a successful sync — the app uses Supabase cloud
        service.sync_finished.connect(
            lambda _p, _r: self._sync_indicator.set_state("live")
        )
        service.sync_error.connect(self._sync_indicator.set_error)
        # Allow the user to manually retry a failed sync by clicking the indicator
        self._sync_indicator.retry_requested.connect(
            getattr(service, "retry_now", service.sync_now)
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
        self._visibility_service.refresh()

    def go_home(self) -> None:
        """Navigate to the Home view and deselect settings/guide buttons."""
        self._on_nav_clicked(0)

    def refresh_all_views(self) -> None:
        """Force every content view to reload from the local DB.

        Called after an account switch so the UI doesn't show stale data from
        the previous user while the cloud sync is pulling the new user's data.
        """
        for refresh_fn in (
            lambda: self._recipes_view.refresh(),
            lambda: self._meal_planner_view.refresh(),
            lambda: self._shopping_view.refresh(),
            lambda: self._nutrition_view.refresh(),
            lambda: self._my_kitchen_storage_view.refresh(),
            lambda: self._stack.widget(0).refresh() if hasattr(self._stack.widget(0), "refresh") else None,
            lambda: self._dishy_view.reset_session(),
            lambda: self._dishy_bubble.reset_session(),
        ):
            try:
                refresh_fn()
            except Exception:
                pass
        self._visibility_service.refresh()

    def set_offline_mode(self) -> None:
        """Legacy alias — calls set_sync_unavailable."""
        self.set_sync_unavailable()

    def set_sync_unavailable(self) -> None:
        """Track sync-unavailable state without showing sidebar sync chrome."""
        self._sync_indicator.setVisible(False)
        self._sync_indicator.set_state("offline")

    def set_account_user(self, user: dict | None, sync_service) -> None:
        """Pass account info to the Settings > Account page."""
        self._settings_view.set_account_info(user, sync_service)
        self._settings_view.set_visibility_service(self._visibility_service)
        # Start meal deduction service after login
        if not hasattr(self, "_meal_deduction_service") or self._meal_deduction_service is None:
            try:
                from utils.meal_deduction import MealDeductionService
                self._meal_deduction_service = MealDeductionService(self._db, parent=self)
                self._meal_deduction_service.ingredients_deducted.connect(
                    self._my_kitchen_storage_view.refresh
                )
            except Exception:
                self._meal_deduction_service = None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                self._settings_view.sign_in_requested.disconnect()
            except Exception:
                pass
        self._settings_view.sign_in_requested.connect(self.sign_in_requested.emit)
        self._settings_view.sign_out_requested.connect(self.sign_out_requested.emit)

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
