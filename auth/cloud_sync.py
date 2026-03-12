"""
CloudSyncService — bidirectional sync between local SQLite and Supabase.

All methods are blocking and designed to run inside run_async() workers.
Conflict resolution: last-write-wins on updated_at.

Settings keys that are NEVER synced to the cloud:
  anthropic_api_key, daily_tip, daily_tip_date
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from models.database import Database
from auth.supabase_client import get_client


# Settings keys that must never leave the device
_EXCLUDED_SETTINGS = {
    "anthropic_api_key",
    "daily_tip", "daily_tip_date",
}

# Local-only sync state keys (stored in the settings table)
_LAST_PUSH_KEY = "sync_last_push_at"
_LAST_PULL_KEY = "sync_last_pull_at"


@dataclass
class SyncResult:
    pushed: int = 0
    pulled: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CloudSyncService:
    """Handles push/pull between local SQLite and Supabase for one user."""

    # Tables and their simple column maps (cloud → local).
    # Only needs entries for columns that differ between schemas.
    _TABLE_COL_MAPS: dict[str, dict] = {
        "recipes":           {},
        "meal_plans":        {"recipe_cloud_id": None},  # None = skip this column on pull
        "shopping_items":    {},
        "nutrition_logs":    {},
        "dishy_chat_history": {},
    }

    def __init__(self, user_id: str):
        self.user_id = user_id

    # ── Public API ────────────────────────────────────────────────────────────

    def sync(self) -> SyncResult:
        """Full push + pull cycle. Called by the background timer."""
        result = SyncResult()
        push_r = self.push_all()
        pull_r = self.pull_all()
        result.pushed = push_r.pushed
        result.pulled = pull_r.pulled
        result.errors = push_r.errors + pull_r.errors
        return result

    def push_all(self) -> SyncResult:
        """Upload local changes to Supabase."""
        result = SyncResult()
        client = get_client()
        if client is None:
            result.errors.append("Supabase client not configured")
            return result

        db = self._open_db()
        last_push = db.get_setting(_LAST_PUSH_KEY, "1970-01-01T00:00:00")

        try:
            # Push each table
            for table in self._TABLE_COL_MAPS:
                self._push_table(db, client, table, last_push, result)

            # Push tombstones
            self._push_tombstones(db, client)

            # Push user settings (non-sensitive only)
            self._push_settings(db, client)

            db.set_setting(_LAST_PUSH_KEY, _now_iso())
        except Exception as e:
            result.errors.append(f"push_all: {e}")
        finally:
            db.close()

        return result

    def pull_all(self) -> SyncResult:
        """Download cloud changes into local SQLite."""
        result = SyncResult()
        client = get_client()
        if client is None:
            result.errors.append("Supabase client not configured")
            return result

        db = self._open_db()
        last_pull = db.get_setting(_LAST_PULL_KEY, "1970-01-01T00:00:00")

        try:
            # Apply tombstones first (deletions from other devices)
            self._apply_tombstones(db, client)

            # Pull each table
            for table, col_map in self._TABLE_COL_MAPS.items():
                self._pull_table(db, client, table, col_map, last_pull, result)

            # Pull user settings
            self._pull_settings(db, client)

            db.set_setting(_LAST_PULL_KEY, _now_iso())
        except Exception as e:
            result.errors.append(f"pull_all: {e}")
        finally:
            db.close()

        return result

    # ── Push helpers ──────────────────────────────────────────────────────────

    def _push_table(self, db: Database, client, table: str,
                    last_push: str, result: SyncResult) -> None:
        """Push new rows + modified rows for one table."""
        # 1. New rows (never pushed)
        for row in db.get_unsynced_rows(table):
            data = self._row_to_cloud(dict(row), table)
            if data is None:
                continue
            # Strip client-side updated_at so the server timestamps the insert
            # using its own clock — eliminates clock-skew conflicts.
            data.pop("updated_at", None)
            try:
                res = client.table(table).insert(data).execute()
                if res.data:
                    cloud_id = res.data[0]["id"]
                    db.set_cloud_id(table, row["id"], cloud_id)
                    # Write the server-assigned timestamp back to local so both
                    # sides use the same reference for future conflict resolution.
                    server_ts = res.data[0].get("updated_at")
                    if server_ts:
                        db.conn.execute(
                            f"UPDATE {table} SET updated_at=? WHERE id=?",
                            (server_ts, row["id"]),
                        )
                        db.conn.commit()
                    result.pushed += 1
            except Exception as e:
                result.errors.append(f"{table} insert: {e}")

        # 2. Modified rows (have cloud_id, updated since last push)
        for row in db.get_modified_rows_since(table, last_push):
            data = self._row_to_cloud(dict(row), table)
            if data is None:
                continue
            try:
                res = client.table(table).update(data).eq("id", row["cloud_id"]).execute()
                # Sync the server-returned timestamp back so both devices share
                # the same reference point on the next conflict comparison.
                if res.data:
                    server_ts = res.data[0].get("updated_at")
                    if server_ts:
                        db.conn.execute(
                            f"UPDATE {table} SET updated_at=? WHERE id=?",
                            (server_ts, row["id"]),
                        )
                        db.conn.commit()
                result.pushed += 1
            except Exception as e:
                result.errors.append(f"{table} update: {e}")

    def _row_to_cloud(self, row: dict, table: str) -> dict | None:
        """Convert a local SQLite row to a Supabase-ready dict."""
        data: dict = {"user_id": self.user_id, "local_id": row.get("id")}
        skip = {"id", "cloud_id"}

        for k, v in row.items():
            if k in skip:
                continue
            # Convert any non-string types that SQLite Row returns
            if isinstance(v, bytes):
                continue
            data[k] = v

        # Remove columns that don't exist in the cloud schema for this table
        if table == "meal_plans":
            data.pop("recipe_id", None)   # cloud uses recipe_cloud_id instead
        if table == "dishy_chat_history":
            pass  # all columns the same

        # Don't push local filesystem paths — they're meaningless on other devices.
        # Supabase Storage URLs and HTTP URLs are fine to push.
        if table == "recipes":
            image_url = data.get("image_url") or ""
            if image_url and not image_url.startswith(("http://", "https://")):
                data["image_url"] = ""

        return data

    def _push_tombstones(self, db: Database, client) -> None:
        """Upload pending local tombstones and clear them."""
        for t in db.get_pending_tombstones():
            try:
                client.table("sync_tombstones").insert({
                    "user_id":    self.user_id,
                    "table_name": t["table_name"],
                    "cloud_id":   t["cloud_id"],
                }).execute()
                db.clear_tombstone(t["id"])
            except Exception:
                pass

    def _push_settings(self, db: Database, client) -> None:
        """Push non-sensitive settings as a single prefs_json row."""
        all_settings = db.conn.execute("SELECT key, value FROM settings").fetchall()
        prefs: dict = {}
        for row in all_settings:
            if row["key"] not in _EXCLUDED_SETTINGS:
                prefs[row["key"]] = row["value"]

        if not prefs:
            return

        try:
            client.table("user_settings").upsert({
                "user_id":    self.user_id,
                "prefs_json": json.dumps(prefs),
                "updated_at": _now_iso(),
            }).execute()
        except Exception:
            pass

    # ── Pull helpers ──────────────────────────────────────────────────────────

    def _pull_table(self, db: Database, client, table: str, col_map: dict,
                    last_pull: str, result: SyncResult) -> None:
        """Pull rows updated since last_pull and upsert locally."""
        try:
            res = (
                client.table(table)
                .select("*")
                .eq("user_id", self.user_id)
                .gt("updated_at", last_pull)
                .execute()
            )
            for cloud_row in (res.data or []):
                # Build effective col_map: skip None-valued entries
                effective_map = {k: v for k, v in col_map.items() if v is not None}
                # Remove cloud-only columns
                skip_cols = {k for k, v in col_map.items() if v is None}
                filtered = {k: v for k, v in cloud_row.items() if k not in skip_cols}
                db.upsert_row_from_cloud(table, filtered, effective_map)
                result.pulled += 1
        except Exception as e:
            result.errors.append(f"{table} pull: {e}")

    def _apply_tombstones(self, db: Database, client) -> None:
        """Fetch cloud tombstones and delete matching local rows."""
        try:
            res = (
                client.table("sync_tombstones")
                .select("*")
                .eq("user_id", self.user_id)
                .execute()
            )
            for t in (res.data or []):
                table    = t.get("table_name", "")
                cloud_id = t.get("cloud_id", "")
                if not table or not cloud_id:
                    continue
                try:
                    row = db.conn.execute(
                        f"SELECT id FROM {table} WHERE cloud_id=?", (cloud_id,)
                    ).fetchone()
                    if row:
                        db.conn.execute(f"DELETE FROM {table} WHERE id=?", (row["id"],))
                        db.conn.commit()
                except Exception:
                    pass
        except Exception:
            pass

    def _pull_settings(self, db: Database, client) -> None:
        """Pull user_settings and merge non-sensitive keys."""
        try:
            res = (
                client.table("user_settings")
                .select("prefs_json, updated_at")
                .eq("user_id", self.user_id)
                .single()
                .execute()
            )
            if not res.data:
                return
            prefs_raw = res.data.get("prefs_json", "")
            if not prefs_raw:
                return
            prefs = json.loads(prefs_raw)
            for k, v in prefs.items():
                if k not in _EXCLUDED_SETTINGS and v is not None:
                    db.set_setting(k, str(v))
        except Exception:
            pass

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _open_db() -> Database:
        db = Database()
        db.connect()
        return db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
