"""Supabase Storage helper for recipe images.

No Qt dependency — safe to call from run_async worker threads.
"""
from __future__ import annotations

import os


def is_supabase_url(url: str) -> bool:
    """Return True if *url* is already a Supabase Storage CDN URL."""
    if not url:
        return False
    supabase_url = os.environ.get("SUPABASE_URL", "")
    if supabase_url and url.startswith(supabase_url):
        return True
    # Also catch generic supabase.co storage URLs
    return "supabase.co/storage" in url or "supabase.in/storage" in url


def upload_recipe_image(
    supabase_client,
    user_id: str,
    recipe_id: int,
    image_source: str,
) -> str | None:
    """Download *image_source* (URL or local path) and upload to Supabase Storage.

    Storage path: ``{user_id}/{recipe_id}.jpg``

    Returns the permanent public CDN URL on success, or ``None`` on any failure.
    Never raises.
    """
    if not image_source or not user_id or not recipe_id:
        return None

    try:
        # Skip if already a Supabase URL
        if is_supabase_url(image_source):
            return None

        # Fetch image bytes
        image_bytes: bytes | None = None
        if image_source.startswith(("http://", "https://")):
            import requests
            resp = requests.get(image_source, timeout=15)
            resp.raise_for_status()
            image_bytes = resp.content
        else:
            # Local file path
            with open(image_source, "rb") as fh:
                image_bytes = fh.read()

        if not image_bytes:
            return None

        storage_path = f"{user_id}/{recipe_id}.jpg"
        supabase_client.storage.from_("recipe-images").upload(
            storage_path,
            image_bytes,
            file_options={"upsert": "true", "content-type": "image/jpeg"},
        )

        supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        if not supabase_url:
            return None
        return f"{supabase_url}/storage/v1/object/public/recipe-images/{storage_path}"

    except Exception:
        return None
