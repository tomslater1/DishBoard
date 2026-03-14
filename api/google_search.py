from __future__ import annotations

from urllib.parse import quote, urljoin

import certifi
import requests

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None  # type: ignore


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
}


def _clean(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


class GoogleSearchAPI:
    def _fetch_html(self, url: str) -> str:
        resp = requests.get(url, headers=_HEADERS, timeout=15, verify=certifi.where())
        resp.raise_for_status()
        return resp.text

    def _search_bbcgoodfood(self, query: str, limit: int) -> list[dict]:
        if BeautifulSoup is None:
            return []
        html = self._fetch_html(f"https://www.bbcgoodfood.com/search?q={quote(query)}")
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict] = []
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "").strip()
            if "/recipes/" not in href:
                continue
            if any(part in href for part in ("/recipes/category/", "/recipes/collection/")):
                continue
            url = urljoin("https://www.bbcgoodfood.com", href)
            if url in seen or not url.startswith("https://www.bbcgoodfood.com/recipes/"):
                continue
            title = _clean(anchor.get_text(" ", strip=True))
            if not title:
                continue
            results.append({"title": title, "url": url, "snippet": ""})
            seen.add(url)
            if len(results) >= limit:
                break
        return results

    def _search_delish(self, query: str, limit: int) -> list[dict]:
        if BeautifulSoup is None:
            return []
        html = self._fetch_html(f"https://www.delish.com/search/?q={quote(query)}")
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict] = []
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "").strip()
            if "/cooking/recipe-ideas/" not in href:
                continue
            url = urljoin("https://www.delish.com", href)
            if url in seen or not url.startswith("https://www.delish.com/cooking/recipe-ideas/"):
                continue
            full_text = _clean(anchor.get_text(" ", strip=True))
            title = _clean(anchor.get("data-vars-ga-call-to-action") or "")
            if not title and full_text:
                title = full_text.split(" Sep ")[0].split(" Oct ")[0].split(" Nov ")[0].split(" Dec ")[0]
            if not title:
                continue
            snippet = full_text[len(title):].strip(" -") if full_text.startswith(title) else ""
            results.append({"title": title, "url": url, "snippet": snippet})
            seen.add(url)
            if len(results) >= limit:
                break
        return results

    def search_recipes(self, query: str, num: int = 50) -> list[dict]:
        """Search for recipes from scrapeable recipe sites."""
        limit = max(6, min(int(num or 18), 24))
        results: list[dict] = []
        seen: set[str] = set()

        def _extend(items: list[dict]) -> None:
            for item in items:
                url = str(item.get("url") or "").strip()
                title = _clean(item.get("title", ""))
                if not url or not title or url in seen:
                    continue
                results.append(
                    {
                        "title": title,
                        "url": url,
                        "snippet": _clean(item.get("snippet", "")),
                    }
                )
                seen.add(url)
                if len(results) >= limit:
                    break

        for loader in (self._search_bbcgoodfood, self._search_delish):
            try:
                _extend(loader(query, limit))
            except Exception:
                continue
            if len(results) >= limit:
                break
        return results[:limit]
