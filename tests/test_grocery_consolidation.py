from __future__ import annotations

import unittest

from utils.grocery_consolidation import consolidate_rows


class TestGroceryConsolidation(unittest.TestCase):
    def test_merges_similar_items(self):
        rows = [
            {"id": 1, "name": "Tomatoes", "quantity": "2", "unit": "", "checked": 0, "source": "manual"},
            {"id": 2, "name": "tomato", "quantity": "1", "unit": "", "checked": 0, "source": "meal_plan"},
            {"id": 3, "name": "milk", "quantity": "1", "unit": "l", "checked": 0, "source": "manual"},
        ]
        merged, stats = consolidate_rows(rows)
        self.assertEqual(stats["merged_rows"], 1)
        self.assertEqual(len(merged), 2)
        names = sorted((r["name"].lower() for r in merged))
        self.assertEqual(names, ["milk", "tomatoes"])


if __name__ == "__main__":
    unittest.main()
