"""Pure helpers for nutrition trend summaries and coaching copy."""

from __future__ import annotations

from datetime import date, timedelta

from utils.macro_goals import get_macro_goals


def build_nutrition_trend(db, *, days: int = 7) -> dict:
    goals = get_macro_goals(db)
    today = date.today()
    day_rows: list[dict] = []
    adherence_hits = 0
    protein_hits = 0

    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        rows = db.get_nutrition_logs(day.isoformat())
        totals = {
            "date": day.isoformat(),
            "kcal": sum(float(r["kcal"] or 0) for r in rows),
            "protein_g": sum(float(r["protein_g"] or 0) for r in rows),
            "carbs_g": sum(float(r["carbs_g"] or 0) for r in rows),
            "fat_g": sum(float(r["fat_g"] or 0) for r in rows),
            "entries": len(rows),
        }
        if totals["entries"] > 0:
            kcal_goal = max(float(goals.get("kcal", 2000) or 2000), 1.0)
            protein_goal = max(float(goals.get("protein_g", 50) or 50), 1.0)
            if abs(totals["kcal"] - kcal_goal) / kcal_goal <= 0.15:
                adherence_hits += 1
            if totals["protein_g"] >= protein_goal * 0.9:
                protein_hits += 1
        day_rows.append(totals)

    tracked_days = sum(1 for row in day_rows if row["entries"] > 0)
    kcal_avg = sum(row["kcal"] for row in day_rows) / max(tracked_days, 1)
    protein_avg = sum(row["protein_g"] for row in day_rows) / max(tracked_days, 1)
    kcal_goal = float(goals.get("kcal", 2000) or 2000)
    protein_goal = float(goals.get("protein_g", 50) or 50)

    if tracked_days == 0:
        summary = "No nutrition has been logged this week yet."
        action = "Log today’s meals and Dishy will start spotting trends."
    else:
        kcal_delta = kcal_avg - kcal_goal
        protein_delta = protein_avg - protein_goal
        if protein_delta < -12:
            summary = "Protein has been the most consistent gap this week."
            action = "Add one higher-protein snack or choose a stronger lunch protein source."
        elif kcal_delta > kcal_goal * 0.12:
            summary = "Calories are trending above target this week."
            action = "Trim one calorie-dense extra and keep protein the same."
        elif kcal_delta < -kcal_goal * 0.12:
            summary = "Calories are trending below target this week."
            action = "Add an extra balanced meal or snack so recovery stays on track."
        else:
            summary = "Your calorie trend is close to target."
            action = "Keep the same rhythm and use Dishy to protect protein consistency."

    return {
        "tracked_days": tracked_days,
        "days": day_rows,
        "adherence_days": adherence_hits,
        "protein_hit_days": protein_hits,
        "avg_kcal": round(kcal_avg, 1),
        "avg_protein_g": round(protein_avg, 1),
        "goal_kcal": round(kcal_goal, 1),
        "goal_protein_g": round(protein_goal, 1),
        "summary": summary,
        "action": action,
    }

