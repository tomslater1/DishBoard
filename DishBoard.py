import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix SSL certificate path for the requests library inside a PyInstaller bundle.
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


def _load_supabase_credentials(db: Database):
    """Ensure SUPABASE_URL and SUPABASE_ANON_KEY are in os.environ.

    Reads from DB first (persisted on previous runs), then falls back to the
    bundled defaults.  No other API keys are loaded here — Dishy uses the
    server-side proxy, and all other third-party keys are managed server-side.
    """
    for db_key, env_key in [("supabase_url", "SUPABASE_URL"),
                             ("supabase_anon_key", "SUPABASE_ANON_KEY")]:
        if not os.environ.get(env_key):
            val = db.get_setting(db_key, "")
            if val:
                os.environ[env_key] = val

    # Fall back to bundled defaults if still not set
    if not os.environ.get("SUPABASE_URL"):
        from auth.supabase_client import _DEFAULT_URL, _DEFAULT_KEY
        os.environ["SUPABASE_URL"] = _DEFAULT_URL
        os.environ["SUPABASE_ANON_KEY"] = _DEFAULT_KEY

    # Persist to DB so they survive across launches
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
        return
    from views.app_tour import AppTourOverlay
    _app_tour = AppTourOverlay(_main_window, _db)
    _app_tour.finished.connect(_on_tour_finished)
    _app_tour.start()


def _on_tour_finished() -> None:
    """Called when the user completes or skips the tour."""
    global _app_tour
    if _app_tour is not None:
        _app_tour.hide()
        _app_tour.deleteLater()
        _app_tour = None
    _db.set_setting("app_tour_complete", "1")


def _on_login_success(user: dict) -> None:
    """Called (on main thread) after a successful sign-in."""
    global _main_window, _root_stack, _db

    _root_stack.setCurrentIndex(1)

    # Offer migration of local data to the new account
    try:
        recipe_count = len(_db.get_saved_recipes())
        if recipe_count > 0:
            from auth.migration_dialog import MigrationDialog
            dlg = MigrationDialog(recipe_count, user_id=user["id"],
                                  parent=_main_window)
            dlg.exec()
    except Exception:
        pass

    _start_cloud_sync(user)
    _main_window.set_account_user(user, _sync_service)
    _maybe_show_onboarding()


def _maybe_show_onboarding() -> None:
    """Switch to the full-screen onboarding wizard if profile not yet set up."""
    if _db.get_setting("onboarding_complete", "") != "1":
        _root_stack.setCurrentIndex(2)


def _on_onboarding_finished() -> None:
    """Called when the user completes or skips onboarding — go to main app."""
    _root_stack.setCurrentIndex(1)
    if _db.get_setting("app_tour_complete", "") != "1":
        QTimer.singleShot(400, _show_app_tour)


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

    # Initialise local database (used as a local cache / offline buffer)
    _db = Database()
    _db.connect()
    _db.init_db()

    # Ensure Supabase credentials are in os.environ before creating the client
    _load_supabase_credentials(_db)

    # Reset Supabase client so it picks up the freshly loaded env vars
    from auth.supabase_client import reset_client
    reset_client()

    # ── Root stack: [0] LoginView  [1] MainWindow  [2] OnboardingWizard ──────
    _root_stack = QStackedWidget()
    _root_stack.setWindowTitle("DishBoard")
    _root_stack.resize(1200, 800)
    _root_stack.setMinimumSize(900, 600)

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
        # Valid session (or session valid but temporarily offline) — skip login
        _root_stack.setCurrentIndex(1)
        if not user.get("_network_unavailable"):
            _start_cloud_sync(user)
        else:
            _main_window.set_sync_unavailable()
        _main_window.set_account_user(user, _sync_service)
    else:
        # No valid session — require login
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
