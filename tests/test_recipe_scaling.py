from __future__ import annotations

import unittest

from utils.recipe_scaling import scale_recipe


class RecipeScalingTests(unittest.TestCase):
    def test_scale_recipe_updates_ingredients_and_totals(self):
        recipe = {
            "servings": 2,
            "ingredients": ["1 chicken breast", "1/2 onion", "2 tbsp yogurt"],
            "nutrition_per_serving": {"kcal": 400, "protein_g": 30, "carbs_g": 20, "fat_g": 10},
        }
        scaled = scale_recipe(recipe, 4)
        self.assertEqual(scaled["servings"], 4)
        self.assertIn("2 chicken breast", scaled["ingredients"][0])
        self.assertIn("1 onion", scaled["ingredients"][1])
        self.assertEqual(scaled["nutrition_total"]["kcal"], 1600.0)
        self.assertEqual(scaled["nutrition_per_serving"]["protein_g"], 30)


if __name__ == "__main__":
    unittest.main()

