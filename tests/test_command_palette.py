from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QLineEdit

from main_window import MainWindow
from tests.base import TempDBTestCase
from widgets.command_palette import _EntryRow


class CommandPaletteTests(TempDBTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        super().setUp()
        self.window = MainWindow(db=self.db)
        self.window.show()
        self.window.activateWindow()
        self._flush()

    def tearDown(self) -> None:
        try:
            self.window.close()
            self.window.deleteLater()
            self._flush()
        finally:
            super().tearDown()

    def _flush(self) -> None:
        self._app.processEvents()
        QTest.qWait(0)
        self._app.processEvents()

    def _shortcut_modifier(self):
        return Qt.KeyboardModifier.MetaModifier if sys.platform == "darwin" else Qt.KeyboardModifier.ControlModifier

    def _save_recipe(self, title: str, *, tags: list[str] | None = None, ingredients: list[str] | None = None) -> int:
        data = {
            "title": title,
            "tags": tags or [],
            "ingredients": ingredients or [],
        }
        return self.db.save_recipe(
            source_id=title.lower().replace(" ", "-"),
            source="test",
            title=title,
            data_json=json.dumps(data),
        )

    def _open_palette_with_query(self, query: str = ""):
        self.window.open_command_palette()
        palette = self.window._command_palette
        if query:
            palette.set_query(query)
        self._flush()
        return palette

    def test_empty_query_shows_recent_quick_add_and_commands(self):
        self.assertTrue(self.window.run_command_palette_entry("open_settings"))
        palette = self._open_palette_with_query("")
        ids = palette.filtered_entry_ids()
        self.assertEqual(ids[0], "open_settings")
        self.assertIn("add_pantry_item", ids)
        self.assertIn("open_recipes", ids)

    def test_shortcut_opens_and_escape_closes_palette(self):
        self.assertFalse(self.window._command_palette.isVisible())
        QTest.keyClick(self.window, Qt.Key.Key_K, self._shortcut_modifier())
        self._flush()
        self.assertTrue(self.window._command_palette.isVisible())

        QTest.keyClick(self.window._command_palette._input, Qt.Key.Key_Escape)
        self._flush()
        self.assertFalse(self.window._command_palette.isVisible())

    def test_recipe_query_uses_saved_recipe_fuzzy_ranking(self):
        target_id = self._save_recipe("Spaghetti Bolognese", tags=["Pasta"], ingredients=["beef mince", "tomato"])
        self._save_recipe("Chicken Curry", tags=["Dinner"], ingredients=["chicken", "rice"])

        palette = self._open_palette_with_query("spagheti")
        self.assertEqual(palette.filtered_entry_ids()[0], f"recipe:{target_id}")

    def test_recipe_results_display_spaces_instead_of_underscores(self):
        recipe_id = self._save_recipe("One_Pot_Pasta", tags=["Quick_Dinner"])

        palette = self._open_palette_with_query("one pot")
        self.assertEqual(palette.filtered_entry_ids()[0], f"recipe:{recipe_id}")

        entry_widget = None
        for row in range(palette._list.count()):
            widget = palette._list.itemWidget(palette._list.item(row))
            if isinstance(widget, _EntryRow):
                entry_widget = widget
                break
        self.assertIsNotNone(entry_widget)
        self.assertEqual(entry_widget._title.text(), "One Pot Pasta")
        self.assertNotIn("_", entry_widget._subtitle.text())

    def test_recipe_results_display_ampersands_without_qt_mnemonics(self):
        recipe_id = self._save_recipe("Tuna_&_Rice", tags=["Fast_&_Cheap"])

        palette = self._open_palette_with_query("tuna")
        self.assertEqual(palette.filtered_entry_ids()[0], f"recipe:{recipe_id}")

        entry_widget = None
        for row in range(palette._list.count()):
            widget = palette._list.itemWidget(palette._list.item(row))
            if isinstance(widget, _EntryRow):
                entry_widget = widget
                break
        self.assertIsNotNone(entry_widget)
        self.assertEqual(entry_widget._title.text(), "Tuna && Rice")
        self.assertEqual(entry_widget._subtitle.text(), "Fast && Cheap")

    def test_recent_recipe_entries_store_spaces_instead_of_underscores(self):
        recipe_id = self._save_recipe("Sheet_Pan_Gnocchi", tags=["Fast_Dinner"])

        self.assertTrue(self.window.run_command_palette_entry(f"recipe:{recipe_id}", query="sheet pan"))
        recents = json.loads(self.db.get_setting("command_palette_recents", "[]"))

        self.assertEqual(recents[0]["title"], "Sheet Pan Gnocchi")
        self.assertNotIn("_", recents[0]["subtitle"])

    def test_mixed_queries_return_expected_result_types(self):
        self.db.add_pantry_item("Greek Yogurt", 2, "tubs", "Fridge")
        self.db.add_shopping_item("Greek Yogurt", quantity="1", unit="pot")
        self.db.save_dishy_message("session-a", "user", "Need a weekly budget dinner plan")
        self.db.save_dishy_message("session-a", "assistant", "Try traybakes and pasta")

        settings_ids = self._open_palette_with_query("settings").filtered_entry_ids()
        self.assertTrue(any(entry_id.startswith("settings:") for entry_id in settings_ids))

        yogurt_ids = self._open_palette_with_query("yogurt").filtered_entry_ids()
        self.assertTrue(any(entry_id.startswith("pantry_item:") for entry_id in yogurt_ids))
        self.assertTrue(any(entry_id.startswith("shopping_item:") for entry_id in yogurt_ids))

        dishy_ids = self._open_palette_with_query("budget").filtered_entry_ids()
        self.assertTrue(any(entry_id.startswith("dishy_session:") for entry_id in dishy_ids))

    def test_recipe_result_opens_detail_view(self):
        recipe_id = self._save_recipe("Harissa Chicken Traybake", tags=["Dinner"])

        self.assertTrue(self.window.run_command_palette_entry(f"recipe:{recipe_id}", query="harissa"))
        self._flush()

        self.assertEqual(self.window._stack.currentIndex(), 1)
        self.assertEqual(self.window._recipes_view._stack.currentIndex(), 2)
        self.assertEqual(self.window._recipes_view._current_recipe_db_id, recipe_id)

    def test_pantry_result_navigates_and_highlights_row(self):
        item_id = self.db.add_pantry_item("Halloumi", 1, "pack", "Fridge")

        self.assertTrue(self.window.run_command_palette_entry(f"pantry_item:{item_id}", query="halloumi"))
        self._flush()

        self.assertEqual(self.window._stack.currentIndex(), 4)
        self.assertEqual(self.window._my_kitchen_storage_view._current_tab, "Fridge")
        panel = self.window._my_kitchen_storage_view._panels["Fridge"]
        row = next(row for row in panel._rows if int(row._item.get("id") or 0) == item_id)
        self.assertTrue(row._highlighted)

    def test_shopping_result_navigates_and_highlights_row(self):
        item_id = self.db.add_shopping_item("Avocados", quantity="2", unit="")

        self.assertTrue(self.window.run_command_palette_entry(f"shopping_item:{item_id}", query="avocados"))
        self._flush()

        self.assertEqual(self.window._stack.currentIndex(), 5)
        row = next(row for row in self.window._shopping_view._all_items if int(row.db_id or 0) == item_id)
        self.assertTrue(row._highlighted)

    def test_meal_slot_result_opens_current_week_slot(self):
        recipe_id = self._save_recipe("Lemon Pasta", tags=["Dinner"])
        week_start = self.window._meal_planner_view.current_week_start_iso()
        self.db.set_meal_slot(week_start, "Monday", "dinner", custom_name="Lemon Pasta", recipe_id=recipe_id)
        slot_row = dict(self.db.get_meal_plan(week_start)[0])

        self.assertTrue(self.window.run_command_palette_entry(f"meal_slot:{slot_row['id']}", query="lemon"))
        self._flush()

        self.assertEqual(self.window._stack.currentIndex(), 2)
        self.assertTrue(self.window._meal_planner_view._slots[("Monday", "dinner")]._highlighted)

    def test_settings_result_opens_exact_section(self):
        self.assertTrue(self.window.run_command_palette_entry("settings:history", query="history"))
        self._flush()

        self.assertEqual(self.window._stack.currentIndex(), 8)
        self.assertEqual(
            self.window._settings_view._stack.currentIndex(),
            self.window._settings_view._page_index_by_key["history"],
        )

    def test_dishy_session_result_opens_selected_session(self):
        session_id = "session-42"
        self.db.save_dishy_message(session_id, "user", "Build me a high protein lunch plan")
        self.db.save_dishy_message(session_id, "assistant", "Try chicken bowls and wraps")

        self.assertTrue(self.window.run_command_palette_entry(f"dishy_session:{session_id}", query="protein"))
        self._flush()

        self.assertEqual(self.window._stack.currentIndex(), 6)
        self.assertEqual(self.window._dishy_view._session_id, session_id)

    def test_pantry_quick_add_validates_saves_and_records_recent(self):
        self.assertTrue(self.window.run_command_palette_entry("add_pantry_item"))
        palette = self.window._command_palette
        self.assertEqual(palette.active_form_id(), "add_pantry_item")

        palette.set_form_values({"name": "Eggs", "quantity": "12", "unit": "", "storage": "Fridge", "expiry_date": "2026-03-20"})
        self.window._on_palette_form_action("add_pantry_item", "primary", palette.current_form_values())
        self._flush()

        self.assertEqual(self.window._stack.currentIndex(), 4)
        self.assertEqual(self.window._my_kitchen_storage_view._current_tab, "Fridge")
        self.assertTrue(any(item["name"] == "Eggs" for item in self.db.get_pantry_items("Fridge")))

        recents = json.loads(self.db.get_setting("command_palette_recents", "[]"))
        self.assertEqual(recents[0]["id"], "add_pantry_item")

    def test_shopping_quick_add_saves_item(self):
        self.assertTrue(self.window.run_command_palette_entry("add_shopping_item"))
        palette = self.window._command_palette
        palette.set_form_values({"name": "Oats", "quantity": "2", "unit": "bags"})
        self.window._on_palette_form_action("add_shopping_item", "primary", palette.current_form_values())
        self._flush()

        self.assertEqual(self.window._stack.currentIndex(), 5)
        rows = [dict(row) for row in self.db.get_shopping_items()]
        self.assertTrue(any(row["name"] == "Oats" and row["quantity"] == "2" for row in rows))

    def test_nutrition_quick_add_looks_up_then_confirms_save(self):
        fake_estimate = {
            "food_name": "Overnight oats",
            "serving": "1 bowl",
            "kcal": 420,
            "protein_g": 21,
            "carbs_g": 48,
            "fat_g": 13,
            "fiber_g": 8,
            "sugar_g": 7,
        }
        self.assertTrue(self.window.run_command_palette_entry("log_nutrition"))
        palette = self.window._command_palette
        palette.set_form_values({"query": "overnight oats"})

        with patch.object(
            self.window._nutrition_view,
            "request_quick_estimate",
            side_effect=lambda query, on_result, on_error: on_result(fake_estimate),
        ):
            self.window._on_palette_form_action("log_nutrition", "primary", palette.current_form_values())
            self._flush()

        self.assertEqual(palette.active_form_id(), "log_nutrition")
        preview = palette.current_form_values()["_preview_payload"]["nutrition"]
        self.assertEqual(preview["food_name"], "Overnight oats")

        self.window._on_palette_form_action("log_nutrition", "primary", palette.current_form_values())
        self._flush()

        today = datetime.now().strftime("%Y-%m-%d")
        logs = [dict(row) for row in self.db.get_nutrition_logs(today)]
        self.assertTrue(any(row["food_name"] == "Overnight oats" for row in logs))
        self.assertEqual(self.window._stack.currentIndex(), 3)

    def test_plan_meal_quick_add_saves_to_active_week(self):
        recipe_id = self._save_recipe("Pesto Gnocchi", tags=["Dinner"])

        self.assertTrue(self.window.run_command_palette_entry("plan_meal"))
        palette = self.window._command_palette
        palette.set_form_values({"day": "Wednesday", "meal_type": "dinner", "recipe_query": "pesto gnoc"})
        self.window._on_palette_form_action("plan_meal", "primary", palette.current_form_values())
        self._flush()

        week_start = self.window._meal_planner_view.current_week_start_iso()
        rows = [dict(row) for row in self.db.get_meal_plan(week_start)]
        self.assertTrue(
            any(
                row["day_of_week"] == "Wednesday"
                and row["meal_type"] == "dinner"
                and int(row["recipe_id"] or 0) == recipe_id
                for row in rows
            )
        )
        self.assertEqual(self.window._stack.currentIndex(), 2)
        self.assertTrue(self.window._meal_planner_view._slots[("Wednesday", "dinner")]._highlighted)

    def test_plan_meal_recipe_field_suggests_saved_recipes_while_typing(self):
        self._save_recipe("Pesto_Gnocchi", tags=["Dinner_Fast"])
        self._save_recipe("Pesto Pasta Bake", tags=["Dinner"])
        self._save_recipe("Chicken_&_Stew", tags=["Comfort"])

        self.assertTrue(self.window.run_command_palette_entry("plan_meal"))
        palette = self.window._command_palette
        recipe_input = palette._form_widgets["recipe_query"]
        self.assertIsInstance(recipe_input, QLineEdit)
        self.assertEqual(palette.field_suggestion_titles("recipe_query"), [])

        recipe_input.setText("psto")
        self._flush()

        suggestions = palette.field_suggestion_titles("recipe_query")
        self.assertTrue(any("Pesto Gnocchi" in title for title in suggestions))
        self.assertTrue(any("Pesto Pasta Bake" in title for title in suggestions))
        self.assertFalse(any("Chicken & Stew" in title for title in suggestions))
        self.assertFalse(any("_" in title for title in suggestions))

    def test_recents_are_deduplicated_and_recency_ordered(self):
        self.assertTrue(self.window.run_command_palette_entry("open_recipes"))
        self.assertTrue(self.window.run_command_palette_entry("open_settings"))
        self.assertTrue(self.window.run_command_palette_entry("open_recipes"))

        recents = json.loads(self.db.get_setting("command_palette_recents", "[]"))
        self.assertEqual([item["id"] for item in recents[:2]], ["open_recipes", "open_settings"])
        self.assertEqual(sum(1 for item in recents if item["id"] == "open_recipes"), 1)

    def test_panel_actions_trigger_cloud_sync_when_recents_are_saved(self):
        with patch.object(self.window, "_trigger_cloud_sync") as trigger_sync:
            self.assertTrue(self.window.run_command_palette_entry("open_settings"))
        trigger_sync.assert_called()

    def test_unboxed_styles_apply_to_input_results_and_inline_fields(self):
        palette = self._open_palette_with_query("settings")
        self.assertIn("border: none", palette._input.styleSheet())

        entry_widget = None
        for row in range(palette._list.count()):
            widget = palette._list.itemWidget(palette._list.item(row))
            if isinstance(widget, _EntryRow):
                entry_widget = widget
                break
        self.assertIsNotNone(entry_widget)
        self.assertIn("border:none", entry_widget._body.styleSheet().replace(" ", ""))

        self.assertTrue(self.window.run_command_palette_entry("add_pantry_item"))
        self._flush()
        for widget in palette._form_widgets.values():
            if isinstance(widget, QLineEdit):
                self.assertIn("border: none", widget.styleSheet())
            else:
                self.assertIn("border: none", widget.styleSheet())

        self.assertTrue(self.window.run_command_palette_entry("plan_meal"))
        self._flush()
        day_combo = self.window._command_palette._form_widgets["day"]
        self.assertIsInstance(day_combo, QComboBox)
        combo_style = day_combo.styleSheet()
        self.assertIn("QAbstractItemView::item:selected", combo_style)
        self.assertIn("rgba(255,107,53", combo_style)

    def test_palette_does_not_open_when_another_modal_dialog_is_active(self):
        dialog = QDialog(self.window)
        dialog.setModal(True)
        dialog.show()
        self._flush()
        try:
            self.window.open_command_palette()
            self._flush()
            self.assertFalse(self.window._command_palette.isVisible())
        finally:
            dialog.close()
            dialog.deleteLater()
            self._flush()

    def test_clicking_outside_palette_closes_it(self):
        palette = self._open_palette_with_query("settings")
        self.assertTrue(palette.isVisible())

        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(8, 8))
        self._flush()

        self.assertFalse(palette.isVisible())


if __name__ == "__main__":
    unittest.main()
