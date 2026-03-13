"""
CloudSyncBackgroundService — QTimer-driven background sync + Realtime WebSocket.

- INTERVAL_MS controls polling frequency (fallback when realtime is active)
- _is_syncing guard prevents concurrent cycles
- Each cycle dispatches a run_async worker (never blocks the main thread)
- Realtime subscriptions run in a daemon thread with their own asyncio loop
- Qt Signals are the bridge from the asyncio thread → Qt main thread
- Signals propagate status to the sidebar SyncIndicator widget
"""

from __future__ import annotations

import logging
import threading
from PySide6.QtCore import QObject, QTimer, Signal, Qt

from utils.sync_resilience import SyncResilienceController
from utils.workers import run_async


class CloudSyncBackgroundService(QObject):
    sync_started  = Signal()
    sync_finished = Signal(int, int)   # pushed, pulled
    sync_error    = Signal(str)
    runtime_status_changed = Signal(dict)

    realtime_connected    = Signal()
    realtime_disconnected = Signal()
    remote_change_received = Signal(str)   # table name

    INTERVAL_MS = 300_000  # 5 minutes (Realtime handles sub-second when connected)

    def __init__(self, user_id: str, parent: QObject | None = None):
        super().__init__(parent)
        self._user_id      = user_id
        self._is_syncing   = False
        self._log          = logging.getLogger("dishboard.sync.bg")
        self._resilience   = SyncResilienceController()
        self._rt_loop      = None   # asyncio event loop in realtime thread
        self._rt_thread    = None   # daemon thread running realtime loop
        self._rt_channel   = None   # supabase-py RealtimeChannel
        self._timer        = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)
        self._timer.start(self.INTERVAL_MS)
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._on_retry_timeout)

        # Wire remote-change signal to pull handler (QueuedConnection = thread-safe)
        self.remote_change_received.connect(
            self._on_remote_change, Qt.ConnectionType.QueuedConnection
        )

    def sync_now(self) -> None:
        """Trigger an immediate sync (e.g. after login or a manual button press)."""
        self._sync(force=False, source="manual")

    def retry_now(self) -> None:
        """Force a manual retry, bypassing temporary backoff state."""
        self._sync(force=True, source="manual_retry")

    def start_realtime(self) -> None:
        """Spawn the realtime subscription thread (idempotent)."""
        if self._rt_thread and self._rt_thread.is_alive():
            return
        self._rt_thread = threading.Thread(
            target=self._realtime_thread_main, daemon=True, name="DishiboardRealtime"
        )
        self._rt_thread.start()

    def stop(self) -> None:
        """Stop the background timer and realtime subscription."""
        self._timer.stop()
        self._retry_timer.stop()
        if self._rt_loop and not self._rt_loop.is_closed():
            try:
                self._rt_loop.call_soon_threadsafe(self._rt_loop.stop)
            except Exception:
                pass

    def runtime_status(self) -> dict:
        status = self._resilience.status()
        status["is_syncing"] = bool(self._is_syncing)
        status["realtime_connected"] = bool(self._rt_thread and self._rt_thread.is_alive())
        return status

    # ── Internal sync ─────────────────────────────────────────────────────────

    def _on_timer_tick(self) -> None:
        self._sync(force=False, source="timer")

    def _on_retry_timeout(self) -> None:
        self._sync(force=False, source="retry")

    def _schedule_retry(self, retry_in_seconds: int) -> None:
        delay_ms = max(1_000, int(max(1, retry_in_seconds) * 1000))
        if self._retry_timer.isActive():
            remaining = self._retry_timer.remainingTime()
            if 0 <= remaining <= delay_ms:
                return
            self._retry_timer.stop()
        self._retry_timer.start(delay_ms)

    def _emit_resilience_error(self, reason: str, retry_in_seconds: int, last_error: str = "") -> None:
        if reason == "circuit_open":
            msg = f"Sync paused after repeated failures. Retrying in {retry_in_seconds}s."
        elif reason == "backoff":
            msg = f"Sync recovering. Retrying in {retry_in_seconds}s."
        elif reason == "offline":
            msg = f"Offline. Sync will retry in {retry_in_seconds}s."
        else:
            msg = f"Sync issue detected. Retrying in {retry_in_seconds}s."
        if last_error:
            msg = f"{msg} ({last_error[:140]})"
        self.sync_error.emit(msg)

    def _sync(self, *, force: bool = False, source: str = "timer") -> None:
        if self._is_syncing:
            return
        allowed, retry_in, reason = self._resilience.can_attempt(force=force)
        if not allowed:
            self._schedule_retry(retry_in)
            # Keep logs concise by only surfacing non-timer blocks.
            if source != "timer":
                self._emit_resilience_error(reason, retry_in, self._resilience.status().get("last_error", ""))
            self.runtime_status_changed.emit(self.runtime_status())
            return

        from auth.supabase_client import is_online
        if not is_online():
            status = self._resilience.record_failure("offline")
            self._emit_resilience_error("offline", int(status.get("retry_in_seconds", 5)), "offline")
            self._schedule_retry(int(status.get("retry_in_seconds", 5)))
            self.runtime_status_changed.emit(self.runtime_status())
            return

        self._is_syncing = True
        self.sync_started.emit()
        self.runtime_status_changed.emit(self.runtime_status())

        def _work():
            from auth.cloud_sync import CloudSyncService
            return CloudSyncService(self._user_id).sync()

        def _done(result):
            self._is_syncing = False
            pushed = int(getattr(result, "pushed", 0) or 0)
            pulled = int(getattr(result, "pulled", 0) or 0)
            self.sync_finished.emit(pushed, pulled)

            errors = list(getattr(result, "errors", []) or [])
            if errors:
                status = self._resilience.record_failure("; ".join(errors[:2]))
                retry_s = int(status.get("retry_in_seconds", 5) or 5)
                self._emit_resilience_error(status.get("reason", "backoff"), retry_s, status.get("last_error", ""))
                self._schedule_retry(retry_s)
            else:
                self._resilience.record_success()
            self.runtime_status_changed.emit(self.runtime_status())

        def _error(err: str):
            self._is_syncing = False
            status = self._resilience.record_failure(err)
            retry_s = int(status.get("retry_in_seconds", 5) or 5)
            self._emit_resilience_error(status.get("reason", "backoff"), retry_s, status.get("last_error", ""))
            self._schedule_retry(retry_s)
            self.runtime_status_changed.emit(self.runtime_status())

        run_async(_work, on_result=_done, on_error=_error)

    # ── Realtime thread ───────────────────────────────────────────────────────

    def _realtime_thread_main(self) -> None:
        """Entry point for the daemon thread; creates and runs an asyncio loop."""
        import asyncio
        loop = asyncio.new_event_loop()
        self._rt_loop = loop
        try:
            loop.run_until_complete(self._realtime_main())
        except Exception:
            pass
        finally:
            try:
                loop.close()
            except Exception:
                pass
            self.realtime_disconnected.emit()

    async def _realtime_main(self) -> None:
        """Subscribe to Postgres changes on all 4 tables via Supabase Realtime."""
        import asyncio
        try:
            from auth.supabase_client import get_client
            sb = get_client()
            if not sb:
                return

            # Obtain current user_id to filter by
            session = sb.auth.get_session()
            if not session or not session.session:
                return
            user_id = str(session.session.user.id)

            channel = sb.channel("dishboard-changes")
            self._rt_channel = channel

            tables = ["recipes", "meal_plans", "shopping_items", "nutrition_logs", "pantry_items"]

            def _make_handler(table: str):
                def _handler(payload):
                    self.remote_change_received.emit(table)
                return _handler

            for table in tables:
                channel.on_postgres_changes(
                    event="*",
                    schema="public",
                    table=table,
                    filter=f"user_id=eq.{user_id}",
                    callback=_make_handler(table),
                )

            await channel.subscribe()
            self._log.info("Realtime connected for user %s", user_id[:8])
            self.realtime_connected.emit()
            self.runtime_status_changed.emit(self.runtime_status())

            # Keep the loop alive until stopped
            while True:
                await asyncio.sleep(30)

        except Exception:
            self.realtime_disconnected.emit()
            self.runtime_status_changed.emit(self.runtime_status())

    # ── Qt slot: received on main thread ──────────────────────────────────────

    def _on_remote_change(self, table: str) -> None:
        """Pull latest data from Supabase (no push — change came FROM the cloud)."""
        if self._is_syncing:
            return
        allowed, retry_in, reason = self._resilience.can_attempt(force=False)
        if not allowed:
            self._schedule_retry(retry_in)
            self.runtime_status_changed.emit(self.runtime_status())
            return

        from auth.supabase_client import is_online
        if not is_online():
            status = self._resilience.record_failure(f"offline during realtime pull:{table}")
            retry_s = int(status.get("retry_in_seconds", 5) or 5)
            self._schedule_retry(retry_s)
            self.runtime_status_changed.emit(self.runtime_status())
            return

        self._is_syncing = True
        self.runtime_status_changed.emit(self.runtime_status())

        def _pull():
            from auth.cloud_sync import CloudSyncService
            svc = CloudSyncService(self._user_id)
            return svc.pull_all()

        def _done(result):
            self._is_syncing = False
            # Emit sync_finished so views can refresh (0 pushed, N pulled)
            pulled = getattr(result, "pulled", 0) if result else 0
            self.sync_finished.emit(0, pulled)
            errors = list(getattr(result, "errors", []) or [])
            if errors:
                status = self._resilience.record_failure("; ".join(errors[:2]))
                retry_s = int(status.get("retry_in_seconds", 5) or 5)
                self._emit_resilience_error(status.get("reason", "backoff"), retry_s, status.get("last_error", ""))
                self._schedule_retry(retry_s)
            else:
                self._resilience.record_success()
            self.runtime_status_changed.emit(self.runtime_status())

        def _error(err: str):
            self._is_syncing = False
            status = self._resilience.record_failure(err)
            retry_s = int(status.get("retry_in_seconds", 5) or 5)
            self._emit_resilience_error(status.get("reason", "backoff"), retry_s, status.get("last_error", ""))
            self._schedule_retry(retry_s)
            self.runtime_status_changed.emit(self.runtime_status())

        run_async(_pull, on_result=_done, on_error=_error)
