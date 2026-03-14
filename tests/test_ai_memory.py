from __future__ import annotations

import json

from tests.base import TempDBTestCase
from utils.ai_memory import build_memory_context, memory_source_summary


class AIMemoryTests(TempDBTestCase):
    def test_memory_contains_relevant_snippets(self):
        self.db.add_pantry_item("Chicken breast", quantity=2, unit="pack", storage="Fridge")
        self.db.save_recipe(
            "m1",
            "manual",
            "Chicken Stir Fry",
            data_json=json.dumps({
                "ingredients": ["chicken breast", "soy sauce", "pepper"],
                "tags": ["Dinner"],
                "description": "Quick stir fry",
            }),
        )

        mem = build_memory_context(self.db, "what can i cook with chicken")
        self.assertIn("Retrieved memory", mem)
        self.assertIn("Chicken", mem)

    def test_memory_summary_counts_sources(self):
        self.db.set_setting("user_name", "Tom")
        self.db.save_dishy_message("s1", "user", "Help me plan dinner")
        summary = memory_source_summary(self.db)
        self.assertGreaterEqual(summary["counts"].get("profile", 0), 1)
        self.assertGreaterEqual(summary["counts"].get("chat", 0), 1)
        self.assertEqual(summary["chat_sessions"], 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
