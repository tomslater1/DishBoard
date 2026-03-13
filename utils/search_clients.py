"""Lazy search/API client factories used by the UI."""

from __future__ import annotations

from functools import lru_cache

from api.google_search import GoogleSearchAPI


@lru_cache(maxsize=1)
def get_google_search_api() -> GoogleSearchAPI:
    return GoogleSearchAPI()
