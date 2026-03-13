"""Cross-platform OS helpers for fonts, file opening, and app integrations."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_macos() -> bool:
    return sys.platform == "darwin"


def preferred_ui_font_family() -> str:
    if is_windows():
        return "Segoe UI"
    if is_macos():
        return ".AppleSystemUIFont"
    return "DejaVu Sans"


def user_documents_dir() -> Path:
    home = Path.home()
    if is_windows():
        return Path(os.environ.get("USERPROFILE") or home) / "Documents"
    return home / "Documents"


def open_path_in_default_app(path: str) -> tuple[bool, str]:
    try:
        if is_windows():
            os.startfile(path)  # type: ignore[attr-defined]
            return True, ""
        if is_macos():
            subprocess.run(["open", path], check=True)
            return True, ""
        subprocess.run(["xdg-open", path], check=True)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def run_apple_script(script: str, *, timeout_seconds: int = 10) -> tuple[bool, str]:
    if not is_macos():
        return False, "AppleScript export is only available on macOS"
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds)),
        )
        if result.returncode != 0:
            return False, (result.stderr or "AppleScript failed").strip()
        return True, ""
    except Exception as exc:
        return False, str(exc)
