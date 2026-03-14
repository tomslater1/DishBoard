"""Recipe scaling helpers for user-facing detail views."""

from __future__ import annotations

import copy
import re
from fractions import Fraction


_NUMBER_RE = re.compile(r"(?<![A-Za-z])(\d+/\d+|\d+(?:\.\d+)?)")
_MACRO_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g")


def _to_float(value) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except Exception:
        pass
    try:
        return float(Fraction(text))
    except Exception:
        return 0.0


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 0.02:
        return str(int(round(value)))
    if 0 < value < 1:
        for denom in (2, 3, 4, 8):
            frac = Fraction(value).limit_denominator(denom)
            if abs(float(frac) - value) < 0.02:
                if frac.numerator > frac.denominator:
                    whole = frac.numerator // frac.denominator
                    rem = frac - whole
                    return f"{whole} {rem.numerator}/{rem.denominator}" if rem.numerator else str(whole)
                return f"{frac.numerator}/{frac.denominator}"
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _scale_text_numbers(text: str, factor: float) -> str:
    if not text or abs(factor - 1.0) < 0.001:
        return text

    def _replace(match: re.Match[str]) -> str:
        raw = match.group(1)
        value = _to_float(raw)
        if value <= 0:
            return raw
        return _format_number(value * factor)

    return _NUMBER_RE.sub(_replace, text, count=2)


def _servings_value(recipe: dict) -> float:
    raw = recipe.get("servings") or recipe.get("yields") or 1
    text = str(raw).strip().split()[0] if str(raw).strip() else "1"
    value = _to_float(text)
    return value if value > 0 else 1.0


def scale_recipe(recipe: dict, target_servings: float | int) -> dict:
    base = copy.deepcopy(recipe or {})
    base_servings = _servings_value(base)
    target = max(1.0, float(target_servings or 1))
    factor = target / base_servings if base_servings > 0 else 1.0

    scaled = copy.deepcopy(base)
    scaled["servings"] = int(target) if float(target).is_integer() else round(target, 1)
    scaled["scaled_from_servings"] = base_servings
    scaled["scale_factor"] = round(factor, 3)

    ingredients = []
    for item in base.get("ingredients", []) or []:
        ingredients.append(_scale_text_numbers(str(item), factor))
    if ingredients:
        scaled["ingredients"] = ingredients

    per_serving = dict(base.get("nutrition_per_serving") or base.get("nutrition") or {})
    total = dict(base.get("nutrition_total") or {})
    if per_serving:
        scaled["nutrition_per_serving"] = per_serving
        scaled["nutrition_total"] = {
            key: round(float(per_serving.get(key, 0) or 0) * target, 1)
            for key in _MACRO_KEYS
        }
    elif total:
        scaled["nutrition_total"] = {
            key: round(float(total.get(key, 0) or 0) * factor, 1)
            for key in _MACRO_KEYS
        }
        scaled["nutrition_per_serving"] = {
            key: round(float(scaled["nutrition_total"].get(key, 0) or 0) / max(target, 1.0), 1)
            for key in _MACRO_KEYS
        }
    return scaled
