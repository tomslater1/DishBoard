"""
CloudSyncService — bidirectional sync between local SQLite and Supabase.

All methods are blocking and designed to run inside run_async() workers.
Conflict resolution: last-write-wins on updated_at.

Settings keys that are NEVER synced to the cloud:
  anthropic_api_key, daily_tip, daily_tip_date

All errors are printed to stdout so they are visible in the terminal.
Run `python3 DishBoard.py` to see sync activity in real time.
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

# Epoch sentinel — means "no previous sync, pull everything"
_EPOCH = "1970-01-01T00:00:00"


@dataclass
class SyncResult:
    pushed: int = 0
    pulled: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _log(msg: str) -> None:
    """Print a sync log line. Always visible in the terminal."""
    print(f"[Sync] {msg}")


class CloudSyncService:
    """Handles push/pull between local SQLite and Supabase for one user."""

    # Tables and their simple column maps (cloud → local).
    # Only needs entries for columns that differ between schemas.
    _TABLE_COL_MAPS: dict[str, dict] = {
        "recipes":            {},
        "meal_plans":         {"recipe_cloud_id": None},  # None = skip on pull
        "shopping_items":     {},
        "nutrition_logs":     {},
        "dishy_chat_history": {},
        "pantry_items":       {},
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
        if result.errors:
            for e in result.errors:
                _log(f"ERROR: {e}")
        else:
            _log(f"OK — pushed={result.pushed} pulled={result.pulled}")
        return result

    def push_all(self) -> SyncResult:
        """Upload local changes to Supabase."""
        result = SyncResult()
        client = get_client()
        if client is None:
            result.errors.append("Supabase client not available")
            return result

        db = self._open_db()
        last_push = db.get_setting(_LAST_PUSH_KEY, _EPOCH)

        try:
            for table in self._TABLE_COL_MAPS:
                self._push_table(db, client, table, last_push, result)
            self._push_tombstones(db, client)
            self._push_settings(db, client, result)
            db.set_setting(_LAST_PUSH_KEY, _now_iso())
        except Exception as e:
            msg = f"push_all fatal: {e}"
            result.errors.append(msg)
            _log(f"ERROR: {msg}")
        finally:
            db.close()

        return result

    def pull_all(self) -> SyncResult:
        """Download cloud changes into local SQLite."""
        result = SyncResult()
        client = get_client()
        if client is None:
            result.errors.append("Supabase client not available")
            return result

        db = self._open_db()
        last_pull = db.get_setting(_LAST_PULL_KEY, _EPOCH)
        is_full_pull = (last_pull == _EPOCH)
        if is_full_pull:
            _log("Full pull (no previous sync timestamp) — fetching all rows")

        try:
            self._apply_tombstones(db, client)
            for table, col_map in self._TABLE_COL_MAPS.items():
                self._pull_table(db, client, table, col_map, last_pull, result)
            self._pull_settings(db, client, result)
            db.set_setting(_LAST_PULL_KEY, _now_iso())
        except Exception as e:
            msg = f"pull_all fatal: {e}"
            result.errors.append(msg)
            _log(f"ERROR: {msg}")
        finally:
            db.close()

        return result

    # ── Push helpers ──────────────────────────────────────────────────────────

    def _push_table(self, db: Database, client, table: str,
                    last_push: str, result: SyncResult) -> None:
        """Push new rows + modified rows for one table."""
        # 1. New rows (never pushed — cloud_id IS NULL)
        new_rows = db.get_unsynced_rows(table)
        if new_rows:
            _log(f"Pushing {len(new_rows)} new rows to {table}")
        for row in new_rows:
            data = self._row_to_cloud(dict(row), table)
            if data is None:
                continue
            # Strip updated_at so the server sets it — avoids clock-skew conflicts
            data.pop("updated_at", None)
            try:
                res = client.table(table).insert(data).execute()
                if res.data:
                    cloud_id = res.data[0]["id"]
                    db.set_cloud_id(table, row["id"], cloud_id)
                    server_ts = res.data[0].get("updated_at")
                    if server_ts:
                        db.conn.execute(
                            f"UPDATE {table} SET updated_at=? WHERE id=?",
                            (server_ts, row["id"]),
                        )
                        db.conn.commit()
                    result.pushed += 1
                else:
                    msg = f"{table} insert returned no data (row id={row['id']})"
                    result.errors.append(msg)
                    _log(f"WARN: {msg}")
            except Exception as e:
                msg = f"{table} insert failed: {e}"
                result.errors.append(msg)
                _log(f"ERROR: {msg}")

        # 2. Modified rows (have cloud_id, changed since last push)
        for row in db.get_modified_rows_since(table, last_push):
            data = self._row_to_cloud(dict(row), table)
            if data is None:
                continue
            try:
                res = client.table(table).update(data).eq("id", row["cloud_id"]).execute()
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
                msg = f"{table} update failed: {e}"
                result.errors.append(msg)
                _log(f"ERROR: {msg}")

    def _row_to_cloud(self, row: dict, table: str) -> dict | None:
        """Convert a local SQLite row to a Supabase-ready dict."""
        data: dict = {"user_id": self.user_id, "local_id": row.get("id")}
        skip = {"id", "cloud_id"}

        for k, v in row.items():
            if k in skip:
                continue
            if isinstance(v, bytes):
                continue
            data[k] = v

        if table == "meal_plans":
            data.pop("recipe_id", None)

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
            except Exception as e:
                _log(f"ERROR: tombstone push failed: {e}")

    def _push_settings(self, db: Database, client, result: SyncResult) -> None:
        """Push settings as a single prefs_json row.

        Merges with the existing cloud row before writing so that a partial
        local settings state (e.g. right after an account-switch wipe) never
        overwrites keys that are already in Supabase (e.g. onboarding_complete).
        Local values always win for any key present in both.
        """
        # Read what Supabase already has for this user
        cloud_prefs: dict = {}
        try:
            res = (
                client.table("user_settings")
                .select("prefs_json")
                .eq("user_id", self.user_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if rows and rows[0].get("prefs_json"):
                cloud_prefs = json.loads(rows[0]["prefs_json"])
        except Exception:
            pass  # Can't read existing settings — will write local only

        # Build local prefs
        local_prefs: dict = {}
        for row in db.conn.execute("SELECT key, value FROM settings").fetchall():
            if row["key"] not in _EXCLUDED_SETTINGS:
                local_prefs[row["key"]] = row["value"]

        # Merge: cloud is the base, local overrides (local always wins for keys it has)
        merged = {**cloud_prefs, **local_prefs}
        if not merged:
            return

        try:
            client.table("user_settings").upsert({
                "user_id":    self.user_id,
                "prefs_json": json.dumps(merged),
                "updated_at": _now_iso(),
            }).execute()
            _log(f"Settings pushed ({len(merged)} total, {len(local_prefs)} local + {len(cloud_prefs)} cloud)")
        except Exception as e:
            msg = f"settings push failed: {e}"
            result.errors.append(msg)
            _log(f"ERROR: {msg}")

    # ── Pull helpers ──────────────────────────────────────────────────────────

    def _pull_table(self, db: Database, client, table: str, col_map: dict,
                    last_pull: str, result: SyncResult) -> None:
        """Pull rows for this user and upsert locally."""
        try:
            query = (
                client.table(table)
                .select("*")
                .eq("user_id", self.user_id)
            )
            # On a full pull (no previous sync timestamp) skip the updated_at
            # filter entirely. In PostgreSQL, NULL > anything evaluates to NULL
            # (not true), so rows with NULL updated_at would be silently excluded
            # if we applied the filter. A fresh pull should always get everything.
            if last_pull and last_pull != _EPOCH:
                query = query.gt("updated_at", last_pull)

            res = query.execute()
            rows = res.data or []
            if rows:
                _log(f"Pulled {len(rows)} rows from {table}")
            # Columns that live in Supabase only — local SQLite has no such columns
            cloud_only = {"local_id", "user_id"}
            for cloud_row in rows:
                effective_map = {k: v for k, v in col_map.items() if v is not None}
                skip_cols = {k for k, v in col_map.items() if v is None} | cloud_only
                filtered = {k: v for k, v in cloud_row.items() if k not in skip_cols}
                db.upsert_row_from_cloud(table, filtered, effective_map)
                result.pulled += 1
        except Exception as e:
            msg = f"{table} pull failed: {e}"
            result.errors.append(msg)
            _log(f"ERROR: {msg}")

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
                except Exception as e:
                    _log(f"WARN: tombstone apply failed for {table}/{cloud_id}: {e}")
        except Exception as e:
            _log(f"WARN: tombstone fetch failed: {e}")

    def _pull_settings(self, db: Database, client, result: SyncResult) -> None:
        """Pull user_settings and merge non-sensitive keys."""
        try:
            res = (
                client.table("user_settings")
                .select("prefs_json")
                .eq("user_id", self.user_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if not rows:
                _log("No user_settings row found for this user (new account or not yet pushed)")
                return
            prefs_raw = rows[0].get("prefs_json", "")
            if not prefs_raw:
                return
            prefs = json.loads(prefs_raw)
            count = 0
            for k, v in prefs.items():
                if k not in _EXCLUDED_SETTINGS and v is not None:
                    db.set_setting(k, str(v))
                    count += 1
            _log(f"Settings pulled ({count} keys, including onboarding_complete={prefs.get('onboarding_complete', 'not set')})")
        except Exception as e:
            msg = f"settings pull failed: {e}"
            result.errors.append(msg)
            _log(f"ERROR: {msg}")

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _open_db() -> Database:
        db = Database()
        db.connect()
        return db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
