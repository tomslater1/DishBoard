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

import threading
from PySide6.QtCore import QObject, QTimer, Signal, Qt

from utils.workers import run_async


class CloudSyncBackgroundService(QObject):
    sync_started  = Signal()
    sync_finished = Signal(int, int)   # pushed, pulled
    sync_error    = Signal(str)

    realtime_connected    = Signal()
    realtime_disconnected = Signal()
    remote_change_received = Signal(str)   # table name

    INTERVAL_MS = 300_000  # 5 minutes (Realtime handles sub-second when connected)

    def __init__(self, user_id: str, parent: QObject | None = None):
        super().__init__(parent)
        self._user_id      = user_id
        self._is_syncing   = False
        self._rt_loop      = None   # asyncio event loop in realtime thread
        self._rt_thread    = None   # daemon thread running realtime loop
        self._rt_channel   = None   # supabase-py RealtimeChannel
        self._timer        = QTimer(self)
        self._timer.timeout.connect(self._sync)
        self._timer.start(self.INTERVAL_MS)

        # Wire remote-change signal to pull handler (QueuedConnection = thread-safe)
        self.remote_change_received.connect(
            self._on_remote_change, Qt.ConnectionType.QueuedConnection
        )

    def sync_now(self) -> None:
        """Trigger an immediate sync (e.g. after login or a manual button press)."""
        self._sync()

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
        if self._rt_loop and not self._rt_loop.is_closed():
            try:
                self._rt_loop.call_soon_threadsafe(self._rt_loop.stop)
            except Exception:
                pass

    # ── Internal sync ─────────────────────────────────────────────────────────

    def _sync(self) -> None:
        if self._is_syncing:
            return

        from auth.supabase_client import is_online
        if not is_online():
            return

        self._is_syncing = True
        self.sync_started.emit()

        def _work():
            from auth.cloud_sync import CloudSyncService
            return CloudSyncService(self._user_id).sync()

        def _done(result):
            self._is_syncing = False
            self.sync_finished.emit(result.pushed, result.pulled)

        def _error(err: str):
            self._is_syncing = False
            self.sync_error.emit(err)

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

            tables = ["recipes", "meal_plans", "shopping_items", "nutrition_logs"]

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
            self.realtime_connected.emit()

            # Keep the loop alive until stopped
            while True:
                await asyncio.sleep(30)

        except Exception:
            self.realtime_disconnected.emit()

    # ── Qt slot: received on main thread ──────────────────────────────────────

    def _on_remote_change(self, table: str) -> None:
        """Pull latest data from Supabase (no push — change came FROM the cloud)."""
        if self._is_syncing:
            return

        from auth.supabase_client import is_online
        if not is_online():
            return

        self._is_syncing = True

        def _pull():
            from auth.cloud_sync import CloudSyncService
            svc = CloudSyncService(self._user_id)
            return svc.pull_all()

        def _done(result):
            self._is_syncing = False
            # Emit sync_finished so views can refresh (0 pushed, N pulled)
            pulled = getattr(result, "pulled", 0) if result else 0
            self.sync_finished.emit(0, pulled)

        def _error(_err: str):
            self._is_syncing = False

        run_async(_pull, on_result=_done, on_error=_error)
