"""
Path helpers for DishBoard.

When running as a PyInstaller bundle:
  - macOS:   ~/Library/Application Support/DishBoard
  - Windows: %APPDATA%\\DishBoard
  - Linux:   ~/.local/share/DishBoard
  - get_resource_path() → sys._MEIPASS/<relative>                   (read-only assets)

When running in dev (python3 DishBoard.py):
  - get_data_dir()      → project root (same as current behaviour)
  - get_resource_path() → project root/<relative>
"""

import os
import sys


def get_data_dir() -> str:
    """Return the writable user-data directory for DishBoard.

    This is where the SQLite database, config.json, and any user-created
    files should live.  In a frozen bundle this is inside
    ~/Library/Application Support rather than the read-only .app bundle.
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support/DishBoard")
        elif sys.platform.startswith("win"):
            base = os.path.join(
                os.environ.get("APPDATA", os.path.expanduser("~")),
                "DishBoard",
            )
        else:
            base = os.path.expanduser("~/.local/share/DishBoard")
    else:
        # Dev: sit next to DishBoard.py (project root)
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(base, exist_ok=True)
    return base


def get_resource_path(relative: str) -> str:
    """Return the path to a bundled read-only asset.

    *relative* should be a path relative to the project root, e.g.
    ``"assets/styles/theme.qss"`` or ``"assets/icons/icon.png"``.
    """
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)
