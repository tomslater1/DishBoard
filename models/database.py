import sqlite3
import os

from utils.paths import get_data_dir

DB_PATH = os.path.join(get_data_dir(), "dishboard.db")


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._conn: sqlite3.Connection | None = None

    def connect(self):
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
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
    ]
    _LATEST_SCHEMA_VERSION = 2

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

    def get_saved_recipes(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM recipes ORDER BY is_favourite DESC, saved_at DESC"
        ).fetchall()

    def save_recipe(self, source_id: str, source: str, title: str,
                    image_url: str = "", summary: str = "",
                    servings: int = 0, ready_mins: int = 0,
                    data_json: str = "{}") -> int:
        cursor = self.conn.execute(
            """INSERT INTO recipes
               (source_id, source, title, image_url, summary, servings, ready_mins,
                data_json, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (source_id, source, title, image_url, summary, servings, ready_mins, data_json),
        )
        self.conn.commit()
        return cursor.lastrowid

    def toggle_favourite(self, recipe_id: int, is_fav: bool):
        self.conn.execute(
            "UPDATE recipes SET is_favourite=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (int(is_fav), recipe_id),
        )
        self.conn.commit()

    def delete_recipe(self, recipe_id: int):
        row = self.conn.execute(
            "SELECT cloud_id FROM recipes WHERE id=?", (recipe_id,)
        ).fetchone()
        if row and row["cloud_id"]:
            self.add_tombstone("recipes", row["cloud_id"])
        self.conn.execute("DELETE FROM recipes WHERE id=?", (recipe_id,))
        self.conn.commit()

    def get_shopping_items(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM shopping_items ORDER BY added_at ASC"
        ).fetchall()

    def add_shopping_item(self, name: str, quantity: str = "", unit: str = "",
                          source: str = "manual") -> int:
        cursor = self.conn.execute(
            "INSERT INTO shopping_items (name, quantity, unit, source, updated_at)"
            " VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (name, quantity, unit, source),
        )
        self.conn.commit()
        return cursor.lastrowid

    def delete_shopping_item(self, item_id: int):
        row = self.conn.execute(
            "SELECT cloud_id FROM shopping_items WHERE id=?", (item_id,)
        ).fetchone()
        if row and row["cloud_id"]:
            self.add_tombstone("shopping_items", row["cloud_id"])
        self.conn.execute("DELETE FROM shopping_items WHERE id=?", (item_id,))
        self.conn.commit()

    def toggle_shopping_item(self, item_id: int, checked: bool):
        self.conn.execute(
            "UPDATE shopping_items SET checked=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (int(checked), item_id),
        )
        self.conn.commit()

    def clear_checked_shopping_items(self):
        rows = self.conn.execute(
            "SELECT cloud_id FROM shopping_items WHERE checked=1 AND cloud_id IS NOT NULL"
        ).fetchall()
        for row in rows:
            self.add_tombstone("shopping_items", row["cloud_id"])
        self.conn.execute("DELETE FROM shopping_items WHERE checked=1")
        self.conn.commit()

    def get_meal_plan(self, week_start: str) -> list:
        return self.conn.execute(
            "SELECT * FROM meal_plans WHERE week_start=? ORDER BY meal_type",
            (week_start,)
        ).fetchall()

    def set_meal_slot(self, week_start: str, day: str, meal_type: str,
                      custom_name: str = "", recipe_id=None):
        existing = self.conn.execute(
            "SELECT id FROM meal_plans WHERE week_start=? AND day_of_week=? AND meal_type=?",
            (week_start, day, meal_type)
        ).fetchone()
        if existing:
            self.conn.execute(
                "UPDATE meal_plans SET custom_name=?, recipe_id=?, updated_at=CURRENT_TIMESTAMP"
                " WHERE id=?",
                (custom_name, recipe_id, existing["id"])
            )
        else:
            self.conn.execute(
                "INSERT INTO meal_plans"
                " (week_start, day_of_week, meal_type, custom_name, recipe_id, updated_at)"
                " VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)",
                (week_start, day, meal_type, custom_name, recipe_id)
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
            " WHERE week_start=? AND day_of_week=?",
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
            " WHERE mp.week_start=? AND mp.day_of_week=?"
            " ORDER BY CASE mp.meal_type"
            "   WHEN 'breakfast' THEN 1 WHEN 'lunch' THEN 2"
            "   WHEN 'dinner' THEN 3 ELSE 4 END",
            (week_start, day_name),
        ).fetchall()
        return [dict(r) for r in rows]

    def clear_meal_slot(self, week_start: str, day: str, meal_type: str):
        row = self.conn.execute(
            "SELECT cloud_id FROM meal_plans"
            " WHERE week_start=? AND day_of_week=? AND meal_type=?",
            (week_start, day, meal_type)
        ).fetchone()
        if row and row["cloud_id"]:
            self.add_tombstone("meal_plans", row["cloud_id"])
        self.conn.execute(
            "DELETE FROM meal_plans WHERE week_start=? AND day_of_week=? AND meal_type=?",
            (week_start, day, meal_type)
        )
        self.conn.commit()

    def clear_week_meal_plan(self, week_start: str):
        rows = self.conn.execute(
            "SELECT cloud_id FROM meal_plans WHERE week_start=? AND cloud_id IS NOT NULL",
            (week_start,)
        ).fetchall()
        for row in rows:
            self.add_tombstone("meal_plans", row["cloud_id"])
        self.conn.execute("DELETE FROM meal_plans WHERE week_start=?", (week_start,))
        self.conn.commit()

    def clear_all_meal_plans(self):
        """Delete every meal plan row across all weeks."""
        rows = self.conn.execute(
            "SELECT cloud_id FROM meal_plans WHERE cloud_id IS NOT NULL"
        ).fetchall()
        for row in rows:
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
        orphans = self.conn.execute(
            "SELECT mp.id, mp.cloud_id FROM meal_plans mp"
            " WHERE mp.recipe_id IS NULL"
            "    OR mp.recipe_id NOT IN (SELECT id FROM recipes)"
        ).fetchall()
        for row in orphans:
            if row["cloud_id"]:
                self.add_tombstone("meal_plans", row["cloud_id"])
            self.conn.execute("DELETE FROM meal_plans WHERE id=?", (row["id"],))
        if orphans:
            self.conn.commit()
        return len(orphans)

    def clear_meal_day_slots(self, week_start: str, day: str):
        """Delete all meal slots (breakfast, lunch, dinner) for a specific day in a week."""
        rows = self.conn.execute(
            "SELECT cloud_id FROM meal_plans"
            " WHERE week_start=? AND day_of_week=? AND cloud_id IS NOT NULL",
            (week_start, day)
        ).fetchall()
        for row in rows:
            self.add_tombstone("meal_plans", row["cloud_id"])
        self.conn.execute(
            "DELETE FROM meal_plans WHERE week_start=? AND day_of_week=?",
            (week_start, day)
        )
        self.conn.commit()

    def clear_all_shopping_items(self):
        rows = self.conn.execute(
            "SELECT cloud_id FROM shopping_items WHERE cloud_id IS NOT NULL"
        ).fetchall()
        for row in rows:
            self.add_tombstone("shopping_items", row["cloud_id"])
        self.conn.execute("DELETE FROM shopping_items")
        self.conn.commit()

    def delete_all_recipes(self):
        rows = self.conn.execute(
            "SELECT cloud_id FROM recipes WHERE cloud_id IS NOT NULL"
        ).fetchall()
        for row in rows:
            self.add_tombstone("recipes", row["cloud_id"])
        self.conn.execute("DELETE FROM recipes")
        self.conn.commit()

    def delete_shopping_item_by_name(self, name: str) -> int:
        """Delete first matching item (case-insensitive). Returns deleted count."""
        row = self.conn.execute(
            "SELECT id, cloud_id FROM shopping_items WHERE lower(name) = lower(?) LIMIT 1",
            (name,)
        ).fetchone()
        if row:
            if row["cloud_id"]:
                self.add_tombstone("shopping_items", row["cloud_id"])
            self.conn.execute("DELETE FROM shopping_items WHERE id=?", (row["id"],))
            self.conn.commit()
            return 1
        return 0

    def delete_recipe_by_title(self, title: str) -> int:
        """Delete first recipe whose title matches (case-insensitive). Returns deleted count."""
        row = self.conn.execute(
            "SELECT id, cloud_id FROM recipes WHERE lower(title) = lower(?) LIMIT 1", (title,)
        ).fetchone()
        if row:
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
        cursor = self.conn.execute(
            "INSERT INTO nutrition_logs"
            " (log_date, food_name, kcal, protein_g, carbs_g, fat_g, fiber_g, sugar_g,"
            "  updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
            (date_str, food_name, kcal, protein_g, carbs_g, fat_g, fiber_g, sugar_g),
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
        cursor = self.conn.execute(
            "INSERT INTO dishy_chat_history"
            " (session_id, role, content, tool_names, updated_at)"
            " VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (session_id, role, content, tool_names),
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
        """)
        # Delete all user-specific settings (onboarding, sync timestamps,
        # macro goals, preferences, etc.) — keep only device-level keys.
        placeholders = ",".join("?" * len(self._DEVICE_SETTING_KEYS))
        self.conn.execute(
            f"DELETE FROM settings WHERE key NOT IN ({placeholders})",
            tuple(self._DEVICE_SETTING_KEYS),
        )
        self.conn.commit()

    # -- Pantry / fridge / freezer helpers --------------------------------

    def add_pantry_item(self, name: str, quantity=None, unit: str = "",
                        storage: str = "Pantry", expiry_date: str = None) -> int:
        cursor = self.conn.execute(
            "INSERT INTO pantry_items (name, quantity, unit, storage, expiry_date, updated_at)"
            " VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (name, quantity, unit or "", storage or "Pantry", expiry_date),
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
        self.conn.execute(
            "UPDATE pantry_items SET quantity=?, unit=?, expiry_date=?, updated_at=CURRENT_TIMESTAMP"
            " WHERE id=?",
            (quantity, unit or "", expiry_date, item_id),
        )
        self.conn.commit()

    def delete_pantry_item(self, item_id: int):
        row = self.conn.execute(
            "SELECT cloud_id FROM pantry_items WHERE id=?", (item_id,)
        ).fetchone()
        if row and row["cloud_id"]:
            self.add_tombstone("pantry_items", row["cloud_id"])
        self.conn.execute("DELETE FROM pantry_items WHERE id=?", (item_id,))
        self.conn.commit()

    def clear_pantry(self, storage: str = None):
        if storage:
            rows = self.conn.execute(
                "SELECT cloud_id FROM pantry_items WHERE storage=? AND cloud_id IS NOT NULL",
                (storage,)
            ).fetchall()
            for row in rows:
                self.add_tombstone("pantry_items", row["cloud_id"])
            self.conn.execute("DELETE FROM pantry_items WHERE storage=?", (storage,))
        else:
            rows = self.conn.execute(
                "SELECT cloud_id FROM pantry_items WHERE cloud_id IS NOT NULL"
            ).fetchall()
            for row in rows:
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
            qty_str, unit, name = m.group(1), m.group(2), m.group(3).strip()
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
                            "UPDATE pantry_items SET quantity=?, updated_at=CURRENT_TIMESTAMP"
                            " WHERE id=?",
                            (new_qty, row["id"]),
                        )
                    break
        self.conn.commit()

    # -- Cloud sync helpers ------------------------------------------------

    def add_tombstone(self, table_name: str, cloud_id: str) -> None:
        """Record a cloud deletion that needs to be propagated during the next sync."""
        try:
            self.conn.execute(
                "INSERT INTO sync_tombstones (table_name, cloud_id) VALUES (?, ?)",
                (table_name, cloud_id),
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
        """Return rows with cloud_id set and updated_at newer than since_iso."""
        return self.conn.execute(
            f"SELECT * FROM {table}"
            f" WHERE cloud_id IS NOT NULL AND updated_at > ?",
            (since_iso,)
        ).fetchall()

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
            f"SELECT id, updated_at FROM {table} WHERE cloud_id=?", (cloud_id,)
        ).fetchone()

        # Build column dict, remapping keys as needed
        data = {}
        for k, v in cloud_row.items():
            if k in ("id", "user_id"):
                continue
            local_k = local_col_map.get(k, k)
            data[local_k] = v
        data["cloud_id"] = cloud_id

        if existing:
            local_updated  = existing["updated_at"] or ""
            cloud_updated  = str(cloud_row.get("updated_at", ""))
            if cloud_updated <= local_updated:
                return  # local is newer or equal — keep it
            set_clause = ", ".join(f"{k}=?" for k in data)
            self.conn.execute(
                f"UPDATE {table} SET {set_clause} WHERE id=?",
                list(data.values()) + [existing["id"]],
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
