"""Lightweight retrieval memory for Dishy prompts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from models.database import Database


_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class MemorySnippet:
    source: str
    text: str


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _score(query: str, snippet: str) -> float:
    q = query.strip().lower()
    if not q:
        return 0.0

    query_tokens = _tokens(q)
    snippet_tokens = _tokens(snippet)
    if not query_tokens or not snippet_tokens:
        return 0.0

    token_set = set(snippet_tokens)
    score = 0.0

    if q in snippet.lower():
        score += 7.0

    for qt in query_tokens:
        if qt in token_set:
            score += 2.0
            continue

        # Typo tolerance: if a near-match token exists, give partial credit.
        best = 0.0
        for st in snippet_tokens[:80]:
            ratio = SequenceMatcher(None, qt, st).ratio()
            if ratio > best:
                best = ratio
        if best >= 0.84:
            score += 1.2
        elif best >= 0.74:
            score += 0.5

    # Additional soft similarity against whole snippet body.
    score += SequenceMatcher(None, q[:120], snippet.lower()[:240]).ratio() * 1.5
    return score


def _build_corpus(db: Database) -> list[MemorySnippet]:
    snippets: list[MemorySnippet] = []

    # Profile + preferences
    for key in (
        "user_name",
        "user_household_size",
        "dietary_prefs",
        "allergens",
        "lifestyle_scenarios",
        "cuisine_preferences",
        "cooking_skill",
        "weekly_cooking_goal",
        "body_height_cm",
        "body_weight_kg",
        "household_user2_name",
        "household_user2_height_cm",
        "household_user2_weight_kg",
    ):
        val = db.get_setting(key, "").strip()
        if val:
            snippets.append(MemorySnippet("profile", f"{key}: {val}"))

    # Recipes
    for row in db.get_saved_recipes()[:300]:
        try:
            data = json.loads(row["data_json"] or "{}")
        except Exception:
            data = {}
        tags = ", ".join(data.get("tags", []))
        ingredients = ", ".join((data.get("ingredients", []) or [])[:15])
        desc = data.get("description", "") or row.get("summary", "")
        text = (
            f"Recipe: {row['title']}. Tags: {tags}. Ingredients: {ingredients}. "
            f"Description: {desc}"
        )
        snippets.append(MemorySnippet("recipe", text))

    # Meal plan
    try:
        from datetime import date, timedelta

        today = date.today()
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        rows = db.get_meal_plan(week_start)
        for row in rows:
            snippets.append(
                MemorySnippet(
                    "meal_plan",
                    f"{row['day_of_week']} {row['meal_type']}: {row.get('custom_name') or ''}",
                )
            )
    except Exception:
        pass

    # Pantry
    for item in db.get_pantry_items():
        qty = item.get("quantity")
        unit = item.get("unit") or ""
        expiry = item.get("expiry_date") or ""
        qty_part = f"{qty} {unit}".strip() if qty is not None else ""
        text = f"{item.get('storage', 'Pantry')} item: {item.get('name', '')} {qty_part}. Expiry: {expiry}"
        snippets.append(MemorySnippet("pantry", text.strip()))

    # Shopping list
    for row in db.get_shopping_items()[:200]:
        snippets.append(MemorySnippet("shopping", f"Shopping: {row['name']} {row.get('quantity') or ''} {row.get('unit') or ''}".strip()))

    # Recent nutrition logs
    try:
        from datetime import date, timedelta

        for d in range(0, 7):
            day = (date.today() - timedelta(days=d)).isoformat()
            for row in db.get_nutrition_logs(day):
                snippets.append(
                    MemorySnippet(
                        "nutrition",
                        f"{row['log_date']}: {row['food_name']} ({row['kcal']} kcal, {row['protein_g']}g protein)",
                    )
                )
    except Exception:
        pass

    # Recent Dishy history
    rows = db.conn.execute(
        "SELECT role, content, timestamp FROM dishy_chat_history ORDER BY id DESC LIMIT 120"
    ).fetchall()
    for row in rows:
        role = row["role"]
        content = (row["content"] or "")[:220]
        snippets.append(MemorySnippet("chat", f"{role}: {content}"))

    return snippets


def build_memory_context(db: Database, query: str, *, max_items: int = 12) -> str:
    """Return a compact ranked memory block for the current prompt."""
    query = (query or "").strip()
    if not query:
        return ""

    snippets = _build_corpus(db)
    if not snippets:
        return ""

    scored: list[tuple[float, MemorySnippet]] = []
    for snip in snippets:
        s = _score(query, snip.text)
        if s >= 1.6:
            scored.append((s, snip))

    if not scored:
        return ""

    scored.sort(key=lambda x: x[0], reverse=True)

    selected: list[str] = []
    seen = set()
    for _, snip in scored[: max_items * 2]:
        line = f"- [{snip.source}] {snip.text.strip()}"
        if line.lower() in seen:
            continue
        seen.add(line.lower())
        selected.append(line)
        if len(selected) >= max_items:
            break

    if not selected:
        return ""

    return "## Retrieved memory\n" + "\n".join(selected)
