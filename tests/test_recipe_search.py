from __future__ import annotations

import json

from tests.base import TempDBTestCase
from utils.recipe_search import filter_and_rank_saved_recipes


class RecipeSearchTests(TempDBTestCase):
    def test_typo_tolerant_title_search(self):
        self.db.save_recipe(
            "a1",
            "manual",
            "Spaghetti Bolognese",
            data_json=json.dumps({"tags": ["Dinner"], "ingredients": ["beef mince", "spaghetti"]}),
        )
        self.db.save_recipe(
            "a2",
            "manual",
            "Chicken Curry",
            data_json=json.dumps({"tags": ["Dinner"], "ingredients": ["chicken breast", "curry paste"]}),
        )

        rows = self.db.get_saved_recipes()
        ranked = filter_and_rank_saved_recipes(rows, "spagheti")

        self.assertTrue(ranked)
        self.assertEqual(dict(ranked[0])["title"], "Spaghetti Bolognese")

    def test_ingredient_and_tag_search(self):
        self.db.save_recipe(
            "b1",
            "manual",
            "Greek Bowl",
            data_json=json.dumps({
                "tags": ["Lunch", "High-Protein"],
                "ingredients": ["chicken", "cucumber", "yogurt"],
                "description": "A fast high protein bowl",
            }),
        )
        rows = self.db.get_saved_recipes()

        ranked = filter_and_rank_saved_recipes(rows, "high protien chicken")
        self.assertEqual(len(ranked), 1)
        self.assertEqual(dict(ranked[0])["title"], "Greek Bowl")


if __name__ == "__main__":
    import unittest

    unittest.main()
