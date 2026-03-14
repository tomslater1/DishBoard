"""Feature flags and lightweight remote config for DishBoard."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

try:
    from models.database import Database
except ModuleNotFoundError:
    # Allow direct execution of this module for debugging from any cwd.
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from models.database import Database


_DEFAULT_FLAGS: dict[str, bool] = {
    "in_app_notifications": True,
    "dishy_memory_context": True,
    "enhanced_recipe_search": True,
    "workflows_enabled": True,
    "telemetry_enabled": True,
    "posthog_enabled": True,
    "sentry_enabled": True,
    "ai_daily_hard_limit": True,
}


def _bool_from_value(raw: str | None, fallback: bool) -> bool:
    if raw is None:
        return fallback
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return fallback


def _rollout_hit(user_id: str, flag_key: str, rollout_pct: int) -> bool:
    if rollout_pct >= 100:
        return True
    if rollout_pct <= 0:
        return False
    digest = hashlib.sha256(f"{user_id}:{flag_key}".encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return bucket < rollout_pct


class FeatureFlagService:
    """Evaluates feature flags from defaults + local overrides + remote cache."""

    def __init__(self, db: Database, user_id: str = ""):
        self._db = db
        self._user_id = user_id or ""

    @property
    def user_id(self) -> str:
        return self._user_id

    def set_user_id(self, user_id: str) -> None:
        self._user_id = user_id or ""

    def _key_user(self, flag: str) -> str:
        return f"ff.user.{self._user_id}.{flag}"

    @staticmethod
    def _key_global(flag: str) -> str:
        return f"ff.global.{flag}"

    @staticmethod
    def _key_remote_user(flag: str, user_id: str) -> str:
        return f"ff.remote.user.{user_id}.{flag}"

    @staticmethod
    def _key_remote_global(flag: str) -> str:
        return f"ff.remote.global.{flag}"

    def ensure_defaults(self) -> None:
        for key, enabled in _DEFAULT_FLAGS.items():
            gk = self._key_global(key)
            if self._db.get_setting(gk, "") == "":
                self._db.set_setting(gk, "1" if enabled else "0")

    def is_enabled(self, flag: str, *, default: bool | None = None) -> bool:
        fallback = _DEFAULT_FLAGS.get(flag, False) if default is None else bool(default)
        user_id = self._user_id

        # Highest priority: explicit per-user override
        if user_id:
            raw = self._db.get_setting(self._key_user(flag), "")
            if raw != "":
                return _bool_from_value(raw, fallback)

        # Remote per-user cache (supports gradual rollout)
        if user_id:
            remote_user_raw = self._db.get_setting(self._key_remote_user(flag, user_id), "")
            if remote_user_raw:
                try:
                    remote = json.loads(remote_user_raw)
                    enabled = bool(remote.get("enabled", fallback))
                    rollout = int(remote.get("rollout_pct", 100) or 100)
                    if rollout < 100:
                        return enabled and _rollout_hit(user_id, flag, rollout)
                    return enabled
                except Exception:
                    pass

        # Remote global cache
        remote_global_raw = self._db.get_setting(self._key_remote_global(flag), "")
        if remote_global_raw:
            try:
                remote = json.loads(remote_global_raw)
                enabled = bool(remote.get("enabled", fallback))
                rollout = int(remote.get("rollout_pct", 100) or 100)
                if rollout < 100 and user_id:
                    return enabled and _rollout_hit(user_id, flag, rollout)
                return enabled
            except Exception:
                pass

        # Device/global local override
        return _bool_from_value(self._db.get_setting(self._key_global(flag), ""), fallback)

    def set_global(self, flag: str, enabled: bool) -> None:
        self._db.set_setting(self._key_global(flag), "1" if enabled else "0")

    def set_user(self, flag: str, enabled: bool) -> None:
        if not self._user_id:
            return
        self._db.set_setting(self._key_user(flag), "1" if enabled else "0")

    def get_config(self, key: str, default: Any = None) -> Any:
        user_id = self._user_id
        if user_id:
            raw = self._db.get_setting(f"cfg.user.{user_id}.{key}", "")
            if raw:
                try:
                    return json.loads(raw)
                except Exception:
                    return raw

        raw = self._db.get_setting(f"cfg.global.{key}", "")
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                return raw
        return default

    def set_global_config(self, key: str, value: Any) -> None:
        self._db.set_setting(f"cfg.global.{key}", json.dumps(value))

    def set_user_config(self, key: str, value: Any) -> None:
        if not self._user_id:
            return
        self._db.set_setting(f"cfg.user.{self._user_id}.{key}", json.dumps(value))

    def all_effective_flags(self) -> list[dict]:
        rows: list[dict] = []
        for flag, default in sorted(_DEFAULT_FLAGS.items()):
            rows.append({
                "flag": flag,
                "enabled": self.is_enabled(flag, default=default),
                "default": bool(default),
            })
        return rows

    def refresh_remote_from_supabase(self) -> tuple[int, str]:
        """Pull remote flags into local settings cache.

        Expected remote schema (optional table):
            feature_flags(key text, enabled bool, scope text, user_id uuid null,
                          rollout_pct int null, config_json jsonb null)

        This method is fully defensive; if the table does not exist, it silently
        returns (0, reason) and local flags continue to work.
        """
        try:
            from auth.supabase_client import get_client, is_online
        except Exception:
            return 0, "supabase_import_unavailable"

        if not is_online():
            return 0, "offline"

        client = get_client()
        if client is None:
            return 0, "client_unavailable"

        user_id = self._user_id
        cached = 0

        try:
            query = client.table("feature_flags").select("key,enabled,scope,user_id,rollout_pct,config_json")
            res = query.execute()
            rows = res.data or []
        except Exception as exc:
            return 0, f"feature_flags_unavailable:{exc}"

        for row in rows:
            key = str(row.get("key") or "").strip()
            if not key:
                continue
            payload = {
                "enabled": bool(row.get("enabled", False)),
                "rollout_pct": int(row.get("rollout_pct", 100) or 100),
            }
            scope = str(row.get("scope") or "global").strip().lower()
            row_user = str(row.get("user_id") or "").strip()
            if scope == "user" and row_user:
                self._db.set_setting(self._key_remote_user(key, row_user), json.dumps(payload))
                if user_id and user_id == row_user:
                    cached += 1
            else:
                self._db.set_setting(self._key_remote_global(key), json.dumps(payload))
                cached += 1

            cfg = row.get("config_json")
            if cfg is not None:
                if scope == "user" and row_user:
                    self._db.set_setting(f"cfg.user.{row_user}.{key}", json.dumps(cfg))
                else:
                    self._db.set_setting(f"cfg.global.{key}", json.dumps(cfg))
        return cached, "ok"


if __name__ == "__main__":
    import sys

    print("feature_flags.py is a support module.")
    print(f"Start DishBoard with: {sys.executable} DishBoard.py")
