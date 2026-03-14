from __future__ import annotations

from tests.base import TempDBTestCase
from utils.planner_intelligence import (
    dump_slot_metadata,
    load_slot_metadata,
    load_templates,
    save_template,
    summarise_week,
)


class PlannerIntelligenceTests(TempDBTestCase):
    def test_template_round_trip_uses_slot_titles(self):
        self.db.set_meal_slot(
            "2026-03-09",
            "Monday",
            "dinner",
            custom_name="Chicken Stir Fry",
            recipe_id=None,
            notes=dump_slot_metadata({"prep_batch": True, "leftover_portions": 2}),
        )
        rows = [dict(r) for r in self.db.conn.execute("SELECT * FROM meal_plans").fetchall()]
        save_template(self.db, "Prep Week", rows, mode="meal_prep")
        templates = load_templates(self.db)
        self.assertEqual(templates[0]["name"], "Prep Week")
        self.assertEqual(templates[0]["slots"][0]["recipe_title"], "Chicken Stir Fry")
        self.assertEqual(templates[0]["slots"][0]["metadata"]["leftover_portions"], 2)

    def test_week_summary_counts_prep_and_leftovers(self):
        rows = [
            {
                "custom_name": "Batch Chili",
                "notes": dump_slot_metadata({"prep_batch": True, "leftover_portions": 2, "owner_label": "Tom"}),
                "recipe_id": 1,
            },
            {
                "custom_name": "Chili Leftovers",
                "notes": dump_slot_metadata({"leftover_source_day": "Monday", "owner_label": "Tom"}),
                "recipe_id": 1,
            },
        ]
        summary = summarise_week(rows)
        self.assertEqual(summary["prep_slots"], 1)
        self.assertEqual(summary["leftover_slots"], 2)
        self.assertEqual(summary["editors"], ["Tom"])
        self.assertTrue(load_slot_metadata(rows[0]["notes"]).get("prep_batch"))

