import requests
from recipe_scrapers import scrape_html

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def check_scrapeable(url: str) -> bool:
    """Quick check: fetch the URL and return True if recipe content can be extracted."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        scraper = scrape_html(resp.text, org_url=url)

        def _safe(fn):
            try:
                return fn()
            except Exception:
                return None

        ingredients  = _safe(scraper.ingredients) or []
        instructions = _safe(scraper.instructions_list) or []
        if not instructions:
            raw = _safe(scraper.instructions) or ""
            instructions = [s.strip() for s in raw.split("\n") if s.strip()]

        return bool(ingredients or instructions)
    except Exception:
        return False


def scrape_recipe(url: str) -> dict:
    """Scrape a recipe from a URL using recipe-scrapers. Returns a structured dict."""
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    scraper = scrape_html(resp.text, org_url=url)

    def _safe(fn):
        try:
            return fn()
        except Exception:
            return None

    ingredients  = _safe(scraper.ingredients) or []
    instructions = _safe(scraper.instructions_list) or []
    if not instructions:
        raw = _safe(scraper.instructions) or ""
        instructions = [s.strip() for s in raw.split("\n") if s.strip()]

    return {
        "title":        _safe(scraper.title)      or "",
        "image":        _safe(scraper.image)       or "",
        "total_time":   _safe(scraper.total_time)  or 0,
        "yields":       _safe(scraper.yields)      or "",
        "ingredients":  ingredients,
        "instructions": instructions,
        "host":         _safe(scraper.host)        or "",
        "url":          url,
    }
