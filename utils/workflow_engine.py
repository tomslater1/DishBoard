"""Lightweight recurring workflow runner backed by SQLite job rows."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QObject, QTimer, Signal

from models.database import Database
from utils.workers import run_async

_LOG = logging.getLogger("dishboard.workflows")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).isoformat(timespec="seconds")


def ensure_default_jobs(db: Database) -> None:
    """Create/update default recurring jobs (idempotent)."""
    now = _utc_now()
    db.upsert_workflow_job(
        "notifications.scan",
        "notifications.scan",
        run_every_minutes=15,
        next_run_at=_iso(now + timedelta(minutes=1)),
    )
    db.upsert_workflow_job(
        "notifications.cleanup",
        "notifications.cleanup",
        run_every_minutes=24 * 60,
        next_run_at=_iso(now + timedelta(minutes=10)),
    )
    db.upsert_workflow_job(
        "flags.refresh",
        "flags.refresh",
        run_every_minutes=180,
        next_run_at=_iso(now + timedelta(minutes=2)),
    )


class WorkflowEngine(QObject):
    """Runs due jobs from workflow_jobs table on a timer."""

    job_finished = Signal(str, bool, str)  # job_key, ok, message

    INTERVAL_MS = 60_000

    def __init__(self, db_path: str, user_id: str = "", parent: QObject | None = None):
        super().__init__(parent)
        self._db_path = db_path
        self._user_id = user_id or ""
        self._running = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.run_due_jobs)
        self._timer.start(self.INTERVAL_MS)

    def set_user_id(self, user_id: str) -> None:
        self._user_id = user_id or ""

    def stop(self) -> None:
        self._timer.stop()

    def run_due_jobs(self) -> None:
        if self._running:
            return

        self._running = True

        def _work():
            return self._run_due_jobs_sync()

        def _done(results: list[tuple[str, bool, str]]):
            self._running = False
            for job_key, ok, msg in results:
                self.job_finished.emit(job_key, ok, msg)

        def _error(err: str):
            self._running = False
            _LOG.warning("workflow runner failed: %s", err)

        run_async(_work, on_result=_done, on_error=_error)

    def _open_db(self) -> Database:
        db = Database(self._db_path)
        db.connect()
        return db

    def _run_due_jobs_sync(self) -> list[tuple[str, bool, str]]:
        db = self._open_db()
        results: list[tuple[str, bool, str]] = []
        now_iso = _iso()
        try:
            jobs = db.get_due_workflow_jobs(now_iso, limit=6)
            for job in jobs:
                key = str(job.get("job_key") or f"job:{job.get('id')}")
                run_every = max(1, int(job.get("run_every_minutes") or 60))
                next_run = _iso(_utc_now() + timedelta(minutes=run_every))
                ok = True
                msg = "ok"

                try:
                    payload_raw = job.get("payload_json") or "{}"
                    payload = json.loads(payload_raw) if isinstance(payload_raw, str) else (payload_raw or {})
                    self._execute_job(db, str(job.get("job_type") or ""), payload)
                except Exception as exc:
                    ok = False
                    msg = str(exc)

                db.mark_workflow_job_result(job["id"], ok=ok, next_run_at=next_run, last_error=("" if ok else msg))
                results.append((key, ok, msg))
        finally:
            db.close()
        return results

    def _execute_job(self, db: Database, job_type: str, payload: dict) -> None:
        if job_type == "notifications.scan":
            from utils.notifications import generate_scheduled_notifications

            created = generate_scheduled_notifications(db, self._user_id)
            _LOG.info("workflow notifications.scan created=%s", created)
            return

        if job_type == "notifications.cleanup":
            from utils.notifications import cleanup_old_notifications

            removed = cleanup_old_notifications(db, older_than_days=int(payload.get("days", 30) or 30))
            _LOG.info("workflow notifications.cleanup removed=%s", removed)
            return

        if job_type == "flags.refresh":
            from utils.feature_flags import FeatureFlagService

            svc = FeatureFlagService(db, self._user_id)
            count, reason = svc.refresh_remote_from_supabase()
            _LOG.info("workflow flags.refresh cached=%s reason=%s", count, reason)
            return

        raise RuntimeError(f"unknown_workflow_job:{job_type}")
