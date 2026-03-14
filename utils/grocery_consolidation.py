"""Shopping-list consolidation helpers."""

from __future__ import annotations

import re


_WORD_RE = re.compile(r"[a-z0-9]+")


def _norm_name(name: str) -> str:
    tokens = _WORD_RE.findall((name or "").lower())
    # Very light plural normalization
    out = []
    for t in tokens:
        if len(t) > 3 and t.endswith("ies"):
            out.append(t[:-3] + "y")
        elif len(t) > 4 and t.endswith("oes"):
            out.append(t[:-2])
        elif len(t) > 3 and t.endswith("s"):
            out.append(t[:-1])
        else:
            out.append(t)
    return " ".join(out).strip()


def _parse_qty(value) -> float | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        pass
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def consolidate_rows(rows: list[dict]) -> tuple[list[dict], dict]:
    """Merge equivalent shopping rows.

    Returns (consolidated_rows, stats).
    """
    groups: dict[str, list[dict]] = {}
    for row in rows or []:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        key = _norm_name(name) or name.lower()
        groups.setdefault(key, []).append(dict(row))

    consolidated: list[dict] = []
    merged_count = 0
    for _key, items in groups.items():
        if len(items) == 1:
            consolidated.append(items[0])
            continue

        merged_count += len(items) - 1
        base = dict(items[0])
        base["name"] = max((str(i.get("name") or "") for i in items), key=len).strip() or base.get("name", "")

        units = {str(i.get("unit") or "").strip().lower() for i in items if str(i.get("unit") or "").strip()}
        qtys = [_parse_qty(i.get("quantity")) for i in items]
        qty_vals = [q for q in qtys if q is not None]

        if len(units) <= 1 and qty_vals and len(qty_vals) == len(items):
            total = round(sum(qty_vals), 2)
            base["quantity"] = str(int(total) if float(total).is_integer() else total)
            base["unit"] = next(iter(units), str(base.get("unit") or ""))
        else:
            base["quantity"] = f"x{len(items)}"
            if len(units) > 1:
                base["unit"] = "mixed"

        base["checked"] = 1 if all(int(i.get("checked") or 0) == 1 for i in items) else 0
        sources = {str(i.get("source") or "") for i in items}
        base["source"] = "meal_plan" if "meal_plan" in sources else (next(iter(sources)) if sources else "manual")
        base["_merged_ids"] = [int(i.get("id") or 0) for i in items if int(i.get("id") or 0) > 0]
        consolidated.append(base)

    stats = {
        "input_rows": len(rows or []),
        "output_rows": len(consolidated),
        "merged_rows": merged_count,
    }
    return consolidated, stats


def build_shopping_overview(rows: list[dict], pantry_items: list[dict] | None = None) -> dict:
    pantry_names = {_norm_name(str(item.get("name") or "")) for item in (pantry_items or []) if str(item.get("name") or "").strip()}
    aisle_groups: dict[str, int] = {}
    estimated_cost = 0.0
    pantry_overlap = 0

    price_table = {
        "produce": 1.8,
        "meat fish": 4.6,
        "dairy egg": 2.2,
        "bakery": 1.7,
        "pantry": 1.3,
        "frozen": 2.4,
        "drink": 1.5,
        "snack": 1.4,
        "other": 1.2,
    }

    for row in rows or []:
        raw_name = str(row.get("name") or "").strip()
        if not raw_name:
            continue
        norm = _norm_name(raw_name)
        if norm in pantry_names:
            pantry_overlap += 1
        aisle = "other"
        lowered = norm.replace("&", " ")
        for key in price_table:
            if key in lowered:
                aisle = key
                break
        aisle_groups[aisle] = aisle_groups.get(aisle, 0) + 1
        qty = _parse_qty(row.get("quantity"))
        estimated_cost += price_table.get(aisle, 1.2) * (qty if qty and qty > 0 else 1.0)

    return {
        "aisle_count": len(aisle_groups),
        "pantry_overlap_count": pantry_overlap,
        "estimated_cost": round(estimated_cost, 2),
    }
