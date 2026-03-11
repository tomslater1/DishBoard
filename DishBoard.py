import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix SSL certificate path for the requests library inside a PyInstaller bundle.
# requests cannot find cacert.pem via its own pkg_resources lookup when frozen,
# so we point it at the certifi bundle explicitly before any network code runs.
import certifi
os.environ.setdefault("SSL_CERT_FILE",      certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

# utils.paths must be imported before anything that uses paths
from utils.paths import get_data_dir, get_resource_path

from models.database import Database
from utils.theme import manager as theme_manager
from qt_material import apply_stylesheet
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QStackedWidget, QStyleFactory


QSS_PATH       = get_resource_path("assets/styles/theme.qss")
ICON_PATH      = get_resource_path("assets/icons/DishBoard-darkicon.png")
ICON_DOCK_PATH = get_resource_path("assets/icons/DishBoard-darkicon.png")


def _load_api_keys_from_db(db: Database):
    """Read API keys saved via the Settings view and push them into os.environ.

    Also loads SUPABASE_URL and SUPABASE_ANON_KEY so the auth client is ready.
    Keys stored in the DB always take priority over os.environ defaults.
    Supabase credentials are persisted back to the DB on first run so they
    survive across launches without any configuration file.
    """
    key_map = {
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "google_api_key":    "GOOGLE_API_KEY",
        "google_cx":         "GOOGLE_CX",
        "supabase_url":      "SUPABASE_URL",
        "supabase_anon_key": "SUPABASE_ANON_KEY",
    }
    for db_key, env_key in key_map.items():
        if not os.environ.get(env_key):
            val = db.get_setting(db_key, "")
            if val:
                os.environ[env_key] = val

    # Ensure Supabase URL is always in os.environ — the AI proxy reads it from here.
    # If nothing was found in DB, fall back to the bundled defaults.
    if not os.environ.get("SUPABASE_URL"):
        from auth.supabase_client import _DEFAULT_URL, _DEFAULT_KEY
        os.environ["SUPABASE_URL"] = _DEFAULT_URL
        os.environ["SUPABASE_ANON_KEY"] = _DEFAULT_KEY

    # Persist Supabase credentials to DB so they survive across launches
    for env_key, db_key in [("SUPABASE_URL", "supabase_url"),
                             ("SUPABASE_ANON_KEY", "supabase_anon_key")]:
        val = os.environ.get(env_key)
        if val:
            db.set_setting(db_key, val)



# ── Global references kept alive so Qt doesn't GC them ───────────────────────
_main_window      = None
_login_view       = None
_root_stack       = None
_sync_service     = None
_db               = None
_onboarding_view  = None
_app_tour         = None   # AppTourOverlay — kept alive during tour
_pending_tour     = False  # True when offline mode chosen (tour always shown)


def _start_cloud_sync(user: dict) -> None:
    """Create CloudSyncBackgroundService and wire it to the main window."""
    global _sync_service
    from utils.cloud_sync_service import CloudSyncBackgroundService
    _sync_service = CloudSyncBackgroundService(user["id"], parent=_main_window)
    _main_window.set_sync_service(_sync_service)
    _sync_service.sync_now()
    _sync_service.start_realtime()


def _show_app_tour() -> None:
    """Create and launch the AppTourOverlay over the main window."""
    global _app_tour
    if _app_tour is not None:
        return  # already running
    from views.app_tour import AppTourOverlay
    _app_tour = AppTourOverlay(_main_window, _db)
    _app_tour.finished.connect(_on_tour_finished)
    _app_tour.start()


def _on_tour_finished() -> None:
    """Called when the user completes or skips the tour."""
    global _app_tour, _pending_tour
    if _app_tour is not None:
        _app_tour.hide()
        _app_tour.deleteLater()
        _app_tour = None
    # Only mark the tour complete for authenticated (non-offline) users
    if not _pending_tour:
        _db.set_setting("app_tour_complete", "1")
    _pending_tour = False


def _on_login_success(user: dict) -> None:
    """Called (on main thread) after a successful sign-in."""
    global _main_window, _root_stack, _db

    # Switch to the main app
    _root_stack.setCurrentIndex(1)

    # Check if local data exists → offer migration to new account
    if not user.get("offline"):
        try:
            recipe_count = len(_db.get_saved_recipes())
            if recipe_count > 0:
                from auth.migration_dialog import MigrationDialog
                dlg = MigrationDialog(recipe_count, user_id=user["id"],
                                      parent=_main_window)
                dlg.exec()
        except Exception:
            pass

    # Start background cloud sync (skip if offline mode)
    if not user.get("offline"):
        _start_cloud_sync(user)
    else:
        _main_window.set_offline_mode()

    # Tell Settings about the logged-in user
    _main_window.set_account_user(user, _sync_service)

    # Show onboarding if profile not yet set up
    _maybe_show_onboarding()


def _on_continue_offline() -> None:
    """User chose to skip account creation — run fully local."""
    global _root_stack, _main_window, _pending_tour
    _pending_tour = True   # always show tour for offline sessions
    _root_stack.setCurrentIndex(1)
    _main_window.set_offline_mode()
    _main_window.set_account_user(None, None)

    # Show onboarding if profile not yet set up
    _maybe_show_onboarding()

    # If onboarding is already complete, show the tour immediately
    if _db.get_setting("onboarding_complete", "") == "1":
        QTimer.singleShot(400, _show_app_tour)
        _pending_tour = False


def _maybe_show_onboarding() -> None:
    """Switch to the full-screen onboarding wizard if profile not yet set up."""
    global _db, _root_stack, _onboarding_view
    if _db.get_setting("onboarding_complete", "") != "1":
        _root_stack.setCurrentIndex(2)


def _on_onboarding_finished() -> None:
    """Called when the user completes or skips onboarding — go to main app."""
    global _root_stack, _pending_tour
    _root_stack.setCurrentIndex(1)
    # Show tour for: new authenticated users (no flag yet) OR pending offline session
    if _pending_tour or _db.get_setting("app_tour_complete", "") != "1":
        QTimer.singleShot(400, _show_app_tour)
    _pending_tour = False


def main():
    global _main_window, _login_view, _root_stack, _db

    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setApplicationName("DishBoard")
    app.setOrganizationName("DishBoard")

    dock_src = ICON_DOCK_PATH if os.path.exists(ICON_DOCK_PATH) else ICON_PATH
    if os.path.exists(dock_src):
        app.setWindowIcon(QIcon(dock_src))

    # Apply theme
    saved_mode = theme_manager.load()
    if saved_mode == "light":
        light_qss = get_resource_path("assets/styles/theme_light.qss")
        if os.path.exists(light_qss):
            with open(light_qss) as f:
                app.setStyleSheet(f.read())
    else:
        apply_stylesheet(app, theme="dark_amber.xml", extra={"density_scale": "0"})
        if os.path.exists(QSS_PATH):
            with open(QSS_PATH) as f:
                app.setStyleSheet(app.styleSheet() + "\n" + f.read())

    # System font
    font = QFont("SF Pro Display", 13)
    if not font.exactMatch():
        font = QFont(".AppleSystemUIFont", 13)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    # Initialise local database
    _db = Database()
    _db.connect()
    _db.init_db()

    # Load API keys from DB into os.environ (includes Supabase keys)
    _load_api_keys_from_db(_db)

    # Reset Supabase client so it picks up the freshly loaded env vars
    from auth.supabase_client import reset_client
    reset_client()

    # ── Root stack: [0] LoginView  [1] MainWindow ────────────────────────────
    _root_stack = QStackedWidget()
    _root_stack.setWindowTitle("DishBoard")
    _root_stack.resize(1200, 800)
    _root_stack.setMinimumSize(900, 600)

    # Centre on screen
    from PySide6.QtGui import QGuiApplication
    screen = QGuiApplication.primaryScreen().availableGeometry()
    _root_stack.move(
        (screen.width()  - 1200) // 2,
        (screen.height() - 800)  // 2,
    )
    if os.path.exists(dock_src):
        _root_stack.setWindowIcon(QIcon(dock_src))

    # Build login view
    from views.login import LoginView
    _login_view = LoginView()
    _login_view.login_successful.connect(_on_login_success)
    _login_view.continue_offline.connect(_on_continue_offline)

    # Build main window
    from main_window import MainWindow
    _main_window = MainWindow()
    _main_window.sign_in_requested.connect(
        lambda: _root_stack.setCurrentIndex(0)
    )

    # Build onboarding wizard
    from views.onboarding import OnboardingWizard
    _onboarding_view = OnboardingWizard(_db)
    _onboarding_view.finished.connect(_on_onboarding_finished)

    _root_stack.addWidget(_login_view)       # index 0
    _root_stack.addWidget(_main_window)      # index 1
    _root_stack.addWidget(_onboarding_view)  # index 2

    # ── Session check ─────────────────────────────────────────────────────────
    from auth.session_manager import get_current_user
    user = get_current_user()

    if user:
        # Valid (or offline) session — skip login screen
        _root_stack.setCurrentIndex(1)
        if not user.get("offline"):
            _start_cloud_sync(user)
        else:
            _main_window.set_offline_mode()
        _main_window.set_account_user(user, _sync_service)
    else:
        # No session — show login
        _root_stack.setCurrentIndex(0)

    _root_stack.show()

    # Check for updates in the background — never blocks launch
    from utils.workers import run_async
    from utils.updater import check_for_update

    def _on_update_result(info):
        if info:
            from widgets.update_dialog import UpdateDialog
            UpdateDialog(info, parent=_root_stack).exec()

    run_async(check_for_update, on_result=_on_update_result, on_error=lambda _: None)

    exit_code = app.exec()
    _db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
