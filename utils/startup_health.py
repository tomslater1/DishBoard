"""Startup health checks and auto-repair for local runtime state."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from models.database import Database

_REPORT_KEY = "runtime_last_health_report"


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value or "").strip())
        return True
    except Exception:
        return False


def run_startup_health_check(db: Database) -> dict:
    """Run lightweight local repairs that are safe to perform on every launch."""
    invalid_tombstones_removed = 0

    for t in db.get_pending_tombstones():
        cloud_id = str((t or {}).get("cloud_id") or "").strip()
        if cloud_id and _is_uuid(cloud_id):
            continue
        try:
            db.clear_tombstone(int(t.get("id")))
            invalid_tombstones_removed += 1
        except Exception:
            pass

    linked_slots = int(db.reconcile_meal_plan_recipe_links() or 0)
    removed_stale_unlinked = int(db.cleanup_unlinked_cloud_meal_plans() or 0)
    removed_orphans = int(db.cleanup_orphan_meal_plans() or 0)
    reset_jobs = int(db.recover_stuck_workflow_jobs(older_than_minutes=20) or 0)

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "invalid_tombstones_removed": invalid_tombstones_removed,
        "linked_meal_slots": linked_slots,
        "removed_stale_unlinked_slots": removed_stale_unlinked,
        "removed_orphan_slots": removed_orphans,
        "recovered_workflow_jobs": reset_jobs,
    }

    try:
        db.set_setting(_REPORT_KEY, json.dumps(report))
    except Exception:
        pass

    return report


def get_last_health_report(db: Database) -> dict:
    raw = str(db.get_setting(_REPORT_KEY, "") or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
