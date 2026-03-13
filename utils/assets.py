"""Helpers for loading bundled text and JSON assets."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from utils.paths import get_resource_path


@lru_cache(maxsize=32)
def load_text_asset(relative_path: str) -> str:
    path = get_resource_path(relative_path)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@lru_cache(maxsize=16)
def load_json_asset(relative_path: str) -> Any:
    return json.loads(load_text_asset(relative_path))
