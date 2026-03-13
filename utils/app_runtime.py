"""Application bootstrap/runtime controller for DishBoard."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QStackedWidget, QStyleFactory
from qt_material import apply_stylesheet

from models.database import Database
from utils.data_service import close_db, get_db, set_db
from utils.logging_config import setup_logging
from utils.platform_ops import preferred_ui_font_family
from utils.service_hub import bus as service_bus, registry as service_registry
from utils.startup_health import run_startup_health_check
from utils.theme import manager as theme_manager
from utils.version import APP_VERSION


@dataclass
class AppContext:
    app: QApplication
    db: Database
    root_stack: QStackedWidget
    login_view: object | None = None
    main_window: object | None = None
    onboarding_view: object | None = None
    sync_service: object | None = None
    workflow_engine: object | None = None
    app_tour: object | None = None


class ApplicationController:
    def __init__(self, *, qss_path: str, icon_path: str, icon_dock_path: str, resource_path_fn):
        self._qss_path = qss_path
        self._icon_path = icon_path
        self._icon_dock_path = icon_dock_path
        self._resource_path = resource_path_fn
        self._log = logging.getLogger("dishboard.app")
        self.ctx: AppContext | None = None

    def _load_supabase_credentials(self, db: Database) -> None:
        for db_key, env_key in [("supabase_url", "SUPABASE_URL"), ("supabase_anon_key", "SUPABASE_ANON_KEY")]:
            if not os.environ.get(env_key):
                val = db.get_setting(db_key, "")
                if val:
                    os.environ[env_key] = val

        if not os.environ.get("SUPABASE_URL"):
            from auth.supabase_client import _DEFAULT_KEY, _DEFAULT_URL

            os.environ["SUPABASE_URL"] = _DEFAULT_URL
            os.environ["SUPABASE_ANON_KEY"] = _DEFAULT_KEY

        for env_key, db_key in [("SUPABASE_URL", "supabase_url"), ("SUPABASE_ANON_KEY", "supabase_anon_key")]:
            val = os.environ.get(env_key)
            if val:
                db.set_setting(db_key, val)

    def _ensure_runtime_defaults(self, db: Database) -> None:
        defaults = {
            "in_app_notifications_enabled": "1",
            "telemetry_enabled": "1",
            "posthog_enabled": "1",
            "sentry_enabled": "1",
            "dishy_daily_limit": "50",
        }
        for key, value in defaults.items():
            if db.get_setting(key, "") == "":
                db.set_setting(key, value)

        try:
            from utils.feature_flags import FeatureFlagService

            FeatureFlagService(db).ensure_defaults()
        except Exception as exc:
            self._log.warning("Could not seed feature flag defaults: %s", exc)

    def _apply_app_theme(self, app: QApplication) -> None:
        saved_mode = theme_manager.load()
        if saved_mode == "light":
            light_qss = self._resource_path("assets/styles/theme_light.qss")
            if os.path.exists(light_qss):
                with open(light_qss, encoding="utf-8") as fh:
                    app.setStyleSheet(fh.read())
        else:
            apply_stylesheet(app, theme="dark_amber.xml", extra={"density_scale": "0"})
            if os.path.exists(self._qss_path):
                with open(self._qss_path, encoding="utf-8") as fh:
                    app.setStyleSheet(app.styleSheet() + "\n" + fh.read())

    def _build_app(self) -> AppContext:
        setup_logging()
        os.environ.setdefault("APP_VERSION", APP_VERSION)

        app = QApplication(sys.argv)
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setApplicationName("DishBoard")
        app.setOrganizationName("DishBoard")

        dock_src = self._icon_dock_path if os.path.exists(self._icon_dock_path) else self._icon_path
        if os.path.exists(dock_src):
            app.setWindowIcon(QIcon(dock_src))

        self._apply_app_theme(app)

        font = QFont(preferred_ui_font_family(), 13)
        if not font.exactMatch():
            font = QFont("Arial", 13)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        app.setFont(font)

        db = get_db(init=True)
        set_db(db)
        self._ensure_runtime_defaults(db)
        health_report = run_startup_health_check(db)
        self._log.info(
            "Startup health check: tombstones_removed=%s linked_slots=%s removed_orphans=%s recovered_jobs=%s",
            health_report.get("invalid_tombstones_removed", 0),
            health_report.get("linked_meal_slots", 0),
            int(health_report.get("removed_orphan_slots", 0) or 0)
            + int(health_report.get("removed_stale_unlinked_slots", 0) or 0),
            health_report.get("recovered_workflow_jobs", 0),
        )

        self._load_supabase_credentials(db)
        from auth.supabase_client import reset_client

        reset_client()

        root_stack = QStackedWidget()
        root_stack.setWindowTitle("DishBoard")
        root_stack.resize(1200, 800)
        root_stack.setMinimumSize(900, 600)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        root_stack.move((screen.width() - 1200) // 2, (screen.height() - 800) // 2)
        if os.path.exists(dock_src):
            root_stack.setWindowIcon(QIcon(dock_src))

        ctx = AppContext(app=app, db=db, root_stack=root_stack)
        self.ctx = ctx
        self._build_views()
        return ctx

    def _build_views(self) -> None:
        assert self.ctx is not None
        from main_window import MainWindow
        from views.login import LoginView
        from views.onboarding import OnboardingWizard

        self.ctx.login_view = LoginView()
        self.ctx.login_view.login_successful.connect(self.on_login_success)

        self.ctx.main_window = MainWindow(db=self.ctx.db)
        self.ctx.main_window.sign_in_requested.connect(lambda: self.ctx.root_stack.setCurrentIndex(0))
        self.ctx.main_window.sign_out_requested.connect(self.on_sign_out)
        self.ctx.main_window.session_expired.connect(self.on_session_expired)

        self.ctx.onboarding_view = OnboardingWizard(self.ctx.db)
        self.ctx.onboarding_view.finished.connect(self.on_onboarding_finished)

        self.ctx.root_stack.addWidget(self.ctx.login_view)
        self.ctx.root_stack.addWidget(self.ctx.main_window)
        self.ctx.root_stack.addWidget(self.ctx.onboarding_view)

    def start_user_runtime_services(self, user: dict) -> None:
        assert self.ctx is not None
        user_id = str(user.get("id", "") or "")
        if not user_id:
            return

        try:
            from utils.telemetry import init_telemetry, set_user, track_event

            init_telemetry(self.ctx.db, user_id)
            set_user(user_id)
            track_event("app.user_session_started", {"email": user.get("email", "")}, user_id=user_id)
        except Exception as exc:
            self._log.warning("Telemetry init failed: %s", exc)

        try:
            from utils.notifications import generate_scheduled_notifications
            from utils.workflow_engine import WorkflowEngine, ensure_default_jobs

            ensure_default_jobs(self.ctx.db)
            generate_scheduled_notifications(self.ctx.db, user_id)
            if self.ctx.workflow_engine is not None:
                try:
                    self.ctx.workflow_engine.stop()
                except Exception:
                    pass
                self.ctx.workflow_engine = None
            self.ctx.workflow_engine = WorkflowEngine(self.ctx.db.path, user_id, parent=self.ctx.main_window)
            service_registry.register("workflow_engine", self.ctx.workflow_engine)
            service_bus.publish("workflow.started", {"user_id": user_id})
        except Exception as exc:
            self._log.warning("Runtime service init failed: %s", exc)

    def start_cloud_sync(self, user: dict) -> None:
        assert self.ctx is not None
        from utils.cloud_sync_service import CloudSyncBackgroundService

        if self.ctx.sync_service is not None:
            try:
                self.ctx.sync_service.stop()
            except Exception:
                pass
            service_registry.unregister("cloud_sync")
        self.ctx.sync_service = CloudSyncBackgroundService(user["id"], parent=self.ctx.main_window)
        self.ctx.main_window.set_sync_service(self.ctx.sync_service)
        service_registry.register("cloud_sync", self.ctx.sync_service)
        service_bus.publish("sync.started", {"user_id": str(user.get("id", ""))})

        def _on_initial_sync_done(_pushed: int, _pulled: int) -> None:
            try:
                self.ctx.sync_service.sync_finished.disconnect(_on_initial_sync_done)
            except Exception:
                pass
            self.ctx.main_window.refresh_all_views()
            removed = self.ctx.db.cleanup_orphan_meal_plans()
            removed += self.ctx.db.cleanup_unlinked_cloud_meal_plans()
            if removed:
                self._log.info("MealPlan cleanup removed %s orphan slot(s)", removed)
                self.ctx.main_window.refresh_all_views()
            self.maybe_show_onboarding()

        self.ctx.sync_service.sync_finished.connect(_on_initial_sync_done)
        self.ctx.sync_service.sync_now()
        self.ctx.sync_service.start_realtime()

    def show_app_tour(self) -> None:
        assert self.ctx is not None
        if self.ctx.app_tour is not None:
            return
        from views.app_tour import AppTourOverlay

        self.ctx.app_tour = AppTourOverlay(self.ctx.main_window, self.ctx.db)
        self.ctx.app_tour.finished.connect(self.on_tour_finished)
        self.ctx.app_tour.start()

    def on_tour_finished(self) -> None:
        assert self.ctx is not None
        if self.ctx.app_tour is not None:
            self.ctx.app_tour.hide()
            self.ctx.app_tour.deleteLater()
            self.ctx.app_tour = None
        self.ctx.db.set_setting("app_tour_complete", "1")
        if self.ctx.sync_service is not None:
            try:
                self.ctx.sync_service.sync_now()
            except Exception:
                pass

    def maybe_show_onboarding(self) -> None:
        assert self.ctx is not None
        if self.ctx.db.get_setting("onboarding_complete", "") != "1":
            self.ctx.root_stack.setCurrentIndex(2)

    def on_login_success(self, user: dict) -> None:
        assert self.ctx is not None
        if self.ctx.db.ensure_active_user_scope(user["id"]):
            self.ctx.main_window.refresh_all_views()
        self.start_user_runtime_services(user)
        self.ctx.root_stack.setCurrentIndex(1)
        self.ctx.main_window.go_home()
        self.start_cloud_sync(user)
        self.ctx.main_window.set_account_user(user, self.ctx.sync_service)

    def on_sign_out(self) -> None:
        assert self.ctx is not None
        if self.ctx.sync_service is not None:
            try:
                self.ctx.sync_service.stop()
            except Exception:
                pass
            self.ctx.sync_service = None
        service_registry.unregister("cloud_sync")
        if self.ctx.workflow_engine is not None:
            try:
                self.ctx.workflow_engine.stop()
            except Exception:
                pass
            self.ctx.workflow_engine = None
        service_registry.unregister("workflow_engine")
        service_bus.publish("session.signed_out", {})
        if self.ctx.login_view is not None:
            self.ctx.login_view.reset()
        self.ctx.root_stack.setCurrentIndex(0)

    def on_session_expired(self, email: str) -> None:
        assert self.ctx is not None
        from widgets.reauth_dialog import ReauthDialog

        dlg = ReauthDialog(email=email, parent=self.ctx.main_window)
        dlg.reauth_successful.connect(self.on_reauth_success)
        dlg.sign_out_requested.connect(lambda: self.ctx.root_stack.setCurrentIndex(0))
        dlg.exec()

    def on_reauth_success(self) -> None:
        from auth.session_manager import get_current_user

        user = get_current_user()
        if user and not user.get("_network_unavailable"):
            self.start_cloud_sync(user)

    def on_onboarding_finished(self) -> None:
        assert self.ctx is not None
        self.ctx.root_stack.setCurrentIndex(1)
        if self.ctx.sync_service is not None:
            try:
                self.ctx.sync_service.sync_now()
            except Exception:
                pass
        if self.ctx.db.get_setting("app_tour_complete", "") != "1":
            QTimer.singleShot(400, self.show_app_tour)

    def _bootstrap_session(self) -> None:
        assert self.ctx is not None
        from auth.session_manager import get_current_user

        user = get_current_user()
        if user:
            if self.ctx.db.ensure_active_user_scope(user["id"]):
                self.ctx.main_window.refresh_all_views()
            self.ctx.root_stack.setCurrentIndex(1)
            self.start_user_runtime_services(user)
            if not user.get("_network_unavailable"):
                self.start_cloud_sync(user)
            else:
                self.ctx.main_window.set_sync_unavailable()
                self.maybe_show_onboarding()
            self.ctx.main_window.set_account_user(user, self.ctx.sync_service)
        else:
            self.ctx.root_stack.setCurrentIndex(0)

    def _start_update_check(self) -> None:
        assert self.ctx is not None
        from utils.updater import check_for_update
        from utils.workers import run_async

        def _on_update_result(info):
            if info:
                from widgets.update_dialog import UpdateDialog

                UpdateDialog(info, parent=self.ctx.root_stack).exec()

        run_async(check_for_update, on_result=_on_update_result, on_error=lambda _: None)

    def run(self) -> int:
        ctx = self._build_app()
        self._bootstrap_session()
        ctx.root_stack.show()
        self._start_update_check()
        exit_code = ctx.app.exec()
        service_registry.clear()
        set_db(None)
        close_db()
        return exit_code
