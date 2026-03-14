import sqlite3
import os
import json
from datetime import datetime, timezone

from utils.paths import get_data_dir


_UNSET = object()


def default_db_path() -> str:
    return os.path.join(get_data_dir(), "dishboard.db")


def _utc_now_iso() -> str:
    """Return a canonical UTC timestamp string for local + cloud sync fields."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_sync_ts(value) -> datetime | None:
    """Parse mixed timestamp formats into a UTC-aware datetime."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    # Common SQLite format: "YYYY-MM-DD HH:MM:SS"
    if " " in raw and "T" not in raw:
        raw = raw.replace(" ", "T", 1)
    # Common RFC3339 UTC marker
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _normalise_sync_ts(value) -> str | None:
    """Normalize any parseable timestamp to a canonical UTC ISO string."""
    dt = _parse_sync_ts(value)
    return dt.isoformat(timespec="seconds") if dt else None


def _cloud_is_newer(local_raw, cloud_raw) -> bool:
    """Return True when cloud timestamp is strictly newer than local timestamp."""
    local_dt = _parse_sync_ts(local_raw)
    cloud_dt = _parse_sync_ts(cloud_raw)
    if local_dt and cloud_dt:
        return cloud_dt > local_dt
    if local_dt and not cloud_dt:
        return False
    if cloud_dt and not local_dt:
        return True
    local_s = str(local_raw or "")
    cloud_s = str(cloud_raw or "")
    if local_s and cloud_s:
        return cloud_s > local_s
    return bool(cloud_s and not local_s)


