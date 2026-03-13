"""Saved-recipe local search with ranking and typo tolerance."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _norm_text(text: str) -> str:
    return (text or "").strip().lower()


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(_norm_text(text))


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _field_text(recipe_row: dict) -> dict[str, str]:
    title = str(recipe_row.get("title") or "")
    summary = str(recipe_row.get("summary") or "")

    tags = ""
    ingredients = ""
    description = ""
    try:
        data = json.loads(recipe_row.get("data_json") or "{}")
        tags = " ".join(data.get("tags", []) or [])
        ingredients = " ".join(data.get("ingredients", []) or [])
        description = str(data.get("description") or "")
    except Exception:
        pass

    return {
        "title": title,
        "summary": summary,
        "tags": tags,
        "ingredients": ingredients,
        "description": description,
    }


def _score_recipe(recipe_row: dict, query: str) -> float:
    q = _norm_text(query)
    if not q:
        return 0.0

    fields = _field_text(recipe_row)
    title = _norm_text(fields["title"])
    summary = _norm_text(fields["summary"])
    tags = _norm_text(fields["tags"])
    ingredients = _norm_text(fields["ingredients"])
    description = _norm_text(fields["description"])

    combined = " ".join([title, tags, ingredients, summary, description]).strip()
    if not combined:
        return 0.0

    q_tokens = _tokens(q)
    title_tokens = _tokens(title)
    tags_tokens = _tokens(tags)
    ing_tokens = _tokens(ingredients)
    rest_tokens = _tokens(summary + " " + description)

    score = 0.0

    if q in title:
        score += 30.0
    if q in tags:
        score += 14.0
    if q in ingredients:
        score += 12.0
    if q in summary or q in description:
        score += 9.0

    title_set = set(title_tokens)
    tags_set = set(tags_tokens)
    ing_set = set(ing_tokens)
    rest_set = set(rest_tokens)

    for qt in q_tokens:
        if qt in title_set:
            score += 8.0
            continue
        if qt in tags_set:
            score += 4.8
            continue
        if qt in ing_set:
            score += 4.2
            continue
        if qt in rest_set:
            score += 2.3
            continue

        # Typo tolerance against title first, then ingredient vocabulary.
        near_title = max((_similarity(qt, tt) for tt in title_tokens[:40]), default=0.0)
        if near_title >= 0.84:
            score += 4.0
            continue
        if near_title >= 0.74:
            score += 2.0
            continue

        near_ing = max((_similarity(qt, it) for it in ing_tokens[:120]), default=0.0)
        if near_ing >= 0.86:
            score += 2.2

    # Whole-query fuzzy fallback for typos like "spagheti".
    score += _similarity(q, title) * 8.0
    score += _similarity(q, tags) * 3.0
    score += _similarity(q, ingredients[:300]) * 2.8

    return score


def filter_and_rank_saved_recipes(recipes: list, query: str) -> list:
    """Return recipes filtered by query and sorted by best match first."""
    q = _norm_text(query)
    if not q:
        return list(recipes)

    scored: list[tuple[float, object]] = []
    for row in recipes:
        row_dict = dict(row)
        score = _score_recipe(row_dict, q)
        if score >= 2.2:
            scored.append((score, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored]
