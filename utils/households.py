"""Household sharing helpers (Supabase-backed with safe local fallback)."""

from __future__ import annotations

import random
import string
import uuid

from models.database import Database


def _gen_code(length: int = 8) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(alphabet) for _ in range(max(6, int(length))))


def _reset_sync_markers(db: Database) -> None:
    db.set_setting("sync_last_push_at", "1970-01-01T00:00:00+00:00")
    db.set_setting("sync_last_pull_at", "1970-01-01T00:00:00+00:00")


def status(db: Database) -> dict:
    hid = db.get_setting("household_id", "").strip()
    return {
        "household_id": hid,
        "household_name": db.get_setting("household_name", "").strip(),
        "household_role": db.get_setting("household_role", "").strip() or "member",
        "invite_code": db.get_setting("household_invite_code", "").strip(),
        "is_shared": bool(hid),
    }


def _current_user_id(client) -> str:
    session = client.auth.get_session()
    user = getattr(session, "user", None)
    if user and getattr(user, "id", None):
        return str(user.id)
    nested = getattr(session, "session", None)
    n_user = getattr(nested, "user", None) if nested else None
    if n_user and getattr(n_user, "id", None):
        return str(n_user.id)
    return ""


def create_household(db: Database, *, name: str) -> tuple[bool, str, dict]:
    from auth.supabase_client import get_client

    client = get_client()
    if client is None:
        return False, "Supabase client unavailable", status(db)

    user_id = _current_user_id(client)
    if not user_id:
        return False, "Please sign in again before creating a household", status(db)

    hid = str(uuid.uuid4())
    code = _gen_code(8)
    hh_name = " ".join((name or "My Household").split()).strip()[:80] or "My Household"

    try:
        client.table("households").insert(
            {
                "id": hid,
                "name": hh_name,
                "owner_user_id": user_id,
            }
        ).execute()
        client.table("household_invites").upsert(
            {
                "invite_code": code,
                "household_id": hid,
                "household_name": hh_name,
                "created_by": user_id,
                "active": True,
            }
        ).execute()
        client.table("household_members").upsert(
            {
                "household_id": hid,
                "user_id": user_id,
                "role": "owner",
            }
        ).execute()
    except Exception as exc:
        return False, f"Could not create household: {exc}", status(db)

    db.set_setting("household_id", hid)
    db.set_setting("household_name", hh_name)
    db.set_setting("household_role", "owner")
    db.set_setting("household_invite_code", code)
    _reset_sync_markers(db)
    return True, "Household created", status(db)


def join_household(db: Database, *, invite_code: str) -> tuple[bool, str, dict]:
    from auth.supabase_client import get_client

    client = get_client()
    if client is None:
        return False, "Supabase client unavailable", status(db)

    user_id = _current_user_id(client)
    if not user_id:
        return False, "Please sign in again before joining a household", status(db)

    code = "".join(str(invite_code or "").upper().split())
    if len(code) < 6:
        return False, "Invite code looks too short", status(db)

    try:
        res = (
            client.table("household_invites")
            .select("household_id,household_name")
            .eq("invite_code", code)
            .eq("active", True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return False, "Invite code not found", status(db)
        row = rows[0]
        hid = str(row.get("household_id") or "").strip()
        if not hid:
            return False, "Invite is missing household id", status(db)

        client.table("household_members").upsert(
            {
                "household_id": hid,
                "user_id": user_id,
                "role": "member",
            }
        ).execute()

        # Switch local cache scope to joined household data.
        db.clear_user_data()
        db.set_setting("household_id", hid)
        db.set_setting("household_name", str(row.get("household_name") or "Shared Household").strip())
        db.set_setting("household_role", "member")
        db.set_setting("household_invite_code", code)
        _reset_sync_markers(db)
        return True, "Joined household", status(db)
    except Exception as exc:
        return False, f"Could not join household: {exc}", status(db)


def leave_household(db: Database) -> tuple[bool, str, dict]:
    from auth.supabase_client import get_client

    current = status(db)
    hid = current["household_id"]
    if not hid:
        return True, "Not currently in a shared household", current

    client = get_client()
    if client is not None:
        user_id = _current_user_id(client)
        if user_id:
            try:
                client.table("household_members").delete().eq("household_id", hid).eq("user_id", user_id).execute()
            except Exception:
                pass

    # Reset local cache when leaving shared scope.
    db.clear_user_data()
    db.set_setting("household_id", "")
    db.set_setting("household_name", "")
    db.set_setting("household_role", "")
    db.set_setting("household_invite_code", "")
    _reset_sync_markers(db)
    return True, "Left household", status(db)
