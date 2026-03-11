"""
GitHub Releases update checker for DishBoard.

Polls the GitHub Releases API on app launch (in a background thread via run_async).
Returns update info if a newer version is available, otherwise None.
All network errors are caught silently — never blocks or crashes the app.
"""

from __future__ import annotations

import requests

from utils.version import APP_VERSION

# Update this to your actual GitHub username/repo before first release
GITHUB_REPO = "tomslater1/dishboard"
_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def check_for_update(current: str = APP_VERSION) -> dict | None:
    """Return a dict with update info if a newer release exists, else None.

    Dict keys: version (str), notes (str), download_url (str)
    Safe to call from any thread.
    """
    try:
        r = requests.get(
            _API_URL,
            timeout=8,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        if r.status_code != 200:
            return None

        data = r.json()
        tag = data.get("tag_name", "").strip().lstrip("v")
        if not tag:
            return None

        if not _version_gt(tag, current.lstrip("v")):
            return None

        # Find the first .dmg asset, fall back to the release HTML page
        download_url = data.get("html_url", "")
        for asset in data.get("assets", []):
            if asset.get("name", "").lower().endswith(".dmg"):
                download_url = asset["browser_download_url"]
                break

        return {
            "version": tag,
            "notes": (data.get("body") or "").strip()[:600],
            "download_url": download_url,
        }
    except Exception:
        return None


def _version_gt(a: str, b: str) -> bool:
    """Return True if version string a is strictly greater than b.

    Handles simple dotted numeric versions like "0.44" or "1.2.3".
    """
    def _parts(v: str) -> list[int]:
        try:
            return [int(x) for x in v.split(".")]
        except ValueError:
            return [0]

    return _parts(a) > _parts(b)
