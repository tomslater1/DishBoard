"""Application version metadata loaded from bundled assets."""

from __future__ import annotations

from utils.assets import load_json_asset


VERSION_HISTORY = load_json_asset("assets/metadata/version_history.json")
APP_VERSION = str((VERSION_HISTORY[0] if VERSION_HISTORY else {}).get("version", "v0.0"))
