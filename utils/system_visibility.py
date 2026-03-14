"""Shared runtime visibility model for Monitoring, account sync copy, and producers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from models.database import Database, _parse_sync_ts
from utils.service_hub import bus as service_bus, registry as service_registry

_MODULE_ORDER = ["recipes", "planner", "shopping", "pantry", "nutrition", "dishy", "system"]
_SEVERITY_ORDER = {"quiet": 0, "info": 1, "warning": 2, "critical": 3}
_WORK_TIMEOUT_SECONDS = {"sync": 300, "ai": 180, "job": 240, "task": 180}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _dt(value: str | None) -> datetime | None:
    return _parse_sync_ts(value or "")


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now_utc()).isoformat(timespec="seconds")


def _relative_time(value: str | None) -> str:
    dt = _dt(value)
    if dt is None:
        return "not yet"
    delta = _now_utc() - dt
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 45:
        return "just now"
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago"
    if seconds < 86400:
        return f"{max(1, seconds // 3600)}h ago"
    return f"{max(1, seconds // 86400)}d ago"


def _display_time(value: str | None) -> str:
    dt = _dt(value)
    if dt is None:
        return "n/a"
    return dt.astimezone().strftime("%d %b %H:%M")


def _age_seconds(value: str | None) -> int:
    dt = _dt(value)
    if dt is None:
        return 0
    return max(0, int((_now_utc() - dt).total_seconds()))


def _max_severity(*levels: str) -> str:
    return max(levels, key=lambda item: _SEVERITY_ORDER.get(item, 0))


def _module_table_name(module: str) -> str:
    return {
        "recipes": "recipes",
        "planner": "meal_plans",
        "shopping": "shopping_items",
        "pantry": "pantry_items",
        "nutrition": "nutrition_logs",
        "dishy": "dishy_chat_history",
        "system": "system",
    }.get(module, module)


def _activity_type(change: "RecentChange") -> str:
    if change.kind in {"sync"}:
        return "sync"
    if change.kind in {"ai"}:
        return "ai"
    if change.kind in {"workflow"}:
        return "job"
    if change.kind in {"notification"}:
        return "notification"
    return "user_change"


def _change_severity(change: "RecentChange") -> str:
    source = str(change.source or "")
    title = str(change.title or "").lower()
    if "failed" in title or "blocked" in title or source.endswith("_failed"):
        return "warning"
    if change.kind in {"sync", "workflow", "notification"}:
        return "info"
    if change.kind in {"ai"} and "completed" in title:
        return "info"
    return "quiet"


def _sync_is_offline(runtime: dict[str, Any]) -> bool:
    text = str(runtime.get("last_error") or "").lower()
    return "offline" in text


def _normalise_attention_reason(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


@dataclass(slots=True)
class ActiveWorkItem:
    key: str
    kind: str
    module: str
    title: str
    detail: str
    started_at: str
    attention_reason: str = ""
    timeout_at: str = ""
    status: str = "active"
    error: str = ""


@dataclass(slots=True)
class ModuleFreshness:
    module: str
    state: str
    label: str
    detail: str
    updated_at: str
    unsynced_count: int = 0
    freshness_age_seconds: int = 0
    sync_age_seconds: int = 0
    confidence: str = "strong"
    stale_reason: str = ""
    covered_by_sync: bool = False


@dataclass(slots=True)
class RecentChange:
    kind: str
    module: str
    title: str
    detail: str
    occurred_at: str
    source: str
    target: str


@dataclass(slots=True)
class VisibilityAction:
    action_id: str
    label: str
    target: str
    payload: dict[str, Any] = field(default_factory=dict)
    style: str = "secondary"


@dataclass(slots=True)
class VisibilityDigestItem:
    kind: str
    module: str
    title: str
    detail: str
    count: int
    occurred_at: str
    severity: str = "info"
    activity_type: str = "user_change"


@dataclass(slots=True)
class VisibilityPolicyResult:
    severity: str
    overall_state: str
    attention_reasons: list[str]
    recommended_actions: list[VisibilityAction]
    feed_summary: list[VisibilityDigestItem]


@dataclass(slots=True)
class VisibilitySnapshot:
    overall_state: str
    severity: str
    summary: str
    detail: str
    active_work: list[ActiveWorkItem] = field(default_factory=list)
    global_freshness: dict[str, Any] = field(default_factory=dict)
    module_freshness: list[ModuleFreshness] = field(default_factory=list)
    recent_changes: list[RecentChange] = field(default_factory=list)
    feed_summary: list[VisibilityDigestItem] = field(default_factory=list)
    recommended_actions: list[VisibilityAction] = field(default_factory=list)
    attention_reasons: list[str] = field(default_factory=list)
    sync_runtime: dict[str, Any] = field(default_factory=dict)
    last_updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class VisibilityWorkHandle:
    """Small scoped work handle so producers do not manually pair begin/finish."""

    def __init__(self, service: "SystemVisibilityService", key: str):
        self._service = service
        self._key = str(key)
        self._closed = False

    def update(self, detail: str) -> None:
        if not self._closed:
            self._service.update_work(self._key, detail=detail)

    def finish(self) -> None:
        if not self._closed:
            self._closed = True
            self._service.finish_work(self._key)

    def fail(self, error: str = "") -> None:
        if not self._closed:
            self._closed = True
            self._service.fail_work(self._key, error=error)

    def __enter__(self) -> "VisibilityWorkHandle":
        return self

    def __exit__(self, _exc_type, exc, _tb) -> bool:
        if exc is not None:
            self.fail(str(exc))
        else:
            self.finish()
        return False


def describe_sync_runtime(runtime: dict[str, Any]) -> tuple[str, str]:
    retry_in = int(runtime.get("retry_in_seconds", 0) or 0)
    if runtime.get("is_syncing"):
        return "Syncing now", "Cloud changes are moving across devices."
    if _sync_is_offline(runtime):
        detail = "Working offline. Changes will retry automatically."
        if retry_in > 0:
            detail = f"Working offline. Retry in about {retry_in}s."
        return "Offline", detail
    if runtime.get("circuit_open"):
        return "Recovering", f"Sync paused after repeated failures. Retry in about {retry_in}s."
    if retry_in > 0 or int(runtime.get("consecutive_failures", 0) or 0) > 0:
        return "Recovering", f"Cloud sync is retrying. Next attempt in about {max(1, retry_in)}s."
    if runtime.get("last_success_at"):
        return "Live sync enabled", f"Last successful sync {_relative_time(runtime.get('last_success_at'))}."
    return "Waiting for first sync", "Sign in to start syncing changes across devices."


def describe_snapshot(snapshot: VisibilitySnapshot | None) -> tuple[str, str]:
    if snapshot is None:
        return "All systems calm", "Everything looks up to date."
    if snapshot.overall_state == "syncing":
        return "Syncing your latest changes", snapshot.detail
    if snapshot.overall_state == "ai_busy":
        return "Dishy is working", snapshot.detail
    if snapshot.overall_state == "offline":
        return "Working offline", snapshot.detail
    if snapshot.overall_state == "recovering":
        return "System recovering", snapshot.detail
    if snapshot.overall_state == "stale":
        return "Changes waiting to sync", snapshot.detail
    if snapshot.severity == "critical":
        return "System needs attention", snapshot.detail
    if snapshot.severity == "warning":
        return "A few things need review", snapshot.detail
    return "All systems calm", snapshot.detail


class SystemVisibilityService(QObject):
    """Main-thread visibility policy engine for Monitoring and shared runtime copy."""

    snapshot_changed = Signal(object)

    def __init__(self, db: Database, parent: QObject | None = None):
        super().__init__(parent)
        self._db = db
        self._sync_service = None
        self._workflow_engine = None
        self._sync_runtime: dict[str, Any] = {}
        self._workflow_runtime: dict[str, Any] = {}
        self._active_work: dict[str, ActiveWorkItem] = {}
        self._runtime_events: list[dict[str, Any]] = []
        self._snapshot = VisibilitySnapshot(
            overall_state="healthy",
            severity="quiet",
            summary="All systems calm",
            detail="Everything looks up to date.",
            last_updated_at=_iso(),
        )
        self._sync_subscriptions: list[tuple[object, str, Callable]] = []
        self._workflow_subscriptions: list[tuple[object, str, Callable]] = []
        service_bus.subscribe("workflow.started", lambda _payload: self.bind_workflow_engine(service_registry.get("workflow_engine")))
        service_bus.subscribe("session.signed_out", lambda _payload: self.clear_runtime())
        self.bind_workflow_engine(service_registry.get("workflow_engine"))
        self.refresh()

    def snapshot(self) -> VisibilitySnapshot:
        return self._snapshot

    def clear_runtime(self) -> None:
        self._sync_runtime = {}
        self._workflow_runtime = {}
        self._active_work.clear()
        self._runtime_events.clear()
        self.refresh()

    def start_work(
        self,
        key: str,
        kind: str,
        module: str,
        title: str,
        detail: str = "",
        *,
        timeout_seconds: int | None = None,
        attention_reason: str = "",
    ) -> VisibilityWorkHandle:
        started_at = _iso()
        timeout = timeout_seconds if timeout_seconds is not None else _WORK_TIMEOUT_SECONDS.get(str(kind), 180)
        timeout_at = _iso(_now_utc() + timedelta(seconds=max(30, int(timeout))))
        item = ActiveWorkItem(
            key=str(key),
            kind=str(kind),
            module=str(module),
            title=str(title),
            detail=str(detail),
            started_at=started_at,
            attention_reason=_normalise_attention_reason(attention_reason),
            timeout_at=timeout_at,
        )
        self._active_work[item.key] = item
        self.refresh()
        return VisibilityWorkHandle(self, item.key)

    def begin_work(self, key: str, kind: str, module: str, title: str, detail: str = "") -> VisibilityWorkHandle:
        return self.start_work(key, kind, module, title, detail)

    def update_work(self, key: str, *, detail: str | None = None, attention_reason: str | None = None) -> None:
        item = self._active_work.get(str(key))
        if item is None:
            return
        if detail is not None:
            item.detail = str(detail)
        if attention_reason is not None:
            item.attention_reason = _normalise_attention_reason(attention_reason)
        self.refresh()

    def finish_work(self, key: str) -> None:
        item = self._active_work.pop(str(key), None)
        if item is not None:
            self._record_runtime_event(
                kind=item.kind,
                module=item.module,
                title=item.title,
                detail=item.detail,
                source=f"runtime.{item.kind}.completed",
                target=item.key,
                severity="info",
            )
        self.refresh()

    def fail_work(self, key: str, error: str = "") -> None:
        item = self._active_work.pop(str(key), None)
        if item is not None:
            message = str(error or item.error or "Task failed").strip()
            self._record_runtime_event(
                kind=item.kind,
                module=item.module,
                title=f"{item.title} failed",
                detail=message[:180],
                source=f"runtime.{item.kind}.failed",
                target=item.key,
                severity="warning",
            )
        self.refresh()

    def bind_sync_service(self, service) -> None:
        if self._sync_service is service:
            return
        for obj, signal_name, handler in self._sync_subscriptions:
            try:
                getattr(obj, signal_name).disconnect(handler)
            except Exception:
                pass
        self._sync_subscriptions = []
        self._sync_service = service
        if service is None:
            self._sync_runtime = {}
            self.refresh()
            return

        def _connect(signal_name: str, handler) -> None:
            signal = getattr(service, signal_name, None)
            if signal is None:
                return
            signal.connect(handler)
            self._sync_subscriptions.append((service, signal_name, handler))

        _connect("runtime_status_changed", self._on_sync_runtime_changed)
        _connect("sync_started", self._on_sync_started)
        _connect("sync_finished", self._on_sync_finished)
        _connect("sync_error", self._on_sync_error)

        if hasattr(service, "runtime_status"):
            try:
                self._sync_runtime = service.runtime_status() or {}
            except Exception:
                self._sync_runtime = {}
        self.refresh()

    def bind_workflow_engine(self, engine) -> None:
        if self._workflow_engine is engine:
            return
        for obj, signal_name, handler in self._workflow_subscriptions:
            try:
                getattr(obj, signal_name).disconnect(handler)
            except Exception:
                pass
        self._workflow_subscriptions = []
        self._workflow_engine = engine
        if engine is None:
            self._workflow_runtime = {}
            self._active_work.pop("workflow_engine", None)
            self.refresh()
            return

        def _connect(signal_name: str, handler) -> None:
            signal = getattr(engine, signal_name, None)
            if signal is None:
                return
            signal.connect(handler)
            self._workflow_subscriptions.append((engine, signal_name, handler))

        _connect("runtime_status_changed", self._on_workflow_runtime_changed)
        if hasattr(engine, "runtime_status"):
            try:
                self._workflow_runtime = engine.runtime_status() or {}
            except Exception:
                self._workflow_runtime = {}
        self.refresh()

    def refresh(self) -> None:
        self._expire_stale_work()
        self._snapshot = self._build_snapshot()
        self.snapshot_changed.emit(self._snapshot)

    def _record_runtime_event(
        self,
        *,
        kind: str,
        module: str,
        title: str,
        detail: str,
        source: str,
        target: str,
        severity: str = "info",
    ) -> None:
        self._runtime_events.append(
            {
                "kind": str(kind),
                "module": str(module),
                "title": str(title),
                "detail": str(detail),
                "occurred_at": _iso(),
                "source": str(source),
                "target": str(target),
                "severity": str(severity),
            }
        )
        self._runtime_events = self._runtime_events[-40:]

    def _expire_stale_work(self) -> None:
        expired: list[ActiveWorkItem] = []
        now = _now_utc()
        for key, item in list(self._active_work.items()):
            timeout_at = _dt(item.timeout_at)
            if timeout_at is not None and timeout_at <= now:
                expired.append(self._active_work.pop(key))
        for item in expired:
            self._record_runtime_event(
                kind=item.kind,
                module=item.module,
                title=f"{item.title} timed out",
                detail=item.detail or "Background work exceeded its expected time window.",
                source=f"runtime.{item.kind}.timeout",
                target=item.key,
                severity="warning",
            )

    def _on_sync_started(self) -> None:
        self.start_work(
            "sync.runtime",
            "sync",
            "system",
            "Syncing changes",
            "Cloud sync is moving your latest edits.",
            timeout_seconds=300,
            attention_reason="sync_active",
        )

    def _on_sync_finished(self, pushed: int, pulled: int) -> None:
        self._active_work.pop("sync.runtime", None)
        if self._sync_service is not None and hasattr(self._sync_service, "runtime_status"):
            try:
                self._sync_runtime = self._sync_service.runtime_status() or {}
            except Exception:
                self._sync_runtime = {}
        self._record_runtime_event(
            kind="sync",
            module="system",
            title="Cloud sync completed",
            detail=f"pushed={int(pushed or 0)} · pulled={int(pulled or 0)}",
            source="runtime.sync.completed",
            target="sync.runtime",
            severity="info",
        )
        self.refresh()

    def _on_sync_error(self, message: str) -> None:
        self._active_work.pop("sync.runtime", None)
        if self._sync_service is not None and hasattr(self._sync_service, "runtime_status"):
            try:
                self._sync_runtime = self._sync_service.runtime_status() or {}
            except Exception:
                self._sync_runtime = {}
        self._record_runtime_event(
            kind="sync",
            module="system",
            title="Cloud sync failed",
            detail=str(message or "").strip()[:180],
            source="runtime.sync.failed",
            target="sync.runtime",
            severity="warning",
        )
        self.refresh()

    def _on_sync_runtime_changed(self, status: dict) -> None:
        previous = dict(self._sync_runtime)
        self._sync_runtime = dict(status or {})
        if self._sync_runtime.get("is_syncing"):
            self.start_work(
                "sync.runtime",
                "sync",
                "system",
                "Syncing changes",
                "Cloud sync is moving your latest edits.",
                timeout_seconds=300,
                attention_reason="sync_active",
            )
        else:
            self._active_work.pop("sync.runtime", None)
        if _sync_is_offline(self._sync_runtime) and previous.get("last_error") != self._sync_runtime.get("last_error"):
            self._record_runtime_event(
                kind="sync",
                module="system",
                title="Cloud sync offline",
                detail=str(self._sync_runtime.get("last_error") or "Offline"),
                source="runtime.sync.offline",
                target="sync.runtime",
                severity="warning",
            )
        self.refresh()

    def _on_workflow_runtime_changed(self, status: dict) -> None:
        self._workflow_runtime = dict(status or {})
        if self._workflow_runtime.get("is_running"):
            self.start_work(
                "workflow_engine",
                "job",
                "system",
                "Background jobs running",
                str(self._workflow_runtime.get("detail") or "Scheduled maintenance is running."),
                timeout_seconds=240,
                attention_reason="job_running",
            )
        else:
            self._active_work.pop("workflow_engine", None)
        for key, ok, msg in self._workflow_runtime.get("last_results", [])[:3]:
            if not ok:
                self._record_runtime_event(
                    kind="workflow",
                    module="system",
                    title="Background job failed",
                    detail=f"{key}: {msg}"[:180],
                    source="runtime.workflow.failed",
                    target=str(key),
                    severity="warning",
                )
        self.refresh()

    def _build_snapshot(self) -> VisibilitySnapshot:
        integrity = self._db.get_sync_integrity_report()
        updates = self._db.get_visibility_module_updates()
        recent_changes = self._collect_recent_changes()
        active_work = self._prioritize_active_work(list(self._active_work.values()))
        modules = self._build_module_freshness(integrity, updates, active_work)
        attention_reasons = self._build_attention_reasons(integrity, modules, active_work, recent_changes)
        overall_state = self._build_overall_state(modules, active_work, attention_reasons)
        severity = self._build_severity(integrity, modules, active_work, recent_changes, attention_reasons)
        feed_summary = self._build_feed_summary(recent_changes)
        recommended_actions = self._build_recommended_actions(modules, attention_reasons, severity)
        global_freshness = self._build_global_freshness(integrity, modules, severity)
        summary, detail = self._describe_snapshot(overall_state, severity, global_freshness, modules, active_work, attention_reasons)
        return VisibilitySnapshot(
            overall_state=overall_state,
            severity=severity,
            summary=summary,
            detail=detail,
            active_work=active_work,
            global_freshness=global_freshness,
            module_freshness=modules,
            recent_changes=recent_changes,
            feed_summary=feed_summary,
            recommended_actions=recommended_actions,
            attention_reasons=attention_reasons,
            sync_runtime=dict(self._sync_runtime),
            last_updated_at=_iso(),
        )

    def _collect_recent_changes(self) -> list[RecentChange]:
        raw = [RecentChange(**row) for row in self._db.get_visibility_recent_changes(limit=32)]
        runtime = [
            RecentChange(
                kind=str(event.get("kind") or "task"),
                module=str(event.get("module") or "system"),
                title=str(event.get("title") or ""),
                detail=str(event.get("detail") or ""),
                occurred_at=str(event.get("occurred_at") or ""),
                source=str(event.get("source") or ""),
                target=str(event.get("target") or ""),
            )
            for event in self._runtime_events
            if _dt(event.get("occurred_at"))
        ]
        combined = raw + runtime
        combined.sort(key=lambda item: _dt(item.occurred_at) or datetime.fromtimestamp(0, tz=timezone.utc), reverse=True)
        return combined[:30]

    def _prioritize_active_work(self, items: list[ActiveWorkItem]) -> list[ActiveWorkItem]:
        priority = {"sync": 0, "ai": 1, "job": 2, "task": 3}
        return sorted(
            items,
            key=lambda item: (priority.get(item.kind, 9), _dt(item.started_at) or datetime.fromtimestamp(0, tz=timezone.utc)),
        )

    def _build_module_freshness(
        self,
        integrity: dict[str, Any],
        updates: dict[str, dict],
        active_work: list[ActiveWorkItem],
    ) -> list[ModuleFreshness]:
        coverage_points = [value for value in [integrity.get("last_pull"), integrity.get("last_push"), self._sync_runtime.get("last_success_at")] if _dt(value)]
        coverage_raw = max(coverage_points, default="")
        coverage_dt = _dt(coverage_raw)
        coverage_age = _age_seconds(coverage_raw)
        unsynced = dict(integrity.get("unsynced_rows") or {})
        workflow_jobs = self._db.list_workflow_jobs(limit=20)
        workflow_errors = sum(1 for job in workflow_jobs if str(job.get("status") or "") == "error")
        pending_tombstones = int(integrity.get("pending_tombstones", 0) or 0)
        orphan_slots = int(integrity.get("orphan_meal_slots", 0) or 0)
        system_unsynced = pending_tombstones + orphan_slots + workflow_errors + int(self._sync_runtime.get("consecutive_failures", 0) or 0)
        active_modules = {item.module for item in active_work}
        weak_sources = {"telemetry_events", "workflow_jobs", "sync_last_push_at", "sync_last_pull_at"}

        items: list[ModuleFreshness] = []
        for module in _MODULE_ORDER:
            data = dict(updates.get(module) or {})
            updated_at = str(data.get("updated_at") or "")
            label = str(data.get("label") or module.title())
            source = str(data.get("source") or "")
            unsynced_count = system_unsynced if module == "system" else int(unsynced.get(_module_table_name(module), 0) or 0)
            confidence = "weak" if source in weak_sources else "strong"
            freshness_age = _age_seconds(updated_at)
            covered_by_sync = bool(updated_at and coverage_dt and (_dt(updated_at) or coverage_dt) <= coverage_dt)
            stale_reason = ""

            if module in active_modules:
                titles = [item.title for item in active_work if item.module == module][:2]
                items.append(
                    ModuleFreshness(
                        module=module,
                        state="working",
                        label=label,
                        detail=", ".join(titles) or "Background work is running.",
                        updated_at=updated_at,
                        unsynced_count=unsynced_count,
                        freshness_age_seconds=freshness_age,
                        sync_age_seconds=coverage_age,
                        confidence=confidence,
                        stale_reason="",
                        covered_by_sync=covered_by_sync,
                    )
                )
                continue

            if not updated_at and unsynced_count == 0:
                detail = "No activity yet."
                if module == "system" and coverage_raw:
                    detail = f"Last successful sync {_relative_time(coverage_raw)}."
                    state = "fresh"
                    updated_at = coverage_raw
                    freshness_age = _age_seconds(updated_at)
                    covered_by_sync = True
                else:
                    state = "idle"
                items.append(
                    ModuleFreshness(
                        module=module,
                        state=state,
                        label=label,
                        detail=detail,
                        updated_at=updated_at,
                        unsynced_count=unsynced_count,
                        freshness_age_seconds=freshness_age,
                        sync_age_seconds=coverage_age,
                        confidence=confidence,
                        stale_reason="",
                        covered_by_sync=covered_by_sync,
                    )
                )
                continue

            is_stale = False
            if unsynced_count > 0:
                is_stale = True
                stale_reason = "unsynced_rows"
            elif module == "system" and orphan_slots > 0:
                is_stale = True
                stale_reason = "integrity_issue"
            elif module == "system" and _sync_is_offline(self._sync_runtime):
                is_stale = True
                stale_reason = "sync_offline"
            elif module == "system" and self._sync_runtime.get("circuit_open"):
                is_stale = True
                stale_reason = "sync_backoff"
            elif updated_at and coverage_dt is not None and (_dt(updated_at) or coverage_dt) > coverage_dt:
                is_stale = True
                stale_reason = "newer_than_sync"
            elif updated_at and coverage_dt is None:
                is_stale = True
                stale_reason = "no_sync_coverage"

            if is_stale:
                if stale_reason == "unsynced_rows":
                    detail = f"{unsynced_count} change{'s' if unsynced_count != 1 else ''} waiting to sync."
                elif stale_reason == "integrity_issue":
                    detail = "A system integrity issue needs attention before this state is trustworthy."
                elif stale_reason == "sync_offline":
                    detail = "Working offline until the connection returns."
                elif stale_reason == "sync_backoff":
                    detail = "Cloud sync is retrying after repeated failures."
                elif stale_reason == "no_sync_coverage":
                    detail = "This state may be out of date because no successful sync has covered it yet."
                elif confidence == "weak":
                    detail = "This state may be out of date based on indirect activity only."
                else:
                    detail = f"Local data is newer than the last sync ({_relative_time(updated_at)})."
                state = "stale"
            else:
                detail = f"Up to date. Last changed {_relative_time(updated_at)}."
                state = "fresh"

            items.append(
                ModuleFreshness(
                    module=module,
                    state=state,
                    label=label,
                    detail=detail,
                    updated_at=updated_at,
                    unsynced_count=unsynced_count,
                    freshness_age_seconds=freshness_age,
                    sync_age_seconds=coverage_age,
                    confidence=confidence,
                    stale_reason=stale_reason,
                    covered_by_sync=covered_by_sync,
                )
            )
        return items

    def _build_attention_reasons(
        self,
        integrity: dict[str, Any],
        modules: list[ModuleFreshness],
        active_work: list[ActiveWorkItem],
        recent_changes: list[RecentChange],
    ) -> list[str]:
        reasons: list[str] = []
        if self._sync_runtime.get("is_syncing"):
            reasons.append("sync_active")
        if _sync_is_offline(self._sync_runtime):
            reasons.append("sync_offline")
        if self._sync_runtime.get("circuit_open") or int(self._sync_runtime.get("retry_in_seconds", 0) or 0) > 0:
            reasons.append("sync_backoff")
        if int(integrity.get("orphan_meal_slots", 0) or 0) > 0:
            reasons.append("integrity_issue")
        if int(integrity.get("pending_tombstones", 0) or 0) > 0:
            reasons.append("pending_tombstones")
        if any(item.kind == "ai" for item in active_work):
            reasons.append("ai_in_progress")
        if any(item.kind == "job" for item in active_work):
            reasons.append("job_running")
        if any(item.state == "stale" for item in modules):
            reasons.append("module_stale")
        if any(item.confidence == "weak" and item.state == "stale" for item in modules):
            reasons.append("weak_evidence")

        recent_ai_failures = sum(1 for change in recent_changes[:12] if change.kind == "ai" and "failed" in change.title.lower())
        if recent_ai_failures:
            reasons.append("ai_failed")
        if recent_ai_failures >= 2:
            reasons.append("ai_repeated_failure")

        recent_job_failures = sum(1 for change in recent_changes[:12] if change.kind == "workflow" and "failed" in change.title.lower())
        if recent_job_failures:
            reasons.append("job_failed")

        sync_failures = sum(1 for change in recent_changes[:12] if change.kind == "sync" and "failed" in change.title.lower())
        if sync_failures:
            reasons.append("sync_failed")
        if sync_failures >= 2 or int(self._sync_runtime.get("consecutive_failures", 0) or 0) >= 3:
            reasons.append("sync_critical")

        normalized = []
        for reason in reasons:
            token = _normalise_attention_reason(reason)
            if token and token not in normalized:
                normalized.append(token)
        return normalized

    def _build_overall_state(
        self,
        modules: list[ModuleFreshness],
        active_work: list[ActiveWorkItem],
        attention_reasons: list[str],
    ) -> str:
        if self._sync_runtime.get("is_syncing") or any(item.kind == "sync" for item in active_work):
            return "syncing"
        if any(item.kind == "ai" for item in active_work):
            return "ai_busy"
        if "sync_offline" in attention_reasons:
            return "offline"
        if "sync_backoff" in attention_reasons:
            return "recovering"
        if any(item.state == "stale" for item in modules):
            return "stale"
        if any(reason in {"job_failed", "ai_failed"} for reason in attention_reasons):
            return "attention"
        return "healthy"

    def _build_severity(
        self,
        integrity: dict[str, Any],
        modules: list[ModuleFreshness],
        active_work: list[ActiveWorkItem],
        recent_changes: list[RecentChange],
        attention_reasons: list[str],
    ) -> str:
        severity = "quiet"
        if active_work or recent_changes[:1]:
            severity = _max_severity(severity, "info")
        if any(item.state == "stale" for item in modules) or "sync_backoff" in attention_reasons or "sync_offline" in attention_reasons:
            severity = _max_severity(severity, "warning")
        if any("failed" in change.title.lower() for change in recent_changes[:5]):
            severity = _max_severity(severity, "warning")

        stale_modules = [item for item in modules if item.state == "stale"]
        oldest_stale_age = max((item.freshness_age_seconds for item in stale_modules), default=0)
        unsynced_total = sum(item.unsynced_count for item in stale_modules)
        last_failure_age = _age_seconds(self._sync_runtime.get("last_failure_at"))

        if "integrity_issue" in attention_reasons:
            severity = _max_severity(severity, "critical")
        if "sync_critical" in attention_reasons:
            severity = _max_severity(severity, "critical")
        if "sync_offline" in attention_reasons and last_failure_age >= 180:
            severity = _max_severity(severity, "critical")
        if "ai_repeated_failure" in attention_reasons:
            severity = _max_severity(severity, "critical")
        if unsynced_total >= 8 or oldest_stale_age >= 3600:
            severity = _max_severity(severity, "critical")
        if int(integrity.get("pending_tombstones", 0) or 0) >= 4:
            severity = _max_severity(severity, "critical")
        return severity

    def _build_feed_summary(self, changes: list[RecentChange]) -> list[VisibilityDigestItem]:
        groups: dict[tuple[str, str, str, str], VisibilityDigestItem] = {}
        for change in changes[:20]:
            activity_type = _activity_type(change)
            title = change.title
            detail = change.detail
            key = (change.kind, change.module, title, activity_type)
            # Collapse low-value repetition into a calmer digest.
            if change.kind in {"sync", "ai", "shopping", "pantry", "recipe", "planner"} and "failed" not in title.lower():
                key = (change.kind, change.module, title.split(":")[0], activity_type)
                if change.kind in {"shopping", "pantry", "recipe", "planner"}:
                    detail = f"Latest {change.module} update {_relative_time(change.occurred_at)}."
            if key in groups:
                groups[key].count += 1
                if _dt(change.occurred_at) and (_dt(change.occurred_at) or datetime.fromtimestamp(0, tz=timezone.utc)) > (_dt(groups[key].occurred_at) or datetime.fromtimestamp(0, tz=timezone.utc)):
                    groups[key].occurred_at = change.occurred_at
                    groups[key].detail = detail
                continue
            groups[key] = VisibilityDigestItem(
                kind=change.kind,
                module=change.module,
                title=title,
                detail=detail,
                count=1,
                occurred_at=change.occurred_at,
                severity=_change_severity(change),
                activity_type=activity_type,
            )
        items = list(groups.values())
        items.sort(
            key=lambda item: (
                _SEVERITY_ORDER.get(item.severity, 0),
                _dt(item.occurred_at) or datetime.fromtimestamp(0, tz=timezone.utc),
            ),
            reverse=True,
        )
        return items[:12]

    def _build_recommended_actions(
        self,
        modules: list[ModuleFreshness],
        attention_reasons: list[str],
        severity: str,
    ) -> list[VisibilityAction]:
        actions: list[VisibilityAction] = []

        def _add(action_id: str, label: str, target: str, *, payload: dict[str, Any] | None = None, style: str = "secondary") -> None:
            if any(item.action_id == action_id and item.target == target for item in actions):
                return
            actions.append(
                VisibilityAction(
                    action_id=action_id,
                    label=label,
                    target=target,
                    payload=dict(payload or {}),
                    style=style,
                )
            )

        if any(reason in attention_reasons for reason in {"sync_offline", "sync_backoff", "sync_failed", "sync_critical"}):
            _add("retry_sync", "Retry sync", "system", style="primary")
            _add("open_monitoring", "Open Monitoring", "system")
        if any(reason in attention_reasons for reason in {"ai_failed", "ai_repeated_failure", "ai_in_progress"}):
            _add("open_dishy", "Open Dishy", "dishy", payload={"module": "dishy"})
        if any(item.module == "shopping" and item.state == "stale" for item in modules):
            _add("review_shopping", "Review Shopping", "shopping", payload={"module": "shopping"})
        if any(item.module == "planner" and item.state == "stale" for item in modules):
            _add("open_planner", "Open Planner", "planner", payload={"module": "planner"})
        if "job_failed" in attention_reasons:
            _add("view_failed_jobs", "View failed jobs", "system", payload={"section": "monitoring"})
        if severity in {"warning", "critical"} and not any(item.action_id == "open_monitoring" for item in actions):
            _add("open_monitoring", "Open Monitoring", "system")
        return actions[:4]

    def _build_global_freshness(
        self,
        integrity: dict[str, Any],
        modules: list[ModuleFreshness],
        severity: str,
    ) -> dict[str, Any]:
        last_pull = str(integrity.get("last_pull") or self._sync_runtime.get("last_success_at") or "")
        last_push = str(integrity.get("last_push") or "")
        stale_modules = [item for item in modules if item.state == "stale"]
        sync_headline, sync_detail = describe_sync_runtime(self._sync_runtime)
        if stale_modules:
            detail = f"{sum(item.unsynced_count for item in stale_modules)} pending sync change(s). Last sync check {_relative_time(max(last_pull, last_push))}."
        elif severity == "info":
            detail = "Background work is active or recently completed."
        elif last_pull or last_push:
            detail = f"Last sync check {_relative_time(max(last_pull, last_push))}. {sync_detail}"
        else:
            detail = sync_detail
        return {
            "detail": detail,
            "sync_headline": sync_headline,
            "last_pull_at": last_pull,
            "last_push_at": last_push,
            "last_pull_label": _display_time(last_pull),
            "last_push_label": _display_time(last_push),
            "stale_module_count": len(stale_modules),
        }

    def _describe_snapshot(
        self,
        overall_state: str,
        severity: str,
        global_freshness: dict[str, Any],
        modules: list[ModuleFreshness],
        active_work: list[ActiveWorkItem],
        attention_reasons: list[str],
    ) -> tuple[str, str]:
        if overall_state == "syncing":
            return "Syncing your latest changes", global_freshness.get("detail", "Cloud sync is in progress.")
        if overall_state == "ai_busy":
            title = active_work[0].title if active_work else "Dishy is working"
            return title, active_work[0].detail if active_work else "An AI task is in progress."
        if overall_state == "offline":
            return "Working offline", global_freshness.get("detail", "Changes will sync when the connection returns.")
        if overall_state == "recovering":
            return "System recovering", global_freshness.get("detail", "Background services are retrying.")
        if overall_state == "stale":
            stale = [item for item in modules if item.state == "stale"]
            if stale:
                lead = stale[0]
                return "Changes waiting to sync", lead.detail
            return "Changes waiting to sync", global_freshness.get("detail", "")
        if severity == "critical":
            if "integrity_issue" in attention_reasons:
                return "System needs attention", "A data integrity issue needs review before the app can be trusted fully."
            return "System needs attention", global_freshness.get("detail", "A blocking issue needs review.")
        if severity == "warning":
            return "A few things need review", global_freshness.get("detail", "Some app state needs attention.")
        if severity == "info" and active_work:
            return active_work[0].title, active_work[0].detail
        return "All systems calm", global_freshness.get("detail", "Everything looks up to date.")
