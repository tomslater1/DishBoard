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
