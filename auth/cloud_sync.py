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
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from models.database import Database
from auth.supabase_client import get_client
from utils.data_validators import sanitize_cloud_row


# Settings keys that must never leave the device
_EXCLUDED_SETTINGS = {
    "anthropic_api_key",
    "daily_tip", "daily_tip_date",
}

# Local-only sync state keys (stored in the settings table)
_LAST_PUSH_KEY = "sync_last_push_at"
_LAST_PULL_KEY = "sync_last_pull_at"

# Epoch sentinel — means "no previous sync, pull everything"
_EPOCH = "1970-01-01T00:00:00+00:00"
_LOGGER = logging.getLogger("dishboard.sync")


@dataclass
class SyncResult:
    pushed: int = 0
    pulled: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _log(msg: str) -> None:
    """Write a sync log line (console + file handlers if configured)."""
    _LOGGER.info(msg)


def _normalise_ts(value) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if " " in raw and "T" not in raw:
        raw = raw.replace(" ", "T", 1)
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
    return dt.isoformat(timespec="seconds")


def _is_uuid(value: str) -> bool:
    """Return True when value parses as a UUID string."""
    try:
        uuid.UUID(str(value).strip())
        return True
    except Exception:
        return False


class CloudSyncService:
    """Handles push/pull between local SQLite and Supabase for one user."""

    # Tables and their simple column maps (cloud → local).
    # Only needs entries for columns that differ between schemas.
    _TABLE_COL_MAPS: dict[str, dict] = {
        "recipes":            {},
        "meal_plans":         {},
        "shopping_items":     {},
        "nutrition_logs":     {},
        "dishy_chat_history": {},
        "pantry_items":       {},
    }
    _HOUSEHOLD_SHARED_TABLES = {
        "recipes",
        "meal_plans",
        "shopping_items",
        "nutrition_logs",
        "pantry_items",
    }

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.household_id = user_id
        self._household_scope_enabled = False

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
            try:
                from utils.telemetry import track_event

                track_event(
                    "sync.failed",
                    {"errors": result.errors[:5], "pushed": result.pushed, "pulled": result.pulled},
                    user_id=self.user_id,
                )
            except Exception:
                pass
        else:
            _log(f"OK — pushed={result.pushed} pulled={result.pulled}")
            try:
                from utils.telemetry import track_event

                track_event(
                    "sync.completed",
                    {"pushed": result.pushed, "pulled": result.pulled},
                    user_id=self.user_id,
                )
            except Exception:
                pass
        return result

    def push_all(self) -> SyncResult:
        """Upload local changes to Supabase."""
        result = SyncResult()
        client = get_client()
        if client is None:
            result.errors.append("Supabase client not available")
            return result

        db = self._open_db()
        self._load_scope(db)
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
        self._load_scope(db)
        last_pull = db.get_setting(_LAST_PULL_KEY, _EPOCH)
        is_full_pull = (last_pull == _EPOCH)
        if is_full_pull:
            _log("Full pull (no previous sync timestamp) — fetching all rows")

        try:
            self._apply_tombstones(db, client)
            for table, col_map in self._TABLE_COL_MAPS.items():
                self._pull_table(db, client, table, col_map, last_pull, result)
            linked = db.reconcile_meal_plan_recipe_links()
            if linked:
                _log(f"Reconciled {linked} meal-plan recipe link(s)")
            if is_full_pull:
                removed = db.cleanup_unlinked_cloud_meal_plans()
                if removed:
                    _log(f"Removed {removed} stale cloud-linked meal-plan row(s)")
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
            data = self._row_to_cloud(db, dict(row), table)
            if data is None:
                continue
            # Strip updated_at so the server sets it — avoids clock-skew conflicts
            data.pop("updated_at", None)
            try:
                res = self._insert_cloud(client, table, data)
                if res.data:
                    cloud_id = res.data[0]["id"]
                    db.set_cloud_id(table, row["id"], cloud_id)
                    server_ts = res.data[0].get("updated_at")
                    if server_ts:
                        server_ts = _normalise_ts(server_ts) or server_ts
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
            data = self._row_to_cloud(db, dict(row), table)
            if data is None:
                continue
            try:
                res = self._update_cloud(client, table, row["cloud_id"], data)
                if res.data:
                    server_ts = res.data[0].get("updated_at")
                    if server_ts:
                        server_ts = _normalise_ts(server_ts) or server_ts
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

    # Tables that have a local_id column in Supabase (pantry_items does not)
    _HAS_LOCAL_ID = {"recipes", "meal_plans", "shopping_items", "nutrition_logs", "dishy_chat_history"}

    def _row_to_cloud(self, db: Database, row: dict, table: str) -> dict | None:
        """Convert a local SQLite row to a Supabase-ready dict."""
        data: dict = {"user_id": self.user_id}
        if self._household_scope_enabled and table in self._HOUSEHOLD_SHARED_TABLES:
            data["household_id"] = self.household_id or self.user_id
        if table in self._HAS_LOCAL_ID:
            data["local_id"] = row.get("id")
        skip = {"id", "cloud_id"}

        for k, v in row.items():
            if k in skip:
                continue
            if k == "household_id" and table in self._HOUSEHOLD_SHARED_TABLES and not self._household_scope_enabled:
                continue
            if k == "household_id" and table in self._HOUSEHOLD_SHARED_TABLES and not v:
                # Keep resolved household scope instead of null local legacy values.
                continue
            if isinstance(v, bytes):
                continue
            data[k] = v

        if table == "meal_plans":
            recipe_cloud_id = row.get("recipe_cloud_id")
            local_recipe_id = row.get("recipe_id")
            if local_recipe_id:
                rr = db.conn.execute(
                    "SELECT cloud_id FROM recipes WHERE id=?",
                    (local_recipe_id,),
                ).fetchone()
                if rr and rr["cloud_id"]:
                    recipe_cloud_id = rr["cloud_id"]
            data["recipe_cloud_id"] = recipe_cloud_id
            data.pop("recipe_id", None)

        if table == "recipes":
            title = str(data.get("title") or "").strip()
            if not title:
                return None
            data["title"] = title
            image_url = data.get("image_url") or ""
            if image_url and not image_url.startswith(("http://", "https://")):
                data["image_url"] = ""

        if table == "shopping_items":
            name = " ".join(str(data.get("name") or "").split())
            if not name:
                return None
            data["name"] = name

        return data

    def _push_tombstones(self, db: Database, client) -> None:
        """Upload pending local tombstones and clear them."""
        for t in db.get_pending_tombstones():
            cloud_id = str(t.get("cloud_id", "")).strip()
            if not _is_uuid(cloud_id):
                _log(
                    "WARN: Dropping legacy tombstone with non-UUID cloud_id: "
                    f"table={t.get('table_name', '')} cloud_id={cloud_id!r}"
                )
                db.clear_tombstone(t["id"])
                continue
            try:
                payload = {
                    "user_id":    self.user_id,
                    "table_name": t["table_name"],
                    "cloud_id":   cloud_id,
                }
                if self._household_scope_enabled:
                    payload["household_id"] = self.household_id or self.user_id
                try:
                    client.table("sync_tombstones").insert(payload).execute()
                except Exception as exc:
                    if "household_id" in str(exc):
                        payload.pop("household_id", None)
                        client.table("sync_tombstones").insert(payload).execute()
                    else:
                        raise
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
            def _run_query(scope_col: str, scope_value: str):
                query = (
                    client.table(table)
                    .select("*")
                    .eq(scope_col, scope_value)
                )
                # On a full pull (no previous sync timestamp) skip the updated_at
                # filter entirely. In PostgreSQL, NULL > anything evaluates to NULL
                # (not true), so rows with NULL updated_at would be silently excluded
                # if we applied the filter. A fresh pull should always get everything.
                if last_pull and last_pull != _EPOCH:
                    query = query.gt("updated_at", last_pull)
                return query.execute()

            if (
                self._household_scope_enabled
                and table in self._HOUSEHOLD_SHARED_TABLES
                and self.household_id
            ):
                try:
                    res = _run_query("household_id", self.household_id)
                except Exception as scoped_err:
                    _log(f"WARN: {table} household pull fallback to user scope: {scoped_err}")
                    res = _run_query("user_id", self.user_id)
            else:
                res = _run_query("user_id", self.user_id)
            rows = res.data or []
            if rows:
                _log(f"Pulled {len(rows)} rows from {table}")
            # Columns that live in Supabase only — local SQLite has no such columns
            cloud_only = {"local_id", "user_id"}
            for cloud_row in rows:
                sanitized_row, reason = sanitize_cloud_row(
                    table,
                    cloud_row,
                    user_id=self.user_id,
                    household_id=self.household_id,
                    household_scope_enabled=self._household_scope_enabled,
                    household_shared_tables=self._HOUSEHOLD_SHARED_TABLES,
                )
                if sanitized_row is None:
                    row_id = str(cloud_row.get("id", "?"))
                    _log(
                        f"WARN: Skipping invalid {table} row from cloud"
                        f" (id={row_id}, reason={reason})"
                    )
                    continue
                effective_map = {k: v for k, v in col_map.items() if v is not None}
                skip_cols = {k for k, v in col_map.items() if v is None} | cloud_only
                filtered = {k: v for k, v in sanitized_row.items() if k not in skip_cols}
                if table == "shopping_items" and "name" in filtered:
                    filtered["name"] = " ".join(str(filtered.get("name") or "").split())
                if table == "recipes" and "title" in filtered:
                    filtered["title"] = str(filtered.get("title") or "").strip()
                if table == "meal_plans":
                    rcid = filtered.get("recipe_cloud_id")
                    if rcid:
                        rr = db.conn.execute(
                            "SELECT id FROM recipes WHERE cloud_id=?",
                            (rcid,),
                        ).fetchone()
                        filtered["recipe_id"] = rr["id"] if rr else None
                    else:
                        filtered["recipe_id"] = None
                try:
                    db.upsert_row_from_cloud(table, filtered, effective_map)
                    result.pulled += 1
                except Exception as row_err:
                    row_id = str(cloud_row.get("id", "?"))
                    msg = f"{table} row pull failed (id={row_id}): {row_err}"
                    result.errors.append(msg)
                    _log(f"ERROR: {msg}")
        except Exception as e:
            msg = f"{table} pull failed: {e}"
            result.errors.append(msg)
            _log(f"ERROR: {msg}")

    def _is_valid_cloud_row(self, table: str, row: dict) -> bool:
        """Best-effort validation to block malformed/ghost cloud rows."""
        sanitized, _reason = sanitize_cloud_row(
            table,
            row,
            user_id=self.user_id,
            household_id=self.household_id,
            household_scope_enabled=self._household_scope_enabled,
            household_shared_tables=self._HOUSEHOLD_SHARED_TABLES,
        )
        return sanitized is not None

    def _apply_tombstones(self, db: Database, client) -> None:
        """Fetch cloud tombstones and delete matching local rows."""
        try:
            tombstones: list[dict] = []
            seen_ids: set[str] = set()
            # Always fetch own tombstones.
            res_user = (
                client.table("sync_tombstones")
                .select("*")
                .eq("user_id", self.user_id)
                .execute()
            )
            for row in (res_user.data or []):
                rid = str(row.get("id", ""))
                if rid and rid in seen_ids:
                    continue
                if rid:
                    seen_ids.add(rid)
                tombstones.append(row)

            # Shared household scope (if available on cloud schema).
            if (
                self._household_scope_enabled
                and self.household_id
                and self.household_id != self.user_id
            ):
                try:
                    res_hh = (
                        client.table("sync_tombstones")
                        .select("*")
                        .eq("household_id", self.household_id)
                        .execute()
                    )
                    for row in (res_hh.data or []):
                        rid = str(row.get("id", ""))
                        if rid and rid in seen_ids:
                            continue
                        if rid:
                            seen_ids.add(rid)
                        tombstones.append(row)
                except Exception as hh_err:
                    _log(f"WARN: household tombstone pull fallback to user scope: {hh_err}")

            for t in tombstones:
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

    def _load_scope(self, db: Database) -> None:
        """Resolve current household scope from local settings."""
        hid = str(db.get_setting("household_id", "") or "").strip()
        self._household_scope_enabled = bool(hid)
        self.household_id = hid or self.user_id

    @staticmethod
    def _insert_cloud(client, table: str, data: dict):
        try:
            return client.table(table).insert(data).execute()
        except Exception as exc:
            # Backward compatibility: cloud schema may not have household_id yet.
            if "household_id" in str(exc):
                retry = dict(data)
                retry.pop("household_id", None)
                return client.table(table).insert(retry).execute()
            raise

    @staticmethod
    def _update_cloud(client, table: str, cloud_id: str, data: dict):
        try:
            return client.table(table).update(data).eq("id", cloud_id).execute()
        except Exception as exc:
            if "household_id" in str(exc):
                retry = dict(data)
                retry.pop("household_id", None)
                return client.table(table).update(retry).eq("id", cloud_id).execute()
            raise

    @staticmethod
    def _open_db() -> Database:
        db = Database()
        db.connect()
        return db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