class Database:
    _USER_DATA_TABLES = (
        "recipes",
        "meal_plans",
        "shopping_items",
        "nutrition_logs",
        "dishy_chat_history",
        "pantry_items",
        "in_app_notifications",
        "ai_usage_daily",
        "workflow_jobs",
        "telemetry_events",
        "trash_bin",
        "recipe_source_stats",
        "pantry_waste_log",
    )

    def __init__(self, path: str | None = None):
        self.path = path or default_db_path()
        self._conn: sqlite3.Connection | None = None

    def connect(self):
        # Multiple connections are used by design (UI + background sync workers).
        # Use WAL + busy timeout and autocommit so brief write contention does
        # not surface as "database is locked" during normal sync/message bursts.
        # Autocommit keeps implicit transactions short across the app's many
        # timers/workers and is safer here than holding a deferred transaction
        # open until some later commit.
        self._conn = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            pass
        self._conn.execute("PRAGMA busy_timeout = 30000")
        self._conn.execute("PRAGMA foreign_keys = ON")

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    def init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS recipes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   TEXT,
                source      TEXT DEFAULT 'scraped',
                title       TEXT NOT NULL,
                image_url   TEXT,
                summary     TEXT,
                servings    INTEGER,
                ready_mins  INTEGER,
                data_json   TEXT,
                saved_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS meal_plans (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                day_of_week TEXT NOT NULL,
                meal_type   TEXT NOT NULL CHECK(meal_type IN ('breakfast','lunch','dinner','snack')),
                recipe_id   INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
                custom_name TEXT,
                week_start  DATE NOT NULL,
                notes       TEXT
            );

            CREATE TABLE IF NOT EXISTS shopping_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                quantity    TEXT,
                unit        TEXT,
                checked     INTEGER DEFAULT 0,
                source      TEXT DEFAULT 'manual',
                added_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key         TEXT PRIMARY KEY,
                value       TEXT
            );

            CREATE TABLE IF NOT EXISTS nutrition_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date    DATE    NOT NULL,
                food_name   TEXT    NOT NULL,
                kcal        REAL    DEFAULT 0,
                protein_g   REAL    DEFAULT 0,
                carbs_g     REAL    DEFAULT 0,
                fat_g       REAL    DEFAULT 0,
                fiber_g     REAL    DEFAULT 0,
                sugar_g     REAL    DEFAULT 0,
                logged_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS dishy_chat_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT    NOT NULL,
                role        TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                tool_names  TEXT    DEFAULT '',
                timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sync_tombstones (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                cloud_id   TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()
        self._run_migrations()

    # ── Schema migrations ─────────────────────────────────────────────────────
    # Each tuple: (target_schema_version, sql_statement)
    # Add new migrations at the END with an incremented version number.
    # Never modify or remove existing entries — they are idempotent on re-run.
    _MIGRATIONS: list[tuple[int, str]] = [
        # v1: cloud sync columns for all tables
        (1, "ALTER TABLE recipes             ADD COLUMN is_favourite  INTEGER DEFAULT 0"),
        (1, "ALTER TABLE recipes             ADD COLUMN cloud_id      TEXT"),
        (1, "ALTER TABLE recipes             ADD COLUMN updated_at    DATETIME DEFAULT NULL"),
        (1, "ALTER TABLE meal_plans          ADD COLUMN cloud_id      TEXT"),
        (1, "ALTER TABLE meal_plans          ADD COLUMN updated_at    DATETIME DEFAULT NULL"),
        (1, "ALTER TABLE shopping_items      ADD COLUMN cloud_id      TEXT"),
        (1, "ALTER TABLE shopping_items      ADD COLUMN updated_at    DATETIME DEFAULT NULL"),
        (1, "ALTER TABLE nutrition_logs      ADD COLUMN cloud_id      TEXT"),
        (1, "ALTER TABLE nutrition_logs      ADD COLUMN updated_at    DATETIME DEFAULT NULL"),
        (1, "ALTER TABLE dishy_chat_history  ADD COLUMN cloud_id      TEXT"),
        (1, "ALTER TABLE dishy_chat_history  ADD COLUMN updated_at    DATETIME DEFAULT NULL"),
        # v2: pantry/fridge/freezer storage tracker
        (2, """CREATE TABLE IF NOT EXISTS pantry_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    quantity     REAL    DEFAULT NULL,
    unit         TEXT    DEFAULT '',
    storage      TEXT    DEFAULT 'Pantry',
    expiry_date  TEXT    DEFAULT NULL,
    added_at     TEXT    DEFAULT (datetime('now')),
    cloud_id     TEXT,
    updated_at   DATETIME DEFAULT NULL
)"""),
        # v3: data integrity + query performance indexes
        (3, """DELETE FROM meal_plans
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM meal_plans
                    GROUP BY week_start, day_of_week, meal_type
                )"""),
        (3, "CREATE UNIQUE INDEX IF NOT EXISTS idx_meal_plans_slot_unique ON meal_plans (week_start, day_of_week, meal_type)"),
        (3, "CREATE INDEX IF NOT EXISTS idx_recipes_updated_at ON recipes(updated_at)"),
        (3, "CREATE UNIQUE INDEX IF NOT EXISTS idx_recipes_cloud_id_uq ON recipes(cloud_id) WHERE cloud_id IS NOT NULL"),
        (3, "CREATE INDEX IF NOT EXISTS idx_recipes_saved_at ON recipes(saved_at)"),
        (3, "CREATE INDEX IF NOT EXISTS idx_meal_plans_updated_at ON meal_plans(updated_at)"),
        (3, "CREATE UNIQUE INDEX IF NOT EXISTS idx_meal_plans_cloud_id_uq ON meal_plans(cloud_id) WHERE cloud_id IS NOT NULL"),
        (3, "CREATE INDEX IF NOT EXISTS idx_meal_plans_week_day ON meal_plans(week_start, day_of_week)"),
        (3, "CREATE INDEX IF NOT EXISTS idx_meal_plans_recipe_cloud_id ON meal_plans(recipe_cloud_id)"),
        (3, "CREATE INDEX IF NOT EXISTS idx_shopping_updated_at ON shopping_items(updated_at)"),
        (3, "CREATE UNIQUE INDEX IF NOT EXISTS idx_shopping_cloud_id_uq ON shopping_items(cloud_id) WHERE cloud_id IS NOT NULL"),
        (3, "CREATE INDEX IF NOT EXISTS idx_shopping_checked_added ON shopping_items(checked, added_at)"),
        (3, "CREATE INDEX IF NOT EXISTS idx_nutrition_updated_at ON nutrition_logs(updated_at)"),
        (3, "CREATE UNIQUE INDEX IF NOT EXISTS idx_nutrition_cloud_id_uq ON nutrition_logs(cloud_id) WHERE cloud_id IS NOT NULL"),
        (3, "CREATE INDEX IF NOT EXISTS idx_nutrition_log_date ON nutrition_logs(log_date)"),
        (3, "CREATE INDEX IF NOT EXISTS idx_dishy_chat_updated_at ON dishy_chat_history(updated_at)"),
        (3, "CREATE UNIQUE INDEX IF NOT EXISTS idx_dishy_chat_cloud_id_uq ON dishy_chat_history(cloud_id) WHERE cloud_id IS NOT NULL"),
        (3, "CREATE INDEX IF NOT EXISTS idx_dishy_chat_session_time ON dishy_chat_history(session_id, timestamp)"),
        (3, "CREATE INDEX IF NOT EXISTS idx_pantry_updated_at ON pantry_items(updated_at)"),
        (3, "CREATE UNIQUE INDEX IF NOT EXISTS idx_pantry_cloud_id_uq ON pantry_items(cloud_id) WHERE cloud_id IS NOT NULL"),
        (3, "CREATE INDEX IF NOT EXISTS idx_pantry_storage_name ON pantry_items(storage, name)"),
        (3, "CREATE INDEX IF NOT EXISTS idx_pantry_expiry ON pantry_items(expiry_date)"),
        (3, "CREATE INDEX IF NOT EXISTS idx_sync_tombstones_table_cloud ON sync_tombstones(table_name, cloud_id)"),
        # v4: ensure older DBs that missed recipe_cloud_id get it safely
        (4, "ALTER TABLE meal_plans ADD COLUMN recipe_cloud_id TEXT"),
        (4, "CREATE INDEX IF NOT EXISTS idx_meal_plans_recipe_cloud_id ON meal_plans(recipe_cloud_id)"),
        # v5: in-app notifications, AI metering, workflow jobs, telemetry events
        (5, """CREATE TABLE IF NOT EXISTS in_app_notifications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT    NOT NULL DEFAULT '',
    notif_type   TEXT    NOT NULL,
    title        TEXT    NOT NULL,
    message      TEXT    NOT NULL,
    severity     TEXT    NOT NULL DEFAULT 'info',
    data_json    TEXT    DEFAULT '{}',
    dedupe_key   TEXT    DEFAULT NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    read_at      DATETIME DEFAULT NULL,
    updated_at   DATETIME DEFAULT NULL
)"""),
        (5, "CREATE UNIQUE INDEX IF NOT EXISTS idx_notifs_dedupe_uq ON in_app_notifications(dedupe_key) WHERE dedupe_key IS NOT NULL"),
        (5, "CREATE INDEX IF NOT EXISTS idx_notifs_user_created ON in_app_notifications(user_id, created_at DESC)"),
        (5, "CREATE INDEX IF NOT EXISTS idx_notifs_user_read ON in_app_notifications(user_id, read_at)"),
        (5, """CREATE TABLE IF NOT EXISTS ai_usage_daily (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT    NOT NULL,
    usage_date    DATE    NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    blocked_count INTEGER NOT NULL DEFAULT 0,
    updated_at    DATETIME DEFAULT NULL
)"""),
        (5, "CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_usage_user_day_uq ON ai_usage_daily(user_id, usage_date)"),
        (5, "CREATE INDEX IF NOT EXISTS idx_ai_usage_day ON ai_usage_daily(usage_date)"),
        (5, """CREATE TABLE IF NOT EXISTS workflow_jobs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    job_key           TEXT    UNIQUE,
    job_type          TEXT    NOT NULL,
    payload_json      TEXT    DEFAULT '{}',
    status            TEXT    NOT NULL DEFAULT 'scheduled',
    run_every_minutes INTEGER NOT NULL DEFAULT 60,
    next_run_at       DATETIME NOT NULL,
    last_run_at       DATETIME DEFAULT NULL,
    last_error        TEXT    DEFAULT '',
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME DEFAULT NULL
)"""),
        (5, "CREATE INDEX IF NOT EXISTS idx_jobs_next_run ON workflow_jobs(next_run_at, status)"),
        (5, """CREATE TABLE IF NOT EXISTS telemetry_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL DEFAULT '',
    event_name      TEXT    NOT NULL,
    properties_json TEXT    DEFAULT '{}',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
)"""),
        (5, "CREATE INDEX IF NOT EXISTS idx_telemetry_user_created ON telemetry_events(user_id, created_at DESC)"),
        # v6: trash/recovery, source trust stats, pantry waste log, household-aware sync columns
        (6, "ALTER TABLE recipes ADD COLUMN household_id TEXT"),
        (6, "ALTER TABLE meal_plans ADD COLUMN household_id TEXT"),
        (6, "ALTER TABLE shopping_items ADD COLUMN household_id TEXT"),
        (6, "ALTER TABLE nutrition_logs ADD COLUMN household_id TEXT"),
        (6, "ALTER TABLE pantry_items ADD COLUMN household_id TEXT"),
        (6, "ALTER TABLE sync_tombstones ADD COLUMN household_id TEXT"),
        (6, "CREATE INDEX IF NOT EXISTS idx_recipes_household_id ON recipes(household_id)"),
        (6, "CREATE INDEX IF NOT EXISTS idx_meal_plans_household_id ON meal_plans(household_id)"),
        (6, "CREATE INDEX IF NOT EXISTS idx_shopping_household_id ON shopping_items(household_id)"),
        (6, "CREATE INDEX IF NOT EXISTS idx_nutrition_household_id ON nutrition_logs(household_id)"),
        (6, "CREATE INDEX IF NOT EXISTS idx_pantry_household_id ON pantry_items(household_id)"),
        (6, "CREATE INDEX IF NOT EXISTS idx_tombstones_household_id ON sync_tombstones(household_id)"),
        (6, """CREATE TABLE IF NOT EXISTS trash_bin (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL DEFAULT '',
    entity_type     TEXT    NOT NULL,
    payload_json    TEXT    NOT NULL,
    reason          TEXT    NOT NULL DEFAULT 'deleted',
    deleted_at      DATETIME DEFAULT CURRENT_TIMESTAMP
)"""),
        (6, "CREATE INDEX IF NOT EXISTS idx_trash_user_deleted ON trash_bin(user_id, deleted_at DESC)"),
        (6, """CREATE TABLE IF NOT EXISTS recipe_source_stats (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id               TEXT    NOT NULL DEFAULT '',
    source_host           TEXT    NOT NULL,
    scrape_success_count  INTEGER NOT NULL DEFAULT 0,
    scrape_fail_count     INTEGER NOT NULL DEFAULT 0,
    nutrition_success_count INTEGER NOT NULL DEFAULT 0,
    nutrition_fail_count  INTEGER NOT NULL DEFAULT 0,
    avg_latency_ms        REAL    NOT NULL DEFAULT 0,
    sample_count          INTEGER NOT NULL DEFAULT 0,
    last_status           TEXT    NOT NULL DEFAULT '',
    updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP
)"""),
        (6, "CREATE UNIQUE INDEX IF NOT EXISTS idx_source_stats_user_host_uq ON recipe_source_stats(user_id, source_host)"),
        (6, """CREATE TABLE IF NOT EXISTS pantry_waste_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           TEXT    NOT NULL DEFAULT '',
    item_name         TEXT    NOT NULL,
    quantity          REAL    DEFAULT NULL,
    unit              TEXT    DEFAULT '',
    reason            TEXT    NOT NULL DEFAULT 'discarded',
    estimated_value   REAL    NOT NULL DEFAULT 0,
    logged_at         DATETIME DEFAULT CURRENT_TIMESTAMP
)"""),
        (6, "CREATE INDEX IF NOT EXISTS idx_pantry_waste_user_time ON pantry_waste_log(user_id, logged_at DESC)"),
    ]
    _LATEST_SCHEMA_VERSION = 6

    def _run_migrations(self) -> None:
        """Apply pending schema migrations, tracked via PRAGMA user_version.

        Each migration SQL is idempotent: errors (duplicate column, etc.) are
        silently swallowed so re-applying an already-applied migration is safe.
        PRAGMA user_version is updated to _LATEST_SCHEMA_VERSION once all
        pending migrations have been attempted.
        """
        current = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if current >= self._LATEST_SCHEMA_VERSION:
            return

        for (target_ver, sql) in self._MIGRATIONS:
            if target_ver > current:
                try:
                    self.conn.execute(sql)
                except Exception:
                    pass  # column/index already exists — safe to ignore

        self.conn.commit()
        self.conn.execute(f"PRAGMA user_version = {self._LATEST_SCHEMA_VERSION}")
        self.conn.commit()

    # -- convenience helpers -----------------------------------------------

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def _active_user_id(self) -> str:
        return str(self.get_setting("active_user_id", "") or "").strip()

    def _active_household_id(self) -> str:
        hid = str(self.get_setting("household_id", "") or "").strip()
        return hid or self._active_user_id()

    @staticmethod
    def _as_dict(row) -> dict:
        return dict(row) if row is not None else {}

    def _stash_deleted_row(self, entity_type: str, payload: dict, *, reason: str = "deleted") -> None:
        if not payload:
            return
        try:
            self.conn.execute(
                "INSERT INTO trash_bin (user_id, entity_type, payload_json, reason)"
                " VALUES (?, ?, ?, ?)",
                (
                    self._active_user_id(),
                    entity_type,
                    json.dumps(payload),
                    reason or "deleted",
                ),
            )
            self.conn.commit()
        except Exception:
            pass

    @staticmethod
    def _to_number(value) -> float:
        try:
            return float(value or 0)
        except Exception:
            return 0.0

    def _estimate_waste_value(self, row: dict) -> float:
        default_item_cost = self._to_number(self.get_setting("pantry_default_item_cost", "2.50"))
        if default_item_cost <= 0:
            default_item_cost = 2.5
        qty = self._to_number((row or {}).get("quantity"))
        if qty > 0:
            return round(qty * default_item_cost, 2)
        return round(default_item_cost, 2)

    def _log_pantry_waste(self, row: dict, *, reason: str = "discarded") -> None:
        if not row:
            return
        try:
            self.conn.execute(
                "INSERT INTO pantry_waste_log (user_id, item_name, quantity, unit, reason, estimated_value)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self._active_user_id(),
                    str(row.get("name") or "Item"),
                    row.get("quantity"),
                    str(row.get("unit") or ""),
                    reason or "discarded",
                    self._estimate_waste_value(row),
                ),
            )
            self.conn.commit()
        except Exception:
            pass

    def list_trash_items(self, *, limit: int = 200) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM trash_bin WHERE user_id=? ORDER BY deleted_at DESC LIMIT ?",
            (self._active_user_id(), max(1, int(limit))),
        ).fetchall()
        out: list[dict] = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.get("payload_json") or "{}")
            except Exception:
                item["payload"] = {}
            out.append(item)
        return out

    def clear_trash(self) -> int:
        cursor = self.conn.execute(
            "DELETE FROM trash_bin WHERE user_id=?",
            (self._active_user_id(),),
        )
        self.conn.commit()
        return int(cursor.rowcount or 0)

    def restore_trash_item(self, trash_id: int) -> bool:
        row = self.conn.execute(
            "SELECT * FROM trash_bin WHERE id=? AND user_id=?",
            (int(trash_id), self._active_user_id()),
        ).fetchone()
        if not row:
            return False
        entity = str(row["entity_type"] or "")
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {}

        now = _utc_now_iso()
        ok = False
        try:
            if entity == "recipes":
                payload.pop("id", None)
                payload["cloud_id"] = None
                payload["updated_at"] = now
                cols = [
                    "source_id", "source", "title", "image_url", "summary", "servings",
                    "ready_mins", "data_json", "saved_at", "is_favourite", "cloud_id",
                    "updated_at", "household_id",
                ]
                data = [payload.get(k) for k in cols]
                self.conn.execute(
                    f"INSERT INTO recipes ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                    data,
                )
                ok = True
            elif entity == "shopping_items":
                payload.pop("id", None)
                payload["cloud_id"] = None
                payload["updated_at"] = now
                cols = ["name", "quantity", "unit", "checked", "source", "added_at", "cloud_id", "updated_at", "household_id"]
                data = [payload.get(k) for k in cols]
                self.conn.execute(
                    f"INSERT INTO shopping_items ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                    data,
                )
                ok = True
            elif entity == "pantry_items":
                payload.pop("id", None)
                payload["cloud_id"] = None
                payload["updated_at"] = now
                cols = ["name", "quantity", "unit", "storage", "expiry_date", "added_at", "cloud_id", "updated_at", "household_id"]
                data = [payload.get(k) for k in cols]
                self.conn.execute(
                    f"INSERT INTO pantry_items ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                    data,
                )
                ok = True
            elif entity == "meal_plans":
                wk = str(payload.get("week_start") or "").strip()
                day = str(payload.get("day_of_week") or "").strip()
                meal_type = str(payload.get("meal_type") or "").strip()
                if wk and day and meal_type:
                    self.conn.execute(
                        "INSERT INTO meal_plans (week_start, day_of_week, meal_type, recipe_id, recipe_cloud_id,"
                        " custom_name, notes, cloud_id, updated_at, household_id)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?)"
                        " ON CONFLICT(week_start, day_of_week, meal_type)"
                        " DO UPDATE SET recipe_id=excluded.recipe_id,"
                        " recipe_cloud_id=excluded.recipe_cloud_id,"
                        " custom_name=excluded.custom_name,"
                        " notes=excluded.notes,"
                        " updated_at=excluded.updated_at,"
                        " household_id=excluded.household_id",
                        (
                            wk,
                            day,
                            meal_type,
                            payload.get("recipe_id"),
                            payload.get("recipe_cloud_id"),
                            payload.get("custom_name"),
                            payload.get("notes"),
                            None,
                            now,
                            payload.get("household_id") or self._active_household_id(),
                        ),
                    )
                    ok = True
        except Exception:
            ok = False

        if ok:
            self.conn.execute("DELETE FROM trash_bin WHERE id=?", (int(trash_id),))
            self.conn.commit()
            return True
        return False

    def record_recipe_source_event(
        self,
        source_host: str,
        *,
        event: str,
        ok: bool,
        latency_ms: float = 0.0,
    ) -> None:
        host = str(source_host or "").strip().lower()
        if not host:
            return
        uid = self._active_user_id()
        row = self.conn.execute(
            "SELECT * FROM recipe_source_stats WHERE user_id=? AND source_host=?",
            (uid, host),
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO recipe_source_stats"
                " (user_id, source_host, updated_at) VALUES (?, ?, ?)",
                (uid, host, _utc_now_iso()),
            )
            row = self.conn.execute(
                "SELECT * FROM recipe_source_stats WHERE user_id=? AND source_host=?",
                (uid, host),
            ).fetchone()
        data = dict(row or {})
        sample_count = int(data.get("sample_count", 0) or 0)
        prev_avg = self._to_number(data.get("avg_latency_ms"))
        latency = max(0.0, float(latency_ms or 0.0))
        new_count = sample_count + 1
        new_avg = ((prev_avg * sample_count) + latency) / max(1, new_count)

        updates = {
            "sample_count": new_count,
            "avg_latency_ms": round(new_avg, 1),
            "last_status": f"{event}:{'ok' if ok else 'fail'}",
            "updated_at": _utc_now_iso(),
        }
        if event == "scrape":
            key = "scrape_success_count" if ok else "scrape_fail_count"
            updates[key] = int(data.get(key, 0) or 0) + 1
        elif event == "nutrition":
            key = "nutrition_success_count" if ok else "nutrition_fail_count"
            updates[key] = int(data.get(key, 0) or 0) + 1

        set_clause = ", ".join(f"{k}=?" for k in updates)
        self.conn.execute(
            f"UPDATE recipe_source_stats SET {set_clause} WHERE user_id=? AND source_host=?",
            [*updates.values(), uid, host],
        )
        self.conn.commit()

    def get_recipe_source_score(self, source_host: str) -> float:
        host = str(source_host or "").strip().lower()
        if not host:
            return 50.0
        row = self.conn.execute(
            "SELECT * FROM recipe_source_stats WHERE user_id=? AND source_host=?",
            (self._active_user_id(), host),
        ).fetchone()
        if not row:
            return 50.0
        d = dict(row)
        scrape_ok = float(d.get("scrape_success_count", 0) or 0)
        scrape_fail = float(d.get("scrape_fail_count", 0) or 0)
        nutr_ok = float(d.get("nutrition_success_count", 0) or 0)
        nutr_fail = float(d.get("nutrition_fail_count", 0) or 0)
        scrape_total = max(1.0, scrape_ok + scrape_fail)
        nutr_total = max(1.0, nutr_ok + nutr_fail)
        scrape_rate = scrape_ok / scrape_total
        nutr_rate = nutr_ok / nutr_total
        latency = float(d.get("avg_latency_ms", 0) or 0)
        latency_penalty = min(12.0, latency / 350.0)
        score = (scrape_rate * 55.0) + (nutr_rate * 35.0) + 10.0 - latency_penalty
        return max(0.0, min(100.0, round(score, 1)))

    def get_pantry_waste_summary(self, *, days: int = 30) -> dict:
        uid = self._active_user_id()
        rows = self.conn.execute(
            "SELECT estimated_value FROM pantry_waste_log"
            " WHERE user_id=? AND datetime(logged_at) >= datetime('now', ?)",
            (uid, f"-{max(1, int(days))} days"),
        ).fetchall()
        total = sum(self._to_number(r["estimated_value"]) for r in rows)
        return {"entries": len(rows), "estimated_value": round(total, 2)}

    def get_top_wasted_items(self, *, days: int = 30, limit: int = 3) -> list[dict]:
        uid = self._active_user_id()
        rows = self.conn.execute(
            "SELECT item_name, COUNT(*) AS times, SUM(estimated_value) AS value_sum"
            " FROM pantry_waste_log"
            " WHERE user_id=? AND datetime(logged_at) >= datetime('now', ?)"
            " GROUP BY item_name"
            " ORDER BY value_sum DESC, times DESC, item_name ASC"
            " LIMIT ?",
            (uid, f"-{max(1, int(days))} days", max(1, int(limit))),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_expiry_risk_summary(self) -> dict:
        rows = self.get_pantry_items()
        from datetime import date as _date

        today = _date.today()
        expired = 0
        expiring_soon = 0
        est_value = 0.0
        for row in rows:
            exp = str(row.get("expiry_date") or "").strip()
            if not exp:
                continue
            try:
                d = _date.fromisoformat(exp)
            except Exception:
                continue
            delta = (d - today).days
            if delta < 0:
                expired += 1
                est_value += self._estimate_waste_value(row)
            elif delta <= 3:
                expiring_soon += 1
                est_value += self._estimate_waste_value(row)
        return {
            "expired": expired,
            "expiring_soon": expiring_soon,
            "estimated_value_at_risk": round(est_value, 2),
        }

    def get_sync_integrity_report(self) -> dict:
        last_push = self.get_setting("sync_last_push_at", "")
        last_pull = self.get_setting("sync_last_pull_at", "")
        pending_tombstones = len(self.get_pending_tombstones())
        unsynced = {}
        for table in ("recipes", "meal_plans", "shopping_items", "nutrition_logs", "pantry_items", "dishy_chat_history"):
            try:
                unsynced[table] = len(self.get_unsynced_rows(table))
            except Exception:
                unsynced[table] = 0
        orphans = self.conn.execute(
            "SELECT COUNT(*) AS c FROM meal_plans"
            " WHERE recipe_id IS NOT NULL"
            " AND recipe_id NOT IN (SELECT id FROM recipes)"
        ).fetchone()
        return {
            "last_push": last_push,
            "last_pull": last_pull,
            "pending_tombstones": pending_tombstones,
            "unsynced_rows": unsynced,
            "orphan_meal_slots": int((orphans["c"] if orphans else 0) or 0),
        }

    def get_visibility_module_updates(self) -> dict[str, dict]:
        """Return the latest meaningful local update for each visibility module."""
        last_push = self.get_setting("sync_last_push_at", "")
        last_pull = self.get_setting("sync_last_pull_at", "")
        results: dict[str, dict] = {
            "recipes": {"updated_at": "", "label": "Recipes", "detail": "", "source": "", "target": ""},
            "planner": {"updated_at": "", "label": "Meal Planner", "detail": "", "source": "", "target": ""},
            "shopping": {"updated_at": "", "label": "Shopping List", "detail": "", "source": "", "target": ""},
            "pantry": {"updated_at": "", "label": "My Kitchen", "detail": "", "source": "", "target": ""},
            "nutrition": {"updated_at": "", "label": "Nutrition", "detail": "", "source": "", "target": ""},
            "dishy": {"updated_at": "", "label": "Dishy", "detail": "", "source": "", "target": ""},
            "system": {"updated_at": "", "label": "System", "detail": "", "source": "", "target": ""},
        }

        def _row_time(row: dict | sqlite3.Row, *keys: str) -> tuple[datetime | None, str]:
            for key in keys:
                raw = str((row or {}).get(key) or "").strip() if isinstance(row, dict) else str(row[key] or "").strip()
                dt = _parse_sync_ts(raw)
                if dt:
                    return dt, raw
            return None, ""

        def _pick_latest(rows, *time_keys: str):
            best_row = None
            best_dt = None
            best_raw = ""
            for row in rows or []:
                dt, raw = _row_time(row, *time_keys)
                if dt is None:
                    continue
                if best_dt is None or dt > best_dt:
                    best_row = row
                    best_dt = dt
                    best_raw = raw
            return best_row, best_raw

        recipe_rows = self.conn.execute(
            "SELECT id, title, source, updated_at, saved_at FROM recipes "
            "ORDER BY id DESC LIMIT 80"
        ).fetchall()
        row, raw = _pick_latest(recipe_rows, "updated_at", "saved_at")
        if row is not None:
            results["recipes"] = {
                "updated_at": raw,
                "label": "Recipes",
                "detail": str(row["title"] or "Recipe updated"),
                "source": str(row["source"] or "recipes"),
                "target": str(row["id"] or ""),
            }

        planner_rows = self.conn.execute(
            "SELECT mp.id, mp.day_of_week, mp.meal_type, mp.custom_name, mp.updated_at, r.title AS recipe_title "
            "FROM meal_plans mp "
            "LEFT JOIN recipes r ON r.id = mp.recipe_id "
            "ORDER BY mp.id DESC LIMIT 80"
        ).fetchall()
        row, raw = _pick_latest(planner_rows, "updated_at")
        if row is not None:
            meal_name = str(row["custom_name"] or row["recipe_title"] or "Meal slot").strip()
            results["planner"] = {
                "updated_at": raw,
                "label": "Meal Planner",
                "detail": f"{str(row['day_of_week'] or '').strip()} {str(row['meal_type'] or '').strip()}: {meal_name}".strip(": "),
                "source": "meal_plans",
                "target": str(row["id"] or ""),
            }

        shopping_rows = self.conn.execute(
            "SELECT id, name, checked, source, updated_at, added_at FROM shopping_items "
            "ORDER BY id DESC LIMIT 80"
        ).fetchall()
        row, raw = _pick_latest(shopping_rows, "updated_at", "added_at")
        if row is not None:
            action = "Checked off" if int(row["checked"] or 0) else "Updated"
            results["shopping"] = {
                "updated_at": raw,
                "label": "Shopping List",
                "detail": f"{action} {str(row['name'] or 'shopping item').strip()}",
                "source": str(row["source"] or "shopping_items"),
                "target": str(row["id"] or ""),
            }

        pantry_rows = self.conn.execute(
            "SELECT id, name, storage, quantity, unit, updated_at, added_at FROM pantry_items "
            "ORDER BY id DESC LIMIT 80"
        ).fetchall()
        row, raw = _pick_latest(pantry_rows, "updated_at", "added_at")
        if row is not None:
            results["pantry"] = {
                "updated_at": raw,
                "label": "My Kitchen",
                "detail": f"{str(row['name'] or 'Kitchen item').strip()} · {str(row['storage'] or 'Pantry').strip()}",
                "source": "pantry_items",
                "target": str(row["id"] or ""),
            }

        nutrition_rows = self.conn.execute(
            "SELECT id, food_name, log_date, updated_at, logged_at FROM nutrition_logs "
            "ORDER BY id DESC LIMIT 80"
        ).fetchall()
        row, raw = _pick_latest(nutrition_rows, "updated_at", "logged_at")
        if row is not None:
            results["nutrition"] = {
                "updated_at": raw,
                "label": "Nutrition",
                "detail": f"{str(row['food_name'] or 'Nutrition entry').strip()} · {str(row['log_date'] or '').strip()}".strip(" ·"),
                "source": "nutrition_logs",
                "target": str(row["id"] or ""),
            }

        dishy_rows = self.conn.execute(
            "SELECT id, session_id, role, content, tool_names, updated_at, timestamp FROM dishy_chat_history "
            "ORDER BY id DESC LIMIT 120"
        ).fetchall()
        row, raw = _pick_latest(dishy_rows, "updated_at", "timestamp")
        if row is not None:
            body = str(row["content"] or "").strip().replace("\n", " ")
            detail = body[:80] + ("…" if len(body) > 80 else "")
            if str(row["role"] or "") == "assistant":
                detail = detail or "Dishy replied"
            else:
                detail = detail or "Asked Dishy"
            results["dishy"] = {
                "updated_at": raw,
                "label": "Dishy",
                "detail": detail,
                "source": str(row["session_id"] or "dishy_chat_history"),
                "target": str(row["id"] or ""),
            }

        system_candidates: list[dict] = []
        for raw, label, detail, source in [
            (last_push, "Cloud sync", "Last push completed", "sync_last_push_at"),
            (last_pull, "Cloud sync", "Last pull completed", "sync_last_pull_at"),
        ]:
            if _parse_sync_ts(raw):
                system_candidates.append(
                    {"updated_at": raw, "label": "System", "detail": detail, "source": source, "target": ""}
                )
        for row in self.conn.execute(
            "SELECT event_name, created_at FROM telemetry_events ORDER BY created_at DESC LIMIT 20"
        ).fetchall():
            if _parse_sync_ts(row["created_at"]):
                system_candidates.append(
                    {
                        "updated_at": str(row["created_at"] or ""),
                        "label": "System",
                        "detail": str(row["event_name"] or "Telemetry event").replace(".", " "),
                        "source": "telemetry_events",
                        "target": str(row["event_name"] or ""),
                    }
                )
        for row in self.conn.execute(
            "SELECT job_key, updated_at, status FROM workflow_jobs ORDER BY updated_at DESC LIMIT 20"
        ).fetchall():
            if _parse_sync_ts(row["updated_at"]):
                system_candidates.append(
                    {
                        "updated_at": str(row["updated_at"] or ""),
                        "label": "System",
                        "detail": f"{str(row['job_key'] or 'job').strip()} · {str(row['status'] or 'scheduled').strip()}",
                        "source": "workflow_jobs",
                        "target": str(row["job_key"] or ""),
                    }
                )
        system_candidates.sort(
            key=lambda item: _parse_sync_ts(item.get("updated_at")) or datetime.fromtimestamp(0, tz=timezone.utc),
            reverse=True,
        )
        if system_candidates:
            results["system"] = dict(system_candidates[0])

        return results

    def get_visibility_recent_changes(self, *, limit: int = 30) -> list[dict]:
        """Return a merged, time-ordered recent activity feed for visibility surfaces."""
        changes: list[dict] = []
        per_table = max(4, min(20, int(limit)))

        def _append(item: dict) -> None:
            ts = str(item.get("occurred_at") or "").strip()
            if not _parse_sync_ts(ts):
                return
            changes.append(
                {
                    "kind": str(item.get("kind") or "change"),
                    "module": str(item.get("module") or "system"),
                    "title": str(item.get("title") or "").strip(),
                    "detail": str(item.get("detail") or "").strip(),
                    "occurred_at": ts,
                    "source": str(item.get("source") or "").strip(),
                    "target": str(item.get("target") or "").strip(),
                }
            )

        for row in self.conn.execute(
            "SELECT id, title, source, COALESCE(updated_at, saved_at) AS ts FROM recipes "
            "WHERE COALESCE(updated_at, saved_at) IS NOT NULL ORDER BY ts DESC LIMIT ?",
            (per_table,),
        ).fetchall():
            _append(
                {
                    "kind": "recipe",
                    "module": "recipes",
                    "title": f"Saved recipe: {str(row['title'] or 'Untitled recipe').strip()}",
                    "detail": str(row["source"] or "recipe").strip(),
                    "occurred_at": str(row["ts"] or ""),
                    "source": "recipes",
                    "target": str(row["id"] or ""),
                }
            )

        for row in self.conn.execute(
            "SELECT mp.id, mp.day_of_week, mp.meal_type, mp.custom_name, mp.updated_at, r.title AS recipe_title "
            "FROM meal_plans mp LEFT JOIN recipes r ON r.id = mp.recipe_id "
            "WHERE mp.updated_at IS NOT NULL ORDER BY mp.updated_at DESC LIMIT ?",
            (per_table,),
        ).fetchall():
            meal_name = str(row["custom_name"] or row["recipe_title"] or "Meal slot").strip()
            _append(
                {
                    "kind": "planner",
                    "module": "planner",
                    "title": f"Updated {str(row['meal_type'] or 'meal').strip()} plan",
                    "detail": f"{str(row['day_of_week'] or '').strip()} · {meal_name}".strip(" ·"),
                    "occurred_at": str(row["updated_at"] or ""),
                    "source": "meal_plans",
                    "target": str(row["id"] or ""),
                }
            )

        for row in self.conn.execute(
            "SELECT id, name, checked, updated_at, added_at FROM shopping_items "
            "WHERE COALESCE(updated_at, added_at) IS NOT NULL ORDER BY COALESCE(updated_at, added_at) DESC LIMIT ?",
            (per_table,),
        ).fetchall():
            checked = int(row["checked"] or 0) == 1
            _append(
                {
                    "kind": "shopping",
                    "module": "shopping",
                    "title": "Checked off shopping item" if checked else "Updated shopping item",
                    "detail": str(row["name"] or "Shopping item").strip(),
                    "occurred_at": str(row["updated_at"] or row["added_at"] or ""),
                    "source": "shopping_items",
                    "target": str(row["id"] or ""),
                }
            )

        for row in self.conn.execute(
            "SELECT id, name, storage, updated_at, added_at FROM pantry_items "
            "WHERE COALESCE(updated_at, added_at) IS NOT NULL ORDER BY COALESCE(updated_at, added_at) DESC LIMIT ?",
            (per_table,),
        ).fetchall():
            _append(
                {
                    "kind": "pantry",
                    "module": "pantry",
                    "title": "Updated kitchen item",
                    "detail": f"{str(row['name'] or 'Item').strip()} · {str(row['storage'] or 'Pantry').strip()}",
                    "occurred_at": str(row["updated_at"] or row["added_at"] or ""),
                    "source": "pantry_items",
                    "target": str(row["id"] or ""),
                }
            )

        for row in self.conn.execute(
            "SELECT id, food_name, log_date, updated_at, logged_at FROM nutrition_logs "
            "WHERE COALESCE(updated_at, logged_at) IS NOT NULL ORDER BY COALESCE(updated_at, logged_at) DESC LIMIT ?",
            (per_table,),
        ).fetchall():
            _append(
                {
                    "kind": "nutrition",
                    "module": "nutrition",
                    "title": "Logged nutrition entry",
                    "detail": f"{str(row['food_name'] or 'Entry').strip()} · {str(row['log_date'] or '').strip()}".strip(" ·"),
                    "occurred_at": str(row["updated_at"] or row["logged_at"] or ""),
                    "source": "nutrition_logs",
                    "target": str(row["id"] or ""),
                }
            )

        for row in self.conn.execute(
            "SELECT id, session_id, role, content, tool_names, updated_at, timestamp FROM dishy_chat_history "
            "WHERE COALESCE(updated_at, timestamp) IS NOT NULL "
            "ORDER BY COALESCE(updated_at, timestamp) DESC LIMIT ?",
            (max(per_table, 8),),
        ).fetchall():
            role = str(row["role"] or "").strip()
            body = str(row["content"] or "").strip().replace("\n", " ")
            _append(
                {
                    "kind": "ai",
                    "module": "dishy",
                    "title": "Dishy replied" if role == "assistant" else "Asked Dishy",
                    "detail": (body[:100] + ("…" if len(body) > 100 else "")) or "Dishy activity",
                    "occurred_at": str(row["updated_at"] or row["timestamp"] or ""),
                    "source": str(row["session_id"] or "dishy_chat_history"),
                    "target": str(row["id"] or ""),
                }
            )

        for row in self.conn.execute(
            "SELECT id, notif_type, title, message, severity, created_at FROM in_app_notifications "
            "ORDER BY created_at DESC LIMIT ?",
            (per_table,),
        ).fetchall():
            module = "system"
            notif_type = str(row["notif_type"] or "").strip()
            if notif_type.startswith("pantry_"):
                module = "pantry"
            _append(
                {
                    "kind": "notification",
                    "module": module,
                    "title": str(row["title"] or "Notification").strip(),
                    "detail": str(row["message"] or "").strip(),
                    "occurred_at": str(row["created_at"] or ""),
                    "source": notif_type or "in_app_notifications",
                    "target": str(row["id"] or ""),
                }
            )

        for row in self.conn.execute(
            "SELECT id, entity_type, reason, deleted_at FROM trash_bin ORDER BY deleted_at DESC LIMIT ?",
            (per_table,),
        ).fetchall():
            entity_type = str(row["entity_type"] or "item").replace("_", " ").strip()
            _append(
                {
                    "kind": "trash",
                    "module": "system",
                    "title": f"Deleted {entity_type}",
                    "detail": str(row["reason"] or "deleted").strip(),
                    "occurred_at": str(row["deleted_at"] or ""),
                    "source": "trash_bin",
                    "target": str(row["id"] or ""),
                }
            )

        telemetry_rows = self.conn.execute(
            "SELECT id, event_name, properties_json, created_at FROM telemetry_events "
            "WHERE event_name IN ("
            "'sync.completed','sync.failed','ai.request_succeeded','ai.request_failed',"
            "'ai.request_blocked','app.user_session_started','workflow.job_succeeded','workflow.job_failed'"
            ") ORDER BY created_at DESC LIMIT ?",
            (max(per_table, 10),),
        ).fetchall()
        for row in telemetry_rows:
            event_name = str(row["event_name"] or "").strip()
            try:
                props = json.loads(row["properties_json"] or "{}")
            except Exception:
                props = {}
            title = event_name.replace(".", " ").strip().title()
            detail = ""
            module = "system"
            kind = "system"
            if event_name == "sync.completed":
                kind = "sync"
                title = "Cloud sync completed"
                detail = f"pushed={int(props.get('pushed', 0) or 0)} · pulled={int(props.get('pulled', 0) or 0)}"
            elif event_name == "sync.failed":
                kind = "sync"
                module = "system"
                title = "Cloud sync failed"
                errors = props.get("errors") or []
                detail = "; ".join(str(e) for e in errors[:2]) if isinstance(errors, list) else str(errors)
            elif event_name.startswith("ai.request_"):
                kind = "ai"
                module = "dishy"
                title = {
                    "ai.request_succeeded": "Dishy request completed",
                    "ai.request_failed": "Dishy request failed",
                    "ai.request_blocked": "Dishy request blocked",
                }.get(event_name, title)
                detail = str(props.get("surface") or props.get("error") or "").strip()
            elif event_name.startswith("workflow.job_"):
                kind = "workflow"
                title = "Background job completed" if event_name.endswith("succeeded") else "Background job failed"
                detail = str(props.get("job_key") or props.get("job_type") or "").strip()
            elif event_name == "app.user_session_started":
                kind = "session"
                title = "Signed in"
                detail = str(props.get("email") or "").strip()
            _append(
                {
                    "kind": kind,
                    "module": module,
                    "title": title,
                    "detail": detail,
                    "occurred_at": str(row["created_at"] or ""),
                    "source": event_name,
                    "target": str(row["id"] or ""),
                }
            )

        changes.sort(
            key=lambda item: _parse_sync_ts(item.get("occurred_at")) or datetime.fromtimestamp(0, tz=timezone.utc),
            reverse=True,
        )
        return changes[: max(1, int(limit))]

    def run_integrity_scan(self) -> dict:
        """Return a readable data-integrity snapshot across user-facing tables."""
        base = self.get_sync_integrity_report()
        counts = {
            "recipes_empty_title": int(
                self.conn.execute(
                    "SELECT COUNT(*) AS c FROM recipes WHERE TRIM(COALESCE(title,''))=''"
                ).fetchone()["c"] or 0
            ),
            "shopping_empty_name": int(
                self.conn.execute(
                    "SELECT COUNT(*) AS c FROM shopping_items WHERE TRIM(COALESCE(name,''))=''"
                ).fetchone()["c"] or 0
            ),
            "pantry_empty_name": int(
                self.conn.execute(
                    "SELECT COUNT(*) AS c FROM pantry_items WHERE TRIM(COALESCE(name,''))=''"
                ).fetchone()["c"] or 0
            ),
            "nutrition_missing_core": int(
                self.conn.execute(
                    "SELECT COUNT(*) AS c FROM nutrition_logs "
                    "WHERE TRIM(COALESCE(log_date,''))='' OR TRIM(COALESCE(food_name,''))=''"
                ).fetchone()["c"] or 0
            ),
            "dishy_chat_missing_core": int(
                self.conn.execute(
                    "SELECT COUNT(*) AS c FROM dishy_chat_history "
                    "WHERE TRIM(COALESCE(session_id,''))='' OR TRIM(COALESCE(role,''))='' "
                    "OR TRIM(COALESCE(content,''))=''"
                ).fetchone()["c"] or 0
            ),
            "meal_slots_invalid_shape": int(
                self.conn.execute(
                    "SELECT COUNT(*) AS c FROM meal_plans "
                    "WHERE TRIM(COALESCE(week_start,''))='' "
                    "OR COALESCE(day_of_week,'') NOT IN ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday') "
                    "OR LOWER(COALESCE(meal_type,'')) NOT IN ('breakfast','lunch','dinner','snack')"
                ).fetchone()["c"] or 0
            ),
            "meal_slots_duplicate_keys": int(
                self.conn.execute(
                    "SELECT COUNT(*) AS c FROM ("
                    "  SELECT week_start, day_of_week, meal_type, COUNT(*) AS n"
                    "  FROM meal_plans"
                    "  GROUP BY week_start, day_of_week, meal_type"
                    "  HAVING n > 1"
                    ")"
                ).fetchone()["c"] or 0
            ),
        }
        issues = int(base.get("orphan_meal_slots", 0) or 0) + int(base.get("pending_tombstones", 0) or 0)
        issues += sum(int(v or 0) for v in counts.values())
        return {
            "sync": base,
            "table_issues": counts,
            "issue_count": issues,
            "healthy": issues == 0,
        }

    def run_sync_integrity_repair(self) -> dict:
        linked = self.reconcile_meal_plan_recipe_links()
        removed_orphans = self.cleanup_orphan_meal_plans()
        return {
            "linked_slots": int(linked or 0),
            "removed_orphans": int(removed_orphans or 0),
        }

    def get_saved_recipes(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM recipes ORDER BY is_favourite DESC, saved_at DESC"
        ).fetchall()

    def save_recipe(self, source_id: str, source: str, title: str,
                    image_url: str = "", summary: str = "",
                    servings: int = 0, ready_mins: int = 0,
                    data_json: str = "{}") -> int:
        now = _utc_now_iso()
        household_id = self._active_household_id()
        cursor = self.conn.execute(
            """INSERT INTO recipes
               (source_id, source, title, image_url, summary, servings, ready_mins,
                data_json, updated_at, household_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_id, source, title, image_url, summary, servings, ready_mins,
                data_json, now, household_id,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def toggle_favourite(self, recipe_id: int, is_fav: bool):
        now = _utc_now_iso()
        self.conn.execute(
            "UPDATE recipes SET is_favourite=?, updated_at=? WHERE id=?",
            (int(is_fav), now, recipe_id),
        )
        self.conn.commit()

    def delete_recipe(self, recipe_id: int):
        row = self.conn.execute(
            "SELECT * FROM recipes WHERE id=?", (recipe_id,)
        ).fetchone()
        if row:
            data = dict(row)
            self._stash_deleted_row("recipes", data, reason="delete_recipe")
            if row["cloud_id"]:
                self.add_tombstone("recipes", row["cloud_id"])
        self.conn.execute("DELETE FROM recipes WHERE id=?", (recipe_id,))
        self.conn.commit()

    def get_shopping_items(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM shopping_items"
            " WHERE trim(coalesce(name, '')) <> ''"
            " ORDER BY added_at ASC"
        ).fetchall()

    def add_shopping_item(self, name: str, quantity: str = "", unit: str = "",
                          source: str = "manual") -> int:
        clean_name = " ".join(str(name or "").split())
        if not clean_name:
            return 0
        now = _utc_now_iso()
        household_id = self._active_household_id()
        cursor = self.conn.execute(
            "INSERT INTO shopping_items (name, quantity, unit, source, updated_at, household_id)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (clean_name, quantity, unit, source or "manual", now, household_id),
        )
        self.conn.commit()
        return cursor.lastrowid

    def delete_shopping_item(self, item_id: int):
        row = self.conn.execute(
            "SELECT * FROM shopping_items WHERE id=?", (item_id,)
        ).fetchone()
        if row:
            data = dict(row)
            self._stash_deleted_row("shopping_items", data, reason="delete_shopping_item")
            if row["cloud_id"]:
                self.add_tombstone("shopping_items", row["cloud_id"])
        self.conn.execute("DELETE FROM shopping_items WHERE id=?", (item_id,))
        self.conn.commit()

    def toggle_shopping_item(self, item_id: int, checked: bool):
        now = _utc_now_iso()
        self.conn.execute(
            "UPDATE shopping_items SET checked=?, updated_at=? WHERE id=?",
            (int(checked), now, item_id),
        )
        self.conn.commit()

    def clear_checked_shopping_items(self):
        rows = self.conn.execute(
            "SELECT * FROM shopping_items WHERE checked=1"
        ).fetchall()
        for row in rows:
            data = dict(row)
            self._stash_deleted_row("shopping_items", data, reason="clear_checked")
            if row["cloud_id"]:
                self.add_tombstone("shopping_items", row["cloud_id"])
        self.conn.execute("DELETE FROM shopping_items WHERE checked=1")
        self.conn.commit()

    def get_meal_plan(self, week_start: str) -> list:
        return self.conn.execute(
            "SELECT * FROM meal_plans"
            " WHERE week_start=? AND recipe_id IS NOT NULL"
            " ORDER BY meal_type",
            (week_start,)
        ).fetchall()

    def set_meal_slot(self, week_start: str, day: str, meal_type: str,
                      custom_name: str = "", recipe_id=None, notes=_UNSET):
        now = _utc_now_iso()
        household_id = self._active_household_id()
        recipe_cloud_id = None
        if recipe_id:
            row = self.conn.execute(
                "SELECT cloud_id FROM recipes WHERE id=?",
                (recipe_id,),
            ).fetchone()
            if row:
                recipe_cloud_id = row["cloud_id"]
        existing = self.conn.execute(
            "SELECT id FROM meal_plans WHERE week_start=? AND day_of_week=? AND meal_type=?",
            (week_start, day, meal_type)
        ).fetchone()
        if existing:
            current_notes = self.conn.execute(
                "SELECT notes FROM meal_plans WHERE id=?",
                (existing["id"],),
            ).fetchone()
            next_notes = (
                current_notes["notes"]
                if notes is _UNSET and current_notes is not None
                else (notes or None)
            )
            self.conn.execute(
                "UPDATE meal_plans SET custom_name=?, recipe_id=?, recipe_cloud_id=?, notes=?, updated_at=?, household_id=?"
                " WHERE id=?",
                (custom_name, recipe_id, recipe_cloud_id, next_notes, now, household_id, existing["id"])
            )
        else:
            self.conn.execute(
                "INSERT INTO meal_plans"
                " (week_start, day_of_week, meal_type, custom_name, recipe_id, recipe_cloud_id, notes, updated_at, household_id)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    week_start,
                    day,
                    meal_type,
                    custom_name,
                    recipe_id,
                    recipe_cloud_id,
                    None if notes is _UNSET else (notes or None),
                    now,
                    household_id,
                )
            )
        self.conn.commit()

    def get_today_meal_slots(self) -> list:
        """Return all meal plan rows for today (any that have a recipe_id)."""
        from datetime import date, timedelta
        today = date.today()
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        day_name   = today.strftime("%A")
        rows = self.conn.execute(
            "SELECT meal_type, custom_name, recipe_id FROM meal_plans"
            " WHERE week_start=? AND day_of_week=? AND recipe_id IS NOT NULL",
            (week_start, day_name),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_today_meal_plan_with_nutrition(self) -> list:
        """Return today's meal plan slots joined with recipe nutrition data.

        Each row contains: meal_type, custom_name, recipe_id, data_json.
        Ordered breakfast → lunch → dinner.
        """
        from datetime import date, timedelta
        today      = date.today()
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        day_name   = today.strftime("%A")
        rows = self.conn.execute(
            "SELECT mp.meal_type, mp.custom_name, mp.recipe_id, r.data_json"
            " FROM meal_plans mp"
            " LEFT JOIN recipes r ON mp.recipe_id = r.id"
            " WHERE mp.week_start=? AND mp.day_of_week=? AND mp.recipe_id IS NOT NULL"
            " ORDER BY CASE mp.meal_type"
            "   WHEN 'breakfast' THEN 1 WHEN 'lunch' THEN 2"
            "   WHEN 'dinner' THEN 3 WHEN 'snack' THEN 4 ELSE 5 END",
            (week_start, day_name),
        ).fetchall()
        return [dict(r) for r in rows]

    def clear_meal_slot(self, week_start: str, day: str, meal_type: str):
        row = self.conn.execute(
            "SELECT * FROM meal_plans"
            " WHERE week_start=? AND day_of_week=? AND meal_type=?",
            (week_start, day, meal_type)
        ).fetchone()
        if row:
            data = dict(row)
            self._stash_deleted_row("meal_plans", data, reason="clear_meal_slot")
            if row["cloud_id"]:
                self.add_tombstone("meal_plans", row["cloud_id"])
        self.conn.execute(
            "DELETE FROM meal_plans WHERE week_start=? AND day_of_week=? AND meal_type=?",
            (week_start, day, meal_type)
        )
        self.conn.commit()

    def clear_week_meal_plan(self, week_start: str):
        rows = self.conn.execute(
            "SELECT * FROM meal_plans WHERE week_start=?",
            (week_start,)
        ).fetchall()
        for row in rows:
            data = dict(row)
            self._stash_deleted_row("meal_plans", data, reason="clear_week_meal_plan")
            if row["cloud_id"]:
                self.add_tombstone("meal_plans", row["cloud_id"])
        self.conn.execute("DELETE FROM meal_plans WHERE week_start=?", (week_start,))
        self.conn.commit()

    def clear_all_meal_plans(self):
        """Delete every meal plan row across all weeks."""
        rows = self.conn.execute(
            "SELECT * FROM meal_plans"
        ).fetchall()
        for row in rows:
            data = dict(row)
            self._stash_deleted_row("meal_plans", data, reason="clear_all_meal_plans")
            if row["cloud_id"]:
                self.add_tombstone("meal_plans", row["cloud_id"])
        self.conn.execute("DELETE FROM meal_plans")
        self.conn.commit()

    def cleanup_orphan_meal_plans(self) -> int:
        """Remove meal plan rows that have no valid recipe attached.

        This covers two cases:
        - recipe_id IS NULL (recipe was deleted, FK set null)
        - recipe_id points to a recipe row that no longer exists locally

        Tombstones are written for any cloud-synced rows so the deletion
        propagates to Supabase on the next sync.

        Returns the number of rows removed.
        """
        # Preserve recipe_id NULL rows: they may represent unresolved cloud links.
        orphans = self.conn.execute(
            "SELECT mp.id, mp.cloud_id FROM meal_plans mp"
            " WHERE mp.recipe_id IS NOT NULL"
            "   AND mp.recipe_id NOT IN (SELECT id FROM recipes)"
        ).fetchall()
        for row in orphans:
            if row["cloud_id"]:
                self.add_tombstone("meal_plans", row["cloud_id"])
            self.conn.execute("DELETE FROM meal_plans WHERE id=?", (row["id"],))
        if orphans:
            self.conn.commit()
        return len(orphans)

    def reconcile_meal_plan_recipe_links(self) -> int:
        """Resolve meal_plans.recipe_id from recipe_cloud_id where possible."""
        cursor = self.conn.execute(
            "UPDATE meal_plans AS mp"
            " SET recipe_id = (SELECT r.id FROM recipes r WHERE r.cloud_id = mp.recipe_cloud_id)"
            " WHERE mp.recipe_cloud_id IS NOT NULL"
            "   AND (mp.recipe_id IS NULL OR mp.recipe_id NOT IN (SELECT id FROM recipes))"
            "   AND EXISTS (SELECT 1 FROM recipes r2 WHERE r2.cloud_id = mp.recipe_cloud_id)"
        )
        self.conn.commit()
        return int(cursor.rowcount or 0)

    def cleanup_unlinked_cloud_meal_plans(self) -> int:
        """Delete cloud-linked meal rows that have no resolvable recipe link.

        These are legacy/stale rows that can cause ghost meals to reappear on login.
        Local-only rows (cloud_id IS NULL) are never touched here.
        """
        rows = self.conn.execute(
            "SELECT id, cloud_id FROM meal_plans"
            " WHERE cloud_id IS NOT NULL"
            "   AND recipe_id IS NULL"
            "   AND ("
            "        recipe_cloud_id IS NULL"
            "        OR recipe_cloud_id NOT IN (SELECT cloud_id FROM recipes WHERE cloud_id IS NOT NULL)"
            "   )"
        ).fetchall()
        for row in rows:
            if row["cloud_id"]:
                self.add_tombstone("meal_plans", row["cloud_id"])
            self.conn.execute("DELETE FROM meal_plans WHERE id=?", (row["id"],))
        if rows:
            self.conn.commit()
        return len(rows)

    def clear_meal_day_slots(self, week_start: str, day: str):
        """Delete all meal slots (breakfast, lunch, dinner) for a specific day in a week."""
        rows = self.conn.execute(
            "SELECT * FROM meal_plans"
            " WHERE week_start=? AND day_of_week=?",
            (week_start, day)
        ).fetchall()
        for row in rows:
            data = dict(row)
            self._stash_deleted_row("meal_plans", data, reason="clear_meal_day_slots")
            if row["cloud_id"]:
                self.add_tombstone("meal_plans", row["cloud_id"])
        self.conn.execute(
            "DELETE FROM meal_plans WHERE week_start=? AND day_of_week=?",
            (week_start, day)
        )
        self.conn.commit()

    def clear_all_shopping_items(self):
        rows = self.conn.execute(
            "SELECT * FROM shopping_items"
        ).fetchall()
        for row in rows:
            data = dict(row)
            self._stash_deleted_row("shopping_items", data, reason="clear_all_shopping_items")
            if row["cloud_id"]:
                self.add_tombstone("shopping_items", row["cloud_id"])
        self.conn.execute("DELETE FROM shopping_items")
        self.conn.commit()

    def delete_all_recipes(self):
        rows = self.conn.execute(
            "SELECT * FROM recipes"
        ).fetchall()
        for row in rows:
            data = dict(row)
            self._stash_deleted_row("recipes", data, reason="delete_all_recipes")
            if row["cloud_id"]:
                self.add_tombstone("recipes", row["cloud_id"])
        self.conn.execute("DELETE FROM recipes")
        self.conn.commit()

    def delete_shopping_item_by_name(self, name: str) -> int:
        """Delete first matching item (case-insensitive). Returns deleted count."""
        row = self.conn.execute(
            "SELECT * FROM shopping_items WHERE lower(name) = lower(?) LIMIT 1",
            (name,)
        ).fetchone()
        if row:
            data = dict(row)
            self._stash_deleted_row("shopping_items", data, reason="delete_by_name")
            if row["cloud_id"]:
                self.add_tombstone("shopping_items", row["cloud_id"])
            self.conn.execute("DELETE FROM shopping_items WHERE id=?", (row["id"],))
            self.conn.commit()
            return 1
        return 0

    def delete_recipe_by_title(self, title: str) -> int:
        """Delete first recipe whose title matches (case-insensitive). Returns deleted count."""
        row = self.conn.execute(
            "SELECT * FROM recipes WHERE lower(title) = lower(?) LIMIT 1", (title,)
        ).fetchone()
        if row:
            data = dict(row)
            self._stash_deleted_row("recipes", data, reason="delete_by_title")
            if row["cloud_id"]:
                self.add_tombstone("recipes", row["cloud_id"])
            self.conn.execute("DELETE FROM recipes WHERE id=?", (row["id"],))
            self.conn.commit()
            return 1
        return 0

    def get_recent_recipes(self, limit: int = 3) -> list:
        return self.conn.execute(
            "SELECT * FROM recipes ORDER BY saved_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def get_nutrition_logs(self, date_str: str) -> list:
        return self.conn.execute(
            "SELECT * FROM nutrition_logs WHERE log_date=? ORDER BY logged_at ASC",
            (date_str,)
        ).fetchall()

    def add_nutrition_log(self, date_str: str, food_name: str,
                          kcal: float, protein_g: float, carbs_g: float,
                          fat_g: float, fiber_g: float, sugar_g: float) -> int:
        now = _utc_now_iso()
        household_id = self._active_household_id()
        cursor = self.conn.execute(
            "INSERT INTO nutrition_logs"
            " (log_date, food_name, kcal, protein_g, carbs_g, fat_g, fiber_g, sugar_g,"
            "  updated_at, household_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                date_str, food_name, kcal, protein_g, carbs_g, fat_g, fiber_g, sugar_g,
                now, household_id,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def delete_nutrition_log(self, log_id: int):
        row = self.conn.execute(
            "SELECT cloud_id FROM nutrition_logs WHERE id=?", (log_id,)
        ).fetchone()
        if row and row["cloud_id"]:
            self.add_tombstone("nutrition_logs", row["cloud_id"])
        self.conn.execute("DELETE FROM nutrition_logs WHERE id=?", (log_id,))
        self.conn.commit()

    def remove_nutrition_log_by_name(self, date_str: str, food_name: str) -> bool:
        """Remove all nutrition log entries matching food_name (case-insensitive) for a given date."""
        rows = self.conn.execute(
            "SELECT cloud_id FROM nutrition_logs"
            " WHERE log_date=? AND lower(food_name)=lower(?) AND cloud_id IS NOT NULL",
            (date_str, food_name),
        ).fetchall()
        for row in rows:
            self.add_tombstone("nutrition_logs", row["cloud_id"])
        cursor = self.conn.execute(
            "DELETE FROM nutrition_logs WHERE log_date=? AND lower(food_name)=lower(?)",
            (date_str, food_name),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def auto_log_meal_nutrition(self, date_str: str, meal_name: str, recipe_id: int) -> bool:
        """Look up a recipe's per-serving nutrition and add it to the daily log.

        Silently skips if:
        - the recipe has no stored nutrition data
        - an entry with the same food_name already exists for date_str

        Returns True if a new log entry was added.
        """
        if not recipe_id or not meal_name:
            return False
        try:
            import json as _json
            rec = self.conn.execute(
                "SELECT data_json FROM recipes WHERE id=?", (recipe_id,)
            ).fetchone()
            if not rec:
                return False
            dj    = _json.loads(rec["data_json"] or "{}")
            per_s = dj.get("nutrition_per_serving", {})
            kcal  = float(per_s.get("kcal", 0) or 0)
            if kcal <= 0:
                return False
            existing = {r["food_name"].lower() for r in self.get_nutrition_logs(date_str)}
            if meal_name.lower() in existing:
                return False
            self.add_nutrition_log(
                date_str, meal_name[:80],
                kcal,
                float(per_s.get("protein_g", 0) or 0),
                float(per_s.get("carbs_g",   0) or 0),
                float(per_s.get("fat_g",     0) or 0),
                float(per_s.get("fiber_g",   0) or 0),
                float(per_s.get("sugar_g",   0) or 0),
            )
            return True
        except Exception:
            return False

    def get_nutrition_logs_range(self, start_date: str, end_date: str) -> list:
        """Return all nutrition log entries between start_date and end_date (inclusive)."""
        return self.conn.execute(
            "SELECT * FROM nutrition_logs WHERE log_date BETWEEN ? AND ? ORDER BY log_date, logged_at",
            (start_date, end_date),
        ).fetchall()

    # -- Dishy chat history ------------------------------------------------

    def save_dishy_message(self, session_id: str, role: str, content: str,
                           tool_names: str = "") -> int:
        now = _utc_now_iso()
        cursor = self.conn.execute(
            "INSERT INTO dishy_chat_history"
            " (session_id, role, content, tool_names, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, tool_names, now),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_dishy_session(self, session_id: str) -> list:
        return self.conn.execute(
            "SELECT * FROM dishy_chat_history WHERE session_id=? ORDER BY id ASC",
            (session_id,)
        ).fetchall()

    def get_latest_dishy_session(self):
        """Return (session_id, rows) for the most recent session, or None."""
        row = self.conn.execute(
            "SELECT session_id FROM dishy_chat_history"
            " GROUP BY session_id ORDER BY MAX(timestamp) DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        sid = row["session_id"]
        rows = self.get_dishy_session(sid)
        return (sid, rows) if rows else None

    def get_dishy_sessions_summary(self) -> list:
        """Return all sessions ordered by most recent, with first user message + count."""
        sessions = self.conn.execute(
            "SELECT session_id, COUNT(*) as message_count,"
            " MIN(timestamp) as start_time, MAX(timestamp) as last_time"
            " FROM dishy_chat_history GROUP BY session_id"
            " ORDER BY MAX(timestamp) DESC"
        ).fetchall()
        result = []
        for s in sessions:
            first_msg = self.conn.execute(
                "SELECT content FROM dishy_chat_history"
                " WHERE session_id=? AND role='user' ORDER BY id ASC LIMIT 1",
                (s["session_id"],)
            ).fetchone()
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(s["last_time"])
                date_str = dt.strftime("%d %b %Y, %H:%M")
            except Exception:
                date_str = s["last_time"] or ""
            result.append({
                "session_id": s["session_id"],
                "message_count": s["message_count"],
                "date": date_str,
                "first_message": first_msg["content"] if first_msg else "(empty)",
            })
        return result

    def delete_dishy_session(self, session_id: str):
        self.conn.execute(
            "DELETE FROM dishy_chat_history WHERE session_id=?", (session_id,)
        )
        self.conn.commit()

    def clear_dishy_history(self):
        self.conn.execute("DELETE FROM dishy_chat_history")
        self.conn.commit()

    # Settings keys that belong to the device, not the user account.
    # These survive an account switch so the app stays usable immediately.
    _DEVICE_SETTING_KEYS = frozenset({
        "theme",
        "supabase_url",
        "supabase_anon_key",
        "active_user_id",   # needed so account-switch detection survives the wipe
        "in_app_notifications_enabled",
        "telemetry_enabled",
        "posthog_enabled",
        "sentry_enabled",
        "dishy_daily_limit",
    })

    def clear_user_data(self) -> None:
        """Wipe all user-data tables AND user-specific settings on account switch.

        Device-level settings (theme, Supabase credentials) are preserved so
        the app stays usable immediately after the switch.
        """
        self.conn.executescript("""
            DELETE FROM recipes;
            DELETE FROM meal_plans;
            DELETE FROM shopping_items;
            DELETE FROM nutrition_logs;
            DELETE FROM dishy_chat_history;
            DELETE FROM sync_tombstones;
            DELETE FROM pantry_items;
            DELETE FROM in_app_notifications;
            DELETE FROM ai_usage_daily;
            DELETE FROM workflow_jobs;
            DELETE FROM telemetry_events;
            DELETE FROM trash_bin;
            DELETE FROM recipe_source_stats;
            DELETE FROM pantry_waste_log;
        """)
        # Delete all user-specific settings (onboarding, sync timestamps,
        # macro goals, preferences, etc.) — keep only device-level keys.
        placeholders = ",".join("?" * len(self._DEVICE_SETTING_KEYS))
        self.conn.execute(
            f"DELETE FROM settings"
            f" WHERE key NOT IN ({placeholders})"
            " AND key NOT LIKE 'ff.global.%'"
            " AND key NOT LIKE 'cfg.global.%'",
            tuple(self._DEVICE_SETTING_KEYS),
        )
        self.conn.commit()

    def ensure_active_user_scope(self, user_id: str) -> bool:
        """Ensure local cache belongs to user_id; wipe stale cache when uncertain.

        Returns True when a cache wipe was performed.
        """
        uid = str(user_id or "").strip()
        if not uid:
            return False

        stored_user_id = str(self.get_setting("active_user_id", "") or "").strip()
        should_wipe = False

        if stored_user_id and stored_user_id != uid:
            should_wipe = True
        elif not stored_user_id:
            # Legacy installs may have local data but no ownership marker.
            for table in self._USER_DATA_TABLES:
                row = self.conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
                if int((row["c"] if row else 0) or 0) > 0:
                    should_wipe = True
                    break

        if should_wipe:
            self.clear_user_data()

        self.set_setting("active_user_id", uid)
        return should_wipe

    # -- Pantry / fridge / freezer helpers --------------------------------

    def add_pantry_item(self, name: str, quantity=None, unit: str = "",
                        storage: str = "Pantry", expiry_date: str = None) -> int:
        now = _utc_now_iso()
        household_id = self._active_household_id()
        cursor = self.conn.execute(
            "INSERT INTO pantry_items (name, quantity, unit, storage, expiry_date, updated_at, household_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, quantity, unit or "", storage or "Pantry", expiry_date, now, household_id),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_pantry_items(self, storage: str = None) -> list:
        if storage:
            rows = self.conn.execute(
                "SELECT * FROM pantry_items WHERE storage=? ORDER BY name ASC", (storage,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM pantry_items ORDER BY storage ASC, name ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def update_pantry_item(self, item_id: int, quantity=None, unit: str = "",
                           expiry_date: str = None):
        now = _utc_now_iso()
        self.conn.execute(
            "UPDATE pantry_items SET quantity=?, unit=?, expiry_date=?, updated_at=?"
            " WHERE id=?",
            (quantity, unit or "", expiry_date, now, item_id),
        )
        self.conn.commit()

    def delete_pantry_item(self, item_id: int):
        row = self.conn.execute(
            "SELECT * FROM pantry_items WHERE id=?", (item_id,)
        ).fetchone()
        if row:
            data = dict(row)
            self._stash_deleted_row("pantry_items", data, reason="delete_pantry_item")
            self._log_pantry_waste(data, reason="manual_delete")
            if row["cloud_id"]:
                self.add_tombstone("pantry_items", row["cloud_id"])
        self.conn.execute("DELETE FROM pantry_items WHERE id=?", (item_id,))
        self.conn.commit()

    def clear_pantry(self, storage: str = None):
        if storage:
            rows = self.conn.execute(
                "SELECT * FROM pantry_items WHERE storage=?",
                (storage,)
            ).fetchall()
            for row in rows:
                data = dict(row)
                self._stash_deleted_row("pantry_items", data, reason=f"clear_pantry:{storage}")
                self._log_pantry_waste(data, reason="clear_storage")
                if row["cloud_id"]:
                    self.add_tombstone("pantry_items", row["cloud_id"])
            self.conn.execute("DELETE FROM pantry_items WHERE storage=?", (storage,))
        else:
            rows = self.conn.execute(
                "SELECT * FROM pantry_items"
            ).fetchall()
            for row in rows:
                data = dict(row)
                self._stash_deleted_row("pantry_items", data, reason="clear_pantry")
                self._log_pantry_waste(data, reason="clear_all")
                if row["cloud_id"]:
                    self.add_tombstone("pantry_items", row["cloud_id"])
            self.conn.execute("DELETE FROM pantry_items")
        self.conn.commit()

    def deduct_pantry_ingredients(self, ingredients: list) -> None:
        """Parse ingredient strings and subtract quantities from matching pantry items."""
        import re
        pattern = re.compile(r'^(\d+\.?\d*)\s*([a-zA-Z]*)\s+(.+)$')
        for ingredient in ingredients:
            if not ingredient:
                continue
            m = pattern.match(ingredient.strip())
            if not m:
                continue
            qty_str, _unit, name = m.group(1), m.group(2), m.group(3).strip()
            try:
                qty = float(qty_str)
            except ValueError:
                continue
            # Fuzzy match: ingredient name in pantry name or vice versa
            name_lower = name.lower()
            rows = self.conn.execute(
                "SELECT id, name, quantity, cloud_id FROM pantry_items"
            ).fetchall()
            for row in rows:
                row_name = row["name"] or ""
                if row_name.lower() in name_lower or name_lower in row_name.lower():
                    existing_qty = float(row["quantity"] or 0)
                    new_qty = existing_qty - qty
                    if new_qty <= 0:
                        if row["cloud_id"]:
                            self.add_tombstone("pantry_items", row["cloud_id"])
                        self.conn.execute("DELETE FROM pantry_items WHERE id=?", (row["id"],))
                    else:
                        self.conn.execute(
                            "UPDATE pantry_items SET quantity=?, updated_at=?"
                            " WHERE id=?",
                            (new_qty, _utc_now_iso(), row["id"]),
                        )
                    break
        self.conn.commit()

    # -- In-app notifications ----------------------------------------------

    def add_in_app_notification(
        self,
        user_id: str,
        notif_type: str,
        title: str,
        message: str,
        *,
        severity: str = "info",
        data_json: str = "{}",
        dedupe_key: str | None = None,
    ) -> int | None:
        """Insert a notification. Returns row id, or None when deduped."""
        now = _utc_now_iso()
        try:
            cursor = self.conn.execute(
                "INSERT INTO in_app_notifications"
                " (user_id, notif_type, title, message, severity, data_json, dedupe_key, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id or "",
                    notif_type or "general",
                    title or "Notification",
                    message or "",
                    severity or "info",
                    data_json or "{}",
                    dedupe_key,
                    now,
                ),
            )
            self.conn.commit()
            return int(cursor.lastrowid or 0)
        except Exception:
            return None

    def get_in_app_notifications(
        self,
        user_id: str,
        *,
        limit: int = 100,
        unread_only: bool = False,
    ) -> list[dict]:
        sql = (
            "SELECT * FROM in_app_notifications"
            " WHERE user_id=?"
            + (" AND read_at IS NULL" if unread_only else "")
            + " ORDER BY created_at DESC LIMIT ?"
        )
        rows = self.conn.execute(sql, (user_id or "", max(1, int(limit)))).fetchall()
        return [dict(r) for r in rows]

    def get_unread_notification_count(self, user_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM in_app_notifications"
            " WHERE user_id=? AND read_at IS NULL",
            (user_id or "",),
        ).fetchone()
        return int((row["c"] if row else 0) or 0)

    def mark_in_app_notification_read(self, notification_id: int) -> None:
        self.conn.execute(
            "UPDATE in_app_notifications SET read_at=?, updated_at=? WHERE id=?",
            (_utc_now_iso(), _utc_now_iso(), int(notification_id)),
        )
        self.conn.commit()

    def mark_all_in_app_notifications_read(self, user_id: str) -> int:
        cursor = self.conn.execute(
            "UPDATE in_app_notifications"
            " SET read_at=?, updated_at=?"
            " WHERE user_id=? AND read_at IS NULL",
            (_utc_now_iso(), _utc_now_iso(), user_id or ""),
        )
        self.conn.commit()
        return int(cursor.rowcount or 0)

    def delete_old_read_notifications(self, older_than_days: int = 30) -> int:
        cursor = self.conn.execute(
            "DELETE FROM in_app_notifications"
            " WHERE read_at IS NOT NULL"
            " AND datetime(read_at) <= datetime('now', ?)",
            (f"-{max(1, int(older_than_days))} days",),
        )
        self.conn.commit()
        return int(cursor.rowcount or 0)

    # -- AI usage metering --------------------------------------------------

    def get_ai_usage(self, user_id: str, usage_date: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM ai_usage_daily WHERE user_id=? AND usage_date=?",
            (user_id or "", usage_date),
        ).fetchone()
        if not row:
            return {
                "user_id": user_id or "",
                "usage_date": usage_date,
                "request_count": 0,
                "blocked_count": 0,
            }
        return dict(row)

    def increment_ai_usage(self, user_id: str, usage_date: str, *, blocked: bool = False) -> dict:
        """Increment request counter (and optionally blocked counter) for a day."""
        now = _utc_now_iso()
        self.conn.execute(
            "INSERT INTO ai_usage_daily (user_id, usage_date, request_count, blocked_count, updated_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(user_id, usage_date) DO UPDATE SET"
            " request_count = ai_usage_daily.request_count + 1,"
            " blocked_count = ai_usage_daily.blocked_count + excluded.blocked_count,"
            " updated_at = excluded.updated_at",
            (user_id or "", usage_date, 1, 1 if blocked else 0, now),
        )
        self.conn.commit()
        return self.get_ai_usage(user_id, usage_date)

    def increment_ai_blocked(self, user_id: str, usage_date: str) -> dict:
        now = _utc_now_iso()
        self.conn.execute(
            "INSERT INTO ai_usage_daily (user_id, usage_date, request_count, blocked_count, updated_at)"
            " VALUES (?, ?, 0, 1, ?)"
            " ON CONFLICT(user_id, usage_date) DO UPDATE SET"
            " blocked_count = ai_usage_daily.blocked_count + 1,"
            " updated_at = excluded.updated_at",
            (user_id or "", usage_date, now),
        )
        self.conn.commit()
        return self.get_ai_usage(user_id, usage_date)

    def get_ai_usage_history(self, user_id: str, *, days: int = 14) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM ai_usage_daily"
            " WHERE user_id=?"
            " ORDER BY usage_date DESC LIMIT ?",
            (user_id or "", max(1, int(days))),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Workflow jobs ------------------------------------------------------

    def upsert_workflow_job(
        self,
        job_key: str,
        job_type: str,
        *,
        payload_json: str = "{}",
        run_every_minutes: int = 60,
        next_run_at: str | None = None,
    ) -> None:
        now = _utc_now_iso()
        next_run = next_run_at or now
        self.conn.execute(
            "INSERT INTO workflow_jobs"
            " (job_key, job_type, payload_json, status, run_every_minutes, next_run_at, updated_at)"
            " VALUES (?, ?, ?, 'scheduled', ?, ?, ?)"
            " ON CONFLICT(job_key) DO UPDATE SET"
            " job_type=excluded.job_type,"
            " payload_json=excluded.payload_json,"
            " run_every_minutes=excluded.run_every_minutes,"
            " next_run_at=CASE"
            "   WHEN workflow_jobs.status='running' THEN workflow_jobs.next_run_at"
            "   ELSE excluded.next_run_at"
            " END,"
            " updated_at=excluded.updated_at",
            (
                job_key,
                job_type,
                payload_json or "{}",
                max(1, int(run_every_minutes)),
                next_run,
                now,
            ),
        )
        self.conn.commit()

    def get_due_workflow_jobs(self, now_iso: str, *, limit: int = 8) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM workflow_jobs"
            " WHERE next_run_at <= ?"
            "   AND status != 'running'"
            " ORDER BY next_run_at ASC LIMIT ?",
            (now_iso, max(1, int(limit))),
        ).fetchall()
        jobs = [dict(r) for r in rows]
        for job in jobs:
            self.conn.execute(
                "UPDATE workflow_jobs SET status='running', updated_at=? WHERE id=?",
                (_utc_now_iso(), job["id"]),
            )
        if jobs:
            self.conn.commit()
        return jobs

    def mark_workflow_job_result(
        self,
        job_id: int,
        *,
        ok: bool,
        next_run_at: str,
        last_error: str = "",
    ) -> None:
        self.conn.execute(
            "UPDATE workflow_jobs"
            " SET status=?,"
            "     next_run_at=?,"
            "     last_run_at=?,"
            "     last_error=?,"
            "     attempt_count = CASE WHEN ? THEN 0 ELSE attempt_count + 1 END,"
            "     updated_at=?"
            " WHERE id=?",
            (
                "scheduled" if ok else "error",
                next_run_at,
                _utc_now_iso(),
                (last_error or "")[:500],
                1 if ok else 0,
                _utc_now_iso(),
                int(job_id),
            ),
        )
        self.conn.commit()

    def list_workflow_jobs(self, *, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM workflow_jobs"
            " ORDER BY updated_at DESC, next_run_at ASC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(r) for r in rows]

    def recover_stuck_workflow_jobs(self, *, older_than_minutes: int = 20) -> int:
        """Recover jobs left in 'running' state after app crash/force quit."""
        mins = max(1, int(older_than_minutes))
        now = _utc_now_iso()
        cursor = self.conn.execute(
            "UPDATE workflow_jobs"
            " SET status='scheduled',"
            "     next_run_at=?,"
            "     last_error=CASE"
            "       WHEN COALESCE(last_error, '')='' THEN 'Recovered stale running job at startup'"
            "       ELSE last_error"
            "     END,"
            "     updated_at=?"
            " WHERE status='running'"
            "   AND (updated_at IS NULL OR datetime(updated_at) <= datetime('now', ?))",
            (now, now, f"-{mins} minutes"),
        )
        self.conn.commit()
        return int(cursor.rowcount or 0)

    # -- Telemetry events ---------------------------------------------------

    def add_telemetry_event(self, user_id: str, event_name: str, properties_json: str = "{}") -> int:
        cursor = self.conn.execute(
            "INSERT INTO telemetry_events (user_id, event_name, properties_json)"
            " VALUES (?, ?, ?)",
            (user_id or "", event_name or "event", properties_json or "{}"),
        )
        self.conn.commit()
        return int(cursor.lastrowid or 0)

    def get_telemetry_events(self, user_id: str, *, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM telemetry_events WHERE user_id=?"
            " ORDER BY created_at DESC LIMIT ?",
            (user_id or "", max(1, int(limit))),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_telemetry_event_at(self, user_id: str = "") -> str:
        if user_id:
            row = self.conn.execute(
                "SELECT created_at FROM telemetry_events WHERE user_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT created_at FROM telemetry_events ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return str(row["created_at"]) if row and row["created_at"] else ""

    # -- Monitoring helpers -------------------------------------------------

    def get_table_count(self, table_name: str) -> int:
        row = self.conn.execute(f"SELECT COUNT(*) AS c FROM {table_name}").fetchone()
        return int((row["c"] if row else 0) or 0)

    # -- Cloud sync helpers ------------------------------------------------

    def add_tombstone(self, table_name: str, cloud_id: str) -> None:
        """Record a cloud deletion that needs to be propagated during the next sync."""
        try:
            household_id = self._active_household_id()
            self.conn.execute(
                "INSERT INTO sync_tombstones (table_name, cloud_id, household_id)"
                " VALUES (?, ?, ?)",
                (table_name, cloud_id, household_id),
            )
            self.conn.commit()
        except Exception:
            pass

    def get_pending_tombstones(self) -> list[dict]:
        """Return all unprocessed tombstones."""
        rows = self.conn.execute(
            "SELECT * FROM sync_tombstones ORDER BY created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def clear_tombstone(self, tombstone_id: int) -> None:
        self.conn.execute("DELETE FROM sync_tombstones WHERE id=?", (tombstone_id,))
        self.conn.commit()

    def get_unsynced_rows(self, table: str) -> list:
        """Return rows where cloud_id IS NULL (never pushed to cloud)."""
        return self.conn.execute(
            f"SELECT * FROM {table} WHERE cloud_id IS NULL"
        ).fetchall()

    def get_modified_rows_since(self, table: str, since_iso: str) -> list:
        """Return rows with cloud_id set and updated_at newer than since_iso.

        Timestamp formats have changed over releases; we compare parsed datetimes
        in Python so old SQLite rows don't get skipped due to string-format drift.
        """
        since_dt = _parse_sync_ts(since_iso) or datetime.fromtimestamp(0, tz=timezone.utc)
        rows = self.conn.execute(
            f"SELECT * FROM {table} WHERE cloud_id IS NOT NULL"
        ).fetchall()
        changed = []
        for row in rows:
            updated_dt = _parse_sync_ts(row["updated_at"])
            if updated_dt and updated_dt > since_dt:
                changed.append(row)
        return changed

    def set_cloud_id(self, table: str, local_id: int, cloud_id: str) -> None:
        """Write the Supabase UUID back to the local row after a successful push."""
        self.conn.execute(
            f"UPDATE {table} SET cloud_id=? WHERE id=?", (cloud_id, local_id)
        )
        self.conn.commit()

    def upsert_row_from_cloud(self, table: str, cloud_row: dict,
                              local_col_map: dict) -> None:
        """Insert or update a local row that arrived from a cloud pull.

        local_col_map maps cloud column names → local column names for any
        that differ.  All cloud columns not in the map use the same name.
        """
        cloud_id = str(cloud_row.get("id", ""))
        # Check if row already exists locally by cloud_id
        existing = self.conn.execute(
            f"SELECT id, updated_at, cloud_id FROM {table} WHERE cloud_id=?", (cloud_id,)
        ).fetchone()

        # Build column dict, remapping keys as needed
        data = {}
        for k, v in cloud_row.items():
            if k in ("id", "user_id"):
                continue
            local_k = local_col_map.get(k, k)
            if local_k == "updated_at":
                data[local_k] = _normalise_sync_ts(v) or v
            else:
                data[local_k] = v
        data["cloud_id"] = cloud_id

        target = existing

        # meal_plans has a unique slot key; reconcile by slot if cloud_id differs.
        if table == "meal_plans" and target is None:
            wk = data.get("week_start")
            day = data.get("day_of_week")
            meal = data.get("meal_type")
            if wk and day and meal:
                target = self.conn.execute(
                    "SELECT id, updated_at, cloud_id FROM meal_plans"
                    " WHERE week_start=? AND day_of_week=? AND meal_type=?",
                    (wk, day, meal),
                ).fetchone()

        if target:
            cloud_newer = _cloud_is_newer(target["updated_at"], cloud_row.get("updated_at"))
            if cloud_newer:
                set_clause = ", ".join(f"{k}=?" for k in data)
                self.conn.execute(
                    f"UPDATE {table} SET {set_clause} WHERE id=?",
                    list(data.values()) + [target["id"]],
                )
            else:
                # Keep newer/equal local row, but attach cloud_id if missing so future pulls match.
                if not target["cloud_id"] and cloud_id:
                    self.conn.execute(
                        f"UPDATE {table} SET cloud_id=? WHERE id=?",
                        (cloud_id, target["id"]),
                    )
        else:
            cols   = ", ".join(data.keys())
            placeholders = ", ".join("?" for _ in data)
            self.conn.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                list(data.values()),
            )
        self.conn.commit()

    def get_nutrition_totals_for_range(self, start_date: str, end_date: str) -> dict:
        """Return summed macro totals for a date range, plus entry count and days logged."""
        rows = self.get_nutrition_logs_range(start_date, end_date)
        totals: dict = {
            "kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0,
            "fat_g": 0.0, "fiber_g": 0.0, "sugar_g": 0.0,
            "entries": len(rows), "days": 0,
        }
        days: set = set()
        for r in rows:
            for key in ["kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g"]:
                totals[key] += float(r[key])
            days.add(r["log_date"])
        totals["days"] = len(days)
        return totals
