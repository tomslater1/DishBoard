"""Recipe quality checks and lightweight auto-fixes."""

from __future__ import annotations

import copy


_MACRO_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g")


def _num(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _clean_text_lines(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        txt = " ".join(str(item or "").split()).strip()
        if not txt:
            continue
        key = txt.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(txt)
    return out


def has_nutrition(recipe: dict | None) -> bool:
    if not recipe:
        return False
    per = recipe.get("nutrition_per_serving") or recipe.get("nutrition") or {}
    return sum(_num(per.get(k)) for k in ("kcal", "protein_g", "carbs_g", "fat_g")) > 0


def validate_recipe(recipe: dict) -> dict:
    """Return {fixed, errors, warnings, score} for a recipe-like dict."""
    fixed = copy.deepcopy(recipe or {})
    errors: list[str] = []
    warnings: list[str] = []

    fixed["title"] = " ".join(str(fixed.get("title") or "").split()).strip()
    fixed["ingredients"] = _clean_text_lines(fixed.get("ingredients") or [])
    fixed["instructions"] = _clean_text_lines(fixed.get("instructions") or [])

    if not fixed["title"]:
        errors.append("Recipe title is missing")
    if not fixed["ingredients"]:
        errors.append("No ingredients were found")
    if not fixed["instructions"]:
        errors.append("No instructions were found")

    servings = fixed.get("servings") or fixed.get("yields") or 0
    try:
        servings_int = int(float(str(servings).split()[0])) if str(servings).strip() else 0
    except Exception:
        servings_int = 0
    if servings_int <= 0:
        warnings.append("Serving count is missing or unclear")

    nutr = fixed.get("nutrition_per_serving") or fixed.get("nutrition") or {}
    if not isinstance(nutr, dict):
        nutr = {}
    total_macro = sum(_num(nutr.get(k)) for k in ("kcal", "protein_g", "carbs_g", "fat_g"))
    if total_macro <= 0:
        warnings.append("Nutrition is missing")

    if len(fixed["ingredients"]) < 3:
        warnings.append("Very short ingredient list")
    if len(fixed["instructions"]) < 2:
        warnings.append("Very short instruction list")

    score = max(0, 100 - (len(errors) * 25) - (len(warnings) * 8))
    return {
        "fixed": fixed,
        "errors": errors,
        "warnings": warnings,
        "score": int(score),
    }


def health_label(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 55:
        return "Needs attention"
    return "Poor"
