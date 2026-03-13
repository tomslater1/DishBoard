from __future__ import annotations

import unittest

from utils.recipe_health import validate_recipe, has_nutrition


class TestRecipeHealth(unittest.TestCase):
    def test_validate_recipe_flags_missing(self):
        report = validate_recipe({"title": "", "ingredients": [], "instructions": []})
        self.assertGreaterEqual(len(report["errors"]), 2)
        self.assertLess(report["score"], 60)

    def test_has_nutrition_detects_macros(self):
        recipe = {"nutrition_per_serving": {"kcal": 400, "protein_g": 25, "carbs_g": 40, "fat_g": 12}}
        self.assertTrue(has_nutrition(recipe))


if __name__ == "__main__":
    unittest.main()
