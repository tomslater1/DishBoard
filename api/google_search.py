from ddgs import DDGS


class GoogleSearchAPI:
    def search_recipes(self, query: str, num: int = 50) -> list[dict]:
        """Search for recipes via DuckDuckGo. Returns list of {title, url, snippet} dicts.
        BBC Good Food results are fetched first and prioritised at the top."""
        ddgs = DDGS()

        def _parse(results):
            return [
                {
                    "title":   r.get("title", ""),
                    "url":     r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in results
            ]

        # BBC Good Food targeted search first
        bbc_results = []
        try:
            bbc_raw = list(ddgs.text(
                f"site:bbcgoodfood.com {query} recipe",
                max_results=10,
            ))
            bbc_results = _parse(bbc_raw)
        except Exception:
            pass

        # General search for broader results
        general_results = []
        try:
            general_raw = list(ddgs.text(
                f"{query} recipe",
                max_results=num,
            ))
            general_results = _parse(general_raw)
        except Exception:
            pass

        # Combine: BBC first, then general (deduped by URL)
        seen_urls = {r["url"] for r in bbc_results}
        combined = bbc_results + [r for r in general_results if r["url"] not in seen_urls]
        return combined
