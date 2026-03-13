"""Cross-platform pre-release checks for DishBoard builds."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    print("▶ Pre-release checks: lint/syntax")
    py_files = [
        "DishBoard.py",
        "main_window.py",
        "auth/cloud_sync.py",
        "models/database.py",
        "utils/cloud_sync_service.py",
        "utils/startup_health.py",
        "utils/telemetry.py",
        "views/settings.py",
        "utils/version.py",
    ]
    _run([sys.executable, "-m", "py_compile", *py_files])

    print("▶ Pre-release checks: test suite")
    _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"])

    print("▶ Pre-release checks: startup health smoke")
    from models.database import Database
    from utils.startup_health import run_startup_health_check
    from utils.version import APP_VERSION

    db = Database()
    db.connect()
    db.init_db()
    report = run_startup_health_check(db)
    print(
        "startup_health:",
        {
            "tombstones_removed": report.get("invalid_tombstones_removed", 0),
            "linked_slots": report.get("linked_meal_slots", 0),
            "removed_orphans": int(report.get("removed_orphan_slots", 0) or 0)
            + int(report.get("removed_stale_unlinked_slots", 0) or 0),
            "recovered_jobs": report.get("recovered_workflow_jobs", 0),
        },
    )
    print("app_version:", APP_VERSION)
    db.close()

    print("✅ Pre-release checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
